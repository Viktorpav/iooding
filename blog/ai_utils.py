import json
import time
import logging
import asyncio

import httpx
from openai import AsyncOpenAI
from django.conf import settings
from django.core.cache import cache
from asgiref.sync import sync_to_async
from blog.redis_vectors import (
    search_similar_async,
    get_cached_embedding_async,
    cache_embedding_async,
    text_search_async,
)

logger = logging.getLogger(__name__)

# Skip RAG for these simple patterns or social queries
SKIP_RAG_PATTERNS = {
    'hi', 'hello', 'hey', 'thanks', 'bye', 'ok', 'yes', 'no', 'sure',
    'how are you', 'what is up', 'good morning', 'good evening', 'who are you',
    'whats up', "what's up", 'sup', 'yo', 'thank you', 'thx',
}

# Singleton instances
_ai_client = None
_httpx_client = None


def _get_httpx_client():
    """Reusable httpx client — avoids TCP/TLS handshake per request."""
    global _httpx_client
    if _httpx_client is None:
        _httpx_client = httpx.AsyncClient(timeout=300.0)
    return _httpx_client


class LocalAIClient:
    """
    Async-First Local AI Client (Ollama).
    Raw httpx streaming for zero-latency SSE — bypasses the OpenAI library buffer.
    """
    def __init__(self, host, api_key):
        base_url = host if host.endswith('/v1') else f"{host.rstrip('/')}/v1"
        self._base_url = base_url
        self._api_key = api_key
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=httpx.Timeout(120.0, connect=5.0),
        )
        self.completion_model = settings.AI_COMPLETION_MODEL
        self.embedding_model = settings.AI_EMBEDDING_MODEL

    async def list(self):
        return await self.client.models.list()

    async def generate(self, model, prompt, options=None):
        messages = [{"role": "user", "content": prompt}]
        try:
            resp = await self.client.chat.completions.create(
                model=self.completion_model,
                messages=messages,
                temperature=options.get("temperature", 0.7) if options else 0.7
            )
            return {"response": resp.choices[0].message.content}
        except Exception as e:
            logger.error(f"Local AI Generate Error: {e}")
            raise

    async def embeddings(self, model, prompt):
        try:
            resp = await self.client.embeddings.create(input=[prompt], model=self.embedding_model)
            return {"embedding": resp.data[0].embedding}
        except Exception as e:
            logger.error(f"Local AI Embeddings Error: {e}")
            raise

    async def chat(self, model, messages, stream, options=None):
        options = options or {}

        if not stream:
            resp = await self.client.chat.completions.create(
                model=self.completion_model,
                messages=messages,
                temperature=options.get("temperature", 0.7),
                top_p=options.get("top_p", 1.0),
            )
            return {"message": {"content": resp.choices[0].message.content}}

        # ── Raw httpx streaming ───────────────────────────────────────────────
        # Bypasses the OpenAI library's SSE parser which buffers chunks.
        # httpx.aiter_lines() yields each line the instant it arrives.
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self.completion_model,
            "messages": messages,
            "stream": True,
            "temperature": options.get("temperature", 0.7),
            "top_p": options.get("top_p", 1.0),
            # Ollama: cap context window to avoid RAM spikes on the Mac host
            "num_ctx": options.get("num_ctx", 4096),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async def generate_chunks():
            start_time = time.time()
            actual_chunks = 0
            http = _get_httpx_client()
            try:
                async with http.stream("POST", url, json=payload, headers=headers) as resp:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break
                        try:
                            data = json.loads(data_str)
                            choices = data.get("choices", [])
                            if choices:
                                content = choices[0].get("delta", {}).get("content") or ""
                                if content:
                                    actual_chunks += 1
                                    yield {"message": {"content": content}, "done": False}
                        except json.JSONDecodeError:
                            continue

                duration_ns = int((time.time() - start_time) * 1e9)
                yield {
                    "done": True,
                    "total_duration": duration_ns,
                    "eval_count": actual_chunks,
                    "eval_duration": duration_ns,
                }
            except Exception as e:
                logger.error(f"Raw stream error: {e}")
                raise

        return generate_chunks()


def get_ai_client():
    """Returns the consolidated Local AI client (Singleton)."""
    global _ai_client
    if _ai_client is None:
        _ai_client = LocalAIClient(
            host=settings.AI_HOST,
            api_key=settings.AI_API_KEY,
        )
    return _ai_client


async def check_ai_status():
    """Check if AI host is reachable and responding."""
    client = get_ai_client()
    try:
        await asyncio.wait_for(client.list(), timeout=2.0)
        return True
    except:
        return False

# ─── RAG Pipeline ─────────────────────────────────────────────────────────────

async def get_site_inventory() -> str:
    """Compact site inventory — cached for 5 minutes to avoid DB hits."""
    cached = cache.get("rag:site_inventory")
    if cached is not None:
        return cached

    from blog.models import Post
    from taggit.models import Tag

    @sync_to_async
    def _fetch():
        posts = list(Post.published.all().order_by('-publish')[:5])
        tags = list(Tag.objects.all().values_list('name', flat=True))
        return posts, tags

    try:
        posts, tags = await _fetch()
        if not posts:
            return 0, ""

        lines = [f"Blog: iooding.local | {len(posts)} articles | Tags: {', '.join(tags[:15])}"]
        for p in posts:
            lines.append(f"- \"{p.title}\" ({p.publish.strftime('%Y-%m-%d')}) → {p.get_absolute_url()}")

        result = (len(posts), "\n".join(lines))
        cache.set("rag:site_inventory", result, timeout=300)  # 5 min cache
        return result
    except Exception as e:
        logger.error(f"Site inventory error: {e}")
        return 0, ""


async def generate_rag_context(user_msg: str, client) -> str:
    """
    RAG pipeline optimized for speed:
    - Skip RAG for small talk
    - Embedding + text search run in TRUE parallel
    - Hard 1200 char context cap
    - Site inventory cached for 5 min
    """
    MAX_CONTEXT_CHARS = 1200

    try:
        msg_lower = user_msg.lower().strip()
        if msg_lower in SKIP_RAG_PATTERNS or len(msg_lower) < 3:
            return "NO_RAG_NEEDED"

        # ── Semantic Context Cache ────────────────────────────────────────────
        import hashlib
        msg_hash = hashlib.md5(msg_lower.encode()).hexdigest()[:16]
        cache_key = f"rag:context:{msg_hash}"
        cached_context = cache.get(cache_key)
        if cached_context:
            return cached_context

        post_count, site_inventory = await get_site_inventory()
        if post_count == 0:
            return "NO_RAG_NEEDED"

        # ── TRUE Parallel Search ──────────────────────────────────────────────
        # Fire text search AND embedding generation at the same time.
        text_results, vector_results = [], []

        async def _get_embedding():
            embedding = await get_cached_embedding_async(user_msg)
            if not embedding:
                emb_resp = await client.embeddings(model=None, prompt=user_msg)
                embedding = emb_resp['embedding']
                await cache_embedding_async(user_msg, embedding)
            return embedding

        try:
            text_task = text_search_async(user_msg, top_k=3)
            emb_task = _get_embedding()
            text_results, embedding = await asyncio.gather(
                text_task, emb_task, return_exceptions=True
            )

            if isinstance(text_results, Exception):
                logger.warning(f"Text search error: {text_results}")
                text_results = []
            if isinstance(embedding, Exception):
                logger.warning(f"Embedding error: {embedding}")
                embedding = None

            if embedding and not isinstance(embedding, Exception):
                vector_results = await search_similar_async(embedding, top_k=4, max_distance=0.55)
        except Exception as e:
            logger.warning(f"RAG search error: {e}")

        # ── Rank & Deduplicate ────────────────────────────────────────────────
        seen, ranked = set(), []
        for match in list(vector_results) + list(text_results):
            key = match.get('content', '')[:80]
            if key and key not in seen:
                seen.add(key)
                ranked.append(match)

        if not ranked:
            return site_inventory

        context_parts = []
        total_chars = 0
        for chunk in ranked:
            title = chunk.get('title', 'Unknown')
            snippet = chunk.get('content', '')[:500].strip()
            if not snippet:
                continue
            entry = f"### {title}\n{snippet}"
            if total_chars + len(entry) > MAX_CONTEXT_CHARS:
                break
            context_parts.append(entry)
            total_chars += len(entry)

        if not context_parts:
            final_context = site_inventory
        else:
            final_context = site_inventory + "\n\n" + "\n\n".join(context_parts)

        # Store in cache for 5 minutes (300s)
        cache.set(cache_key, final_context, timeout=300)
        return final_context

    except Exception as e:
        logger.error(f"RAG pipeline error: {e}")
        return "NO_RAG_NEEDED"


def get_rag_system_prompt(context: str) -> str:
    """System prompt kept minimal to reduce prefill tokens → faster first output token."""
    return (
        "You are Ding AI for iooding.local. Answer using the blog content below. "
        "Use markdown. Link posts as [Title](url). Be concise.\n\n"
        f"--- Blog ---\n{context}\n---"
    )

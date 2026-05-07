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
    Async-First Local AI Client (Ollama / LM Studio / vLLM).
    Optimized for zero-latency streaming and resource efficiency.
    """
    def __init__(self, host, api_key):
        base_url = host if host.endswith('/v1') else f"{host.rstrip('/')}/v1"
        self._base_url = base_url
        self._api_key = api_key
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=httpx.Timeout(120.0, connect=5.0), # Fail fast on connection
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
            logger.error(f"LM Studio Generate Error: {e}")
            raise

    async def embeddings(self, model, prompt):
        try:
            resp = await self.client.embeddings.create(input=[prompt], model=self.embedding_model)
            return {"embedding": resp.data[0].embedding}
        except Exception as e:
            logger.error(f"Local AI Embeddings Error: {e}")
            raise

    async def chat(self, messages, stream, options=None):
        """Unified chat method with built-in resilience and Ollama tuning."""
        options = options or {}
        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self.completion_model,
            "messages": messages,
            "stream": stream,
            "temperature": options.get("temperature", 0.2),
            "num_ctx": options.get("num_ctx", 4096),
            "stream_options": {"include_usage": True} if stream else None,
        }

        if not stream:
            try:
                resp = await self.client.chat.completions.create(**payload)
                return {"message": {"content": resp.choices[0].message.content}}
            except Exception as e:
                logger.error(f"Chat error: {e}")
                raise

        async def generate_chunks():
            start_time = time.time()
            http = _get_httpx_client()
            for attempt in range(3):
                try:
                    async with http.stream("POST", url, json=payload, headers={"Authorization": f"Bearer {self._api_key}"}) as resp:
                        async for line in resp.aiter_lines():
                            if not line.startswith("data: "): continue
                            data_str = line[6:].strip()
                            if data_str == "[DONE]": break
                            try:
                                data = json.loads(data_str)
                                choices = data.get('choices', [])
                                if choices:
                                    content = choices[0].get('delta', {}).get('content')
                                    if content: yield {"content": content}
                                
                                # Capture usage metrics from the final chunk
                                if 'usage' in data:
                                    yield {
                                        "done": True,
                                        "total_duration": time.time() - start_time,
                                        "eval_count": data['usage'].get('completion_tokens', 0),
                                        "prompt_count": data['usage'].get('prompt_tokens', 0),
                                    }
                            except (KeyError, json.JSONDecodeError): continue
                    return
                except Exception as e:
                    if attempt == 2: yield {"error": str(e)}
                    await asyncio.sleep(1)

        return generate_chunks()


def get_ai_client():
    """Returns the consolidated local AI client (Singleton)."""
    global _ai_client
    if _ai_client is None:
        _ai_client = LocalAIClient(
            host=settings.AI_HOST,
            api_key=settings.AI_API_KEY
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
    - Hard 1500 char context cap
    - Site inventory cached for 5 min
    """
    MAX_CONTEXT_CHARS = 1200

    try:
        msg_lower = user_msg.lower().strip()
        if msg_lower in SKIP_RAG_PATTERNS or len(msg_lower) < 3:
            return "NO_RAG_NEEDED"

        post_count, site_inventory = await get_site_inventory()
        if post_count == 0:
            return "NO_RAG_NEEDED"

        # ── TRUE Parallel Search ──────────────────────────────────────────────
        # Fire text search AND embedding generation at the same time.
        # Previously embedding blocked before vector search could even start.
        text_results, vector_results = [], []

        async def _get_embedding():
            embedding = await get_cached_embedding_async(user_msg)
            if not embedding:
                emb_resp = await client.embeddings(model=None, prompt=user_msg)
                embedding = emb_resp['embedding']
                await cache_embedding_async(user_msg, embedding)
            return embedding

        try:
            # Run text search + embedding generation in parallel
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

            # Vector search needs the embedding, so it runs after
            if embedding and not isinstance(embedding, Exception):
                vector_results = await search_similar_async(embedding, top_k=4, max_distance=0.55) # Tighter threshold
        except Exception as e:
            logger.warning(f"RAG search error: {e}")

        # ── Rank & Deduplicate ────────────────────────────────────────────────
        seen, ranked = set(), []
        for match in list(vector_results) + list(text_results):
            key = match.get('content', '')[:80]
            if key and key not in seen:
                seen.add(key)
                ranked.append(match)

        # ── Trim to 1500 chars ────────────────────────────────────────────────
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
            return site_inventory

        return site_inventory + "\n\n" + "\n\n".join(context_parts)

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


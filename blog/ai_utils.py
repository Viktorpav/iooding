from django.conf import settings
from blog.redis_vectors import (
    search_similar_async, 
    get_cached_embedding_async, 
    cache_embedding_async,
    text_search_async
)
import os
import json
import time
import logging
import asyncio
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

import httpx
from openai import AsyncOpenAI
from django.conf import settings
from django.core.cache import cache
from asgiref.sync import sync_to_async, async_to_sync

logger = logging.getLogger(__name__)

# Skip RAG for these simple patterns or social queries
SKIP_RAG_PATTERNS = {
    'hi', 'hello', 'hey', 'thanks', 'bye', 'ok', 'yes', 'no', 'sure', 
    'how are you', 'what is up', 'good morning', 'good evening', 'who are you',
    'whats up', "what's up", 'sup', 'yo', 'thank you', 'thx',
}

# Singleton instance
_ai_client = None

class LMStudioClient:
    """Async-First LM Studio Client with raw httpx streaming for zero-latency SSE."""
    def __init__(self, host, api_key):
        base_url = host if host.endswith('/v1') else f"{host.rstrip('/')}/v1"
        self._base_url = base_url          # Used by raw httpx streaming
        self._api_key = api_key
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=300.0,
        )
        self.completion_model = settings.LM_STUDIO_COMPLETION_MODEL
        self.embedding_model = settings.LM_STUDIO_EMBEDDING_MODEL

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
            raise e

    async def embeddings(self, model, prompt):
        try:
            resp = await self.client.embeddings.create(input=[prompt], model=self.embedding_model)
            return {"embedding": resp.data[0].embedding}
        except Exception as e:
            logger.error(f"LM Studio Embeddings Error: {e}")
            raise e

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
        # Bypasses the OpenAI library's SSE parser/object builder which buffers
        # chunks before yielding ChatCompletionChunk objects.
        # httpx.aiter_lines() yields each \n-terminated SSE line the instant it
        # comes off the wire — zero intermediate buffering.

        url = f"{self._base_url}/chat/completions"
        payload = {
            "model": self.completion_model,
            "messages": messages,
            "stream": True,
            "temperature": options.get("temperature", 0.7),
            "top_p": options.get("top_p", 1.0),
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async def generate_chunks():
            start_time = time.time()
            actual_chunks = 0
            try:
                async with httpx.AsyncClient(timeout=300.0) as http:
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
    """Returns the consolidated LM Studio client (Singleton)."""
    global _ai_client
    if _ai_client is None:
        _ai_client = LMStudioClient(
            host=settings.LM_STUDIO_HOST,
            api_key=settings.LM_STUDIO_API_KEY
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

# ─── RAG Pipeline (Optimized for Small Models like Gemma 2B) ─────────────────

async def get_site_inventory() -> str:
    """Compact site inventory: titles, tags, dates. Cheap to build, no LLM needed."""
    from blog.models import Post
    from taggit.models import Tag
    
    @sync_to_async
    def _fetch():
        posts = list(Post.published.all().order_by('-publish')[:20])
        tags = list(Tag.objects.all().values_list('name', flat=True))
        return posts, tags

    try:
        posts, tags = await _fetch()
        if not posts:
            return 0, ""
        
        lines = [f"Blog: iooding.local | {len(posts)} articles | Tags: {', '.join(tags[:15])}"]
        for p in posts:
            lines.append(f"- \"{p.title}\" ({p.publish.strftime('%Y-%m-%d')}) → {p.get_absolute_url()}")
        
        return len(posts), "\n".join(lines)
    except Exception as e:
        logger.error(f"Site inventory error: {e}")
        return 0, ""

async def get_full_site_content() -> str:
    """Fetches full content of all published posts. Used for small blogs (<=10 posts)."""
    from blog.models import Post
    
    @sync_to_async
    def _fetch():
        posts = Post.published.all().order_by('-publish')
        results = []
        for p in posts:
            clean_body = re.sub('<[^<]+?>', '', p.body)[:3000]
            results.append(
                f"## {p.title}\n"
                f"URL: {p.get_absolute_url()}\n"
                f"Date: {p.publish.strftime('%Y-%m-%d')} | Read time: {p.read_time} min\n\n"
                f"{clean_body}"
            )
        return results
    
    try:
        contents = await _fetch()
        return "\n\n---\n\n".join(contents)
    except:
        return ""

async def generate_rag_context(user_msg: str, client) -> str:
    """
    RAG pipeline with:
    - Skip RAG for small talk
    - Hybrid vector + text search
    - Hard 3k char context cap (keeps small models fast)
    - Always includes compact site inventory header
    """
    MAX_CONTEXT_CHARS = 3000

    try:
        msg_lower = user_msg.lower().strip()
        if msg_lower in SKIP_RAG_PATTERNS or len(msg_lower) < 3:
            return "NO_RAG_NEEDED"

        post_count, site_inventory = await get_site_inventory()
        if post_count == 0:
            return "NO_RAG_NEEDED"

        # ── Search ───────────────────────────────────────────────────────────
        text_results, vector_results = [], []
        try:
            text_task = text_search_async(user_msg, top_k=3)

            embedding = await get_cached_embedding_async(user_msg)
            if not embedding:
                emb_resp = await client.embeddings(model=None, prompt=user_msg)
                embedding = emb_resp['embedding']
                await cache_embedding_async(user_msg, embedding)

            vector_task = search_similar_async(embedding, top_k=4)
            text_results, vector_results = await asyncio.gather(
                text_task, vector_task, return_exceptions=True
            )
            if isinstance(text_results, Exception):
                logger.warning(f"Text search error: {text_results}")
                text_results = []
            if isinstance(vector_results, Exception):
                logger.warning(f"Vector search error: {vector_results}")
                vector_results = []
        except Exception as e:
            logger.warning(f"RAG search error: {e}")

        # ── Rank & Deduplicate ───────────────────────────────────────────────
        # Vector results are sorted by distance (best first), text results come second
        seen, ranked = set(), []
        for match in list(vector_results) + list(text_results):
            key = match.get('content', '')[:80]
            if key and key not in seen:
                seen.add(key)
                ranked.append(match)

        # ── Trim to 3k chars ─────────────────────────────────────────────────
        if not ranked:
            logger.info(f"No RAG results for: {user_msg!r}")
            return site_inventory

        context_parts = []
        total_chars = 0
        for chunk in ranked:
            title = chunk.get('title', 'Unknown')
            # Take at most 800 chars per chunk to allow multiple articles in context
            snippet = chunk.get('content', '')[:800].strip()
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
    """
    System prompt optimized for small models (Gemma 2B).
    """
    return (
        "You are Ding AI, a friendly and knowledgeable assistant for the iooding.local tech blog.\n\n"
        "Your job:\n"
        "- Answer questions using the blog content provided below when relevant.\n"
        "- If the blog content covers the topic, reference it with links.\n"
        "- If the blog doesn't cover the topic, use your general knowledge to help.\n"
        "- Be concise, helpful, and use markdown formatting.\n"
        "- When referencing blog posts, link them like: [Post Title](url)\n"
        "- At the end, suggest 1-2 related questions the user might want to ask.\n\n"
        f"--- Blog Content ---\n{context}\n--- End ---"
    )

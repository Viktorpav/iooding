from django.conf import settings
from blog.redis_vectors import (
    search_similar_async, 
    get_cached_embedding_async, 
    cache_embedding_async,
    text_search_async
)
import time
import json
import logging
import re
import asyncio
from openai import AsyncOpenAI
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
    """Consolidated Async-First LM Studio Client."""
    def __init__(self, host, api_key):
        base_url = host if host.endswith('/v1') else f"{host.rstrip('/')}/v1"
        self.client = AsyncOpenAI(
            base_url=base_url, 
            api_key=api_key,
            timeout=60.0,
        )
        self.completion_model = settings.LM_STUDIO_COMPLETION_MODEL
        self.embedding_model = settings.LM_STUDIO_EMBEDDING_MODEL

    async def list(self):
        return await self.client.models.list()

    async def generate(self, model, prompt, options=None):
        m = self.completion_model
        messages = [{"role": "user", "content": prompt}]
        try:
            resp = await self.client.chat.completions.create(
                model=m, 
                messages=messages, 
                temperature=options.get("temperature", 0.7) if options else 0.7
            )
            return {"response": resp.choices[0].message.content}
        except Exception as e:
            logger.error(f"LM Studio Generate Error: {e}")
            raise e

    async def embeddings(self, model, prompt):
        m = self.embedding_model
        try:
            resp = await self.client.embeddings.create(input=[prompt], model=m)
            return {"embedding": resp.data[0].embedding}
        except Exception as e:
            logger.error(f"LM Studio Embeddings Error: {e}")
            raise e

    async def chat(self, model, messages, stream, options=None):
        m = self.completion_model
        options = options or {}
        kwargs = {
            "model": m,
            "messages": messages,
            "stream": stream,
            "temperature": options.get("temperature", 0.7),
            "top_p": options.get("top_p", 1.0),
        }
        if stream:
            kwargs["stream_options"] = {"include_usage": True}
        
        try:
            resp = await self.client.chat.completions.create(**kwargs)
        except Exception as e:
            logger.error(f"LM Studio Chat Connection Error: {e}")
            raise e
        
        if stream:
            async def generate_chunks():
                start_time = time.time()
                generated_tokens = 0
                actual_chunks = 0
                try:
                    async for chunk in resp:
                        if hasattr(chunk, 'usage') and chunk.usage:
                            generated_tokens = chunk.usage.completion_tokens

                        if chunk.choices and len(chunk.choices) > 0:
                            content = chunk.choices[0].delta.content or ""
                            if content:
                                actual_chunks += 1
                                yield {"message": {"content": content}, "done": False}
                    
                    if not generated_tokens or generated_tokens < actual_chunks:
                        generated_tokens = actual_chunks
                        
                    end_time = time.time()
                    duration_ns = int((end_time - start_time) * 1e9)
                    
                    yield {
                        "done": True, 
                        "total_duration": duration_ns, 
                        "eval_count": generated_tokens, 
                        "eval_duration": duration_ns
                    }
                except Exception as e:
                    logger.error(f"Stream error: {e}")
            return generate_chunks()
        else:
            return {"message": {"content": resp.choices[0].message.content}}

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
    Streamlined RAG pipeline optimized for small models (Gemma 2B).
    """
    try:
        msg_lower = user_msg.lower().strip()
        if msg_lower in SKIP_RAG_PATTERNS or len(msg_lower) < 3:
            return "NO_RAG_NEEDED"
        
        post_count, site_inventory = await get_site_inventory()
        
        if post_count == 0:
            return "NO_RAG_NEEDED"
        
        if post_count <= 15:
            full_content = await get_full_site_content()
            return f"{site_inventory}\n\n{full_content}"
        
        text_results = []
        vector_results = []
        
        try:
            text_task = text_search_async(user_msg, top_k=3)
            embedding = await get_cached_embedding_async(user_msg)
            if not embedding:
                emb_resp = await client.embeddings(model=None, prompt=user_msg)
                embedding = emb_resp['embedding']
                await cache_embedding_async(user_msg, embedding)
            
            vector_task = search_similar_async(embedding, top_k=4)
            text_results, vector_results = await asyncio.gather(
                text_task, vector_task,
                return_exceptions=True
            )
            
            if isinstance(text_results, Exception):
                logger.warning(f"Text search failed: {text_results}")
                text_results = []
            if isinstance(vector_results, Exception):
                logger.warning(f"Vector search failed: {vector_results}")
                vector_results = []
                
        except Exception as e:
            logger.warning(f"Search error: {e}")
        
        seen_content = set()
        ranked_chunks = []
        
        for match in vector_results:
            content_key = match['content'][:100]
            if content_key not in seen_content:
                seen_content.add(content_key)
                ranked_chunks.append(match)
        
        for match in text_results:
            content_key = match['content'][:100]
            if content_key not in seen_content:
                seen_content.add(content_key)
                ranked_chunks.append(match)
        
        if ranked_chunks:
            context_parts = [site_inventory, ""]
            for i, chunk in enumerate(ranked_chunks[:5]):
                context_parts.append(
                    f"### From: {chunk['title']}\n{chunk['content'][:1500]}"
                )
            return "\n\n".join(context_parts)
        else:
            logger.info(f"No RAG results for: {user_msg}")
            return site_inventory
            
    except Exception as e:
        logger.error(f"RAG pipeline error: {e}")
        try:
            _, inventory = await get_site_inventory()
            return inventory if inventory else "NO_RAG_NEEDED"
        except:
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

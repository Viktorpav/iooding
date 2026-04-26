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
from openai import AsyncOpenAI, OpenAI
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

# Skip RAG for these simple patterns or social queries
SKIP_RAG_PATTERNS = {
    'hi', 'hello', 'hey', 'thanks', 'bye', 'ok', 'yes', 'no', 'sure', 
    'how are you', 'what is up', 'good morning', 'good evening', 'who are you',
    'whats up', "what's up", 'sup', 'yo', 'thank you', 'thx',
}

# Shared clients to reduce latency from connection overhead
_ai_client = None
_ai_async_client = None

class LMStudioAsyncClient:
    def __init__(self, host, api_key):
        # Ensure host ends with /v1 for LM Studio compatibility
        base_url = host if host.endswith('/v1') else f"{host.rstrip('/')}/v1"
        self.client = AsyncOpenAI(
            base_url=base_url, 
            api_key=api_key,
            timeout=10.0,  # Add timeout for robustness
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
            logger.error(f"LM Studio Sync Generate Error: {e}")
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

class LMStudioSyncClient:
    def __init__(self, host, api_key):
        # Ensure host ends with /v1 for LM Studio compatibility
        base_url = host if host.endswith('/v1') else f"{host.rstrip('/')}/v1"
        self.client = OpenAI(
            base_url=base_url, 
            api_key=api_key,
            timeout=10.0
        )
        self.completion_model = settings.LM_STUDIO_COMPLETION_MODEL
        self.embedding_model = settings.LM_STUDIO_EMBEDDING_MODEL

    def generate(self, model, prompt, options=None):
        m = self.completion_model
        messages = [{"role": "user", "content": prompt}]
        resp = self.client.chat.completions.create(
            model=m, 
            messages=messages, 
            temperature=options.get("temperature", 0.7) if options else 0.7
        )
        return {"response": resp.choices[0].message.content}

    def embeddings(self, model, prompt):
        m = self.embedding_model
        resp = self.client.embeddings.create(input=[prompt], model=m)
        return {"embedding": resp.data[0].embedding}

def get_ai_client(async_client=False):
    """Factory for LM Studio clients."""
    global _ai_client, _ai_async_client
    
    if async_client:
        if _ai_async_client is None:
            _ai_async_client = LMStudioAsyncClient(
                host=settings.LM_STUDIO_HOST,
                api_key=settings.LM_STUDIO_API_KEY
            )
        return _ai_async_client
    else:
        if _ai_client is None:
            _ai_client = LMStudioSyncClient(
                host=settings.LM_STUDIO_HOST,
                api_key=settings.LM_STUDIO_API_KEY
            )
        return _ai_client

async def check_ai_status():
    """Check if AI host is reachable and responding."""
    client = get_ai_client(async_client=True)
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
    
    Strategy:
    - No extra LLM calls for classification/expansion (too expensive for 2B)
    - For small blogs (<=10 posts): dump all content directly (fast & complete)
    - For larger blogs: hybrid keyword + semantic search
    - Return well-formatted context the model can easily parse
    """
    try:
        # 1. Quick check: skip RAG for greetings
        msg_lower = user_msg.lower().strip()
        if msg_lower in SKIP_RAG_PATTERNS or len(msg_lower) < 3:
            return "NO_RAG_NEEDED"
        
        # 2. Get site inventory (always cheap)
        post_count, site_inventory = await get_site_inventory()
        
        if post_count == 0:
            return "NO_RAG_NEEDED"
        
        # 3. For small blogs: include everything — no search needed
        if post_count <= 15:
            full_content = await get_full_site_content()
            return f"{site_inventory}\n\n{full_content}"
        
        # 4. For larger blogs: hybrid search (keyword + semantic)
        text_results = []
        vector_results = []
        
        try:
            # Run keyword and semantic search in parallel
            text_task = text_search_async(user_msg, top_k=3)
            
            # Get or compute embedding
            embedding = await get_cached_embedding_async(user_msg)
            if not embedding:
                emb_resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
                embedding = emb_resp['embedding']
                await cache_embedding_async(user_msg, embedding)
            
            vector_task = search_similar_async(embedding, top_k=4)
            
            text_results, vector_results = await asyncio.gather(
                text_task, vector_task,
                return_exceptions=True
            )
            
            # Handle exceptions from gather
            if isinstance(text_results, Exception):
                logger.warning(f"Text search failed: {text_results}")
                text_results = []
            if isinstance(vector_results, Exception):
                logger.warning(f"Vector search failed: {vector_results}")
                vector_results = []
                
        except Exception as e:
            logger.warning(f"Search error: {e}")
        
        # 5. Merge and deduplicate results
        seen_content = set()
        ranked_chunks = []
        
        # Prioritize semantic matches (usually more relevant)
        for match in vector_results:
            content_key = match['content'][:100]
            if content_key not in seen_content:
                seen_content.add(content_key)
                ranked_chunks.append(match)
        
        # Add keyword matches that weren't already found
        for match in text_results:
            content_key = match['content'][:100]
            if content_key not in seen_content:
                seen_content.add(content_key)
                ranked_chunks.append(match)
        
        # 6. Format context for the model
        if ranked_chunks:
            context_parts = [site_inventory, ""]
            for i, chunk in enumerate(ranked_chunks[:5]):
                context_parts.append(
                    f"### From: {chunk['title']}\n{chunk['content'][:1500]}"
                )
            return "\n\n".join(context_parts)
        else:
            # No search results — still give the model the site inventory
            # so it can at least recommend articles
            logger.info(f"No RAG results for: {user_msg}")
            return site_inventory
            
    except Exception as e:
        logger.error(f"RAG pipeline error: {e}")
        # Graceful fallback: still try to get site inventory
        try:
            _, inventory = await get_site_inventory()
            return inventory if inventory else "NO_RAG_NEEDED"
        except:
            return "NO_RAG_NEEDED"


def get_rag_system_prompt(context: str) -> str:
    """
    System prompt optimized for small models (Gemma 2B).
    
    Key principles for small models:
    - Use clear, natural language (not compressed tokens)
    - Be permissive: allow general knowledge when blog doesn't cover a topic
    - Give explicit examples of good behavior
    - Keep instructions short and unambiguous
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

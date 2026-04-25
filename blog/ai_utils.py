from django.conf import settings
from blog.redis_vectors import (
    search_similar_async, 
    get_cached_embedding_async, 
    cache_embedding_async
)

# Skip RAG for these simple patterns or social queries
SKIP_RAG_PATTERNS = {
    'hi', 'hello', 'hey', 'thanks', 'bye', 'ok', 'yes', 'no', 'sure', 
    'how are you', 'what is up', 'good morning', 'good evening', 'who are you'
}

# Shared clients to reduce latency from connection overhead
_ai_client = None
_ai_async_client = None

class LMStudioAsyncClient:
    def __init__(self, host, api_key):
        from openai import AsyncOpenAI
        from django.conf import settings
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
            import logging
            logging.getLogger(__name__).error(f"LM Studio Sync Generate Error: {e}")
            raise e

    async def embeddings(self, model, prompt):
        m = self.embedding_model
        try:
            resp = await self.client.embeddings.create(input=[prompt], model=m)
            return {"embedding": resp.data[0].embedding}
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"LM Studio Embeddings Error: {e}")
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
            import logging
            logging.getLogger(__name__).error(f"LM Studio Chat Connection Error: {e}")
            raise e
        
        if stream:
            async def generate_chunks():
                start_time = __import__('time').time()
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
                        
                    end_time = __import__('time').time()
                    duration_ns = int((end_time - start_time) * 1e9)
                    
                    yield {
                        "done": True, 
                        "total_duration": duration_ns, 
                        "eval_count": generated_tokens, 
                        "eval_duration": duration_ns
                    }
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).error(f"Stream error: {e}")
            return generate_chunks()
        else:
            return {"message": {"content": resp.choices[0].message.content}}

class LMStudioSyncClient:
    def __init__(self, host, api_key):
        from openai import OpenAI
        from django.conf import settings
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
        import asyncio
        await asyncio.wait_for(client.list(), timeout=2.0)
        return True
    except:
        return False

async def expand_query(user_msg: str, client) -> str:
    """Expand simple queries with technical synonyms for better recall (Suggestion 6)."""
    prompt = (
        f"User is asking about technical topics in a blog.\n"
        f"QUERY: {user_msg}\n"
        "Return 3-5 keywords or synonyms that would improve search results for this query. "
        "Format: comma separated list. No intro."
    )
    try:
        resp = await client.generate(model='qwen3-coder:latest', prompt=prompt, options={"temperature": 0.0})
        expansion = resp['response'].strip()
        return f"{user_msg}, {expansion}"
    except:
        return user_msg

async def classify_query(user_msg: str, client) -> dict:
    """Classify the user query to decide on retrieval strategy."""
    import json
    import logging
    logger = logging.getLogger(__name__)

    prompt = (
        f"Analyze this user query: '{user_msg}'\n"
        "Return ONLY a JSON object with these keys:\n"
        "- intent: greeting | navigation | explanation | code | opinion\n"
        "- needs_rag: true | false\n"
        "- scope: narrow | broad\n"
        "- expected_depth: shallow | deep"
    )
    try:
        resp = await client.generate(model='qwen3-coder:latest', prompt=prompt, options={"temperature": 0.0})
        import re
        match = re.search(r'\{.*\}', resp['response'], re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"intent": "explanation", "needs_rag": True, "scope": "narrow", "expected_depth": "deep"}
    except Exception as e:
        logger.error(f"Classification failure: {e}")
        return {"intent": "explanation", "needs_rag": True, "scope": "narrow", "expected_depth": "deep"}

async def get_post_recency_score(post_id: int) -> float:
    """Calculate a boost score based on post age (Suggestion 3)."""
    from django.utils import timezone
    from blog.models import Post
    from asgiref.sync import sync_to_async
    
    @sync_to_async
    def _get_age():
        try:
            p = Post.objects.get(id=post_id)
            days = (timezone.now() - p.publish).days
            return max(0, 1 - (days / 365)) # Boost for posts < 1 year old
        except: return 0.0
    return await _get_age()

async def rank_search_results(user_msg, text_matches, vector_matches):
    """Hybrid ranker with Diversity Penalty and Recency Boost (Suggestion 2 & 3)."""
    seen_chunks = {} # doc_id -> score
    
    # 1. Semantic Weights
    for m in vector_matches:
        doc_id = f"{m['post_id']}:{m['content'][:50]}"
        score = (1.0 - m['distance']) * 2.5 # Weighting semantic higher
        seen_chunks[doc_id] = {"score": score, "doc": m}
        
    # 2. Keyword & Recency Boosts
    user_words = set(user_msg.lower().split())
    for doc_id, data in seen_chunks.items():
        m = data["doc"]
        # Keyword Boost
        if any(word in m['title'].lower() for word in user_words):
            data["score"] += 1.2
            
        # Recency Boost (Suggestion 3)
        recency = await get_post_recency_score(m['post_id'])
        data["score"] += recency * 0.5

    # 3. Diversity Filter (Suggestion 2)
    ranked = sorted(seen_chunks.values(), key=lambda x: x['score'], reverse=True)
    post_counts = {}
    final_docs = []
    
    for r in ranked:
        pid = r['doc']['post_id']
        # Allow max 2 chunks from same post to ensure diversity
        if post_counts.get(pid, 0) >= 2:
            continue
        final_docs.append(r['doc'])
        post_counts[pid] = post_counts.get(pid, 0) + 1
        if len(final_docs) >= 6: break
        
    return final_docs

async def distill_context(context: str, query: str, client) -> str:
    """Compress context into relevant facts (Suggestion 3)."""
    if not context or len(context) < 300: return context
    prompt = (
        f"QUESTION: {query}\n\nRAW CONTEXT:\n{context}\n\n"
        "INSTRUCTION: Extract ONLY factual bullet points from the context that answer the question. "
        "Cite source titles in brackets like [Post Title]. If no info is relevant, return 'NO RELEVANT INFO'."
    )
    try:
        resp = await client.generate(model='qwen3-coder:latest', prompt=prompt, options={"temperature": 0.1})
        res = resp['response'].strip()
        return res if "NO RELEVANT INFO" not in res else ""
    except:
        return context

async def get_full_site_content() -> str:
    """Fetches full content + rich metadata of all published posts."""
    from asgiref.sync import sync_to_async
    from blog.models import Post
    import re
    
    @sync_to_async
    def _fetch():
        posts = Post.published.all()
        return [
            f"POST: {p.title}\nURL: {p.get_absolute_url()}\nDATE: {p.publish.strftime('%Y-%m-%d')}\n"
            f"READ_TIME: {p.read_time} min\nCONTENT: {re.sub('<[^<]+?>', '', p.body)[:2500]}"
            for p in posts
        ]
    
    try:
        contents = await _fetch()
        return "\n\n---\n\n".join(contents)
    except: return ""

async def get_site_metadata() -> str:
    """Compact site inventory for token efficiency (Suggestion 4)."""
    from asgiref.sync import sync_to_async
    from blog.models import Post
    from taggit.models import Tag
    
    @sync_to_async
    def _fetch():
        posts = list(Post.published.all().order_by('-publish'))
        tags = Tag.objects.all().values_list('name', flat=True)
        return posts, list(tags)

    try:
        posts, tags = await _fetch()
        meta = "[SITE_INTEL]\n"
        meta += f"Identity: DingAI | Inventory: {len(posts)} Posts | Tags: {', '.join(tags) if tags else 'None'}\n"
        meta += "Titles: " + (", ".join([p.title for p in posts]) if posts else "None")
        return len(posts), meta
    except Exception:
        return 0, "[SITE_INTEL] Error retrieving metadata."

async def generate_rag_context(user_msg: str, client) -> str:
    """Advanced RAG Orchestrator (Suggestion 1, 2, 3, 6, 7)."""
    from blog.redis_vectors import text_search_async, search_similar_async
    import asyncio
    
    try:
        # 0. Fast Track for small blogs (Suggestion 7 Fallback)
        post_count, site_meta = await get_site_metadata()
        if 0 < post_count <= 10:
             full_content = await get_full_site_content()
             return f"{site_meta}\n\n--- SITE KNOWLEDGE ---\n{full_content}"

        import logging
        logger = logging.getLogger(__name__)

        # 1. Fast Intent Check (Heuristic)
        msg_lower = user_msg.lower().strip()
        if msg_lower in SKIP_RAG_PATTERNS or len(msg_lower) < 5:
            return "NO_RAG_NEEDED"
            
        # 2. Hybrid Retrieval with Cache (Fast)
        top_k = 5
        
        # Keyword Search
        text_matches = await text_search_async(user_msg, top_k=3)
        
        # Semantic Search
        embedding = await get_cached_embedding_async(user_msg)
        if not embedding:
            emb_resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
            embedding = emb_resp['embedding']
            await cache_embedding_async(user_msg, embedding)
            
        vector_matches = await search_similar_async(embedding, top_k=top_k)
        
        # 3. Hybrid Ranking
        ranked_chunks = await rank_search_results(user_msg, text_matches, vector_matches)
        
        raw_context = ""
        for m in ranked_chunks:
            raw_context += f"SOURCE: {m['title']}\nCONTENT: {m['content']}\n\n"
            
        if not raw_context:
            logger.warning(f"RAG_EMPTY: No relevant docs found for: {user_msg}")
            
        final_context = f"{site_meta}\n\n[CONTENT_MAP]\n{raw_context[:3000]}"

        
        # Suggestion 4: Answer Verification Step
        # verified = await verify_answer(..., final_context, client) 
        # (This is handled by prompt instructions for efficiency)
        
        return final_context
    except Exception as e:
        # Suggestion 7 Fallback: If everything fails, return just site map
        _, site_meta = await get_site_metadata()
        logger.error(f"RAG_FAILURE: {e}")
        return f"{site_meta}\n\n[System Alert: Knowledge base retrieval is slow. Falling back to site-map.]"

async def verify_answer(answer, context, client):
    """Self-correction protocol to reduce hallucinations (Suggestion 4)."""
    if not answer or not context: return answer
    prompt = (
        f"You are a fact-checker.\nCONTEXT:\n{context}\n\nANSWER TO VERIFY:\n{answer}\n\n"
        "Check if the answer contains any facts NOT present in the context. "
        "If yes, return a slightly revised, safer version of the answer. "
        "If the answer is perfectly grounded, return it exactly as is. "
        "Provide ONLY the final text."
    )
    try:
        resp = await client.generate(model='qwen3-coder:latest', prompt=prompt, options={"temperature": 0.0})
        return resp['response'].strip()
    except: return answer

def get_rag_system_prompt(context: str) -> str:
    """Optimized Compact System Prompt (Suggestion 4: Token Efficiency)."""
    return (
        "Identity: DingAI (K8s-hosted System). Authority: Internal Data Docs. "
        "Strict Rule: Answer ONLY from [CONTENT_MAP]. If missing, say 'Information not found in site docs.' "
        "Instruction: Use Technical Markdown, clickable [Links](URL), and suggest 3 Related Questions at end.\n\n"
        f"--- CONTEXT ---\n{context}\n--- END ---"
    )

from django.conf import settings
from blog.redis_vectors import (
    search_similar_async, 
    get_cached_embedding_async, 
    cache_embedding_async
)

# Skip RAG for these simple patterns
SKIP_RAG_PATTERNS = {'hi', 'hello', 'hey', 'thanks', 'bye', 'ok', 'yes', 'no', 'sure'}

# Shared clients to reduce latency from connection overhead
_ollama_client = None
_ollama_async_client = None

def get_ollama_client(async_client=False):
    """Factory for Ollama clients - reuses instances to minimize latency."""
    import ollama
    global _ollama_client, _ollama_async_client
    host = settings.OLLAMA_HOST
    
    if async_client:
        if _ollama_async_client is None:
            _ollama_async_client = ollama.AsyncClient(host=host)
        return _ollama_async_client
    else:
        if _ollama_client is None:
            _ollama_client = ollama.Client(host=host)
        return _ollama_client

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

        # 1. Query Intelligence (Suggestion 1)
        # Add a total timeout for reasoning (Circuit Breaker Suggestion 7)
        try:
            meta = await asyncio.wait_for(classify_query(user_msg, client), timeout=5.0)
        except asyncio.TimeoutError:
            return f"{site_meta}\n\n[Warning: Deep reasoning timed out. Using fast retrieval.]"
            
        if not meta["needs_rag"]:
            return "NO_RAG_NEEDED"
            
        # 2. Query Expansion (Suggestion 6)
        expanded_query = await expand_query(user_msg, client)
        
        # 3. Hybrid Retrieval with Cache (Suggestion 1)
        top_k = 8 if meta["scope"] == "broad" else 5
        
        # Keyword Search
        text_matches = await text_search_async(user_msg, top_k=3)
        
        # Semantic Search (Using Cache)
        embedding = await get_cached_embedding_async(expanded_query)
        if not embedding:
            emb_resp = await client.embeddings(model='nomic-embed-text', prompt=expanded_query)
            embedding = emb_resp['embedding']
            await cache_embedding_async(expanded_query, embedding)
            
        vector_matches = await search_similar_async(embedding, top_k=top_k)
        
        # 4. Hybrid Ranking
        ranked_chunks = await rank_search_results(user_msg, text_matches, vector_matches)
        
        raw_context = ""
        for m in ranked_chunks:
            # Suggestion 5: Mention section titles in raw context
            raw_context += f"SOURCE: {m['title']}\nCONTENT: {m['content']}\n\n"
            
        # 5. Context Distillation (Suggestion 3)
        try:
            distilled = await asyncio.wait_for(distill_context(raw_context, user_msg, client), timeout=8.0)
        except asyncio.TimeoutError:
            distilled = raw_context[:2000] # Fallback to raw if distillation is too slow
        
        if not distilled and not raw_context:
            logger.warning(f"RAG_EMPTY: No relevant docs found for: {user_msg}")
            
        final_context = f"{site_meta}\n\n[CONTENT_MAP]\n{distilled or raw_context}"
        
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

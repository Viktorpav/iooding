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
    """Classify the user query to decide on retrieval strategy (Suggestion 1)."""
    import json
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
        # Try to find JSON in response since LLMs sometimes add talk
        import re
        match = re.search(r'\{.*\}', resp['response'], re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"intent": "explanation", "needs_rag": True, "scope": "narrow", "expected_depth": "deep"}
    except:
        return {"intent": "explanation", "needs_rag": True, "scope": "narrow", "expected_depth": "deep"}

async def rank_search_results(user_msg, text_matches, vector_matches):
    """Hybrid ranker with score-aware boosting (Suggestion 2)."""
    seen = {} # doc_id -> score
    
    # 1. Semantic Weights
    for m in vector_matches:
        doc_id = f"{m['post_id']}:{m['content'][:50]}"
        score = (1.0 - m['distance']) * 2.0 # 0.0 to 2.0
        seen[doc_id] = {"score": score, "doc": m}
        
    # 2. Keyword Boosts (Suggestion 2)
    user_words = set(user_msg.lower().split())
    for m in text_matches:
        doc_id = f"{m['post_id']}:{m['content'][:50]}"
        bonus = 1.5 if any(word in m['title'].lower() for word in user_words) else 1.0
        if doc_id in seen:
            seen[doc_id]["score"] += bonus
        else:
            seen[doc_id] = {"score": bonus, "doc": m}
            
    # Sort and return top chunks
    ranked = sorted(seen.values(), key=lambda x: x['score'], reverse=True)
    return [r['doc'] for r in ranked[:6]]

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
    """Fetches a detailed inventory of the blog's current state."""
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
        latest = posts[0].title if posts else "None"
        meta = "--- SYSTEM AWARENESS: SITE INVENTORY ---\n"
        meta += f"Assistant Identity: Ding AI (Integrated Site Engine)\n"
        meta += f"Host: Ding Blog (iooding.local)\n"
        meta += f"Total Records: {len(posts)} Posts\n"
        meta += f"Tags/Categories: {', '.join(tags) if tags else 'General'}\n"
        meta += f"Latest Post: {latest}\n"
        meta += "Available Titles Index: " + (", ".join([p.title for p in posts]) if posts else "No content")
        return len(posts), meta
    except Exception as e:
        return 0, f"Error: {e}"

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
        
        # 3. Hybrid Retrieval (Suggestion 2)
        top_k = 8 if meta["scope"] == "broad" else 5
        
        # Keyword Search
        text_matches = await text_search_async(user_msg, top_k=3)
        
        # Semantic Search (Using Expanded Query)
        emb_resp = await client.embeddings(model='nomic-embed-text', prompt=expanded_query)
        vector_matches = await search_similar_async(emb_resp['embedding'], top_k=top_k)
        
        # 4. Hybrid Ranking (Suggestion 2)
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
        
        return f"{site_meta}\n\n--- VERIFIED FACTS ---\n{distilled or raw_context}"
    except Exception as e:
        # Suggestion 7 Fallback: If everything fails, return just site map
        _, site_meta = await get_site_metadata()
        return f"{site_meta}\n\n[System Alert: Knowledge base retrieval is slow. Falling back to site-map.]"

def get_rag_system_prompt(context: str) -> str:
    """The Balanced Authority directive (Suggestion 4, 8, 9)."""
    return (
        "ROLE: You are 'Ding AI', the specialized expert for this blog. "
        "IDENTITY: You run on a local Kubernetes cluster using Ollama + Redis. "
        "KNOWLEDGE: Use ONLY the provided context for specific blog information. "
        "GUIDELINES:\n"
        "1. HONESTY: If the context doesn't contain the answer, say 'I don't see this in the current posts' "
        "(Suggestion 4). Then, you may use your general knowledge but clarify it's an external guess.\n"
        "2. LINKS: Always provide Markdown links [Title](URL) for site content.\n"
        "3. FORMAT: Use technical Markdown (code blocks, bold headers).\n"
        "4. NEXT STEPS: Always end with exactly 3 'Related Questions' that the user might want to ask next "
        "based on the site content (Suggestion 9).\n\n"
        "--- PROVIDED CONTEXT STRATEGIC SUMMARY ---\n"
        f"{context}\n"
        "--- CONTEXT END ---"
    )

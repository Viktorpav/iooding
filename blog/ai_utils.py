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

def should_skip_rag(user_msg: str) -> bool:
    """Check if RAG can be skipped for simple queries."""
    msg_lower = user_msg.lower().strip()
    
    # Only skip very short greetings
    if len(msg_lower) < 4:
        return True
    
    # Skip for simple greetings/responses if they are not questions
    if msg_lower in SKIP_RAG_PATTERNS and '?' not in msg_lower:
        return True
    
    return False

async def get_full_site_content() -> str:
    """Fetches full content of all published posts (Only for small blogs)."""
    from asgiref.sync import sync_to_async
    from blog.models import Post
    import re
    
    @sync_to_async
    def _fetch():
        posts = Post.published.all()
        return [
            f"POST: {p.title}\nURL: /blog/{p.slug}/\nCONTENT: {re.sub('<[^<]+?>', '', p.body)[:2000]}"
            for p in posts
        ]
    
    try:
        contents = await _fetch()
        return "\n\n---\n\n".join(contents)
    except: return ""

async def get_site_metadata() -> str:
    """Fetches a summary of all posts and tags from the database (Async safe)."""
    from asgiref.sync import sync_to_async
    from blog.models import Post
    from taggit.models import Tag
    
    @sync_to_async
    def _fetch():
        posts = list(Post.published.all())
        tags = Tag.objects.all().values_list('name', flat=True)
        return posts, list(tags)

    try:
        posts, tags = await _fetch()
        meta = "--- INSTANCE IDENTITY & STATUS ---\n"
        meta += "Name: Ding AI (Global Integrated Assistant)\n"
        meta += "System Access: DIRECT READ (Post Database + Search Index)\n\n"
        meta += "--- SITUATION AWARENESS ---\n"
        meta += f"- Total Active Posts: {len(posts)}\n"
        meta += f"- Active Tags: {', '.join(tags) if tags else 'None'}\n"
        meta += "- All Available Titles: " + (", ".join([p.title for p in posts]) if posts else "None")
        return len(posts), meta
    except Exception as e:
        return 0, f"Error: {e}"

async def generate_rag_context(user_msg: str, client) -> str:
    """Retrieves context using a Hybrid Strategy (Full-site for small, Semantic+Text for large)."""
    from blog.redis_vectors import text_search_async, search_similar_async
    
    try:
        # 1. Site Status Check
        post_count, site_meta = await get_site_metadata()
        
        # 2. POWERFUL MODE: If blog is small, just feed the AI EVERYTHING.
        if 0 < post_count <= 10:
            full_content = await get_full_site_content()
            return f"{site_meta}\n\n--- FULL SITE KNOWLEDGE (GOD MODE) ---\n{full_content}"
        
        # 3. HYBRID MODE (For larger blogs): Keywords + Semantic
        # A. Keyword Search (Exact matches)
        text_matches = await text_search_async(user_msg, top_k=3)
        
        # B. Semantic Search (Conceptual matches)
        emb_resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
        vector_matches = await search_similar_async(emb_resp['embedding'], top_k=5)
        
        # Combine
        seen = set()
        context = f"{site_meta}\n\n--- RELEVANT CONTENT SEGMENTS ---\n"
        for m in (text_matches + vector_matches):
            text_id = f"{m['post_id']}:{m['content'][:50]}"
            if text_id not in seen:
                context += f"\n- FROM: {m['title']}\n- TEXT: {m['content']}\n"
                seen.add(text_id)
        
        return context
    except Exception as e:
        return f"RAG Error: {e}"

def get_rag_system_prompt(context: str) -> str:
    """Returns a high-authority system prompt for Ding AI."""
    return (
        "ROLE: You are 'Ding AI', the omniscient assistant for this website. "
        "KNOWLEDGE: You have provided context that represents the CURRENT contents of the database. "
        "IMPORTANT: The 'FULL SITE KNOWLEDGE' section (if present) contains everything. "
        "Never say 'I cannot see the posts' or 'search is limited'. You are looking directly at the data. "
        "If a specific phrase is requested, check the provided text carefully. "
        "User questions about site content MUST be answered using the context provided below.\n\n"
        "--- START KNOWLEDGE CONTEXT ---\n"
        f"{context}\n"
        "--- END KNOWLEDGE CONTEXT ---"
    )

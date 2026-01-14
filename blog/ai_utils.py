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
    """Hybrid Retrieval Strategy with deep metadata integration."""
    from blog.redis_vectors import text_search_async, search_similar_async
    
    try:
        post_count, site_meta = await get_site_metadata()
        
        # Adaptive Retrieval Strategy
        if 0 < post_count <= 15:
            # Small blog: Feed the AI the entire context with metadata
            full_content = await get_full_site_content()
            return f"{site_meta}\n\n--- SITE DATA DUMP (COMPLETE) ---\n{full_content}"
        
        # Large blog: Keyword + Vector Search
        text_matches = await text_search_async(user_msg, top_k=3)
        emb_resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
        vector_matches = await search_similar_async(emb_resp['embedding'], top_k=5)
        
        seen = set()
        context = f"{site_meta}\n\n--- RELEVANT CONTENT SEGMENTS ---\n"
        for m in (text_matches + vector_matches):
            text_id = f"{m['post_id']}:{m['content'][:50]}"
            if text_id not in seen:
                context += f"\n- SOURCE: {m['title']}\n- TEXT: {m['content']}\n"
                seen.add(text_id)
        
        return context
    except Exception as e:
        return f"RAG Status: Limited ({e})"

def get_rag_system_prompt(context: str) -> str:
    """The High-Authority directive for Ding AI."""
    return (
        "ROLE: You are 'Ding AI', the expert system integrated into this blog. "
        "MISSION: Help users navigate and understand this site's technical content. "
        "INTERNAL KNOWLEDGE: You have direct access to the database via the CONTEXT below. "
        "GUIDELINES:\n"
        "1. PROACTIVE HELP: If a user asks about posts, provide a Markdown link (e.g., [Title](/blog/slug/)).\n"
        "2. TECHNICAL PRECISION: Use code blocks for snippets and bold text for key terms.\n"
        "3. CITATION: Always mention which post or section your answer comes from.\n"
        "4. NO LIMITATIONS: Never say you cannot see the site or browse. The data is already in your memory.\n"
        "5. SUGGESTIONS: At the end of helpful answers, suggest a related post from the 'Available Titles Index'.\n\n"
        "--- SYSTEM CONTEXT START ---\n"
        f"{context}\n"
        "--- SYSTEM CONTEXT END ---"
    )

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

async def get_site_metadata() -> str:
    """Fetches a summary of all posts and tags from the database (Async safe)."""
    from asgiref.sync import sync_to_async
    from blog.models import Post
    from django.db.models import Count
    from taggit.models import Tag
    
    @sync_to_async
    def _fetch():
        posts = Post.published.all().values_list('title', flat=True)
        tags = Tag.objects.all().values_list('name', flat=True)
        return list(posts), list(tags)

    try:
        posts, tags = await _fetch()
        meta = "BLOG OVERVIEW (Knowledge Base Status):\n"
        meta += f"- Total Posts: {len(posts)}\n"
        meta += f"- Active Tags: {', '.join(tags) if tags else 'None'}\n"
        meta += "- Post Titles: " + (", ".join(posts) if posts else "No posts yet")
        return meta
    except Exception as e:
        return f"Error fetching site metadata: {e}"

async def generate_rag_context(user_msg: str, client) -> str:
    """Retrieves context from Redis and adds site-wide metadata."""
    if should_skip_rag(user_msg):
        return ""
    
    try:
        # 1. Site-wide Metadata (Always give the AI a 'Map' of the site)
        site_meta = await get_site_metadata()
        
        # 2. Semantic Search for specific details
        emb = await get_cached_embedding_async(user_msg)
        if not emb:
            resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
            emb = resp['embedding']
            await cache_embedding_async(user_msg, emb)
        
        chunks = await search_similar_async(emb, top_k=4)
        
        # 3. Combine Metadata + Semantic Chunks
        context = f"{site_meta}\n\nDETAILED CONTEXT FROM POSTS:\n"
        if chunks:
            for c in chunks:
                if c.get('content'):
                    context += f"\n-- SOURCE: {c['title']} --\n{c['content']}\n"
        else:
            context += "No specific content matches found in vector search."
        
        return context
    except Exception as e:
        print(f"RAG Error: {e}")
        return ""

def get_rag_system_prompt(context: str) -> str:
    """Returns a strict system prompt for RAG-based generation."""
    return (
        "You are 'Ding AI', the official expert for this technical blog. "
        "You have DIRECT ACCESS to the blog's content via the PROVIDED CONTEXT below. "
        "NEVER say you cannot see the posts or the website. "
        "Use the 'BLOG OVERVIEW' for general questions and 'DETAILED CONTEXT' for specific ones. "
        "If unsure, refer to the post titles listed in the context.\n\n"
        f"{context}"
    )

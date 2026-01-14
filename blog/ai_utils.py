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
        meta = "--- INSTANCE IDENTITY & STATUS ---\n"
        meta += "Name: Ding AI (Integrated Assistant)\n"
        meta += "Host: Ding Technical Blog (iooding.local)\n"
        meta += "Architecture: Django + Redis Stack (Vector DB) + Kubernetes + Ollama\n"
        meta += "System Access: READ-ONLY (Database + Vector Search)\n\n"
        meta += "--- KNOWLEDGE BASE SUMMARY ---\n"
        meta += f"- Total Published Posts: {len(posts)}\n"
        meta += f"- Active Categories/Tags: {', '.join(tags) if tags else 'None'}\n"
        meta += "- Current Post Titles: " + (", ".join(posts) if posts else "Indexing in progress...")
        return meta
    except Exception as e:
        return f"Error fetching site metadata: {e}"

async def generate_rag_context(user_msg: str, client) -> str:
    """Retrieves context from Redis and adds site-wide metadata."""
    if should_skip_rag(user_msg):
        return ""
    
    try:
        # 1. Site-wide Identity & Metadata
        site_meta = await get_site_metadata()
        
        # 2. Semantic Search for specific details
        emb = await get_cached_embedding_async(user_msg)
        if not emb:
            resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
            emb = resp['embedding']
            await cache_embedding_async(user_msg, emb)
        
        chunks = await search_similar_async(emb, top_k=5)
        
        # 3. Combine Metadata + Semantic Chunks
        context = f"{site_meta}\n\n--- DETAILED CONTENT FROM BLOG POSTS ---\n"
        if chunks:
            for c in chunks:
                if c.get('content'):
                    context += f"\nSOURCE: {c['title']}\nCONTENT: {c['content']}\n"
        else:
            context += "No specific matching text found for this query."
        
        return context
    except Exception as e:
        print(f"RAG Error: {e}")
        return ""

def get_rag_system_prompt(context: str) -> str:
    """Returns a high-authority system prompt for Ding AI."""
    return (
        "ROLE: You are 'Ding AI', the integrated intelligence of this website. "
        "IDENTITY: You are NOT a generic large language model; you are a custom-built assistant "
        "running on this blog's local infrastructure (Kubernetes + Ollama). "
        "CAPABILITY: You have direct read-access to the blog's database and knowledge base. "
        "INSTRUCTION: Never claim you cannot see the posts or the website. You are LITERALLY INSIDE it. "
        "Use the 'INSTANCE IDENTITY' section to answer questions about yourself and the "
        "'KNOWLEDGE BASE SUMMARY' to list posts/tags. Be professional and technically precise.\n\n"
        "--- PROVIDED CONTEXT START ---\n"
        f"{context}\n"
        "--- PROVIDED CONTEXT END ---"
    )

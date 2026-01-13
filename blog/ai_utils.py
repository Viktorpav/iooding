import ollama
import hashlib
from django.conf import settings
from django.core.cache import cache
from blog.models import PostChunk
from pgvector.django import CosineDistance
from asgiref.sync import sync_to_async

# Skip RAG for these simple patterns
SKIP_RAG_PATTERNS = ['hi', 'hello', 'hey', 'thanks', 'bye', 'ok', 'yes', 'no']

def get_ollama_client(async_client=False):
    """Factory for Ollama clients using settings."""
    host = settings.OLLAMA_HOST
    if async_client:
        return ollama.AsyncClient(host=host)
    return ollama.Client(host=host)

@sync_to_async
def get_similar_chunks(embedding, limit=3):
    """Retrieve similar chunks from the AI database."""
    return list(PostChunk.objects.annotate(
        distance=CosineDistance('embedding', embedding)
    ).order_by('distance')[:limit])

def should_skip_rag(user_msg):
    """Check if RAG can be skipped for simple queries."""
    msg_lower = user_msg.lower().strip()
    # Skip for very short messages
    if len(msg_lower) < 10:
        return True
    # Skip for simple greetings
    if msg_lower in SKIP_RAG_PATTERNS:
        return True
    # Skip for messages that are clearly not about blog content
    if msg_lower.startswith(('write ', 'explain ', 'what is ', 'how to ')):
        # These might still benefit from RAG, don't skip
        return False
    return False

def get_embedding_cache_key(text):
    """Generate cache key for embedding."""
    return f"emb:{hashlib.md5(text.encode()).hexdigest()[:16]}"

@sync_to_async
def get_cached_embedding(key):
    """Get embedding from cache."""
    return cache.get(key)

@sync_to_async
def set_cached_embedding(key, embedding):
    """Cache embedding for 1 hour."""
    cache.set(key, embedding, timeout=3600)

async def generate_rag_context(user_msg, client):
    """
    Generates context string for RAG.
    Returns empty string if failure, skip, or no match.
    """
    # Fast path: skip RAG for simple queries
    if should_skip_rag(user_msg):
        return ""
    
    try:
        # Check cache first
        cache_key = get_embedding_cache_key(user_msg)
        embedding = await get_cached_embedding(cache_key)
        
        if not embedding:
            # Generate embedding with timeout consideration
            resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
            embedding = resp['embedding']
            # Cache for future use
            await set_cached_embedding(cache_key, embedding)
        
        # Search DB
        chunks = await get_similar_chunks(embedding, limit=2)  # Reduced from 3 to 2 for speed
        
        if not chunks:
            return ""
        
        # Only use chunks with reasonable similarity (distance < 0.5)
        relevant_chunks = [c for c in chunks if hasattr(c, 'distance') and c.distance < 0.5]
        if not relevant_chunks:
            return ""
            
        return "\n\n".join([c.content for c in relevant_chunks])
    except Exception as e:
        print(f"RAG Error (non-blocking): {e}")
        return ""

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
    
    # Skip for very short messages
    if len(msg_lower) < 10:
        return True
    
    # Skip for simple greetings/responses
    if msg_lower in SKIP_RAG_PATTERNS:
        return True
    
    # Skip for code generation requests
    code_indicators = ('write code', 'write a function', 'implement', 'create a script')
    if any(msg_lower.startswith(ind) for ind in code_indicators):
        return True
    
    return False

async def generate_rag_context(user_msg: str, client) -> str:
    """
    Generates context string for RAG using Redis vector search.
    Returns empty string if skip, failure, or no relevant match.
    Fully async to avoid blocking the event loop.
    """
    if should_skip_rag(user_msg):
        return ""
    
    try:
        # Check async cache first for the embedding
        embedding = await get_cached_embedding_async(user_msg)
        
        if not embedding:
            # Generate embedding via Ollama (already async client passed in)
            resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
            embedding = resp['embedding']
            # Cache for future use (async)
            await cache_embedding_async(user_msg, embedding, timeout=3600)
        
        # Search Redis for similar chunks (async)
        chunks = await search_similar_async(embedding, top_k=2, max_distance=0.5)
        
        if not chunks:
            return ""
        
        # Build context from relevant chunks
        context_parts = []
        for chunk in chunks:
            if chunk.get('content'):
                context_parts.append(f"From '{chunk['title']}':\n{chunk['content']}")
        
        return "\n\n---\n\n".join(context_parts)
        
    except Exception as e:
        print(f"RAG Error (non-blocking): {e}")
        return ""

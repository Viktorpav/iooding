"""
AI utilities for the blog - optimized for low latency.
Uses Redis Stack for vector search instead of PostgreSQL.
"""
import ollama
from django.conf import settings
from blog.redis_vectors import (
    search_similar, 
    get_cached_embedding, 
    cache_embedding
)

# Skip RAG for these simple patterns
SKIP_RAG_PATTERNS = {'hi', 'hello', 'hey', 'thanks', 'bye', 'ok', 'yes', 'no', 'sure'}

def get_ollama_client(async_client=False):
    """Factory for Ollama clients using settings."""
    host = settings.OLLAMA_HOST
    if async_client:
        return ollama.AsyncClient(host=host)
    return ollama.Client(host=host)

def should_skip_rag(user_msg: str) -> bool:
    """Check if RAG can be skipped for simple queries."""
    msg_lower = user_msg.lower().strip()
    
    # Skip for very short messages
    if len(msg_lower) < 10:
        return True
    
    # Skip for simple greetings/responses
    if msg_lower in SKIP_RAG_PATTERNS:
        return True
    
    # Skip for code generation requests (usually not about blog content)
    code_indicators = ('write code', 'write a function', 'implement', 'create a script')
    if any(msg_lower.startswith(ind) for ind in code_indicators):
        return True
    
    return False

async def generate_rag_context(user_msg: str, client) -> str:
    """
    Generates context string for RAG using Redis vector search.
    Returns empty string if skip, failure, or no relevant match.
    """
    # Fast path: skip RAG for simple queries
    if should_skip_rag(user_msg):
        return ""
    
    try:
        # Check cache first for the embedding
        embedding = get_cached_embedding(user_msg)
        
        if not embedding:
            # Generate embedding
            resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
            embedding = resp['embedding']
            # Cache for future use
            cache_embedding(user_msg, embedding, timeout=3600)
        
        # Search Redis for similar chunks
        chunks = search_similar(embedding, top_k=2, max_distance=0.5)
        
        if not chunks:
            return ""
        
        # Build context from relevant chunks
        context_parts = []
        for chunk in chunks:
            if chunk['content']:
                context_parts.append(f"From '{chunk['title']}':\n{chunk['content']}")
        
        return "\n\n---\n\n".join(context_parts)
        
    except Exception as e:
        # Non-blocking: log and continue without RAG
        print(f"RAG Error (non-blocking): {e}")
        return ""

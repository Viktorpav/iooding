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
    """Retrieves and formats context from Redis for the LLM."""
    if should_skip_rag(user_msg):
        return ""
    
    try:
        # 1. Semantic Embedding
        emb = await get_cached_embedding_async(user_msg)
        if not emb:
            resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
            emb = resp['embedding']
            await cache_embedding_async(user_msg, emb)
        
        # 2. Vector Search (Top 4 chunks for broader context)
        chunks = await search_similar_async(emb, top_k=4)
        if not chunks:
            return ""
        
        # 3. Instruction-based context formatting
        context = "RELATIIVE CONTEXT FROM INTERNAL DOCUMENTS:\n"
        for c in chunks:
            if c.get('content'):
                context += f"\n-- SOURCE: {c['title']} --\n{c['content']}\n"
        
        return context
    except Exception as e:
        print(f"RAG Retrieval Error: {e}")
        return ""

def get_rag_system_prompt(context: str) -> str:
    """Returns a strict system prompt for RAG-based generation."""
    return (
        "You are 'Ding AI', an expert assistant for this blog. "
        "Use the PROVIDED CONTEXT below to answer the user accurately. "
        "If the answer isn't in the context, say you don't know based on internal docs, "
        "but then use your general knowledge to provide a helpful guess. "
        "ALWAYS cite the source title if you use the context.\n\n"
        f"{context}"
    )

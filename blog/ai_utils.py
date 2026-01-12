import ollama
from django.conf import settings
from blog.models import PostChunk
from pgvector.django import CosineDistance
from asgiref.sync import sync_to_async

def get_ollama_client(async_client=False):
    """Factory for Ollama clients using settings."""
    host = settings.OLLAMA_HOST
    # Increase timeout to handle queuing/concurrency better
    # Ollama python client might simpler, but we can configure it if needed
    # Currently standard client doesn't expose timeout easily in constructor 
    # but we can wrap calls or assume default.
    if async_client:
        return ollama.AsyncClient(host=host)
    return ollama.Client(host=host)

@sync_to_async
def get_similar_chunks(embedding, limit=3):
    """Retrieve similar chunks from the AI database."""
    return list(PostChunk.objects.annotate(
        distance=CosineDistance('embedding', embedding)
    ).order_by('distance')[:limit])

async def generate_rag_context(user_msg, client):
    """
    Generates context string for RAG.
    Returns empty string if failure or no match.
    """
    try:
        # 1. Get embedding
        resp = await client.embeddings(model='nomic-embed-text', prompt=user_msg)
        embedding = resp['embedding']
        
        # 2. Search DB
        chunks = await get_similar_chunks(embedding)
        
        if not chunks:
            return ""
            
        return "\n\n".join([c.content for c in chunks])
    except Exception as e:
        print(f"RAG Generation Error: {e}")
        return ""

"""
Redis-based vector search and embedding storage for RAG.
Uses Redis Stack's built-in vector similarity search (VSS).
Replaces PostgreSQL pgvector for better performance.
"""
import json
import hashlib
import numpy as np
from django.conf import settings
from django.core.cache import cache
import redis
from redis.commands.search.field import VectorField, TextField, NumericField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

# Index configuration
INDEX_NAME = "idx:blog_chunks"
VECTOR_DIM = 768  # nomic-embed-text dimension
DOC_PREFIX = "chunk:"

_redis_client = None

def get_redis_client():
    """Get Redis client - singleton pattern for connection reuse."""
    global _redis_client
    if _redis_client is None:
        redis_url = settings.CACHES.get('default', {}).get('LOCATION', 'redis://redis:6379/1')
        _redis_client = redis.from_url(redis_url, decode_responses=False)
    return _redis_client

def ensure_index_exists():
    """Create the vector index if it doesn't exist."""
    client = get_redis_client()
    try:
        client.ft(INDEX_NAME).info()
        return True
    except redis.ResponseError:
        # Index doesn't exist, create it
        try:
            schema = (
                TextField("$.title", as_name="title"),
                TextField("$.content", as_name="content"),
                NumericField("$.post_id", as_name="post_id"),
                VectorField(
                    "$.embedding",
                    "FLAT",  # FLAT for small datasets (<10k), HNSW for larger
                    {
                        "TYPE": "FLOAT32",
                        "DIM": VECTOR_DIM,
                        "DISTANCE_METRIC": "COSINE",
                    },
                    as_name="embedding"
                )
            )
            
            definition = IndexDefinition(
                prefix=[DOC_PREFIX],
                index_type=IndexType.JSON
            )
            
            client.ft(INDEX_NAME).create_index(
                schema,
                definition=definition
            )
            print(f"Created Redis vector index: {INDEX_NAME}")
            return True
        except Exception as e:
            print(f"Failed to create index: {e}")
            return False

def index_chunk(post_id: int, title: str, content: str, embedding: list) -> str:
    """Index a single chunk in Redis."""
    client = get_redis_client()
    ensure_index_exists()
    
    # Create unique ID based on post and content hash
    content_hash = hashlib.md5(content[:100].encode()).hexdigest()[:8]
    doc_id = f"{DOC_PREFIX}{post_id}:{content_hash}"
    
    doc = {
        "post_id": post_id,
        "title": title,
        "content": content,
        "embedding": embedding  # List of floats
    }
    
    client.json().set(doc_id, "$", doc)
    return doc_id

def search_similar(query_embedding: list, top_k: int = 3, max_distance: float = 0.5) -> list:
    """
    Search for similar chunks using vector similarity.
    Returns list of dicts with title, content, post_id, distance.
    """
    client = get_redis_client()
    
    if not ensure_index_exists():
        return []
    
    # Convert embedding to bytes for Redis query
    query_vector = np.array(query_embedding, dtype=np.float32).tobytes()
    
    # Build KNN query
    q = (
        Query(f"*=>[KNN {top_k} @embedding $query_vector AS distance]")
        .sort_by("distance")
        .return_fields("title", "content", "post_id", "distance")
        .dialect(2)
    )
    
    try:
        results = client.ft(INDEX_NAME).search(
            q,
            query_params={"query_vector": query_vector}
        )
        
        # Filter by distance and return
        return [
            {
                "post_id": int(doc.post_id) if hasattr(doc, 'post_id') else 0,
                "title": doc.title if hasattr(doc, 'title') else "",
                "content": doc.content if hasattr(doc, 'content') else "",
                "distance": float(doc.distance) if hasattr(doc, 'distance') else 1.0
            }
            for doc in results.docs
            if float(doc.distance) < max_distance
        ]
    except redis.ResponseError as e:
        print(f"Redis search error: {e}")
        return []

def delete_post_chunks(post_id: int):
    """Delete all chunks for a specific post."""
    client = get_redis_client()
    cursor = 0
    deleted = 0
    while True:
        cursor, keys = client.scan(cursor, match=f"{DOC_PREFIX}{post_id}:*")
        for key in keys:
            client.delete(key)
            deleted += 1
        if cursor == 0:
            break
    return deleted

def get_chunk_count() -> int:
    """Get total number of indexed chunks."""
    client = get_redis_client()
    try:
        info = client.ft(INDEX_NAME).info()
        return int(info.get('num_docs', 0))
    except redis.ResponseError:
        return 0

# --- Embedding Cache Functions ---
def get_embedding_cache_key(text: str) -> str:
    """Generate cache key for embedding."""
    return f"emb:{hashlib.md5(text.encode()).hexdigest()[:16]}"

def get_cached_embedding(text: str) -> list | None:
    """Get cached embedding for text."""
    key = get_embedding_cache_key(text)
    cached = cache.get(key)
    return cached

def cache_embedding(text: str, embedding: list, timeout: int = 3600):
    """Cache embedding for text (default 1 hour)."""
    key = get_embedding_cache_key(text)
    cache.set(key, embedding, timeout=timeout)

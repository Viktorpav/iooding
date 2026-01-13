"""
Redis-based vector search for RAG.
Uses Redis Stack's built-in vector similarity search (VSS).
"""
import json
import hashlib
import numpy as np
from django.conf import settings
import redis
from redis.commands.search.field import VectorField, TextField, NumericField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

# Redis connection
def get_redis_client():
    """Get Redis client from Django settings."""
    redis_url = settings.CACHES.get('default', {}).get('LOCATION', 'redis://redis:6379/1')
    return redis.from_url(redis_url)

# Index configuration
INDEX_NAME = "idx:blog_chunks"
VECTOR_DIM = 768  # nomic-embed-text dimension
DOC_PREFIX = "chunk:"

def ensure_index_exists(client):
    """Create the vector index if it doesn't exist."""
    try:
        client.ft(INDEX_NAME).info()
    except redis.ResponseError:
        # Index doesn't exist, create it
        schema = (
            TextField("$.title", as_name="title"),
            TextField("$.content", as_name="content"),
            NumericField("$.post_id", as_name="post_id"),
            VectorField(
                "$.embedding",
                "FLAT",  # FLAT for small datasets, HNSW for larger
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

def index_chunk(client, post_id, title, content, embedding):
    """Index a single chunk in Redis."""
    ensure_index_exists(client)
    
    doc_id = f"{DOC_PREFIX}{post_id}:{hashlib.md5(content[:100].encode()).hexdigest()[:8]}"
    
    doc = {
        "post_id": post_id,
        "title": title,
        "content": content,
        "embedding": embedding
    }
    
    client.json().set(doc_id, "$", doc)
    return doc_id

def search_similar(client, query_embedding, top_k=3):
    """Search for similar chunks using vector similarity."""
    ensure_index_exists(client)
    
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
        
        return [
            {
                "post_id": doc.post_id,
                "title": doc.title,
                "content": doc.content,
                "distance": float(doc.distance)
            }
            for doc in results.docs
        ]
    except redis.ResponseError as e:
        print(f"Redis search error: {e}")
        return []

def delete_post_chunks(client, post_id):
    """Delete all chunks for a specific post."""
    # Scan for matching keys
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor, match=f"{DOC_PREFIX}{post_id}:*")
        for key in keys:
            client.delete(key)
        if cursor == 0:
            break

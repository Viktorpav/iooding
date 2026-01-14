import hashlib
import json
from django.conf import settings
from django.core.cache import cache
import redis
import redis.asyncio as async_redis
from redis.commands.search.field import VectorField, TextField, NumericField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query

# Index configuration
INDEX_NAME = "idx:blog_chunks"
VECTOR_DIM = 768  # nomic-embed-text dimension
DOC_PREFIX = "chunk:"

_redis_client = None
_async_redis_client = None

def get_redis_client():
    """Get Redis client - singleton pattern for connection reuse."""
    global _redis_client
    if _redis_client is None:
        redis_url = settings.CACHES.get('default', {}).get('LOCATION', 'redis://redis:6379/1')
        _redis_client = redis.from_url(redis_url, decode_responses=False)
    return _redis_client

def get_async_redis_client():
    """Get Async Redis client for use in async views."""
    global _async_redis_client
    if _async_redis_client is None:
        redis_url = settings.CACHES.get('default', {}).get('LOCATION', 'redis://redis:6379/1')
        _async_redis_client = async_redis.from_url(redis_url, decode_responses=False)
    return _async_redis_client

def get_schema():
    """Shared schema definition for Redis vector index."""
    return (
        TextField("$.title", as_name="title"),
        TextField("$.content", as_name="content"),
        NumericField("$.post_id", as_name="post_id"),
        VectorField(
            "$.embedding",
            "FLAT",
            {
                "TYPE": "FLOAT32",
                "DIM": VECTOR_DIM,
                "DISTANCE_METRIC": "COSINE",
            },
            as_name="embedding"
        )
    )

def ensure_index_exists():
    """Create the vector index if it doesn't exist (Sync version)."""
    client = get_redis_client()
    try:
        client.ft(INDEX_NAME).info()
        return True
    except redis.ResponseError:
        try:
            definition = IndexDefinition(prefix=[DOC_PREFIX], index_type=IndexType.JSON)
            client.ft(INDEX_NAME).create_index(get_schema(), definition=definition)
            return True
        except Exception as e:
            print(f"Failed to create Redis index: {e}")
            return False

async def ensure_index_exists_async():
    """Create the vector index if it doesn't exist (Async version)."""
    client = get_async_redis_client()
    try:
        await client.ft(INDEX_NAME).info()
        return True
    except redis.ResponseError:
        try:
            definition = IndexDefinition(prefix=[DOC_PREFIX], index_type=IndexType.JSON)
            await client.ft(INDEX_NAME).create_index(get_schema(), definition=definition)
            return True
        except Exception:
            return False

def index_chunk(post_id: int, title: str, content: str, embedding: list) -> str:
    """Index a single chunk in Redis (Sync)."""
    client = get_redis_client()
    ensure_index_exists()
    content_hash = hashlib.md5(content[:100].encode()).hexdigest()[:8]
    doc_id = f"{DOC_PREFIX}{post_id}:{content_hash}"
    doc = {
        "post_id": post_id,
        "title": title,
        "content": content,
        "embedding": embedding
    }
    client.json().set(doc_id, "$", doc)
    return doc_id

async def search_similar_async(query_embedding: list, top_k: int = 5, max_distance: float = 0.7) -> list:
    """Search for similar chunks using vector similarity (Async)."""
    import numpy as np
    client = get_async_redis_client()

    # Ensure index exists before searching
    await ensure_index_exists_async()

    def parse_doc(doc):
        try:
            return {
                "post_id": int(doc.post_id) if hasattr(doc, 'post_id') else 0,
                "title": doc.title if hasattr(doc, 'title') else "",
                "content": doc.content if hasattr(doc, 'content') else "",
                "distance": float(doc.distance) if hasattr(doc, 'distance') else 1.0
            }
        except (ValueError, AttributeError):
            return None

    query_vector = np.array(query_embedding, dtype=np.float32).tobytes()
    q = (
        Query(f"*=>[KNN {top_k} @embedding $query_vector AS distance]")
        .sort_by("distance")
        .return_fields("title", "content", "post_id", "distance")
        .dialect(2)
    )
    try:
        results = await client.ft(INDEX_NAME).search(q, query_params={"query_vector": query_vector})
        parsed = [parse_doc(doc) for doc in results.docs]
        return [p for p in parsed if p and p['distance'] < max_distance]
    except Exception as e:
        print(f"Async Redis search error: {e}")
        return []

def search_similar(query_embedding: list, top_k: int = 5, max_distance: float = 0.7) -> list:
    """Search for similar chunks using vector similarity (Sync)."""
    import numpy as np
    client = get_redis_client()
    if not ensure_index_exists(): return []
    query_vector = np.array(query_embedding, dtype=np.float32).tobytes()
    q = (
        Query(f"*=>[KNN {top_k} @embedding $query_vector AS distance]")
        .sort_by("distance")
        .return_fields("title", "content", "post_id", "distance")
        .dialect(2)
    )
    try:
        results = client.ft(INDEX_NAME).search(q, query_params={"query_vector": query_vector})
        return [
            {
                "post_id": int(doc.post_id) if hasattr(doc, 'post_id') else 0,
                "title": doc.title if hasattr(doc, 'title') else "",
                "content": doc.content if hasattr(doc, 'content') else "",
                "distance": float(doc.distance) if hasattr(doc, 'distance') else 1.0
            }
            for doc in results.docs if float(doc.distance) < max_distance
        ]
    except Exception:
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
        if cursor == 0: break
    return deleted

def get_chunk_count() -> int:
    """Get total number of indexed chunks."""
    client = get_redis_client()
    try:
        info = client.ft(INDEX_NAME).info()
        return int(info.get('num_docs', 0))
    except Exception: return 0

def get_post_hash_key(post_id: int) -> str:
    """Key for storing post-level metadata (hash)."""
    return f"post_meta:{post_id}"

def get_post_hash(post_id: int) -> str | None:
    """Get stored hash for a post to check if re-indexing is needed."""
    client = get_redis_client()
    data = client.get(get_post_hash_key(post_id))
    if data:
        try:
            return json.loads(data).get('hash')
        except: return None
    return None

def set_post_hash(post_id: int, content_hash: str):
    """Store hash for a post after successful indexing."""
    client = get_redis_client()
    client.set(get_post_hash_key(post_id), json.dumps({'hash': content_hash}))

def get_embedding_cache_key(text: str) -> str:
    return f"emb:{hashlib.md5(text.encode()).hexdigest()[:16]}"

async def get_cached_embedding_async(text: str) -> list | None:
    """Get cached embedding for text (Async)."""
    client = get_async_redis_client()
    key = f"emb_json:{get_embedding_cache_key(text)}"
    data = await client.get(key)
    return json.loads(data) if data else None

async def cache_embedding_async(text: str, embedding: list, timeout: int = 3600):
    """Cache embedding for text (Async)."""
    client = get_async_redis_client()
    key = f"emb_json:{get_embedding_cache_key(text)}"
    await client.setex(key, timeout, json.dumps(embedding))

def get_cached_embedding(text: str) -> list | None:
    return cache.get(get_embedding_cache_key(text))

def cache_embedding(text: str, embedding: list, timeout: int = 3600):
    cache.set(get_embedding_cache_key(text), embedding, timeout=timeout)

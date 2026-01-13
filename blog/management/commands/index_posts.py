from django.core.management.base import BaseCommand
from blog.models import Post
from blog.redis_vectors import index_chunk, delete_post_chunks, get_chunk_count, ensure_index_exists
from blog.ai_utils import get_ollama_client
import re

class Command(BaseCommand):
    help = 'Index blog posts into Redis vector database for RAG'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force re-index all posts',
        )

    def handle(self, *args, **options):
        self.stdout.write("Starting Redis vector indexing...")
        ensure_index_exists()
        
        client = get_ollama_client()
        indexed = 0
        failed = 0
        
        for post in Post.published.all():
            try:
                # Clean HTML from body
                clean_text = re.sub('<[^<]+?>', '', post.body)
                
                # Chunk the content (first 3000 chars for now)
                # TODO: Implement proper text splitting for longer posts
                content_chunk = clean_text[:3000].strip()
                
                if not content_chunk:
                    self.stdout.write(self.style.WARNING(f"Skipping empty post: {post.title}"))
                    continue
                
                # Generate embedding
                embedding = client.embeddings(
                    model='nomic-embed-text', 
                    prompt=content_chunk
                )['embedding']
                
                # Delete existing chunks for this post
                deleted = delete_post_chunks(post.id)
                if deleted:
                    self.stdout.write(f"  Removed {deleted} old chunks for post {post.id}")
                
                # Index in Redis
                doc_id = index_chunk(
                    post_id=post.id,
                    title=post.title,
                    content=content_chunk,
                    embedding=embedding
                )
                
                indexed += 1
                self.stdout.write(self.style.SUCCESS(f"✓ Indexed: {post.title}"))
                
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f"✗ Failed to index {post.title}: {e}"))
        
        # Summary
        total = get_chunk_count()
        self.stdout.write(self.style.SUCCESS(
            f"\nIndexing complete: {indexed} posts indexed, {failed} failed. "
            f"Total chunks in Redis: {total}"
        ))

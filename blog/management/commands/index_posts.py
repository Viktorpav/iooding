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
        self.stdout.write("Building RAG Knowledge Base...")
        ensure_index_exists()
        client = get_ollama_client()
        indexed, failed = 0, 0
        
        for post in Post.published.all():
            try:
                text = re.sub('<[^<]+?>', '', post.body).strip()
                if not text: continue
                
                # 1. Clean up old chunks for this post
                delete_post_chunks(post.id)
                
                # 2. Split into overlapping chunks (~1000 chars with 200 char overlap)
                chunk_size, overlap = 1000, 200
                chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size - overlap)]
                
                for i, content in enumerate(chunks):
                    if len(content) < 50: continue # Skip tiny fragments
                    emb = client.embeddings(model='nomic-embed-text', prompt=content)['embedding']
                    index_chunk(
                        post_id=post.id, 
                        title=f"{post.title} (Part {i+1})", 
                        content=content, 
                        embedding=emb
                    )
                
                indexed += 1
                self.stdout.write(self.style.SUCCESS(f"✓ {post.title} ({len(chunks)} chunks)"))
            except Exception as e:
                failed += 1
                self.stdout.write(self.style.ERROR(f"✗ {post.title}: {e}"))
        
        self.stdout.write(self.style.SUCCESS(f"\nDone. Knowledge base updated: {indexed} posts processed."))

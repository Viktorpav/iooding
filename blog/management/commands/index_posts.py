from django.core.management.base import BaseCommand
from blog.models import Post, PostChunk
from pgvector.django import CosineDistance
import ollama

class Command(BaseCommand):
    help = 'Index blog posts into vector database for RAG'

    def handle(self, *args, **kwargs):
        self.stdout.write("Starting indexing...")
        
        # In a real app, you'd chunk large posts. Here we take the body text.
        # Ensure your model supports the dimensions (768 for nomic-embed-text)
        
        client = ollama.Client(host='http://192.168.0.18:11434')
        
        for post in Post.published.all():
            # Basic text extraction (removing HTML tags roughly or using just body)
            import re
            clean_text = re.sub('<[^<]+?>', '', post.body)
            # Naive chunking: index the whole post if small, or first N chars
            # For better RAG, use a proper text splitter (RecursiveCharacterTextSplitter)
            
            # Using first 2000 chars as context for now to keep it simple
            content_chunk = clean_text[:3000]
            
            try:
                embedding = client.embeddings(model='nomic-embed-text', prompt=content_chunk)['embedding']
                
                # Check if chunk exists or update
                # Simplified: Delete old chunks for this post and create new
                PostChunk.objects.filter(post_id=post.id).delete()
                
                PostChunk.objects.create(
                    post_id=post.id,
                    content=content_chunk,
                    embedding=embedding
                )
                self.stdout.write(self.style.SUCCESS(f"Indexed post: {post.title}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Failed to index {post.title}: {e}"))

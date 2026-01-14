from django.core.management.base import BaseCommand
import re
import hashlib

class Command(BaseCommand):
    help = 'Index blog posts into Redis vector database with Section-Awareness'

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Force re-index')

    def handle(self, *args, **options):
        from blog.models import Post
        from blog.redis_vectors import index_chunk, delete_post_chunks, ensure_index_exists, get_post_hash, set_post_hash
        from blog.ai_utils import get_ollama_client

        self.stdout.write("Building Neural Index (Section-Aware Mode)...")
        ensure_index_exists()
        client = get_ollama_client()
        force = options.get('force')
        
        for post in Post.published.all():
            try:
                # 1. Check if content has changed (on raw body to preserve HTML markers)
                current_hash = hashlib.md5(post.body.encode()).hexdigest()
                if not force and get_post_hash(post.id) == current_hash:
                    continue
                
                # 1. Generate Semantic Summary if missing (Suggestion 5: Editor Tool)
                if not post.semantic_summary or force:
                    self.stdout.write(f"  ...generating semantic summary for '{post.title}'")
                    summary_prompt = f"Summarize the technical core of this post in 3 sentences for an AI knowledge base:\n\n{re.sub('<[^<]+?>', '', post.body)[:3000]}"
                    summary_resp = client.generate(model='qwen3-coder:latest', prompt=summary_prompt)
                    post.semantic_summary = summary_resp['response'].strip()
                    post.save()

                delete_post_chunks(post.id)
                
                # 2. Section Extraction (H2, H3 tags)
                # Split body into sections by headers
                sections = re.split(r'<(h[1-4])[^>]*>(.*?)</\1>', post.body, flags=re.IGNORECASE)
                
                # sections will be [pre-h, tag, h-content, pre-next-h, tag2, h-content2, ...]
                parts = []
                current_header = "Introduction"
                
                # Handle leading text before first header
                intro_text = sections[0].strip()
                if intro_text:
                    parts.append((current_header, intro_text))
                
                for i in range(1, len(sections), 3):
                    tag = sections[i]
                    header = sections[i+1]
                    content = sections[i+2] if i+2 < len(sections) else ""
                    parts.append((header, content))

                for section_title, html_content in parts:
                    clean_text = re.sub('<[^<]+?>', '', html_content).strip()
                    if len(clean_text) < 50: continue
                    
                    # Split long sections into chunks
                    chunk_size = 1200
                    for i in range(0, len(clean_text), chunk_size - 200):
                        chunk_text = clean_text[i:i + chunk_size]
                        if len(chunk_text) < 100: continue
                        
                        # Suggestion 5: Prepend section metadata
                        rich_context = f"Post: {post.title} | Section: {section_title}\n{chunk_text}"
                        emb = client.embeddings(model='nomic-embed-text', prompt=rich_context)['embedding']
                        
                        index_chunk(
                            post_id=post.id,
                            title=post.title,
                            content=f"[{section_title}] {chunk_text}",
                            embedding=emb
                        )
                
                set_post_hash(post.id, current_hash)
                self.stdout.write(self.style.SUCCESS(f"✓ {post.title} indexed"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ {post.title}: {e}"))

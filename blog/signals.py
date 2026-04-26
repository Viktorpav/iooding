from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Post
import threading
from django.core.management import call_command

def run_indexing(post_id):
    """Background task to re-index a single post."""
    try:
        # We run the management command for the specific post
        # For simplicity, we just run the full index command, but index_posts.py
        # already has logic to skip unchanged posts, so this is efficient.
        call_command('index_posts')
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Auto-reindexing failed for post {post_id}: {e}")

@receiver(post_save, sender=Post)
def reindex_on_save(sender, instance, **kwargs):
    """Trigger re-indexing when a post is saved in published status."""
    if instance.status == 'published':
        # Use a simple thread for background processing to avoid blocking the request
        # In a larger app, this would be Celery or RQ.
        threading.Thread(target=run_indexing, args=(instance.id,), daemon=True).start()

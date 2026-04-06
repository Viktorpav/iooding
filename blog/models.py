from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.urls import reverse
from django_ckeditor_5.fields import CKEditor5Field
from taggit.managers import TaggableManager
import re


class PublishedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status='published')


class Post(models.Model):
    STATUS_CHOICES = (
        ('draft',     'Draft'),
        ('published', 'Published'),
    )

    title    = models.CharField(max_length=250)
    slug     = models.SlugField(max_length=250, unique_for_date='publish')
    image    = models.ImageField(upload_to='featured_image/%Y/%m/%d/', blank=True, null=True)
    author   = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blog_posts')
    body     = CKEditor5Field('Text', config_name='extends')
    publish  = models.DateTimeField(default=timezone.now, db_index=True)
    created  = models.DateTimeField(auto_now_add=True)
    updated  = models.DateTimeField(auto_now=True)
    status   = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft', db_index=True)
    tags     = TaggableManager()
    semantic_summary = models.TextField(blank=True, help_text='AI-generated semantic summary for RAG indexing')

    objects  = models.Manager()
    published = PublishedManager()

    class Meta:
        ordering = ('-publish',)
        indexes = [
            models.Index(fields=['status', 'publish']),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('blog:post_detail', args=[self.slug])

    @property
    def read_time(self) -> int:
        """Estimated reading time in minutes (≈200 wpm)."""
        text = re.sub(r'<[^<]+?>', '', self.body)
        return max(1, round(len(text.split()) / 200))

    def get_comments(self):
        """Return root-level active comments only."""
        return self.comments.filter(parent=None, active=True)


class Comment(models.Model):
    post    = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    name    = models.CharField(max_length=50)
    email   = models.EmailField()
    parent  = models.ForeignKey('self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies')
    body    = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    active  = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ('created',)

    def __str__(self):
        return f'Comment by {self.name} on "{self.post}"'

    def get_replies(self):
        return self.replies.filter(active=True)
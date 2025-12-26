from django.contrib import admin
from .models import Post, Comment

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'author', 'publish', 'status')
    list_filter = ('status', 'created', 'publish', 'author')
    search_fields = ('title', 'body')
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ('author',)
    date_hierarchy = 'publish'
    ordering = ('status', 'publish')
    list_editable = ('status',)
    actions = ['make_published', 'make_draft']

    @admin.action(description='Mark selected posts as published')
    def make_published(self, request, queryset):
        queryset.update(status='published')

    @admin.action(description='Mark selected posts as draft')
    def make_draft(self, request, queryset):
        queryset.update(status='draft')

@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display=('name', 'email', 'post', 'created', 'active')
    list_filter = ('active', 'created', 'updated')
    search_fields = ('name', 'email', 'body')
    list_editable = ('active',)

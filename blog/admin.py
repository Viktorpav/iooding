from django.contrib import admin
from .models import Post, Comment


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display  = ('title', 'author', 'publish', 'status', 'read_time')
    list_filter   = ('status', 'publish', 'author')
    list_editable = ('status',)
    search_fields = ('title', 'body')
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ('author',)
    date_hierarchy = 'publish'
    ordering = ('-publish',)
    readonly_fields = ('created', 'updated')
    fieldsets = (
        ('Header', {
            'fields': ('title', 'slug', 'author', 'status', 'image'),
        }),
        ('Content', {
            'fields': ('body', 'tags', 'semantic_summary'),
        }),
        ('Metadata', {
            'fields': ('publish', 'created', 'updated'),
            'classes': ('collapse',),
        }),
    )
    actions = ['make_published', 'make_draft']

    @admin.action(description='✅ Mark selected posts as published')
    def make_published(self, request, queryset):
        updated = queryset.update(status='published')
        self.message_user(request, f'{updated} post(s) marked as published.')

    @admin.action(description='📝 Mark selected posts as draft')
    def make_draft(self, request, queryset):
        updated = queryset.update(status='draft')
        self.message_user(request, f'{updated} post(s) moved to draft.')


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display  = ('name', 'email', 'post', 'created', 'active')
    list_filter   = ('active', 'created')
    list_editable = ('active',)
    search_fields = ('name', 'email', 'body')
    readonly_fields = ('created', 'updated')
    actions = ['approve_comments', 'reject_comments']

    @admin.action(description='✅ Approve selected comments')
    def approve_comments(self, request, queryset):
        updated = queryset.update(active=True)
        self.message_user(request, f'{updated} comment(s) approved.')

    @admin.action(description='🚫 Reject selected comments')
    def reject_comments(self, request, queryset):
        updated = queryset.update(active=False)
        self.message_user(request, f'{updated} comment(s) rejected.')

from django.urls import path
from django.views.decorators.cache import cache_page
from . import views

app_name = 'blog'

# Cache static pages for 24 hours (86400 seconds) since they rarely change
urlpatterns = [
    path('', views.post_list, name='post_list'),
    path('comment/reply/', views.reply_page, name='reply'),
    path('tag/<slug:tag_slug>/', views.post_list, name='post_tag'),
    path('privacy/', cache_page(86400)(views.privacy), name='privacy'),
    path('terms/', cache_page(86400)(views.terms), name='terms'),
    path('about/', cache_page(86400)(views.about), name='about'),
    path('games/', cache_page(86400)(views.games), name='games'),
    path('api/chat/', views.chat_api, name='chat_api'),
    path('api/chat/status/', views.ai_status, name='ai_status'),
    path('search/live/', views.search_live, name='search_live'),
    # Note: health/ is also registered at root level in iooding/urls.py
    path('<slug:post>/', views.post_detail, name='post_detail'),
]
from django.urls import path
from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.post_list, name="post_list"),
    path('comment/reply/', views.reply_page, name="reply"),
    path('tag/<slug:tag_slug>/', views.post_list, name='post_tag'),
    path('<slug:post>/', views.post_detail, name="post_detail"),
    path('api/chat/', views.chat_api, name='chat_api'), # The AI Endpoint
    path('api/chat/status/', views.ai_status, name='ai_status'),
    path('privacy/', views.privacy, name='privacy'),
    path('about/', views.about, name='about'),
    path('health/', views.health_check, name='health_check'),
]
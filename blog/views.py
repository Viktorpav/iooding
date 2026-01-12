from django.db.models import Q
from taggit.models import Tag
from django.shortcuts import render, get_object_or_404, redirect
from .models import Post, Comment
from .forms import CommentForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count
from django.http import HttpResponse, StreamingHttpResponse
import json, ollama
from django.views.decorators.csrf import csrf_exempt

def post_list(request, tag_slug=None):
    posts = Post.published.all()
    tag = None
    
    # Handle tag filtering
    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)
        posts = posts.filter(tags__in=[tag])
    
    # Handle search query
    query = request.GET.get("q")
    if query:
        posts = posts.filter(
            Q(title__icontains=query) | Q(tags__name__icontains=query)
        ).distinct()
    
    # Pagination
    paginator = Paginator(posts, 10)  # 10 posts in each page
    page = request.GET.get('page')
    
    try:
        posts = paginator.page(page)
    except PageNotAnInteger:
        # If page is not an integer deliver the first page
        posts = paginator.page(1)
    except EmptyPage:
        # If page is out of range deliver last page of results
        posts = paginator.page(paginator.num_pages)
    
    return render(request, 'post_list.html', {
        'posts': posts,
        'page': 'pages',
        'tag': tag,
        'query': query
    })


def post_detail(request, post):
    post = get_object_or_404(Post, slug=post, status='published')
    
    # List of active comments for this post
    comments = post.comments.filter(active=True)
    new_comment = None
    
    if request.method == 'POST':
        # A comment was posted
        comment_form = CommentForm(data=request.POST)
        if comment_form.is_valid():
            # Create Comment object but don't save to database yet
            new_comment = comment_form.save(commit=False)
            # Assign the current post to the comment
            new_comment.post = post
            # Save the comment to the database
            new_comment.save()
            # Redirect to same page and focus on that comment
            return redirect(post.get_absolute_url() + '#' + str(new_comment.id))
    else:
        comment_form = CommentForm()
    
    # List of similar posts
    post_tags_ids = post.tags.values_list('id', flat=True)
    similar_posts = Post.published.filter(tags__in=post_tags_ids).exclude(id=post.id)
    similar_posts = similar_posts.annotate(same_tags=Count('tags')).order_by('-same_tags', '-publish')[:6]
    
    return render(request, 'post_detail.html', {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'similar_posts': similar_posts
    })


def reply_page(request):
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            post_id = request.POST.get('post_id')  # from hidden input
            parent_id = request.POST.get('parent')  # from hidden input
            post_url = request.POST.get('post_url')  # from hidden input
            
            reply = form.save(commit=False)
            reply.post = Post(id=post_id)
            reply.parent = Comment(id=parent_id)
            reply.save()
            
            return redirect(post_url + '#' + str(reply.id))
    
    return redirect("/")


def health_check(request):
    """Simplified health check for K8s probes"""
    return HttpResponse("ok", content_type="text/plain")

# --- Optimized AI Agent (Direct Streaming) ---
# Removed RAG context for lower overhead and faster TTFB (Time To First Byte)
# as requested by the user.

ollama_client = ollama.Client(host='http://192.168.0.18:11434')

@csrf_exempt
def chat_api(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            messages = data.get("messages", [])
            # If no history, use the current message
            if not messages:
                user_msg = data.get("message", "")
                if user_msg:
                    messages = [{'role': 'user', 'content': user_msg}]

            def stream_response():
                try:
                    stream = ollama_client.chat(
                        model='qwen3-coder',
                        messages=messages,
                        stream=True,
                    )
                    
                    for chunk in stream:
                        # 1. Handle "Thinking" (Reasoning)
                        # Note: Ollama python client structure might vary slightly, 
                        # but usually it's in chunk['message']
                        
                        content = chunk.get('message', {}).get('content', '')
                        
                        # Handle legacy deepseek/qwen thinking tags if they appear in content
                        # (Some models output <think>...</think> in content)
                        if '<think>' in content:
                            yield f"data: {json.dumps({'thinking': 'Started thinking...'})}\n\n"
                            # Strip the tag for cleaner content if needed, or send as thinking
                            content = content.replace('<think>', '')
                        
                        if content:
                            yield f"data: {json.dumps({'content': content})}\n\n"
                        
                        # 2. Handle Metrics (Final chunk)
                        if chunk.get('done'):
                            metrics = {
                                'total_duration': chunk.get('total_duration', 0) / 1e9,
                                'eval_count': chunk.get('eval_count', 0),
                                'eval_duration': chunk.get('eval_duration', 1) / 1e9
                            }
                            yield f"data: {json.dumps({'done': True, 'metrics': metrics})}\n\n"
                            
                except Exception as e:
                    print(f"Ollama Error: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"

            response = StreamingHttpResponse(stream_response(), content_type='text/event-stream')
            # Critical headers for Nginx to disable buffering
            response['X-Accel-Buffering'] = 'no'
            response['Cache-Control'] = 'no-cache'
            return response
            
        except Exception as e:
             return HttpResponse(json.dumps({'error': str(e)}), status=500, content_type="application/json")
             
    return HttpResponse("Method not allowed", status=405)
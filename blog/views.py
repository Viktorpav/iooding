from django.db.models import Q
from taggit.models import Tag
from django.shortcuts import render, get_object_or_404, redirect
from .models import Post, Comment
from .forms import CommentForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count
from django.http import HttpResponse, StreamingHttpResponse
import json
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


async def health_check(request):
    """Simplified health check for K8s probes - Async to avoid threadpool block"""
    return HttpResponse("ok", content_type="text/plain")

async def ai_status(request):
    """Endpoint to check the status of the local AI (Ollama)."""
    from .ai_utils import check_ollama_status
    is_online = await check_ollama_status()
    return HttpResponse(json.dumps({'online': is_online}), content_type="application/json")

# --- Optimized AI Agent (Async Direct Streaming) ---

@csrf_exempt
async def chat_api(request):
    """
    Async API endpoint for AI Chat.
    Handles message history, RAG context, and streams responses from Ollama.
    """
    if request.method != "POST":
        return HttpResponse("Method not allowed", status=405)

    try:
        data = json.loads(request.body)
        user_msg = data.get("message", "")
        history = data.get("messages", [])
        
        # Build prompt: last 10 turns + current message
        messages = history[-10:] if history else []
        if user_msg and (not messages or messages[-1].get('content') != user_msg):
            messages.append({'role': 'user', 'content': user_msg})

        if not messages:
            return HttpResponse(json.dumps({'error': 'Empty message'}), status=400)

        from blog.ai_utils import get_ollama_client, generate_rag_context, get_rag_system_prompt
        client = get_ollama_client(async_client=True)

        async def stream_response():
            try:
                yield f"data: {json.dumps({'thinking': 'Analyzing intent and scope...'})}\n\n"
                
                # 1. Classification & Context Discovery
                context_text = await generate_rag_context(user_msg, client)
                
                if context_text == "NO_RAG_NEEDED":
                    yield f"data: {json.dumps({'thinking': 'General query detected. Responding directly...'})}\n\n"
                    messages.insert(0, {'role': 'system', 'content': "You are 'Ding AI'. Provide a helpful, concise response."})
                elif context_text:
                    messages.insert(0, {'role': 'system', 'content': get_rag_system_prompt(context_text)})
                    yield f"data: {json.dumps({'thinking': 'Knowledge retrieved. Synthesizing final answer...'})}\n\n"
                else:
                    messages.insert(0, {'role': 'system', 'content': "You are 'Ding AI'. Context limited. Help generally."})
                    yield f"data: {json.dumps({'thinking': 'Limited info found. Using latent knowledge...'})}\n\n"

                # 2. Optimized Chat Stream (Suggestion 8)
                options = {
                    "temperature": 0.2, # Stable & focused
                    "top_p": 0.9,
                    "repeat_penalty": 1.1,
                    "num_ctx": 4096
                }
                
                chat_resp = await client.chat(
                    model='qwen3-coder:latest', 
                    messages=messages, 
                    stream=True, 
                    options=options
                )
                
                async for chunk in chat_resp:
                    content = chunk.get('message', {}).get('content', '')
                    if content:
                        yield f"data: {json.dumps({'content': content})}\n\n"
                    
                    if chunk.get('done'):
                        metrics = {
                            'total_duration': chunk.get('total_duration', 0) / 1e9,
                            'eval_count': chunk.get('eval_count', 0),
                            'eval_duration': (chunk.get('eval_duration', 0) / 1e9) or 0.001
                        }
                        yield f"data: {json.dumps({'done': True, 'metrics': metrics})}\n\n"
                        
            except Exception as e:
                yield f"data: {json.dumps({'error': f'AI Error: {str(e)}'})}\n\n"
def privacy(request):
    return render(request, 'privacy.html')

        response = StreamingHttpResponse(stream_response(), content_type='text/event-stream')
        response['X-Accel-Buffering'], response['Cache-Control'] = 'no', 'no-cache'
        return response
            
    except Exception as e:
         return HttpResponse(json.dumps({'error': str(e)}), status=500, content_type="application/json")
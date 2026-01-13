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

# --- Optimized AI Agent (Async Direct Streaming) ---

@csrf_exempt
async def chat_api(request):
    print("AI Chat API call started.")
    if request.method == "POST":
        try:
            # 1. Read body safely
            try:
                # In Django 5.x async views, request.body is okay but we'll monitor it
                body_bytes = request.body
                print(f"Body received, size: {len(body_bytes)}")
                data = json.loads(body_bytes)
            except Exception as e:
                print(f"Error parsing request body: {e}")
                return HttpResponse(json.dumps({'error': f'Invalid request body: {e}'}), status=400)
            
            messages = data.get("messages", [])
            if not messages:
                user_msg = data.get("message", "")
                if user_msg:
                    messages = [{'role': 'user', 'content': user_msg}]

            print(f"Messages count: {len(messages)}")

            # 2. Imports and Client
            try:
                from blog.ai_utils import get_ollama_client, generate_rag_context
                client = get_ollama_client(async_client=True)
                print("Ollama client initialized.")
            except Exception as e:
                import traceback
                print(f"Error initializing AI utils: {traceback.format_exc()}")
                return HttpResponse(json.dumps({'error': f'AI Startup Error: {e}'}), status=500)

            # 3. Stream Generator
            async def stream_response():
                try:
                    print("Stream Generator started.")
                    # 1. Immediate feedback to user
                    yield f"data: {json.dumps({'thinking': 'Analyzing query...'})}\n\n"
                    
                    # 2. RAG Logic
                    user_msg_content = ""
                    for m in reversed(messages):
                        if m['role'] == 'user':
                            user_msg_content = m['content']
                            break
                    
                    if user_msg_content:
                        print(f"Generating RAG context for: {user_msg_content[:30]}...")
                        context_text = await generate_rag_context(user_msg_content, client)
                        if context_text:
                            print("Context found, adding to messages.")
                            system_prompt = f"You are a helpful assistant. Use the following context to answer:\n\n{context_text}"
                            messages.insert(0, {'role': 'system', 'content': system_prompt})
                            yield f"data: {json.dumps({'thinking': 'Context retrieved, generating answer...'})}\n\n"
                        else:
                            print("No relevant context found.")
                            yield f"data: {json.dumps({'thinking': 'Direct response (no relevant context found)...'})}\n\n"

                    # 3. Stream from Ollama
                    print(f"Starting chat stream from Ollama model: qwen3-coder:latest")
                    try:
                        # Use await on the result if it's a coroutine returning an async iterator
                        chat_resp = await client.chat(
                            model='qwen3-coder:latest',
                            messages=messages,
                            stream=True,
                        )
                        print("Ollama stream connection established.")
                        
                        async for chunk in chat_resp:
                            content = chunk.get('message', {}).get('content', '')
                            
                            if '<think>' in content:
                                yield f"data: {json.dumps({'thinking': 'Started thinking...'})}\n\n"
                                content = content.replace('<think>', '')
                            
                            if content:
                                yield f"data: {json.dumps({'content': content})}\n\n"
                            
                            if chunk.get('done'):
                                metrics = {
                                    'total_duration': chunk.get('total_duration', 0) / 1e9,
                                    'eval_count': chunk.get('eval_count', 0),
                                    'eval_duration': (chunk.get('eval_duration', 0) / 1e9) or 0.001
                                }
                                yield f"data: {json.dumps({'done': True, 'metrics': metrics})}\n\n"
                                break # End of stream
                    except Exception as e:
                        import traceback
                        print(f"Ollama inner chat error: {traceback.format_exc()}")
                        yield f"data: {json.dumps({'error': f'Ollama Chat Error: {str(e)}'})}\n\n"

                except Exception as e:
                    import traceback
                    print(f"Stream Generator outer error: {traceback.format_exc()}")
                    yield f"data: {json.dumps({'error': f'Stream Processing Error: {str(e)}'})}\n\n"

            print("Returning StreamingHttpResponse.")
            response = StreamingHttpResponse(stream_response(), content_type='text/event-stream')
            response['X-Accel-Buffering'] = 'no'
            response['Cache-Control'] = 'no-cache'
            return response
            
        except Exception as e:
             import traceback
             print(f"Chat API Top-level Recovery: {traceback.format_exc()}")
             return HttpResponse(json.dumps({'error': str(e)}), status=500, content_type="application/json")
             
    return HttpResponse("Method not allowed", status=405)
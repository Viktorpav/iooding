from django.db.models import Q
from taggit.models import Tag
from django.shortcuts import render, get_object_or_404, redirect
from .models import Post, Comment
from .forms import CommentForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Count
from django.http import HttpResponse
import json, ollama
from django.http import StreamingHttpResponse
from pgvector.django import CosineDistance
from .models import PostChunk


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

# 1. Helper: Find relevant context from your blog
def get_blog_context(query_text):
    # Convert user query to embedding using Ollama
    query_embedding = ollama.embeddings(model='nomic-embed-text', prompt=query_text)['embedding']
    
    # Semantic search in Postgres
    relevant_chunks = PostChunk.objects.annotate(
        distance=CosineDistance('embedding', query_embedding)
    ).order_by('distance')[:3]
    
    return "\n".join([c.content for c in relevant_chunks])

# 2. The AI Agent View (Streaming)
def chat_api(request):
    if request.method == "POST":
        data = json.loads(request.body)
        user_query = data.get("message", "")
        # Support full message history if provided
        history = data.get("messages", [])
        
        # Get context from database
        context = get_blog_context(user_query)
        
        system_prompt = f"""
        You are Ding Assistant, a helpful and technical AI for this blog.
        Base your answers on the following blog context as much as possible:
        {context}
        
        If the information isn't in the context, answer from your general knowledge but clarify it.
        Be concise, friendly, and use markdown for code or emphasis.
        """

        messages = [{'role': 'system', 'content': system_prompt}]
        if history:
            messages.extend(history)
        else:
            messages.append({'role': 'user', 'content': user_query})

        def stream_response():
            try:
                stream = ollama.chat(
                    model='qwen3-coder:30b',
                    messages=messages,
                    stream=True,
                )
                for chunk in stream:
                    content = chunk['message']['content']
                    data_packet = {'content': content}
                    
                    if chunk.get('done'):
                        data_packet['done'] = True
                        data_packet['metrics'] = {
                            'total_duration': chunk.get('total_duration', 0) / 1e9,
                            'eval_count': chunk.get('eval_count', 0),
                            'eval_duration': chunk.get('eval_duration', 1) / 1e9
                        }
                    
                    yield f"data: {json.dumps(data_packet)}\n\n"
                    
            except Exception as e:
                # Critical: Log the error and send to client
                print(f"Ollama Error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return StreamingHttpResponse(stream_response(), content_type='text/event-stream')
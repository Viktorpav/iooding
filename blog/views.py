from django.db.models import Q, Count
from taggit.models import Tag
from django.shortcuts import render, get_object_or_404, redirect
from .models import Post, Comment
from .forms import CommentForm
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import json
import logging

logger = logging.getLogger(__name__)

POSTS_PER_PAGE = 10


def post_list(request, tag_slug=None):
    posts = Post.published.select_related('author').prefetch_related('tags')
    tag = None

    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)
        posts = posts.filter(tags__in=[tag])

    query = request.GET.get('q', '').strip()
    if query:
        posts = posts.filter(
            Q(title__icontains=query) | Q(tags__name__icontains=query)
        ).distinct()

    paginator = Paginator(posts, POSTS_PER_PAGE)
    page = request.GET.get('page')
    try:
        posts = paginator.page(page)
    except PageNotAnInteger:
        posts = paginator.page(1)
    except EmptyPage:
        posts = paginator.page(paginator.num_pages)

    return render(request, 'post_list.html', {
        'posts': posts,
        'tag': tag,
        'query': query,
    })


def post_detail(request, post):
    post = get_object_or_404(
        Post.published.select_related('author').prefetch_related('tags'),
        slug=post,
    )
    comments = post.comments.filter(active=True, parent=None).select_related()
    comment_form = CommentForm()

    if request.method == 'POST':
        comment_form = CommentForm(data=request.POST)
        if comment_form.is_valid():
            new_comment = comment_form.save(commit=False)
            new_comment.post = post
            new_comment.save()
            return redirect(post.get_absolute_url() + '#' + str(new_comment.id))

    post_tags_ids = post.tags.values_list('id', flat=True)
    similar_posts = (
        Post.published
        .filter(tags__in=post_tags_ids)
        .exclude(id=post.id)
        .annotate(same_tags=Count('tags'))
        .order_by('-same_tags', '-publish')[:6]
    )

    return render(request, 'post_detail.html', {
        'post': post,
        'comments': comments,
        'comment_form': comment_form,
        'similar_posts': similar_posts,
    })


@require_POST
def reply_page(request):
    form = CommentForm(request.POST)
    if form.is_valid():
        post_id = request.POST.get('post_id')
        parent_id = request.POST.get('parent')
        post_url = request.POST.get('post_url', '/')

        reply = form.save(commit=False)
        reply.post_id = post_id
        reply.parent_id = parent_id
        reply.save()
        return redirect(post_url + '#' + str(reply.id))
    return redirect('/')


async def health_check(request):
    """Lightweight K8s liveness/readiness probe."""
    return HttpResponse('ok', content_type='text/plain')


async def ai_status(request):
    """Check Ollama availability."""
    from .ai_utils import check_ollama_status
    is_online = await check_ollama_status()
    return HttpResponse(
        json.dumps({'online': is_online}),
        content_type='application/json',
    )


@csrf_exempt
async def chat_api(request):
    """
    Async SSE endpoint for AI chat with RAG.
    Streams responses from Ollama token-by-token.
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)

    try:
        data = json.loads(request.body)
        user_msg = data.get('message', '').strip()
        history = data.get('messages', [])

        # Keep last 10 turns to bound token usage
        messages = list(history[-10:])
        if user_msg and (not messages or messages[-1].get('content') != user_msg):
            messages.append({'role': 'user', 'content': user_msg})

        if not messages:
            return HttpResponse(
                json.dumps({'error': 'Empty message'}),
                status=400,
                content_type='application/json',
            )

        from blog.ai_utils import get_ollama_client, generate_rag_context, get_rag_system_prompt
        client = get_ollama_client(async_client=True)

        async def stream_response():
            try:
                yield f"data: {json.dumps({'thinking': 'Analyzing intent...'})}\n\n"

                context_text = await generate_rag_context(user_msg, client)

                if context_text == 'NO_RAG_NEEDED':
                    yield f"data: {json.dumps({'thinking': 'General query – responding directly...'})}\n\n"
                    messages.insert(0, {'role': 'system', 'content': "You are 'Ding AI'. Be helpful and concise."})
                elif context_text:
                    messages.insert(0, {'role': 'system', 'content': get_rag_system_prompt(context_text)})
                    yield f"data: {json.dumps({'thinking': 'Knowledge retrieved – synthesizing answer...'})}\n\n"
                else:
                    messages.insert(0, {'role': 'system', 'content': "You are 'Ding AI'. Context limited. Help generally."})
                    yield f"data: {json.dumps({'thinking': 'Limited context – using latent knowledge...'})}\n\n"

                options = {
                    'temperature': 0.2,
                    'top_p': 0.9,
                    'repeat_penalty': 1.1,
                    'num_ctx': 4096,
                }
                chat_resp = await client.chat(
                    model='qwen3-coder:latest',
                    messages=messages,
                    stream=True,
                    options=options,
                )

                async for chunk in chat_resp:
                    content = chunk.get('message', {}).get('content', '')
                    if content:
                        yield f"data: {json.dumps({'content': content})}\n\n"

                    if chunk.get('done'):
                        metrics = {
                            'total_duration': round(chunk.get('total_duration', 0) / 1e9, 2),
                            'eval_count': chunk.get('eval_count', 0),
                            'tokens_per_sec': round(
                                chunk.get('eval_count', 0) /
                                max(chunk.get('eval_duration', 1) / 1e9, 0.001), 1
                            ),
                        }
                        yield f"data: {json.dumps({'done': True, 'metrics': metrics})}\n\n"

            except Exception as exc:
                logger.error('chat_api stream error: %s', exc)
                yield f"data: {json.dumps({'error': f'AI Error: {exc}'})}\n\n"

        response = StreamingHttpResponse(stream_response(), content_type='text/event-stream')
        response['X-Accel-Buffering'] = 'no'
        response['Cache-Control'] = 'no-cache'
        return response

    except Exception as exc:
        logger.exception('chat_api error')
        return HttpResponse(
            json.dumps({'error': str(exc)}),
            status=500,
            content_type='application/json',
        )


def privacy(request):
    return render(request, 'privacy.html')


def about(request):
    return render(request, 'about.html')
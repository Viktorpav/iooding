import json
import hashlib
import logging

from django.db import connections
from django.db.models import Count
from django.shortcuts import render, get_object_or_404, redirect
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, StreamingHttpResponse
from django.views.decorators.http import require_POST
from django.core.cache import cache
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank

from taggit.models import Tag

from .models import Post
from .forms import CommentForm
from .ai_utils import (
    check_ai_status,
    generate_rag_context,
    get_ai_client,
    get_rag_system_prompt,
)
from .redis_vectors import search_similar_async, get_cached_embedding_async, cache_embedding_async

logger = logging.getLogger(__name__)

POSTS_PER_PAGE = 10

def post_list(request, tag_slug=None):
    posts = Post.published.select_related('author').prefetch_related('tags')
    tag = None

    if tag_slug:
        tag = Tag.objects.filter(slug=tag_slug).first()
        if tag:
            posts = posts.filter(tags__in=[tag])
        else:
            posts = posts.none()
            tag = {'name': tag_slug.replace('-', ' ').title(), 'slug': tag_slug}

    query = request.GET.get('q', '').strip()
    if query:
        search_vector = SearchVector('title', weight='A') + SearchVector('tags__name', weight='B')
        search_query = SearchQuery(query)
        posts = posts.annotate(
            rank=SearchRank(search_vector, search_query)
        ).filter(rank__gte=0.1).order_by('-rank').distinct()

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

def get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')

def post_detail(request, post):
    post = get_object_or_404(
        Post.published.select_related('author').prefetch_related('tags'),
        slug=post,
    )
    comments = post.comments.filter(active=True, parent=None).select_related()
    comment_form = CommentForm()

    if request.method == 'POST':
        ip = get_client_ip(request)
        cache_key = f"comment_rate:{ip}"
        if cache.get(cache_key):
            return HttpResponse('Rate limit exceeded. Please wait 10s.', status=429)
        cache.set(cache_key, True, timeout=10)

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
    ip = get_client_ip(request)
    cache_key = f"comment_rate:{ip}"
    if cache.get(cache_key):
        return HttpResponse('Rate limit exceeded. Please wait 10s.', status=429)
    
    cache.set(cache_key, True, timeout=10)

    form = CommentForm(request.POST)
    if form.is_valid():
        post_id = request.POST.get('post_id')
        parent_id = request.POST.get('parent')
        post_url = request.POST.get('post_url', '/')

        if not post_id:
            logger.warning("Reply attempt without post_id")
            return redirect('/')

        reply = form.save(commit=False)
        reply.post_id = int(post_id)
        if parent_id:
            reply.parent_id = int(parent_id)
        reply.save()
        return redirect(post_url + '#' + str(reply.id))
    
    logger.warning(f"Comment form invalid: {form.errors}")
    return redirect('/')

def health_check(request):
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute("SELECT 1")
        return HttpResponse('ok', content_type='text/plain')
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HttpResponse('Service Unavailable', status=503, content_type='text/plain')

async def ai_status(request):
    try:
        is_online = await check_ai_status()
        return HttpResponse(
            json.dumps({'online': is_online}),
            content_type='application/json',
        )
    except Exception as e:
        logger.warning(f"AI status check failed: {e}")
        return HttpResponse(
            json.dumps({'online': False, 'error': str(e)}),
            content_type='application/json',
            status=200,
        )

async def chat_api(request):
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)

    try:
        data = json.loads(request.body)
        user_msg = data.get('message', '').strip()
        history = data.get('messages', [])

        if not user_msg:
            return HttpResponse(
                json.dumps({'error': 'Empty message'}),
                status=400, content_type='application/json',
            )

        messages = list(history[-4:])
        if not messages or messages[-1].get('content') != user_msg:
            messages.append({'role': 'user', 'content': user_msg})

        cache_key = f"ai:exact:{hashlib.sha256(user_msg.lower().encode()).hexdigest()}"
        cached = cache.get(cache_key)

        if cached:
            async def stream_cached():
                yield f"data: {json.dumps({'thinking': '⚡ Cached response — instant answer'})}\n\n"
                for i in range(0, len(cached['content']), 60):
                    yield f"data: {json.dumps({'content': cached['content'][i:i+60]})}\n\n"
                metrics = {**cached['metrics'], 'cached': True}
                yield f"data: {json.dumps({'done': True, 'metrics': metrics})}\n\n"

            resp = StreamingHttpResponse(stream_cached(), content_type='text/event-stream')
            resp['X-Accel-Buffering'] = 'no'
            resp['Cache-Control'] = 'no-cache, no-transform'
            resp['Content-Encoding'] = 'identity'
            return resp

        client = get_ai_client()

        async def stream_response():
            accumulated = ""
            try:
                yield f"data: {json.dumps({'thinking': 'Searching knowledge base...'})}\n\n"
                context_text = await generate_rag_context(user_msg, client)

                if context_text == 'NO_RAG_NEEDED':
                    yield f"data: {json.dumps({'thinking': 'Responding directly...'})}\n\n"
                    messages.insert(0, {'role': 'system', 'content': "You are Ding AI for iooding.local. Be concise, use markdown."})
                else:
                    messages.insert(0, {'role': 'system', 'content': get_rag_system_prompt(context_text)})
                    yield f"data: {json.dumps({'thinking': 'Context found — generating answer...'})}\n\n"

                chat_resp = await client.chat(
                    model=None,
                    messages=messages,
                    stream=True,
                    options={'temperature': 0.2, 'top_p': 0.9},
                )

                async for chunk in chat_resp:
                    content = chunk.get('message', {}).get('content', '')
                    if content:
                        accumulated += content
                        yield f"data: {json.dumps({'content': content})}\n\n"

                    if chunk.get('done'):
                        metrics = {
                            'total_duration': round(chunk.get('total_duration', 0) / 1e9, 2),
                            'eval_count': chunk.get('eval_count', 0),
                            'tokens_per_sec': round(chunk.get('eval_count', 0) / max(chunk.get('eval_duration', 1) / 1e9, 0.001), 1),
                            'cached': False,
                        }
                        if accumulated:
                            cache.set(cache_key, {'content': accumulated, 'metrics': metrics}, timeout=3600)
                        yield f"data: {json.dumps({'done': True, 'metrics': metrics})}\n\n"
            except Exception as exc:
                logger.error(f"Stream Error: {exc}")
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        response = StreamingHttpResponse(stream_response(), content_type='text/event-stream')
        response['X-Accel-Buffering'] = 'no'
        response['Cache-Control'] = 'no-cache, no-transform'
        response['Content-Encoding'] = 'identity'
        return response
    except Exception as exc:
        logger.exception('chat_api error: %s', exc)
        return HttpResponse(json.dumps({'error': str(exc)}), status=500, content_type='application/json')

def privacy(request):
    return render(request, 'privacy.html')

def about(request):
    return render(request, 'about.html')

def terms(request):
    return render(request, 'terms.html')

def games(request):
    return render(request, 'games.html')

async def search_live(request):
    """
    HTMX live search endpoint.
    Ultra-clean Hybrid Search: Ranked Keywords -> Neural Fallback.
    """
    query = request.GET.get('q', '').strip()
    if not query or len(query) < 2:
        return HttpResponse('')

    from asgiref.sync import sync_to_async

    # 1. Advanced Keyword Search (Ranked)
    @sync_to_async
    def get_ranked_results(q):
        search_vector = SearchVector('title', weight='A') + SearchVector('tags__name', weight='B')
        search_query = SearchQuery(q)
        return list(
            Post.published.annotate(rank=SearchRank(search_vector, search_query))
            .filter(rank__gte=0.03)
            .select_related('author')
            .prefetch_related('tags')
            .order_by('-rank')[:5]
        )
    
    results = await get_ranked_results(query)
    search_type = 'classic'

    # 2. Neural Fallback (if classic finds nothing or very little)
    # We trigger neural if classic results are < 2 to ensure high-quality suggestions
    if len(results) < 2:
        try:
            client = get_ai_client()
            embedding = await get_cached_embedding_async(query)
            if not embedding:
                emb_resp = await client.embeddings(model=None, prompt=query)
                embedding = emb_resp['embedding']
                await cache_embedding_async(query, embedding)
            
            vector_results = await search_similar_async(embedding, top_k=5, max_distance=0.5)
            if vector_results:
                post_ids = [r['post_id'] for r in vector_results]
                
                @sync_to_async
                def get_posts(ids):
                    order = {id: i for i, id in enumerate(ids)}
                    qs = list(Post.published.filter(id__in=ids).select_related('author'))
                    # Merge results if any classic existed, otherwise just neural
                    return qs
                
                neural_results = await get_posts(post_ids)
                
                # Deduplicate and prioritize classic results
                existing_ids = {p.id for p in results}
                for p in neural_results:
                    if p.id not in existing_ids:
                        results.append(p)
                        if len(results) >= 5: break
                
                if any(p for p in results if p.id not in existing_ids):
                    search_type = 'neural'
                    
        except Exception as e:
            logger.warning(f"Live Neural Search failed: {e}")

    return render(request, 'blog/partials/search_results.html', {
        'results': results[:5],
        'query': query,
        'search_type': search_type
    })
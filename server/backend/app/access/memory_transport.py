"""Versioned, default-off private story collaboration HTTP contract."""
import asyncio
import base64
import binascii

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _integer, _query
from .memory_books import MemoryBooks, FIELDS as BOOK_FIELDS
from .memory_book_editorial import MemoryBookEditorial
from .memory_book_planning import MemoryBookPlanning
from .memory_contributions import MemoryContributions, FIELDS as CONTRIBUTION_FIELDS
from .memory_jobs import MemoryJobs
from .memory_stories import _json
from .service import AccessService
from .stories import _uuid
from .transport import TransportError, _body, _runtime, _single, credentials_from_request

router = APIRouter(route_class=LibraryRoute)


def call(runtime, store, action, *args, editorial_enabled=False):
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        instance = (store(access, editorial_enabled=editorial_enabled)
                    if store in (MemoryJobs, MemoryBookPlanning) else store(access))
        if action == 'authorize_contribution':
            with instance.access._transaction():
                instance._parent(*args)
            return None
        return getattr(instance, action)(*args)


def authorize(runtime, token, library):
    with runtime.connection_factory() as db:
        return AccessService(db, clock=runtime.clock).require(token, library, 'library.read')


async def scope(request, *, originals=False, generation=False, allowed=None):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, allowed or {'library', 'page'})
    runtime = _runtime(request, allow_query=True)
    await run_in_threadpool(authorize, runtime, token, query['library'])
    if not request.app.state.memory_collaboration_enabled:
        raise TransportError(503, 'Memory community unavailable')
    if not request.app.state.memory_retention_healthy:
        raise TransportError(503, 'Memory history maintenance unavailable')
    if originals and not request.app.state.memory_originals_enabled:
        raise TransportError(503, 'Original memory contributions unavailable')
    if generation and not request.app.state.memory_generation_enabled:
        raise TransportError(503, 'Memory drafting unavailable')
    return runtime, token, query


def json_response(value):
    response = JSONResponse(value)
    if len(response.body)>512*1024:
        raise TransportError(503, 'Memory response unavailable')
    return response


@router.get('/memory-community/v1/capabilities')
async def capabilities(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    await run_in_threadpool(authorize, _runtime(request, allow_query=True), token, query['library'])
    state = request.app.state
    return JSONResponse({'version':1, 'enabled':state.memory_collaboration_enabled,
        'contributions_enabled':state.memory_originals_enabled,
        'generation_enabled':state.memory_generation_enabled, 'conversation_retention_days':30,
        'audio_format':'wav_pcm16_mono_16000', 'max_audio_seconds':30,
        'max_text_bytes':8192, 'original_retention':'until_owner_deletes'})


@router.get('/memory-community/v1/books')
async def books(request: Request):
    runtime, token, query = await scope(request)
    return json_response(await run_in_threadpool(call, runtime, MemoryBooks, 'list', token,
        query['library'], _integer(query.get('page','1'),100000)))


@router.get('/memory-community/v1/books/{book_id}')
async def book(book_id: str, request: Request):
    runtime, token, query = await scope(request)
    return json_response(await run_in_threadpool(call, runtime, MemoryBooks, 'get', token,
                                                 query['library'], _uuid(book_id)))




def call_editorial(runtime, action, *args):
    with runtime.connection_factory() as db:
        instance = MemoryBookEditorial(AccessService(db, clock=runtime.clock), enabled=True)
        return getattr(instance, action)(*args)


async def editorial_scope(request):
    runtime, token, query = await scope(request, allowed={'library'})
    if not request.app.state.memory_editorial_enabled:
        raise TransportError(503, 'Memoir editorial unavailable')
    return runtime, token, query


def editorial_context_choice(request, query):
    if 'editorial_context' not in query:
        return False
    if query['editorial_context'] != '1':
        raise TransportError(400, 'Invalid memoir context choice')
    if not request.app.state.memory_editorial_enabled:
        raise TransportError(503, 'Memoir drafting context unavailable')
    return True


async def editorial_body(request):
    if (_single(request, 'content-encoding') is not None
            or _single(request, 'content-type') != 'application/json'):
        raise TransportError(400, 'Invalid memoir editorial content type')
    length = _single(request, 'content-length')
    if length is not None and (not length.isascii() or not length.isdecimal() or int(length)>65536):
        raise TransportError(413, 'Memoir editorial request too large')
    raw = bytearray()
    try:
        async with asyncio.timeout(10):
            async for part in request.stream():
                if len(raw)+len(part)>65536:
                    raise TransportError(413, 'Memoir editorial request too large')
                raw.extend(part)
    except TimeoutError:
        raise TransportError(408, 'Memoir editorial request timed out') from None
    if length is not None and len(raw)!=int(length):
        raise TransportError(400, 'Incomplete memoir editorial request')
    return bytes(raw)


@router.get('/memory-community/v1/books/{book_id}/editorial')
async def book_editorial(book_id: str, request: Request):
    runtime, token, query = await editorial_scope(request)
    return json_response(await run_in_threadpool(call_editorial, runtime, 'get',
        token, query['library'], _uuid(book_id)))


@router.put('/memory-community/v1/books/{book_id}/editorial')
async def edit_book_editorial(book_id: str, request: Request):
    runtime, token, query = await editorial_scope(request)
    raw = await editorial_body(request)
    return json_response(await run_in_threadpool(call_editorial, runtime, 'save',
        token, query['library'], _uuid(book_id), raw))


@router.get('/memory-community/v1/books/{book_id}/plan')
async def book_plan(book_id: str, request: Request):
    runtime, token, query = await scope(request, allowed={'library', 'editorial_context'})
    selected = editorial_context_choice(request, query)
    return json_response(await run_in_threadpool(call, runtime, MemoryBookPlanning, 'get',
        token, query['library'], _uuid(book_id), selected,
        editorial_enabled=request.app.state.memory_editorial_enabled))


async def save_book(request, ident=None):
    runtime, token, query = await scope(request)
    body = await _body(request, BOOK_FIELDS, max_body=64*1024)
    return json_response(await run_in_threadpool(call, runtime, MemoryBooks, 'save', token,
        query['library'], body, ident))


@router.post('/memory-community/v1/books')
async def create_book(request: Request):
    return await save_book(request)


@router.put('/memory-community/v1/books/{book_id}')
async def edit_book(book_id: str, request: Request):
    return await save_book(request, _uuid(book_id))


@router.get('/memory-community/v1/stories/{story_id}/contributions')
async def contributions(story_id: str, request: Request):
    runtime, token, query = await scope(request, originals=True)
    return json_response(await run_in_threadpool(call, runtime, MemoryContributions, 'list', token,
        query['library'], _uuid(story_id), _integer(query.get('page','1'),100000)))


@router.get('/memory-community/v1/stories/{story_id}/contributions/{contribution_id}')
async def contribution(story_id: str, contribution_id: str, request: Request):
    runtime, token, query = await scope(request, originals=True)
    return json_response(await run_in_threadpool(call, runtime, MemoryContributions, 'get', token,
        query['library'], _uuid(story_id), _uuid(contribution_id)))


@router.post('/memory-community/v1/stories/{story_id}/contributions/text')
async def create_text(story_id: str, request: Request):
    runtime, token, query = await scope(request, originals=True)
    body = await _body(request, CONTRIBUTION_FIELDS, max_body=64*1024)
    if body['kind']!='text':
        raise TransportError(400, 'Invalid contribution kind')
    return json_response(await run_in_threadpool(call, runtime, MemoryContributions, 'create', token,
        query['library'], _uuid(story_id), body))


async def wav_body(request):
    if _single(request, 'content-encoding') is not None or _single(request,'content-type')!='audio/wav':
        raise TransportError(400, 'Invalid recording content type')
    length = _single(request, 'content-length')
    if length is not None and (not length.isascii() or not length.isdecimal() or int(length)>2*1024*1024):
        raise TransportError(413, 'Recording too large')
    raw = bytearray()
    try:
        async with asyncio.timeout(10):
            async for part in request.stream():
                if len(raw)+len(part)>2*1024*1024:
                    raise TransportError(413, 'Recording too large')
                raw.extend(part)
    except TimeoutError:
        raise TransportError(408, 'Recording upload timed out') from None
    if length is not None and len(raw)!=int(length):
        raise TransportError(400, 'Incomplete recording')
    return bytes(raw)


@router.post('/memory-community/v1/stories/{story_id}/contributions/audio')
async def create_audio(story_id: str, request: Request):
    runtime, token, query = await scope(request, originals=True)
    ident = _uuid(story_id)
    await run_in_threadpool(call, runtime, MemoryContributions, 'authorize_contribution', token,
                            query['library'], ident)
    encoded = _single(request,'x-photohouse-memory-metadata')
    try:
        if not encoded or len(encoded)>4096 or not encoded.isascii():
            raise ValueError()
        body = _json(base64.b64decode(encoded, validate=True).decode('utf-8'))
        if type(body) is not dict or set(body)!=CONTRIBUTION_FIELDS or body.get('kind')!='audio':
            raise ValueError()
    except (ValueError, UnicodeError, binascii.Error, RecursionError):
        raise TransportError(400, 'Invalid recording metadata') from None
    audio = await wav_body(request)
    return json_response(await run_in_threadpool(call, runtime, MemoryContributions, 'create', token,
        query['library'], ident, body, audio))


@router.get('/memory-community/v1/stories/{story_id}/contributions/{contribution_id}/audio')
async def contribution_audio(story_id: str, contribution_id: str, request: Request):
    runtime, token, query = await scope(request, originals=True)
    audio = await run_in_threadpool(call, runtime, MemoryContributions, 'audio', token,
        query['library'], _uuid(story_id), _uuid(contribution_id))
    return Response(audio, media_type='audio/wav', headers={'Content-Disposition':'inline; filename="memory.wav"'})


@router.post('/memory-community/v1/stories/{story_id}/contributions/{contribution_id}/review')
async def review_contribution(story_id: str, contribution_id: str, request: Request):
    runtime, token, query = await scope(request, originals=True)
    body = await _body(request, {'state','revision'})
    return json_response(await run_in_threadpool(call, runtime, MemoryContributions, 'review', token,
        query['library'], _uuid(story_id), _uuid(contribution_id), body['state'], body['revision']))


@router.delete('/memory-community/v1/stories/{story_id}/contributions/{contribution_id}')
async def delete_contribution(story_id: str, contribution_id: str, request: Request):
    runtime, token, query = await scope(request, originals=True)
    return json_response(await run_in_threadpool(call, runtime, MemoryContributions, 'delete', token,
        query['library'], _uuid(story_id), _uuid(contribution_id)))


@router.post('/memory-community/v1/conversations')
async def start_conversation(request: Request):
    runtime, token, query = await scope(request, generation=True)
    body = await _body(request, {'id','target_type','target_id'})
    return json_response(await run_in_threadpool(call, runtime, MemoryJobs, 'start', token,
        query['library'], body['target_type'], body['target_id'], body['id']))


@router.get('/memory-community/v1/conversations')
async def list_conversations(request: Request):
    runtime, token, query = await scope(request, allowed={'library','target_type','target_id','preview'})
    if not {'library','target_type','target_id'} <= set(query):
        raise TransportError(400, 'Select a memory target')
    if 'preview' in query and query['preview'] != '1':
        raise TransportError(400, 'Invalid conversation preview option')
    return json_response(await run_in_threadpool(call, runtime, MemoryJobs, 'conversations', token,
        query['library'], query['target_type'], query['target_id'], query.get('preview') == '1'))


@router.get('/memory-community/v1/conversations/{conversation_id}/turns')
async def conversation_turns(conversation_id: str, request: Request):
    runtime, token, query = await scope(request, allowed={'library', 'page', 'reply_context', 'order'})
    if 'reply_context' in query and query['reply_context'] != '1':
        raise TransportError(400, 'Invalid reply context option')
    if 'order' in query and query['order'] != 'recent':
        raise TransportError(400, 'Invalid history order option')
    return json_response(await run_in_threadpool(call, runtime, MemoryJobs, 'turns', token,
        query['library'], _uuid(conversation_id), _integer(query.get('page','1'),100000),
        query.get('reply_context') == '1', query.get('order') == 'recent',
        editorial_enabled=request.app.state.memory_editorial_enabled))


@router.post('/memory-community/v1/conversations/{conversation_id}/turns')
async def send_turn(conversation_id: str, request: Request):
    runtime, token, query = await scope(request, generation=True, allowed={'library', 'editorial_context'})
    selected = editorial_context_choice(request, query)
    body = await _body(request, {'revision','mutation_id','text'}, max_body=32*1024)
    return json_response(await run_in_threadpool(call, runtime, MemoryJobs, 'send', token,
        query['library'], _uuid(conversation_id), body['revision'], body['mutation_id'], body['text'], selected,
        editorial_enabled=request.app.state.memory_editorial_enabled))


@router.delete('/memory-community/v1/conversations/{conversation_id}')
async def close_conversation(conversation_id: str, request: Request):
    runtime, token, query = await scope(request)
    return json_response(await run_in_threadpool(call, runtime, MemoryJobs, 'close', token,
        query['library'], _uuid(conversation_id)))


@router.post('/memory-community/v1/jobs')
async def queue_narrative(request: Request):
    runtime, token, query = await scope(request, generation=True, allowed={'library', 'editorial_context'})
    selected = editorial_context_choice(request, query)
    body = await _body(request, {'target_type','target_id','revision','mutation_id','instructions'}, max_body=32*1024)
    return json_response(await run_in_threadpool(call, runtime, MemoryJobs, 'narrative', token,
        query['library'], body['target_type'], body['target_id'], body['revision'], body['mutation_id'], body['instructions'], selected,
        editorial_enabled=request.app.state.memory_editorial_enabled))


@router.get('/memory-community/v1/jobs/{job_id}')
async def job(job_id: str, request: Request):
    runtime, token, query = await scope(request)
    return json_response(await run_in_threadpool(call, runtime, MemoryJobs, 'get', token,
        query['library'], _uuid(job_id), editorial_enabled=request.app.state.memory_editorial_enabled))


@router.delete('/memory-community/v1/jobs/{job_id}')
async def cancel_job(job_id: str, request: Request):
    runtime, token, query = await scope(request)
    return json_response(await run_in_threadpool(call, runtime, MemoryJobs, 'get', token,
        query['library'], _uuid(job_id), True))

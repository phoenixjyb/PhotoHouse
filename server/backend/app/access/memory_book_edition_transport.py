"""HTTP transport for explicitly reviewed memoir editions.

This router delegates authorization and current-source validation to the
edition service. The feature flag is a transport gate only; proposals never
invoke a model and therefore do not depend on the generation flag.
"""
import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import Response, JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _integer
from .memory_books import MemoryBooks
from .memory_book_editions import MemoryBookEditions
from .memory_book_edition_sources import MemoryBookEditionSources
from .memory_transport import json_response, scope
from .service import AccessService
from .stories import _uuid
from .transport import TransportError, _single

MAX_REQUEST_BYTES = 128 * 1024

router = APIRouter(route_class=LibraryRoute)


def call_edition(runtime, action, token, library, book_id, *args,
                 editorial_enabled=False):
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        store = MemoryBookEditions(access, enabled=True,
                                   editorial_enabled=editorial_enabled)
        return getattr(store, action)(token, library, book_id, *args)


def call_authorize_write(runtime, token, library, book_id, *, editorial_enabled=False):
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        store = MemoryBookEditions(access, enabled=True,
                                   editorial_enabled=editorial_enabled)
        with access._transaction():
            store._book(token, library, book_id, write=True)


def call_capabilities(runtime, token, library, book_id, *, enabled,
                      editorial_enabled=False):
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        if enabled:
            store = MemoryBookEditions(access, enabled=True,
                                       editorial_enabled=editorial_enabled)
            with access._transaction():
                member, row, _children = store._book(token, library, book_id)
                can_save = MemoryBooks._can_edit(member, row)
        else:
            # Capabilities remain readable while editions are switched off;
            # the ordinary book read still checks every child story and asset.
            MemoryBooks(access).get(token, library, book_id)
            can_save = False
        return {'version': 1, 'enabled': enabled, 'can_save': bool(can_save)}


async def edition_scope(request, *, allowed=None, write_book_id=None):
    runtime, token, query = await scope(request, allowed=allowed or {'library'})
    if not request.app.state.memory_editions_enabled:
        raise TransportError(503, 'Reviewed memoir editions unavailable')
    if write_book_id is not None:
        book_id = _uuid(write_book_id)
        await run_in_threadpool(call_authorize_write, runtime, token, query['library'],
            book_id, editorial_enabled=request.app.state.memory_editorial_enabled)
    return runtime, token, query


def call_edition_source(runtime, action, token, library, book_id, edition_id, *args,
                        editorial_enabled=False, originals_enabled=False):
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        editions = MemoryBookEditions(access, enabled=True,
                                      editorial_enabled=editorial_enabled)
        sources = MemoryBookEditionSources(editions, originals_enabled=originals_enabled)
        return getattr(sources, action)(token, library, book_id, edition_id, *args)


async def source_scope(request, *, allowed=None):
    runtime, token, query = await scope(request, allowed=allowed or {'library'})
    if not request.app.state.memory_editions_enabled:
        raise TransportError(503, 'Reviewed memoir editions unavailable')
    return runtime, token, query


async def edition_body(request):
    if (_single(request, 'content-encoding') is not None
            or _single(request, 'content-type') != 'application/json'):
        raise TransportError(400, 'Invalid memoir edition content type')
    length = _single(request, 'content-length')
    if length is not None:
        if not length.isascii() or not length.isdecimal():
            raise TransportError(400, 'Invalid memoir edition content length')
        if len(length) > len(str(MAX_REQUEST_BYTES)):
            raise TransportError(413, 'Memoir edition request too large')
        if str(int(length)) != length:
            raise TransportError(400, 'Invalid memoir edition content length')
        if int(length) > MAX_REQUEST_BYTES:
            raise TransportError(413, 'Memoir edition request too large')
    raw = bytearray()
    try:
        async with asyncio.timeout(10):
            async for part in request.stream():
                if len(raw) + len(part) > MAX_REQUEST_BYTES:
                    raise TransportError(413, 'Memoir edition request too large')
                raw.extend(part)
    except TimeoutError:
        raise TransportError(408, 'Memoir edition request timed out') from None
    if length is not None and len(raw) != int(length):
        raise TransportError(400, 'Incomplete memoir edition request')
    return bytes(raw)


@router.get('/memory-community/v1/books/{book_id}/edition-capabilities')
async def edition_capabilities(book_id: str, request: Request):
    runtime, token, query = await scope(request, allowed={'library'})
    enabled = request.app.state.memory_editions_enabled
    result = await run_in_threadpool(call_capabilities, runtime, token,
        query['library'], _uuid(book_id), enabled=enabled,
        editorial_enabled=request.app.state.memory_editorial_enabled)
    return json_response(result)


@router.get('/memory-community/v1/books/{book_id}/editions/proposals/{job_id}')
async def edition_proposal(book_id: str, job_id: str, request: Request):
    runtime, token, query = await edition_scope(request)
    result = await run_in_threadpool(call_edition, runtime, 'proposal', token,
        query['library'], _uuid(book_id), _uuid(job_id),
        editorial_enabled=request.app.state.memory_editorial_enabled)
    return json_response(result)


@router.post('/memory-community/v1/books/{book_id}/editions')
async def save_edition(book_id: str, request: Request):
    runtime, token, query = await edition_scope(request, write_book_id=book_id)
    raw = await edition_body(request)
    result = await run_in_threadpool(call_edition, runtime, 'save', token,
        query['library'], _uuid(book_id), raw,
        editorial_enabled=request.app.state.memory_editorial_enabled)
    return json_response(result)


@router.get('/memory-community/v1/books/{book_id}/editions')
async def list_editions(book_id: str, request: Request):
    runtime, token, query = await edition_scope(request, allowed={'library', 'page'})
    page = _integer(query.get('page', '1'), 100000)
    result = await run_in_threadpool(call_edition, runtime, 'list', token,
        query['library'], _uuid(book_id), page,
        editorial_enabled=request.app.state.memory_editorial_enabled)
    return json_response(result)


@router.get('/memory-community/v1/books/{book_id}/editions/{edition_id}')
async def get_edition(book_id: str, edition_id: str, request: Request):
    runtime, token, query = await edition_scope(request)
    result = await run_in_threadpool(call_edition, runtime, 'get', token,
        query['library'], _uuid(book_id), _uuid(edition_id),
        editorial_enabled=request.app.state.memory_editorial_enabled)
    return json_response(result)


@router.get('/memory-community/v1/books/{book_id}/editions/{edition_id}/sources')
async def list_edition_sources(book_id: str, edition_id: str, request: Request):
    runtime, token, query = await source_scope(request, allowed={'library', 'page'})
    page = _integer(query.get('page', '1'), 100000)
    result = await run_in_threadpool(call_edition_source, runtime, 'list', token,
        query['library'], _uuid(book_id), _uuid(edition_id), page,
        editorial_enabled=request.app.state.memory_editorial_enabled,
        originals_enabled=request.app.state.memory_originals_enabled)
    return json_response(result)


@router.get('/memory-community/v1/books/{book_id}/editions/{edition_id}/sources/{source_id}')
async def get_edition_source(book_id: str, edition_id: str, source_id: str, request: Request):
    runtime, token, query = await source_scope(request)
    result = await run_in_threadpool(call_edition_source, runtime, 'detail', token,
        query['library'], _uuid(book_id), _uuid(edition_id), source_id,
        editorial_enabled=request.app.state.memory_editorial_enabled,
        originals_enabled=request.app.state.memory_originals_enabled)
    return json_response(result)


@router.get('/memory-community/v1/books/{book_id}/editions/{edition_id}/sources/{source_id}/audio')
async def get_edition_source_audio(book_id: str, edition_id: str, source_id: str, request: Request):
    runtime, token, query = await source_scope(request)
    result = await run_in_threadpool(call_edition_source, runtime, 'audio', token,
        query['library'], _uuid(book_id), _uuid(edition_id), source_id,
        editorial_enabled=request.app.state.memory_editorial_enabled,
        originals_enabled=request.app.state.memory_originals_enabled)
    if result['state'] != 'current':
        return JSONResponse({'version': 1, 'book_id': _uuid(book_id),
            'edition_id': _uuid(edition_id), 'state': result['state']}, status_code=409,
            headers={'Cache-Control': 'no-store'})
    return Response(result['audio'], media_type='audio/wav',
                    headers={'Cache-Control': 'no-store'})

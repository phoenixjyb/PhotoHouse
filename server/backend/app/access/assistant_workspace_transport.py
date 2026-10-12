"""Protected HTTP surface for private assistant workspace history/preferences.

This adapter never accepts assistant replies or cards from clients. It serves
only owned stored text; persisted source bindings are deliberately reduced to
non-actionable type/count placeholders until a future turn path can revalidate
them against current source authorization.
"""
import asyncio
import json
import re
import uuid
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from .assistant_workspace_store import (AssistantWorkspaceStore,
    WorkspaceStoreConflict, WorkspaceStoreMissing, WorkspaceStoreUnavailable)
from .service import AccessDenied, AccessService
from .transport import (AccessRuntime, PRIVACY_HEADERS, TransportError, _runtime,
                        _single, credentials_from_request)

MAX_BODY = 2048
MAX_QUERY = 1024
MAX_REVISION = (1 << 63) - 2


class WorkspaceInvalid(ValueError):
    pass


def _failure(status, code, detail):
    return JSONResponse({'error': code, 'detail': detail}, status_code=status,
                        headers=PRIVACY_HEADERS)


class WorkspaceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                _runtime(request, allow_query=request.method == 'GET')
                response = await handler(request)
            except TransportError as exc:
                code = ('access_denied' if exc.status in (401, 403) else
                        'request_too_large' if exc.status == 413 else 'invalid_request')
                response = _failure(exc.status, code, exc.message)
            except AccessDenied:
                response = _failure(401, 'access_denied', 'Access denied')
            except WorkspaceInvalid:
                response = _failure(400, 'invalid_request', 'Invalid workspace request')
            except WorkspaceStoreConflict:
                response = _failure(409, 'revision_conflict', 'Refresh workspace state')
            except WorkspaceStoreMissing:
                response = _failure(404, 'workspace_unavailable', 'Workspace item unavailable')
            except WorkspaceStoreUnavailable:
                response = _failure(503, 'workspace_unavailable', 'Workspace unavailable')
            except asyncio.CancelledError:
                raise
            except Exception:
                response = _failure(503, 'workspace_unavailable', 'Workspace unavailable')
            for key, value in PRIVACY_HEADERS.items():
                response.headers[key] = value
            return response

        return guarded


router = APIRouter(route_class=WorkspaceRoute)


def _workspace(request):
    store = getattr(request.app.state, 'assistant_workspace_store', None)
    if (not getattr(request.app.state, 'assistant_enabled', False) or
            not isinstance(store, AssistantWorkspaceStore) or
            not getattr(request.app.state, 'assistant_workspace_healthy', False)):
        raise WorkspaceStoreUnavailable()
    return store


def _query(request, allowed, required):
    raw = request.scope.get('query_string', b'')
    if len(raw) > MAX_QUERY:
        raise WorkspaceInvalid()
    try:
        text = raw.decode('ascii')
        if re.search(r'%(?![0-9a-fA-F]{2})', text):
            raise ValueError()
        pairs = parse_qsl(text, keep_blank_values=True, strict_parsing=True,
                          errors='strict', max_num_fields=len(allowed))
        values = dict(pairs)
        if (len(values) != len(pairs) or set(values) - set(allowed) or
                not set(required) <= set(values)):
            raise ValueError()
        return values
    except (UnicodeError, ValueError):
        raise WorkspaceInvalid() from None


def _library(value):
    if type(value) is not str:
        raise WorkspaceInvalid()
    try:
        valid_length = 1 <= len(value.encode('utf-8')) <= 128
    except UnicodeError:
        raise WorkspaceInvalid() from None
    if not valid_length or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise WorkspaceInvalid()
    return value


def _revision(value):
    if type(value) is not int or not 0 <= value <= MAX_REVISION:
        raise WorkspaceInvalid()
    return value


def _thread_id(value):
    try:
        parsed = uuid.UUID(value)
        if parsed.version != 4 or str(parsed) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise WorkspaceInvalid() from None


async def _body(request, fields, *, required=None):
    if request.scope.get('query_string') or _single(request, 'content-encoding') is not None:
        raise WorkspaceInvalid()
    if (_single(request, 'content-type') or '').split(';')[0].strip().lower() != 'application/json':
        raise WorkspaceInvalid()
    length = _single(request, 'content-length')
    if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > MAX_BODY):
        raise TransportError(413, 'Request too large')
    raw = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_BODY:
                    raise TransportError(413, 'Request too large')
                raw.extend(chunk)
    except TimeoutError:
        raise TransportError(408, 'Request timed out') from None
    if length is not None and len(raw) != int(length):
        raise WorkspaceInvalid()

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError()
            value[key] = item
        return value

    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                           parse_constant=lambda _constant: (_ for _ in ()).throw(ValueError()))
        if (type(value) is not dict or set(value) - set(fields) or
                not set(required if required is not None else fields) <= set(value)):
            raise ValueError()
        return value
    except (UnicodeError, ValueError, RecursionError):
        raise WorkspaceInvalid() from None


async def _principal(request, library):
    access = _runtime(request, allow_query=request.method == 'GET')
    token, _mode = credentials_from_request(request, allow_query=request.method == 'GET')
    header_library = _single(request, 'x-photohouse-library-id')
    if header_library is not None and header_library != library:
        raise WorkspaceInvalid()
    return await run_in_threadpool(_authorize, access, token, library)


def _authorize(access, token, library):
    with access.connection_factory() as connection:
        return AccessService(connection, clock=access.clock).library_principal(token, library)


def _store_call(store, method, *args, **kwargs):
    return getattr(store, method)(*args, **kwargs)


async def _call(store, method, *args, **kwargs):
    return await run_in_threadpool(_store_call, store, method, *args, **kwargs)


def _safe_thread(row):
    return {key: row[key] for key in
            ('thread_id', 'library_id', 'created_at', 'updated_at', 'expires_at',
             'revision', 'exchange_count') if key in row}


def _safe_exchange(row):
    cards = row.get('cards', [])
    by_type = {}
    for card in cards:
        kind = card.get('type') if type(card) is dict else None
        if kind not in {'media', 'album', 'story', 'memoir', 'timeline'}:
            kind = 'unavailable'
        by_type[kind] = by_type.get(kind, 0) + 1
    return {'exchange_id': row['exchange_id'], 'revision': row['revision'],
            'created_at': row['created_at'], 'expires_at': row['expires_at'],
            'input_text': row['input_text'], 'reply': row['reply'],
            'cards': [{'type': kind, 'count': count, 'actionable': False}
                      for kind, count in sorted(by_type.items())],
            'receipt_count': len(row.get('receipts', []))}


@router.get('/assistant/workspace/v1/capabilities')
async def capabilities(request: Request):
    query = _query(request, {'library_id'}, {'library_id'})
    library = _library(query['library_id'])
    account = await _principal(request, library)
    store = getattr(request.app.state, 'assistant_workspace_store', None)
    healthy = (getattr(request.app.state, 'assistant_enabled', False) and
               isinstance(store, AssistantWorkspaceStore) and
               getattr(request.app.state, 'assistant_workspace_healthy', False))
    if healthy:
        try:
            await run_in_threadpool(store.get_preferences, account)
        except WorkspaceStoreUnavailable:
            healthy = False
        except Exception:
            healthy = False
    return JSONResponse({'version': 1, 'available': bool(healthy),
                         'threads': bool(healthy), 'preferences': bool(healthy),
                         'preferences_applied': False,
                         'server_owned_turns': False}, headers=PRIVACY_HEADERS)


@router.get('/assistant/workspace/v1/threads')
async def list_threads(request: Request):
    query = _query(request, {'library_id', 'limit'}, {'library_id'})
    library = _library(query['library_id'])
    account = await _principal(request, library)
    limit = 50
    if 'limit' in query:
        if not query['limit'].isascii() or not query['limit'].isdecimal() or not 1 <= int(query['limit']) <= 100:
            raise WorkspaceInvalid()
        limit = int(query['limit'])
    store = _workspace(request)
    items = await _call(store, 'list_threads', account, library, limit=limit)
    return JSONResponse({'version': 1, 'threads': [_safe_thread(row) for row in items]},
                        headers=PRIVACY_HEADERS)


@router.post('/assistant/workspace/v1/threads')
async def create_thread(request: Request):
    body = await _body(request, {'library_id'})
    library = _library(body['library_id'])
    account = await _principal(request, library)
    result = await _call(_workspace(request), 'create_thread', account, library)
    return JSONResponse({'version': 1, 'thread': _safe_thread(result)}, status_code=201,
                        headers=PRIVACY_HEADERS)


@router.get('/assistant/workspace/v1/threads/{thread_id}')
async def read_thread(request: Request, thread_id: str):
    query = _query(request, {'library_id'}, {'library_id'})
    library = _library(query['library_id'])
    account = await _principal(request, library)
    result = await _call(_workspace(request), 'get_thread', account, library, _thread_id(thread_id))
    return JSONResponse({'version': 1, 'thread': _safe_thread(result['thread']),
                         'exchanges': [_safe_exchange(row) for row in result['exchanges']]},
                        headers=PRIVACY_HEADERS)


@router.delete('/assistant/workspace/v1/threads/{thread_id}')
async def delete_thread(request: Request, thread_id: str):
    body = await _body(request, {'library_id', 'expected_revision'})
    library = _library(body['library_id'])
    revision = _revision(body['expected_revision'])
    account = await _principal(request, library)
    result = await _call(_workspace(request), 'delete_thread', account, library,
                         _thread_id(thread_id), revision)
    return JSONResponse(result, headers=PRIVACY_HEADERS)


@router.get('/assistant/workspace/v1/preferences')
async def read_preferences(request: Request):
    query = _query(request, {'library_id'}, {'library_id'})
    account = await _principal(request, _library(query['library_id']))
    value = await _call(_workspace(request), 'get_preferences', account)
    return JSONResponse({'version': 1, **value}, headers=PRIVACY_HEADERS)


@router.put('/assistant/workspace/v1/preferences')
async def update_preferences(request: Request):
    fields = {'library_id', 'expected_revision', 'locale', 'reply_length', 'voice_pace'}
    body = await _body(request, fields, required={'library_id', 'expected_revision'})
    library = _library(body['library_id'])
    revision = body['expected_revision']
    revision = _revision(revision)
    updates = {key: body[key] for key in ('locale', 'reply_length', 'voice_pace') if key in body}
    if not updates:
        raise WorkspaceInvalid()
    allowed = {'locale': {None, 'zh', 'en'},
               'reply_length': {None, 'brief', 'standard'},
               'voice_pace': {None, 'slow', 'normal'}}
    if any(type(value) not in (str, type(None)) or value not in allowed[key]
           for key, value in updates.items()):
        raise WorkspaceInvalid()
    account = await _principal(request, library)
    value = await _call(_workspace(request), 'update_preferences', account, revision, updates)
    return JSONResponse({'version': 1, **value}, headers=PRIVACY_HEADERS)


@router.post('/assistant/workspace/v1/preferences/reset')
async def reset_preferences(request: Request):
    body = await _body(request, {'library_id', 'expected_revision'})
    library = _library(body['library_id'])
    revision = body['expected_revision']
    revision = _revision(revision)
    account = await _principal(request, library)
    value = await _call(_workspace(request), 'reset_preferences', account, revision)
    return JSONResponse({'version': 1, **value}, headers=PRIVACY_HEADERS)

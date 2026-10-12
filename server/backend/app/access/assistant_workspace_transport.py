"""Protected, per-account assistant history and server-owned read-only turns.

The client supplies words and a revision, never trusted context or replies.
Readback revalidates current source authorization and never replays effects.
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

from . import assistant as assistant_engine
from . import discovery as discovery_engine
from .assistant_journal import Journal, JournalUnavailable, JournalConflict, JournalMissing

from .assistant_workspace_store import (AssistantWorkspaceStore,
    WorkspaceStoreConflict, WorkspaceStoreMissing, WorkspaceStoreUnavailable)
from .service import AccessDenied, AccessService
from .transport import (AccessRuntime, PRIVACY_HEADERS, TransportError, _runtime,
                        _single, credentials_from_request)

MAX_BODY = 2048
MAX_QUERY = 1024
MAX_REVISION = (1 << 63) - 2
MAX_RESPONSE_BYTES = 240 * 1024


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
            except (assistant_engine.AssistantChanged, discovery_engine.DiscoveryChanged):
                response = _failure(409, 'context_changed', 'Refresh assistant results')
            except (assistant_engine.AssistantInvalid, discovery_engine.DiscoveryInvalid):
                response = _failure(400, 'invalid_request', 'Invalid assistant request')
            except discovery_engine.DiscoveryBusy:
                response = _failure(429, 'assistant_busy', 'Assistant busy')
                response.headers['Retry-After'] = '2'
            except JournalUnavailable:
                response = _failure(503, 'tracking_unavailable', 'Request tracking unavailable')
            except JournalConflict:
                response = _failure(409, 'request_conflict', 'Check the existing request')
            except JournalMissing:
                response = _failure(404, 'receipt_unavailable', 'Receipt unavailable')
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


async def _body(request, fields, *, required=None, maximum=MAX_BODY):
    if request.scope.get('query_string') or _single(request, 'content-encoding') is not None:
        raise WorkspaceInvalid()
    if (_single(request, 'content-type') or '').split(';')[0].strip().lower() != 'application/json':
        raise WorkspaceInvalid()
    length = _single(request, 'content-length')
    if length is not None and (not length.isascii() or not length.isdecimal() or int(length) > maximum):
        raise TransportError(413, 'Request too large')
    raw = bytearray()
    try:
        async with asyncio.timeout(3):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > maximum:
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
    fields = ('thread_id', 'library_id', 'created_at', 'updated_at', 'expires_at',
              'revision', 'exchange_count', 'label')
    return {key: row[key] for key in fields if key in row}


def _safe_exchange(row):
    cards = row.get('cards', [])
    by_type = {}
    for card in cards:
        kind = card.get('type') if type(card) is dict else None
        if kind not in {'media', 'album', 'story', 'memoir', 'timeline'}:
            kind = 'unavailable'
        by_type[kind] = by_type.get(kind, 0) + 1
    return {'exchange_id': row['exchange_id'], 'revision': row['revision'],
            'request_id': row['request_id'],
            'created_at': row['created_at'], 'expires_at': row['expires_at'],
            'input_text': row['input_text'], 'reply': row['reply'],
            'cards': [{'type': kind, 'count': count, 'actionable': False}
                      for kind, count in sorted(by_type.items())],
            'receipt_count': len(row.get('receipts', []))}


def _json_size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                          allow_nan=False).encode('utf-8'))


def _bounded_exchange_rows(rows, response, *, has_older):
    """Drop oldest complete projections until the serialized response fits."""
    selected = list(rows)
    dropped = False
    while selected:
        more = bool(has_older or dropped)
        if _json_size(response(selected, more)) <= MAX_RESPONSE_BYTES:
            return selected, more
        selected.pop(0)
        dropped = True
    if _json_size(response([], False)) > MAX_RESPONSE_BYTES:
        raise WorkspaceStoreUnavailable()
    # An empty response must never claim another page exists.
    return [], False


def _canonical_revision(value, *, positive=False):
    if (type(value) is not str or re.fullmatch(r'(?:0|[1-9][0-9]*)', value) is None):
        raise WorkspaceInvalid()
    parsed = int(value)
    if parsed > MAX_REVISION or positive and parsed == 0:
        raise WorkspaceInvalid()
    return parsed


def _create_owned_thread(store, account, library, selected):
    if selected is not None:
        try:
            return store.get_thread(account, library, selected)['thread'], False
        except WorkspaceStoreMissing:
            pass
    try:
        return store.create_thread(account, library, selected), True
    except WorkspaceStoreConflict:
        # Another identical request may have committed while its response was
        # lost. A foreign thread still cannot be adopted or read.
        if selected is None:
            raise
        return store.get_thread(account, library, selected)['thread'], False


def _turn_text(value):
    if type(value) is not str or not value.strip():
        raise WorkspaceInvalid()
    try:
        if len(value.encode('utf-8')) > 1024:
            raise WorkspaceInvalid()
    except UnicodeError:
        raise WorkspaceInvalid() from None
    if any(ord(char) < 32 and char not in '\n\t' or ord(char) == 127 for char in value):
        raise WorkspaceInvalid()
    return value


def _turn_result(engine, token, library, summary, *, recovered):
    result = dict(summary)
    context = summary['context']
    items = []
    if context is not None:
        context = assistant_engine._context(context, library)
        found = assistant_engine._search(engine, token, library, context['binding'],
                                         context['filters'], context['fingerprint'])
        if ([item['id'] for item in found['items']] != context['visible_ids'] or
                found['total'] != context['total']):
            raise assistant_engine.AssistantChanged()
        items = found['items']
    result['items'] = items
    if recovered:
        result['effect'] = None
        if result['kind'] == 'open':
            result['kind'] = 'results'
            result['reply'] = ('结果已恢复，请选择要打开的照片或视频。'
                               if assistant_engine._language(result['reply']) == 'zh' else
                               'Results restored. Choose the photo or video to open.')
    return result


async def _turn_envelope(request, account, library, row, *, recovered):
    result = None
    revision = row['revision']
    if row['status'] == 'completed':
        token, _mode = credentials_from_request(request, allow_query=request.method == 'GET')
        _access, engine = assistant_engine._engine(request)
        if engine is None:
            raise WorkspaceStoreUnavailable()
        result = await run_in_threadpool(_turn_result, engine, token, library,
                                        row['result_summary'], recovered=recovered)
    else:
        owned = await _call(_workspace(request), 'get_thread', account, library, row['thread_id'])
        revision = owned['thread']['revision']
    if await _principal(request, library) != account:
        raise AccessDenied()
    return JSONResponse({'version': 1, 'thread_id': row['thread_id'],
        'request_id': row['request_id'], 'status': row['status'],
        'revision': revision, 'recovered': recovered,
        'error': row['error_code'], 'result': result}, headers=PRIVACY_HEADERS)


def _journal(request):
    journal = getattr(request.app.state, 'assistant_journal', None)
    if journal is not None and (not isinstance(journal, Journal) or
            not getattr(request.app.state, 'assistant_journal_healthy', False)):
        raise JournalUnavailable()
    return journal


def _error_code(exc):
    if isinstance(exc, (assistant_engine.AssistantChanged, discovery_engine.DiscoveryChanged)):
        return 'context_changed'
    if isinstance(exc, AccessDenied):
        return 'access_denied'
    if isinstance(exc, (WorkspaceInvalid, assistant_engine.AssistantInvalid,
                        discovery_engine.DiscoveryInvalid)):
        return 'invalid_request'
    if isinstance(exc, asyncio.CancelledError):
        return 'request_cancelled'
    if isinstance(exc, WorkspaceStoreUnavailable):
        return 'storage_unavailable'
    return 'assistant_unavailable'


@router.post('/assistant/workspace/v1/threads/{thread_id}/turns')
async def create_turn(request: Request, thread_id: str):
    body = await _body(request, {'library_id', 'request_id', 'expected_revision', 'text'},
                       maximum=20 * 1024)
    library, selected = _library(body['library_id']), _thread_id(thread_id)
    ident, revision = _thread_id(body['request_id']), _revision(body['expected_revision'])
    words = _turn_text(body['text'])
    account = await _principal(request, library)
    token, _mode = credentials_from_request(request)
    access, engine = assistant_engine._engine(request)
    if engine is None:
        raise WorkspaceStoreUnavailable()
    header_id = _single(request, 'x-photohouse-request-id')
    if header_id is not None and header_id != ident:
        raise WorkspaceInvalid()
    parent = _single(request, 'x-photohouse-parent-request-id')
    if parent is not None:
        _thread_id(parent)
    store = _workspace(request)
    row = await _call(store, 'begin_turn', account, library, selected, ident, revision, words)
    if row['replayed']:
        return await _turn_envelope(request, account, library, row, recovered=True)
    lease = row['lease_id']
    committed = False
    journal_started = False
    journal = None
    try:
        journal = _journal(request)
        if journal is not None:
            await run_in_threadpool(journal.begin, account, library, 'turn', ident, parent, words)
            journal_started = True
            await run_in_threadpool(journal.stage, ident, 'action_started')
        preferences = await _call(store, 'get_preferences', account)
        result = await run_in_threadpool(assistant_engine._turn, engine, token, library,
            words, row['context'], access.clock, language=preferences['locale'])
        if await _principal(request, library) != account:
            raise AccessDenied()
        summary = {key: value for key, value in result.items() if key != 'items'}
        context = result['context']
        cards = ([] if context is None else [dict(type='media', id=item['id'],
                 revision=context['binding'], fingerprint=context['fingerprint'])
                 for item in result['items']])
        row = await _call(store, 'complete_turn', account, library, selected, ident,
                          lease, summary, cards, [ident] if journal_started else [])
        committed = row['status'] == 'completed'
        if journal_started:
            await run_in_threadpool(journal.finish, ident,
                'succeeded' if committed else 'failed', http_status=200 if committed else 409,
                error=None if committed else 'turn_interrupted',
                kind=result['kind'] if committed else None,
                total=result['total'] if committed else None)
        response = await _turn_envelope(request, account, library, row, recovered=False)
        response.headers['X-PhotoHouse-Request-Id'] = ident
        response.headers['X-PhotoHouse-Tracking'] = 'enabled' if journal is not None else 'disabled'
        if journal_started:
            response.headers['X-PhotoHouse-Receipt-Status'] = 'succeeded' if committed else 'failed'
        return response
    except BaseException as exc:
        if not committed:
            try:
                await asyncio.shield(_call(store, 'fail_turn', account, library, selected,
                                           ident, lease, _error_code(exc)))
            except Exception:
                # A hard shutdown leaves a bounded lease, not permission to
                # regenerate the same request. Readback reconciles its expiry.
                pass
        if journal_started and not committed:
            try:
                await asyncio.shield(run_in_threadpool(journal.finish, ident, 'failed',
                    http_status=499 if isinstance(exc, asyncio.CancelledError) else 503,
                    error=_error_code(exc)))
            except Exception:
                pass
        raise


@router.get('/assistant/workspace/v1/threads/{thread_id}/requests/{request_id}')
async def read_turn(request: Request, thread_id: str, request_id: str):
    query = _query(request, {'library_id'}, {'library_id'})
    library = _library(query['library_id'])
    account = await _principal(request, library)
    row = await _call(_workspace(request), 'get_turn', account, library,
                      _thread_id(thread_id), _thread_id(request_id))
    return await _turn_envelope(request, account, library, row, recovered=True)


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
    _access, engine = assistant_engine._engine(request)
    turns = bool(healthy and engine is not None)
    return JSONResponse({'version': 1, 'available': bool(healthy),
                         'threads': bool(healthy), 'preferences': bool(healthy),
                         'thread_labels': bool(healthy), 'history_paging': bool(healthy),
                         'preferences_applied': turns,
                         'applied_preferences': ['locale'] if turns else [],
                         'server_owned_turns': turns}, headers=PRIVACY_HEADERS)


@router.get('/assistant/workspace/v1/threads')
async def list_threads(request: Request):
    query = _query(request, {'library_id', 'limit', 'include_labels'}, {'library_id'})
    library = _library(query['library_id'])
    account = await _principal(request, library)
    limit = 50
    if 'limit' in query:
        if not query['limit'].isascii() or not query['limit'].isdecimal() or not 1 <= int(query['limit']) <= 100:
            raise WorkspaceInvalid()
        limit = int(query['limit'])
    include_labels = False
    if 'include_labels' in query:
        if query['include_labels'] not in ('true', 'false'):
            raise WorkspaceInvalid()
        include_labels = query['include_labels'] == 'true'
    store = _workspace(request)
    items = await _call(store, 'list_threads', account, library, limit=limit,
                        include_labels=include_labels)
    if await _principal(request, library) != account:
        raise AccessDenied()
    return JSONResponse({'version': 1, 'threads': [_safe_thread(row) for row in items]},
                        headers=PRIVACY_HEADERS)


@router.post('/assistant/workspace/v1/threads')
async def create_thread(request: Request):
    body = await _body(request, {'library_id', 'thread_id'}, required={'library_id'})
    library = _library(body['library_id'])
    account = await _principal(request, library)
    store = _workspace(request)
    selected = _thread_id(body['thread_id']) if 'thread_id' in body else None
    result, created = await run_in_threadpool(_create_owned_thread, store, account, library, selected)
    return JSONResponse({'version': 1, 'thread': _safe_thread(result)}, status_code=201 if created else 200,
                        headers=PRIVACY_HEADERS)


@router.get('/assistant/workspace/v1/threads/{thread_id}')
async def read_thread(request: Request, thread_id: str):
    query = _query(request, {'library_id'}, {'library_id'})
    library = _library(query['library_id'])
    account = await _principal(request, library)
    store = _workspace(request)
    selected = _thread_id(thread_id)
    result = await _call(store, 'get_thread', account, library, selected)
    latest = result.get('latest_request_id')
    all_rows = result['exchanges']

    def response(rows, has_older):
        return {'version': 1, 'thread': _safe_thread(result['thread']),
                'exchanges': [_safe_exchange(row) for row in rows],
                'has_older_exchanges': has_older,
                'latest_request_id': latest}

    selected_rows = all_rows[-20:]
    bounded, has_older = _bounded_exchange_rows(
        selected_rows, response, has_older=len(all_rows) > len(selected_rows))
    return JSONResponse(response(bounded, has_older), headers=PRIVACY_HEADERS)


@router.get('/assistant/workspace/v1/threads/{thread_id}/history')
async def read_thread_history(request: Request, thread_id: str):
    query = _query(request, {'library_id', 'snapshot_revision', 'before_revision'},
                   {'library_id', 'snapshot_revision', 'before_revision'})
    library = _library(query['library_id'])
    snapshot = _canonical_revision(query['snapshot_revision'])
    before = _canonical_revision(query['before_revision'], positive=True)
    if before > snapshot:
        raise WorkspaceInvalid()
    account = await _principal(request, library)
    selected = _thread_id(thread_id)
    result = await _call(_workspace(request), 'get_thread_history_page', account,
                         library, selected, snapshot, before)
    rows = result['exchanges']

    def response(page, has_older):
        revisions = [row['revision'] for row in page]
        next_cursor = revisions[0] if has_older and revisions else None
        return {'version': 1, 'thread_id': selected,
                'snapshot_revision': snapshot, 'before_revision': before,
                'exchanges': [_safe_exchange(row) for row in page],
                'has_older_exchanges': bool(has_older and page),
                'next_before_revision': next_cursor}

    bounded, has_older = _bounded_exchange_rows(
        rows, response, has_older=result['has_older_exchanges'])
    if await _principal(request, library) != account:
        raise AccessDenied()
    return JSONResponse(response(bounded, has_older), headers=PRIVACY_HEADERS)


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

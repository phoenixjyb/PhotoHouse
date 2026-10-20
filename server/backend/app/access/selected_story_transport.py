"""Default-off, protected selected-source prepare/cancel HTTP boundary.

No model discovery, save authority, queue, polling or native stop receipt.
The application-owned operation service supplies all source/result metadata.
"""
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .library import LibraryRoute, _query
from .memory_narrative import _canonical_uuid
from .selected_story_operations import DraftOperationError, DraftOperations
from .selected_story_snapshot import MAX_REQUEST_BYTES
from .transport import TransportError, _single, credentials_from_request


router = APIRouter(route_class=LibraryRoute)
CANCEL_BYTES = 512
# Public v1 codes are fixed and deliberately exclude provider/source diagnostics.
ERRORS = {
    'invalid_request': (400, 'draft_invalid_request', 'Invalid draft request'),
    'denied': (401, 'draft_access_denied', 'Access denied'),
    'conflict': (409, 'draft_conflict', 'Story references or request changed'),
    'scope_changed': (409, 'draft_scope_changed', 'Draft scope changed'),
    'cancelled': (409, 'draft_cancelled', 'Draft cancelled'),
    'busy': (429, 'draft_busy', 'Draft preparation busy'),
    'registry_full': (429, 'draft_capacity', 'Draft capacity reached'),
    'timed_out': (504, 'draft_timed_out', 'Draft preparation timed out'),
    'unavailable': (503, 'draft_unavailable', 'Draft preparation unavailable'),
    'closed': (503, 'draft_unavailable', 'Draft preparation unavailable'),
}


def _failure(reason):
    status, code, detail = ERRORS.get(reason, ERRORS['unavailable'])
    return JSONResponse({'detail': detail, 'code': code}, status_code=status,
                        headers={'Retry-After': '2'} if reason == 'busy' else None)


def _scope(request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    owner = getattr(request.app.state, 'selected_story_operations', None)
    if (getattr(request.app.state, 'selected_story_drafts_enabled', False) is not True or
            type(owner) is not DraftOperations):
        raise DraftOperationError('unavailable')
    return owner, token, query['library']


async def _json(request, limit):
    if _single(request, 'content-encoding') is not None:
        raise TransportError(400, 'Invalid request')
    if (_single(request, 'content-type') or '').split(';')[0].strip().lower() != 'application/json':
        raise TransportError(400, 'Invalid request')
    length = _single(request, 'content-length')
    if length is not None:
        if not length.isascii() or not length.isdecimal():
            raise TransportError(400, 'Invalid request')
        if len(length) > 10 or int(length) > limit:
            raise TransportError(413, 'Request too large')
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > limit:
            raise TransportError(413, 'Request too large')
        raw.extend(chunk)
    if length is not None and int(length) != len(raw):
        raise TransportError(400, 'Invalid request')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate_field')
            value[key] = item
        return value
    def constant(_value):
        raise ValueError('invalid_json_constant')
    try:
        value = json.loads(raw.decode('utf-8', errors='strict'),
                           object_pairs_hook=unique, parse_constant=constant)
        if type(value) is not dict:
            raise ValueError('invalid_json_object')
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise TransportError(400, 'Invalid request') from None


@router.post('/story-workspace/drafts/prepare')
async def prepare(request: Request):
    try:
        owner, token, library = _scope(request)
        body = await _json(request, MAX_REQUEST_BYTES)
        result = await owner.prepare(token, library, body)
        return JSONResponse(result)
    except DraftOperationError as error:
        return _failure(error.reason)


@router.post('/story-workspace/drafts/cancel')
async def cancel(request: Request):
    try:
        owner, token, library = _scope(request)
        body = await _json(request, CANCEL_BYTES)
        try:
            if set(body) != {'version', 'request_id'} or type(body['version']) is not int or body['version'] != 1:
                raise ValueError('invalid_cancel')
            _canonical_uuid(body['request_id'], 'request id')
        except (ValueError, TypeError):
            raise DraftOperationError('invalid_request') from None
        matched = await owner.cancel(token, library, body['request_id'])
        # True means the registered output is fenced, not native stop proof.
        # False creates no tombstone and cannot fence a future first prepare.
        return JSONResponse({'version': 1, 'request_id': body['request_id'], 'matched': matched})
    except DraftOperationError as error:
        return _failure(error.reason)

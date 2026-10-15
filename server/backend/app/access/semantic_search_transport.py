"""Explicitly mounted, authenticated semantic-search pilot; no default route."""
import asyncio
import json
import re

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from . import discovery as d
from .discovery_transport import (BODY_SECONDS, MAX_BODY, DiscoveryRoute,
                                 bounded_structure, invoke, reject_constant, unique)
from .semantic_search import SemanticSearchRuntime
from .transport import TransportError, _runtime, _single, credentials_from_request


router = APIRouter(route_class=DiscoveryRoute)


async def _body(request):
    if request.scope.get('query_string') or _single(request, 'content-encoding') is not None:
        raise d.DiscoveryInvalid()
    content_type = (_single(request, 'content-type') or '').lower().replace(' ', '')
    if content_type not in ('application/json', 'application/json;charset=utf-8'):
        raise d.DiscoveryInvalid()
    length = _single(request, 'content-length')
    if length is not None and (not re.fullmatch(r'[0-9]{1,5}', length) or int(length) > MAX_BODY):
        raise TransportError(413, 'Request too large')
    raw = bytearray()
    try:
        async with asyncio.timeout(BODY_SECONDS):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > MAX_BODY:
                    raise TransportError(413, 'Request too large')
                raw.extend(chunk)
    except TimeoutError:
        raise TransportError(408, 'Request timed out') from None
    try:
        if length is not None and int(length) != len(raw):
            raise ValueError()
        result = json.loads(raw.decode('utf-8', errors='strict'),
                            object_pairs_hook=unique, parse_constant=reject_constant)
        bounded_structure(result)
        if (type(result) is not dict or not {'query', 'filters'} <= set(result)
                or set(result) - {'query', 'filters', 'binding', 'fingerprint', 'page', 'page_size'}):
            raise ValueError()
        # The pilot deliberately caps page size; it never truncates the
        # eligible vector cohort before ranking all of it.
        size = result.get('page_size', 20)
        if type(size) is not int or not 1 <= size <= 20:
            raise ValueError()
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise d.DiscoveryInvalid() from None


@router.post('/libraries/{library_id}/semantic-search/v1/query')
async def search(library_id: str, request: Request):
    access = _runtime(request, allow_query=False)
    token, _ = credentials_from_request(request, allow_query=False)
    engine = getattr(request.app.state, 'semantic_search_runtime', None)
    if type(engine) is not SemanticSearchRuntime or engine.access is not access:
        raise d.DiscoveryUnavailable()
    await run_in_threadpool(engine.authorize, token, library_id)
    return await invoke(request, engine, 'search', token, library_id, await _body(request))

"""Protected lookup over an explicitly approved, in-process video-moment catalog.

This is a bounded read adapter only. It does not create labels, inspect worker
frames, or expose the historical unprotected video-segment routes.
"""
from dataclasses import dataclass
import hashlib
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from ..home_catalog import digest, identity
from ..home_feed import Refused, bounded_read, unique
from .media import MediaRuntime, verified_prepared_video_provider
from .prepared_video import PreparedVideos, pin
from .service import AccessDenied, AccessService
from .transport import (AccessRoute, PRIVACY_HEADERS, TransportError,
                        _body, _runtime as access_runtime,
                        credentials_from_request)

MAX_MOMENTS = 32
MAX_QUERY_CHARS = 128
MAX_CATALOG_BYTES = 64 * 1024


@dataclass(frozen=True)
class VideoMoment:
    asset_id: int
    label: str
    start_sec: float
    end_sec: float
    source_identity: tuple[int, int, int, int]
    duration_ms: int
    playback_sha256: str

    def __post_init__(self):
        if (type(self.asset_id) is not int or not 1 <= self.asset_id <= 2**63 - 1
                or type(self.label) is not str or not self.label.strip() or len(self.label) > 160
                or any(ord(char) < 32 or 0x7f <= ord(char) < 0xa0
                       or 0xd800 <= ord(char) <= 0xdfff for char in self.label)
                or type(self.start_sec) not in (int, float)
                or type(self.end_sec) not in (int, float)
                or type(self.duration_ms) is not int or not 1 <= self.duration_ms <= 86400000
                or not 0 <= self.start_sec < self.end_sec <= self.duration_ms / 1000
                or type(self.playback_sha256) is not str
                or re.fullmatch(r'[0-9a-f]{64}', self.playback_sha256) is None
                or type(self.source_identity) is not tuple or len(self.source_identity) != 4
                or any(type(value) is not int or value < 0 for value in self.source_identity)
                or self.source_identity[2] <= 0):
            raise ValueError('Invalid video moment')


@dataclass(frozen=True)
class VideoMomentCatalog:
    """Owner-reviewed bounded labels tied to prepared source identity/duration."""
    moments: tuple[VideoMoment, ...]

    def __post_init__(self):
        if (type(self.moments) is not tuple or len(self.moments) > MAX_MOMENTS
                or any(type(item) is not VideoMoment for item in self.moments)):
            raise ValueError('Invalid video moment catalog')


def load_reviewed_catalog(path, expected_sha256, prepared: PreparedVideos) -> VideoMomentCatalog:
    """Load an explicitly pinned operator-reviewed catalog alongside prepared playback."""
    fields = {'asset_id', 'label', 'start_sec', 'end_sec', 'source_identity',
              'duration_ms', 'playback_sha256'}
    try:
        if type(prepared) is not PreparedVideos or not digest(expected_sha256):
            raise ValueError()
        before = identity(path)
        raw = bounded_read(path, MAX_CATALOG_BYTES)
        if hashlib.sha256(raw).hexdigest() != expected_sha256 or identity(path) != before:
            raise ValueError()
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique)
        if (type(value) is not dict or set(value) != {'version', 'moments'}
                or type(value['version']) is not int or value['version'] != 1
                or type(value['moments']) is not list or len(value['moments']) > MAX_MOMENTS):
            raise ValueError()
        moments = []
        for row in value['moments']:
            if type(row) is not dict or set(row) != fields or type(row['source_identity']) is not list:
                raise ValueError()
            moment = VideoMoment(**(row | {'source_identity': tuple(row['source_identity'])}))
            asset = prepared.entries.get(moment.asset_id)
            if (asset is None or tuple(asset['source_identity']) != moment.source_identity
                    or asset['video']['duration_ms'] != moment.duration_ms
                    or asset['video']['sha256'] != moment.playback_sha256):
                raise ValueError()
            moments.append(moment)
        if len(set(moments)) != len(moments):
            raise ValueError()
        prepared.current()
        return VideoMomentCatalog(tuple(moments))
    except (OSError, Refused, ValueError, RecursionError, TransportError):
        raise ValueError('Reviewed video moment catalog unavailable') from None


def configured_runtime(request):
    catalog = getattr(request.app.state, 'video_moment_catalog', None)
    media = getattr(request.app.state, 'media_runtime', None)
    if (type(catalog) is not VideoMomentCatalog or type(media) is not MediaRuntime
            or type(media.prepared_videos) is not PreparedVideos):
        raise TransportError(503, 'Video moments unavailable')
    return media, catalog


def _require_library(access, token, library):
    with access.connection_factory() as connection:
        AccessService(connection, clock=access.clock).require(token, library, 'library.read')


def _source_pin(media, access, token, library, asset_id):
    opened, info, extension = media.open_file(
        access, token, library, asset_id, 'display_source', 256)
    try:
        if extension not in ('.mp4', '.mov', '.webm'):
            raise TransportError(409, 'Video moments changed')
        return pin(info)
    finally:
        opened.close()


def _current_prepared(media, provider, access, token, library, moment):
    try:
        current = _source_pin(media, access, token, library, moment.asset_id)
    except AccessDenied:
        # Catalog entries outside this caller's current library are invisible.
        _require_library(access, token, library)
        return False
    except (FileNotFoundError, NotADirectoryError):
        raise TransportError(409, 'Video moments changed') from None
    if current != moment.source_identity:
        raise TransportError(409, 'Video moments changed')
    try:
        reader = provider.open(moment.asset_id, current)
    except TransportError as error:
        if error.status in (404, 409):
            raise TransportError(409, 'Video moments changed') from None
        raise
    try:
        if reader.meta['duration_ms'] != moment.duration_ms:
            raise TransportError(409, 'Video moments changed')
        if reader.meta['sha256'] != moment.playback_sha256:
            raise TransportError(409, 'Video moments changed')
        reader.check()
    finally:
        reader.close()
    # Reauthorize and re-pin after checking the prepared index. The playback
    # route performs the same current-source check before each streamed chunk.
    if _source_pin(media, access, token, library, moment.asset_id) != current:
        raise TransportError(409, 'Video moments changed')
    return True


def _search(access, media, catalog, token, library, query):
    _require_library(access, token, library)
    provider = verified_prepared_video_provider(media)
    needle = query.casefold().strip()
    if not needle:
        raise TransportError(400, 'Invalid request')
    matches = [item for item in catalog.moments if needle in item.label.casefold()]
    results = []
    for moment in matches:
        if not _current_prepared(media, provider, access, token, library, moment):
            continue
        results.append({'asset_id': str(moment.asset_id), 'label': moment.label,
                        'start_sec': float(moment.start_sec),
                        'end_sec': float(moment.end_sec),
                        'playback_revision': moment.playback_sha256})
    _require_library(access, token, library)
    provider.current()
    return {'version': 1, 'results': results}


router = APIRouter(route_class=AccessRoute)


@router.post('/libraries/{library_id}/video-moments/v1/search')
async def search_video_moments(request: Request, library_id: str):
    token, _mode = credentials_from_request(request)
    access = access_runtime(request, allow_query=False)
    # Authorize before parsing query text or disclosing whether the optional
    # catalog/runtime is configured.
    await run_in_threadpool(_require_library, access, token, library_id)
    media, catalog = configured_runtime(request)
    body = await _body(request, {'query'}, max_body=2048)
    query = body['query']
    if (len(query) > MAX_QUERY_CHARS
            or any(ord(char) < 32 or 0x7f <= ord(char) < 0xa0 for char in query)):
        raise TransportError(400, 'Invalid request')
    result = await run_in_threadpool(_search, access, media, catalog,
                                     token, library_id, query)
    return JSONResponse(result, headers=PRIVACY_HEADERS)


@router.get('/libraries/{library_id}/video-moments/v1/capabilities')
async def video_moment_capabilities(request: Request, library_id: str):
    token, _mode = credentials_from_request(request)
    access = access_runtime(request, allow_query=False)
    await run_in_threadpool(_require_library, access, token, library_id)
    media, _catalog = configured_runtime(request)
    await run_in_threadpool(verified_prepared_video_provider, media)
    return JSONResponse({'version': 1, 'enabled': True,
                         'search': {'max_moments': MAX_MOMENTS,
                                    'playback_revision': 'sha256'}},
                        headers=PRIVACY_HEADERS)

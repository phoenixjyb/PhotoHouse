"""Default-off, author-private transport for resumable oral-history sources."""
import asyncio
import json
import re

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .assistant_speech import AssistantAsrFailure
from .oral_history_intake import OralHistoryIntake, CREATE_FIELDS, _uuid
from .oral_history_schema import MAX_SECTION_BYTES, MAX_SECTIONS, MAX_REVIEW_REVISION, MAX_REVIEW_TEXT_BYTES
from .service import AccessService
from .transport import AccessRoute, TransportError, _runtime, _single, credentials_from_request

router = APIRouter(route_class=AccessRoute)
MAX_JSON_BYTES = 2048
BODY_SECONDS = 5
TEXT_FIELDS = {'title', 'subject_label', 'narrator_label', 'language', 'request_id'}


def _intake_call(runtime, operation, token, library, *args, **kwargs):
    with runtime.connection_factory() as db:
        service = AccessService(db, clock=runtime.clock)
        return getattr(OralHistoryIntake(service, enabled=True), operation)(
            token, library, *args, **kwargs)


def _authorize(runtime, token, library):
    with runtime.connection_factory() as db:
        return AccessService(db, clock=runtime.clock).require(token, library, 'library.read')


def _admitted(request):
    token, _mode = credentials_from_request(request)
    runtime = _runtime(request)
    if not getattr(request.app.state, 'oral_history_intake_enabled', False):
        raise TransportError(503, 'Recording intake unavailable')
    return runtime, token


async def _read_json(request, maximum):
    if (request.scope.get('query_string') or _single(request, 'content-encoding') is not None
            or _single(request, 'transfer-encoding') is not None):
        raise TransportError(400, 'Invalid recording request')
    content_types = request.headers.getlist('content-type')
    if len(content_types) != 1 or content_types[0].strip().lower() != 'application/json':
        raise TransportError(415, 'JSON body required')
    lengths = request.headers.getlist('content-length')
    if len(lengths) > 1:
        raise TransportError(400, 'Invalid recording request')
    if lengths:
        value = lengths[0]
        if not re.fullmatch(r'[0-9]{1,7}', value) or int(value) > maximum:
            raise TransportError(413, 'Recording request too large')
    payload = bytearray()
    try:
        async with asyncio.timeout(BODY_SECONDS):
            async for chunk in request.stream():
                if len(payload) + len(chunk) > maximum:
                    raise TransportError(413, 'Recording request too large')
                payload.extend(chunk)
    except TimeoutError:
        raise TransportError(408, 'Recording request timed out') from None
    if lengths and len(payload) != int(lengths[0]):
        raise TransportError(400, 'Invalid recording request')

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate')
            result[key] = value
        return result

    try:
        return json.loads(payload.decode('utf-8', errors='strict'), object_pairs_hook=unique,
                          parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, RecursionError):
        raise TransportError(400, 'Invalid recording request') from None


async def _json_body(request):
    body = await _read_json(request, MAX_JSON_BYTES)
    try:
        if type(body) is not dict or set(body) != CREATE_FIELDS:
            raise ValueError()
        if any(type(body[key]) is not str for key in TEXT_FIELDS):
            raise ValueError()
        if any(type(body[key]) is not bool for key in ('retention_consent', 'processing_consent')):
            raise ValueError()
        for value in body.values():
            if type(value) is str:
                value.encode('utf-8', errors='strict')
        return body
    except (ValueError, UnicodeError):
        raise TransportError(400, 'Invalid recording request') from None


async def _audio_body(request):
    if request.scope.get('query_string') or _single(request, 'content-encoding') is not None:
        raise TransportError(400, 'Invalid recording section')
    content_types = request.headers.getlist('content-type')
    if len(content_types) != 1 or content_types[0].strip().lower() != 'audio/wav':
        raise TransportError(415, 'WAV section required')
    lengths = request.headers.getlist('content-length')
    if len(lengths) > 1:
        raise TransportError(400, 'Invalid recording section')
    if lengths:
        value = lengths[0]
        if not re.fullmatch(r'[0-9]{1,7}', value) or int(value) > MAX_SECTION_BYTES:
            raise TransportError(413, 'Recording section too large')
    payload = bytearray()
    try:
        async with asyncio.timeout(BODY_SECONDS):
            async for chunk in request.stream():
                if len(payload) + len(chunk) > MAX_SECTION_BYTES:
                    raise TransportError(413, 'Recording section too large')
                payload.extend(chunk)
    except TimeoutError:
        raise TransportError(408, 'Recording section timed out') from None
    if lengths and len(payload) != int(lengths[0]):
        raise TransportError(400, 'Invalid recording section')
    return bytes(payload)


def _json_response(value, status=200):
    return JSONResponse(value, status_code=status)


@router.post('/oral-history/v1/libraries/{library_id}/sessions')
async def create_session(library_id: str, request: Request):
    runtime, token = _admitted(request)
    # Check current membership before consuming caller-authored metadata.
    await run_in_threadpool(_authorize, runtime, token, library_id)
    body = await _json_body(request)
    result = await run_in_threadpool(_intake_call, runtime, 'create', token, library_id, body)
    return _json_response(result, status=201)


@router.get('/oral-history/v1/libraries/{library_id}/sessions')
async def list_open_sessions(library_id: str, request: Request):
    runtime, token = _admitted(request)
    result = await run_in_threadpool(_intake_call, runtime, 'list_open', token, library_id)
    return _json_response(result)


@router.get('/oral-history/v1/libraries/{library_id}/sessions/completed')
async def list_completed_sessions(library_id: str, request: Request):
    runtime, token = _admitted(request)
    result = await run_in_threadpool(_intake_call, runtime, 'list_completed', token, library_id)
    return _json_response(result)


@router.get('/oral-history/v1/libraries/{library_id}/sessions/{session_id}')
async def session_status(library_id: str, session_id: str, request: Request):
    runtime, token = _admitted(request)
    result = await run_in_threadpool(_intake_call, runtime, 'status', token, library_id, session_id)
    return _json_response(result)


def _section_revision(request):
    expected = _single(request, 'x-photohouse-expected-revision')
    if (expected is None or not re.fullmatch(r'[1-9][0-9]{0,2}', expected)
            or int(expected) > MAX_SECTIONS + 2):
        raise TransportError(400, 'Invalid recording section')
    return int(expected)


@router.get('/oral-history/v1/libraries/{library_id}/sessions/{session_id}/timeline')
async def completed_timeline(library_id: str, session_id: str, request: Request):
    runtime, token = _admitted(request)
    result = await run_in_threadpool(_intake_call, runtime, 'completed_timeline', token,
        library_id, session_id, expected_revision=_section_revision(request))
    return _json_response(result)


@router.get('/oral-history/v1/libraries/{library_id}/sessions/{session_id}/sections/{ordinal}')
async def completed_section(library_id: str, session_id: str, ordinal: str, request: Request):
    runtime, token = _admitted(request)
    revision = _section_revision(request)
    if not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})', ordinal) or int(ordinal) >= MAX_SECTIONS:
        raise TransportError(400, 'Invalid recording section')
    audio = await run_in_threadpool(_intake_call, runtime, 'completed_audio', token,
        library_id, session_id, int(ordinal), expected_revision=revision)
    return Response(audio, media_type='audio/wav')


def _transcription_preview(runtime, token, library, session_id, ordinal, revision, asr, lock):
    args = (runtime, 'completed_audio', token, library, session_id, ordinal)
    options = {'expected_revision': revision, 'for_transcription': True}
    audio = _intake_call(*args, **options)
    if not lock.acquire(blocking=False):
        raise TransportError(503, 'Recording transcription is busy')
    try:
        try:
            transcript = asr.transcribe(audio)
        except AssistantAsrFailure as error:
            raise TransportError(error.status, 'Recording transcription unavailable') from None
        if _intake_call(*args, **options) != audio:
            raise TransportError(409, 'Recording changed; refresh before reading')
    finally:
        lock.release()
    return {'version': 1, 'session_id': session_id, 'revision': revision, 'ordinal': ordinal,
            'text': transcript['text'], 'language': transcript['language'], 'saved': False}


@router.post('/oral-history/v1/libraries/{library_id}/sessions/{session_id}/sections/{ordinal}/transcription')
async def transcribe_section(library_id: str, session_id: str, ordinal: str, request: Request):
    runtime, token = _admitted(request)
    await run_in_threadpool(_authorize, runtime, token, library_id)
    state = request.app.state
    if not state.oral_history_transcription_enabled:
        raise TransportError(503, 'Recording transcription unavailable')
    body = await _read_json(request, MAX_JSON_BYTES)
    if (type(body) is not dict or set(body) != {'expected_revision'}
            or type(body['expected_revision']) is not int
            or not 1 <= body['expected_revision'] <= MAX_SECTIONS + 2
            or not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})', ordinal)
            or int(ordinal) >= MAX_SECTIONS):
        raise TransportError(400, 'Invalid recording section')
    result = await run_in_threadpool(_transcription_preview, runtime, token, library_id,
                                    session_id, int(ordinal), body['expected_revision'],
                                    state.assistant_asr, state.oral_history_transcription_lock)
    return _json_response(result)


@router.api_route(
    '/oral-history/v1/libraries/{library_id}/sessions/{session_id}/sections/{ordinal}/reviewed-text',
    methods=['GET', 'PUT'],
)
async def reviewed_section(library_id: str, session_id: str, ordinal: str, request: Request):
    runtime, token = _admitted(request)
    await run_in_threadpool(_authorize, runtime, token, library_id)
    if not request.app.state.oral_history_reviewed_text_enabled:
        raise TransportError(503, 'Recording review unavailable')
    if not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})', ordinal) or int(ordinal) >= MAX_SECTIONS:
        raise TransportError(400, 'Invalid recording section')
    if request.method == 'PUT':
        body = await _read_json(request, 6 * MAX_REVIEW_TEXT_BYTES + MAX_JSON_BYTES)
        if (type(body) is not dict or set(body) != {'expected_revision', 'expected_review_revision', 'text'}
                or type(body['expected_revision']) is not int
                or not 1 <= body['expected_revision'] <= MAX_SECTIONS + 2
                or type(body['expected_review_revision']) is not int
                or not 0 <= body['expected_review_revision'] <= MAX_REVIEW_REVISION
                or type(body['text']) is not str):
            raise TransportError(400, 'Invalid recording section')
        options = body
    else:
        expected = _single(request, 'x-photohouse-expected-revision')
        if (expected is None or not re.fullmatch(r'[1-9][0-9]{0,2}', expected)
                or int(expected) > MAX_SECTIONS + 2):
            raise TransportError(400, 'Invalid recording section')
        options = {'expected_revision': int(expected)}
    result = await run_in_threadpool(_intake_call, runtime, 'reviewed_section', token, library_id,
                                    session_id, int(ordinal), **options)
    return _json_response(result)


@router.post('/oral-history/v1/libraries/{library_id}/sessions/{session_id}/sections')
async def append_section(library_id: str, session_id: str, request: Request):
    runtime, token = _admitted(request)
    request_id = _single(request, 'x-photohouse-request-id')
    expected = _single(request, 'x-photohouse-expected-revision')
    ordinal = _single(request, 'x-photohouse-ordinal')
    if (request_id is None or expected is None or ordinal is None
            or not re.fullmatch(r'[1-9][0-9]{0,2}', expected)
            or not re.fullmatch(r'(?:0|[1-9][0-9]{0,2})', ordinal)
            or int(expected) > MAX_SECTIONS + 2 or int(ordinal) >= MAX_SECTIONS):
        raise TransportError(400, 'Invalid recording section')
    request_id = _uuid(request_id)
    # Author and exact session scope are checked before any audio bytes are read.
    await run_in_threadpool(_intake_call, runtime, 'status', token, library_id, session_id)
    audio = await _audio_body(request)
    result = await run_in_threadpool(_intake_call, runtime, 'append', token, library_id, session_id,
        request_id=request_id, expected_revision=int(expected), ordinal=int(ordinal), audio=audio)
    return _json_response(result)


async def _close(request, library_id, session_id, *, cancel):
    runtime, token = _admitted(request)
    body = await _json_body_close(request)
    result = await run_in_threadpool(_intake_call, runtime, 'close', token, library_id, session_id,
        request_id=body['request_id'], expected_revision=body['expected_revision'], cancel=cancel)
    return _json_response(result)


async def _json_body_close(request):
    value = await _read_json(request, 1024)
    try:
        if (type(value) is not dict or set(value) != {'request_id', 'expected_revision'}
                or type(value['request_id']) is not str or type(value['expected_revision']) is not int):
            raise ValueError()
        return value
    except (ValueError, UnicodeError, RecursionError):
        raise TransportError(400, 'Invalid recording request') from None


@router.post('/oral-history/v1/libraries/{library_id}/sessions/{session_id}/complete')
async def complete_session(library_id: str, session_id: str, request: Request):
    return await _close(request, library_id, session_id, cancel=False)


@router.post('/oral-history/v1/libraries/{library_id}/sessions/{session_id}/cancel')
async def cancel_session(library_id: str, session_id: str, request: Request):
    return await _close(request, library_id, session_id, cancel=True)

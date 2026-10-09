"""Protected, bounded PhotoHouse assistant turns.

The first action set is deliberately read-only. A client-held context is never
authority: every follow-up repeats policy and discovery checks before an asset
reference can become an ``open_asset`` effect. Speech providers are separate
opt-in capabilities and never turn recognized words into credentials.
"""
import asyncio
import calendar
from datetime import datetime
import json
import math
import re
import uuid
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from starlette.concurrency import run_in_threadpool

from . import discovery as d
from .discovery_transport import DiscoveryRuntime
from .service import AccessDenied, AccessService
from .assistant_journal import (Journal, JournalUnavailable, JournalConflict,
                                JournalMissing, request_id)
from .assistant_speech import (LocalAssistantAsr, LocalAssistantTts, valid_wav,
                               MAX_WAV_BYTES, MAX_AUDIO_SECONDS, AssistantSpeechUnavailable)
from .transport import (AccessRuntime, PRIVACY_HEADERS, TransportError, _runtime,
                        _single, credentials_from_request)

MAX_BODY = 20 * 1024
PAGE_SIZE = 20
ORDINALS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
CHINESE_MONTHS = dict(ORDINALS, 十一=11, 十二=12)

# Recognized command openings only. Unmatched details still require clarification;
# a conversational prefix never supplies a person, place or unrestricted action.
SEARCH_PREFIX = r'^(?:请)?(?:帮我找|帮我查找|帮我搜索|我想看看|我想看|给我看看|给我看|查找|搜索|显示|看看|找|find|search|show)'
REFINE_PREFIX = r'^(?:只看|只要|筛选|再找|再看看|再看|缩小|换成|改成|那么|那|refine|only|filter|just|what about|how about|same but)'
BARE_FOLLOWUP = re.compile(
    r'(?:视频|影片|照片|图片|相片|videos?|movies?|photos?|pictures?|images?|'
    r'(?:去年|今年|20\d{2}年)(?:(?:1[0-2]|0?[1-9]|十一|十二|十|[一二三四五六七八九])月)?(?:的)?|'
    r'(?:last year|this year))(?:呢)?[。！？.!?]*', re.IGNORECASE)


class AssistantInvalid(ValueError):
    pass


class AssistantChanged(Exception):
    pass


def failure(status, code, detail):
    return JSONResponse({'error': code, 'detail': detail}, status_code=status)


class AssistantRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                _runtime(request, allow_query=request.method == 'GET')
                response = await handler(request)
            except TransportError as error:
                code = ('access_denied' if error.status in (401, 403) else
                        'request_too_large' if error.status == 413 else 'invalid_request')
                response = failure(error.status, code, error.message)
            except AccessDenied:
                response = failure(401, 'access_denied', 'Access denied')
            except AssistantInvalid:
                response = failure(400, 'invalid_request', 'Invalid assistant request')
            except (AssistantChanged, d.DiscoveryChanged):
                response = failure(409, 'context_changed', 'Refresh assistant results')
            except d.DiscoveryInvalid:
                response = failure(400, 'invalid_request', 'Invalid assistant request')
            except d.DiscoveryBusy:
                response = failure(429, 'assistant_busy', 'Assistant busy')
                response.headers['Retry-After'] = '2'
            except AssistantSpeechUnavailable:
                response = failure(503, 'speech_unavailable', 'Local speech service unavailable')
            except JournalUnavailable:
                response = failure(503, 'tracking_unavailable', 'Request tracking unavailable')
            except JournalConflict:
                response = failure(409, 'request_conflict', 'Check the existing receipt')
            except JournalMissing:
                response = failure(404, 'receipt_unavailable', 'Receipt unavailable')
            except asyncio.CancelledError:
                ident = getattr(request.state, 'assistant_request_id', None)
                if ident is not None:
                    try:
                        await asyncio.shield(run_in_threadpool(
                            request.app.state.assistant_journal.finish, ident, 'failed',
                            http_status=499, error='request_cancelled'))
                    except Exception:
                        # A hard shutdown leaves the original durable receipt;
                        # startup reconciliation then marks it interrupted.
                        pass
                raise
            except Exception:
                # No source paths, session labels, request words or provider details.
                response = failure(503, 'assistant_unavailable', 'Assistant unavailable')
            journal = getattr(request.app.state, 'assistant_journal', None)
            response.headers['X-PhotoHouse-Tracking'] = 'enabled' if journal is not None else 'disabled'
            ident = getattr(request.state, 'assistant_request_id', None)
            if ident is not None:
                error = None
                if response.status_code >= 400:
                    try:
                        error = json.loads(response.body)['error']
                    except (ValueError, KeyError, AttributeError):
                        error = 'assistant_unavailable'
                try:
                    await run_in_threadpool(journal.finish, ident,
                        'succeeded' if response.status_code < 400 else 'failed',
                        http_status=response.status_code, error=error,
                        **getattr(request.state, 'assistant_summary', {}))
                    response.headers['X-PhotoHouse-Request-Id'] = ident
                    response.headers['X-PhotoHouse-Receipt-Status'] = ('succeeded' if response.status_code < 400 else 'failed')
                except Exception:
                    response = failure(503, 'tracking_unavailable', 'Request tracking unavailable')
                    response.headers['X-PhotoHouse-Tracking'] = 'enabled'
                    # Begin was durable, but finalization was not acknowledged.
                    response.headers['X-PhotoHouse-Request-Id'] = ident
                    response.headers['X-PhotoHouse-Receipt-Status'] = 'received'
            for key, value in PRIVACY_HEADERS.items():
                response.headers[key] = value
            return response

        return guarded


router = APIRouter(route_class=AssistantRoute)


def _engine(request):
    access = _runtime(request, allow_query=request.method == 'GET')
    discovery = getattr(request.app.state, 'discovery_runtime', None)
    enabled = getattr(request.app.state, 'assistant_enabled', False)
    if (not enabled or not isinstance(access, AccessRuntime)
            or not isinstance(discovery, DiscoveryRuntime) or discovery.access is not access):
        return access, None
    return access, discovery


def _authorize(access, token, library):
    with access.connection_factory() as connection:
        return AccessService(connection, clock=access.clock).library_principal(token, library)


async def _begin(request, access, token, library, operation, text=None):
    identity = await run_in_threadpool(_authorize, access, token, library)
    header_library = _single(request, 'x-photohouse-library-id')
    if header_library is not None and header_library != library:
        raise AssistantInvalid()
    journal = getattr(request.app.state, 'assistant_journal', None)
    if journal is None:
        return
    if not isinstance(journal, Journal) or not request.app.state.assistant_journal_healthy:
        raise JournalUnavailable()
    try:
        selected = _single(request, 'x-photohouse-request-id')
        ident = request_id(str(uuid.uuid4()) if selected is None else selected)
        parent = _single(request, 'x-photohouse-parent-request-id')
        if parent is not None:
            request_id(parent)
    except ValueError:
        raise AssistantInvalid() from None
    await run_in_threadpool(journal.begin, identity, library, operation, ident, parent, text)
    request.state.assistant_request_id = ident


async def _stage(request, stage):
    ident = getattr(request.state, 'assistant_request_id', None)
    if ident is not None:
        await run_in_threadpool(request.app.state.assistant_journal.stage, ident, stage)


def _library(value):
    if (type(value) is not str or not 1 <= len(value) <= 128
            or any(ord(char) < 32 for char in value)):
        raise AssistantInvalid()
    return value


def _query_library(request):
    try:
        raw = request.scope.get('query_string', b'').decode('ascii')
        if re.search(r'%(?![0-9a-fA-F]{2})', raw):
            raise ValueError()
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True,
                          errors='strict', max_num_fields=1)
        if len(pairs) != 1 or pairs[0][0] != 'library_id':
            raise ValueError()
        return _library(pairs[0][1])
    except (UnicodeError, ValueError):
        raise AssistantInvalid() from None


def _bounded(value, depth=0, count=None):
    if count is None:
        count = [0]
    count[0] += 1
    if count[0] > 256 or depth > 5:
        raise AssistantInvalid()
    if type(value) is str:
        if len(value.encode('utf-8')) > 4096 or any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise AssistantInvalid()
    elif type(value) is dict:
        for key, item in value.items():
            _bounded(key, depth + 1, count)
            _bounded(item, depth + 1, count)
    elif type(value) is list:
        for item in value:
            _bounded(item, depth + 1, count)
    elif value is not None and type(value) not in (bool, int, float):
        raise AssistantInvalid()


async def _body(request, fields=frozenset({'library_id', 'text', 'context'})):
    if request.scope.get('query_string') or _single(request, 'content-encoding') is not None:
        raise AssistantInvalid()
    if (_single(request, 'content-type') or '').split(';')[0].strip().lower() != 'application/json':
        raise AssistantInvalid()
    length = _single(request, 'content-length')
    if length is not None and (not length.isdecimal() or int(length) > MAX_BODY):
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
        raise AssistantInvalid()

    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise AssistantInvalid()
            result[key] = item
        return result

    try:
        result = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                            parse_constant=lambda _: (_ for _ in ()).throw(AssistantInvalid()))
        _bounded(result)
        if type(result) is not dict or set(result) != fields:
            raise AssistantInvalid()
        _library(result['library_id'])
        if 'context' in fields and result['context'] is not None and type(result['context']) is not dict:
            raise AssistantInvalid()
        if 'text' in fields and (type(result['text']) is not str or not result['text'].strip()
                                 or len(result['text'].encode('utf-8')) > 1024):
            raise AssistantInvalid()
        if 'language' in fields and result['language'] not in ('zh', 'en'):
            raise AssistantInvalid()
        if 'outcome' in fields and result['outcome'] not in ('displayed','open_requested','failed','cancelled'):
            raise AssistantInvalid()
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise AssistantInvalid() from None


def _context(value, library):
    if type(value) is not dict or set(value) != {'library_id', 'binding', 'fingerprint', 'filters', 'visible_ids', 'total'}:
        raise AssistantInvalid()
    if value['library_id'] != library:
        raise AssistantChanged()
    if not d.hashed(value['binding']) or not d.hashed(value['fingerprint']):
        raise AssistantInvalid()
    if type(value['filters']) is not dict or type(value['visible_ids']) is not list:
        raise AssistantInvalid()
    if (len(value['visible_ids']) > PAGE_SIZE or len(set(map(str, value['visible_ids']))) != len(value['visible_ids'])
            or any(type(item) is not str for item in value['visible_ids'])
            or type(value['total']) is not int or value['total'] < 0):
        raise AssistantInvalid()
    for item in value['visible_ids']:
        d.identifier(item)
    return value


def _language(words):
    return 'zh' if re.search(r'[\u3400-\u9fff]', words) else 'en'


def _ordinal(words):
    compact = re.sub(r'\s+', '', words.strip().casefold())
    english = re.fullmatch(r'(?:open|show)(?:the)?(first|second|third|fourth|fifth|[1-9]|10)(?:result|photo|video)?', compact)
    if english:
        raw = english.group(1)
        return {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5}.get(raw, int(raw) if raw.isdecimal() else None)
    match = re.fullmatch(r'(?:请)?(?:打开|查看|看|open|show)(?:第)?([1-9]|10|[一二三四五六七八九十])(?:个|张|条|项|st|nd|rd|th)?(?:结果|照片|视频|photo|video)?', compact)
    if not match:
        return None
    raw = match.group(1)
    return ORDINALS.get(raw, int(raw) if raw.isdecimal() else None)


def _date_filter(words, now):
    normalized = words.casefold()
    match = re.search(r'(?<!\d)(20\d{2})[年/.-](1[0-2]|0?[1-9])(?:月)?(?!\d)', normalized)
    if match:
        year, month = int(match.group(1)), int(match.group(2))
    else:
        absolute_year = re.search(r'(?<!\d)(20\d{2})年(?!\d)', normalized)
        year = int(absolute_year.group(1)) if absolute_year else now.year - (1 if '去年' in normalized or 'last year' in normalized else 0)
        month_match = re.search(r'(?<!\d)(1[0-2]|0?[1-9])月', normalized)
        month = int(month_match.group(1)) if month_match else None
        if month is None:
            chinese = re.search(r'(十一|十二|十|[一二三四五六七八九])月', normalized)
            month = CHINESE_MONTHS[chinese.group(1)] if chinese else None
        if absolute_year is None and year == now.year and month is None and not ('今年' in normalized or 'this year' in normalized):
            return None
    if month is None:
        return {'from': f'{year:04d}-01-01', 'to': f'{year:04d}-12-31'}
    last = calendar.monthrange(year, month)[1]
    return {'from': f'{year:04d}-{month:02d}-01', 'to': f'{year:04d}-{month:02d}-{last:02d}'}


def _matches(words, items):
    haystack = words.casefold()
    found, matched = [], []
    for item in items:
        labels = [item.get('label'), *item.get('aliases', [])]
        # Reviewed bilingual display labels commonly use "English / 中文".
        labels += [part.strip() for label in labels if type(label) is str
                   for part in label.split('/')]
        hits = [label.casefold() for label in labels if type(label) is str
                and len(label.strip()) >= 2 and label.casefold() in haystack]
        if hits:
            found.append(item['id'])
            matched.append(max(hits, key=len))
    return found[:20], matched


def _unmatched(words, labels):
    remaining = words.casefold()
    for label in sorted(labels, key=len, reverse=True):
        remaining = remaining.replace(label, ' ')
    remaining = re.sub(r'(?<!\d)20\d{2}(?:年(?:(?:1[0-2]|0?[1-9])月?(?!\d))?|[/.\-](?:1[0-2]|0?[1-9])月?(?!\d))', ' ', remaining)
    remaining = re.sub(r'\b(?:last year|this year)\b|去年|今年|(?<!\d)(?:1[0-2]|0?[1-9])月|(?:十一|十二|十|[一二三四五六七八九])月', ' ', remaining)
    remaining = re.sub(SEARCH_PREFIX + '|' + REFINE_PREFIX, ' ', remaining)
    remaining = re.sub(r'视频|影片|照片|图片|相片|\b(?:videos?|movies?|photos?|pictures?|images?)\b', ' ', remaining)
    remaining = re.sub(r'\b(?:the|from|by|in|of|at|and|me|some)\b|[的、，。！？:：,.!?\s]+', '', remaining)
    # A trailing question particle is allowed only when every substantive detail
    # was consumed. Words such as 不要/删除 or unknown places remain unmatched.
    return '' if remaining == '呢' else remaining


def _facets(engine, token, library, facet, binding):
    result = []
    for page in range(1, 6):
        response = engine.call('facets', token, library, lambda: False,
                               {'facet': facet, 'page': page, 'page_size': 100,
                                'binding': binding if page > 1 else binding})
        result.extend(response['items'])
        if not response['has_more']:
            break
    return result


def _search(engine, token, library, binding, filters, fingerprint=None):
    result = engine.call('search', token, library, lambda: False,
                         {'binding': binding, 'filters': filters, 'page': 1,
                          'page_size': PAGE_SIZE, 'fingerprint': fingerprint})
    # Mirror discovery_transport's external card normalization; native clients
    # must not receive invalid dimensions from old imported metadata.
    for item in result['items']:
        for field in ('width', 'height'):
            value = item[field]
            if type(value) is not int or not 1 <= value <= 1000000:
                item[field] = None
        value = item['duration_sec']
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value)
                                  or not 0 <= value <= 1e9):
            item['duration_sec'] = None
    return result


def _turn(engine, token, library, words, previous, clock):
    lang = _language(words)
    now = datetime.fromtimestamp(clock())
    existing = None
    if previous is not None:
        previous = _context(previous, library)
        existing = _search(engine, token, library, previous['binding'],
                           previous['filters'], previous['fingerprint'])
        if ([item['id'] for item in existing['items']] != previous['visible_ids']
                or existing['total'] != previous['total']):
            raise AssistantChanged()
    ordinal = _ordinal(words)
    if ordinal is not None:
        if existing is None or ordinal > len(existing['items']):
            reply = '请先查找，再从当前结果中选择。' if lang == 'zh' else 'Search first, then choose a visible result.'
            return {'version': 1, 'kind': 'clarification', 'reply': reply,
                    'context': previous, 'filters': previous['filters'] if previous else None,
                    'items': existing['items'] if existing else [], 'total': existing['total'] if existing else 0,
                    'has_more': existing['has_more'] if existing else False, 'effect': None}
        asset_id = existing['items'][ordinal - 1]['id']
        reply = f'打开第{ordinal}项。' if lang == 'zh' else f'Opening result {ordinal}.'
        return {'version': 1, 'kind': 'open', 'reply': reply, 'context': previous,
                'filters': previous['filters'], 'items': existing['items'],
                'total': existing['total'], 'has_more': existing['has_more'],
                'effect': {'type': 'open_asset', 'asset_id': asset_id}}

    lower = words.strip().casefold()
    refine = bool(re.match(REFINE_PREFIX, lower) or BARE_FOLLOWUP.fullmatch(lower))
    search = bool(re.match(SEARCH_PREFIX, lower))
    if not (refine or search):
        reply = ('请说“找照片”、“找去年九月的视频”或“打开第二个”。' if lang == 'zh' else
                 'Try “find photos”, “find videos from last year”, or “open the second result”.')
        return {'version': 1, 'kind': 'unsupported', 'reply': reply, 'context': previous,
                'filters': previous['filters'] if previous else None,
                'items': existing['items'] if existing else [], 'total': existing['total'] if existing else 0,
                'has_more': existing['has_more'] if existing else False, 'effect': None}
    if refine and existing is None:
        reply = '请先查找，再缩小结果。' if lang == 'zh' else 'Search first, then refine the results.'
        return {'version': 1, 'kind': 'clarification', 'reply': reply, 'context': None,
                'filters': None, 'items': [], 'total': 0, 'has_more': False, 'effect': None}

    first = engine.call('facets', token, library, lambda: False,
                        {'facet': 'people', 'page': 1, 'page_size': 100})
    binding, enabled = first['binding'], set(first['enabled'])
    filters = dict(previous['filters']) if refine else {}
    if re.search(r'视频|影片|videos?\b|movies?\b', lower):
        filters['media'] = ['video']
    elif re.search(r'照片|图片|相片|photos?\b|pictures?\b|images?\b', lower):
        filters['media'] = ['image']
    dated = _date_filter(words, now)
    if dated is not None and 'date' not in enabled:
        reply = ('这个相册库暂时没有可用的日期索引。' if lang == 'zh' else
                 'Date search is not available in this library yet.')
        return {'version': 1, 'kind': 'clarification', 'reply': reply,
                'context': previous, 'filters': previous['filters'] if previous else None,
                'items': existing['items'] if existing else [], 'total': existing['total'] if existing else 0,
                'has_more': existing['has_more'] if existing else False, 'effect': None}
    if dated is not None:
        filters['date'] = dated
    labels = []
    if 'people' in enabled:
        people, hits = _matches(words, _facets(engine, token, library, 'people', binding))
        labels.extend(hits)
        if people:
            filters['people'] = {'ids': people, 'match': 'any'}
    if 'tags' in enabled:
        tags, hits = _matches(words, _facets(engine, token, library, 'tags', binding))
        labels.extend(hits)
        if tags:
            filters['tags'] = {'ids': tags, 'match': 'any'}
    if 'locations' in enabled:
        places, hits = _matches(words, _facets(engine, token, library, 'locations', binding))
        labels.extend(hits)
        if places:
            filters['locations'] = places
    if _unmatched(words, labels):
        reply = ('有些条件还无法准确匹配。请使用相册库中已有的人名、标签、地点，或指定年月。'
                 if lang == 'zh' else
                 'Some details could not be matched. Try a library person, label, place, or month.')
        return {'version': 1, 'kind': 'clarification', 'reply': reply,
                'context': previous, 'filters': previous['filters'] if previous else None,
                'items': existing['items'] if existing else [], 'total': existing['total'] if existing else 0,
                'has_more': existing['has_more'] if existing else False, 'effect': None}
    result = _search(engine, token, library, binding, filters)
    context = {'library_id': library, 'binding': result['binding'],
               'fingerprint': result['fingerprint'], 'filters': filters,
               'visible_ids': [item['id'] for item in result['items']], 'total': result['total']}
    reply = (f'找到 {result["total"]} 项。' if lang == 'zh' else
             f'Found {result["total"]} results.')
    return {'version': 1, 'kind': 'results', 'reply': reply, 'context': context,
            'filters': filters, 'items': result['items'], 'total': result['total'],
            'has_more': result['has_more'], 'effect': None}


@router.get('/assistant/v1/capabilities')
async def capabilities(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    library = _query_library(request)
    access, engine = _engine(request)
    await run_in_threadpool(_authorize, access, token, library)
    asr = getattr(request.app.state, 'assistant_asr', None)
    tts = getattr(request.app.state, 'assistant_tts', None)
    transcribe = engine is not None and isinstance(asr, LocalAssistantAsr)
    return {'version': 1, 'enabled': engine is not None, 'text': engine is not None,
            'transcribe': transcribe, 'speech': engine is not None and isinstance(tts, LocalAssistantTts),
            'max_audio_seconds': MAX_AUDIO_SECONDS if transcribe else 0}


@router.post('/assistant/v1/turns')
async def turns(request: Request):
    token, _ = credentials_from_request(request)
    access, engine = _engine(request)
    payload = await _body(request)
    library = payload['library_id']
    await _begin(request, access, token, library, 'turn', payload['text'])
    if engine is None:
        return failure(503, 'assistant_unavailable', 'Assistant unavailable')
    await _stage(request, 'action_started')
    result = await run_in_threadpool(_turn, engine, token, library,
                                     payload['text'], payload['context'], access.clock)
    request.state.assistant_summary = {'kind':result['kind'], 'total':result['total']}
    return JSONResponse(result)


@router.post('/assistant/v1/transcribe')
async def transcribe(request: Request):
    token, _ = credentials_from_request(request)
    access, engine = _engine(request)
    asr = getattr(request.app.state, 'assistant_asr', None)
    library = _library(_single(request, 'x-photohouse-library-id'))
    await _begin(request, access, token, library, 'transcribe')
    if engine is None or not isinstance(asr, LocalAssistantAsr):
        raise AssistantSpeechUnavailable()
    if (request.scope.get('query_string') or _single(request, 'content-encoding') is not None
            or (_single(request, 'content-type') or '').split(';')[0].strip().lower() != 'audio/wav'):
        raise AssistantInvalid()
    length = _single(request, 'content-length')
    if length is not None and (not length.isdecimal() or int(length) > MAX_WAV_BYTES):
        raise TransportError(413, 'Request too large')
    payload = bytearray()
    try:
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                if len(payload) + len(chunk) > MAX_WAV_BYTES:
                    raise TransportError(413, 'Request too large')
                payload.extend(chunk)
    except TimeoutError:
        raise TransportError(408, 'Request timed out') from None
    if (length is not None and len(payload) != int(length)) or not valid_wav(bytes(payload)):
        raise AssistantInvalid()
    # Provider request is made only after current library policy, and never saved
    # as an authored note. The returned transcript is a draft for user review.
    await run_in_threadpool(engine.authorize, token, library)
    await _stage(request, 'validated')
    await _stage(request, 'provider_started')
    result = await run_in_threadpool(asr.transcribe, bytes(payload))
    await run_in_threadpool(engine.authorize, token, library)
    await _stage(request, 'provider_completed')
    request.state.assistant_summary = {'transcript': result['text']}
    return JSONResponse(result)


@router.post('/assistant/v1/speech')
async def speech(request: Request):
    token, _ = credentials_from_request(request)
    access, engine = _engine(request)
    tts = getattr(request.app.state, 'assistant_tts', None)
    payload = await _body(request, frozenset({'library_id', 'context', 'language'}))
    library = payload['library_id']
    await _begin(request, access, token, library, 'speech')
    if engine is None or not isinstance(tts, LocalAssistantTts):
        raise AssistantSpeechUnavailable()
    context = _context(payload['context'], library)
    result = await run_in_threadpool(_search, engine, token, library, context['binding'],
                                     context['filters'], context['fingerprint'])
    if ([item['id'] for item in result['items']] != context['visible_ids']
            or result['total'] != context['total']):
        raise AssistantChanged()
    language = payload['language']
    words = (f'找到 {result["total"]} 项。' if language == 'zh' else
             f'Found {result["total"]} results.')
    await _stage(request, 'validated')
    await _stage(request, 'provider_started')
    audio = await run_in_threadpool(tts.synthesize, words, language)
    await run_in_threadpool(engine.authorize, token, library)
    await _stage(request, 'provider_completed')
    return Response(content=audio, media_type='audio/wav')


async def _receipt_author(request, token, library, ident):
    access, engine = _engine(request)
    if engine is None:
        raise JournalMissing()
    identity = await run_in_threadpool(_authorize, access, token, library)
    journal = getattr(request.app.state, 'assistant_journal', None)
    if journal is None:
        raise JournalMissing()
    try:
        request_id(ident)
    except ValueError:
        raise AssistantInvalid() from None
    return journal, identity


@router.get('/assistant/v1/receipts/{ident}')
async def receipt(request: Request, ident: str):
    token, _ = credentials_from_request(request, allow_query=True)
    library = _query_library(request)
    journal, identity = await _receipt_author(request, token, library, ident)
    return await run_in_threadpool(journal.get, ident, identity, library)


@router.post('/assistant/v1/receipts/{ident}/outcome')
async def receipt_outcome(request: Request, ident: str):
    token, _ = credentials_from_request(request)
    payload = await _body(request, frozenset({'library_id','outcome'}))
    library = payload['library_id']
    journal, identity = await _receipt_author(request, token, library, ident)
    return await run_in_threadpool(journal.outcome, ident, identity, library, payload['outcome'])

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
                               MAX_WAV_BYTES, MAX_AUDIO_SECONDS, AssistantSpeechUnavailable,
                               AssistantAsrFailure)
from .transport import (AccessRuntime, PRIVACY_HEADERS, TransportError, _runtime,
                        _single, credentials_from_request)

MAX_BODY = 20 * 1024
PAGE_SIZE = 20
MAX_REPLY_BYTES = 600
ORDINALS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
            '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
CHINESE_MONTHS = dict(ORDINALS, 十一=11, 十二=12)

# Recognized command openings only. Unmatched details still require clarification;
# a conversational prefix never supplies a person, place or unrestricted action.
SEARCH_PREFIX = (
    r'^(?:(?:(?:请|麻烦)(?:你)?\s*)?'
    r'(?:(?:帮我|替我|我想)(?:找一找|搜一搜|查找|搜索|找|查|搜|看看|看)|'
    r'给我(?:看看|看)|找一找|搜一搜|查找|搜索|显示|看看|找|查|搜)(?:一下)?|'
    r'(?:(?:please|can you|could you)\s+)?(?:find|search|show)\b'
    r'(?:\s+(?:me|for)\b)?)')
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
                code = ('search_version_unsupported' if error.status == 400 and
                        error.message == 'Search version is not supported on this endpoint' else
                        'access_denied' if error.status in (401, 403) else
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
            except AssistantAsrFailure as error:
                response = failure(error.status, error.code, 'Local transcription could not complete')
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


def _search_v2_endpoint(request):
    path = request.url.path
    return (path in ('/assistant/v1/turns', '/assistant/v1/speech', '/assistant/v1/capabilities',
                     '/assistant/workspace/v1/capabilities') or
            re.fullmatch(r'/assistant/workspace/v1/threads/[0-9a-f-]+/turns', path) is not None or
            re.fullmatch(r'/assistant/workspace/v1/threads/[0-9a-f-]+/requests/[0-9a-f-]+(?:/speech)?', path) is not None)


def _scene_endpoint(request):
    # The stateless assistant and speech routes never accept server-owned v4 state.
    return re.fullmatch(r'/assistant/workspace/v1/threads/[0-9a-f-]+/(?:turns|requests/[0-9a-f-]+)',
                        request.url.path) is not None


def _engine(request):
    access = _runtime(request, allow_query=request.method == 'GET')
    discovery = getattr(request.app.state, 'discovery_runtime', None)
    enabled = getattr(request.app.state, 'assistant_enabled', False)
    if (not enabled or not isinstance(access, AccessRuntime)
            or not isinstance(discovery, DiscoveryRuntime) or discovery.access is not access):
        return access, None
    version = _single(request, 'x-photohouse-search-version')
    if version == '4':
        from .assistant_scene_search import SceneSearchRuntime
        from .semantic_search import SemanticSearchRuntime
        semantic = getattr(request.app.state, 'semantic_search_runtime', None)
        if (not _scene_endpoint(request) or
                not getattr(request.app.state, 'assistant_semantic_search_enabled', False) or
                type(semantic) is not SemanticSearchRuntime or semantic.discovery is not discovery):
            raise TransportError(400, 'Search version is not supported on this endpoint')
        return access, SceneSearchRuntime(semantic, getattr(request.app.state, 'assistant_kinship_provider', None))
    if version not in (None, '1', '2', '3'):
        raise AssistantInvalid()
    if version in ('2', '3'):
        if not _search_v2_endpoint(request):
            raise TransportError(400, 'Search version is not supported on this endpoint')
        planner = getattr(request.app.state, 'assistant_intent_planner', None)
        if version == '3' and planner is None:
            raise TransportError(400, 'Search version is not supported on this endpoint')
        from .assistant_search import SearchRuntime
        discovery = SearchRuntime(discovery, getattr(request.app.state, 'assistant_kinship_provider', None),
                                  search_version=int(version), intent_planner=planner if version == '3' else None)
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


def _bounded(value, depth=0, count=None, *, max_depth=5, max_count=256):
    if count is None:
        count = [0]
    count[0] += 1
    if count[0] > max_count or depth > max_depth:
        raise AssistantInvalid()
    if type(value) is str:
        if len(value.encode('utf-8')) > 4096 or any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise AssistantInvalid()
    elif type(value) is dict:
        for key, item in value.items():
            _bounded(key, depth + 1, count, max_depth=max_depth, max_count=max_count)
            _bounded(item, depth + 1, count, max_depth=max_depth, max_count=max_count)
    elif type(value) is list:
        for item in value:
            _bounded(item, depth + 1, count, max_depth=max_depth, max_count=max_count)
    elif value is not None and type(value) not in (bool, int, float):
        raise AssistantInvalid()


async def _body(request, fields=frozenset({'library_id', 'text', 'context'}), *,
                outcome_values=('displayed', 'open_requested', 'failed', 'cancelled')):
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
        v3 = _single(request, 'x-photohouse-search-version') == '3'
        _bounded(result, max_depth=9 if v3 else 5, max_count=512 if v3 else 256)
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
        if 'outcome' in fields and result['outcome'] not in outcome_values:
            raise AssistantInvalid()
        return result
    except (ValueError, UnicodeError, RecursionError):
        raise AssistantInvalid() from None


def _context(value, library):
    if (type(value) is not dict or set(value) - {'search_version'} !=
            {'library_id', 'binding', 'fingerprint', 'filters', 'visible_ids', 'total'} or
            ('search_version' in value and (type(value['search_version']) is not int or value['search_version'] not in (2, 3)))):
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


def _asset_number(words):
    """An explicit ID marker avoids confusing asset IDs with result ordinals."""
    compact = re.sub(r'\s+', '', words.strip().casefold()).rstrip('。.!！?？')
    match = re.fullmatch(
        r'(?:(?:请)?(打开|查看|看|查找|搜索|找)(?:照片|图片|视频|素材)?(?:编号|号码)|'
        r'(open|show|find|search)(?:photo|video|asset)?(?:number|id|#))([1-9][0-9]{0,18})', compact)
    if not match or int(match.group(3)) > (1 << 63) - 1:
        return None
    return match.group(3), (match.group(1) or match.group(2)) in ('打开', '查看', '看', 'open', 'show')


def _describe_results(words):
    # Complete, read-only follow-ups only. Additional instructions are not
    # discarded, and a missing context never becomes an unrestricted search.
    normalized = re.sub(r'\s+', ' ', words.strip().casefold()).rstrip('。.!！?？')
    english = normalized.removeprefix('please ')
    if english in {'describe these results', 'tell me about these results',
                   'when were these photos taken', 'when were these videos taken',
                   'what date were these photos taken', 'what date were these videos taken',
                   'what dates are recorded for these results'}:
        return True
    chinese = re.sub(r'\s+', '', normalized).removeprefix('请')
    return chinese in {'介绍这些结果', '介绍一下这些结果', '介绍当前结果',
                       '介绍这些照片', '介绍一下这些照片', '介绍这些视频', '介绍一下这些视频',
                       '讲讲这些结果', '说说这些结果', '这些照片是什么时候拍的',
                       '这些照片是哪天拍的', '这些视频是哪天拍的',
                       '这些视频是什么时候拍的', '这些照片是什么时候的', '这些结果是什么时候的'}


def _result_overview(result, language):
    """Speak only bounded metadata from the current authorized card order.

    Discovery cards do not contain filename/upload date hints, captions or
    stories. A recorded date is therefore never inferred from those sources,
    nor converted into the client's unspecified timezone.
    """
    total, items = result['total'], result['items']
    zh = language == 'zh'
    if not items:
        return ('没有找到匹配的照片或视频。可以调整查找条件。' if zh else
                'No matching photos or videos were found. Try adjusting the search.')
    prefix = (f'找到 {total} 项。当前列表前{min(3, len(items))}项：' if zh else
              f'Found {total} {"result" if total == 1 else "results"}. In the current list: ')
    opening = next((i for i, item in enumerate(items[:3], 1)
                    if item.get('kind') in ('image', 'video')), None)
    if opening is None:
        suffix = '可以继续补充查找条件。' if zh else 'You can refine the search.'
    else:
        suffix = (f'可以说“打开第{opening}项”查看。' if zh else
                  f'Say "open the {("first", "second", "third")[opening - 1]} result" to view it.')
    clauses = []
    months = ('January', 'February', 'March', 'April', 'May', 'June',
              'July', 'August', 'September', 'October', 'November', 'December')
    for ordinal, item in enumerate(items[:3], 1):
        kind = ({'image': '照片', 'video': '视频'}.get(item.get('kind'), '素材') if zh else
                {'image': 'a photo', 'video': 'a video'}.get(item.get('kind'), 'an item'))
        day = d.taken_day(item.get('taken_at'))
        if day is None:
            dated = '日期未记录' if zh else 'date not recorded'
        else:
            year, month, date_day = map(int, day.split('-'))
            dated = (f'日期记录为 {year}年{month}月{date_day}日' if zh else
                     f'recorded date {months[month - 1]} {date_day}, {year}')
        clause = (f'第{ordinal}项是{kind}，{dated}。' if zh else
                  f'Result {ordinal} is {kind}, {dated}. ')
        candidate = prefix + ''.join(clauses) + clause + suffix
        if len(candidate.encode('utf-8')) > MAX_REPLY_BYTES:
            break
        clauses.append(clause)
    return prefix + ''.join(clauses) + suffix


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
    remaining = d.fold(words)
    for label in sorted(labels, key=len, reverse=True):
        remaining = remaining.replace(d.fold(label), ' ')
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


def _normalize_cards(result):
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


def _search(engine, token, library, binding, filters, fingerprint=None):
    return _normalize_cards(engine.call('search', token, library, lambda: False,
                            {'binding': binding, 'filters': filters, 'page': 1,
                             'page_size': PAGE_SIZE, 'fingerprint': fingerprint}))


def _context_result(engine, token, library, context):
    from .assistant_search import SearchRuntime
    if context.get('search_version', 1) != (engine.search_version if isinstance(engine, SearchRuntime) else 1):
        raise AssistantChanged()
    # Singleton lookup contexts use the same bounded wire shape as search. The
    # fingerprint binds the explicit ID and current session/membership/source.
    ids = context['visible_ids']
    if (context['filters'] == {} and context['total'] == 1 and len(ids) == 1
            and context['fingerprint'] == d.assistant_asset_fingerprint(context['binding'], ids[0])):
        result = _normalize_cards(engine.call('assistant_asset', token, library, lambda: False,
            {'asset_id': ids[0], 'binding': context['binding'], 'fingerprint': context['fingerprint']}))
    else:
        result = _search(engine, token, library, context['binding'], context['filters'], context['fingerprint'])
    if [item['id'] for item in result['items']] != ids or result['total'] != context['total']:
        raise AssistantChanged()
    return result


def _turn(engine, token, library, words, previous, clock, *, language=None, continuation=None):
    from .assistant_search import SearchRuntime
    if isinstance(engine, SearchRuntime):
        with engine.turn_scope():
            return _turn_scoped(engine, token, library, words, previous, clock, language=language,
                                continuation=continuation)
    return _turn_scoped(engine, token, library, words, previous, clock, language=language,
                        continuation=continuation)


def _turn_scoped(engine, token, library, words, previous, clock, *, language=None, continuation=None):
    from .assistant_search import SearchRuntime
    v2 = isinstance(engine, SearchRuntime)
    if previous is not None:
        previous = _context(previous, library)
    # A new explicit search may leave a legacy result behind. Refinements and
    # ordinal opens must retain the original protocol and source binding.
    from .search_refinement import query_mode
    if v2 and engine.search_version == 3:
        from .search_intent import intent_mode
        new_search = intent_mode(words) == 'search'
        if new_search:
            # An independent new v3 request reads the current authorized
            # library even when a previous result snapshot has gone stale.
            previous = None
    else:
        new_search = (query_mode(words) == 'search' if v2 else
                  bool(re.match(SEARCH_PREFIX, words.strip().casefold())))
    if (previous is not None and previous.get('search_version', 1) != (engine.search_version if v2 else 1)
            and new_search):
        previous = None
    source = {}
    result = _turn_impl(engine, token, library, words, previous, clock, language=language,
                        source=source, continuation=continuation)
    if v2:
        result['version'] = engine.search_version
        interpretation = source.get('interpretation')
        if result['context'] is not None:
            result['context'] = dict(result['context'], search_version=engine.search_version)
        if interpretation is None:
            presentation = engine.call('presentation', token, library, lambda: False,
                {'binding': result['context']['binding']} if result['context'] else {})
            interpretation = {key: value for key, value in presentation.items() if key != 'version'}
            interpretation.update(people=[], tags=[], locations=[])
        result['interpretation'] = interpretation
    return result


def _turn_impl(engine, token, library, words, previous, clock, *, language=None, source=None,
               continuation=None):
    from .assistant_search import SearchRuntime
    search_v2 = isinstance(engine, SearchRuntime)
    search_v3 = search_v2 and engine.search_version == 3
    if continuation is not None:
        from .assistant_query_plan import _valid_previous
        if (not search_v2 or previous is not None or type(continuation) is not dict
                or set(continuation) not in ({'binding', 'date'},
                                             {'binding', 'date', 'redacted_span'})
                or type(continuation['binding']) is not str
                or re.fullmatch('[0-9a-f]{64}', continuation['binding']) is None
                or not _valid_previous({'date': continuation['date']})):
            raise AssistantChanged()
    source = {} if source is None else source
    lang = language if language in ('zh', 'en') else _language(words)
    now = datetime.fromtimestamp(clock())
    existing = None
    if previous is not None:
        previous = _context(previous, library)
        existing = _context_result(engine, token, library, previous)
        source.update(existing)
    if search_v2:
        from .search_explanation import (describe_filter_query, explain_filters,
                                         describe_empty_query, no_results_guidance)
        explain_request = describe_filter_query(words)
        empty_request = describe_empty_query(words)
        if explain_request or empty_request:
            if existing is None:
                return {'version': 1, 'kind': 'clarification',
                        'reply': ('请先查找照片或视频，再询问当前筛选条件。' if lang == 'zh' else
                                  'Search for photos or videos first, then ask about the current filters.'),
                        'context': None, 'filters': None, 'items': [], 'total': 0,
                        'has_more': False, 'effect': None}
            if explain_request:
                reply = explain_filters(previous['filters'], existing.get('interpretation', {}), lang)
            elif existing['total'] == 0:
                reply = no_results_guidance(previous['filters'], lang)
            else:
                reply = (f'当前查找有 {existing["total"]} 项结果。可以问“现在筛选了哪些条件”。' if lang == 'zh' else
                         f'The current search has {existing["total"]} results. Ask "what filters are active" to review the conditions.')
            return {'version': 1, 'kind': 'results', 'reply': reply,
                    'context': previous, 'filters': previous['filters'], 'items': existing['items'],
                    'total': existing['total'], 'has_more': existing['has_more'], 'effect': None}
    from .result_explanation import parse_why_result_query, explain_result
    why_result = parse_why_result_query(words)
    if why_result is not None:
        selected = why_result['ordinal']
        if selected is None and existing is not None and existing['total'] == 1 and len(existing['items']) == 1:
            selected = 1
        target = (existing['items'][selected - 1]
                  if existing is not None and selected is not None and 1 <= selected <= len(existing['items'])
                  else None)
        if target is None or (why_result['kind'] is not None and target.get('kind') != why_result['kind']):
            reply = ('请先查找，再指定当前列表中的第几项；“这张照片”或“这个视频”需要唯一且类型相符的结果。'
                     if lang == 'zh' else
                     'Search first, then specify a result number in the current list. “This photo” or “this video” needs one result of that type.')
            kind = 'clarification'
        else:
            reply = explain_result(target, selected, previous['filters'],
                                   existing.get('interpretation', {}), lang)
            kind = 'results'
        return {'version': 1, 'kind': kind, 'reply': reply, 'context': previous,
                'filters': previous['filters'] if previous else None,
                'items': existing['items'] if existing else [],
                'total': existing['total'] if existing else 0,
                'has_more': existing['has_more'] if existing else False, 'effect': None}
    if _describe_results(words):
        if existing is None:
            return {'version': 1, 'kind': 'clarification',
                    'reply': ('请先查找照片或视频，再说“介绍这些结果”。' if lang == 'zh' else
                              'Search for photos or videos first, then say "describe these results".'),
                    'context': None, 'filters': None, 'items': [], 'total': 0,
                    'has_more': False, 'effect': None}
        return {'version': 1, 'kind': 'results', 'reply': _result_overview(existing, lang),
                'context': previous, 'filters': previous['filters'], 'items': existing['items'],
                'total': existing['total'], 'has_more': existing['has_more'], 'effect': None}
    numbered = _asset_number(words)
    if numbered is not None:
        asset_id, opens = numbered
        first = engine.call('facets', token, library, lambda: False,
                            {'facet': 'people', 'page': 1, 'page_size': 1})
        found = _normalize_cards(engine.call('assistant_asset', token, library, lambda: False,
            {'asset_id': asset_id, 'binding': first['binding']}))
        if found['items']:
            source.clear()
            source.update(found)
        if not found['items']:
            return {'version': 1, 'kind': 'clarification',
                    'reply': ('当前相册库中没有可访问的这个编号。请确认编号和相册库。' if lang == 'zh' else
                              'This number is not available in the current library. Check the number and library.'),
                    'context': previous, 'filters': previous['filters'] if previous else None,
                    'items': existing['items'] if existing else [], 'total': existing['total'] if existing else 0,
                    'has_more': existing['has_more'] if existing else False, 'effect': None}
        context = {'library_id': library, 'binding': found['binding'], 'fingerprint': found['fingerprint'],
                   'filters': {}, 'visible_ids': [asset_id], 'total': 1}
        reply = ((f'打开编号 {asset_id}。' if opens else f'找到编号 {asset_id}。') if lang == 'zh' else
                 (f'Opening asset {asset_id}.' if opens else f'Found asset {asset_id}.'))
        return {'version': 1, 'kind': 'open' if opens else 'results', 'reply': reply,
                'context': context, 'filters': {}, 'items': found['items'], 'total': 1, 'has_more': False,
                'effect': {'type': 'open_asset', 'asset_id': asset_id} if opens else None}
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
    people_answer = None
    answer_entities = None
    if search_v2:
        from .search_refinement import query_mode, plan_people_answer
        if search_v3:
            from .search_intent import intent_mode
            planned_mode = intent_mode(words)
        else:
            planned_mode = query_mode(words)
        refine = refine or planned_mode == 'refine'
        search = search or planned_mode == 'search'
        if existing is not None and not (refine or search):
            # A complete reviewed name can answer a conversational question.
            # Resolve it only after the previous scope has been revalidated;
            # the pure planner still rejects extra conditions or actions.
            answer_entities = engine.call('entities', token, library, lambda: False,
                                          {'words': words})
            people_answer = plan_people_answer(words, now=now, entities=answer_entities,
                                               previous_filters=previous['filters'])
            if people_answer is not None:
                refine = True
        if search_v3 and not (refine or search):
            # V3 accepts ordinary read-only search language. The bounded
            # intent compiler must account for all conditions before retrieval.
            # Preserve the explicit capture/search ambiguity from v2.
            if not re.match(r'^(?:请)?(?:帮我)?照一下', lower):
                refine = previous is not None
                search = not refine
    if not (refine or search):
        # Do not silently rewrite a transcript or treat a possible capture
        # request as permission to search. Ask the user to correct it instead.
        if re.match(r'^(?:请)?(?:帮我)?照一下', lower):
            reply = ('语音可能把“找一下”识别成了“照一下”。如果要查找已有照片，'
                     '请更正文字或说“帮我找一下……”。' if lang == 'zh' else
                     'The transcript may mean taking a photo rather than finding one. '
                     'Please correct it or say “find photos”.')
            return {'version': 1, 'kind': 'clarification', 'reply': reply, 'context': previous,
                    'filters': previous['filters'] if previous else None,
                    'items': existing['items'] if existing else [],
                    'total': existing['total'] if existing else 0,
                    'has_more': existing['has_more'] if existing else False, 'effect': None}
        reply = ('请说“找照片”、“找去年九月的视频”、“打开第二个”或“打开编号123”。' if lang == 'zh' else
                 'Try “find photos”, “find videos from last year”, “open the second result”, or “open asset id 123”.')
        return {'version': 1, 'kind': 'unsupported', 'reply': reply, 'context': previous,
                'filters': previous['filters'] if previous else None,
                'items': existing['items'] if existing else [], 'total': existing['total'] if existing else 0,
                'has_more': existing['has_more'] if existing else False, 'effect': None}
    if refine and existing is None:
        reply = '请先查找，再缩小结果。' if lang == 'zh' else 'Search first, then refine the results.'
        return {'version': 1, 'kind': 'clarification', 'reply': reply, 'context': None,
                'filters': None, 'items': [], 'total': 0, 'has_more': False, 'effect': None}

    condition_words = re.sub(r'[“"][^“”"]+[”"]', ' ', words) if search_v2 else words
    condition_lower = condition_words.casefold()
    first = (answer_entities if people_answer is not None else
             engine.call('entities' if search_v2 else 'facets', token, library, lambda: False,
                         {'words': condition_words} if search_v2 else
                         {'facet': 'people', 'page': 1, 'page_size': 100}))
    if existing is None:
        source.update(first)
    binding, enabled = first['binding'], set(first['enabled'])
    if continuation is not None and binding != continuation['binding']:
        raise AssistantChanged()
    if search_v2:
        from .search_refinement import plan_query
        if search_v3:
            from .search_intent import plan_query as plan_intent
            plan = plan_intent(words, now=now, entities=first,
                               previous_filters=previous['filters'] if previous else None,
                               planner=engine.intent_planner,
                               redacted_span=continuation.get('redacted_span')
                               if continuation is not None else None)
            # Inference can outlive source or membership changes. Withhold
            # even a clarification until the same authorized snapshot replays.
            engine.call('presentation', token, library, lambda: False, {'binding': binding})
            if continuation is not None and plan.status == 'ready':
                from .assistant_query_plan import QueryPlan
                if plan.filters.get('date') not in (None, continuation['date']):
                    raise AssistantChanged()
                plan = QueryPlan(3, 'ready', dict(plan.filters, date=continuation['date']))
        else:
            plan = (people_answer if people_answer is not None else
                    plan_query(words, now=now, entities=first,
                               previous_filters=previous['filters'] if previous else None, refine=refine))
            if continuation is not None and plan.status == 'ready':
                if plan.filters.get('date') not in (None, continuation['date']):
                    raise AssistantChanged()
                from .assistant_query_plan import QueryPlan
                plan = QueryPlan(plan.version, 'ready',
                                 dict(plan.filters, date=continuation['date']))
        if plan.status != 'ready':
            reply = ('有些细节还无法匹配。请发送完整查找句，例如：找包含“红风筝”的照片。'
                     '如需限定人物、拍摄日期、标签或地点，也请在完整句中写明；未匹配的条件不会被忽略。'
                     if lang == 'zh' else
                     'Some details could not be matched. Send the complete query, for example: find photos '
                     'containing "red kite". Add any reviewed person, capture date, tag, or place you need; '
                     'unmatched conditions are not dropped.')
            if plan.reason in ('ambiguous_date_entity', 'ambiguous_media_entity'):
                reply = ('有个词既可能是已登记的名称，也可能是日期或媒体类型。请补充完整名称，或明确日期和类型。'
                         if lang == 'zh' else
                         'A word could mean a reviewed name or a date/media type. Use the full name or specify the date and type.')
            elif plan.reason in ('ambiguous_entities', 'ambiguous_people', 'ambiguous'):
                reply = ('有些姓名或条件有歧义。请补充完整姓名，并明确哪些人需要同时出现。'
                         if lang == 'zh' else
                         'Some names or conditions are ambiguous. Use full reviewed names and specify who must appear together.')
            elif plan.reason == 'people_reference_unavailable':
                reply = ('当前查找条件还没有明确人物，无法判断指的是谁。请提供已登记的姓名。' if lang == 'zh' else
                         'The current search has no selected people to refer to. Use a reviewed name first.')
            elif plan.reason == 'ambiguous_people_reference':
                reply = ('这个人物指代与当前选定的人数不一致。请提供完整姓名，或明确要沿用哪些人物。' if lang == 'zh' else
                         'That reference does not match the number of selected people. Use full names or clarify who you mean.')
            elif plan.reason == 'ambiguous_people_answer':
                reply = ('请在姓名之间加“和”表示需要同时出现，或加“或”表示任意一位。' if lang == 'zh' else
                         'Join the names with "and" to require everyone together, or "or" to match any of them.')
            elif plan.reason == 'conflicting_people_reference':
                reply = ('不能在同一句中既沿用原来的人物，又指定或取消人物。请分别操作。' if lang == 'zh' else
                         'Keep the selected people or change the people filter in a separate request.')
            elif plan.reason == 'description_removal_mismatch':
                reply = ('要移除的线索与当前查找不一致。请使用检索条件中显示的原线索。' if lang == 'zh' else
                         'That clue does not match the current search. Use the original clue shown in the search conditions.')
            elif plan.reason == 'description_removal_ambiguous':
                reply = ('有多个线索与要移除的内容一致。请重新描述这次查找。' if lang == 'zh' else
                         'More than one clue matches the requested removal. Describe the full search again.')
            elif plan.reason == 'description_removal_target_unavailable':
                reply = ('当前查找没有可单独移除的描述线索。请先查找一个具体场景。' if lang == 'zh' else
                         'The current search has no descriptive clue to remove. Search for a specific scene first.')
            elif plan.reason == 'description_removal_unsupported':
                reply = ('请一次移除一个原描述线索，例如：去掉“红外套”线索。其他条件请分别调整。' if lang == 'zh' else
                         'Remove one original descriptive clue at a time, for example: remove the "red coat" clue. Change other conditions separately.')
            elif plan.reason == 'description_addition_target_unavailable':
                reply = ('请先开始一次查找，再补充场景线索，例如：再加上蓝帽子。' if lang == 'zh' else
                         'Start a search first, then add a visual clue, for example: also with a blue hat.')
            elif plan.reason == 'description_addition_duplicate':
                reply = ('当前查找已包含这条场景线索，原有条件已保留。请补充其他细节。' if lang == 'zh' else
                         'That visual clue is already in the current search. The existing conditions are kept; add a different detail.')
            elif plan.reason == 'description_addition_limit':
                reply = ('当前查找已有六条场景线索。请先移除一条，再补充新线索，或重新描述完整查找。' if lang == 'zh' else
                         'The current search already has six visual clues. Remove one before adding another, or describe a complete new search.')
            elif plan.reason == 'description_addition_unsupported':
                reply = ('请一次补充一个场景线索，例如：再加上蓝帽子。原有线索和条件已保留；人物、日期和类型请分别调整。' if lang == 'zh' else
                         'Add one visual clue at a time, for example: also with a blue hat. Existing clues and conditions are kept; change people, dates or media separately.')
            elif plan.reason == 'description_correction_mismatch':
                reply = ('要更正的场景线索与当前查找不一致。请使用查找摘要中显示的原线索。' if lang == 'zh' else
                         'That scene clue does not match the current search. Use the original clue shown in the search summary.')
            elif plan.reason == 'description_correction_ambiguous':
                reply = ('有多个相同的场景线索，无法确定要更正哪一个。请重新描述这次查找。' if lang == 'zh' else
                         'More than one scene clue matches. Describe the full search again so the intended change is clear.')
            elif plan.reason == 'description_correction_target_unavailable':
                reply = ('当前查找没有可更正的场景线索。请先查找一个具体场景。' if lang == 'zh' else
                         'The current search has no scene clue to correct. Search for a specific scene first.')
            elif plan.reason == 'description_correction_unsupported':
                reply = ('请一次更正一个场景线索，例如“不是红外套，是蓝外套”。人物和日期请分别调整。' if lang == 'zh' else
                         'Correct one scene clue at a time, for example “not red coat, but blue coat”. Change people and dates separately.')
            elif plan.reason == 'correction_target_unavailable':
                reply = ('当前查找还没有这个日期或媒体类型条件。请先明确要查找的日期或类型。' if lang == 'zh' else
                         'The current search has no such date or media filter to correct. Specify that filter first.')
            elif plan.reason == 'correction_mismatch':
                reply = ('要更正的原条件与当前查找不一致。请确认当前日期或媒体类型，再更正。' if lang == 'zh' else
                         'The old value does not match the current search. Check the date or media filter before correcting it.')
            elif plan.reason == 'unsupported_correction':
                reply = ('一次只能更正一个日期或媒体类型条件，例如“不是照片，是视频”。其他条件请分别调整。' if lang == 'zh' else
                         'Correct one date or media filter at a time, for example “not photos, but videos”. Change other filters separately.')
            elif plan.reason == 'conflicting_refinement':
                reply = ('同一个条件不能同时取消和重新指定。请分别操作，或保留一个条件。' if lang == 'zh' else
                         'A filter cannot be removed and replaced in the same request. Choose one change or send them separately.')
            elif plan.reason in ('invalid_date', 'conflicting_dates'):
                reply = ('日期条件无效或互相冲突，请明确一个拍摄日期范围。' if lang == 'zh' else
                         'The date conditions are invalid or conflicting. Specify one capture-date range.')
            elif plan.reason == 'date_unavailable':
                reply = ('这个相册库暂时没有可用的日期索引。' if lang == 'zh' else
                         'Date search is not available in this library yet.')
            elif plan.reason == 'text_too_long':
                reply = ('要匹配的文字太长，请缩短引号内的内容后再查找。' if lang == 'zh' else
                         'The quoted text is too long. Shorten it and search again.')
            elif plan.reason in ('intent_date', 'intent_person', 'intent_description', 'intent_scope'):
                replies = {
                    'intent_date': ('大概是哪一年或哪几个月？请在这次查找中补充时间。',
                                    'About which year or months? Add that time to this search.'),
                    'intent_person': ('你指的是谁？请提供相册库中已登记的姓名。',
                                      'Who do you mean? Use a reviewed name from this library.'),
                    'intent_description': ('当时在做什么？有什么醒目的物品或地点？请再发送完整查找句，并写明需要的人物姓名和拍摄日期（如适用）。',
                                           'What was happening, and what distinctive object or place should I look for? Then send the complete search, including any reviewed person and capture date you want.'),
                    'intent_scope': ('这次要继续缩小当前结果，还是开始一次新的查找？',
                                     'Would you like to refine these results or start a new search?'),
                }
                reply = replies[plan.reason][0 if lang == 'zh' else 1]
            elif plan.reason == 'intent_unavailable':
                reply = ('可以按相册库已登记姓名、拍摄日期或带引号的照片说明原文查找，例如：找包含“红风筝”的照片。' if lang == 'zh' else
                         'Try searching by a reviewed person, capture date, or quoted caption text, for example: '
                         'find photos containing "red kite".')
            elif plan.reason in ('unsupported_action', 'intent_unsupported_action'):
                reply = ('这里可以查找已有照片和视频。请把修改、分享或拍摄请求分开处理。' if lang == 'zh' else
                         'This search finds existing photos and videos. Handle changes, sharing or capture separately.')
            elif 'people' not in enabled:
                reply += (' 当前相册库尚未启用人物检索；未识别的条件不会被忽略。' if lang == 'zh' else
                          ' People search is not enabled in this library. Unmatched details were not ignored.')
            return {'version': 1, 'kind': 'unsupported' if plan.status == 'unsupported' else 'clarification', 'reply': reply,
                    'context': previous, 'filters': previous['filters'] if previous else None,
                    'items': existing['items'] if existing else [], 'total': existing['total'] if existing else 0,
                    'has_more': existing['has_more'] if existing else False, 'effect': None}
        return _search_reply(engine, token, library, binding, plan.filters, source, lang)
    filters = dict(previous['filters']) if refine else {}
    if re.search(r'视频|影片|videos?\b|movies?\b', condition_lower):
        filters['media'] = ['video']
    elif re.search(r'照片|图片|相片|photos?\b|pictures?\b|images?\b', condition_lower):
        filters['media'] = ['image']
    dated = _date_filter(condition_words, now)
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
    ambiguous = False
    if 'people' in enabled:
        people, hits = _matches(words, _facets(engine, token, library, 'people', binding))
        labels.extend(hits)
        if people:
            connective_words = d.fold(condition_words)
            for label in hits:
                connective_words = connective_words.replace(d.fold(label), ' ')
            together = bool(re.search(r'一起|同时|\bboth\b|\btogether\b', connective_words))
            conjunction = bool(re.search(r'和|与|及|\band\b', connective_words))
            mode = 'all' if together or conjunction else 'any'
            filters['people'] = {'ids': people, 'match': mode}
            if len(people) >= 2:
                labels.extend(['同时出现', '一起出现', '一起', '同时', '和', '与', '及', '或者', '或',
                               'both', 'together', 'and', 'or'])
            elif together:
                ambiguous = True
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
    if ambiguous or _unmatched(words, labels):
        reply = ('有些条件还无法准确匹配。请使用相册库中已有的人名、标签、地点，或指定年月。'
                 if lang == 'zh' else
                 'Some details could not be matched. Try a library person, label, place, or month.')
        missing = [field for field in ('people', 'caption', 'tags') if field not in enabled
                   and not (field == 'caption' and 'text' in enabled)]
        if ambiguous:
            reply = ('有些姓名或条件有歧义。请补充完整姓名，并明确哪些人需要同时出现。'
                     if lang == 'zh' else
                     'Some names or conditions are ambiguous. Use full reviewed names and specify who must appear together.')
        elif missing:
            names = ({'people': '人物', 'caption': '照片说明', 'tags': '标签'} if lang == 'zh' else
                     {'people': 'people', 'caption': 'captions', 'tags': 'tags'})
            unavailable = ('、' if lang == 'zh' else ', ').join(names[field] for field in missing)
            reply = (f'有些条件还无法准确匹配。当前相册库尚未启用{unavailable}检索。'
                     '可以先按已登记地点或年月查找；未识别的条件不会被忽略。' if lang == 'zh' else
                     f'Some details could not be matched. Search for {unavailable} is not enabled '
                     'in this library. Try a recorded place or month. Unmatched details were not ignored.')
        return {'version': 1, 'kind': 'clarification', 'reply': reply,
                'context': previous, 'filters': previous['filters'] if previous else None,
                'items': existing['items'] if existing else [], 'total': existing['total'] if existing else 0,
                'has_more': existing['has_more'] if existing else False, 'effect': None}
    return _search_reply(engine, token, library, binding, filters, source, lang)


def _search_reply(engine, token, library, binding, filters, source, lang):
    result = _search(engine, token, library, binding, filters)
    source.clear()
    source.update(result)
    context = {'library_id': library, 'binding': result['binding'],
               'fingerprint': result['fingerprint'], 'filters': filters,
               'visible_ids': [item['id'] for item in result['items']], 'total': result['total']}
    reply = _result_overview(result, lang)
    from .assistant_search import SearchRuntime
    if result['total'] == 0 and isinstance(engine, SearchRuntime):
        from .search_explanation import no_results_guidance
        reply = no_results_guidance(filters, lang)
    elif result['total'] == 0 and 'date' in filters:
        reply = ('没有找到符合条件且已记录拍摄日期的照片或视频。未记录拍摄日期的素材'
                 '不包含在日期搜索中；可以先只按照片或视频查找。' if lang == 'zh' else
                 'No matching photos or videos with a recorded capture date were found. '
                 'Items without a capture date are excluded from date searches. '
                 'Try searching by media type without a date.')
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
    result = {'version': 1, 'enabled': engine is not None, 'text': engine is not None,
            'transcribe': transcribe, 'speech': engine is not None and isinstance(tts, LocalAssistantTts),
            'max_audio_seconds': MAX_AUDIO_SECONDS if transcribe else 0}
    version = _single(request, 'x-photohouse-search-version')
    if version in ('2', '3'):
        result.update(version=int(version), search={'version': int(version), 'text_sources': ['current_caption', 'photo_memory'],
                                      'date_basis': 'capture',
                                      'ranking': ('authored_then_descriptive_and_literal_quality_then_asset_id'
                                                  if version == '3' else
                                                  'authored_then_literal_quality_then_asset_id')})
    return result


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
    if _single(request, 'x-photohouse-search-version') in ('2', '3'):
        result['version'] = int(_single(request, 'x-photohouse-search-version'))
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
    result = await run_in_threadpool(_context_result, engine, token, library, context)
    language = payload['language']
    words = _result_overview(result, language)
    await _stage(request, 'validated')
    await _stage(request, 'provider_started')
    audio = await run_in_threadpool(tts.synthesize, words, language)
    await run_in_threadpool(engine.authorize, token, library)
    await run_in_threadpool(_context_result, engine, token, library, context)
    await _stage(request, 'provider_completed')
    return Response(content=audio, media_type='audio/wav', headers=_playback_headers(request))


def _playback_headers(request):
    return {'X-PhotoHouse-Playback-Tracking': 'enabled'} if getattr(
        request.state, 'assistant_request_id', None) is not None else {}


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


@router.post('/assistant/v1/receipts/{ident}/playback')
async def receipt_playback(request: Request, ident: str):
    token, _ = credentials_from_request(request)
    payload = await _body(request, frozenset({'library_id', 'outcome'}),
                          outcome_values=('completed', 'failed', 'cancelled'))
    outcome = payload['outcome']
    library = payload['library_id']
    journal, identity = await _receipt_author(request, token, library, ident)
    return await run_in_threadpool(journal.playback, ident, identity, library, outcome)

"""Read-only, library-scoped evidence for an ephemeral multi-media story draft.

This route does not save, publish, invoke inference or change the photo catalog.
Family words and machine observations remain separate from the editable outline.
"""
import hashlib
import json
import re
from datetime import date, datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, HINT_FIELDS, SOURCE, _asset, _integer, _query
from .service import AccessDenied, AccessService
from .story_outline import build_outline
from .transport import TransportError, _body, _runtime, credentials_from_request

router = APIRouter(route_class=LibraryRoute)
FIELDS = {'asset_ids', 'theme', 'language', 'title'}
MAX_ITEMS = 24
MAX_RESPONSE = 256 * 1024
RELATED_PAGE_SIZE = 20
RELATED_SCAN_SIZE = 80
_CAPTURE_DATE = re.compile(r'\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z', re.ASCII)
_CAPTURE_DATETIME = re.compile(
    r'\A[0-9]{4}-[0-9]{2}-[0-9]{2}[T ][0-9]{2}:[0-9]{2}'
    r'(?::[0-9]{2}(?:\.[0-9]{1,6})?)?'
    r'(?:Z|[+-][0-9]{2}:?[0-9]{2})?\Z', re.ASCII)


def _text(value, limit=1800):
    return (value or '').encode('utf-8')[:limit].decode('utf-8', errors='ignore')


def _selection(body):
    raw = body['asset_ids'].split(',')
    if not 1 <= len(raw) <= MAX_ITEMS or len(set(raw)) != len(raw):
        raise TransportError(400, 'Select between one and 24 distinct items')
    ids = [_integer(value, 2**63-1) for value in raw]
    # Canonical IDs also prevent aliases such as 101 and 0101 from duplicating media.
    if any(str(ident) != value for ident, value in zip(ids, raw)):
        raise TransportError(400, 'Invalid selection')
    if body['language'] not in {'zh', 'en'} or body['theme'] not in {
            'trip', 'growing_up', 'birthday', 'grandparents', 'year_in_review', 'everyday'}:
        raise TransportError(400, 'Invalid story theme or language')
    if len(body['title']) > 160 or any(ord(c) < 32 for c in body['title']):
        raise TransportError(400, 'Invalid title')
    return ids


def _recorded_capture_day(value):
    """Validate recorded capture metadata and preserve its written calendar day.

    Date hints are intentionally not inputs here. Offset timestamps are not
    converted to UTC: this feature groups by the day PhotoHouse recorded.
    """
    if not isinstance(value, str):
        return None
    try:
        if _CAPTURE_DATE.fullmatch(value):
            return date.fromisoformat(value).isoformat()
        if _CAPTURE_DATETIME.fullmatch(value):
            parsed = datetime.fromisoformat(value[:-1] + '+00:00' if value.endswith('Z') else value)
            return parsed.date().isoformat()
    except (ValueError, OverflowError):
        return None
    return None


def _related_selection(body):
    raw = body['asset_ids'].split(',')
    if not 1 <= len(raw) <= MAX_ITEMS or len(set(raw)) != len(raw):
        raise TransportError(400, 'Select between one and 24 distinct items')
    ids = [_integer(value, 2**63 - 1) for value in raw]
    if any(str(ident) != value for ident, value in zip(ids, raw)):
        raise TransportError(400, 'Invalid selection')
    before = body['before_id']
    if before:
        ident = _integer(before, 2**63 - 1)
        if str(ident) != before:
            raise TransportError(400, 'Invalid cursor')
        before_id = ident
    else:
        before_id = None
    return ids, before_id


def related_media(runtime, token, library, body):
    """Suggest a bounded page sharing a selected asset's recorded capture day."""
    seed_ids, before_id = _related_selection(body)
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        with access._transaction():
            access._require(token, library, 'library.read')

            # Resolve the complete seed set before deriving or returning any
            # candidate metadata. A missing, inactive, foreign, or unmapped
            # seed denies the whole request.
            seed_rows = []
            for ident in seed_ids:
                row = db.execute('''SELECT a.id,a.mime,a.taken_at FROM assets a
                    JOIN access_asset_libraries scope ON scope.asset_id=a.id
                    WHERE scope.library_id=? AND a.id=?
                      AND (a.status IS NULL OR a.status='active')''',
                    (library, ident)).fetchone()
                if row is None:
                    raise AccessDenied('Access denied')
                seed_rows.append(row)

            seeds = []
            for row in seed_rows:
                kind = 'video' if (row[1] or '').startswith('video/') else \
                    'image' if (row[1] or '').startswith('image/') else 'other'
                if kind not in {'image', 'video'}:
                    raise TransportError(400, 'Select photos or videos')
                seeds.append((int(row[0]), _recorded_capture_day(row[2])))

            days = sorted({day for _, day in seeds if day is not None})
            result = {'version': 1, 'library_id': library,
                      'seed_asset_ids': [str(ident) for ident in seed_ids],
                      'recorded_days': days, 'needs_review': True,
                      'has_more': False, 'next_before_id': None, 'items': []}
            if not days:
                return result

            excluded = ','.join('?' for _ in seed_ids)
            day_predicate = ' OR '.join('a.taken_at LIKE ?' for _ in days)
            sql = '''SELECT a.id,a.mime,a.width,a.height,a.duration_sec,a.taken_at''' + SOURCE + '''
                AND (a.mime GLOB 'image/*' OR a.mime GLOB 'video/*')
                AND a.id NOT IN (''' + excluded + ''')
                AND (''' + day_predicate + ''')'''
            args = [library, *seed_ids, *(day + '%' for day in days)]
            if before_id is not None:
                sql += ' AND a.id<?'
                args.append(before_id)
            sql += ' ORDER BY a.id DESC LIMIT ?'
            args.append(RELATED_SCAN_SIZE + 1)
            rows = db.execute(sql, tuple(args)).fetchall()

            last_inspected = None
            inspected = 0
            for row in rows[:RELATED_SCAN_SIZE]:
                inspected += 1
                last_inspected = int(row[0])
                candidate_day = _recorded_capture_day(row[5])
                if candidate_day not in days:
                    continue
                item = _asset(row, library)
                item['match_reason'] = 'same_recorded_capture_day'
                result['items'].append(item)
                if len(result['items']) == RELATED_PAGE_SIZE:
                    break

            # The scan cursor advances over invalid timestamps too. One
            # uninspected row proves that another bounded request can continue.
            result['has_more'] = inspected < len(rows)
            if result['has_more'] and last_inspected is not None:
                result['next_before_id'] = str(last_inspected)

            response = JSONResponse(result)
            if len(response.body) > MAX_RESPONSE:
                raise TransportError(503, 'Related media unavailable')
            return result


def collect_items(db, library, ids):
    items = []
    for ident in ids:
        row = db.execute('SELECT ' + HINT_FIELDS + SOURCE + ' AND a.id=?',
                         (library, ident)).fetchone()
        if row is None:
            raise AccessDenied('Access denied')
        item = _asset(row, library, hints=True)
        if item['kind'] not in {'image', 'video'}:
            raise TransportError(400, 'Select photos or videos')
        evidence = []
        # Children and parents share the same authorization snapshot. Each
        # source is bounded and current; revisions/history never enter drafts.
        for story in db.execute('''SELECT id,substr(title,1,160),substr(text,1,1800),revision
                FROM access_stories WHERE library_id=? AND asset_id=? AND deleted=0
                ORDER BY updated_at DESC,id LIMIT 2''', (library, ident)):
            evidence.append({'id': 'family-' + story[0], 'source': 'family',
                             'title': _text(story[1], 512), 'text': _text(story[2]),
                             'revision': story[3]})
        for caption in db.execute('''SELECT id,substr(text,1,1800),user_edited
                FROM captions WHERE asset_id=? AND superseded=0
                ORDER BY user_edited DESC,id DESC LIMIT 1''', (ident,)):
            evidence.append({'id': 'caption-' + str(caption[0]),
                             'source': 'family' if caption[2] else 'ai',
                             'title': '', 'text': _text(caption[1])})
        item['evidence'] = evidence
        items.append(item)
    return items


def preview(runtime, token, library, body):
    ids = _selection(body)
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        with access._transaction():
            access._require(token, library, 'library.read')
            items = collect_items(db, library, ids)
            outline_items = [{key: item[key] for key in ('id', 'kind', 'taken_at', 'date_hint')} |
                {'evidence': [{key: e[key] for key in ('id', 'source', 'text')}
                              for e in item['evidence']]} for item in items]
            outline = build_outline(outline_items, theme=body['theme'], language=body['language'],
                                    title=body['title'])
            revision = hashlib.sha256(json.dumps([library, items], sort_keys=True,
                ensure_ascii=True, allow_nan=False).encode()).hexdigest()
            result = {'version': 1, 'library_id': library, 'selection_revision': revision,
                      'state': 'draft', 'saved': False, 'items': items, **outline}
            response = JSONResponse(result)
            if len(response.body) > MAX_RESPONSE:
                raise TransportError(503, 'Story evidence unavailable')
            return result


@router.post('/story-workspace/preview')
async def story_preview(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, FIELDS, max_body=4096)
    result = await run_in_threadpool(preview, _runtime(request, allow_query=True),
                                     token, query['library'], body)
    return JSONResponse(result)


@router.post('/story-workspace/related-media')
async def story_related_media(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'asset_ids', 'before_id'}, max_body=4096)
    result = await run_in_threadpool(related_media, _runtime(request, allow_query=True),
                                     token, query['library'], body)
    return JSONResponse(result)


def title_capabilities(runtime, token, library, enabled):
    with runtime.connection_factory() as db:
        access = AccessService(db, clock=runtime.clock)
        with access._transaction():
            access._require(token, library, 'library.read')
    return {'version': 1, 'enabled': enabled, 'max_suggestions': 3,
            'needs_review': True}


def title_suggestions(runtime, token, library, body, adapter, lock):
    # Authorize every selected frame before passing any context to inference.
    outline_body = {key: body[key] for key in ('asset_ids', 'theme', 'language')} | {'title': ''}
    snapshot = preview(runtime, token, library, outline_body)
    if not re.fullmatch(r'[0-9a-f]{64}', body['selection_revision']) or body['selection_revision'] != snapshot['selection_revision']:
        raise TransportError(409, 'Story references changed')
    try:
        from .memory_narrative import _strict_loads, LocalMemoryNarrativeError
        chapters = _strict_loads(body['chapters'].encode('utf-8'))
        if type(chapters) is not list or len(chapters) != len(snapshot['chapters']):
            raise ValueError()
        for expected, chapter in zip(snapshot['chapters'], chapters):
            if (type(chapter) is not dict or set(chapter) != {'id', 'narration'} or
                    chapter['id'] != expected['id'] or type(chapter['narration']) is not str or
                    len(chapter['narration'].encode('utf-8')) > 6000 or
                    any((ord(c) < 32 or 0x7f <= ord(c) <= 0x9f) and c not in '\n\t' for c in chapter['narration'])):
                raise ValueError()
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportError(400, 'Invalid title context') from None
    if adapter is None:
        raise TransportError(503, 'Title suggestions unavailable')
    from .story_titles import validate_bundle, validate_suggestions
    sources = [{'id': e['id'], 'source': e['source'], 'text': e['text']}
               for item in snapshot['items'] for e in item['evidence'] if e['text'].strip()]
    sources.extend({'id': 'draft-' + chapter['id'], 'source': 'draft',
                    'text': _text(chapter['narration'], 1800)}
                   for chapter in chapters if chapter['narration'].strip())
    try:
        bundle = validate_bundle({'version': 1, 'language': body['language'], 'theme': body['theme'],
            'selection_revision': snapshot['selection_revision'], 'sources': sources})
    except ValueError:
        raise TransportError(400, 'Title context exceeds its limit') from None
    if not lock.acquire(blocking=False):
        raise TransportError(503, 'Title suggestions busy')
    try:
        try:
            result = validate_suggestions(adapter.suggest(bundle), bundle)
        except (LocalMemoryNarrativeError, ValueError, TypeError, UnicodeError, RecursionError):
            raise TransportError(503, 'Title suggestions unavailable') from None
        # Inference holds no SQLite transaction. Recheck membership, sources,
        # deletion and media mappings before returning a proposal.
        latest = preview(runtime, token, library, outline_body)
        if latest['selection_revision'] != snapshot['selection_revision']:
            raise TransportError(409, 'Story references changed')
        return result
    finally:
        lock.release()


@router.get('/story-workspace/title-capabilities')
async def story_title_capabilities(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    return JSONResponse(await run_in_threadpool(title_capabilities,
        _runtime(request, allow_query=True), token, query['library'],
        request.app.state.story_title_suggester is not None))


@router.post('/story-workspace/title-suggestions')
async def story_title_suggestions(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'asset_ids', 'theme', 'language', 'selection_revision', 'chapters'}, max_body=65536)
    return JSONResponse(await run_in_threadpool(title_suggestions,
        _runtime(request, allow_query=True), token, query['library'], body,
        request.app.state.story_title_suggester, request.app.state.story_title_lock))

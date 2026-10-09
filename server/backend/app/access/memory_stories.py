"""Saved multi-asset drafts. Every read/write reauthorizes the entire selection.

Only editorial text/order is stored. Source words and media are hydrated from
current authorized records; originals, inference and public TV feeds are untouched.
"""
import hashlib
import json
import re
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _integer, _query
from .service import AccessService, AccessDenied
from .stories import _uuid
from .story_workspace import collect_items, _selection, MAX_RESPONSE
from .story_outline import THEMES, build_outline
from .transport import TransportError, _body, _runtime, credentials_from_request
from .memory_source_refs import (current_groups, parse_groups, replace_groups,
    available as source_refs_available, validate_groups)

router = APIRouter(route_class=LibraryRoute)
FIELDS = {'title', 'theme', 'language', 'asset_ids', 'chapters',
          'selection_revision', 'revision', 'mutation_id'}
PAGE_SIZE = 8


def snapshot(library, items):
    return hashlib.sha256(json.dumps([library, items], sort_keys=True,
        ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def evidence_digest(evidence):
    return hashlib.sha256(json.dumps(evidence, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate field')
            result[key] = value
        return result
    def invalid_constant(_):
        raise ValueError('Invalid number')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


def content(body):
    ids = _selection(body)
    if not body['title'].strip():
        raise TransportError(422, 'Give this story a title')
    if not re.fullmatch('[0-9a-f]{64}', body['selection_revision']):
        raise TransportError(400, 'Invalid selection revision')
    try:
        chapters = _json(body['chapters'])
        if not isinstance(chapters, list) or not 1 <= len(chapters) <= 6:
            raise ValueError()
        flattened = []
        for index, chapter in enumerate(chapters):
            if not isinstance(chapter, dict) or set(chapter) != {'id', 'title', 'narration', 'asset_ids', 'evidence_ids'}:
                raise ValueError()
            if chapter['id'] != f'chapter-{index+1}':
                raise ValueError()
            for key, limit in (('title', 640), ('narration', 6000)):
                value = chapter[key]
                if not isinstance(value, str) or len(value.encode('utf-8')) > limit or any(
                        0xD800 <= ord(c) <= 0xDFFF or (ord(c) < 32 and (key != 'narration' or c not in '\n\t')) for c in value):
                    raise ValueError()
            if len(chapter['title']) > 160 or not chapter['title'].strip():
                raise ValueError()
            selected = chapter['asset_ids']
            refs = chapter['evidence_ids']
            if not isinstance(selected, list) or not 1 <= len(selected) <= 4:
                raise ValueError()
            if any(not isinstance(value, str) for value in selected):
                raise ValueError()
            if not isinstance(refs, list) or len(refs) > 12 or any(
                    not isinstance(value, str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,127}', value) for value in refs):
                raise ValueError()
            if len(set(refs)) != len(refs):
                raise ValueError()
            flattened.extend(selected)
        if flattened != [str(ident) for ident in ids]:
            raise ValueError()
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportError(422, 'Invalid story chapters; nothing was saved') from None
    return {key: body[key] for key in ('title', 'theme', 'language')} | {
        'asset_ids': [str(ident) for ident in ids], 'chapters': chapters}


class MemoryStories:
    def __init__(self, access):
        self.access, self.db = access, access.db

    def _ready(self):
        tables = {r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'access_memory_stories', 'access_memory_revisions'} <= tables:
            raise TransportError(503, 'Saved stories unavailable')

    def _row(self, ident, library):
        row = self.access._one('SELECT * FROM access_memory_stories WHERE id=? AND library_id=?', (ident, library))
        if row is None:
            raise AccessDenied('Access denied')
        return row

    @staticmethod
    def _can_edit(member, row):
        return member['role'] == 'owner' or (member['role'] == 'contributor' and row['author_id'] == member['account_id'])

    def _read(self, row, library, member):
        stored = _json(row['content'])
        items = collect_items(self.db, library, [int(ident) for ident in stored['asset_ids']])
        # Only current evidence references are returned. Old copies of private
        # source words are never retained in a saved draft or revision payload.
        chapters = []
        for chapter in stored['chapters']:
            current = {e['id'] for i in items if i['id'] in chapter['asset_ids'] for e in i['evidence']
                       if stored.get('evidence_versions', {}).get(e['id']) == evidence_digest(e)}
            chapters.append(chapter | {'evidence_ids': [ref for ref in chapter['evidence_ids'] if ref in current]})
        questions = build_outline([], theme=stored['theme'], language=stored['language'])['questions']
        return {**stored, 'version': 1, 'library_id': library, 'id': row['id'],
            'revision': str(row['revision']), 'created_at': row['created_at'], 'updated_at': row['updated_at'],
            'can_edit': self._can_edit(member, row), 'saved': True, 'state': 'draft',
            'generator': 'family_edited_outline', 'needs_review': True,
            'selection_revision': snapshot(library, items), 'items': items,
            'chapters': chapters, 'questions': questions}  # asset_ids removed below

    def _present(self, row, library, member):
        result = self._read(row, library, member)
        result.pop('asset_ids')
        result.pop('evidence_versions', None)
        if len(JSONResponse(result).body) > MAX_RESPONSE:
            raise TransportError(503, 'Story response unavailable')
        return result

    def list(self, token, library, page, theme=None):
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            self._ready()
            if theme is not None and (not isinstance(theme, str) or theme not in THEMES):
                raise TransportError(400, 'Invalid story theme')
            # Filter unavailable parents before pagination. Neither their IDs,
            # story text, counts nor title may escape after media moves/deletion.
            rows = self.db.execute('''SELECT s.* FROM access_memory_stories s
                WHERE library_id=? AND (? IS NULL OR json_extract(s.content,'$.theme')=?) AND NOT EXISTS (
                    SELECT 1 FROM json_each(s.content,'$.asset_ids') j
                    WHERE NOT EXISTS (SELECT 1 FROM assets a JOIN access_asset_libraries l ON l.asset_id=a.id
                        WHERE a.id=CAST(j.value AS INTEGER) AND l.library_id=s.library_id
                        AND (a.status IS NULL OR a.status='active')))
                ORDER BY s.updated_at DESC,s.id DESC LIMIT ? OFFSET ?''',
                (library, theme, theme, PAGE_SIZE+1, (page-1)*PAGE_SIZE))
            rows = [dict(zip((c[0] for c in rows.description), r)) for r in rows]
            summaries = []
            for row in rows[:PAGE_SIZE]:
                stored = _json(row['content'])
                summaries.append({key: stored[key] for key in ('title', 'theme', 'language')} | {
                    'id': row['id'], 'revision': str(row['revision']),
                    'cover_asset_id': stored['asset_ids'][0], 'item_count': len(stored['asset_ids']),
                    'chapter_count': len(stored['chapters']), 'updated_at': row['updated_at'],
                    'can_edit': self._can_edit(member, row)})
            return {'library_id': library, 'page': page, 'page_size': PAGE_SIZE,
                'has_more': len(rows) > PAGE_SIZE, 'can_create': member['role'] in {'owner', 'contributor'},
                'items': summaries}

    def get(self, token, library, ident):
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            self._ready()
            return self._present(self._row(ident, library), library, member)

    def contribution_refs(self, token, library, ident, revision):
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            self._ready()
            if not source_refs_available(self.db):
                raise TransportError(503, 'Contribution references unavailable')
            row = self._row(ident, library)
            # Hydrate the complete selected media set before returning any child
            # reference. This follows the same authorization boundary as story GET.
            self._present(row, library, member)
            if row['revision'] != revision:
                raise TransportError(409, 'Story revision changed; reload before reading references')
            stored = _json(row['content'])
            chapter_ids = [chapter['id'] for chapter in stored['chapters']]
            groups = dict(current_groups(self.db, row['id'], revision, chapter_ids, library))
            return {'version': 1, 'id': row['id'], 'library_id': library,
                'revision': str(revision), 'chapters': [
                    {'id': chapter, 'contribution_ids': groups.get(chapter, [])}
                    for chapter in chapter_ids]}

    def save(self, token, library, body, ident=None, refs_enabled=False):
        stored = content(body)
        supplied_groups = None
        if refs_enabled:
            supplied_groups = parse_groups(body['contribution_refs'],
                                            [chapter['id'] for chapter in stored['chapters']])
            if ident is None and any(refs for _chapter, refs in supplied_groups):
                raise TransportError(422, 'New stories cannot inherit contribution references')
        mutation = _uuid(body['mutation_id'])
        revision = _integer(body['revision'], 2**63-2) if ident else 0
        if ident is None and body['revision'] != '0':
            raise TransportError(400, 'Invalid revision')
        digest = hashlib.sha256(json.dumps([library, ident, body], sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        with self.access._transaction(write=True):
            member = self.access._require(token, library, 'story.write')
            self._ready()
            refs_ready = source_refs_available(self.db) if refs_enabled else False
            if refs_enabled and not refs_ready:
                raise TransportError(503, 'Contribution references unavailable')
            row = self._row(ident, library) if ident else None
            if row is not None and not refs_enabled:
                refs_ready = source_refs_available(self.db)
            if row and not self._can_edit(member, row):
                raise AccessDenied('Access denied')
            actor = member['account_id']
            prior = self.access._one('SELECT * FROM access_memory_revisions WHERE editor_id=? AND mutation_id=?', (actor, mutation))
            if prior:
                if prior['request_digest'] != digest:
                    raise TransportError(409, 'Save identifier already used; keep your draft')
                return self._present(self._row(prior['story_id'], library), library, member)
            items = collect_items(self.db, library, [int(value) for value in stored['asset_ids']])
            if snapshot(library, items) != body['selection_revision'] or (row and row['revision'] != revision):
                raise TransportError(409, 'Story or references changed; keep your draft and reload before saving')
            for chapter in stored['chapters']:
                refs = {e['id'] for item in items if item['id'] in chapter['asset_ids'] for e in item['evidence']}
                if any(ref not in refs for ref in chapter['evidence_ids']):
                    raise TransportError(422, 'Invalid source reference')
            if refs_enabled and row is not None:
                validate_groups(self.db, supplied_groups, ident, library)
            elif refs_enabled and supplied_groups:
                # Empty groups are valid during creation; non-empty groups were
                # rejected above because there is no prior saved story to cite.
                supplied_groups = []
            stored['evidence_versions'] = {e['id']: evidence_digest(e) for item in items for e in item['evidence']}
            ident = ident or str(uuid.uuid4())
            now = self.access._now()
            raw = json.dumps(stored, ensure_ascii=True, sort_keys=True)
            revision_new = revision + 1
            if refs_enabled:
                groups_to_save = supplied_groups
            elif row is not None and refs_ready:
                old_content = _json(row['content'])
                old_chapters = {chapter['id']: chapter for chapter in old_content['chapters']}
                new_chapters = {chapter['id']: chapter for chapter in stored['chapters']}
                unchanged = {chapter_id for chapter_id, chapter in new_chapters.items()
                    if chapter_id in old_chapters
                    and chapter['narration'] == old_chapters[chapter_id]['narration']
                    and chapter['asset_ids'] == old_chapters[chapter_id]['asset_ids']}
                groups_to_save = [(chapter, refs) for chapter, refs in
                    current_groups(self.db, ident, revision, list(old_chapters), library)
                    if chapter in unchanged and chapter in new_chapters]
            else:
                groups_to_save = []
            if row:
                self.db.execute('UPDATE access_memory_stories SET content=?,revision=?,updated_at=? WHERE id=?',
                    (raw, revision+1, now, ident))
            else:
                self.db.execute('''INSERT INTO access_memory_stories
                    (id,library_id,author_id,revision,content,created_at,updated_at) VALUES (?,?,?,1,?,?,?)''',
                    (ident, library, actor, raw, now, now))
            self.db.execute('''INSERT INTO access_memory_revisions
                (story_id,revision,editor_id,mutation_id,request_digest,content,occurred_at) VALUES (?,?,?,?,?,?,?)''',
                (ident, revision_new, actor, mutation, digest, raw, now))
            if refs_ready and groups_to_save:
                replace_groups(self.db, ident, revision_new, groups_to_save)
            self.access._audit(actor, 'memory.create' if row is None else 'memory.edit', library)
            return self._present(self._row(ident, library), library, member)


def call(runtime, action, *args):
    with runtime.connection_factory() as db:
        return getattr(MemoryStories(AccessService(db, clock=runtime.clock)), action)(*args)


@router.get('/memory-stories')
async def list_memories(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page', 'theme'})
    result = await run_in_threadpool(call, _runtime(request, allow_query=True), 'list', token,
                                    query['library'], _integer(query.get('page', '1'), 100000), query.get('theme'))
    return JSONResponse(result)


@router.get('/memory-stories/{story_id}')
async def get_memory(story_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    result = await run_in_threadpool(call, _runtime(request, allow_query=True), 'get', token, query['library'], _uuid(story_id))
    return JSONResponse(result)


@router.get('/memory-stories/{story_id}/contribution-refs')
async def get_contribution_refs(story_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'revision'})
    revision = _integer(query.get('revision', ''), 2**63-1)
    result = await run_in_threadpool(call, _runtime(request, allow_query=True),
        'contribution_refs', token, query['library'], _uuid(story_id), revision)
    return JSONResponse(result)


@router.post('/memory-stories')
async def create_memory(request: Request):
    return await save_memory(request)


@router.put('/memory-stories/{story_id}')
async def edit_memory(story_id: str, request: Request):
    return await save_memory(request, _uuid(story_id))


async def save_memory(request, ident=None):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'contribution_refs'})
    refs_enabled = query.get('contribution_refs') == '1'
    if 'contribution_refs' in query and not refs_enabled:
        raise TransportError(400, 'Invalid request')
    fields = FIELDS | ({'contribution_refs'} if refs_enabled else set())
    body = await _body(request, fields, max_body=384*1024)
    result = await run_in_threadpool(call, _runtime(request, allow_query=True), 'save', token,
        query['library'], body, ident, refs_enabled)
    return JSONResponse(result)

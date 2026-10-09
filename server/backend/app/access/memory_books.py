"""Private memoirs composed from currently readable saved memory stories."""
import hashlib
import json
import uuid

from fastapi.responses import JSONResponse

from .library import _integer
from .memory_stories import MemoryStories
from .service import AccessDenied
from .stories import _uuid
from .transport import TransportError

FIELDS = {'title', 'language', 'introduction', 'story_ids', 'revision', 'mutation_id'}
MAX_BODY_BYTES = 8192
MAX_RESPONSE_BYTES = 512 * 1024
MAX_STORIES = 24
MAX_TITLE_BYTES = 512
MAX_INTRODUCTION_BYTES = 6000
PAGE_SIZE = 8
BOOK_CONTENT_KEYS = {'title', 'language', 'introduction', 'kind', 'story_ids'}


def _body(body):
    if type(body) is not dict or set(body) != FIELDS or any(type(value) is not str for value in body.values()):
        raise TransportError(400, 'Invalid memoir request')
    try:
        size = sum(len(value.encode('utf-8')) for value in body.values())
    except UnicodeError:
        raise TransportError(400, 'Invalid memoir request') from None
    if size > MAX_BODY_BYTES:
        raise TransportError(413, 'Memoir request too large')
    title, introduction = body['title'], body['introduction']
    if (not title.strip() or len(title.encode('utf-8')) > MAX_TITLE_BYTES
            or '\x00' in title):
        raise TransportError(422, 'Invalid memoir title')
    if (len(introduction.encode('utf-8')) > MAX_INTRODUCTION_BYTES
            or '\x00' in introduction):
        raise TransportError(422, 'Memoir introduction too large or invalid')
    if body['language'] not in {'zh', 'en'}:
        raise TransportError(422, 'Unsupported memoir language')
    parts = body['story_ids'].split(',')
    if not 1 <= len(parts) <= MAX_STORIES or len(set(parts)) != len(parts):
        raise TransportError(422, 'Select one to 24 distinct saved stories')
    try:
        story_ids = [_uuid(value) for value in parts]
        mutation_id = _uuid(body['mutation_id'])
    except (TypeError, AttributeError):
        raise TransportError(400, 'Invalid memoir identifier') from None
    if body['revision'] == '0':
        revision = 0
    else:
        revision = _integer(body['revision'], 2**63 - 2)
    return {
        'title': title,
        'language': body['language'],
        'introduction': introduction,
        'kind': 'memoir',
        'story_ids': story_ids,
    }, revision, mutation_id


def _stored(raw):
    try:
        value = json.loads(raw)
        if (type(value) is not dict or set(value) != BOOK_CONTENT_KEYS
                or value['kind'] != 'memoir' or type(value['story_ids']) is not list
                or not 1 <= len(value['story_ids']) <= MAX_STORIES
                or any(type(item) is not str for item in value['story_ids'])
                or len(set(value['story_ids'])) != len(value['story_ids'])):
            raise ValueError()
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportError(503, 'Memoir unavailable') from None


class MemoryBooks:
    """Domain operations for e7 books; HTTP routing remains with integration."""

    def __init__(self, access):
        self.access = access
        self.db = access.db
        self.stories = MemoryStories(access)

    def _ready(self):
        tables = {row[0] for row in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'access_memory_books', 'access_memory_book_revisions'} <= tables:
            raise TransportError(503, 'Memory books unavailable')

    def _row(self, ident, library):
        row = self.access._one(
            'SELECT * FROM access_memory_books WHERE id=? AND library_id=?',
            (ident, library))
        if row is None:
            raise AccessDenied('Access denied')
        return row

    @staticmethod
    def _can_edit(member, row):
        return (member['role'] == 'owner'
                or (member['role'] == 'contributor'
                    and row['author_id'] == member['account_id']))

    def _stories(self, content, library, member):
        result = []
        for ident in content['story_ids']:
            row = self.stories._row(ident, library)
            detail = self.stories._read(row, library, member)
            result.append({
                'id': ident,
                'title': detail['title'],
                'revision': detail['revision'],
                'item_count': len(detail['items']),
                'cover_asset_id': detail['items'][0]['id'],
            })
        return result

    def _present(self, row, library, member):
        content = _stored(row['content'])
        result = {
            'version': 1,
            'type': 'memoir',
            'id': row['id'],
            'revision': str(row['revision']),
            'can_edit': self._can_edit(member, row),
            'title': content['title'],
            'introduction': content['introduction'],
            'language': content['language'],
            'stories': self._stories(content, library, member),
        }
        if len(JSONResponse(result).body) > MAX_RESPONSE_BYTES:
            raise TransportError(503, 'Memoir response unavailable')
        return result

    def _available_rows(self, library, page):
        # Filter missing/moved/deleted story media before pagination. The domain
        # hydration below rechecks each child through MemoryStories._row/_read.
        return self.db.execute('''WITH available_story AS (
                SELECT s.id,s.library_id FROM access_memory_stories s
                WHERE json_valid(s.content)
                  AND json_type(s.content,'$.asset_ids')='array'
                  AND json_array_length(s.content,'$.asset_ids') BETWEEN 1 AND 24
                  AND NOT EXISTS (
                    SELECT 1 FROM json_each(
                        CASE WHEN json_valid(s.content) THEN s.content ELSE '{"asset_ids":[]}' END,
                        '$.asset_ids') media
                    WHERE NOT EXISTS (
                        SELECT 1 FROM assets a
                        JOIN access_asset_libraries l ON l.asset_id=a.id
                        WHERE a.id=CAST(media.value AS INTEGER)
                          AND l.library_id=s.library_id
                          AND (a.status IS NULL OR a.status='active')))
            )
            SELECT b.* FROM access_memory_books b
            WHERE b.library_id=?
              AND json_valid(b.content)
              AND json_type(b.content,'$.story_ids')='array'
              AND json_array_length(b.content,'$.story_ids') BETWEEN 1 AND 24
              AND NOT EXISTS (
                SELECT 1 FROM json_each(
                    CASE WHEN json_valid(b.content) THEN b.content ELSE '{"story_ids":[]}' END,
                    '$.story_ids') ref
                LEFT JOIN available_story s
                  ON s.id=ref.value AND s.library_id=b.library_id
                WHERE s.id IS NULL)
            ORDER BY b.updated_at DESC,b.id DESC LIMIT ? OFFSET ?''',
            (library, PAGE_SIZE + 1, (page - 1) * PAGE_SIZE))

    def list(self, token, library, page):
        if type(page) is not int or not 1 <= page <= 100000:
            raise TransportError(400, 'Invalid page')
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            self._ready()
            cursor = self._available_rows(library, page)
            names = [column[0] for column in cursor.description]
            rows = [dict(zip(names, row)) for row in cursor.fetchall()]
            page_rows = rows[:PAGE_SIZE]
            items = []
            for row in page_rows:
                content = _stored(row['content'])
                summaries = self._stories(content, library, member)
                items.append({
                    'version': 1,
                    'type': 'memoir',
                    'id': row['id'],
                    'revision': str(row['revision']),
                    'can_edit': self._can_edit(member, row),
                    'title': content['title'],
                    'introduction': content['introduction'],
                    'language': content['language'],
                    'stories': summaries,
                })
            result = {
                'version': 1,
                'library_id': library,
                'page': page,
                'page_size': PAGE_SIZE,
                'has_more': len(rows) > PAGE_SIZE,
                'can_create': member['role'] in {'owner', 'contributor'},
                'items': items,
            }
            if len(JSONResponse(result).body) > MAX_RESPONSE_BYTES:
                raise TransportError(503, 'Memoir list unavailable')
            return result

    def get(self, token, library, ident):
        ident = _uuid(ident)
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            self._ready()
            return self._present(self._row(ident, library), library, member)

    def save(self, token, library, body, ident=None):
        content, revision, mutation = _body(body)
        if ident is not None:
            ident = _uuid(ident)
            if revision < 1:
                raise TransportError(400, 'Invalid memoir revision')
        elif revision != 0:
            raise TransportError(400, 'New memoir revision must be zero')
        digest = hashlib.sha256(json.dumps(
            [library, ident, body], sort_keys=True, ensure_ascii=True,
            separators=(',', ':')).encode()).hexdigest()
        with self.access._transaction(write=True):
            member = self.access._require(token, library, 'story.write')
            self._ready()
            row = self._row(ident, library) if ident is not None else None
            if row is not None and not self._can_edit(member, row):
                raise AccessDenied('Access denied')
            actor = member['account_id']
            prior = self.access._one('''SELECT book_id,request_digest
                FROM access_memory_book_revisions
                WHERE editor_id=? AND mutation_id=?''', (actor, mutation))
            if prior is not None:
                if prior['request_digest'] != digest:
                    raise TransportError(409, 'Memoir request identifier already used; keep your draft')
                return self._present(self._row(prior['book_id'], library), library, member)
            # Reauthorize and hydrate the entire selected set before writing.
            self._stories(content, library, member)
            if row is not None and row['revision'] != revision:
                raise TransportError(409, 'Memoir changed; keep your draft and reload')
            next_revision = revision + 1
            now = self.access._now()
            raw = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            book_id = ident or str(uuid.uuid4())
            if row is None:
                self.db.execute('''INSERT INTO access_memory_books
                    (id,library_id,author_id,revision,content,created_at,updated_at)
                    VALUES(?,?,?,1,?,?,?)''', (book_id, library, actor, raw, now, now))
            else:
                self.db.execute('''UPDATE access_memory_books
                    SET revision=?,content=?,updated_at=? WHERE id=?''',
                    (next_revision, raw, now, book_id))
            self.db.execute('''INSERT INTO access_memory_book_revisions
                (book_id,revision,editor_id,mutation_id,request_digest,content,occurred_at)
                VALUES(?,?,?,?,?,?,?)''',
                (book_id, next_revision, actor, mutation, digest, raw, now))
            self.access._audit(actor, 'memory.book_create' if row is None else 'memory.book_edit', library)
            saved = self._row(book_id, library)
            # Use the same current child hydration as a later read; the local
            # summary above deliberately is not copied into book storage.
            return self._present(saved, library, member)

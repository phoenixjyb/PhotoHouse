"""Private family contributions to a saved story, with parent-scoped auth."""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
import io
import wave

from .assistant_speech import valid_wav
from .library import _integer
from .memory_stories import MemoryStories
from .service import AccessDenied
from .stories import _uuid
from .transport import TransportError

PAGE_SIZE = 16
MAX_TEXT_BYTES = 8192
MAX_BYLINE_BYTES = 256
LANGUAGES = {'zh', 'en', 'mixed', 'und'}
STATES = {'accepted', 'declined'}
FIELDS = {'kind', 'text', 'language', 'byline', 'consent', 'chapter_id',
          'revision', 'mutation_id'}


def _canonical_uuid(value):
    try:
        return _uuid(value)
    except (TransportError, TypeError, AttributeError):
        raise TransportError(400, 'Invalid contribution identifier') from None


def _text(value, limit, *, nonblank=False):
    if type(value) is not str:
        raise TransportError(422, 'Invalid contribution text')
    try:
        size = len(value.encode('utf-8', errors='strict'))
    except UnicodeEncodeError:
        raise TransportError(422, 'Invalid contribution text') from None
    if size > limit or any(unicodedata.category(ch) == 'Cc' and ch not in '\n\t'
                           for ch in value):
        raise TransportError(422, 'Invalid contribution text')
    if nonblank and not value.strip():
        raise TransportError(422, 'Contribution text cannot be blank')
    return value


def _body(body, audio):
    if (type(body) is not dict or set(body) != FIELDS
            or any(type(value) is not str for value in body.values())):
        raise TransportError(400, 'Invalid contribution request')
    try:
        if sum(len(value.encode('utf-8', errors='strict')) for value in body.values()) > MAX_TEXT_BYTES + 1024:
            raise TransportError(413, 'Contribution request too large')
    except UnicodeEncodeError:
        raise TransportError(400, 'Invalid contribution request') from None
    kind = body['kind']
    if kind not in {'text', 'audio'}:
        raise TransportError(422, 'Unsupported contribution kind')
    text = _text(body['text'], MAX_TEXT_BYTES, nonblank=(kind == 'text'))
    byline = _text(body['byline'], MAX_BYLINE_BYTES)
    if body['language'] not in LANGUAGES or body['consent'] not in {'0', '1'}:
        raise TransportError(422, 'Invalid contribution options')
    if kind == 'text' and audio is not None:
        raise TransportError(422, 'Text contributions cannot include audio')
    if kind == 'audio':
        if text != '' or not valid_wav(audio):
            raise TransportError(422, 'Unsupported recording')
    chapter_id = body['chapter_id']
    if chapter_id:
        if not isinstance(chapter_id, str) or len(chapter_id) > 32:
            raise TransportError(400, 'Invalid chapter identifier')
        if not chapter_id.startswith('chapter-') or not chapter_id[8:].isascii() or not chapter_id[8:].isdecimal():
            raise TransportError(400, 'Invalid chapter identifier')
        index = int(chapter_id[8:])
        if not 1 <= index <= 6 or chapter_id != f'chapter-{index}':
            raise TransportError(400, 'Invalid chapter identifier')
    revision = body['revision']
    if not revision or not revision.isascii() or not revision.isdecimal() or revision.startswith('0'):
        raise TransportError(400, 'Invalid story revision')
    revision = _integer(revision, 2**63 - 1)
    mutation_id = _canonical_uuid(body['mutation_id'])
    duration_ms = None
    raw = text.encode('utf-8')
    if kind == 'audio':
        raw = audio
        with wave.open(io.BytesIO(audio), 'rb') as wav:
            frames, rate = wav.getnframes(), wav.getframerate()
            duration_ms = max(1, (frames * 1000 + rate - 1) // rate)
    return revision, mutation_id, duration_ms, hashlib.sha256(raw).hexdigest()


class MemoryContributions:
    """Contribution operations; no model/provider work occurs here."""

    def __init__(self, access):
        self.access = access
        self.db = access.db
        self.stories = MemoryStories(access)

    def _ready(self):
        names = {r[0] for r in self.db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        required = {'access_memory_contributions',
                    'access_memory_contribution_derivations',
                    'access_memory_books', 'access_memory_book_revisions',
                    'access_memory_jobs', 'access_memory_turns',
                    'access_memory_conversations'}
        if not required <= names:
            raise TransportError(503, 'Memory contributions unavailable')

    def _parent(self, token, library, story_id):
        member = self.access._require(token, library, 'library.read')
        self._ready()
        story_id = _canonical_uuid(story_id)
        row = self.stories._row(story_id, library)
        # Hydrate the full selected set on every operation. This detects moved,
        # deleted and otherwise unreadable source media before child access.
        detail = self.stories._present(row, library, member)
        return member, row, detail

    @staticmethod
    def _can_review(member, story):
        return (member['role'] == 'owner' or
                (member['role'] == 'contributor' and story['author_id'] == member['account_id']))

    @staticmethod
    def _can_see(member, story, contribution):
        return (MemoryContributions._can_review(member, story) or
                (contribution['author_id'] == member['account_id'] and
                 contribution['state'] in {'pending', 'declined'}) or
                contribution['state'] == 'accepted')

    def _contribution(self, ident, story_id, library, *, include_audio=False):
        columns = '''id,story_id,library_id,author_id,kind,original_text,language,byline,
            sha256,duration_ms,local_processing_consent,chapter_id,base_story_revision,
            state,created_at'''
        if include_audio:
            columns += ',original_audio'
        row = self.access._one(f'''SELECT {columns} FROM access_memory_contributions
            WHERE id=? AND story_id=? AND library_id=?''', (ident, story_id, library))
        if row is None:
            raise AccessDenied('Access denied')
        return row

    @staticmethod
    def _present(row):
        result = {key: row[key] for key in (
            'id', 'story_id', 'author_id', 'kind', 'language', 'byline', 'sha256',
            'duration_ms', 'chapter_id', 'base_story_revision', 'state', 'created_at')}
        result['base_story_revision'] = str(result['base_story_revision'])
        result['text'] = row['original_text'] if row['kind'] == 'text' else None
        result['processing_consent'] = bool(row['local_processing_consent'])
        return result

    def _receipt(self, row, member, story):
        result = self._present(row)
        result['version'] = 1
        result['can_review'] = self._can_review(member, story)
        result['can_delete'] = member['role'] == 'owner'
        return result

    def list(self, token, library, story_id, page):
        if type(page) is not int or not 1 <= page <= 100000:
            raise TransportError(400, 'Invalid page')
        with self.access._transaction():
            member, story, _ = self._parent(token, library, story_id)
            review_all = self._can_review(member, story)
            visibility = '' if review_all else " AND (state='accepted' OR author_id=?)"
            params = (story['id'], library) if review_all else (story['id'], library, member['account_id'])
            cursor = self.db.execute(f'''SELECT id,story_id,library_id,author_id,kind,original_text,
                language,byline,sha256,duration_ms,local_processing_consent,chapter_id,
                base_story_revision,state,created_at FROM access_memory_contributions
                WHERE story_id=? AND library_id=?{visibility}
                ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?''',
                (*params, PAGE_SIZE + 1, (page - 1) * PAGE_SIZE))
            rows = [dict(zip((column[0] for column in cursor.description), raw))
                    for raw in cursor.fetchmany(PAGE_SIZE + 1)]
            items = [self._present(row) for row in rows[:PAGE_SIZE]]
            return {'version': 1, 'story_id': story['id'], 'page': page,
                    'page_size': PAGE_SIZE, 'has_more': len(rows) > PAGE_SIZE,
                    'can_review': review_all, 'can_delete':member['role']=='owner', 'items': items}

    def get(self, token, library, story_id, ident):
        ident = _canonical_uuid(ident)
        with self.access._transaction():
            member, story, _ = self._parent(token, library, story_id)
            row = self._contribution(ident, story['id'], library)
            if not self._can_see(member, story, row):
                raise AccessDenied('Access denied')
            result = self._receipt(row, member, story)
            derivation = self.access._one('''SELECT revision,state,transcript,polished_text,tags,
                error_code,created_at,updated_at FROM access_memory_contribution_derivations
                WHERE contribution_id=? ORDER BY revision DESC LIMIT 1''', (ident,))
            result['derivation'] = self._present_derivation(derivation) if derivation else None
            return result

    @staticmethod
    def _present_derivation(row):
        result = dict(row)
        for field in ('transcript', 'polished_text'):
            value = result[field]
            if value is not None:
                try:
                    if type(value) is not str or len(value.encode('utf-8', 'strict')) > MAX_TEXT_BYTES:
                        raise ValueError()
                    if any(unicodedata.category(ch) == 'Cc' and ch not in '\n\t' for ch in value):
                        raise ValueError()
                except (ValueError, UnicodeError):
                    raise TransportError(503, 'Contribution derivation unavailable') from None
        try:
            if type(result['tags']) is not str or len(result['tags'].encode('utf-8', 'strict')) > MAX_TEXT_BYTES:
                raise ValueError()
            tags = json.loads(result['tags'])
            if type(tags) is not list or len(tags) > 24:
                raise ValueError()
            for tag in tags:
                if type(tag) is not str or len(tag.encode('utf-8', 'strict')) > 256 or not tag.strip():
                    raise ValueError()
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise TransportError(503, 'Contribution derivation unavailable') from None
        result['tags'] = tags
        return result

    def audio(self, token, library, story_id, ident):
        ident = _canonical_uuid(ident)
        with self.access._transaction():
            member, story, _ = self._parent(token, library, story_id)
            row = self._contribution(ident, story['id'], library, include_audio=True)
            if row['kind'] != 'audio' or not self._can_see(member, story, row):
                raise AccessDenied('Access denied')
            return bytes(row['original_audio'])

    def create(self, token, library, story_id, body, audio=None):
        revision, mutation, duration_ms, raw_sha = _body(body, audio)
        story_id = _canonical_uuid(story_id)
        request_digest = hashlib.sha256(json.dumps(
            [library, story_id, body, raw_sha], sort_keys=True,
            ensure_ascii=True, separators=(',', ':')).encode('ascii')).hexdigest()
        with self.access._transaction(write=True):
            member, story, detail = self._parent(token, library, story_id)
            actor = member['account_id']
            prior = self.access._one('''SELECT * FROM access_memory_contributions
                WHERE author_id=? AND mutation_id=?''', (actor, mutation))
            if prior is not None:
                if prior['request_digest'] != request_digest:
                    raise TransportError(409, 'Contribution request identifier already used')
                if prior['story_id'] != story_id:
                    raise TransportError(409, 'Contribution request identifier already used')
                return self._receipt(prior, member, story)
            if revision != story['revision']:
                raise TransportError(409, 'Story changed; reload before contributing')
            chapter_id = body['chapter_id']
            chapters = {chapter['id'] for chapter in detail['chapters']}
            if chapter_id and chapter_id not in chapters:
                raise TransportError(422, 'Chapter is no longer available')
            if body['kind'] == 'audio':
                original_text, original_audio = None, audio
            else:
                original_text, original_audio = body['text'], None
            ident = str(uuid.uuid4())
            now = self.access._now()
            self.db.execute('''INSERT INTO access_memory_contributions
                (id,story_id,library_id,author_id,kind,original_text,original_audio,language,
                 byline,sha256,duration_ms,local_processing_consent,chapter_id,
                 base_story_revision,state,mutation_id,request_digest,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'pending',?,?,?)''',
                (ident, story_id, library, actor, body['kind'], original_text,
                 original_audio, body['language'], body['byline'], raw_sha,
                 duration_ms, int(body['consent']), body['chapter_id'] or None,
                 revision, mutation, request_digest, now))
            self.access._audit(actor, 'memory.contribution_create', library)
            return self._receipt(self._contribution(ident, story_id, library), member, story)

    def review(self, token, library, story_id, ident, state, expected_revision):
        ident = _canonical_uuid(ident)
        if type(state) is not str or state not in STATES:
            raise TransportError(422, 'Invalid contribution review state')
        if type(expected_revision) is str:
            expected_revision = _integer(expected_revision, 2**63 - 1)
        if type(expected_revision) is not int or expected_revision < 1:
            raise TransportError(400, 'Invalid story revision')
        with self.access._transaction(write=True):
            member, story, _ = self._parent(token, library, story_id)
            if not self._can_review(member, story):
                raise AccessDenied('Access denied')
            if story['revision'] != expected_revision:
                raise TransportError(409, 'Story changed; reload before reviewing')
            contribution = self._contribution(ident, story['id'], library)
            if contribution['state'] != 'pending':
                raise TransportError(409, 'Contribution was already reviewed')
            now = self.access._now()
            self.db.execute('''UPDATE access_memory_contributions SET state=?,reviewed_by_id=?,
                reviewed_at=? WHERE id=? AND state='pending' ''',
                (state, member['account_id'], now, ident))
            if state == 'accepted' and contribution['local_processing_consent']:
                self.db.execute('''INSERT INTO access_memory_contribution_derivations
                    (contribution_id,revision,state,created_at,updated_at)
                    VALUES(?,1,'waiting',?,?)''', (ident, now, now))
            elif state == 'declined':
                self.db.execute('''UPDATE access_memory_contribution_derivations
                    SET state='cancelled',transcript=NULL,polished_text=NULL,tags='[]',
                        error_code=NULL,lease_id=NULL,lease_until=NULL,updated_at=?
                    WHERE contribution_id=?''', (now, ident))
            self.access._audit(member['account_id'], 'memory.contribution_' + state, library)
            return self._receipt(self._contribution(ident, story['id'], library), member, story)

    def delete(self, token, library, story_id, ident):
        ident = _canonical_uuid(ident)
        if self.db.execute('PRAGMA secure_delete=ON').fetchone()[0] != 1:
            raise TransportError(503, 'Memory deletion unavailable')
        with self.access._transaction(write=True):
            member, story, _ = self._parent(token, library, story_id)
            if member['role'] != 'owner':
                raise AccessDenied('Access denied')
            contribution = self._contribution(ident, story['id'], library, include_audio=True)
            if self.access.original_deletions is not None:
                try:
                    self.access.original_deletions.append(self.db, 'memory', contribution, self.access._now())
                except RuntimeError:
                    raise TransportError(503, 'Memory deletion unavailable') from None
            from .original_deletions import erase_memory_original
            erase_memory_original(self.db, ident, story['id'], library, self.access._now())
            self.access._audit(member['account_id'], 'memory.contribution_delete',
                                library, contribution['author_id'])
            return {'deleted': True, 'id': ident}

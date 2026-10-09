"""Edition-bound, explicitly requested reads of current original source material."""
import hashlib
import re
import unicodedata
import uuid

from .assistant_speech import MAX_WAV_BYTES, valid_wav
from .memory_book_edition_schema import EDITION_TABLE
from .service import AccessDenied
from .transport import TransportError

SOURCE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}', re.ASCII)
PAGE_SIZE = 16
MAX_TEXT_BYTES = 8192


def _bounded_text(value, *, nullable=False):
    if value is None and nullable:
        return None, False
    if type(value) is not str:
        raise ValueError()
    raw = value.encode('utf-8', 'strict')
    if any(unicodedata.category(ch) == 'Cc' and ch not in '\n\t' for ch in value):
        raise ValueError()
    truncated = len(raw) > MAX_TEXT_BYTES
    raw = raw[:MAX_TEXT_BYTES]
    while True:
        try:
            return raw.decode('utf-8', 'strict'), truncated
        except UnicodeDecodeError:
            raw = raw[:-1]


def _decode_prefix(raw):
    raw = bytes(raw)
    try:
        value = raw.decode('utf-8', 'strict')
    except UnicodeDecodeError as error:
        if error.reason != 'unexpected end of data' or error.end != len(raw):
            raise ValueError() from None
        value = raw[:error.start].decode('utf-8', 'strict')
    _bounded_text(value)
    return value


def _byline(value):
    if value is None:
        return None
    if type(value) is not str or len(value.encode('utf-8', 'strict')) > 256:
        raise ValueError()
    if any(unicodedata.category(ch) == 'Cc' and ch not in '\n\t' for ch in value):
        raise ValueError()
    return value or None


def _prefix(source_id):
    if source_id.startswith('contribution-'):
        return 'contribution_text', source_id[len('contribution-'):]
    if source_id.startswith('caption-'):
        return 'caption', source_id[len('caption-'):]
    if source_id.startswith('family-'):
        return 'asset_note', source_id[len('family-'):]
    if source_id.startswith('editorial-book-'):
        return 'book_introduction', source_id[len('editorial-book-'):]
    match = re.fullmatch(r'editorial-([0-9a-f-]{36})-(chapter-[1-6])', source_id, re.ASCII)
    if match:
        return 'story_chapter', (match.group(1), match.group(2))
    return None, None


def _canonical_uuid(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError):
        raise AccessDenied('Access denied') from None


class MemoryBookEditionSources:
    def __init__(self, editions, *, originals_enabled=False):
        if type(originals_enabled) is not bool:
            raise ValueError('memoir_originals_flag_must_be_boolean')
        self.editions = editions
        self.access, self.db = editions.access, editions.db
        self.originals_enabled = originals_enabled

    def _ready(self):
        self.editions._ready()
        if not self.originals_enabled:
            raise TransportError(503, 'Memoir original sources unavailable')

    def _edition(self, token, library, book_id, edition_id):
        member, book, children = self.editions._book(token, library, book_id)
        row = self.access._one(f'''SELECT * FROM {EDITION_TABLE}
            WHERE id=? AND book_id=? AND library_id=?''', (edition_id, book_id, library))
        if row is None:
            raise AccessDenied('Access denied')
        receipt, state, bundle, verified = self.editions._verified_read(
            row, library, member, book, children)
        return book, receipt, state, bundle, verified

    @staticmethod
    def _envelope(receipt, book, edition_id, source_id, state, source=None):
        return {'version': 1, 'book_id': book['id'], 'edition_id': edition_id,
            'book_revision': receipt['book_revision'], 'source_id': source_id,
            'state': state, 'source': source}

    def list(self, token, library, book_id, edition_id, page=1):
        if type(page) is not int or not 1 <= page <= 100000:
            raise TransportError(400, 'Invalid memoir source page')
        book_id, edition_id = _canonical_uuid(book_id), _canonical_uuid(edition_id)
        with self.access._transaction():
            book, receipt, state, bundle, verified = self._edition(
                token, library, book_id, edition_id)
            self._ready()
            result = {'version': 1, 'book_id': book_id, 'edition_id': edition_id,
                'book_revision': receipt['book_revision'], 'state': state, 'page': page,
                'page_size': PAGE_SIZE, 'has_more': False, 'items': []}
            if state != 'current':
                return result
            provenance, _manuscript = verified
            sources = []
            for value in provenance.sources:
                origin, identity = _prefix(value.source_id)
                if origin is None:
                    raise TransportError(503, 'Memoir source unavailable')
                if origin == 'contribution_text':
                    _canonical_uuid(identity)
                    if value.kind == 'transcript':
                        origin = 'contribution_audio'
                elif origin == 'caption':
                    if (not identity.isascii() or not identity.isdecimal() or str(int(identity)) != identity
                            or not 1 <= int(identity) <= 9223372036854775807):
                        raise TransportError(503, 'Memoir source unavailable')
                elif origin == 'story_chapter' and type(identity) is tuple:
                    _canonical_uuid(identity[0])
                else:
                    _canonical_uuid(identity)
                sources.append({'source_id': value.source_id, 'origin': origin,
                    'kind': value.kind, 'asset_id': value.asset_id})
            offset = (page - 1) * PAGE_SIZE
            result['items'] = sources[offset:offset + PAGE_SIZE]
            result['has_more'] = offset + PAGE_SIZE < len(sources)
            return result

    def _resolve(self, library, book, source_id, bundle, provenance, *, audio=False):
        by_id = {item.source_id: item for item in provenance.sources}
        dependency = by_id.get(source_id)
        source_prompt = next((item for item in bundle['sources'] if item['id'] == source_id), None)
        if dependency is None or source_prompt is None:
            raise AccessDenied('Access denied')
        origin, identity = _prefix(source_id)
        reported_origin = ('contribution_audio' if origin == 'contribution_text'
                           and dependency.kind == 'transcript' else origin)
        if origin is None:
            raise TransportError(503, 'Memoir source unavailable')
        try:
            prompt_excerpt, _ = _bounded_text(source_prompt['text'])
            text_value = transcript = None
            text_truncated = transcript_truncated = False
            audio_payload = None
            byline = story_id = None
            audio_available = False
            if origin == 'contribution_text':
                cid = _canonical_uuid(identity)
                row = self.access._one('''SELECT c.id,c.story_id,c.kind,
                        c.sha256,c.byline,c.state,c.local_processing_consent,d.state AS derivation_state,
                        substr(CAST(d.transcript AS BLOB),1,8192) AS transcript_prefix,
                        length(CAST(d.transcript AS BLOB))>8192 AS transcript_truncated
                    FROM access_memory_contributions c LEFT JOIN access_memory_contribution_derivations d
                      ON d.contribution_id=c.id AND d.revision=(SELECT MAX(revision)
                        FROM access_memory_contribution_derivations WHERE contribution_id=c.id)
                    WHERE c.id=? AND c.library_id=? AND c.story_id=?''',
                    (cid, library, dependency.contribution_story_id))
                if (row is None or row['state'] != 'accepted' or not row['local_processing_consent'] or
                        row['story_id'] != dependency.contribution_story_id):
                    raise AccessDenied('Access denied')
                story_id = row['story_id']
                byline = _byline(row['byline'])
                if row['kind'] == 'text' and dependency.kind == 'family':
                    prefix, truncated = self.db.execute('''SELECT
                        substr(CAST(original_text AS BLOB),1,8192),
                        length(CAST(original_text AS BLOB))>8192
                        FROM access_memory_contributions WHERE id=? AND library_id=? AND story_id=?''',
                        (cid, library, story_id)).fetchone()
                    # Decode only the bounded SQL byte prefix, trimming an incomplete code point.
                    text_value = _decode_prefix(prefix)
                    text_truncated = bool(truncated)
                elif row['kind'] == 'audio' and dependency.kind == 'transcript':
                    if row['derivation_state'] != 'ready' or row['transcript_prefix'] is None:
                        raise AccessDenied('Access denied')
                    transcript = _decode_prefix(row['transcript_prefix'])
                    transcript_truncated = bool(row['transcript_truncated'])
                    audio_available = True
                    if audio:
                        audio_row = self.access._one('''SELECT original_audio
                            FROM access_memory_contributions
                            WHERE id=? AND library_id=? AND story_id=?
                              AND length(original_audio) BETWEEN 44 AND ?''',
                            (cid, library, story_id, MAX_WAV_BYTES))
                        audio_payload = audio_row['original_audio'] if audio_row is not None else None
                        if (not audio_payload or hashlib.sha256(audio_payload).hexdigest() != row['sha256']
                                or not valid_wav(audio_payload)):
                            raise TransportError(503, 'Memoir source audio unavailable')
                else:
                    raise AccessDenied('Access denied')
            elif origin == 'caption':
                if (not identity.isascii() or not identity.isdecimal() or str(int(identity)) != identity
                        or not 1 <= int(identity) <= 9223372036854775807):
                    raise AccessDenied('Access denied')
                caption_id = int(identity)
                row = self.access._one('''SELECT c.id,c.asset_id,c.user_edited,
                        length(CAST(c.text AS BLOB))>8192 AS truncated,
                        substr(CAST(c.text AS BLOB),1,8192) AS prefix,
                        a.status,l.asset_id AS linked_asset
                    FROM captions c JOIN assets a ON a.id=c.asset_id
                    JOIN access_asset_libraries l ON l.asset_id=a.id
                    WHERE c.id=? AND c.asset_id=? AND l.library_id=? AND c.superseded=0
                      AND (a.status IS NULL OR a.status='active')''',
                    (caption_id, dependency.asset_id, library))
                if row is None or bool(row['user_edited']) != (dependency.kind == 'family'):
                    raise AccessDenied('Access denied')
                text_value = _decode_prefix(row['prefix'])
                text_truncated = bool(row['truncated'])
            elif origin == 'story_chapter':
                if type(identity) is tuple:
                    sid = _canonical_uuid(identity[0])
                    chapter_id = identity[1]
                    child_revisions = {child.id: child.revision for child in provenance.children}
                    if sid not in child_revisions or dependency.kind != 'editorial':
                        raise AccessDenied('Access denied')
                    index = int(chapter_id.split('-', 1)[1]) - 1
                    path = f'$.chapters[{index}].narration'
                    row = self.access._one('''SELECT
                            substr(CAST(json_extract(content,?) AS BLOB),1,8192) AS prefix,
                            length(CAST(json_extract(content,?) AS BLOB))>8192 AS truncated
                        FROM access_memory_stories WHERE id=? AND library_id=? AND revision=?''',
                        (path, path, sid, library, int(child_revisions[sid])))
                    if row is None or row['prefix'] is None:
                        raise AccessDenied('Access denied')
                    text_value = _decode_prefix(row['prefix'])
                    text_truncated = bool(row['truncated'])
            elif origin == 'asset_note':
                sid = _canonical_uuid(identity)
                row = self.access._one('''SELECT s.id,s.asset_id,s.byline,
                        length(CAST(s.text AS BLOB))>8192 AS truncated,
                        substr(CAST(s.text AS BLOB),1,8192) AS prefix
                    FROM access_stories s JOIN assets a ON a.id=s.asset_id
                    JOIN access_asset_libraries l ON l.asset_id=a.id
                    WHERE s.id=? AND s.asset_id=? AND s.library_id=? AND s.deleted=0
                      AND l.library_id=? AND (a.status IS NULL OR a.status='active')''',
                    (sid, dependency.asset_id, library, library))
                if row is None or dependency.kind != 'family':
                    raise AccessDenied('Access denied')
                byline = _byline(row['byline'])
                text_value = _decode_prefix(row['prefix'])
                text_truncated = bool(row['truncated'])
            elif origin == 'book_introduction':
                bid = _canonical_uuid(identity)
                if bid != book['id'] or dependency.kind != 'editorial':
                    raise AccessDenied('Access denied')
                intro = self.db.execute('''SELECT
                        substr(CAST(json_extract(content,'$.introduction') AS BLOB),1,8192) AS prefix,
                        length(CAST(json_extract(content,'$.introduction') AS BLOB))>8192 AS truncated
                    FROM access_memory_books WHERE id=? AND library_id=?''',
                    (bid, library)).fetchone()
                if intro is None or intro[0] is None:
                    raise AccessDenied('Access denied')
                text_value = _decode_prefix(intro[0])
                if not text_value.strip():
                    raise AccessDenied('Access denied')
                text_truncated = bool(intro[1])
            else:
                raise AccessDenied('Access denied')
            return {'origin': reported_origin, 'kind': dependency.kind,
                'asset_id': None if origin == 'story_chapter' else dependency.asset_id,
                'story_id': sid if origin == 'story_chapter' else story_id,
                'byline': byline, 'original_text': text_value,
                'original_truncated': text_truncated if text_value is not None else False,
                'transcript': transcript,
                'transcript_truncated': transcript_truncated if transcript is not None else False,
                'prompt_excerpt': prompt_excerpt, 'audio_available': audio_available}, audio_payload
        except AccessDenied:
            raise
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, RecursionError):
            raise TransportError(503, 'Memoir source unavailable') from None

    def detail(self, token, library, book_id, edition_id, source_id):
        book_id, edition_id = _canonical_uuid(book_id), _canonical_uuid(edition_id)
        if type(source_id) is not str or SOURCE_ID.fullmatch(source_id) is None:
            raise TransportError(400, 'Invalid memoir source identifier')
        with self.access._transaction():
            book, _receipt, state, bundle, verified = self._edition(
                token, library, book_id, edition_id)
            self._ready()
            if state != 'current':
                return self._envelope(_receipt, book, edition_id, source_id, state)
            provenance, _manuscript = verified
            source, _audio = self._resolve(library, book, source_id, bundle, provenance)
            return self._envelope(_receipt, book, edition_id, source_id, 'current', source)

    def audio(self, token, library, book_id, edition_id, source_id):
        book_id, edition_id = _canonical_uuid(book_id), _canonical_uuid(edition_id)
        if type(source_id) is not str or SOURCE_ID.fullmatch(source_id) is None:
            raise TransportError(400, 'Invalid memoir source identifier')
        with self.access._transaction():
            book, receipt, state, bundle, verified = self._edition(
                token, library, book_id, edition_id)
            self._ready()
            if state != 'current':
                return {'state': state, 'audio': None}
            provenance, _manuscript = verified
            source, payload = self._resolve(library, book, source_id, bundle,
                                            provenance, audio=True)
            if source['origin'] != 'contribution_audio' or source['kind'] != 'transcript' or payload is None:
                raise AccessDenied('Access denied')
            return {'state': 'current', 'audio': payload}

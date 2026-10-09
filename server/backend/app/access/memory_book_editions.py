"""Default-off, explicitly reviewed memoir editions, independent of expiring jobs.

No model calls, migrations, routing, or source text snapshots happen here. A
proposal is actor-private; a saved edition is readable only through the current
library/book/media authorization and a matching complete source closure.
"""
import json
import sqlite3
import uuid

from .memory_book_edition_contract import (
    EditionChildRevision, parse_reviewed_edition, reviewed_edition_identity,
)
from .memory_book_edition_deletions import EditionDeletionError, verify_edition_schema
from .memory_book_edition_provenance import build_edition_provenance
from .family_note_identity import (identity_enabled, resolve_note_identity,
    persist_edition_note_identities, edition_note_identities_match)
from .family_note_identity_schema import IDENTITY_REVISION
from .memory_book_edition_schema import EDITION_REVISION, EDITION_TABLE, SOURCES_TABLE
from .memory_jobs import (
    EDITORIAL_CONTEXT_PROFILE, MemoryJobs, context, digest, editorial_choice, parent,
    text,
)
from .memory_narrative import validate_narrative
from .memory_stories import _json
from .service import AccessDenied
from .stories import _uuid
from .transport import TransportError

PAGE_SIZE = 8


def _json_string(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False)


class MemoryBookEditions:
    def __init__(self, access, *, enabled=False, editorial_enabled=False):
        if type(enabled) is not bool or type(editorial_enabled) is not bool:
            raise ValueError('memoir_edition_flags_must_be_boolean')
        self.access, self.db = access, access.db
        self.enabled, self.editorial_enabled = enabled, editorial_enabled

    def _ready(self):
        if not self.enabled:
            raise TransportError(503, 'Reviewed memoir editions unavailable')
        try:
            if self.db.execute('SELECT version_num FROM alembic_version').fetchall() not in (
                    [(EDITION_REVISION,)], [(IDENTITY_REVISION,)]):
                raise EditionDeletionError('memoir_edition_schema_unavailable')
            verify_edition_schema(self.db)
            identity_enabled(self.db)
        except (EditionDeletionError, sqlite3.DatabaseError):
            raise TransportError(503, 'Reviewed memoir editions unavailable') from None

    def _book(self, token, library, book_id, *, write=False):
        member = self.access._require(token, library, 'story.write' if write else 'library.read')
        self._ready()
        row, details, can_edit, _ = parent(self.access, library, member, 'book', book_id)
        if write and not can_edit:
            raise AccessDenied('Access denied')
        children = tuple(EditionChildRevision(value['id'], value['revision']) for value in details)
        return member, row, children

    def _context(self, library, member, book_id, profile):
        if profile not in {'stories', EDITORIAL_CONTEXT_PROFILE}:
            raise TransportError(503, 'Reviewed memoir editions unavailable')
        selected = editorial_choice(
            {'context_profile': profile} if profile != 'stories' else {},
            enabled=self.editorial_enabled)
        return context(self.access, library, member, 'book', book_id,
                       editorial_context=selected, principal_neutral_fingerprint=True)

    def _provenance(self, bundle, children, library):
        # These identities come from authorized storage, never model citations.
        child_ids = tuple(child.id for child in children)
        source_ids = tuple(source['id'][len('contribution-'):] for source in bundle['sources']
                           if source['id'].startswith('contribution-'))
        owners = dict(self.db.execute('''SELECT id,story_id FROM access_memory_contributions
            WHERE library_id=? AND state='accepted' AND local_processing_consent=1
            AND story_id IN (''' + ','.join('?' for _ in child_ids) + ''')
            AND id IN (''' + ','.join('?' for _ in source_ids) + ')',
            (library, *child_ids, *source_ids)).fetchall()) if source_ids else {}
        note_identities = None
        if identity_enabled(self.db):
            note_identities = {}
            for source in bundle['sources']:
                if source['id'].startswith('family-'):
                    note_id = source['id'][len('family-'):]
                    note_identities[note_id] = resolve_note_identity(
                        self.db, note_id, library, source['asset_id'])
        return build_edition_provenance(bundle, children, contribution_owners=owners,
                                        family_note_identities=note_identities)

    def _job(self, library, member, book_id, job_id):
        MemoryJobs(self.access)._ready()
        job = self.access._one('''SELECT * FROM access_memory_jobs
            WHERE id=? AND library_id=? AND actor_id=? AND book_id=? AND story_id IS NULL
            AND conversation_id IS NULL AND kind='narrative' AND expires_at>?''',
            (job_id, library, member['account_id'], book_id, self.access._now()))
        if job is None:
            raise AccessDenied('Access denied')
        if (job['state'] != 'ready' or job['output_json'] is None or
                job['lease_id'] is not None or job['lease_until'] is not None or
                job['error_code'] is not None):
            raise TransportError(409, 'Wait for a current completed memoir draft')
        try:
            controls = _json(job['input_json'])
            if (type(controls) is not dict or set(controls) not in
                    ({'instructions'}, {'instructions', 'context_profile'})):
                raise ValueError()
            text(controls['instructions'], 4096, blank=True)
            selected = editorial_choice(controls, enabled=self.editorial_enabled)
        except TransportError:
            raise TransportError(503, 'Reviewed memoir editions unavailable') from None
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise TransportError(503, 'Reviewed memoir editions unavailable') from None
        profile = EDITORIAL_CONTEXT_PROFILE if selected else 'stories'
        return job, profile

    def _proposal(self, library, member, book_id, children, job):
        job, profile = self._job(library, member, book_id, job)
        # First bind the actor-private ready job using the unchanged private job
        # fingerprint. The saved family's edition uses a principal-neutral
        # source fingerprint so another approved reader can open the same prose.
        _, job_fingerprint, _ = MemoryJobs(self.access,
            editorial_enabled=self.editorial_enabled)._job_context(library, member, job)
        bundle, fingerprint, can_edit = self._context(library, member, book_id, profile)
        if not can_edit:
            raise AccessDenied('Access denied')
        if (job['base_revision'] != bundle['target']['revision'] or
                job['source_fingerprint'] != job_fingerprint):
            raise TransportError(409, 'Memoir sources changed; request a new draft')
        try:
            result = validate_narrative(_json(job['output_json']), bundle)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise TransportError(503, 'Reviewed memoir draft unavailable') from None
        provenance = self._provenance(bundle, children, library)
        return job, profile, bundle, fingerprint, result, provenance

    def proposal(self, token, library, book_id, job_id):
        book_id, job_id = _uuid(book_id), _uuid(job_id)
        with self.access._transaction():
            member, book, children = self._book(token, library, book_id, write=True)
            job, profile, _, fingerprint, result, _ = self._proposal(
                library, member, book_id, children, job_id)
            return {'version': 1, 'book_id': book_id, 'revision': str(book['revision']),
                'job_id': job['id'], 'job_result_sha256': digest(result),
                'source_fingerprint': fingerprint, 'context_profile': profile,
                'children': [{'id': child.id, 'revision': child.revision} for child in children],
                'manuscript': result, 'needs_review': True}

    @staticmethod
    def _receipt(row):
        # Retry receipts are deliberately content-free, including after expiry,
        # edits, or source erasure. A separate fresh authorized read opens prose.
        return {'version': 1, 'id': row['id'], 'book_id': row['book_id'],
            'book_revision': str(row['book_revision']), 'created_at': row['created_at'],
            'state': row['state'], 'mutation_id': row['mutation_id']}

    def save(self, token, library, book_id, raw):
        book_id = _uuid(book_id)
        mutation_id, request_digest = reviewed_edition_identity(raw)
        with self.access._transaction(write=True):
            member, book, children = self._book(token, library, book_id, write=True)
            prior = self.access._one(f'''SELECT * FROM {EDITION_TABLE}
                WHERE creator_account_id=? AND mutation_id=?''',
                (member['account_id'], mutation_id))
            if prior is not None:
                if (prior['book_id'] != book_id or prior['library_id'] != library or
                        prior['request_digest'] != request_digest):
                    raise TransportError(409, 'Save identifier already used; keep your manuscript')
                return self._receipt(prior)
            # Full shape and source validation are required only for a new save.
            # The bounded identity parser above cannot authorize persistence.
            from .memory_book_edition_contract import _decode, _canonical_uuid
            job_id = _canonical_uuid(_decode(raw)['job_id'])
            job, profile, bundle, fingerprint, result, provenance = self._proposal(
                library, member, book_id, children, job_id)
            request = parse_reviewed_edition(raw, bundle)
            if (request.children != children or request.source_fingerprint != fingerprint or
                    request.job_result_sha256 != digest(result)):
                raise TransportError(409, 'Memoir draft or sources changed; keep your manuscript')
            if request.request_digest != request_digest:
                raise TransportError(400, 'Invalid memoir edition request')
            manuscript = _json(request.canonical_json)['manuscript']
            ident, now = str(uuid.uuid4()), self.access._now()
            values = (ident, book_id, book['revision'], library, member['account_id'],
                job['id'], digest(result), fingerprint, profile,
                _json_string([{'id': child.id, 'revision': child.revision} for child in children]),
                _json_string(manuscript), mutation_id, request_digest, now, 'current')
            self.db.execute(f'''INSERT INTO {EDITION_TABLE}
                (id,book_id,book_revision,library_id,creator_account_id,originating_job_id,
                 job_result_sha256,source_fingerprint,context_profile,children_json,
                 manuscript_json,mutation_id,request_digest,created_at,state)
                VALUES({','.join('?' for _ in values)})''', values)
            for ordinal, source in enumerate(provenance.sources):
                self.db.execute(f'''INSERT INTO {SOURCES_TABLE}
                    (edition_id,ordinal,source_id,kind,asset_id,source_digest,chapter_ids_json,
                     contribution_id,contribution_story_id) VALUES(?,?,?,?,?,?,?,?,?)''',
                    (ident, ordinal, source.source_id, source.kind, source.asset_id,
                     source.source_digest, _json_string(list(source.chapter_ids)),
                     source.contribution_id, source.contribution_story_id))
            persist_edition_note_identities(self.db, ident, provenance.sources)
            self.access._audit(member['account_id'], 'memory.book_edition_save', library)
            return self._receipt(self.access._one(f'SELECT * FROM {EDITION_TABLE} WHERE id=?', (ident,)))

    def _verified_read(self, row, library, member, book, children):
        """Rebuild and verify the complete current server closure once per read."""
        receipt = self._receipt(row)
        if row['state'] == 'source_invalidated':
            return receipt, 'source_invalidated', None, None
        if row['state'] != 'current' or row['manuscript_json'] is None:
            raise TransportError(503, 'Reviewed memoir edition unavailable')
        if row['book_revision'] != book['revision']:
            return receipt, 'source_changed', None, None
        try:
            saved_children = _json(row['children_json'])
            expected_children = [{'id': child.id, 'revision': child.revision} for child in children]
            if saved_children != expected_children:
                return receipt, 'source_changed', None, None
            bundle, fingerprint, _ = self._context(library, member, book['id'], row['context_profile'])
            if fingerprint != row['source_fingerprint']:
                return receipt, 'source_changed', None, None
            provenance = self._provenance(bundle, children, library)
            persisted = self.db.execute(f'''SELECT ordinal,source_id,kind,asset_id,source_digest,
                chapter_ids_json,contribution_id,contribution_story_id FROM {SOURCES_TABLE}
                WHERE edition_id=? ORDER BY ordinal''', (row['id'],)).fetchall()
            expected = [(ordinal, source.source_id, source.kind, source.asset_id,
                source.source_digest, _json_string(list(source.chapter_ids)),
                source.contribution_id, source.contribution_story_id)
                for ordinal, source in enumerate(provenance.sources)]
            if ([tuple(value) for value in persisted] != expected or
                    not edition_note_identities_match(self.db, row['id'], provenance.sources)):
                return receipt, 'source_changed', None, None
            manuscript = validate_narrative(_json(row['manuscript_json']), bundle)
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise TransportError(503, 'Reviewed memoir edition unavailable') from None
        return receipt, 'current', bundle, (provenance, manuscript)

    def _read(self, row, library, member, book, children, *, include_manuscript=True):
        receipt, state, _bundle, verified = self._verified_read(
            row, library, member, book, children)
        if state != 'current':
            return {**receipt, 'state': state, 'manuscript': None}
        _provenance, manuscript = verified
        return {**receipt, 'state': 'current',
                'manuscript': manuscript if include_manuscript else None}

    def get(self, token, library, book_id, edition_id):
        book_id, edition_id = _uuid(book_id), _uuid(edition_id)
        with self.access._transaction():
            member, book, children = self._book(token, library, book_id)
            row = self.access._one(f'''SELECT * FROM {EDITION_TABLE}
                WHERE id=? AND book_id=? AND library_id=?''', (edition_id, book_id, library))
            if row is None:
                raise AccessDenied('Access denied')
            return self._read(row, library, member, book, children)

    def list(self, token, library, book_id, page=1):
        if type(page) is not int or not 1 <= page <= 100000:
            raise TransportError(400, 'Invalid memoir edition page')
        book_id = _uuid(book_id)
        with self.access._transaction():
            member, book, children = self._book(token, library, book_id)
            cursor = self.db.execute(f'''SELECT * FROM {EDITION_TABLE}
                WHERE book_id=? AND library_id=? ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?''',
                (book_id, library, PAGE_SIZE + 1, (page - 1) * PAGE_SIZE))
            names = [column[0] for column in cursor.description]
            rows = [dict(zip(names, value)) for value in cursor.fetchall()]
            return {'version': 1, 'book_id': book_id, 'page': page, 'page_size': PAGE_SIZE,
                'has_more': len(rows) > PAGE_SIZE,
                'items': [self._read(row, library, member, book, children, include_manuscript=False)
                          for row in rows[:PAGE_SIZE]]}

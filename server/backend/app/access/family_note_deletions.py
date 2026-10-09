"""Identity-based family-note erasure and content-free restore verification.

No authorization, journal append, commit, migration or backfill in this module.
Callers own the secure write transaction and durable append-before-purge order.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid

from .family_note_identity import MAX_SCOPE_ENTRIES, _lineage, identity_enabled
from .family_note_identity_schema import IDENTITIES, SCOPES, EDITION_NOTES
from .memory_book_edition_deletions import verify_edition_schema, _normalized
from .memory_book_edition_schema import EDITION_TABLE, SOURCES_TABLE
from .original_deletions import OriginalDeletionError
from .transport import TransportError

MAX_BINDING_BYTES = 300 * 1024
_HEX = re.compile(r'[0-9a-f]{64}', re.ASCII)


def _refuse():
    raise OriginalDeletionError('Family note erasure unavailable') from None


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False,
                      separators=(',', ':'))


def _sha(value):
    return hashlib.sha256(_json(value).encode('ascii')).hexdigest()


def parse_family_binding(value):
    try:
        if type(value) is not str or not value.isascii() or not 1 <= len(value) <= MAX_BINDING_BYTES:
            _refuse()
        binding = json.loads(value)
        if (type(binding) is not dict or set(binding) != {'version', 'identity_id', 'registry_sha256',
                'expected_revision', 'revision_sha256', 'scope_digests'} or binding['version'] != 2 or
                type(binding['version']) is not int or
                type(binding['identity_id']) is not str or str(uuid.UUID(binding['identity_id'])) != binding['identity_id'] or
                type(binding['expected_revision']) is not int or not 1 <= binding['expected_revision'] <= 2**63-1 or
                type(binding['scope_digests']) is not list or not 1 <= len(binding['scope_digests']) <= MAX_SCOPE_ENTRIES or
                any(type(d) is not str or _HEX.fullmatch(d) is None for d in
                    [binding['registry_sha256'], binding['revision_sha256'], *binding['scope_digests']]) or
                _json(binding) != value):
            _refuse()
        return binding
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        _refuse()


def _storage(db):
    if not db.in_transaction:
        _refuse()
    try:
        if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
            _refuse()
        if not identity_enabled(db):
            _refuse()
        verify_edition_schema(db)
        # Compile required raw-note definitions from the migration-only builder.
        from sqlalchemy import Column, Integer, MetaData, Table, Text
        from sqlalchemy.schema import CreateTable, CreateIndex
        from sqlalchemy.dialects.sqlite import dialect
        from .story_schema import add_story_tables
        metadata = MetaData()
        for name, kind in (('assets', Integer), ('access_libraries', Text), ('access_accounts', Text)):
            Table(name, metadata, Column('id', kind, primary_key=True))
        for table in add_story_tables(metadata):
            objects = [('table', table.name, str(CreateTable(table).compile(dialect=dialect())))]
            objects += [('index', index.name, str(CreateIndex(index).compile(dialect=dialect()))) for index in table.indexes]
            from .family_note_identity_schema import sqlite_family_note_identity_contract
            expected_triggers = {name for kind, name, ddl in sqlite_family_note_identity_contract()
                if kind == 'trigger' and (' ON ' + table.name + ' ') in ddl}
            actual_triggers = {r[0] for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table.name,))}
            if actual_triggers != expected_triggers:
                _refuse()
            for kind, name, ddl in objects:
                actual = db.execute('SELECT type,sql FROM sqlite_master WHERE name=?', (name,)).fetchone()
                if actual is None or actual[0] != kind or _normalized(actual[1]) != _normalized(ddl):
                    _refuse()
    except (sqlite3.Error, ValueError, TransportError, UnicodeError):
        _refuse()


def _identity(db, note_id):
    row = db.execute(f'SELECT * FROM {IDENTITIES} WHERE note_id=?', (note_id,)).fetchone()
    if row is None:
        _refuse()
    identity = list(row)
    try:
        _lineage(db, identity[0])
    except (TransportError, sqlite3.Error, ValueError):
        _refuse()
    scopes = [list(r) for r in db.execute(f'SELECT * FROM {SCOPES} WHERE identity_id=? ORDER BY ordinal',
                                        (identity[0],))]
    previous = _sha(['family_note_scope_v2', identity])
    digests = []
    for scope in scopes:
        previous = _sha([previous, scope])
        digests.append(previous)
    return identity, scopes, digests


def _note(db, note_id):
    cursor = db.execute('SELECT * FROM access_stories WHERE id=?', (note_id,))
    row = cursor.fetchone()
    return dict(zip((c[0] for c in cursor.description), row)) if row is not None else None


def _verify_note(row, identity, scopes):
    if row is None:
        return
    if (row['id'] != identity[1] or row['asset_id'] != identity[2] or row['author_id'] != identity[3] or
            row['created_at'] != identity[5] or row['library_id'] != scopes[-1][3] or
            type(row['revision']) is not int or not 1 <= row['revision'] <= 2**63-1 or
            any(type(row[field]) is not str for field in ('title', 'text', 'language', 'byline')) or
            type(row['updated_at']) is not int or type(row['deleted']) is not int or row['deleted'] not in {0, 1}):
        _refuse()


def _revision_sha(row):
    # Library moves do not edit the raw revision; ledger hashes bind that field.
    return _sha({key: value for key, value in row.items() if key != 'library_id'})


def prepare_family_tombstone(db, note_id, expected_revision, occurred_at):
    _storage(db)
    identity, scopes, digests = _identity(db, note_id)
    row = _note(db, note_id)
    _verify_note(row, identity, scopes)
    if row is None or row['revision'] != expected_revision or type(expected_revision) is not int:
        _refuse()
    binding = {'version': 2, 'identity_id': identity[0], 'registry_sha256': _sha(identity),
        'expected_revision': expected_revision, 'revision_sha256': _revision_sha(row), 'scope_digests': digests}
    value = _json(binding)
    parse_family_binding(value)
    return {'collection': 'family_note', 'library_id': row['library_id'], 'object_id': note_id,
        'original_kind': 'text', 'original_sha256': hashlib.sha256(row['text'].encode('utf-8')).hexdigest(),
        'batch': None, 'asset_id': identity[2], 'story_id': None, 'occurred_at': occurred_at,
        'family_binding_json': value}


def verify_family_record(db, record):
    """Accept matching older mutable revisions and exact ledger prefixes only."""
    _storage(db)
    binding = parse_family_binding(record['family_binding_json'])
    identity, scopes, digests = _identity(db, record['object_id'])
    if (identity[0] != binding['identity_id'] or _sha(identity) != binding['registry_sha256'] or
            identity[2] != record['asset_id'] or len(digests) > len(binding['scope_digests']) or
            digests != binding['scope_digests'][:len(digests)] or
            (len(digests) == len(binding['scope_digests']) and scopes[-1][3] != record['library_id'])):
        _refuse()
    row = _note(db, record['object_id'])
    _verify_note(row, identity, scopes)
    if row is not None:
        if row['revision'] > binding['expected_revision']:
            _refuse()
        # A pre-move backup may keep the same revision and old library. Source
        # content must match at an equal revision; exclude only the sanctioned
        # mutable library field for that comparison.
        if row['revision'] == binding['expected_revision']:
            if _revision_sha(row) != binding['revision_sha256']:
                _refuse()
    revisions = db.execute('SELECT min(revision),max(revision) FROM access_story_revisions WHERE story_id=?',
                           (record['object_id'],)).fetchone()
    if revisions[0] is not None and (revisions[0] < 1 or revisions[1] > binding['expected_revision']):
        _refuse()
    return identity, scopes, row


def _dependent_editions(db, identity, scopes):
    orphan = db.execute(f'''SELECT 1 FROM {EDITION_NOTES} n
        LEFT JOIN {EDITION_TABLE} e ON e.id=n.edition_id
        LEFT JOIN {SOURCES_TABLE} s ON s.edition_id=n.edition_id AND s.ordinal=n.ordinal
        WHERE n.identity_id=? AND (e.id IS NULL OR s.ordinal IS NULL) LIMIT 1''', (identity[0],)).fetchone()
    if orphan:
        _refuse()
    matches = db.execute(f'''SELECT DISTINCT e.id,e.library_id,e.book_id,e.originating_job_id,e.children_json,
        e.state,e.manuscript_json FROM {EDITION_TABLE} e JOIN {EDITION_NOTES} n ON n.edition_id=e.id
        WHERE n.identity_id=? LIMIT 10001''', (identity[0],)).fetchall()
    if len(matches) > 10000:
        _refuse()
    for edition in matches:
        if not ((edition[5] == 'current' and edition[6] is not None) or
                (edition[5] == 'source_invalidated' and edition[6] is None)):
            _refuse()
        bindings = db.execute(f'''SELECT n.scope_ordinal,s.source_id,s.kind,s.asset_id
            FROM {EDITION_NOTES} n JOIN {SOURCES_TABLE} s
            ON s.edition_id=n.edition_id AND s.ordinal=n.ordinal
            WHERE n.edition_id=? AND n.identity_id=?''', (edition[0], identity[0])).fetchall()
        if not bindings or any(type(n[0]) is not int or not 0 <= n[0] < len(scopes) or
                scopes[n[0]][3] != edition[1] or tuple(n[1:]) != ('family-' + identity[1], 'family', str(identity[2]))
                for n in bindings):
            _refuse()
    # Opaque C2 source IDs cannot establish original identity. Refuse an
    # unqualified historical row rather than guessing or silently adopting it.
    unbound = db.execute(f'''SELECT 1 FROM {SOURCES_TABLE} s LEFT JOIN {EDITION_NOTES} n
        ON n.edition_id=s.edition_id AND n.ordinal=s.ordinal
        WHERE s.source_id=? AND (n.identity_id IS NULL OR n.identity_id!=?) LIMIT 1''',
        ('family-' + identity[1], identity[0])).fetchone()
    if unbound:
        _refuse()
    return matches


def _private_targets(db, identity, scopes, editions):
    """Find current/historical asset stories and edition targets; preserve inputs."""
    libraries = {scope[3] for scope in scopes}
    targets = {library: {'stories': set(), 'books': set(), 'jobs': set()} for library in libraries}
    for ident, library, book, job, children, _state, _prose in editions:
        target = targets[library]
        target['books'].add(book)
        target['jobs'].add(job)
        try:
            target['stories'].update(child['id'] for child in json.loads(children))
        except (ValueError, TypeError, KeyError):
            _refuse()
    if sum(len(values) for target in targets.values() for values in target.values()) > 10000:
        _refuse()
    for library, target in targets.items():
        target['stories'].update(row[0] for row in db.execute('''SELECT s.id FROM access_memory_stories s
            WHERE s.library_id=? AND EXISTS (SELECT 1 FROM json_each(
                CASE WHEN json_valid(s.content) THEN s.content ELSE '{}' END,'$.asset_ids') a
                WHERE CAST(a.value AS TEXT)=?) LIMIT 10001''', (library, str(identity[2]))))
        target['stories'].update(row[0] for row in db.execute('''SELECT DISTINCT r.story_id
            FROM access_memory_revisions r JOIN access_memory_stories s ON s.id=r.story_id
            WHERE s.library_id=? AND EXISTS (SELECT 1 FROM json_each(
                CASE WHEN json_valid(r.content) THEN r.content ELSE '{}' END,'$.asset_ids') a
                WHERE CAST(a.value AS TEXT)=?) LIMIT 10001''', (library, str(identity[2]))))
        if sum(map(len, target.values())) > 10000:
            _refuse()
        for story in target['stories']:
            target['books'].update(row[0] for row in db.execute('''SELECT b.id FROM access_memory_books b
                WHERE b.library_id=? AND EXISTS (SELECT 1 FROM json_each(
                    CASE WHEN json_valid(b.content) THEN b.content ELSE '{}' END,'$.story_ids') a
                    WHERE a.value=?) LIMIT 10001''', (library, story)))
            target['books'].update(row[0] for row in db.execute('''SELECT DISTINCT r.book_id
                FROM access_memory_book_revisions r JOIN access_memory_books b ON b.id=r.book_id
                WHERE b.library_id=? AND EXISTS (SELECT 1 FROM json_each(
                    CASE WHEN json_valid(r.content) THEN r.content ELSE '{}' END,'$.story_ids') a
                    WHERE a.value=?) LIMIT 10001''', (library, story)))
            if sum(map(len, target.values())) > 10000:
                _refuse()
        if sum(len(values) for t in targets.values() for values in t.values()) > 10000:
            _refuse()
    try:
        for target in targets.values():
            for values in target.values():
                if any(type(value) is not str or str(uuid.UUID(value)) != value for value in values):
                    _refuse()
    except (ValueError, TypeError, AttributeError):
        _refuse()
    return targets


def preflight_family_erasure(db, record):
    """Check identity and complete typed closure before a durable append."""
    identity, scopes, row = verify_family_record(db, record)
    editions = _dependent_editions(db, identity, scopes)
    _private_targets(db, identity, scopes, editions)
    return identity, scopes, row


def _purge_private_replies(db, identity, scopes, editions, now):
    # Bounded batches avoid SQLite's host-parameter limit. A whole target's AI
    # copies are conservatively erased; manual story/book text and input remain.
    for library, target in _private_targets(db, identity, scopes, editions).items():
        for field, key in (('story_id', 'stories'), ('book_id', 'books'), ('id', 'jobs')):
            ids = sorted(target[key])
            for offset in range(0, len(ids), 200):
                batch = ids[offset:offset + 200]
                query = 'library_id=? AND ' + field + ' IN (' + ','.join('?' for _ in batch) + ')'
                args = (library, *batch)
                db.execute('UPDATE access_memory_turns SET reply_text=NULL,reply_kind=NULL '
                    'WHERE job_id IN (SELECT id FROM access_memory_jobs WHERE ' + query + ')', args)
                if field != 'id':
                    db.execute('UPDATE access_memory_turns SET reply_text=NULL,reply_kind=NULL '
                        'WHERE conversation_id IN (SELECT id FROM access_memory_conversations WHERE ' + query + ')', args)
                db.execute("""UPDATE access_memory_jobs SET state=CASE WHEN state IN ('queued','running')
                    THEN 'cancelled' ELSE state END,input_json='{}',output_json=NULL,error_code=NULL,
                    lease_id=NULL,lease_until=NULL,updated_at=? WHERE """ + query, (now, *args))


def erase_family_note_original(db, record):
    """Secure caller-owned purge after a durable family-note tombstone."""
    if not db.in_transaction or db.execute('PRAGMA secure_delete').fetchone()[0] != 1 or (
            db.execute('PRAGMA foreign_keys').fetchone()[0] != 1):
        _refuse()
    try:
        identity, scopes, _row = verify_family_record(db, record)
        editions = _dependent_editions(db, identity, scopes)
        _purge_private_replies(db, identity, scopes, editions, record['occurred_at'])
        for ident, _library, _book, _job, _children, state, prose in editions:
            if state == 'current' and prose is not None:
                db.execute(f"UPDATE {EDITION_TABLE} SET state='source_invalidated',manuscript_json=NULL WHERE id=?", (ident,))
            elif state != 'source_invalidated' or prose is not None:
                _refuse()
            db.execute(f'DELETE FROM {SOURCES_TABLE} WHERE edition_id=?', (ident,))
        db.execute('DELETE FROM access_story_revisions WHERE story_id=?', (record['object_id'],))
        db.execute('DELETE FROM access_stories WHERE id=?', (record['object_id'],))
        return {'deleted': True, 'id': record['object_id'], 'editions_scrubbed': len(editions)}
    except (sqlite3.Error, ValueError, TransportError, UnicodeError):
        _refuse()

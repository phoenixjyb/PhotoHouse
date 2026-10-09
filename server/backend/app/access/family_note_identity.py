"""Transaction-bound family-note lineage. No migration, backfill or erasure."""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import uuid

from .family_note_identity_schema import (EDITION_NOTES, IDENTITIES, IDENTITY_REVISION,
    SCOPES, sqlite_family_note_identity_contract)
from .transport import TransportError

MAX_SCOPE_ENTRIES = 4096


def unavailable():
    raise TransportError(503, 'Family note identity unavailable') from None


def _uuid(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            unavailable()
    except (ValueError, TypeError, AttributeError):
        unavailable()
    return value


def verify_family_note_identity_schema(db):
    from .memory_book_edition_deletions import _normalized
    try:
        for kind, name, ddl in sqlite_family_note_identity_contract():
            row = db.execute('SELECT type,sql FROM sqlite_master WHERE name=?', (name,)).fetchone()
            if row is None or row[0] != kind or _normalized(row[1]) != _normalized(ddl):
                unavailable()
    except (sqlite3.Error, ValueError):
        unavailable()


def identity_enabled(db):
    if [tuple(row) for row in db.execute('SELECT version_num FROM alembic_version')] != [(IDENTITY_REVISION,)]:
        return False
    verify_family_note_identity_schema(db)
    return True


@dataclass(frozen=True, slots=True)
class FamilyNoteIdentity:
    identity_id: str
    note_id: str
    asset_id: str
    scope_ordinal: int
    library_id: str


def _lineage(db, identity):
    rows = db.execute(f'''SELECT ordinal,from_library_id,library_id,plan_id,plan_digest,occurred_at
        FROM {SCOPES} WHERE identity_id=? ORDER BY ordinal LIMIT ?''', (identity, MAX_SCOPE_ENTRIES+1)).fetchall()
    original = db.execute(f'SELECT origin_library_id,created_at FROM {IDENTITIES} WHERE identity_id=?',
                          (identity,)).fetchone()
    if not original or not rows or len(rows) > MAX_SCOPE_ENTRIES:
        unavailable()
    previous = None
    for expected, row in enumerate(rows):
        ordinal, source, library, plan_id, plan_digest, occurred = row
        if ordinal != expected:
            unavailable()
        if expected == 0:
            if (source is not None or plan_id is not None or plan_digest is not None or
                    library != original[0] or occurred != original[1]):
                unavailable()
        elif source != previous or library == source:
            unavailable()
        previous = library
    return rows[-1][0], previous


def create_note_identity(db, note_id):
    """Only called immediately after inserting a new note, in its transaction."""
    if not db.in_transaction:
        unavailable()
    if not identity_enabled(db):
        return
    _uuid(note_id)
    row = db.execute('SELECT asset_id,author_id,library_id,created_at,revision,deleted '
                     'FROM access_stories WHERE id=?', (note_id,)).fetchone()
    if row is None or row[4:] != (1, 0):
        unavailable()
    identity = str(uuid.uuid4())
    db.execute(f'INSERT INTO {IDENTITIES} VALUES(?,?,?,?,?,?)', (identity, note_id, *row[:4]))
    db.execute(f'INSERT INTO {SCOPES} VALUES(?,0,NULL,?,NULL,NULL,?)', (identity, row[2], row[3]))


def resolve_note_identity(db, note_id, library_id, asset_id):
    """Fresh, current, complete lineage; missing legacy bindings fail closed."""
    if not db.in_transaction or not identity_enabled(db):
        unavailable()
    _uuid(note_id)
    row = db.execute(f'''SELECT i.identity_id,i.note_id,i.asset_id,p.ordinal,p.library_id
        FROM {IDENTITIES} i JOIN access_stories n ON n.id=i.note_id
        JOIN {SCOPES} p ON p.identity_id=i.identity_id
        JOIN access_asset_libraries m ON m.asset_id=n.asset_id AND m.library_id=n.library_id
        JOIN assets a ON a.id=n.asset_id
        WHERE i.note_id=? AND n.library_id=? AND n.asset_id=? AND n.deleted=0
        AND (a.status IS NULL OR a.status='active') AND i.asset_id=n.asset_id AND i.author_id=n.author_id
        AND i.created_at=n.created_at AND p.library_id=n.library_id
        AND p.ordinal=(SELECT max(q.ordinal) FROM {SCOPES} q WHERE q.identity_id=i.identity_id)''',
        (note_id, library_id, asset_id)).fetchone()
    if row is None:
        unavailable()
    _uuid(row[0])
    if _lineage(db, row[0]) != (row[3], row[4]):
        unavailable()
    return FamilyNoteIdentity(row[0], row[1], str(row[2]), row[3], row[4])


def append_note_scope_moves(db, asset_id, source, destination, plan_id, plan_digest, now):
    """Append bound-note lineage before the same transaction moves the notes.

    Legacy unbound notes retain their old semantics and remain unqualified.
    The promotion review separately seals every lineage row before applying.
    """
    if not db.in_transaction:
        unavailable()
    if not identity_enabled(db) or source == destination:
        return
    rows = db.execute(f'''SELECT i.identity_id,p.ordinal,p.library_id
        FROM access_stories n JOIN {IDENTITIES} i ON i.note_id=n.id
        JOIN {SCOPES} p ON p.identity_id=i.identity_id
        WHERE n.asset_id=? AND n.library_id=?
        AND p.ordinal=(SELECT max(q.ordinal) FROM {SCOPES} q WHERE q.identity_id=i.identity_id)''',
        (asset_id, source)).fetchall()
    bound_count = db.execute(f'''SELECT count(*) FROM access_stories n
        JOIN {IDENTITIES} i ON i.note_id=n.id WHERE n.asset_id=? AND n.library_id=?''',
        (asset_id, source)).fetchone()[0]
    if len(rows) != bound_count or any(row[2] != source for row in rows):
        unavailable()
    for identity, ordinal, _library in rows:
        if ordinal >= MAX_SCOPE_ENTRIES-1 or _lineage(db, identity) != (ordinal, source):
            unavailable()
        db.execute(f'INSERT INTO {SCOPES} VALUES(?,?,?,?,?,?,?)',
            (identity, ordinal+1, source, destination, plan_id, plan_digest, now))


def persist_edition_note_identities(db, edition_id, sources):
    if not db.in_transaction:
        unavailable()
    if not identity_enabled(db):
        return
    for ordinal, source in enumerate(sources):
        if source.family_note_identity is not None:
            binding = source.family_note_identity
            db.execute(f'INSERT INTO {EDITION_NOTES} VALUES(?,?,?,?)',
                (edition_id, ordinal, binding.identity_id, binding.scope_ordinal))


def edition_note_identities_match(db, edition_id, sources):
    if not identity_enabled(db):
        return True
    expected = [(ordinal, s.family_note_identity.identity_id, s.family_note_identity.scope_ordinal)
                for ordinal, s in enumerate(sources) if s.family_note_identity is not None]
    actual = db.execute(f'SELECT ordinal,identity_id,scope_ordinal FROM {EDITION_NOTES} '
                        'WHERE edition_id=? ORDER BY ordinal', (edition_id,)).fetchall()
    return [tuple(row) for row in actual] == expected

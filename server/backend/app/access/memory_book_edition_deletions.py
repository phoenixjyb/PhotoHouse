"""Caller-owned transaction erasure of every dependent reviewed AI edition.

The common original eraser calls this after its durable tombstone.
Legacy databases without edition tables are a no-op. This module does not
commit, authorize, append a tombstone, or change a feature flag.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3
import re
import uuid

from .memory_book_edition_schema import EDITION_TABLE, SOURCES_TABLE


class EditionDeletionError(ValueError):
    """Bounded fail-closed erasure error without private row identifiers."""


@dataclass(frozen=True, slots=True)
class EditionDeletionCounts:
    editions_scrubbed: int = 0
    references_deleted: int = 0


def _unavailable():
    raise EditionDeletionError('memoir_edition_erasure_unavailable') from None


def _scope(contribution_id, story_id, library_id):
    try:
        for ident in (contribution_id, story_id):
            if type(ident) is not str or str(uuid.UUID(ident)) != ident:
                _unavailable()
        if (type(library_id) is not str or not 1 <= len(library_id.encode('utf-8', errors='strict')) <= 128
                or any(ord(c) < 32 for c in library_id)):
            _unavailable()
    except (ValueError, TypeError, AttributeError, UnicodeError):
        _unavailable()


def _normalized(sql):
    if type(sql) is not str:
        _unavailable()
    normalized = ' '.join(sql.split()).rstrip(';')
    return re.sub(r'^(CREATE (?:TABLE|INDEX|TRIGGER)) IF NOT EXISTS ', r'\1 ', normalized)


def verify_edition_schema(db):
    """Reject partial, altered table/index/trigger definitions before any write.

    The deterministic schema contract is compiled from the source builder.
    Extra indexes are harmless, but each required object must match exactly.
    """
    from .memory_book_edition_schema import sqlite_edition_schema_contract
    for kind, name, ddl in sqlite_edition_schema_contract():
        row = db.execute('SELECT type,sql FROM sqlite_master WHERE name=?', (name,)).fetchone()
        if row is None or row[0] != kind or _normalized(row[1]) != _normalized(ddl):
            _unavailable()


def invalidate_editions_for_contribution(db, contribution_id, story_id, library_id):
    """Scrub content and all closure rows in the caller's secure write transaction.

    A contribution in the full prompt closure invalidates the whole edition,
    including historical book revisions and contributions not cited in its prose.
    Scope comes from the immutable edition/library and normalized source owner;
    no current-book join can hide an orphaned historical record during replay.
    """
    _scope(contribution_id, story_id, library_id)
    if getattr(db, 'in_transaction', False) is not True:
        _unavailable()
    try:
        names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        present = {EDITION_TABLE, SOURCES_TABLE} & names
        if not present:
            return EditionDeletionCounts()
        if present != {EDITION_TABLE, SOURCES_TABLE}:
            _unavailable()
        verify_edition_schema(db)
        if db.execute('PRAGMA secure_delete').fetchone()[0] != 1:
            _unavailable()
        matches = db.execute(f'''SELECT DISTINCT e.id,e.state,e.manuscript_json
            FROM {EDITION_TABLE} e JOIN {SOURCES_TABLE} r ON r.edition_id=e.id
            WHERE e.library_id=? AND r.contribution_id=? AND r.contribution_story_id=?''',
            (library_id, contribution_id, story_id)).fetchall()
        changed = refs = 0
        for ident, state, content in matches:
            if state == 'current' and content is not None:
                changed += db.execute(f'''UPDATE {EDITION_TABLE}
                    SET state='source_invalidated',manuscript_json=NULL WHERE id=? AND state='current' ''',
                    (ident,)).rowcount
            elif state != 'source_invalidated' or content is not None:
                _unavailable()
            refs += db.execute(f'DELETE FROM {SOURCES_TABLE} WHERE edition_id=?', (ident,)).rowcount
        return EditionDeletionCounts(changed, refs)
    except sqlite3.Error:
        _unavailable()

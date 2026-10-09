"""Deletion companion for memoir editorial records.

The common original eraser calls this after the durable deletion tombstone is
written, with secure_delete enabled, inside its existing primary write
transaction. Authorization and tombstone durability remain caller duties. This
helper neither commits nor rolls back; live a0 databases have no sidecar tables,
so it remains a no-op there.
"""
from __future__ import annotations

from dataclasses import dataclass
import uuid

from .memory_book_editorial_schema import BOOK_TABLE, REFS_TABLE


class EditorialDeletionError(ValueError):
    """Bounded fail-closed error without identifiers or database details."""


@dataclass(frozen=True, slots=True)
class EditorialDeletionCounts:
    sidecars_invalidated: int = 0
    refs_deleted: int = 0


_EXPECTED_COLUMNS = {
    BOOK_TABLE: (
        ('book_id', 'TEXT', 1, 1),
        ('book_revision', 'INTEGER', 1, 2),
        ('children_json', 'TEXT', 1, 0),
        ('transitions_json', 'TEXT', 1, 0),
        ('state', 'TEXT', 1, 0),
    ),
    REFS_TABLE: (
        ('book_id', 'TEXT', 1, 1),
        ('book_revision', 'INTEGER', 1, 2),
        ('section_key', 'TEXT', 1, 3),
        ('ordinal', 'INTEGER', 1, 4),
        ('story_id', 'TEXT', 1, 0),
        ('story_revision', 'INTEGER', 1, 0),
        ('chapter_id', 'TEXT', 1, 0),
        ('contribution_id', 'TEXT', 1, 0),
    ),
}


def _canonical_uuid(value: object) -> str:
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise EditorialDeletionError('editorial_deletion_invalid_scope') from None
    return value


def _bounded_library_id(value: object) -> str:
    if type(value) is not str:
        raise EditorialDeletionError('editorial_deletion_invalid_scope')
    try:
        size = len(value.encode('utf-8', errors='strict'))
    except UnicodeError:
        raise EditorialDeletionError('editorial_deletion_invalid_scope') from None
    if not 1 <= size <= 128:
        raise EditorialDeletionError('editorial_deletion_invalid_scope')
    return value


def _table_names(db) -> set[str]:
    return {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _validate_columns(db, table_name: str) -> None:
    rows = db.execute(f'PRAGMA table_info({table_name})').fetchall()
    actual = tuple((row[1], row[2].upper(), row[3], row[5]) for row in rows)
    if actual != _EXPECTED_COLUMNS[table_name]:
        raise EditorialDeletionError('editorial_deletion_schema_invalid')


def _foreign_keys(db, table_name: str) -> set[tuple[str, str, str, str]]:
    # (target table, source column, target column, on delete action)
    rows = db.execute(f'PRAGMA foreign_key_list({table_name})').fetchall()
    return {(row[2], row[3], row[4], row[6].upper()) for row in rows}


def _validate_schema(db) -> None:
    for table_name in (BOOK_TABLE, REFS_TABLE):
        _validate_columns(db, table_name)
    if _foreign_keys(db, BOOK_TABLE) != {
            ('access_memory_book_revisions', 'book_id', 'book_id', 'CASCADE'),
            ('access_memory_book_revisions', 'book_revision', 'revision', 'CASCADE')}:
        raise EditorialDeletionError('editorial_deletion_schema_invalid')
    if _foreign_keys(db, REFS_TABLE) != {
            (BOOK_TABLE, 'book_id', 'book_id', 'CASCADE'),
            (BOOK_TABLE, 'book_revision', 'book_revision', 'CASCADE'),
            ('access_memory_revisions', 'story_id', 'story_id', 'CASCADE'),
            ('access_memory_revisions', 'story_revision', 'revision', 'CASCADE'),
            ('access_memory_contributions', 'contribution_id', 'id', 'CASCADE')}:
        raise EditorialDeletionError('editorial_deletion_schema_invalid')
    required_constraints = {
        BOOK_TABLE: {
            'fk_memory_book_editorial_revision',
            'ck_memory_book_editorial_revision',
            'ck_memory_book_editorial_children_bytes',
            'ck_memory_book_editorial_transition_bytes',
            'ck_memory_book_editorial_state',
        },
        REFS_TABLE: {
            'fk_memory_book_editorial_ref_parent',
            'fk_memory_book_editorial_ref_story_revision',
            'fk_memory_book_editorial_ref_contribution',
            'uq_memory_book_editorial_ref_source',
            'ck_memory_book_editorial_ref_revisions',
            'ck_memory_book_editorial_ref_ordinal',
            'ck_memory_book_editorial_ref_section',
            'ck_memory_book_editorial_ref_chapter',
        },
    }
    for table_name, names_required in required_constraints.items():
        ddl_row = db.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)).fetchone()
        if (ddl_row is None or type(ddl_row[0]) is not str
                or not names_required <= set(ddl_row[0].split())):
            raise EditorialDeletionError('editorial_deletion_schema_invalid')
    required_parent_columns = {
        'access_memory_books': {'id', 'library_id'},
    }
    for table_name, columns in required_parent_columns.items():
        if table_name not in _table_names(db):
            raise EditorialDeletionError('editorial_deletion_schema_invalid')
        actual = {row[1] for row in db.execute(
            f'PRAGMA table_info({table_name})').fetchall()}
        if not columns <= actual:
            raise EditorialDeletionError('editorial_deletion_schema_invalid')


def invalidate_for_contribution(db, contribution_id: str, story_id: str,
                                library_id: str) -> EditorialDeletionCounts:
    """Invalidate matching historical sidecars, then delete their source refs.

    The caller must have independently authorized deletion, durably appended
    its tombstone, enabled SQLite secure_delete, and opened the primary write
    transaction. The connection/transaction stays owned by that caller.
    Legacy databases with neither editorial table are a no-op; partial or
    malformed future schemas fail closed before any mutation.
    """
    contribution_id = _canonical_uuid(contribution_id)
    story_id = _canonical_uuid(story_id)
    library_id = _bounded_library_id(library_id)
    if getattr(db, 'in_transaction', False) is not True:
        raise EditorialDeletionError('editorial_deletion_transaction_required')

    try:
        names = _table_names(db)
        has_sidecar, has_refs = BOOK_TABLE in names, REFS_TABLE in names
        if not has_sidecar and not has_refs:
            return EditorialDeletionCounts()
        if has_sidecar != has_refs:
            raise EditorialDeletionError('editorial_deletion_schema_partial')
        _validate_schema(db)
        secure_delete = db.execute('PRAGMA secure_delete').fetchone()
        if secure_delete is None or secure_delete[0] != 1:
            raise EditorialDeletionError('editorial_deletion_secure_delete_required')

        scope = f'''EXISTS (
            SELECT 1 FROM {REFS_TABLE} r
            JOIN access_memory_books b ON b.id=r.book_id
            WHERE r.book_id=e.book_id AND r.book_revision=e.book_revision
              AND r.contribution_id=? AND r.story_id=? AND b.library_id=?)'''
        updated = db.execute(f'''UPDATE {BOOK_TABLE} AS e
            SET state='source_invalidated'
            WHERE e.state='current' AND {scope}''',
            (contribution_id, story_id, library_id))
        invalidated = max(0, updated.rowcount)

        deleted = db.execute(f'''DELETE FROM {REFS_TABLE} AS target
            WHERE target.contribution_id=? AND target.story_id=?
              AND EXISTS (SELECT 1 FROM access_memory_books b
                          WHERE b.id=target.book_id AND b.library_id=?)''',
            (contribution_id, story_id, library_id))
        return EditorialDeletionCounts(invalidated, max(0, deleted.rowcount))
    except EditorialDeletionError:
        raise
    except Exception:
        # The enclosing caller must roll back the transaction on any failure.
        raise EditorialDeletionError('editorial_deletion_unavailable') from None

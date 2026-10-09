"""Durable private references from saved chapters to accepted family contributions.

Only opaque contribution identifiers are retained. Original words, bylines and
transcripts stay in their existing source records and are never copied here.
"""
from __future__ import annotations

import json
import sqlite3
import uuid

from .transport import TransportError

TABLE = 'access_memory_contribution_refs'
MAX_GROUPS = 6
MAX_PER_CHAPTER = 12
MAX_JSON_BYTES = 32768


def add_source_ref_table(metadata):
    # Keep SQLAlchemy out of application import paths; this is called only by
    # explicit Alembic/migration metadata construction.
    from sqlalchemy import (CheckConstraint, Column, ForeignKeyConstraint,
                            Index, Integer, Table, Text, UniqueConstraint)
    table = Table(TABLE, metadata,
        Column('story_id', Text, primary_key=True, nullable=False),
        Column('revision', Integer, primary_key=True, nullable=False),
        Column('chapter_id', Text, primary_key=True, nullable=False),
        Column('ordinal', Integer, primary_key=True, nullable=False),
        Column('contribution_id', Text, nullable=False),
        ForeignKeyConstraint(['story_id', 'revision'],
            ['access_memory_revisions.story_id', 'access_memory_revisions.revision'],
            ondelete='CASCADE'),
        ForeignKeyConstraint(['contribution_id'], ['access_memory_contributions.id'],
            ondelete='CASCADE'),
        CheckConstraint('revision > 0 AND ordinal BETWEEN 0 AND 11'))
    table.append_constraint(UniqueConstraint('story_id', 'revision', 'chapter_id',
                                             'contribution_id'))
    table.append_constraint(CheckConstraint("chapter_id IN ('chapter-1','chapter-2','chapter-3','chapter-4','chapter-5','chapter-6')"))
    Index('ix_memory_contribution_refs_source', table.c.contribution_id)
    return table


def table_exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (TABLE,)).fetchone() is not None


def available(db):
    """Only a database at the exact additive revision may use this contract."""
    try:
        versions = db.execute('SELECT version_num FROM alembic_version').fetchall()
    except sqlite3.Error:
        return False
    return (len(versions) == 1 and versions[0][0] in {'a0c9d2e4f817', 'b1d7e4a9c230', 'c2e6b8a1d490', 'd1f6a8c3e920'}
            and table_exists(db))


def _canonical(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise TransportError(422, 'Invalid contribution reference') from None
    return value


def parse_groups(raw, chapter_ids):
    if type(raw) is not str:
        raise TransportError(400, 'Invalid contribution references')
    try:
        encoded = raw.encode('utf-8', errors='strict')
        if len(encoded) > MAX_JSON_BYTES:
            raise TransportError(413, 'Contribution references too large')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        groups = json.loads(raw, object_pairs_hook=unique,
                            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()))
        if type(groups) is not list or len(groups) > MAX_GROUPS:
            raise ValueError()
        allowed = set(chapter_ids)
        seen_chapters, normalized = set(), []
        for group in groups:
            if type(group) is not dict or set(group) != {'chapter_id', 'contribution_ids'}:
                raise ValueError()
            chapter = group['chapter_id']
            refs = group['contribution_ids']
            if type(chapter) is not str or chapter not in allowed or chapter in seen_chapters:
                raise ValueError()
            if type(refs) is not list or len(refs) > MAX_PER_CHAPTER:
                raise ValueError()
            clean = [_canonical(ref) for ref in refs]
            if len(set(clean)) != len(clean):
                raise ValueError()
            seen_chapters.add(chapter)
            normalized.append((chapter, clean))
        return normalized
    except TransportError:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise TransportError(422, 'Invalid contribution references') from None


def eligible(db, contribution_id, story_id, library, chapter_id):
    row = db.execute('''SELECT story_id,library_id,state,local_processing_consent,chapter_id
        FROM access_memory_contributions WHERE id=?''', (contribution_id,)).fetchone()
    if (row is None or row[0] != story_id or row[1] != library or row[2] != 'accepted'
            or row[3] != 1 or (row[4] is not None and row[4] != chapter_id)):
        return False
    return True


def validate_groups(db, groups, story_id, library):
    for chapter, refs in groups:
        for ident in refs:
            if not eligible(db, ident, story_id, library, chapter):
                raise TransportError(422, 'Invalid contribution reference')


def current_groups(db, story_id, revision, chapter_ids, library):
    rows = db.execute(f'''SELECT r.chapter_id,r.contribution_id FROM {TABLE} r
        JOIN access_memory_contributions c ON c.id=r.contribution_id
        WHERE r.story_id=? AND r.revision=? AND c.story_id=? AND c.library_id=?
          AND c.state='accepted' AND c.local_processing_consent=1
          AND (c.chapter_id IS NULL OR c.chapter_id=r.chapter_id)
        ORDER BY r.chapter_id,r.ordinal''', (story_id, revision, story_id, library)).fetchall()
    by_chapter = {chapter: [] for chapter in chapter_ids}
    for chapter, contribution in rows:
        if chapter in by_chapter:
            by_chapter[chapter].append(contribution)
    return [(chapter, refs) for chapter, refs in by_chapter.items() if refs]


def replace_groups(db, story_id, revision, groups):
    for chapter, refs in groups:
        db.executemany(f'''INSERT INTO {TABLE}
            (story_id,revision,chapter_id,ordinal,contribution_id) VALUES (?,?,?,?,?)''',
            ((story_id, revision, chapter, ordinal, ident) for ordinal, ident in enumerate(refs)))

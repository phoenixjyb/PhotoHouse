"""Additive tables for authored book source bindings and transitions.

The b1 migration creates these tables without backfill. Runtime activation
remains an explicit default-off capability; source inclusion does not migrate
or enable an existing database.
"""

from .memory_book_edition_schema import EDITION_REVISION
from .family_note_identity_schema import IDENTITY_REVISION

EDITORIAL_REVISION = 'b1d7e4a9c230'  # Additive source revision; live deployment is a separate gate.
EDITORIAL_REVISIONS = frozenset({EDITORIAL_REVISION, EDITION_REVISION, IDENTITY_REVISION})
BOOK_TABLE = 'access_memory_book_editorial'
REFS_TABLE = 'access_memory_book_editorial_refs'
MAX_CHILDREN = 24
MAX_SNAPSHOT_BYTES = 16384
# Request JSON is capped at 64 KiB; ensure_ascii serialization can expand
# UTF-8 text by at most 3x (two-byte code points become six ASCII bytes).
MAX_TRANSITION_JSON_BYTES = 3 * 65536


def add_book_editorial_tables(metadata):
    """Add the two future tables to an existing combined SQLAlchemy Metadata.

    Existing definitions must match the complete expected SQLite schema. A
    partial or conflicting installation is rejected instead of silently
    accepted. This function performs no database I/O or backfill.
    """
    from sqlalchemy import (CheckConstraint, Column, ForeignKeyConstraint,
                            DDL, Index, Integer, MetaData, Table, Text, event,
                            UniqueConstraint)
    from sqlalchemy.schema import CreateIndex, CreateTable
    from sqlalchemy.dialects import sqlite

    required = {
        'access_memory_book_revisions': {'book_id', 'revision'},
        'access_memory_revisions': {'story_id', 'revision'},
        'access_memory_contributions': {'id'},
    }
    for name, columns in required.items():
        table = metadata.tables.get(name)
        if table is None or not columns <= set(table.c.keys()):
            raise ValueError('editorial_schema_prerequisite_missing')

    expected = MetaData()
    # Parent stubs reproduce only the referenced keys; they are not returned
    # or copied into caller metadata.
    Table('access_memory_book_revisions', expected,
          Column('book_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_revisions', expected,
          Column('story_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_contributions', expected,
          Column('id', Text, primary_key=True))

    editorial = Table(BOOK_TABLE, expected,
        Column('book_id', Text, primary_key=True, nullable=False),
        Column('book_revision', Integer, primary_key=True, nullable=False),
        Column('children_json', Text, nullable=False),
        Column('transitions_json', Text, nullable=False),
        Column('state', Text, nullable=False),
        ForeignKeyConstraint(['book_id', 'book_revision'],
            ['access_memory_book_revisions.book_id',
             'access_memory_book_revisions.revision'], ondelete='CASCADE',
            name='fk_memory_book_editorial_revision'),
        CheckConstraint('book_revision > 0', name='ck_memory_book_editorial_revision'),
        CheckConstraint('length(CAST(children_json AS BLOB)) BETWEEN 1 AND 16384',
                        name='ck_memory_book_editorial_children_bytes'),
        CheckConstraint(f'length(CAST(transitions_json AS BLOB)) BETWEEN 1 AND {MAX_TRANSITION_JSON_BYTES}',
                        name='ck_memory_book_editorial_transition_bytes'),
        CheckConstraint("state IN ('current','source_invalidated')",
                        name='ck_memory_book_editorial_state'))

    refs = Table(REFS_TABLE, expected,
        Column('book_id', Text, primary_key=True, nullable=False),
        Column('book_revision', Integer, primary_key=True, nullable=False),
        Column('section_key', Text, primary_key=True, nullable=False),
        Column('ordinal', Integer, primary_key=True, nullable=False),
        Column('story_id', Text, nullable=False),
        Column('story_revision', Integer, nullable=False),
        Column('chapter_id', Text, nullable=False),
        Column('contribution_id', Text, nullable=False),
        ForeignKeyConstraint(['book_id', 'book_revision'],
            [f'{BOOK_TABLE}.book_id', f'{BOOK_TABLE}.book_revision'],
            ondelete='CASCADE', name='fk_memory_book_editorial_ref_parent'),
        ForeignKeyConstraint(['story_id', 'story_revision'],
            ['access_memory_revisions.story_id', 'access_memory_revisions.revision'],
            ondelete='CASCADE', name='fk_memory_book_editorial_ref_story_revision'),
        ForeignKeyConstraint(['contribution_id'],
            ['access_memory_contributions.id'], ondelete='CASCADE',
            name='fk_memory_book_editorial_ref_contribution'),
        UniqueConstraint('book_id', 'book_revision', 'section_key',
                         'contribution_id', name='uq_memory_book_editorial_ref_source'),
        CheckConstraint('book_revision > 0 AND story_revision > 0',
                        name='ck_memory_book_editorial_ref_revisions'),
        CheckConstraint('ordinal BETWEEN 0 AND 11',
                        name='ck_memory_book_editorial_ref_ordinal'),
        CheckConstraint("section_key='introduction' OR section_key IN (" +
            ','.join(repr(f'transition-{i:02d}') for i in range(MAX_CHILDREN - 1)) + ')',
            name='ck_memory_book_editorial_ref_section'),
        CheckConstraint('length(CAST(chapter_id AS BLOB)) BETWEEN 1 AND 128',
                        name='ck_memory_book_editorial_ref_chapter'))
    Index('ix_memory_book_editorial_ref_contribution', refs.c.contribution_id)
    Index('ix_memory_book_editorial_ref_story_revision', refs.c.story_id,
          refs.c.story_revision)

    new_names = {BOOK_TABLE, REFS_TABLE}
    present = new_names & set(metadata.tables)
    if present and present != new_names:
        raise ValueError('editorial_schema_partial_installation')

    dialect = sqlite.dialect()

    def schema_signature(table):
        ddl = str(CreateTable(table).compile(dialect=dialect))
        indexes = tuple(sorted(str(CreateIndex(index).compile(dialect=dialect))
                               for index in table.indexes))
        return ddl, indexes

    if present:
        for name in (BOOK_TABLE, REFS_TABLE):
            if schema_signature(metadata.tables[name]) != schema_signature(expected.tables[name]):
                raise ValueError('editorial_schema_definition_mismatch')
        return metadata.tables[BOOK_TABLE], metadata.tables[REFS_TABLE]

    # Recreate definitions against caller metadata after validating parents.
    editorial = Table(BOOK_TABLE, metadata,
        Column('book_id', Text, primary_key=True, nullable=False),
        Column('book_revision', Integer, primary_key=True, nullable=False),
        Column('children_json', Text, nullable=False),
        Column('transitions_json', Text, nullable=False),
        Column('state', Text, nullable=False),
        ForeignKeyConstraint(['book_id', 'book_revision'],
            ['access_memory_book_revisions.book_id',
             'access_memory_book_revisions.revision'], ondelete='CASCADE',
            name='fk_memory_book_editorial_revision'),
        CheckConstraint('book_revision > 0', name='ck_memory_book_editorial_revision'),
        CheckConstraint('length(CAST(children_json AS BLOB)) BETWEEN 1 AND 16384',
                        name='ck_memory_book_editorial_children_bytes'),
        CheckConstraint(f'length(CAST(transitions_json AS BLOB)) BETWEEN 1 AND {MAX_TRANSITION_JSON_BYTES}',
                        name='ck_memory_book_editorial_transition_bytes'),
        CheckConstraint("state IN ('current','source_invalidated')",
                        name='ck_memory_book_editorial_state'))
    refs = Table(REFS_TABLE, metadata,
        Column('book_id', Text, primary_key=True, nullable=False),
        Column('book_revision', Integer, primary_key=True, nullable=False),
        Column('section_key', Text, primary_key=True, nullable=False),
        Column('ordinal', Integer, primary_key=True, nullable=False),
        Column('story_id', Text, nullable=False),
        Column('story_revision', Integer, nullable=False),
        Column('chapter_id', Text, nullable=False),
        Column('contribution_id', Text, nullable=False),
        ForeignKeyConstraint(['book_id', 'book_revision'],
            [f'{BOOK_TABLE}.book_id', f'{BOOK_TABLE}.book_revision'],
            ondelete='CASCADE', name='fk_memory_book_editorial_ref_parent'),
        ForeignKeyConstraint(['story_id', 'story_revision'],
            ['access_memory_revisions.story_id', 'access_memory_revisions.revision'],
            ondelete='CASCADE', name='fk_memory_book_editorial_ref_story_revision'),
        ForeignKeyConstraint(['contribution_id'],
            ['access_memory_contributions.id'], ondelete='CASCADE',
            name='fk_memory_book_editorial_ref_contribution'),
        UniqueConstraint('book_id', 'book_revision', 'section_key',
                         'contribution_id', name='uq_memory_book_editorial_ref_source'),
        CheckConstraint('book_revision > 0 AND story_revision > 0',
                        name='ck_memory_book_editorial_ref_revisions'),
        CheckConstraint('ordinal BETWEEN 0 AND 11',
                        name='ck_memory_book_editorial_ref_ordinal'),
        CheckConstraint("section_key='introduction' OR section_key IN (" +
            ','.join(repr(f'transition-{i:02d}') for i in range(MAX_CHILDREN - 1)) + ')',
            name='ck_memory_book_editorial_ref_section'),
        CheckConstraint('length(CAST(chapter_id AS BLOB)) BETWEEN 1 AND 128',
                        name='ck_memory_book_editorial_ref_chapter'))
    Index('ix_memory_book_editorial_ref_contribution', refs.c.contribution_id)
    Index('ix_memory_book_editorial_ref_story_revision', refs.c.story_id,
          refs.c.story_revision)

    def install_immutability_triggers(table):
        # Alembic does not represent SQLite triggers in Table metadata. These
        # create_all hooks document/enforce the future table contract when the
        # builder is explicitly used in synthetic schema creation.
        statements = {
            BOOK_TABLE: (
                "CREATE TRIGGER IF NOT EXISTS trg_memory_book_editorial_immutable "
                f"BEFORE UPDATE ON {BOOK_TABLE} WHEN "
                "NEW.book_id != OLD.book_id OR NEW.book_revision != OLD.book_revision OR "
                "NEW.children_json != OLD.children_json OR "
                "NEW.transitions_json != OLD.transitions_json OR "
                "(NEW.state != OLD.state AND NOT "
                "(OLD.state='current' AND NEW.state='source_invalidated')) "
                "BEGIN SELECT RAISE(ABORT, 'Editorial snapshot is immutable'); END",
                "DROP TRIGGER IF EXISTS trg_memory_book_editorial_immutable"),
            REFS_TABLE: (
                "CREATE TRIGGER IF NOT EXISTS trg_memory_book_editorial_refs_immutable "
                f"BEFORE UPDATE ON {REFS_TABLE} "
                "BEGIN SELECT RAISE(ABORT, 'Editorial source references are immutable'); END",
                "DROP TRIGGER IF EXISTS trg_memory_book_editorial_refs_immutable"),
        }
        create_sql, drop_sql = statements[table.name]
        event.listen(table, 'after_create', DDL(create_sql).execute_if(dialect='sqlite'))
        event.listen(table, 'before_drop', DDL(drop_sql).execute_if(dialect='sqlite'))

    install_immutability_triggers(editorial)
    install_immutability_triggers(refs)
    return editorial, refs

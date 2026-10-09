"""Additive schema builder for immutable reviewed memoir editions.

This builder does not run a migration or enable the feature. Contribution
foreign-key cascades are safe only after the common eraser has scrubbed every
dependent edition in the same write transaction.
"""
from __future__ import annotations

EDITION_TABLE = 'access_memory_book_editions'
EDITION_REVISION = 'c2e6b8a1d490'
SOURCES_TABLE = 'access_memory_book_edition_sources'
MAX_CHILDREN_JSON_BYTES = 16_384
MAX_MANUSCRIPT_JSON_BYTES = 196_608
MAX_SOURCE_ROWS = 96
MAX_SOURCE_ID_BYTES = 128
MAX_ASSET_ID_BYTES = 128
MAX_CHAPTER_IDS_JSON_BYTES = 16_384


def _required_parents(metadata):
    required = {
        'access_memory_books': {'id', 'library_id'},
        'access_memory_book_revisions': {'book_id', 'revision'},
        'access_libraries': {'id'},
        'access_accounts': {'id'},
        'access_memory_stories': {'id'},
        'access_memory_contributions': {'id', 'story_id'},
    }
    for name, columns in required.items():
        table = metadata.tables.get(name)
        if table is None or not columns <= set(table.c.keys()):
            raise ValueError('book_edition_schema_prerequisite_missing')

    primary_keys = {
        'access_memory_books': {'id'},
        'access_memory_book_revisions': {'book_id', 'revision'},
        'access_libraries': {'id'},
        'access_accounts': {'id'},
        'access_memory_stories': {'id'},
        'access_memory_contributions': {'id'},
    }
    for name, expected in primary_keys.items():
        actual = {column.name for column in metadata.tables[name].primary_key.columns}
        if actual != expected:
            raise ValueError('book_edition_schema_prerequisite_key_invalid')


def _add_tables(metadata):
    from sqlalchemy import (CheckConstraint, Column, ForeignKey,
                            ForeignKeyConstraint, Index, Integer, Table, Text,
                            UniqueConstraint)

    editions = Table(EDITION_TABLE, metadata,
        Column('id', Text, primary_key=True, nullable=False),
        Column('book_id', Text, nullable=False),
        Column('book_revision', Integer, nullable=False),
        Column('library_id', Text, ForeignKey('access_libraries.id', ondelete='CASCADE'),
               nullable=False),
        Column('creator_account_id', Text,
               ForeignKey('access_accounts.id', ondelete='CASCADE'), nullable=False),
        # Job rows are intentionally not parents: proposals expire after 30 days.
        Column('originating_job_id', Text, nullable=False),
        Column('job_result_sha256', Text, nullable=False),
        Column('source_fingerprint', Text, nullable=False),
        Column('context_profile', Text, nullable=False),
        Column('children_json', Text, nullable=False),
        Column('manuscript_json', Text),
        Column('mutation_id', Text, nullable=False),
        Column('request_digest', Text, nullable=False),
        Column('created_at', Integer, nullable=False),
        Column('state', Text, nullable=False),
        ForeignKeyConstraint(['book_id'], ['access_memory_books.id'], ondelete='CASCADE',
            name='fk_memory_book_edition_book'),
        ForeignKeyConstraint(['book_id', 'book_revision'],
            ['access_memory_book_revisions.book_id',
             'access_memory_book_revisions.revision'], ondelete='CASCADE',
            name='fk_memory_book_edition_revision'),
        UniqueConstraint('creator_account_id', 'mutation_id',
                         name='uq_memory_book_edition_mutation'),
        CheckConstraint('book_revision > 0', name='ck_memory_book_edition_revision'),
        CheckConstraint('created_at >= 0', name='ck_memory_book_edition_created_at'),
        CheckConstraint("context_profile IN ('stories','memoir_editorial_v1')",
                        name='ck_memory_book_edition_context_profile'),
        CheckConstraint(
            f"length(CAST(children_json AS BLOB)) BETWEEN 1 AND {MAX_CHILDREN_JSON_BYTES} "
            "AND json_valid(children_json) AND json_type(children_json)='array'",
            name='ck_memory_book_edition_children_bytes'),
        CheckConstraint(
            f"manuscript_json IS NULL OR (length(CAST(manuscript_json AS BLOB)) "
            f"BETWEEN 1 AND {MAX_MANUSCRIPT_JSON_BYTES} "
            "AND manuscript_json NOT GLOB '*[^ -~]*' AND json_valid(manuscript_json) "
            "AND json_type(manuscript_json)='object')",
            name='ck_memory_book_edition_manuscript_bytes'),
        CheckConstraint(
            "(state='current' AND manuscript_json IS NOT NULL) OR "
            "(state='source_invalidated' AND manuscript_json IS NULL)",
            name='ck_memory_book_edition_state_content'),
        CheckConstraint("state IN ('current','source_invalidated')",
                        name='ck_memory_book_edition_state'),
        CheckConstraint("length(job_result_sha256)=64 AND "
                        "job_result_sha256 NOT GLOB '*[^0-9a-f]*'",
                        name='ck_memory_book_edition_job_digest'),
        CheckConstraint("length(source_fingerprint)=64 AND "
                        "source_fingerprint NOT GLOB '*[^0-9a-f]*'",
                        name='ck_memory_book_edition_source_fingerprint'),
        CheckConstraint("length(request_digest)=64 AND "
                        "request_digest NOT GLOB '*[^0-9a-f]*'",
                        name='ck_memory_book_edition_request_digest'))
    Index('ix_memory_book_edition_book_revision', editions.c.book_id,
          editions.c.book_revision)
    Index('ix_memory_book_edition_library_created', editions.c.library_id,
          editions.c.created_at)

    sources = Table(SOURCES_TABLE, metadata,
        Column('edition_id', Text,
               ForeignKey(f'{EDITION_TABLE}.id', ondelete='CASCADE'),
               primary_key=True, nullable=False),
        Column('ordinal', Integer, primary_key=True, nullable=False),
        Column('source_id', Text, nullable=False),
        Column('kind', Text, nullable=False),
        Column('asset_id', Text),
        Column('source_digest', Text, nullable=False),
        Column('chapter_ids_json', Text, nullable=False),
        Column('contribution_id', Text,
               ForeignKey('access_memory_contributions.id', ondelete='CASCADE')),
        Column('contribution_story_id', Text,
               ForeignKey('access_memory_stories.id', ondelete='CASCADE')),
        UniqueConstraint('edition_id', 'source_id',
                         name='uq_memory_book_edition_source_id'),
        CheckConstraint(f'ordinal BETWEEN 0 AND {MAX_SOURCE_ROWS - 1}',
                        name='ck_memory_book_edition_source_ordinal'),
        CheckConstraint(f'length(CAST(source_id AS BLOB)) BETWEEN 1 AND {MAX_SOURCE_ID_BYTES}',
                        name='ck_memory_book_edition_source_id'),
        CheckConstraint("kind IN ('family','transcript','ai','editorial')",
                        name='ck_memory_book_edition_source_kind'),
        CheckConstraint(
            f"asset_id IS NULL OR length(CAST(asset_id AS BLOB)) BETWEEN 1 AND {MAX_ASSET_ID_BYTES}",
            name='ck_memory_book_edition_source_asset_id'),
        CheckConstraint("length(source_digest)=64 AND "
                        "source_digest NOT GLOB '*[^0-9a-f]*'",
                        name='ck_memory_book_edition_source_digest'),
        CheckConstraint(
            f"length(CAST(chapter_ids_json AS BLOB)) BETWEEN 1 AND {MAX_CHAPTER_IDS_JSON_BYTES} "
            "AND json_valid(chapter_ids_json) AND json_type(chapter_ids_json)='array'",
            name='ck_memory_book_edition_source_chapters'),
        CheckConstraint('(contribution_id IS NULL) = (contribution_story_id IS NULL)',
                        name='ck_memory_book_edition_contribution_pair'))
    Index('ix_memory_book_edition_source_contribution', sources.c.contribution_id,
          sources.c.contribution_story_id)

    _attach_triggers(editions, sources)
    return editions, sources


def add_book_edition_tables(metadata):
    """Add the two future edition tables to combined SQLAlchemy Metadata.

    Parent keys and any pre-existing edition definitions are validated. Exact
    reapplication is idempotent; partial or drifted tables fail closed. No
    database I/O, migration, or backfill is performed here.
    """
    from sqlalchemy import MetaData
    from sqlalchemy.schema import CreateIndex, CreateTable
    from sqlalchemy.dialects import sqlite

    _required_parents(metadata)
    expected = _expected_metadata()

    new_names = {EDITION_TABLE, SOURCES_TABLE}
    present = new_names & set(metadata.tables)
    if present and present != new_names:
        raise ValueError('book_edition_schema_partial_installation')

    dialect = sqlite.dialect()

    def schema_signature(table):
        ddl = str(CreateTable(table).compile(dialect=dialect))
        indexes = tuple(sorted(str(CreateIndex(index).compile(dialect=dialect))
                               for index in table.indexes))
        return ddl, indexes

    if present:
        for name in (EDITION_TABLE, SOURCES_TABLE):
            if schema_signature(metadata.tables[name]) != schema_signature(expected.tables[name]):
                raise ValueError('book_edition_schema_definition_mismatch')
        # Reapplying to exact existing tables must also install hooks if the
        # definitions were attached to metadata by another compatible builder.
        _attach_triggers(metadata.tables[EDITION_TABLE], metadata.tables[SOURCES_TABLE])
        return metadata.tables[EDITION_TABLE], metadata.tables[SOURCES_TABLE]

    editions, sources = _add_tables(metadata)
    return editions, sources


def _expected_metadata():
    """Build deterministic expected metadata without database access."""
    from sqlalchemy import Column, Integer, MetaData, Table, Text

    metadata = MetaData()
    Table('access_memory_books', metadata,
          Column('id', Text, primary_key=True), Column('library_id', Text))
    Table('access_memory_book_revisions', metadata,
          Column('book_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_libraries', metadata, Column('id', Text, primary_key=True))
    Table('access_accounts', metadata, Column('id', Text, primary_key=True))
    Table('access_memory_stories', metadata, Column('id', Text, primary_key=True))
    Table('access_memory_contributions', metadata,
          Column('id', Text, primary_key=True), Column('story_id', Text))
    _add_tables(metadata)
    return metadata


def sqlite_edition_schema_contract():
    """Return deterministic (kind, name, DDL) tuples for SQLite verification.

    The result describes expected definitions only. Calling this helper does
    not connect to a database, create tables, or enable the feature.
    """
    from sqlalchemy.schema import CreateIndex, CreateTable
    from sqlalchemy.dialects import sqlite

    metadata = _expected_metadata()
    dialect = sqlite.dialect()
    contract = []
    for name in (EDITION_TABLE, SOURCES_TABLE):
        table = metadata.tables[name]
        contract.append(('table', name, str(CreateTable(table).compile(dialect=dialect))))
        contract.extend(('index', index.name,
                         str(CreateIndex(index).compile(dialect=dialect)))
                        for index in table.indexes)
    contract.extend(('trigger', name, sql)
                    for name, sql in _trigger_statements().items())
    return tuple(sorted(contract))


def _trigger_statements():
    unchanged_columns = (
        'id', 'book_id', 'book_revision', 'library_id', 'creator_account_id',
        'originating_job_id', 'job_result_sha256', 'source_fingerprint',
        'context_profile', 'children_json', 'mutation_id', 'request_digest',
        'created_at',
    )
    unchanged = ' AND '.join(f'NEW.{name} IS OLD.{name}' for name in unchanged_columns)
    return {
        'trg_memory_book_edition_immutable': (
            f"CREATE TRIGGER IF NOT EXISTS trg_memory_book_edition_immutable "
            f"BEFORE UPDATE ON {EDITION_TABLE} WHEN NOT ("
            "OLD.state='current' AND NEW.state='source_invalidated' "
            "AND OLD.manuscript_json IS NOT NULL AND NEW.manuscript_json IS NULL AND "
            f'{unchanged}) '
            "BEGIN SELECT RAISE(ABORT, 'Reviewed memoir edition is immutable'); END"),
        'trg_memory_book_edition_sources_immutable': (
            f"CREATE TRIGGER IF NOT EXISTS trg_memory_book_edition_sources_immutable "
            f"BEFORE UPDATE ON {SOURCES_TABLE} "
            "BEGIN SELECT RAISE(ABORT, 'Reviewed memoir edition sources are immutable'); END"),
    }


def _attach_triggers(editions, sources):
    """Install SQLite immutability hooks, including on validated existing tables."""
    from sqlalchemy import DDL, event
    if not editions.info.get('memory_book_edition_immutable_hooks'):
        triggers = _trigger_statements()
        event.listen(editions, 'after_create', DDL(
            triggers['trg_memory_book_edition_immutable']
        ).execute_if(dialect='sqlite'))
        event.listen(editions, 'before_drop', DDL(
            'DROP TRIGGER IF EXISTS trg_memory_book_edition_immutable'
        ).execute_if(dialect='sqlite'))
        editions.info['memory_book_edition_immutable_hooks'] = True
    if not sources.info.get('memory_book_edition_source_immutable_hooks'):
        triggers = _trigger_statements()
        event.listen(sources, 'after_create', DDL(
            triggers['trg_memory_book_edition_sources_immutable']
        ).execute_if(dialect='sqlite'))
        event.listen(sources, 'before_drop', DDL(
            'DROP TRIGGER IF EXISTS trg_memory_book_edition_sources_immutable'
        ).execute_if(dialect='sqlite'))
        sources.info['memory_book_edition_source_immutable_hooks'] = True

"""Persistent ID-only asset-group tables used by explicit migration metadata.

Application startup executes no DDL. Real installations need the reviewed
additive migration before the default-off group domain can be enabled.
"""

from .photo_stack_schema import REVISION as PHOTO_STACK_REVISION

GROUP_REVISION = 'e7c1a9d5b304'
GROUP_REVISIONS = frozenset({GROUP_REVISION, PHOTO_STACK_REVISION})
TABLE = 'access_memory_groups'
REVISION_TABLE = 'access_memory_group_revisions'


def add_memory_group_tables(metadata):
    """Add the ID-only group tables to caller-owned migration metadata.

    No DDL is executed here. Callers decide whether and where to create these
    tables through the explicit additive migration.
    """
    from sqlalchemy import (CheckConstraint, Column, ForeignKey, Index, Integer,
                            Table, Text, UniqueConstraint)

    required = {
        'access_libraries': {'id'},
        'access_accounts': {'id'},
    }
    for name, columns in required.items():
        table = metadata.tables.get(name)
        if table is None or not columns <= set(table.c.keys()):
            raise ValueError('memory_group_schema_prerequisite_missing')

    groups = Table(TABLE, metadata,
        Column('id', Text, primary_key=True, nullable=False),
        Column('library_id', Text, ForeignKey('access_libraries.id'), nullable=False),
        Column('author_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('revision', Integer, nullable=False),
        Column('theme', Text, nullable=False),
        Column('asset_ids_json', Text, nullable=False),
        Column('excluded_asset_ids_json', Text, nullable=False),
        Column('source_story_ids_json', Text, nullable=False),
        Column('created_at', Integer, nullable=False),
        Column('updated_at', Integer, nullable=False),
        CheckConstraint('revision > 0', name='ck_memory_group_revision'),
        CheckConstraint("theme IN ('trip','growing_up','birthday','grandparents','year_in_review','everyday')",
                        name='ck_memory_group_theme'),
        CheckConstraint('length(CAST(asset_ids_json AS BLOB)) BETWEEN 1 AND 512',
                        name='ck_memory_group_assets_bytes'),
        CheckConstraint('length(CAST(excluded_asset_ids_json AS BLOB)) <= 16384',
                        name='ck_memory_group_exclusions_bytes'),
        CheckConstraint('length(CAST(source_story_ids_json AS BLOB)) <= 8192',
                        name='ck_memory_group_sources_bytes'))
    Index('ix_memory_group_library_updated', groups.c.library_id,
          groups.c.updated_at, groups.c.id)

    revisions = Table(REVISION_TABLE, metadata,
        Column('group_id', Text, ForeignKey(f'{TABLE}.id', ondelete='CASCADE'),
               primary_key=True, nullable=False),
        Column('revision', Integer, primary_key=True, nullable=False),
        Column('editor_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('mutation_id', Text, nullable=False),
        Column('request_digest', Text, nullable=False),
        Column('theme', Text, nullable=False),
        Column('asset_ids_json', Text, nullable=False),
        Column('excluded_asset_ids_json', Text, nullable=False),
        Column('source_story_ids_json', Text, nullable=False),
        Column('occurred_at', Integer, nullable=False),
        UniqueConstraint('editor_id', 'mutation_id',
                         name='uq_memory_group_editor_mutation'),
        CheckConstraint('revision > 0', name='ck_memory_group_revision_number'),
        CheckConstraint("theme IN ('trip','growing_up','birthday','grandparents','year_in_review','everyday')",
                        name='ck_memory_group_revision_theme'),
        CheckConstraint('length(CAST(asset_ids_json AS BLOB)) BETWEEN 1 AND 512',
                        name='ck_memory_group_revision_assets_bytes'),
        CheckConstraint('length(CAST(excluded_asset_ids_json AS BLOB)) <= 16384',
                        name='ck_memory_group_revision_exclusions_bytes'),
        CheckConstraint('length(CAST(source_story_ids_json AS BLOB)) <= 8192',
                        name='ck_memory_group_revision_sources_bytes'))
    Index('ix_memory_group_revision_mutation', revisions.c.editor_id,
          revisions.c.mutation_id, unique=True)
    return groups, revisions


def available(db):
    """Require the exact known table columns before using optional storage."""
    expected = {
        TABLE: (
            ('id', 'TEXT', 1, 1), ('library_id', 'TEXT', 1, 0),
            ('author_id', 'TEXT', 1, 0), ('revision', 'INTEGER', 1, 0),
            ('theme', 'TEXT', 1, 0), ('asset_ids_json', 'TEXT', 1, 0),
            ('excluded_asset_ids_json', 'TEXT', 1, 0),
            ('source_story_ids_json', 'TEXT', 1, 0),
            ('created_at', 'INTEGER', 1, 0), ('updated_at', 'INTEGER', 1, 0),
        ),
        REVISION_TABLE: (
            ('group_id', 'TEXT', 1, 1), ('revision', 'INTEGER', 1, 2),
            ('editor_id', 'TEXT', 1, 0), ('mutation_id', 'TEXT', 1, 0),
            ('request_digest', 'TEXT', 1, 0), ('theme', 'TEXT', 1, 0),
            ('asset_ids_json', 'TEXT', 1, 0),
            ('excluded_asset_ids_json', 'TEXT', 1, 0),
            ('source_story_ids_json', 'TEXT', 1, 0), ('occurred_at', 'INTEGER', 1, 0),
        ),
    }
    try:
        for table, signature in expected.items():
            rows = db.execute(f'PRAGMA table_info({table})').fetchall()
            actual = tuple((row[1], row[2].upper(), row[3], row[5]) for row in rows)
            if actual != signature:
                return False
        indexes = {row[1] for row in db.execute(f'PRAGMA index_list({REVISION_TABLE})')}
        if 'uq_memory_group_editor_mutation' not in indexes:
            # SQLite may name a SQLAlchemy unique constraint differently.
            unique_pairs = []
            for index in db.execute(f'PRAGMA index_list({REVISION_TABLE})'):
                if index[2]:
                    cols = tuple(row[2] for row in db.execute(
                        f'PRAGMA index_info("{index[1]}")'))
                    unique_pairs.append(cols)
            if ('editor_id', 'mutation_id') not in unique_pairs:
                return False
        return True
    except Exception:
        return False


def verify_memory_group_schema(db):
    """Public exact-signature check for the optional group tables."""
    return available(db)

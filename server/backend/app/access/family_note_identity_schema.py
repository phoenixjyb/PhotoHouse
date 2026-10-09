"""Additive, content-free original identities; never installed at startup.

No foreign key from an identity to deletable media/account/note records: the
identity and its scope history must survive content erasure and parent removal.
Existing C2 tables are deliberately unchanged. No legacy identity backfill.
"""
from __future__ import annotations

IDENTITY_REVISION = 'd1f6a8c3e920'
IDENTITIES = 'access_family_note_identities'
SCOPES = 'access_family_note_scopes'
EDITION_NOTES = 'access_memory_book_edition_family_notes'
IDENTITY_TABLES = frozenset({IDENTITIES, SCOPES, EDITION_NOTES})


def _tables(metadata):
    from sqlalchemy import (CheckConstraint, Column, ForeignKeyConstraint,
                            Index, Integer, Table, Text, UniqueConstraint)
    identities = Table(IDENTITIES, metadata,
        Column('identity_id', Text, primary_key=True, nullable=False),
        Column('note_id', Text, nullable=False),
        Column('asset_id', Integer, nullable=False),
        Column('author_id', Text, nullable=False),
        Column('origin_library_id', Text, nullable=False),
        Column('created_at', Integer, nullable=False),
        UniqueConstraint('note_id', name='uq_family_note_original_note'),
        CheckConstraint('length(identity_id)=36 AND length(note_id)=36 AND identity_id!=note_id',
                        name='ck_family_note_original_ids'),
        CheckConstraint('asset_id > 0 AND created_at >= 0', name='ck_family_note_original_numbers'),
        CheckConstraint('length(CAST(author_id AS BLOB)) BETWEEN 1 AND 128 AND '
                        'length(CAST(origin_library_id AS BLOB)) BETWEEN 1 AND 128',
                        name='ck_family_note_original_scope'))
    scopes = Table(SCOPES, metadata,
        Column('identity_id', Text, primary_key=True, nullable=False),
        Column('ordinal', Integer, primary_key=True, nullable=False),
        Column('from_library_id', Text),
        Column('library_id', Text, nullable=False),
        Column('plan_id', Text), Column('plan_digest', Text),
        Column('occurred_at', Integer, nullable=False),
        ForeignKeyConstraint(['identity_id'], [IDENTITIES + '.identity_id']),
        CheckConstraint('ordinal >= 0 AND occurred_at >= 0', name='ck_family_note_scope_numbers'),
        CheckConstraint('length(CAST(library_id AS BLOB)) BETWEEN 1 AND 128',
                        name='ck_family_note_scope_library'),
        CheckConstraint("(ordinal=0 AND from_library_id IS NULL AND plan_id IS NULL AND plan_digest IS NULL) OR "
                        "(ordinal>0 AND from_library_id IS NOT NULL AND from_library_id!=library_id "
                        "AND length(CAST(from_library_id AS BLOB)) BETWEEN 1 AND 128 "
                        "AND plan_id IS NOT NULL AND length(plan_id)=36 "
                        "AND plan_digest IS NOT NULL AND length(plan_digest)=64 "
                        "AND plan_digest NOT GLOB '*[^0-9a-f]*')", name='ck_family_note_scope_move'))
    refs = Table(EDITION_NOTES, metadata,
        Column('edition_id', Text, primary_key=True, nullable=False),
        Column('ordinal', Integer, primary_key=True, nullable=False),
        Column('identity_id', Text, nullable=False),
        Column('scope_ordinal', Integer, nullable=False),
        ForeignKeyConstraint(['edition_id', 'ordinal'],
            ['access_memory_book_edition_sources.edition_id',
             'access_memory_book_edition_sources.ordinal'], ondelete='CASCADE'),
        ForeignKeyConstraint(['identity_id', 'scope_ordinal'],
            [SCOPES + '.identity_id', SCOPES + '.ordinal']),
        CheckConstraint('ordinal BETWEEN 0 AND 95 AND scope_ordinal >= 0',
                        name='ck_memory_edition_family_note_ordinals'))
    Index('ix_memory_edition_family_note_identity', refs.c.identity_id, refs.c.edition_id)
    _attach(identities, scopes, refs)
    return identities, scopes, refs


def _triggers():
    sql = {}
    for table in (IDENTITIES, SCOPES):
        for operation in ('UPDATE', 'DELETE'):
            name = f'trg_{table}_{operation.lower()}'
            sql[name] = (f'CREATE TRIGGER IF NOT EXISTS {name} BEFORE {operation} ON {table} '
                         "BEGIN SELECT RAISE(ABORT, 'Family note lineage is immutable'); END")
    sql['trg_family_note_identity_insert'] = (
        f'CREATE TRIGGER IF NOT EXISTS trg_family_note_identity_insert BEFORE INSERT ON {IDENTITIES} '
        'WHEN NOT EXISTS (SELECT 1 FROM access_stories s WHERE s.id=NEW.note_id '
        'AND s.asset_id=NEW.asset_id AND s.author_id=NEW.author_id AND s.library_id=NEW.origin_library_id '
        'AND s.created_at=NEW.created_at AND s.revision=1 AND s.deleted=0) '
        "BEGIN SELECT RAISE(ABORT, 'Family note original unavailable'); END")
    sql['trg_family_note_scope_insert'] = (
        f'CREATE TRIGGER IF NOT EXISTS trg_family_note_scope_insert BEFORE INSERT ON {SCOPES} '
        f'WHEN NOT EXISTS (SELECT 1 FROM {IDENTITIES} i JOIN access_stories n ON n.id=i.note_id '
        'WHERE i.identity_id=NEW.identity_id AND n.asset_id=i.asset_id AND n.author_id=i.author_id AND '
        f'((NEW.ordinal=0 AND NEW.library_id=i.origin_library_id AND n.library_id=NEW.library_id '
        f'AND NOT EXISTS (SELECT 1 FROM {SCOPES} p WHERE p.identity_id=i.identity_id)) OR '
        f'(NEW.ordinal>0 AND NEW.from_library_id=n.library_id AND EXISTS (SELECT 1 FROM {SCOPES} p '
        'WHERE p.identity_id=i.identity_id AND p.ordinal=NEW.ordinal-1 AND p.library_id=NEW.from_library_id '
        f'AND p.ordinal=(SELECT max(q.ordinal) FROM {SCOPES} q WHERE q.identity_id=i.identity_id))))) '
        "BEGIN SELECT RAISE(ABORT, 'Family note scope history unavailable'); END")
    sql['trg_family_note_no_reuse'] = (
        'CREATE TRIGGER IF NOT EXISTS trg_family_note_no_reuse BEFORE INSERT ON access_stories '
        f'WHEN EXISTS (SELECT 1 FROM {IDENTITIES} WHERE note_id=NEW.id) '
        "BEGIN SELECT RAISE(ABORT, 'Family note original cannot be reused'); END")
    sql['trg_family_note_original_update'] = (
        'CREATE TRIGGER IF NOT EXISTS trg_family_note_original_update BEFORE UPDATE ON access_stories '
        f'WHEN (NEW.id IS NOT OLD.id AND EXISTS (SELECT 1 FROM {IDENTITIES} WHERE note_id=NEW.id)) OR '
        f'(EXISTS (SELECT 1 FROM {IDENTITIES} WHERE note_id=OLD.id) AND ('
        'NEW.id IS NOT OLD.id OR NEW.asset_id IS NOT OLD.asset_id OR NEW.author_id IS NOT OLD.author_id '
        'OR NEW.created_at IS NOT OLD.created_at OR '
        f'NOT EXISTS (SELECT 1 FROM {IDENTITIES} i JOIN {SCOPES} p ON p.identity_id=i.identity_id '
        'WHERE i.note_id=OLD.id AND p.library_id=NEW.library_id '
        f'AND p.ordinal=(SELECT max(q.ordinal) FROM {SCOPES} q WHERE q.identity_id=i.identity_id)))) '
        "BEGIN SELECT RAISE(ABORT, 'Family note original or scope changed'); END")
    sql['trg_memory_edition_family_note_update'] = (
        f'CREATE TRIGGER IF NOT EXISTS trg_memory_edition_family_note_update BEFORE UPDATE ON {EDITION_NOTES} '
        "BEGIN SELECT RAISE(ABORT, 'Family note edition binding is immutable'); END")
    sql['trg_memory_edition_family_note_insert'] = (
        f'CREATE TRIGGER IF NOT EXISTS trg_memory_edition_family_note_insert BEFORE INSERT ON {EDITION_NOTES} '
        f'WHEN NOT EXISTS (SELECT 1 FROM access_memory_book_edition_sources s '
        f'JOIN access_memory_book_editions e ON e.id=s.edition_id JOIN {IDENTITIES} i '
        f'ON s.source_id=\'family-\'||i.note_id JOIN {SCOPES} p ON p.identity_id=i.identity_id '
        'WHERE s.edition_id=NEW.edition_id AND s.ordinal=NEW.ordinal AND s.kind=\'family\' '
        'AND s.asset_id=CAST(i.asset_id AS TEXT) AND s.contribution_id IS NULL '
        'AND NEW.identity_id=i.identity_id AND NEW.scope_ordinal=p.ordinal '
        "AND p.library_id=e.library_id AND e.state='current') "
        "BEGIN SELECT RAISE(ABORT, 'Family note edition binding unavailable'); END")
    return sql


def _attach(*tables):
    from sqlalchemy import DDL, event
    identities, scopes, refs = tables
    targets = {name: identities for name in _triggers()}
    targets['trg_family_note_scope_insert'] = scopes
    targets['trg_' + SCOPES + '_update'] = scopes
    targets['trg_' + SCOPES + '_delete'] = scopes
    targets['trg_memory_edition_family_note_update'] = refs
    targets['trg_memory_edition_family_note_insert'] = refs
    for name, sql in _triggers().items():
        target = targets[name]
        if target.info.get(name):
            continue
        event.listen(target, 'after_create', DDL(sql).execute_if(dialect='sqlite'))
        event.listen(target, 'before_drop', DDL('DROP TRIGGER IF EXISTS ' + name).execute_if(dialect='sqlite'))
        target.info[name] = True


def add_family_note_identity_tables(metadata):
    from sqlalchemy.schema import CreateIndex, CreateTable
    from sqlalchemy.dialects.sqlite import dialect
    parent = metadata.tables.get('access_memory_book_edition_sources')
    if parent is None or {c.name for c in parent.primary_key.columns} != {'edition_id', 'ordinal'}:
        raise ValueError('family_note_identity_schema_prerequisite')
    present = IDENTITY_TABLES & set(metadata.tables)
    if present and present != IDENTITY_TABLES:
        raise ValueError('family_note_identity_schema_partial')
    if present:
        expected = _expected()
        for name in IDENTITY_TABLES:
            actual = metadata.tables[name]
            wanted = expected.tables[name]
            signature = lambda t: (str(CreateTable(t).compile(dialect=dialect())),
                sorted(str(CreateIndex(i).compile(dialect=dialect())) for i in t.indexes))
            if signature(actual) != signature(wanted):
                raise ValueError('family_note_identity_schema_mismatch')
        tables = tuple(metadata.tables[n] for n in (IDENTITIES, SCOPES, EDITION_NOTES))
        _attach(*tables)
        return tables
    return _tables(metadata)


def _expected():
    from sqlalchemy import Column, Integer, MetaData, Table, Text
    metadata = MetaData()
    Table('access_memory_book_edition_sources', metadata,
          Column('edition_id', Text, primary_key=True), Column('ordinal', Integer, primary_key=True))
    _tables(metadata)
    return metadata


def sqlite_family_note_identity_contract():
    from sqlalchemy.schema import CreateIndex, CreateTable
    from sqlalchemy.dialects.sqlite import dialect
    metadata = _expected()
    rows = []
    for name in IDENTITY_TABLES:
        table = metadata.tables[name]
        rows.append(('table', name, str(CreateTable(table).compile(dialect=dialect()))))
        rows.extend(('index', i.name, str(CreateIndex(i).compile(dialect=dialect()))) for i in table.indexes)
    rows.extend(('trigger', name, ddl) for name, ddl in _triggers().items())
    return tuple(sorted(rows))

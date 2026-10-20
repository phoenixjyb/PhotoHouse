"""Optional derived library stacks and private display choices; no startup DDL."""
REVISION = 'f2a8c5d1e640'
TABLES = ('access_photo_stack_indexes', 'access_photo_stack_groups',
          'access_photo_stack_members', 'access_photo_stack_preferences')


def add_photo_stack_tables(metadata):
    from sqlalchemy import (Table, Column, Text, Integer, ForeignKey,
                            ForeignKeyConstraint, CheckConstraint, UniqueConstraint, Index)
    indexes = Table(TABLES[0], metadata,
        Column('library_id', Text, ForeignKey('access_libraries.id'), primary_key=True, nullable=False),
        Column('generation', Text, nullable=False), Column('source_digest', Text, nullable=False), Column('asset_count', Integer, nullable=False),
        Column('built_at', Integer, nullable=False), CheckConstraint('asset_count BETWEEN 0 AND 100000'))
    groups = Table(TABLES[1], metadata,
        Column('library_id', Text, ForeignKey(TABLES[0]+'.library_id', ondelete='CASCADE'), primary_key=True, nullable=False),
        Column('group_id', Text, primary_key=True, nullable=False),
        Column('signature', Text, nullable=False), Column('anchor_id', Integer, ForeignKey('assets.id'), nullable=False),
        Column('reason', Text, nullable=False), Column('member_count', Integer, nullable=False),
        CheckConstraint("reason IN ('near_capture','same_upload')"),
        CheckConstraint('member_count BETWEEN 2 AND 24'))
    members = Table(TABLES[2], metadata,
        Column('library_id', Text, primary_key=True, nullable=False),
        Column('group_id', Text, nullable=False),
        Column('asset_id', Integer, ForeignKey('assets.id'), primary_key=True, nullable=False),
        Column('ordinal', Integer, nullable=False), Column('source_mime', Text, nullable=False),
        Column('source_taken_at', Text), Column('source_phash', Text, nullable=False),
        Column('source_account', Text), Column('source_batch', Text),
        ForeignKeyConstraint(['library_id','group_id'], [TABLES[1]+'.library_id', TABLES[1]+'.group_id'], ondelete='CASCADE'),
        UniqueConstraint('library_id','group_id','ordinal', name='uq_photo_stack_ordinal'),
        CheckConstraint('ordinal BETWEEN 0 AND 23'))
    Index('ix_photo_stack_group_members', members.c.library_id, members.c.group_id, members.c.ordinal)
    preferences = Table(TABLES[3], metadata,
        Column('library_id', Text, ForeignKey('access_libraries.id'), primary_key=True, nullable=False),
        Column('account_id', Text, ForeignKey('access_accounts.id'), primary_key=True, nullable=False),
        Column('revision', Integer, nullable=False), Column('choices_json', Text, nullable=False),
        Column('updated_at', Integer, nullable=False), CheckConstraint('revision > 0'),
        CheckConstraint('length(CAST(choices_json AS BLOB)) BETWEEN 1 AND 262144'))
    return indexes, groups, members, preferences


_COLUMNS = {
 TABLES[0]: (('library_id','TEXT',1,1),('generation','TEXT',1,0),('source_digest','TEXT',1,0),('asset_count','INTEGER',1,0),('built_at','INTEGER',1,0)),
 TABLES[1]: (('library_id','TEXT',1,1),('group_id','TEXT',1,2),('signature','TEXT',1,0),('anchor_id','INTEGER',1,0),('reason','TEXT',1,0),('member_count','INTEGER',1,0)),
 TABLES[2]: (('library_id','TEXT',1,1),('group_id','TEXT',1,0),('asset_id','INTEGER',1,2),('ordinal','INTEGER',1,0),('source_mime','TEXT',1,0),('source_taken_at','TEXT',0,0),('source_phash','TEXT',1,0),('source_account','TEXT',0,0),('source_batch','TEXT',0,0)),
 TABLES[3]: (('library_id','TEXT',1,1),('account_id','TEXT',1,2),('revision','INTEGER',1,0),('choices_json','TEXT',1,0),('updated_at','INTEGER',1,0)),
}


def available(db):
    # Exact signature gate; application startup never creates/mends these tables.
    return all(tuple((r[1],r[2].upper(),r[3],r[5]) for r in db.execute('PRAGMA table_info('+t+')')) == signature
               for t,signature in _COLUMNS.items())

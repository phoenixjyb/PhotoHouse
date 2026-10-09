"""Add revision-bound memoir transitions without historical backfill."""
from alembic import op
from sqlalchemy import Column, Integer, MetaData, Table, Text
from app.access.memory_book_editorial_schema import add_book_editorial_tables

revision = 'b1d7e4a9c230'
down_revision = 'a0c9d2e4f817'
branch_labels = None
depends_on = None


def upgrade():
    metadata = MetaData()
    Table('access_memory_book_revisions', metadata,
          Column('book_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_revisions', metadata,
          Column('story_id', Text, primary_key=True),
          Column('revision', Integer, primary_key=True))
    Table('access_memory_contributions', metadata,
          Column('id', Text, primary_key=True))
    editorial, refs = add_book_editorial_tables(metadata)
    editorial.create(op.get_bind())
    refs.create(op.get_bind())


def downgrade():
    bind = op.get_bind()
    for name in ('access_memory_book_editorial_refs', 'access_memory_book_editorial'):
        if bind.exec_driver_sql(f'SELECT 1 FROM {name} LIMIT 1').first() is not None:
            raise RuntimeError('Memoir editorial records require reviewed offline backup restoration')
    bind.exec_driver_sql('DROP TABLE access_memory_book_editorial_refs')
    bind.exec_driver_sql('DROP TABLE access_memory_book_editorial')

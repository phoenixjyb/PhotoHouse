"""Keep authorized contribution references beside immutable saved revisions."""
from alembic import op
from sqlalchemy import Column, Integer, MetaData, Table, Text

from app.access.memory_source_refs import add_source_ref_table

revision = 'a0c9d2e4f817'
down_revision = 'f7c3a9d2e614'
branch_labels = None
depends_on = None


def upgrade():
    metadata = MetaData()
    Table('access_memory_revisions', metadata,
        Column('story_id', Text, primary_key=True),
        Column('revision', Integer, primary_key=True))
    Table('access_memory_contributions', metadata,
        Column('id', Text, primary_key=True))
    add_source_ref_table(metadata).create(op.get_bind())


def downgrade():
    bind = op.get_bind()
    if bind.exec_driver_sql(
            'SELECT 1 FROM access_memory_contribution_refs LIMIT 1').first() is not None:
        raise RuntimeError('Contribution references require reviewed offline backup restoration')
    bind.exec_driver_sql('DROP TABLE access_memory_contribution_refs')

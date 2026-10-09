"""Add story contributions, book drafts and private conversation job records."""
from alembic import op
from sqlalchemy import Column, MetaData, Table, Text

from app.access.memory_collaboration_schema import add_collaboration_tables

revision = 'f7c3a9d2e614'
down_revision = 'e6b2f8a1c903'
branch_labels = None
depends_on = None


def upgrade():
    metadata = MetaData()
    for name in ('access_accounts', 'access_libraries', 'access_memory_stories'):
        Table(name, metadata, Column('id', Text, primary_key=True))
    tables = add_collaboration_tables(metadata)
    bind = op.get_bind()
    for table in tables:
        table.create(bind)


def downgrade():
    bind = op.get_bind()
    for name in (
        'access_original_deletion_state',
        'access_memory_turns',
        'access_memory_jobs',
        'access_memory_conversations',
        'access_memory_book_revisions',
        'access_memory_books',
        'access_memory_contribution_derivations',
        'access_memory_contributions',
    ):
        bind.exec_driver_sql('DROP TABLE ' + name)

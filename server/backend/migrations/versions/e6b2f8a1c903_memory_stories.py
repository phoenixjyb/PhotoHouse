"""Add private saved multi-asset story drafts and revision receipts."""
from alembic import op
from sqlalchemy import Column, MetaData, Table, Text
from app.access.memory_schema import add_memory_tables

revision = 'e6b2f8a1c903'
down_revision = 'd4a7e3c9b821'
branch_labels = None
depends_on = None


def upgrade():
    metadata = MetaData()
    for name in ('access_accounts', 'access_libraries'):
        Table(name, metadata, Column('id', Text, primary_key=True))
    for table in add_memory_tables(metadata):
        table.create(op.get_bind())


def downgrade():
    raise RuntimeError('Saved memory downgrade requires reviewed offline backup restoration')

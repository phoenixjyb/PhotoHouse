"""Add revisioned, ID-only private memory groups."""
from alembic import op

from app.access.memory_group_schema import REVISION_TABLE, TABLE
from app.access.metadata import migration_metadata
from app.db import Base

revision = 'e7c1a9d5b304'
down_revision = 'd1f6a8c3e920'
branch_labels = None
depends_on = None


def _tables():
    metadata = migration_metadata(Base.metadata)
    return metadata.tables[TABLE], metadata.tables[REVISION_TABLE]


def upgrade():
    bind = op.get_bind()
    for table in _tables():
        table.create(bind)


def downgrade():
    bind = op.get_bind()
    tables = _tables()
    # Check both current rows and revision history before dropping either table.
    # A partial downgrade must never remove group membership or its audit trail.
    if any(bind.exec_driver_sql(
            f'SELECT 1 FROM {table.name} LIMIT 1').first() is not None
            for table in tables):
        raise RuntimeError(
            'Memory group records require reviewed offline backup restoration')
    for table in reversed(tables):
        table.drop(bind)

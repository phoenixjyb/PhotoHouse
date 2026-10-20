"""Optional derived library-wide photo stacks and private display choices."""
from alembic import op
from app.access.metadata import migration_metadata
from app.access.photo_stack_schema import TABLES
from app.db import Base
revision = 'f2a8c5d1e640'
down_revision = 'e7c1a9d5b304'
branch_labels = None
depends_on = None


def upgrade():
    metadata = migration_metadata(Base.metadata)
    for name in TABLES:
        metadata.tables[name].create(op.get_bind())


def downgrade():
    bind = op.get_bind()
    if any(bind.exec_driver_sql('SELECT 1 FROM '+t+' LIMIT 1').first() is not None for t in TABLES):
        raise RuntimeError('Photo stack records require reviewed offline backup restoration')
    metadata = migration_metadata(Base.metadata)
    for name in reversed(TABLES):
        metadata.tables[name].drop(bind)

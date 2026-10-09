"""Content-free family note identity and scope ledger; no historical backfill."""
from alembic import op
from app.access.family_note_identity_schema import add_family_note_identity_tables
from app.access.metadata import migration_metadata
from app.db import Base

revision = 'd1f6a8c3e920'
down_revision = 'c2e6b8a1d490'
branch_labels = None
depends_on = None


def _tables():
    return add_family_note_identity_tables(migration_metadata(Base.metadata))


def upgrade():
    for table in _tables():
        table.create(op.get_bind())


def downgrade():
    tables = _tables()
    bind = op.get_bind()
    if any(bind.exec_driver_sql('SELECT 1 FROM ' + t.name + ' LIMIT 1').first() is not None for t in tables):
        raise RuntimeError('Family note lineage requires reviewed offline backup restoration')
    for table in reversed(tables):
        table.drop(bind)

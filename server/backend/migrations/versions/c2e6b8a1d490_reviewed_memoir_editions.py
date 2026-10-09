"""Add immutable reviewed memoir editions without historical backfill."""
from alembic import op

from app.access.memory_book_edition_schema import add_book_edition_tables
from app.access.metadata import migration_metadata
from app.db import Base

revision = 'c2e6b8a1d490'
down_revision = 'b1d7e4a9c230'
branch_labels = None
depends_on = None


def _edition_tables():
    metadata = migration_metadata(Base.metadata)
    return add_book_edition_tables(metadata)


def upgrade():
    editions, sources = _edition_tables()
    bind = op.get_bind()
    editions.create(bind)
    sources.create(bind)


def downgrade():
    bind = op.get_bind()
    for name in ('access_memory_book_editions', 'access_memory_book_edition_sources'):
        if bind.exec_driver_sql(f'SELECT 1 FROM {name} LIMIT 1').first() is not None:
            raise RuntimeError(
                'Reviewed memoir editions require reviewed offline backup restoration')

    editions, sources = _edition_tables()
    sources.drop(bind)
    editions.drop(bind)

"""Add private authored family upload annotations and versioned derived review rows."""
from alembic import op
from sqlalchemy import Column, Integer, MetaData, Table, Text
from app.access.annotation_schema import add_annotation_tables

revision = 'd4a7e3c9b821'
down_revision = 'c3f7a91d5e20'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    metadata = MetaData()
    Table('assets', metadata, Column('id', Integer, primary_key=True))
    Table('access_accounts', metadata, Column('id', Text, primary_key=True))
    Table('access_libraries', metadata, Column('id', Text, primary_key=True))
    originals, derivations, proposals = add_annotation_tables(metadata)
    originals.create(bind)
    derivations.create(bind)
    proposals.create(bind)
    # Authored source is immutable; new ASR/polish outputs receive later derivation revisions.
    op.execute('''CREATE TRIGGER trg_access_upload_annotations_immutable
        BEFORE UPDATE ON access_upload_annotations
        BEGIN SELECT RAISE(ABORT, 'Authored annotation is immutable'); END''')


def downgrade():
    raise RuntimeError('Family annotation downgrade requires reviewed offline backup restoration')

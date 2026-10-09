"""Add per-library member upload destination and owner auto-approval policy."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, Integer, MetaData, Table, Text
from app.access.upload_schema import add_upload_auto_policy_table

revision = 'c3f7a91d5e20'
down_revision = 'a8d4c2e6f901'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Helpers describe the current from-scratch schema, so a freshly migrated tree may
    # already contain these columns. Older deployed databases need the nullable ALTERs.
    upload_columns = {column['name'] for column in inspector.get_columns('access_uploads')}
    if 'destination_library_id' not in upload_columns:
        # SQLite's ALTER TABLE ADD COLUMN accepts an inline REFERENCES clause, while
        # Alembic op.add_column emits a separate unsupported ALTER for the FK.
        op.execute('ALTER TABLE access_uploads ADD COLUMN destination_library_id TEXT '
                   'REFERENCES access_libraries(id)')
    if 'approval_mode' not in upload_columns:
        op.execute("ALTER TABLE access_uploads ADD COLUMN approval_mode TEXT "
                   "CHECK (approval_mode IS NULL OR approval_mode IN ('manual','automatic'))")

    transfer_columns = {column['name'] for column in inspector.get_columns('access_upload_transfers')}
    if 'destination_library_id' not in transfer_columns:
        op.execute('ALTER TABLE access_upload_transfers ADD COLUMN destination_library_id TEXT '
                   'REFERENCES access_libraries(id)')

    if 'access_upload_auto_policies' not in set(inspector.get_table_names()):
        metadata = MetaData()
        Table('access_accounts', metadata, Column('id', Text, primary_key=True))
        Table('access_libraries', metadata, Column('id', Text, primary_key=True))
        add_upload_auto_policy_table(metadata).create(bind)


def downgrade():
    raise RuntimeError('Upload approval policy downgrade requires reviewed offline backup restoration')

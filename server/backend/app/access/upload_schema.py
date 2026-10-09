"""Migration-only schema for member uploads; no startup DDL.

An upload writes an `assets` row and this provenance row, and deliberately writes **no**
`access_asset_libraries` row: an incoming photo is in no library, so it is invisible to every
member until an operator promotes and assigns it.
"""
from sqlalchemy import CheckConstraint, Column, ForeignKey, Index, Integer, Table, Text, text


def add_upload_tables(metadata):
    """The provenance row for one accepted upload.

    `incoming_label` is *stored*, not derived. It is a path component, so it must not change
    when an account is renamed: recomputing it would either move a folder or leave the stored
    path pointing at a name that no longer matches.

    `asset_id` is unique, so one asset has at most one provenance row and a retried upload can
    be recognised rather than duplicated.
    """
    columns = [
        Column('id', Integer, primary_key=True, nullable=False),
        Column('asset_id', Integer, ForeignKey('assets.id'), nullable=False, unique=True),
        Column('account_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('incoming_label', Text, nullable=False),
        Column('batch', Text, nullable=False),
        Column('original_name', Text, nullable=False),
        Column('sha256', Text, nullable=False),
        Column('bytes', Integer, nullable=False),
        Column('state', Text, nullable=False),
        Column('created_at', Integer, nullable=False),
    ]
    # Older revision scripts construct this migration-only table from a minimal metadata
    # object containing only assets and accounts. Emit the new FK columns in the full schema
    # reflection (where access_libraries is present); the additive head revision adds them to
    # older databases.
    if 'access_libraries' in metadata.tables:
        columns.extend([
            Column('destination_library_id', Text, ForeignKey('access_libraries.id')),
            Column('approval_mode', Text),
        ])
    uploads = Table('access_uploads', metadata, *columns,
        CheckConstraint("state IN ('incoming','assigned')"),
        CheckConstraint('bytes >= 0'),
        *([CheckConstraint("approval_mode IS NULL OR approval_mode IN ('manual','automatic')")]
          if 'access_libraries' in metadata.tables else []))
    Index('ix_access_uploads_account', uploads.c.account_id, uploads.c.id)
    Index('ix_access_uploads_state', uploads.c.state, uploads.c.id)
    return [uploads]


def add_upload_auto_policy_table(metadata):
    """Owner policy for future uploads to one library from one member account.

    No row means manual approval. The owner identity is retained for each policy change.
    """
    table = Table('access_upload_auto_policies', metadata,
        Column('library_id', Text, ForeignKey('access_libraries.id'), primary_key=True, nullable=False),
        Column('account_id', Text, ForeignKey('access_accounts.id'), primary_key=True, nullable=False),
        Column('enabled', Integer, nullable=False, server_default=text('0')),
        Column('revision', Integer, nullable=False),
        Column('enabled_by', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('updated_at', Integer, nullable=False),
        CheckConstraint('enabled IN (0,1)'),
        CheckConstraint('revision > 0'))
    return table

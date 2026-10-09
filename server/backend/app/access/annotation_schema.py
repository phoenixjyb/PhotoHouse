"""Migration-only schema for private authored annotations and their derived review rows."""
from sqlalchemy import (CheckConstraint, Column, ForeignKey, Index, Integer,
                        LargeBinary, MetaData, Table, Text, UniqueConstraint)

MAX_ANNOTATION_AUDIO_BYTES = 2 * 1024 * 1024
MAX_ANNOTATION_TEXT_BYTES = 16 * 1024


def add_annotation_tables(metadata: MetaData):
    """Append immutable originals, versioned derivations and proposed tags.

    These tables are deliberately separate from captions and stories. Original text/audio is
    retained as authored; transcription and polishing produce later derivation rows.
    """
    originals = Table('access_upload_annotations', metadata,
        Column('id', Text, primary_key=True, nullable=False),
        Column('author_id', Text, ForeignKey('access_accounts.id'), nullable=False),
        Column('library_id', Text, ForeignKey('access_libraries.id'), nullable=False),
        Column('batch', Text, nullable=False),
        Column('asset_id', Integer, ForeignKey('assets.id')),
        Column('kind', Text, nullable=False),
        Column('original_text', Text),
        Column('original_audio', LargeBinary),
        Column('mime', Text),
        Column('duration_ms', Integer),
        Column('sha256', Text, nullable=False),
        Column('language', Text, nullable=False),
        Column('consent', Integer, nullable=False),
        Column('mutation_id', Text, nullable=False),
        Column('request_digest', Text, nullable=False),
        Column('created_at', Integer, nullable=False),
        UniqueConstraint('author_id', 'mutation_id'),
        CheckConstraint("kind IN ('text','audio')"),
        CheckConstraint("length(batch)=32 AND batch NOT GLOB '*[^0-9a-f]*'"),
        CheckConstraint("(kind='text' AND original_text IS NOT NULL AND length(trim(original_text)) > 0 AND length(CAST(original_text AS BLOB)) <= 16384 AND original_audio IS NULL AND mime IS NULL AND duration_ms IS NULL) OR (kind='audio' AND original_text IS NULL AND original_audio IS NOT NULL AND length(original_audio) BETWEEN 1 AND 2097152 AND mime='audio/wav' AND duration_ms > 0)"),
        CheckConstraint('consent IN (0,1)'),
        CheckConstraint("length(sha256)=64 AND sha256 NOT GLOB '*[^0-9a-f]*'"),
        CheckConstraint("length(request_digest)=64 AND request_digest NOT GLOB '*[^0-9a-f]*'"),
        CheckConstraint("length(mutation_id) BETWEEN 1 AND 128"),
        CheckConstraint('duration_ms IS NULL OR duration_ms > 0'),
        CheckConstraint("language IN ('en','zh','mixed','und')"),
        CheckConstraint('mime IS NULL OR length(mime) BETWEEN 1 AND 128'))
    Index('ix_access_upload_annotations_library_created',
          originals.c.library_id, originals.c.created_at, originals.c.id)
    Index('ix_access_upload_annotations_batch',
          originals.c.author_id, originals.c.library_id, originals.c.batch)

    derivations = Table('access_annotation_derivations', metadata,
        Column('annotation_id', Text, ForeignKey('access_upload_annotations.id'),
               primary_key=True, nullable=False),
        Column('revision', Integer, primary_key=True, nullable=False),
        Column('state', Text, nullable=False),
        Column('transcript', Text),
        Column('polished_text', Text),
        Column('provider', Text),
        Column('model', Text),
        Column('provider_version', Text),
        Column('model_version', Text),
        Column('error_code', Text),
        Column('created_at', Integer, nullable=False),
        Column('updated_at', Integer, nullable=False),
        Column('started_at', Integer),
        Column('finished_at', Integer),
        CheckConstraint('revision > 0'),
        CheckConstraint("state IN ('held','waiting','running','completed','failed','dead')"),
        CheckConstraint('started_at IS NULL OR started_at >= created_at'),
        CheckConstraint('finished_at IS NULL OR finished_at >= created_at'),
        CheckConstraint('length(error_code) <= 128 OR error_code IS NULL'),
        CheckConstraint('length(provider) <= 128 OR provider IS NULL'),
        CheckConstraint('length(model) <= 256 OR model IS NULL'),
        CheckConstraint('length(provider_version) <= 128 OR provider_version IS NULL'),
        CheckConstraint('length(model_version) <= 128 OR model_version IS NULL'))
    Index('ix_access_annotation_derivations_state_updated',
          derivations.c.state, derivations.c.updated_at, derivations.c.annotation_id)

    tag_proposals = Table('access_annotation_tag_proposals', metadata,
        Column('annotation_id', Text, ForeignKey('access_upload_annotations.id'),
               primary_key=True, nullable=False),
        Column('tag', Text, primary_key=True, nullable=False),
        Column('status', Text, nullable=False),
        Column('revision', Integer, primary_key=True, nullable=False),
        CheckConstraint("length(trim(tag)) BETWEEN 1 AND 128"),
        CheckConstraint("status IN ('proposed','accepted','rejected')"),
        CheckConstraint('revision > 0'))
    Index('ix_access_annotation_tag_proposals_status',
          tag_proposals.c.status, tag_proposals.c.annotation_id)
    return originals, derivations, tag_proposals

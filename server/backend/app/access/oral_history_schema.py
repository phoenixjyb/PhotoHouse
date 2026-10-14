"""Experimental oral-history tables; explicit generated-fixture installation only.

Not an Alembic migration or runtime initializer. The caller owns the transaction.
Production admission, withdrawal/replay and a transport must be qualified separately.
"""
import sqlite3

SESSION = 'access_oral_history_sessions'
SECTION = 'access_oral_history_sections'
MUTATION = 'access_oral_history_mutations'
MAX_SECTIONS = 180
MAX_SECTION_FRAMES = 20 * 16000
MAX_SECTION_BYTES = 44 + MAX_SECTION_FRAMES * 2
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_TOTAL_FRAMES = 3600 * 16000
MAX_SESSIONS_PER_AUTHOR = 8

STATEMENTS = (
    f'''CREATE TABLE {SESSION} (
        id TEXT PRIMARY KEY NOT NULL,
        library_id TEXT NOT NULL REFERENCES access_libraries(id),
        author_id TEXT NOT NULL REFERENCES access_accounts(id),
        title TEXT NOT NULL CHECK(length(CAST(title AS BLOB)) BETWEEN 1 AND 512),
        subject_label TEXT NOT NULL CHECK(length(CAST(subject_label AS BLOB)) <= 512),
        narrator_label TEXT NOT NULL CHECK(length(CAST(narrator_label AS BLOB)) <= 256),
        language TEXT NOT NULL CHECK(language IN ('zh','en','mixed','und')),
        processing_consent INTEGER NOT NULL CHECK(processing_consent IN (0,1)),
        state TEXT NOT NULL CHECK(state IN ('open','completed','cancelled')),
        revision INTEGER NOT NULL CHECK(revision > 0),
        section_count INTEGER NOT NULL CHECK(section_count BETWEEN 0 AND {MAX_SECTIONS}),
        total_bytes INTEGER NOT NULL CHECK(total_bytes BETWEEN 0 AND {MAX_TOTAL_BYTES}),
        total_frames INTEGER NOT NULL CHECK(total_frames BETWEEN 0 AND {MAX_TOTAL_FRAMES}),
        manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64 AND manifest_sha256 NOT GLOB '*[^0-9a-f]*'),
        created_at INTEGER NOT NULL CHECK(created_at >= 0)
    )''',
    f'''CREATE INDEX ix_oral_history_author ON {SESSION}(author_id,library_id,id)''',
    f'''CREATE TABLE {SECTION} (
        session_id TEXT NOT NULL REFERENCES {SESSION}(id),
        ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 0 AND {MAX_SECTIONS - 1}),
        start_frame INTEGER NOT NULL CHECK(start_frame >= 0),
        frames INTEGER NOT NULL CHECK(frames BETWEEN 1 AND {MAX_SECTION_FRAMES}),
        byte_count INTEGER NOT NULL CHECK(byte_count=44+frames*2 AND byte_count <= {MAX_SECTION_BYTES}),
        audio BLOB NOT NULL CHECK(length(audio)=byte_count),
        sha256 TEXT NOT NULL CHECK(length(sha256)=64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
        parent_manifest TEXT NOT NULL CHECK(length(parent_manifest)=64 AND parent_manifest NOT GLOB '*[^0-9a-f]*'),
        manifest_sha256 TEXT NOT NULL CHECK(length(manifest_sha256)=64 AND manifest_sha256 NOT GLOB '*[^0-9a-f]*'),
        created_at INTEGER NOT NULL CHECK(created_at >= 0),
        PRIMARY KEY(session_id,ordinal)
    )''',
    f'''CREATE TABLE {MUTATION} (
        author_id TEXT NOT NULL REFERENCES access_accounts(id),
        request_id TEXT NOT NULL,
        session_id TEXT NOT NULL REFERENCES {SESSION}(id),
        operation TEXT NOT NULL CHECK(operation IN ('create','append','complete','cancel')),
        request_digest TEXT NOT NULL CHECK(length(request_digest)=64 AND request_digest NOT GLOB '*[^0-9a-f]*'),
        receipt_json TEXT NOT NULL CHECK(length(CAST(receipt_json AS BLOB)) BETWEEN 1 AND 16384),
        receipt_sha256 TEXT NOT NULL CHECK(length(receipt_sha256)=64 AND receipt_sha256 NOT GLOB '*[^0-9a-f]*'),
        PRIMARY KEY(author_id,request_id)
    )''',
    f'''CREATE TRIGGER oral_history_session_identity BEFORE UPDATE ON {SESSION}
        WHEN NEW.id IS NOT OLD.id OR NEW.library_id IS NOT OLD.library_id
        OR NEW.author_id IS NOT OLD.author_id OR NEW.title IS NOT OLD.title
        OR NEW.subject_label IS NOT OLD.subject_label OR NEW.narrator_label IS NOT OLD.narrator_label
        OR NEW.language IS NOT OLD.language OR NEW.processing_consent IS NOT OLD.processing_consent
        OR NEW.created_at IS NOT OLD.created_at
        BEGIN SELECT RAISE(ABORT,'oral_history_identity_immutable'); END''',
    f'''CREATE TRIGGER oral_history_session_transition BEFORE UPDATE ON {SESSION}
        WHEN OLD.state != 'open' OR NEW.revision != OLD.revision+1 OR NOT (
            (NEW.state='open' AND NEW.section_count=OLD.section_count+1 AND EXISTS (
                SELECT 1 FROM {SECTION} p WHERE p.session_id=OLD.id AND p.ordinal=OLD.section_count
                AND p.start_frame=OLD.total_frames AND p.frames=NEW.total_frames-OLD.total_frames
                AND p.byte_count=NEW.total_bytes-OLD.total_bytes
                AND p.parent_manifest=OLD.manifest_sha256 AND p.manifest_sha256=NEW.manifest_sha256))
            OR (NEW.state IN ('completed','cancelled') AND NEW.section_count=OLD.section_count
                AND NEW.total_frames=OLD.total_frames AND NEW.total_bytes=OLD.total_bytes
                AND NEW.manifest_sha256=OLD.manifest_sha256
                AND (NEW.state='cancelled' OR OLD.section_count > 0)))
        BEGIN SELECT RAISE(ABORT,'oral_history_transition_invalid'); END''',
    f'''CREATE TRIGGER oral_history_section_insert BEFORE INSERT ON {SECTION}
        WHEN NOT EXISTS (SELECT 1 FROM {SESSION} s WHERE s.id=NEW.session_id
            AND s.state='open' AND s.section_count=NEW.ordinal AND s.total_frames=NEW.start_frame
            AND s.manifest_sha256=NEW.parent_manifest)
        BEGIN SELECT RAISE(ABORT,'oral_history_section_order_invalid'); END''',
    f'''CREATE TRIGGER oral_history_session_delete BEFORE DELETE ON {SESSION}
        BEGIN SELECT RAISE(ABORT,'oral_history_erasure_unqualified'); END''',
    *(f'''CREATE TRIGGER oral_history_{kind}_{op.lower()} BEFORE {op} ON {table}
        BEGIN SELECT RAISE(ABORT,'oral_history_source_immutable'); END'''
      for kind, table in (('section', SECTION), ('mutation', MUTATION))
      for op in ('UPDATE', 'DELETE')),
)


def _definition(statement):
    words = statement.split()
    return words[2], statement.strip()


EXPECTED = dict(_definition(s) for s in STATEMENTS)


def assert_schema(db):
    """Verify every owned table/index/trigger; never install or repair it."""
    try:
        rows = db.execute('SELECT name,sql FROM sqlite_master WHERE tbl_name IN (?,?,?)',
                          (SESSION, SECTION, MUTATION)).fetchall()
        actual = {name: sql.strip() for name, sql in rows if sql is not None}
        if (actual != EXPECTED or db.execute('PRAGMA foreign_keys').fetchone()[0] != 1
                or db.execute('PRAGMA ignore_check_constraints').fetchone()[0] != 0):
            raise ValueError('oral_history_schema_unavailable')
    except sqlite3.DatabaseError:
        raise ValueError('oral_history_schema_unavailable') from None


def install_fixture_schema(db):
    """Explicit additive fixture DDL, no commit/backfill/migration or live admission."""
    if not db.in_transaction or db.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        raise ValueError('oral_history_schema_requires_owned_transaction')
    for name in ('access_accounts', 'access_libraries'):
        columns = list(db.execute(f'PRAGMA table_info({name})'))
        keys = [r for r in columns if r[5]]
        if len(keys) != 1 or keys[0][1] != 'id' or keys[0][2].upper() != 'TEXT' or keys[0][5] != 1:
            raise ValueError('oral_history_schema_prerequisite_missing')
    present = {r[0] for r in db.execute('SELECT name FROM sqlite_master')}
    if present & set(EXPECTED):
        assert_schema(db)
        return
    # Savepoint avoids a partial install if any DDL fails; the outer commit is caller-owned.
    db.execute('SAVEPOINT oral_history_fixture_schema')
    try:
        for statement in STATEMENTS:
            db.execute(statement)
        assert_schema(db)
        db.execute('RELEASE oral_history_fixture_schema')
    except BaseException:
        db.execute('ROLLBACK TO oral_history_fixture_schema')
        db.execute('RELEASE oral_history_fixture_schema')
        raise

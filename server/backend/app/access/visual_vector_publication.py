"""Optional, guarded publication of immutable derived image vectors.

This internal coordinator does not authorize an upload or qualify a provider.
Its trusted worker must supply a guard that rechecks the exact task claim,
approval, source and library inside the supplied SQLite writer transaction.
The finalizer completes that same task in the transaction which records the
ready artifact. The coordinator owns a dedicated SQLite connection and its
callback authorizer; callers must not share it with another authorizer owner.
Neither optional schema is installed automatically.

Intents are committed before file writes. Recovery visits only known pending
intents, never scans arbitrary files or invokes a model. File bytes are synced;
directory entries are synced on POSIX. Windows power-loss durability requires
separate filesystem qualification; the recovery protocol covers process death.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields, replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import stat

from .visual_candidates import UNIT_NORM_TOLERANCE, VectorSpaceIdentity, canonical_vector_checksum
from .visual_vector_artifacts import ImmutableVectorArtifact, validate_artifact
from .visual_vector_loader import _checked_root, _decode_npy, _is_reparse, _read_vector, _root_snapshot, _same_file
from .visual_vector_schema import _normalized, verify_visual_vector_schema


_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TABLE = "image_vector_publications"
_MAX_BYTES = 64 * 1024
_ARTIFACT_FIELDS = tuple(field.name for field in fields(ImmutableVectorArtifact))


class VectorPublicationRefused(ValueError):
    def __init__(self):
        super().__init__("Vector publication unavailable")


@dataclass(frozen=True)
class VectorRecoveryResult:
    record_id: str
    status: str


def _contract():
    return (
        ("table", _TABLE, f"""CREATE TABLE IF NOT EXISTS {_TABLE} (
            record_id TEXT NOT NULL PRIMARY KEY
                CHECK(length(record_id)=64 AND record_id NOT GLOB '*[^0-9a-f]*'),
            asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE RESTRICT CHECK(asset_id>0),
            claim_sha256 TEXT NOT NULL
                CHECK(length(claim_sha256)=64 AND claim_sha256 NOT GLOB '*[^0-9a-f]*'),
            artifact_json TEXT NOT NULL CHECK(length(artifact_json)<=4096),
            state TEXT NOT NULL CHECK(state IN ('prepared','committed')),
            created_at INTEGER NOT NULL CHECK(created_at>=0)
        )"""),
        ("index", "uq_image_vector_publication_claim",
         f"CREATE UNIQUE INDEX IF NOT EXISTS uq_image_vector_publication_claim ON {_TABLE}(claim_sha256)"),
        ("trigger", "trg_image_vector_publication_binding",
         f"""CREATE TRIGGER IF NOT EXISTS trg_image_vector_publication_binding BEFORE UPDATE ON {_TABLE}
             WHEN OLD.state!='prepared' OR NEW.state!='committed'
               OR NEW.record_id IS NOT OLD.record_id OR NEW.asset_id IS NOT OLD.asset_id
               OR NEW.claim_sha256 IS NOT OLD.claim_sha256 OR NEW.artifact_json IS NOT OLD.artifact_json
               OR NEW.created_at IS NOT OLD.created_at
             BEGIN SELECT RAISE(ABORT,'Image vector publication binding is immutable'); END"""),
        ("trigger", "trg_image_vector_publication_delete",
         f"CREATE TRIGGER IF NOT EXISTS trg_image_vector_publication_delete BEFORE DELETE ON {_TABLE} "
         "BEGIN SELECT RAISE(ABORT,'Image vector publication binding is immutable'); END"),
    )


def create_visual_publication_schema(db) -> None:
    """Create only the optional intent contract in a supplied synthetic DB."""
    for _kind, _name, sql in _contract():
        db.execute(sql)


def verify_visual_publication_schema(db) -> bool:
    """Verify exact required intent objects without changing schema or rows."""
    try:
        for kind, name, sql in _contract():
            row = db.execute("SELECT type,sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
            if row is None or row[0] != kind or _normalized(row[1]) != _normalized(sql):
                return False
        for kind in ("index", "trigger"):
            actual = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type=? AND tbl_name=? AND sql IS NOT NULL",
                (kind, _TABLE))}
            if actual != {name for expected_kind, name, _sql in _contract() if expected_kind == kind}:
                return False
        return True
    except (AttributeError, sqlite3.Error, TypeError, ValueError):
        return False


def _encoding(record):
    return json.dumps(asdict(record), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _artifact(raw, expected_identity):
    try:
        if type(raw) is not str or len(raw) > 4096:
            raise VectorPublicationRefused()
        value = json.loads(raw)
        if type(value) is not dict or set(value) != set(_ARTIFACT_FIELDS):
            raise VectorPublicationRefused()
        record = ImmutableVectorArtifact(**value)
        if not validate_artifact(record, expected_identity) or _encoding(record) != raw:
            raise VectorPublicationRefused()
        return record
    except (TypeError, ValueError, RecursionError) as error:
        raise VectorPublicationRefused() from error


def _valid_vector(vector, record):
    try:
        return (vector is not None
                and canonical_vector_checksum(vector) == record.component_sha256
                and abs(math.sqrt(math.fsum(value * value for value in vector)) - 1.0)
                <= UNIT_NORM_TOLERANCE)
    except (TypeError, ValueError, OverflowError):
        return False


def _valid_raw(raw, record):
    return (type(raw) is bytes and 0 < len(raw) <= _MAX_BYTES
            and hashlib.sha256(raw).hexdigest() == record.file_sha256
            and _valid_vector(_decode_npy(raw, record.dimension), record))


def _directory(root, *parts):
    if _checked_root(root) is None:
        raise VectorPublicationRefused()
    current = root
    for part in parts:
        current = current / part
        try:
            current.mkdir()
        except FileExistsError:
            pass
        info = current.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or _is_reparse(info) or _root_snapshot(current) is None):
            raise VectorPublicationRefused()
    return current


def _sync_directory(path):
    if os.name == "nt":
        # Python's directory fsync is not portable to Windows. Do not infer
        # power-loss durability from a successful process-crash replay.
        return
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _paths(root, record):
    stage_dir = _directory(root, "image-vectors", ".staging")
    final_dir = _directory(root, "image-vectors", record.identity_sha256)
    return stage_dir / f"{record.record_id}.npy", final_dir / f"{record.record_id}.npy"


def _valid_file(root, path, record):
    probe = replace(record, relative_path=path.relative_to(root).as_posix())
    return _valid_vector(_read_vector(root, probe), record)


def _settle_link(root, stage, target, record):
    """Handle only the known stage/final hardlink left by interrupted publish."""
    if not os.path.lexists(target) or not os.path.lexists(stage):
        return
    left, right = stage.lstat(), target.lstat()
    if (not stat.S_ISREG(left.st_mode) or not stat.S_ISREG(right.st_mode)
            or stat.S_ISLNK(left.st_mode) or stat.S_ISLNK(right.st_mode)
            or _is_reparse(left) or _is_reparse(right)):
        raise VectorPublicationRefused()
    if (left.st_dev, left.st_ino) != (right.st_dev, right.st_ino):
        # Two independent complete copies are permitted; validate separately.
        return
    if left.st_nlink != 2 or right.st_nlink != 2:
        raise VectorPublicationRefused()
    # _read_vector deliberately refuses nlink=2. Verify the bounded descriptor
    # contents before removing this exact stage link, then use its ordinary
    # nlink=1 integrity check on the surviving final file.
    ancestry = _root_snapshot(stage.parent)
    final_ancestry = _root_snapshot(target.parent)
    if ancestry is None or final_ancestry is None:
        raise VectorPublicationRefused()
    descriptor = os.open(stage, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino, opened.st_nlink) != (left.st_dev, left.st_ino, 2):
            raise VectorPublicationRefused()
        if not 0 < opened.st_size <= _MAX_BYTES:
            raise VectorPublicationRefused()
        chunks, remaining = [], opened.st_size + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 8192))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if not _valid_raw(b"".join(chunks), record):
            raise VectorPublicationRefused()
        if (_root_snapshot(stage.parent) != ancestry
                or _root_snapshot(target.parent) != final_ancestry
                or not _same_file(opened, os.fstat(descriptor))):
            raise VectorPublicationRefused()
        after_stage, after_target = stage.lstat(), target.lstat()
        if ((after_stage.st_dev, after_stage.st_ino, after_stage.st_nlink)
                != (opened.st_dev, opened.st_ino, 2)
                or (after_target.st_dev, after_target.st_ino, after_target.st_nlink)
                != (opened.st_dev, opened.st_ino, 2)
                or not _same_file(opened, after_stage) or not _same_file(opened, after_target)):
            raise VectorPublicationRefused()
    finally:
        os.close(descriptor)
    # Close before unlink for Windows handles which do not share deletion.
    if (not _same_file(opened, stage.lstat()) or not _same_file(opened, target.lstat())
            or _root_snapshot(stage.parent) != ancestry
            or _root_snapshot(target.parent) != final_ancestry):
        raise VectorPublicationRefused()
    stage.unlink()
    _sync_directory(stage.parent)


class VectorPublicationStore:
    """Internal guarded coordinator; callers provide real worker authorization."""

    def __init__(self, db, root: Path, expected_identity: VectorSpaceIdentity, *, guard, finalize):
        if not callable(guard) or not callable(finalize):
            raise VectorPublicationRefused()
        self.db, self.root, self.expected_identity = db, root, expected_identity
        self.guard, self.finalize = guard, finalize

    @contextmanager
    def _transaction(self):
        if self.db.in_transaction or self.db.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise VectorPublicationRefused()
        try:
            self.db.execute("BEGIN IMMEDIATE")
            if not verify_visual_vector_schema(self.db) or not verify_visual_publication_schema(self.db):
                raise VectorPublicationRefused()
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _callback(self, callback, record, claim, *, read_only):
        # A callback cannot split ready-row/task/journal atomicity by committing
        # early. Guard callbacks are reads only; finalizers may change task rows.
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ,
                   sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
        if not read_only:
            allowed.update((sqlite3.SQLITE_INSERT, sqlite3.SQLITE_UPDATE, sqlite3.SQLITE_DELETE))
        self.db.set_authorizer(lambda action, *_args:
                               sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        try:
            return callback(self.db, record, claim)
        finally:
            self.db.set_authorizer(None)

    def _guard(self, record, claim):
        # A completed withdrawal also fences future writes after cleanup releases
        # its SQLite reservation. This invariant cannot be weakened by a callback.
        parent = self.db.execute("SELECT status FROM assets WHERE id=?",
                                 (int(record.asset_id),)).fetchone()
        if parent is None or parent[0] not in (None, "active"):
            raise VectorPublicationRefused()
        if self._callback(self.guard, record, claim, read_only=True) is not True:
            raise VectorPublicationRefused()

    def _intent(self, record_id):
        if type(record_id) is not str or _SHA.fullmatch(record_id) is None:
            raise VectorPublicationRefused()
        row = self.db.execute(f"SELECT asset_id,claim_sha256,artifact_json,state,created_at FROM {_TABLE} WHERE record_id=?",
                              (record_id,)).fetchone()
        if row is None:
            raise VectorPublicationRefused()
        record = _artifact(row[2], self.expected_identity)
        if (type(row[0]) is not int or str(row[0]) != record.asset_id or record.record_id != record_id
                or type(row[1]) is not str or _SHA.fullmatch(row[1]) is None
                or row[3] not in ("prepared", "committed") or type(row[4]) is not int
                or row[4] != record.created_at):
            raise VectorPublicationRefused()
        self._guard(record, row[1])
        return record, row[1], row[3]

    def _ready(self, record):
        row = self.db.execute("SELECT " + ",".join(_ARTIFACT_FIELDS)
                              + " FROM image_vector_artifacts WHERE record_id=?", (record.record_id,)).fetchone()
        if row is None:
            return False
        values = list(row)
        if type(values[1]) is not int:
            raise VectorPublicationRefused()
        values[1] = str(values[1])
        if ImmutableVectorArtifact(*values) != record:
            raise VectorPublicationRefused()
        return True

    def prepare(self, record: ImmutableVectorArtifact, claim_sha256: str) -> str:
        if (not validate_artifact(record, self.expected_identity) or type(claim_sha256) is not str
                or _SHA.fullmatch(claim_sha256) is None):
            raise VectorPublicationRefused()
        with self._transaction():
            self._guard(record, claim_sha256)
            existing = self.db.execute(f"SELECT artifact_json,claim_sha256,state FROM {_TABLE} WHERE record_id=?",
                                       (record.record_id,)).fetchone()
            if existing:
                if existing[0] != _encoding(record) or existing[1] != claim_sha256:
                    raise VectorPublicationRefused()
                if existing[2] == "committed" and not self._ready(record):
                    raise VectorPublicationRefused()
                return existing[2]
            if self.db.execute("SELECT 1 FROM image_vector_artifacts WHERE asset_id=? AND source_sha256=? AND identity_sha256=?",
                               (int(record.asset_id), record.source_sha256, record.identity_sha256)).fetchone():
                raise VectorPublicationRefused()
            self.db.execute(f"INSERT INTO {_TABLE} VALUES (?,?,?,?,?,?)",
                            (record.record_id, int(record.asset_id), claim_sha256,
                             _encoding(record), "prepared", record.created_at))
        return "prepared"

    def _complete(self, record, claim):
        # The caller's guard has already run under this writer reservation.
        if self._ready(record):
            raise VectorPublicationRefused()  # A ready row with a pending intent is inconsistent.
        values = [getattr(record, name) for name in _ARTIFACT_FIELDS]
        values[1] = int(record.asset_id)
        self.db.execute("INSERT INTO image_vector_artifacts (" + ",".join(_ARTIFACT_FIELDS)
                        + ") VALUES (" + ",".join("?" for _ in values) + ")", values)
        self._callback(self.finalize, record, claim, read_only=False)
        if not self.db.in_transaction:
            raise VectorPublicationRefused()  # Callbacks must not commit/rollback.
        changed = self.db.execute(f"UPDATE {_TABLE} SET state='committed' WHERE record_id=? AND state='prepared'",
                                  (record.record_id,)).rowcount
        if changed != 1:
            raise VectorPublicationRefused()

    def _publish_locked(self, record, claim, raw):
        if not isinstance(self.root, Path) or _checked_root(self.root) is None:
            raise VectorPublicationRefused()
        if raw is not None and not _valid_raw(raw, record):
            raise VectorPublicationRefused()
        stage, target = _paths(self.root, record)
        _settle_link(self.root, stage, target, record)
        if os.path.lexists(target):
            if not _valid_file(self.root, target, record):
                raise VectorPublicationRefused()
            if os.path.lexists(stage):
                if not _valid_file(self.root, stage, record):
                    raise VectorPublicationRefused()
                stage.unlink()
                _sync_directory(stage.parent)
        else:
            if not os.path.lexists(stage):
                if raw is None:
                    raise VectorPublicationRefused()
                with stage.open("xb") as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                _sync_directory(stage.parent)
            if not _valid_file(self.root, stage, record):
                raise VectorPublicationRefused()
            # Same-volume no-overwrite publication. A crash can leave both links;
            # recovery accepts nlink=2 only for these exact two validated paths.
            os.link(stage, target, follow_symlinks=False)
            _sync_directory(target.parent)
            _settle_link(self.root, stage, target, record)
            if not _valid_file(self.root, target, record):
                raise VectorPublicationRefused()
        self._complete(record, claim)
        return "committed"

    def publish(self, record_id: str, raw: bytes) -> str:
        with self._transaction():
            record, claim, state = self._intent(record_id)
            if state == "committed":
                if not self._ready(record) or not _valid_raw(raw, record):
                    raise VectorPublicationRefused()
                if not _valid_file(self.root, self.root / record.relative_path, record):
                    raise VectorPublicationRefused()
                return "committed"
            return self._publish_locked(record, claim, raw)

    def recover_record(self, record_id: str) -> str:
        """Recover one explicitly bound intent without inference or a scan.

        The trusted worker supplies the original claim guard. Missing/partial
        bytes and revoked claims remain unavailable; this never resets tasks.
        """
        with self._transaction():
            record, claim, state = self._intent(record_id)
            if state == "committed":
                if (not self._ready(record)
                        or not _valid_file(self.root, self.root / record.relative_path, record)):
                    raise VectorPublicationRefused()
                return "committed"
            return self._publish_locked(record, claim, None)

    def recover(self, limit: int = 32, *, after_record_id: str | None = None) -> tuple[VectorRecoveryResult, ...]:
        """Advance a bounded pending-only pass even past unavailable intents."""
        if (type(limit) is not int or not 1 <= limit <= 128
                or (after_record_id is not None and
                    (type(after_record_id) is not str or _SHA.fullmatch(after_record_id) is None))):
            raise VectorPublicationRefused()
        with self._transaction():
            ids = tuple(row[0] for row in self.db.execute(
                f"SELECT record_id FROM {_TABLE} WHERE state='prepared' AND record_id>? ORDER BY record_id LIMIT ?",
                (after_record_id or "", limit)))
        results = []
        for record_id in ids:
            try:
                with self._transaction():
                    record, claim, state = self._intent(record_id)
                    if state == "committed":
                        if not self._ready(record):
                            raise VectorPublicationRefused()
                    else:
                        self._publish_locked(record, claim, None)
                status = "committed"
            except Exception:
                status = "unavailable"
            results.append(VectorRecoveryResult(record_id, status))
        return tuple(results)

"""Optional receipt-bound erasure of known immutable vector files.

The dedicated primary connection serializes publication and cleanup. Plans are
committed before filesystem changes. An exclusive hard link claims each private
quarantine name without overwriting; recovery accepts only the recorded inode
and complete vector bytes at known names. Metadata, task claims and originals
are retained. This is an internal maintenance contract, not a route or migration.
Windows directory durability and ACL inheritance require native qualification.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat

from .original_deletions import OriginalDeletionError, OriginalDeletionJournal
from .private_storage import require_private_directory, sync_directory
from .visual_vector_cleanup import MAX_CLEANUP_ARTIFACTS, _COLUMNS, _validated_artifact
from .visual_vector_loader import _checked_root, _is_reparse, _root_snapshot, _same_file
from .visual_vector_publication import (
    _artifact, _valid_raw, verify_visual_publication_schema,
)
from .visual_vector_schema import _normalized, verify_visual_vector_schema


_TABLE = "image_vector_erasures"
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_MANIFEST = 2 * 1024 * 1024


class VectorErasureRefused(ValueError):
    def __init__(self):
        super().__init__("Vector erasure unavailable")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value):
    return hashlib.sha256(_json(value).encode("ascii")).hexdigest()


def _contract():
    return (
        ("table", _TABLE, f"""CREATE TABLE IF NOT EXISTS {_TABLE} (
            job_id TEXT NOT NULL PRIMARY KEY CHECK(length(job_id)=64 AND job_id NOT GLOB '*[^0-9a-f]*'),
            asset_id INTEGER NOT NULL UNIQUE REFERENCES assets(id) ON DELETE RESTRICT CHECK(asset_id>0),
            manifest_json TEXT NOT NULL CHECK(length(manifest_json)<={_MAX_MANIFEST}),
            total_files INTEGER NOT NULL CHECK(total_files BETWEEN 0 AND 256),
            next_file INTEGER NOT NULL CHECK(next_file BETWEEN 0 AND total_files)
        )"""),
        ("trigger", "trg_image_vector_erasure_progress", f"""CREATE TRIGGER IF NOT EXISTS
            trg_image_vector_erasure_progress BEFORE UPDATE ON {_TABLE}
            WHEN NEW.job_id IS NOT OLD.job_id OR NEW.asset_id IS NOT OLD.asset_id
              OR NEW.manifest_json IS NOT OLD.manifest_json OR NEW.total_files IS NOT OLD.total_files
              OR NEW.next_file!=OLD.next_file+1
            BEGIN SELECT RAISE(ABORT,'Image vector erasure binding is immutable'); END"""),
        ("trigger", "trg_image_vector_erasure_delete", f"""CREATE TRIGGER IF NOT EXISTS
            trg_image_vector_erasure_delete BEFORE DELETE ON {_TABLE}
            BEGIN SELECT RAISE(ABORT,'Image vector erasure binding is immutable'); END"""),
    )


def create_visual_erasure_schema(db):
    """Create the optional contract only on an explicitly supplied synthetic DB."""
    for _kind, _name, ddl in _contract():
        db.execute(ddl)


def verify_visual_erasure_schema(db):
    try:
        for kind, name, ddl in _contract():
            row = db.execute("SELECT type,sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
            if row is None or row[0] != kind or _normalized(row[1]) != _normalized(ddl):
                return False
        triggers = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (_TABLE,))}
        indexes = list(db.execute("SELECT name FROM sqlite_master WHERE type='index' "
                                  "AND tbl_name=? AND sql IS NOT NULL", (_TABLE,)))
        return triggers == {name for kind, name, _ in _contract() if kind == "trigger"} and not indexes
    except (AttributeError, sqlite3.Error, TypeError, ValueError):
        return False


def _file_binding(info):
    # Linking/unlinking changes POSIX ctime and link count, not content identity.
    # Windows birthtime remains stable; refuse if the native API omits it.
    binding = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]
    if os.name == "nt":
        birth = getattr(info, "st_birthtime_ns", None)
        if type(birth) is not int:
            raise VectorErasureRefused()
        binding.append(birth)
    return binding


def _path(root, relative):
    """Check every known lexical parent; absence never causes directory creation."""
    parts = Path(relative).parts
    if not parts or Path(relative).is_absolute() or ".." in parts:
        raise VectorErasureRefused()
    current = root
    for part in parts[:-1]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            return None
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
            raise VectorErasureRefused()
    return root.joinpath(*parts)


def _inspect(root, relative, record):
    path = _path(root, relative)
    if path is None:
        return None
    try:
        before = path.lstat()
    except FileNotFoundError:
        return None
    if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
            or _is_reparse(before) or not 0 < before.st_size <= 64 * 1024):
        raise VectorErasureRefused()
    ancestry = _root_snapshot(path.parent)
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    try:
        opened = os.fstat(fd)
        if not _same_file(before, opened) or opened.st_nlink != before.st_nlink:
            raise VectorErasureRefused()
        chunks, remaining = [], opened.st_size + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 8192))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = path.lstat()
        if (ancestry is None or _root_snapshot(path.parent) != ancestry
                or not _same_file(opened, os.fstat(fd)) or not _same_file(opened, after)
                or after.st_nlink != opened.st_nlink or not _valid_raw(b"".join(chunks), record)):
            raise VectorErasureRefused()
        return _file_binding(opened), opened.st_nlink
    finally:
        os.close(fd)


class VectorErasureStore:
    """Dedicated-connection coordinator for a committed V3 asset withdrawal.

    The root must be private and owned by the maintenance identity. All trusted
    publishers share the primary writer reservation and deny deleted parents.
    Concurrent same-owner filesystem editing is outside this maintenance scope.
    """

    def __init__(self, db, root: Path, journal):
        if not isinstance(journal, OriginalDeletionJournal):
            raise VectorErasureRefused()
        self.db, self.root, self.journal = db, root, journal
        self._owned = False

    @contextmanager
    def _transaction(self):
        try:
            if (self.db.in_transaction
                    or self.db.execute("PRAGMA foreign_keys").fetchone()[0] != 1
                    or self.db.execute("PRAGMA synchronous").fetchone()[0] != 2):
                raise VectorErasureRefused()
            self.db.execute("BEGIN IMMEDIATE")
            self._owned = True
            if not verify_visual_erasure_schema(self.db):
                raise VectorErasureRefused()
            yield
            self.db.commit()
        except BaseException as error:
            # Never roll back a transaction which belongs to our caller.
            if getattr(self, "_owned", False):
                self.db.rollback()
            if isinstance(error, (OSError, sqlite3.Error, ValueError, TypeError, AttributeError,
                                  KeyError, IndexError, RecursionError, OriginalDeletionError)):
                raise VectorErasureRefused() from None
            raise
        finally:
            self._owned = False

    def _root(self):
        if _checked_root(self.root) is None:
            raise VectorErasureRefused()
        require_private_directory(self.root)
        snapshot = _root_snapshot(self.root)
        if snapshot is None:
            raise VectorErasureRefused()
        return {"path_sha256": hashlib.sha256(str(self.root).encode("utf-8")).hexdigest(),
                "ancestors": [list(item) for item in snapshot]}

    def _metadata(self, asset_id):
        receipt = self.journal.asset_record(self.db, asset_id)
        if not verify_visual_vector_schema(self.db) or not verify_visual_publication_schema(self.db):
            raise VectorErasureRefused()
        rows = self.db.execute(f"SELECT {_COLUMNS} FROM image_vector_artifacts WHERE asset_id=? "
                               "ORDER BY record_id LIMIT 129", (asset_id,)).fetchall()
        intents = self.db.execute("SELECT record_id,asset_id,claim_sha256,artifact_json,state,created_at "
                                  "FROM image_vector_publications WHERE asset_id=? "
                                  "ORDER BY record_id LIMIT 129", (asset_id,)).fetchall()
        if len(rows) > MAX_CLEANUP_ARTIFACTS or len(intents) > MAX_CLEANUP_ARTIFACTS:
            raise VectorErasureRefused()
        ready = {row[0]: _validated_artifact(row, asset_id) for row in rows}
        records = dict(ready)
        paths = {record.relative_path: record.record_id for record in ready.values()}
        for record_id, parent, claim, raw, state, created in intents:
            record = _artifact(raw, None)
            if (type(parent) is not int or parent != asset_id or record.asset_id != str(asset_id)
                    or record.record_id != record_id or type(claim) is not str or not _SHA.fullmatch(claim)
                    or type(created) is not int or record.created_at != created
                    or state not in ("prepared", "committed")
                    or (state == "committed" and ready.get(record_id) != record)
                    or (state == "prepared" and record_id in ready)
                    or (record_id in records and records[record_id] != record)):
                raise VectorErasureRefused()
            records[record_id] = record
            paths[record.relative_path] = record_id
            paths[f"image-vectors/.staging/{record_id}.npy"] = record_id
        if len(records) > MAX_CLEANUP_ARTIFACTS:
            raise VectorErasureRefused()
        return {"receipt": receipt, "ready": [asdict(ready[key]) for key in sorted(ready)],
                "intents": [list(row) for row in intents]}, records, sorted(paths.items())

    def _preflight(self, manifest, progress):
        if self._root() != manifest["root"]:
            raise VectorErasureRefused()
        metadata, records, paths = self._metadata(manifest["asset_id"])
        if metadata != manifest["metadata"] or paths != [tuple(item) for item in manifest["paths"]]:
            raise VectorErasureRefused()
        job_id = _digest(manifest)
        for relative in ("image-vectors/.erasing", f"image-vectors/.erasing/{job_id}"):
            selected = _path(self.root, relative)
            if selected is not None and os.path.lexists(selected):
                require_private_directory(selected)
                if selected.stat().st_dev != self.root.stat().st_dev:
                    raise VectorErasureRefused()
        observed = []
        for index, (relative, record_id) in enumerate(paths):
            quarantine = f"image-vectors/.erasing/{job_id}/{index:03d}.npy"
            for name in (relative, quarantine):
                value = _inspect(self.root, name, records[record_id])
                binding = manifest["bindings"][index]
                if value is not None and (index < progress or binding is None or value[0] != binding):
                    raise VectorErasureRefused()
                if value is not None:
                    observed.append((index, name, value))
        self._links(observed)
        return records

    @staticmethod
    def _links(observed):
        groups = {}
        for index, name, (binding, links) in observed:
            key = tuple(binding[:2])
            groups.setdefault(key, []).append((index, name, binding, links))
        for group in groups.values():
            # Only stage/final of one record and their quarantine claims can
            # share an inode; all names must be in this complete bounded plan.
            if any(item[3] != len(group) or item[2] != group[0][2] for item in group):
                raise VectorErasureRefused()

    def prepare(self, asset_id: int) -> str:
        """Commit a complete immutable plan; reads files but never creates paths."""
        if type(asset_id) is not int or not 1 <= asset_id <= 2**63 - 1:
            raise VectorErasureRefused()
        with self._transaction():
            existing = self.db.execute(f"SELECT job_id FROM {_TABLE} WHERE asset_id=?", (asset_id,)).fetchone()
            if existing:
                manifest, progress = self._load(existing[0])
                self._preflight(manifest, progress)
                return existing[0]
            metadata, records, paths = self._metadata(asset_id)
            root = self._root()
            bindings, observed = [], []
            for index, (relative, record_id) in enumerate(paths):
                value = _inspect(self.root, relative, records[record_id])
                if value and value[0][0] != self.root.stat().st_dev:
                    raise VectorErasureRefused()
                bindings.append(value[0] if value else None)
                if value:
                    observed.append((index, relative, value))
            self._links(observed)
            # The only allowed initial alias is one publication's stage/final.
            for left in observed:
                for right in observed:
                    if left[0] != right[0] and left[2][0][:2] == right[2][0][:2]:
                        if paths[left[0]][1] != paths[right[0]][1]:
                            raise VectorErasureRefused()
            manifest = {"version": 1, "asset_id": asset_id, "metadata": metadata,
                        "root": root, "paths": paths, "bindings": bindings}
            raw, job_id = _json(manifest), _digest(manifest)
            if len(raw) > _MAX_MANIFEST:
                raise VectorErasureRefused()
            for index in range(len(paths)):
                quarantine = f"image-vectors/.erasing/{job_id}/{index:03d}.npy"
                selected = _path(self.root, quarantine)
                if selected is not None and os.path.lexists(selected):
                    raise VectorErasureRefused()
            # Existing quarantine collisions must be refused before saving a plan.
            self._preflight(manifest, 0)
            self.db.execute(f"INSERT INTO {_TABLE} VALUES (?,?,?,?,0)",
                            (job_id, asset_id, raw, len(paths)))
        return job_id

    def _load(self, job_id):
        if type(job_id) is not str or not _SHA.fullmatch(job_id):
            raise VectorErasureRefused()
        row = self.db.execute(f"SELECT asset_id,manifest_json,total_files,next_file FROM {_TABLE} WHERE job_id=?",
                              (job_id,)).fetchone()
        if row is None or type(row[1]) is not str or len(row[1]) > _MAX_MANIFEST:
            raise VectorErasureRefused()
        manifest = json.loads(row[1])
        if (type(manifest) is not dict
                or set(manifest) != {"version", "asset_id", "metadata", "root", "paths", "bindings"}
                or type(manifest["version"]) is not int or manifest["version"] != 1
                or type(manifest["asset_id"]) is not int or manifest["asset_id"] != row[0]
                or _json(manifest) != row[1] or _digest(manifest) != job_id
                or type(manifest["paths"]) is not list or type(manifest["bindings"]) is not list
                or len(manifest["paths"]) != row[2] or len(manifest["bindings"]) != row[2]
                or type(row[2]) is not int or type(row[3]) is not int
                or not 0 <= row[3] <= row[2] <= 256):
            raise VectorErasureRefused()
        return manifest, row[3]

    def _quarantine(self, job_id):
        current = self.root
        for part in ("image-vectors", ".erasing", job_id):
            current /= part
            try:
                current.mkdir(mode=0o700)
                sync_directory(current.parent)
            except FileExistsError:
                pass
            if _checked_root(current) is None:
                raise VectorErasureRefused()
            # Ordinary publication directories may be 0755 under the private
            # root. Require owner-only quarantine directories, not that parent.
            if part != "image-vectors":
                require_private_directory(current)
            if current.stat().st_dev != self.root.stat().st_dev:
                raise VectorErasureRefused()
        return current

    def step(self, job_id: str) -> bool:
        """Process one known file; True means all planned names are absent."""
        with self._transaction():
            manifest, index = self._load(job_id)
            self._preflight(manifest, index)
            if index == len(manifest["paths"]):
                return True
            relative, _record_id = manifest["paths"][index]
            source = self.root / relative
            destination = self._quarantine(job_id) / f"{index:03d}.npy"
            # Recheck the whole bounded cohort after creating private parents.
            self._preflight(manifest, index)
            if os.path.lexists(source) and not os.path.lexists(destination):
                # Atomic destination creation: never replace an existing file.
                os.link(source, destination, follow_symlinks=False)
                sync_directory(destination.parent)
            self._preflight(manifest, index)
            if os.path.lexists(source):
                source.unlink()
                sync_directory(source.parent)
            self._preflight(manifest, index)
            if os.path.lexists(destination):
                destination.unlink()
                sync_directory(destination.parent)
            self._preflight(manifest, index + 1)
            changed = self.db.execute(f"UPDATE {_TABLE} SET next_file=next_file+1 "
                                      "WHERE job_id=? AND next_file=?", (job_id, index)).rowcount
            if changed != 1:
                raise VectorErasureRefused()
            return index + 1 == len(manifest["paths"])

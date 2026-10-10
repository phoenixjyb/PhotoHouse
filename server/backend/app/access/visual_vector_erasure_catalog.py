"""Private, database-independent recovery copies of reviewed erasure plans.

No directory discovery or overwriting is allowed. The caller supplies a reviewed
job digest and an existing private directory. A partial interrupted archive is
refused; cleanup must not begin until the complete file has been synced and
verified. Windows power-loss qualification remains separate.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re

from .private_storage import require_private_directory, require_private_file, sync_directory
from .visual_vector_loader import _checked_root, _root_snapshot, _same_file


MAX_MANIFEST_BYTES = 2 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class VectorCatalogRefused(ValueError):
    def __init__(self):
        super().__init__("Vector recovery catalog unavailable")


def encode_manifest(manifest):
    return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def manifest_digest(manifest):
    return hashlib.sha256(encode_manifest(manifest).encode("ascii")).hexdigest()


def validate_manifest(raw, job_id):
    """Validate the canonical envelope; the store verifies every semantic binding."""
    try:
        if (type(raw) is not str or len(raw) > MAX_MANIFEST_BYTES
                or type(job_id) is not str or _SHA.fullmatch(job_id) is None):
            raise VectorCatalogRefused()
        manifest = json.loads(raw)
        if (type(manifest) is not dict
                or set(manifest) != {"version", "asset_id", "metadata", "root", "paths", "bindings"}
                or type(manifest["version"]) is not int or manifest["version"] != 1
                or type(manifest["asset_id"]) is not int or not 1 <= manifest["asset_id"] <= 2**63-1
                or type(manifest["metadata"]) is not dict or type(manifest["root"]) is not dict
                or type(manifest["paths"]) is not list or type(manifest["bindings"]) is not list
                or len(manifest["paths"]) != len(manifest["bindings"])
                or len(manifest["paths"]) > 256 or encode_manifest(manifest) != raw
                or manifest_digest(manifest) != job_id):
            raise VectorCatalogRefused()
        return manifest
    except (TypeError, ValueError, UnicodeError, RecursionError, KeyError):
        raise VectorCatalogRefused() from None


class VectorErasureCatalog:
    def __init__(self, private_directory: Path):
        self.root = private_directory
        self._root()

    def _root(self):
        if _checked_root(self.root) is None:
            raise VectorCatalogRefused()
        require_private_directory(self.root)
        snapshot = _root_snapshot(self.root)
        if snapshot is None:
            raise VectorCatalogRefused()
        return snapshot

    def read(self, job_id: str):
        """Read only this exact bounded digest-named archive, without a scan."""
        try:
            if type(job_id) is not str or _SHA.fullmatch(job_id) is None:
                raise VectorCatalogRefused()
            ancestry = self._root()
            target = self.root / f"{job_id}.json"
            require_private_file(target)
            before = target.lstat()
            if not 0 < before.st_size <= MAX_MANIFEST_BYTES + 1:
                raise VectorCatalogRefused()
            fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
            try:
                opened = os.fstat(fd)
                if not _same_file(before, opened) or opened.st_nlink != 1:
                    raise VectorCatalogRefused()
                chunks, remaining = [], opened.st_size + 1
                while remaining:
                    chunk = os.read(fd, min(remaining, 8192))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                raw = b"".join(chunks)
                if (len(raw) != opened.st_size or self._root() != ancestry
                        or not _same_file(opened, os.fstat(fd))
                        or not _same_file(opened, target.lstat())):
                    raise VectorCatalogRefused()
            finally:
                os.close(fd)
            if not raw.endswith(b"\n"):
                raise VectorCatalogRefused()
            return validate_manifest(raw[:-1].decode("ascii"), job_id)
        except (OSError, TypeError, ValueError, AttributeError, UnicodeError):
            raise VectorCatalogRefused() from None

    def archive(self, manifest) -> str:
        """Sync a new complete copy; never repair or overwrite an existing file."""
        try:
            raw = encode_manifest(manifest)
            job_id = manifest_digest(manifest)
            validate_manifest(raw, job_id)
            ancestry = self._root()
            target = self.root / f"{job_id}.json"
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
            try:
                fd = os.open(target, flags, 0o600)
            except FileExistsError:
                if self.read(job_id) != manifest:
                    raise VectorCatalogRefused()
                # A previous process may have died after writing complete bytes
                # but before its fsync. A successful retry must sync them too.
                before = target.lstat()
                fd = os.open(target, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
                try:
                    if not _same_file(before, os.fstat(fd)):
                        raise VectorCatalogRefused()
                    os.fsync(fd)
                    if not _same_file(before, target.lstat()):
                        raise VectorCatalogRefused()
                finally:
                    os.close(fd)
                sync_directory(self.root)
                if self._root() != ancestry or self.read(job_id) != manifest:
                    raise VectorCatalogRefused()
                return job_id
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw.encode("ascii") + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            sync_directory(self.root)
            if self._root() != ancestry or self.read(job_id) != manifest:
                raise VectorCatalogRefused()
            return job_id
        except (OSError, TypeError, ValueError, AttributeError, UnicodeError):
            raise VectorCatalogRefused() from None

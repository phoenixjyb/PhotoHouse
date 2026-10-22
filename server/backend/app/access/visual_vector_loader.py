"""Library-scoped, read-only loading of prepared image vectors.

The loader has no model/provider integration and never consults legacy indexes.
It resolves current library authorization and the complete bounded artifact
cohort in one SQLite snapshot before touching any vector file.
"""
from __future__ import annotations

import ast
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct

from .service import AccessDenied, AccessService
from .private_storage import stable_stat_identity
from .visual_candidates import (
    MAX_CANDIDATES,
    MAX_DIMENSION,
    UNAVAILABLE,
    AuthorizationSnapshot,
    RankingResult,
    VectorRecord,
    VectorSpaceIdentity,
    canonical_vector_checksum,
    rank_visual_candidates,
)
from .visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256, validate_artifact
from .visual_vector_schema import verify_visual_vector_schema


_ASSET_ID = re.compile(r"[1-9][0-9]{0,18}\Z", re.ASCII)
_LIBRARY_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)
_MAX_FILE_BYTES = 64 * 1024
_MAX_HEADER_BYTES = 4096
_COLUMNS = (
    "record_id,asset_id,source_sha256,model_name,artifact_sha256,preprocessing_sha256,"
    "vector_space_id,model_version,dimension,normalization,identity_sha256,relative_path,"
    "file_sha256,component_sha256,created_at,status"
)
_VECTOR_COLUMNS = ",".join(f"v.{column.strip()}" for column in _COLUMNS.split(","))


class VisualVectorReads:
    """Load and rank a complete, authorized image-vector cohort.

    ``vector_root`` is the explicit root beneath which immutable
    ``image-vectors/<identity>/<record>.npy`` artifacts are stored.
    """

    def __init__(self, service: AccessService, vector_root: Path,
                 expected_identity: VectorSpaceIdentity):
        self.service = service
        self.vector_root = vector_root
        self.expected_identity = expected_identity

    def candidates(self, token, library_id, seed_ids) -> RankingResult:
        """Return IDs only, or the fixed unavailable result for any bad cohort."""
        return self._read(token, library_id, seed_ids)

    def memory_group(self, token, library_id, seed_ids, *, excluded_ids=()):
        """Read qualified vectors and propose capture-proximate group members."""
        return self._read(token, library_id, seed_ids, grouping=True, excluded_ids=excluded_ids)

    def memory_group_items(self, token, library_id, seed_ids, *, excluded_ids=()):
        """Hydrate proposal thumbnails in the same authorization snapshot."""
        return self._read(token, library_id, seed_ids, grouping=True,
                          excluded_ids=excluded_ids, present_items=True)

    def _read(self, token, library_id, seed_ids, *, grouping=False, excluded_ids=(),
              present_items=False):
        from .memory_grouping import UNAVAILABLE as GROUP_UNAVAILABLE, propose_memory_group
        unavailable = GROUP_UNAVAILABLE if grouping else UNAVAILABLE
        capture_column = ",a.taken_at" if grouping else ""
        metadata_size = 2 if grouping else 1
        with self.service._transaction():
            # Do not inspect caller IDs, paths, schema, or artifact storage until
            # the current membership policy has approved this library read.
            self.service._require(token, library_id, "library.read")
            try:
                if (type(library_id) is not str or _LIBRARY_ID.fullmatch(library_id) is None
                        or type(seed_ids) not in (tuple, list)
                        or not 1 <= len(seed_ids) <= 24
                        or any(type(item) is not str or _ASSET_ID.fullmatch(item) is None
                               or int(item) > 2**63 - 1 for item in seed_ids)
                        or len(set(seed_ids)) != len(seed_ids)
                        or not _valid_identity(self.expected_identity)
                        or not _valid_root_argument(self.vector_root)):
                    return unavailable

                db = self.service.db
                seed_marks = ",".join("?" for _ in seed_ids)
                seed_rows = db.execute(
                    f"""SELECT a.id,a.mime,a.hash_sha256{capture_column} FROM assets a
                        JOIN access_asset_libraries scope ON scope.asset_id=a.id
                        WHERE scope.library_id=? AND a.id IN ({seed_marks})
                          AND (a.status IS NULL OR a.status='active')""",
                    (library_id, *seed_ids),
                ).fetchall()
                seed_by_id = {str(row[0]): row for row in seed_rows}
                # A missing/inactive/unmapped ID is a non-enumerating denial.
                if set(seed_by_id) != set(seed_ids):
                    raise AccessDenied("Access denied")
                # This loader is explicitly image-only. Do not probe vector schema
                # or paths for a video/non-image seed.
                if any(type(row[1]) is not str or not row[1].startswith("image/")
                       for row in seed_by_id.values()):
                    return unavailable

                expected_digest = identity_sha256(self.expected_identity)
                if not verify_visual_vector_schema(db):
                    return unavailable

                seed_artifact_rows = db.execute(
                    f"SELECT {_COLUMNS} FROM image_vector_artifacts WHERE asset_id IN ({seed_marks}) "
                    "AND status='ready' AND identity_sha256=? ORDER BY asset_id",
                    (*seed_ids, expected_digest),
                ).fetchall()

                candidate_artifact_rows = db.execute(
                    f"""SELECT {_VECTOR_COLUMNS},a.hash_sha256{capture_column} FROM image_vector_artifacts v
                        JOIN assets a ON a.id=v.asset_id
                        JOIN access_asset_libraries scope ON scope.asset_id=a.id
                        WHERE scope.library_id=? AND (a.status IS NULL OR a.status='active')
                          AND a.mime GLOB 'image/*' AND v.status='ready'
                          AND v.identity_sha256=? AND v.asset_id NOT IN ({seed_marks})
                        ORDER BY v.asset_id LIMIT ?""",
                    (library_id, expected_digest, *seed_ids, MAX_CANDIDATES + 1),
                ).fetchall()
                if len(candidate_artifact_rows) > MAX_CANDIDATES:
                    return unavailable

                # Convert and validate every row, including the current source
                # hash and one-record-per-asset coverage, before any filesystem
                # operation. A corrupt tail cannot produce a partial ranking.
                seed_records = _validated_rows(seed_artifact_rows, self.expected_identity)
                candidate_records = _validated_rows(
                    [row[:-metadata_size] for row in candidate_artifact_rows], self.expected_identity
                )
                if len(seed_records) != len(seed_ids) or set(seed_records) != set(seed_ids):
                    return unavailable
                if any(seed_by_id[asset_id][2] != artifact.source_sha256
                       for asset_id, artifact in seed_records.items()):
                    return unavailable
                if len(candidate_records) != len(candidate_artifact_rows):
                    return unavailable
                # The candidate SQL's last field is the current asset digest.
                for row in candidate_artifact_rows:
                    artifact = _artifact_from_row(row[:-metadata_size])
                    if artifact is None or row[-metadata_size] != artifact.source_sha256:
                        return unavailable

                root = _checked_root(self.vector_root)
                if root is None:
                    return unavailable
                all_artifacts = list(seed_records.values()) + list(candidate_records.values())
                vectors: dict[str, VectorRecord] = {}
                for artifact in all_artifacts:
                    vector = _read_vector(root, artifact)
                    if vector is None:
                        return unavailable
                    try:
                        component_hash = canonical_vector_checksum(vector)
                    except (OverflowError, TypeError, ValueError):
                        return unavailable
                    if component_hash != artifact.component_sha256:
                        return unavailable
                    vectors[artifact.asset_id] = VectorRecord(
                        asset_id=artifact.asset_id,
                        identity=self.expected_identity,
                        vector=vector,
                        checksum_sha256=component_hash,
                    )

                seed_vector_records = tuple(vectors[item] for item in seed_ids)
                candidate_ids = tuple(candidate_records)
                candidate_vector_records = tuple(vectors[item] for item in candidate_ids)
                authorized_ids = frozenset((*seed_ids, *candidate_ids))
                if grouping:
                    capture_times = {asset_id: row[3] for asset_id, row in seed_by_id.items()}
                    capture_times.update({str(row[1]): row[-1] for row in candidate_artifact_rows})
                    result = propose_memory_group(
                        AuthorizationSnapshot(library_id=library_id, photo_ids=authorized_ids),
                        seed_ids=tuple(seed_ids), seed_vectors=seed_vector_records,
                        candidate_ids=candidate_ids, candidate_vectors=candidate_vector_records,
                        expected_identity=self.expected_identity, capture_times=capture_times,
                        excluded_ids=excluded_ids,
                    )
                    if not present_items or result.status != 'ready':
                        return result
                    from .library import FIELDS, SOURCE, _asset
                    items = []
                    for candidate in result.candidates:
                        row = db.execute('SELECT ' + FIELDS + SOURCE + ' AND a.id=?',
                                         (library_id, int(candidate.asset_id))).fetchone()
                        if row is None:
                            raise AccessDenied('Access denied')
                        item = _asset(row, library_id)
                        item.update(matched_seed_asset_id=candidate.matched_seed_asset_id,
                                    time_reason=candidate.time_reason)
                        items.append(item)
                    return {'version': 1, 'status': 'ready', 'library_id': library_id,
                            'needs_review': True, 'seed_asset_ids': list(seed_ids), 'items': items}
                return rank_visual_candidates(
                    AuthorizationSnapshot(library_id=library_id, photo_ids=authorized_ids),
                    seed_ids=tuple(seed_ids),
                    seed_vectors=seed_vector_records,
                    candidate_ids=candidate_ids,
                    candidate_vectors=candidate_vector_records,
                    expected_identity=self.expected_identity,
                )
            except AccessDenied:
                raise
            except (OSError, sqlite3.Error, TypeError, ValueError, OverflowError):
                return unavailable


def _valid_identity(identity: object) -> bool:
    try:
        return identity_sha256(identity) is not None
    except (AttributeError, TypeError, ValueError):
        return False


def _valid_root_argument(root: object) -> bool:
    return isinstance(root, Path) and root.is_absolute() and ".." not in root.parts


def _artifact_from_row(row, expected_identity=None) -> ImmutableVectorArtifact | None:
    try:
        if (len(row) != 16 or type(row[1]) is not int or row[1] <= 0
                or row[1] > 2**63 - 1):
            return None
        values = list(row)
        values[1] = str(values[1])
        artifact = ImmutableVectorArtifact(*values)
    except (TypeError, ValueError):
        return None
    return artifact if validate_artifact(artifact, expected_identity) else None


def _validated_rows(rows, expected_identity):
    result: dict[str, ImmutableVectorArtifact] = {}
    for row in rows:
        artifact = _artifact_from_row(row, expected_identity)
        if artifact is None or artifact.asset_id in result:
            return {}
        result[artifact.asset_id] = artifact
    return result


def _checked_root(root: Path) -> Path | None:
    """Return a direct, existing directory only when no path component aliases."""
    if not _valid_root_argument(root):
        return None
    current = Path(root.anchor)
    try:
        for part in root.parts[1:]:
            current = current / part
            info = os.lstat(current)
            if stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                return None
        info = os.lstat(root)
        if not stat.S_ISDIR(info.st_mode) or _is_reparse(info):
            return None
        return root
    except OSError:
        return None


def _is_reparse(info) -> bool:
    # On Windows Python exposes FILE_ATTRIBUTE_REPARSE_POINT in st_file_attributes.
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _read_vector(root: Path, artifact: ImmutableVectorArtifact, *, charge=None) -> tuple[float, ...] | None:
    """Read one tightly bounded NPY payload without shape-driven allocation."""
    if not _valid_root_argument(root):
        return None
    relative = Path(artifact.relative_path)
    if relative.is_absolute() or ".." in relative.parts or len(relative.parts) != 3:
        return None
    target = root.joinpath(*relative.parts)
    try:
        # One complete lexical ancestor walk subsumes both the root check and
        # relative-directory walk. Keep its identity snapshot through the read;
        # no path decisions are cached across files, passes or requests.
        path_snapshot = _root_snapshot(target.parent)
        if path_snapshot is None:
            return None
        before = os.lstat(target)
        if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                or _is_reparse(before) or before.st_nlink != 1
                or before.st_size > _MAX_FILE_BYTES):
            return None
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        descriptor = os.open(target, flags)
        try:
            opened = os.fstat(descriptor)
            if not _same_file(before, opened) or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                return None
            remaining = min(opened.st_size, _MAX_FILE_BYTES) + 1
            # Reserve the maximum bytes this handle can read before I/O. The
            # optional large-cohort caller shares one budget across both passes.
            if charge is not None:
                charge(remaining)
            chunks = []
            while remaining:
                chunk = os.read(descriptor, min(remaining, 8192))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after_fd = os.fstat(descriptor)
            after_path = os.lstat(target)
            if (len(raw) != opened.st_size or len(raw) > _MAX_FILE_BYTES
                    or not _same_file(opened, after_fd) or not _same_file(opened, after_path)
                    or _root_snapshot(target.parent) != path_snapshot):
                return None
        finally:
            os.close(descriptor)
    except OSError:
        return None

    if hashlib.sha256(raw).hexdigest() != artifact.file_sha256:
        return None
    return _decode_npy(raw, artifact.dimension)


def _decode_npy(raw: bytes, dimension: int) -> tuple[float, ...] | None:
    """Decode only an exact bounded NPY v1/v2 float32 vector without NumPy."""
    try:
        if len(raw) < 10 or raw[:6] != b"\x93NUMPY":
            return None
        version = (raw[6], raw[7])
        if version == (1, 0):
            prefix_size, header_length = 10, struct.unpack_from("<H", raw, 8)[0]
        elif version == (2, 0):
            if len(raw) < 12:
                return None
            prefix_size, header_length = 12, struct.unpack_from("<I", raw, 8)[0]
        else:
            return None
        if header_length > _MAX_HEADER_BYTES or prefix_size + header_length > len(raw):
            return None
        header_bytes = raw[prefix_size:prefix_size + header_length]
        if not header_bytes.endswith(b"\n"):
            return None
        header = ast.literal_eval(header_bytes.decode("ascii").rstrip(" \n"))
        if (type(header) is not dict or set(header) != {"descr", "fortran_order", "shape"}
                or type(header["descr"]) is not str or header["descr"] != "<f4"
                or type(header["fortran_order"]) is not bool or header["fortran_order"] is not False
                or type(header["shape"]) is not tuple or len(header["shape"]) != 1
                or type(header["shape"][0]) is not int or header["shape"] != (dimension,)):
            return None
        payload_offset = prefix_size + header_length
        if payload_offset + dimension * 4 != len(raw):
            return None
        return tuple(struct.unpack_from(f"<{dimension}f", raw, payload_offset))
    except (EOFError, UnicodeDecodeError, ValueError, TypeError, OverflowError, struct.error,
            SyntaxError, MemoryError, RecursionError):
        return None


def _same_file(left, right) -> bool:
    try:
        return stable_stat_identity(left) == stable_stat_identity(right)
    except (AttributeError, ValueError, OSError):
        return False


def _root_snapshot(root: Path):
    """Capture every lexical ancestor so persistent parent swaps are refused."""
    # Operate on native lexical strings during the walk. Constructing a new
    # lazy Path for every ancestor repeatedly reparses and formats the same
    # components across large cohorts; no resolution or alias following is needed.
    current = root.anchor
    observed = []
    try:
        for part in root.parts[1:]:
            current = os.path.join(current, part)
            info = os.lstat(current)
            if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode) or _is_reparse(info):
                return None
            observed.append((info.st_dev, info.st_ino, info.st_mode))
        return tuple(observed)
    except OSError:
        return None

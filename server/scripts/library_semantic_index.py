"""Prepare and inspect an unpublished, resumable private library image index.

The input is a frozen owner-selected snapshot. This module writes immutable
vector artifacts and an append-only batch checkpoint; only a complete manifest
can be inspected. It never loads a model itself or changes a live index.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import time

import library_image_inputs as preparation
import library_siglip
import qualify_multilingual_scenes as qualification
from app.access.private_storage import require_private_directory, require_private_file
from app.access.semantic_encoder import SemanticUnavailable
from app.access.visual_candidates import (VectorRecord, VectorSpaceIdentity,
    canonical_vector_checksum, _canonical_components)
from app.access.visual_vector_artifacts import (ImmutableVectorArtifact,
    identity_sha256, validate_artifact)
from app.access.visual_vector_loader import _decode_npy, _read_vector
from image_embedding_receipts import (recipe_sha256, inspect_checkpoint, verify_checkpoint,
    CheckpointPin, _checkpoint_path, _stat_identity, _open_pinned)
from semantic_openclip import _source_pin


SCHEMA = "photohouse.library_semantic_snapshot.v1"
INDEX_SCHEMA = "photohouse.library_semantic_index.v1"
RUN_SCHEMA = "photohouse.library_semantic_index_run.v1"
BATCH_SCHEMA = "photohouse.library_semantic_index_batch.v1"
MAX_ASSETS = 100_000
MAX_MANIFEST_BYTES = 64 * 1024**2
MAX_DOCUMENT_BYTES = 2 * 1024**2
MAX_VECTOR_BYTES = 64 * 1024
DEFAULT_FREE_SPACE_FLOOR = 32 * 1024**3
BATCH_SIZE = 8
MAX_SCRATCH_BYTES = BATCH_SIZE * preparation.MAX_COMBINED_BYTES
DIMENSION = 768
SPACE = library_siglip.SPACE
MODEL_VERSION = library_siglip.MODEL_VERSION
MODEL_NAME = "siglip2-base-p16-256"
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ASSET_ID = re.compile(r"[1-9][0-9]{0,18}\Z", re.ASCII)
_LIBRARY_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z", re.ASCII)


class LibraryIndexUnavailable(ValueError):
    """Fixed refusal for invalid, stale, incomplete, or unsafe index state."""

    def __init__(self):
        super().__init__("library_semantic_index_unavailable")


def _require(condition):
    if not condition:
        raise LibraryIndexUnavailable()


class _CoordinatedCheck:
    """Remember coordinator cancellation even if a helper sanitizes its error."""

    def __init__(self, callback):
        self.callback = callback
        self.failed = False

    def __call__(self):
        try:
            self.callback()
        except BaseException:
            self.failed = True
            raise


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False).encode("ascii")


def _unique_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise LibraryIndexUnavailable()
        value[key] = item
    return value


def _load_json(path: Path, limit: int):
    try:
        require_private_file(path)
        info = path.lstat()
        _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & 0x400
            and 0 < info.st_size <= limit)
        pin = inspect_checkpoint(path, hashlib.sha256(path.read_bytes()).hexdigest())
        value = json.loads(Path(pin.path).read_bytes(), object_pairs_hook=_unique_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(LibraryIndexUnavailable()))
        _require(type(value) is dict and canonical(value) + b"\n" == path.read_bytes())
        verify_checkpoint(pin)
        return value
    except LibraryIndexUnavailable:
        raise
    except Exception:
        raise LibraryIndexUnavailable() from None


def _load_json_inspector(path: Path, limit: int, *, expected_sha256=None):
    """Load canonical JSON once from a pinned descriptor for read-only audits.

    The same bounded byte string is hashed, parsed, and compared with its
    canonical encoding. A second independent digest/identity pass closes the
    load race; resumable writer paths deliberately continue to use _load_json.
    """
    try:
        _require(type(limit) is int and 0 < limit <= MAX_MANIFEST_BYTES)
        if expected_sha256 is not None:
            _require(type(expected_sha256) is str and _SHA.fullmatch(expected_sha256) is not None)
        require_private_file(path)
        checkpoint = _checkpoint_path(path)
        before_info = checkpoint.lstat()
        _require(stat.S_ISREG(before_info.st_mode) and not stat.S_ISLNK(before_info.st_mode)
            and not (getattr(before_info, "st_file_attributes", 0) & 0x400)
            and before_info.st_nlink == 1 and 0 < before_info.st_size <= limit)
        identity = _stat_identity(before_info)
        _require(type(identity) is tuple and len(identity) == 7
            and all(type(item) is int for item in identity))
        with _open_pinned(checkpoint, identity) as stream:
            opened_info = os.fstat(stream.fileno())
            _require(stat.S_ISREG(opened_info.st_mode)
                and not (getattr(opened_info, "st_file_attributes", 0) & 0x400)
                and opened_info.st_nlink == 1 and _stat_identity(opened_info) == identity)
            raw = stream.read(limit + 1)
            _require(type(raw) is bytes and 0 < len(raw) <= limit
                and len(raw) == identity[3])
            post_descriptor = os.fstat(stream.fileno())
            _require(stat.S_ISREG(post_descriptor.st_mode)
                and not (getattr(post_descriptor, "st_file_attributes", 0) & 0x400)
                and post_descriptor.st_nlink == 1
                and _stat_identity(post_descriptor) == identity)
        post_path = _checkpoint_path(path)
        post_path_info = post_path.lstat()
        _require(post_path == checkpoint and stat.S_ISREG(post_path_info.st_mode)
            and not stat.S_ISLNK(post_path_info.st_mode)
            and not (getattr(post_path_info, "st_file_attributes", 0) & 0x400)
            and post_path_info.st_nlink == 1 and _stat_identity(post_path_info) == identity)
        require_private_file(path)
        digest = hashlib.sha256(raw).hexdigest()
        _require(expected_sha256 is None or digest == expected_sha256)
        value = json.loads(raw, object_pairs_hook=_unique_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(LibraryIndexUnavailable()))
        _require(type(value) is dict and canonical(value) + b"\n" == raw)
        pin = CheckpointPin(str(checkpoint), digest, identity)
        verify_checkpoint(pin)
        require_private_file(path)
        return value
    except LibraryIndexUnavailable:
        raise
    except Exception:
        raise LibraryIndexUnavailable() from None


def _write_json(path: Path, value, *, limit=MAX_DOCUMENT_BYTES):
    raw = canonical(value) + b"\n"
    _require(0 < len(raw) <= limit)
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            require_private_file(path)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        raise LibraryIndexUnavailable() from None
    return hashlib.sha256(raw).hexdigest()


def _write_bytes(path: Path, raw: bytes):
    _require(type(raw) is bytes and 0 < len(raw) <= MAX_VECTOR_BYTES)
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            require_private_file(path)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        raise LibraryIndexUnavailable() from None


def validate_snapshot(snapshot):
    """Validate the one exact, frozen snapshot contract used by the worker."""
    _require(type(snapshot) is dict and set(snapshot) == {"schema", "library_id", "assets"}
        and snapshot["schema"] == SCHEMA
        and type(snapshot["library_id"]) is str
        and _LIBRARY_ID.fullmatch(snapshot["library_id"]) is not None
        and type(snapshot["assets"]) is list and len(snapshot["assets"]) <= MAX_ASSETS)
    seen = set()
    assets = []
    for asset in snapshot["assets"]:
        _require(type(asset) is dict and set(asset) == {
            "asset_id", "path", "sha256", "mime", "width", "height"})
        asset_id, raw_path, digest = asset["asset_id"], asset["path"], asset["sha256"]
        _require(type(asset_id) is str and _ASSET_ID.fullmatch(asset_id) is not None
            and int(asset_id) <= 2**63 - 1 and asset_id not in seen
            and type(raw_path) is str and len(raw_path) <= 32_768)
        path = Path(raw_path)
        _require(path.is_absolute() and ".." not in path.parts and path != Path(path.anchor))
        _require(digest is None or (type(digest) is str and _SHA.fullmatch(digest) is not None))
        mime = asset["mime"]
        _require(mime is None or (type(mime) is str and 1 <= len(mime) <= 128
            and all(0x20 <= ord(char) <= 0x7e for char in mime)))
        # Catalog dimensions are diagnostic only. Zero and negative values are
        # retained in the snapshot; observed preparation dimensions are used.
        for name in ("width", "height"):
            value = asset[name]
            _require(value is None or (type(value) is int and -(2**31) <= value < 2**31))
        seen.add(asset_id)
        assets.append({**asset, "path": str(path)})
    normalized = {"schema": SCHEMA, "library_id": snapshot["library_id"], "assets": assets}
    # Enforce a practical private-document bound before any source is opened.
    _require(len(canonical(normalized)) + 1 <= MAX_MANIFEST_BYTES)
    return normalized


def _preflight_manifest_size(snapshot):
    # Reserve ample room for the per-row receipt fields before any image I/O.
    # Paths are repeated in the final manifest and may dominate the document.
    estimated = 2048 + sum(2048 + 2 * len(asset["path"]) for asset in snapshot["assets"])
    _require(estimated <= MAX_MANIFEST_BYTES)


def snapshot_sha256(snapshot) -> str:
    return hashlib.sha256(canonical(validate_snapshot(snapshot))).hexdigest()


def _validate_roots(original_roots):
    _require(type(original_roots) in (tuple, list) and 1 <= len(original_roots) <= 64)
    roots = []
    for item in original_roots:
        root = preparation._canonical_path(item, directory=True)
        if root not in roots:
            roots.append(root)
    _require(bool(roots))
    return tuple(sorted(roots, key=lambda path: str(path)))


def _private_target(output_directory, roots, *, resume):
    target = Path(output_directory)
    _require(target.is_absolute() and ".." not in target.parts
        and target != Path(target.anchor)
        and not target.resolve(strict=False).is_relative_to(Path(__file__).resolve().parents[2]))
    parent = preparation._canonical_path(target.parent, directory=True)
    require_private_directory(parent)
    for root in roots:
        try:
            common = os.path.commonpath((str(target), str(root)))
        except (OSError, ValueError):
            continue
        _require(common not in (str(target), str(root)))
    if os.path.lexists(target):
        target = preparation._canonical_path(target, directory=True)
        require_private_directory(target)
        if not resume:
            _require(not any(target.iterdir()))
    else:
        target.mkdir(mode=0o700)
        target = preparation._canonical_path(target, directory=True)
        require_private_directory(target)
    return target


def _source_state(raw_path, roots):
    """Return an approved canonical source, the explicit missing state, or refusal."""
    try:
        path = Path(raw_path)
        _require(path.is_absolute() and ".." not in path.parts)
        root = next((item for item in roots
            if os.path.commonpath((str(path), str(item))) == str(item) and path != item), None)
        if root is None:
            return None, "source_not_approved"
        relative = path.relative_to(root)
        cursor = root
        for index, component in enumerate(relative.parts):
            cursor = cursor / component
            try:
                info = cursor.lstat()
            except FileNotFoundError:
                return None, "source_missing"
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return None, "source_not_approved"
            if index < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
                return None, "source_not_approved"
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            return None, "source_not_approved"
        return path, None
    except (OSError, RuntimeError, TypeError, ValueError):
        return None, "source_not_approved"


def _hash_source(raw_path, roots, check):
    path, failure = _source_state(raw_path, roots)
    if failure:
        return {"path": str(raw_path), "failure": failure,
            "source_sha256": None, "source_stat_identity": None}
    try:
        stream, stable = preparation._open_source(path)
        with stream:
            before = os.fstat(stream.fileno())
            stat_receipt = preparation._stat_receipt(before)
            size = before.st_size
            if not 0 < size <= preparation.MAX_ORIGINAL_BYTES:
                return {"path": str(path), "failure": "source_size_invalid",
                    "source_sha256": None, "source_stat_identity": stat_receipt}
            digest = hashlib.sha256()
            total = 0
            while True:
                check()
                block = stream.read(preparation.COPY_CHUNK_BYTES)
                if not block:
                    break
                total += len(block)
                if total > preparation.MAX_ORIGINAL_BYTES:
                    return {"path": str(path), "failure": "source_size_invalid",
                        "source_sha256": None, "source_stat_identity": stat_receipt}
                digest.update(block)
            after = os.fstat(stream.fileno())
            current_path = path.lstat()
            if (preparation._stable_identity(after) != stable
                    or preparation._stable_identity(current_path) != stable):
                raise LibraryIndexUnavailable()
            return {"path": str(path), "failure": None,
                "source_sha256": digest.hexdigest(), "source_stat_identity": stat_receipt}
    except LibraryIndexUnavailable:
        raise
    except Exception:
        if getattr(check, "failed", False):
            raise LibraryIndexUnavailable() from None
        return {"path": str(raw_path), "failure": "source_unavailable",
            "source_sha256": None, "source_stat_identity": None}


def _stat_source(raw_path, roots):
    path, failure = _source_state(raw_path, roots)
    if failure:
        return {"path": str(raw_path), "failure": failure,
            "source_stat_identity": None}
    try:
        info = path.stat()
        receipt = preparation._stat_receipt(info)
        if not 0 < info.st_size <= preparation.MAX_ORIGINAL_BYTES:
            return {"path": str(path), "failure": "source_size_invalid",
                "source_stat_identity": receipt}
        return {"path": str(path), "failure": None, "source_stat_identity": receipt}
    except Exception:
        return {"path": str(raw_path), "failure": "source_unavailable",
            "source_stat_identity": None}


def _verify_source_stat(path, expected_stat, roots):
    current = _stat_source(path, roots)
    _require(current["failure"] is None and current["source_stat_identity"] == expected_stat)


def _verify_source(path, expected_sha256, expected_stat, roots, check):
    actual = _hash_source(path, roots, check)
    _require(actual["failure"] is None
        and actual["source_sha256"] == expected_sha256
        and actual["source_stat_identity"] == expected_stat)


def _npy_bytes(vector):
    _require(type(vector) in (tuple, list) and len(vector) == DIMENSION)
    checksum = canonical_vector_checksum(vector)
    _require(checksum)
    norm = math.sqrt(math.fsum(float(value) * float(value) for value in vector))
    _require(math.isfinite(norm) and abs(norm - 1.0) <= 1e-3)
    header = b"{'descr': '<f4', 'fortran_order': False, 'shape': (768,), }"
    header += b" " * ((64 - (10 + len(header) + 1) % 64) % 64) + b"\n"
    raw = b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header
    raw += struct.pack("<768f", *[float(value) for value in vector])
    _require(_decode_npy(raw, DIMENSION) is not None)
    return raw


def _record_id(snapshot_digest, asset_id, identity_digest):
    return hashlib.sha256(canonical({"schema": "photohouse.library_semantic_record.v1",
        "snapshot_sha256": snapshot_digest, "asset_id": asset_id,
        "identity_sha256": identity_digest})).hexdigest()


def _model_state(model):
    try:
        _require(type(model.image_identity) is VectorSpaceIdentity
            and type(model.text_identity) is VectorSpaceIdentity
            and model.image_identity.vector_space_id == SPACE
            and model.text_identity.vector_space_id == SPACE
            and model.image_identity.model_version == MODEL_VERSION
            and model.text_identity.model_version == MODEL_VERSION
            and model.image_identity.dimension == DIMENSION
            and model.text_identity.dimension == DIMENSION
            and model.image_identity.artifact_sha256 == model.text_identity.artifact_sha256
            and model.image_identity.normalization == model.text_identity.normalization == "unit_l2"
            and getattr(model, "binding", None) is None)
        model.verify()
        receipt = model.receipt()
        _verify_model_receipt(receipt, model.image_identity, model.text_identity)
        return (asdict(model.image_identity), asdict(model.text_identity), receipt,
            hashlib.sha256(canonical(receipt)).hexdigest())
    except LibraryIndexUnavailable:
        raise
    except Exception:
        raise LibraryIndexUnavailable() from None


def _verify_model_receipt(receipt, expected_image=None, expected_text=None):
    """Check the full library recipe against current source and policy pins."""
    _require(type(receipt) is dict and set(receipt) == {
        "schema", "image_identity", "text_identity", "base_model_receipt",
        "image_recipe", "cpu_threads", "activation_approved", "relevance_accepted"}
        and receipt["schema"] == "photohouse.siglip2_library_recipe_receipt.v1"
        and receipt["cpu_threads"] == 2 and receipt["activation_approved"] is False
        and receipt["relevance_accepted"] is False)
    try:
        image = VectorSpaceIdentity(**receipt["image_identity"])
        text = VectorSpaceIdentity(**receipt["text_identity"])
        _require((expected_image is None or image == expected_image)
            and (expected_text is None or text == expected_text)
            and image.dimension == text.dimension == DIMENSION
            and image.vector_space_id == text.vector_space_id == SPACE
            and image.model_version == text.model_version == MODEL_VERSION
            and image.artifact_sha256 == text.artifact_sha256
            and image.normalization == text.normalization == "unit_l2")
        identity_sha256(image); identity_sha256(text)
        base = receipt["base_model_receipt"]
        _require(type(base) is dict and set(base) == {
            "schema", "image_identity", "text_identity", "recipes", "cpu_threads",
            "relevance_accepted", "activation_approved"}
            and base["schema"] == "photohouse.siglip2_adapter_receipt.v1"
            and base["cpu_threads"] == 2 and base["activation_approved"] is False
            and base["relevance_accepted"] is False
            and type(base["recipes"]) is dict and set(base["recipes"]) == {"image", "text"})
        base_image = VectorSpaceIdentity(**base["image_identity"])
        base_text = VectorSpaceIdentity(**base["text_identity"])
        _require(base_image.artifact_sha256 == base_text.artifact_sha256 == image.artifact_sha256
            and base_image.vector_space_id == base_text.vector_space_id == SPACE
            and base_image.model_version == base_text.model_version == MODEL_VERSION
            and base_image.dimension == base_text.dimension == DIMENSION
            and base_image.normalization == base_text.normalization == "unit_l2"
            and text == base_text)
        recipes = base["recipes"]
        for role, identity in (("image", base_image), ("text", base_text)):
            recipe = recipes[role]
            _require(type(recipe) is dict and recipe.get("role") == role
                and identity.preprocessing_sha256 == recipe_sha256(recipe)
                and recipe.get("schema") == "photohouse.siglip2_recipe.v1"
                and type(recipe.get("source_digests")) is dict
                and recipe.get("model_id") == qualification.MODEL_ID
                and recipe.get("revision") == qualification.REVISION
                and recipe.get("artifacts") == qualification.OFFICIAL_ARTIFACTS
                and recipe.get("package_versions") == qualification.EXPECTED_PACKAGES
                and recipe.get("source_digests")
                and identity.artifact_sha256
                    == qualification.OFFICIAL_ARTIFACTS["model.safetensors"]["sha256"]
                and recipe.get("dimension") == DIMENSION
                and recipe.get("device") == "cpu" and recipe.get("dtype") == "float32")
        recipe = receipt["image_recipe"]
        _require(type(recipe) is dict and image.preprocessing_sha256 == recipe_sha256(recipe)
            and recipe.get("schema") == "photohouse.siglip2_library_image_recipe.v1"
            and recipe.get("base_image_identity") == asdict(base_image)
            and recipe.get("base_text_identity") == asdict(base_text)
            and recipe.get("preparation_recipe") == preparation.PROFILE_RECIPE
            and recipe.get("batch") == {
                "size": BATCH_SIZE,
                "tail_padding": "repeat_last_input_to_fixed_size_then_discard_padding_outputs",
                "output": "float32_unit_l2_per_row"})
        source = recipe.get("source_digests")
        _require(type(source) is dict and set(source) == {
            "base_image_preprocessing_sha256", "base_text_preprocessing_sha256",
            "library_wrapper_sha256", "library_preparation_sha256"}
            and source["base_image_preprocessing_sha256"] == base_image.preprocessing_sha256
            and source["base_text_preprocessing_sha256"] == base_text.preprocessing_sha256
            and _SHA.fullmatch(source["library_wrapper_sha256"]) is not None
            and _SHA.fullmatch(source["library_preparation_sha256"]) is not None)
        wrapper_source = _source_pin(Path(library_siglip.__file__).resolve())
        preparation_source = _source_pin(Path(preparation.__file__).resolve())
        _require(wrapper_source.sha256 == source["library_wrapper_sha256"]
            and preparation_source.sha256 == source["library_preparation_sha256"])
        recomputed_image, recomputed_recipe = library_siglip._image_identity(base_image,
            base_text, preparation.PROFILE_RECIPE, wrapper_source.sha256,
            preparation_source.sha256)
        _require(recomputed_image == image and recomputed_recipe == recipe)
    except LibraryIndexUnavailable:
        raise
    except Exception:
        raise LibraryIndexUnavailable() from None
    return image, text


def _ensure_private_tree(target):
    for name in ("checkpoints", "image-vectors"):
        path = target / name
        if os.path.lexists(path):
            path = preparation._canonical_path(path, directory=True)
            require_private_directory(path)
        else:
            path.mkdir(mode=0o700)
            require_private_directory(path)
    scratch = target / "prepared"
    if os.path.lexists(scratch):
        scratch = preparation._canonical_path(scratch, directory=True)
        require_private_directory(scratch)
    else:
        scratch.mkdir(mode=0o700)
        require_private_directory(scratch)
    return scratch


def _ensure_identity_directory(target, identity):
    digest = identity_sha256(identity)
    vector_root = target / "image-vectors"
    path = vector_root / digest
    if os.path.lexists(path):
        path = preparation._canonical_path(path, directory=True)
        require_private_directory(path)
    else:
        path.mkdir(mode=0o700)
        require_private_directory(path)
    return digest, path


def _space_available(target, floor):
    _require(type(floor) is int and floor >= 0)
    _require(shutil.disk_usage(target).free >= floor)


def _scratch_bytes(scratch):
    """Validate retained preparation files and return bounded scratch usage."""
    total = 0
    for path in scratch.iterdir():
        match = preparation._OWNED_NAME.fullmatch(path.name)
        _require(match is not None)
        info = path.lstat()
        max_size = (preparation.MAX_ORIGINAL_BYTES if match.group(2) == "original"
            else preparation.MAX_DERIVED_BYTES)
        _require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & 0x400
            and info.st_nlink == 1 and 0 <= info.st_size <= max_size)
        require_private_file(path)
        total += info.st_size
        _require(total <= MAX_SCRATCH_BYTES)
    return total


def _batch_path(target, number):
    return target / "checkpoints" / f"batch-{number:08d}.json"


def _read_run(target, snapshot, snapshot_digest, roots, image, text, receipt, receipt_digest,
              *, resume, may_initialize):
    run_path = target / "run.json"
    snapshot_path = target / "snapshot.json"
    wanted = {"schema": RUN_SCHEMA, "library_id": snapshot["library_id"],
        "snapshot_sha256": snapshot_digest, "asset_count": len(snapshot["assets"]),
        "original_roots": [str(root) for root in roots],
        "image_identity": asdict(image), "text_identity": asdict(text),
        "model_receipt": receipt, "model_receipt_sha256": receipt_digest}
    if os.path.lexists(run_path):
        _require(resume)
        current = _load_json(run_path, MAX_DOCUMENT_BYTES)
        _require(current == wanted)
        frozen_snapshot = _load_json(snapshot_path, MAX_MANIFEST_BYTES)
        _require(frozen_snapshot == snapshot
            and hashlib.sha256(canonical(frozen_snapshot)).hexdigest() == snapshot_digest)
    else:
        _require(may_initialize)
        _write_json(snapshot_path, snapshot, limit=MAX_MANIFEST_BYTES)
        _write_json(run_path, wanted)
    return wanted


def _verify_batch(batch, number, snapshot, snapshot_digest, roots, identity, identity_digest,
                  receipt_digest, check, *, verify_sources=True):
    _require(type(batch) is dict and set(batch) == {"schema", "batch_number",
        "snapshot_sha256", "identity_sha256", "model_receipt_sha256", "asset_ids", "results"}
        and batch["schema"] == BATCH_SCHEMA and batch["batch_number"] == number
        and batch["snapshot_sha256"] == snapshot_digest
        and batch["identity_sha256"] == identity_digest
        and batch["model_receipt_sha256"] == receipt_digest)
    start = number * BATCH_SIZE
    expected_assets = snapshot["assets"][start:start + BATCH_SIZE]
    _require(batch["asset_ids"] == [asset["asset_id"] for asset in expected_assets]
        and type(batch["results"]) is list and len(batch["results"]) == len(expected_assets))
    seen = []
    for asset, result in zip(expected_assets, batch["results"]):
        check()
        _require(type(result) is dict and result.get("asset_id") == asset["asset_id"])
        seen.append(result["asset_id"])
        if result.get("status") == "ready":
            expected_keys = {"status", "asset_id", "source_path", "source_sha256",
                "source_stat_identity", "derived_sha256", "preparation_recipe_sha256",
                "observed_format", "observed_width", "observed_height", "orientation",
                "prepared_width", "prepared_height", "record_id", "metadata_sha256"}
            _require(set(result) == expected_keys
                and result["source_path"] == asset["path"]
                and _SHA.fullmatch(result["source_sha256"]) is not None
                and result["preparation_recipe_sha256"] == preparation.RECIPE_SHA256
                and _SHA.fullmatch(result["derived_sha256"]) is not None
                and _SHA.fullmatch(result["metadata_sha256"]) is not None
                and result["observed_format"] in ("JPEG", "PNG")
                and type(result["observed_width"]) is int and result["observed_width"] > 0
                and type(result["observed_height"]) is int and result["observed_height"] > 0
                and type(result["prepared_width"]) is int and 1 <= result["prepared_width"] <= 2048
                and type(result["prepared_height"]) is int and 1 <= result["prepared_height"] <= 2048
                and type(result["orientation"]) is int and 1 <= result["orientation"] <= 8)
            if asset["sha256"] is not None:
                _require(result["source_sha256"] == asset["sha256"])
            if verify_sources:
                _verify_source(result["source_path"], result["source_sha256"],
                    result["source_stat_identity"], roots, check)
            else:
                _verify_source_stat(result["source_path"], result["source_stat_identity"], roots)
            record_id = _record_id(snapshot_digest, asset["asset_id"], identity_digest)
            _require(result["record_id"] == record_id)
            metadata_path = target_path = None
            # The caller checks vector and metadata files after structural
            # validation, when it has the actual index directory root.
        elif result.get("status") == "failed":
            _require(set(result) == {"status", "asset_id", "source_path", "code",
                "source_sha256", "source_stat_identity"}
                and result["source_path"] == asset["path"]
                and (result["source_sha256"] is None
                    or (type(result["source_sha256"]) is str
                        and _SHA.fullmatch(result["source_sha256"]) is not None))
                and result["code"] in {"source_missing", "source_not_approved",
                    "source_size_invalid", "source_hash_mismatch", "source_unavailable",
                    "preparation_unavailable"})
            state = (_hash_source(result["source_path"], roots, check) if verify_sources
                else _stat_source(result["source_path"], roots))
            if result["code"] == "source_missing":
                _require(state["failure"] == "source_missing"
                    and result["source_sha256"] is None and result["source_stat_identity"] is None)
            elif result["code"] == "source_not_approved":
                _require(state["failure"] == "source_not_approved"
                    and result["source_sha256"] is None
                    and result["source_stat_identity"] is None)
            elif result["code"] == "source_size_invalid":
                _require(state["failure"] == "source_size_invalid"
                    and result["source_sha256"] is None
                    and result["source_stat_identity"] == state["source_stat_identity"])
            elif result["code"] == "source_unavailable":
                if verify_sources:
                    _require(state["failure"] == "source_unavailable"
                        and result["source_sha256"] is None
                        and result["source_stat_identity"] is None)
                else:
                    _require(result["source_sha256"] is None
                        and result["source_stat_identity"] is None)
            else:
                if verify_sources:
                    _require(state["failure"] is None
                        and result["source_sha256"] == state["source_sha256"]
                        and result["source_stat_identity"] == state["source_stat_identity"])
                else:
                    _require(state["failure"] is None
                        and result["source_stat_identity"] == state["source_stat_identity"])
                if result["code"] == "source_hash_mismatch":
                    _require(asset["sha256"] is not None
                        and result["source_sha256"] != asset["sha256"])
                else:
                    _require(result["code"] == "preparation_unavailable"
                        and (asset["sha256"] is None
                            or result["source_sha256"] == asset["sha256"]))
        else:
            raise LibraryIndexUnavailable()
    _require(seen == [asset["asset_id"] for asset in expected_assets])


def _verify_batch_files(target, batch, identity):
    identity_digest = identity_sha256(identity)
    for result in batch["results"]:
        if result["status"] != "ready":
            continue
        record_id = result["record_id"]
        directory = target / "image-vectors" / identity_digest
        metadata_path = directory / f"{record_id}.json"
        vector_path = directory / f"{record_id}.npy"
        metadata_pin = inspect_checkpoint(metadata_path, result["metadata_sha256"])
        metadata = _load_json(metadata_path, MAX_DOCUMENT_BYTES)
        _require(set(metadata) == set(ImmutableVectorArtifact.__dataclass_fields__))
        record = ImmutableVectorArtifact(**metadata)
        _require(validate_artifact(record, identity)
            and record.record_id == record_id and record.asset_id == result["asset_id"]
            and record.source_sha256 == result["source_sha256"]
            and record.relative_path == f"image-vectors/{identity_digest}/{record_id}.npy")
        verify_checkpoint(metadata_pin)
        vector = _read_vector(target, record)
        _require(vector is not None and canonical_vector_checksum(vector) == record.component_sha256)


def _read_committed(target, snapshot, snapshot_digest, roots, identity, identity_digest,
                    receipt_digest, check):
    committed = []
    gap = False
    batch_count = (len(snapshot["assets"]) + BATCH_SIZE - 1) // BATCH_SIZE
    for number in range(batch_count):
        path = _batch_path(target, number)
        if not os.path.lexists(path):
            gap = True
            continue
        _require(not gap)
        batch = _load_json(path, MAX_DOCUMENT_BYTES)
        _verify_batch(batch, number, snapshot, snapshot_digest, roots, identity,
            identity_digest, receipt_digest, check)
        _verify_batch_files(target, batch, identity)
        committed.append(batch)
    checkpoint_directory = target / "checkpoints"
    # run.json and snapshot.json live at the index root, so only batch files
    # belong in this directory. Unknown or uncommitted checkpoint files stay
    # untouched and cause a refusal before any new vector is produced.
    _require({item.name for item in checkpoint_directory.iterdir()} ==
        {f"batch-{i:08d}.json" for i in range(len(committed))})
    expected_vector_names = set()
    for batch in committed:
        for result in batch["results"]:
            if result["status"] == "ready":
                expected_vector_names.update((result["record_id"] + ".npy",
                    result["record_id"] + ".json"))
    identity_dir = target / "image-vectors" / identity_digest
    _require({item.name for item in identity_dir.iterdir()} == expected_vector_names)
    _require({item.name for item in (target / "image-vectors").iterdir()} == {identity_digest})
    allowed_root_names = {"run.json", "snapshot.json", "checkpoints", "image-vectors", "prepared"}
    if os.path.lexists(target / "index.json"):
        allowed_root_names.add("index.json")
    _require({item.name for item in target.iterdir()} == allowed_root_names)
    return committed


def execute(snapshot, output_directory, *, model, original_roots, resume=False,
            check=lambda: None, free_space_floor=DEFAULT_FREE_SPACE_FLOOR,
            max_new_assets=None, progress=None):
    """Prepare an immutable full-library index, or checkpoint a bounded slice.

    ``max_new_assets`` is a positive multiple of eight. Partial runs return
    without an ``index.json`` manifest; a later ``resume=True`` call continues
    at the first uncommitted batch. ``check`` belongs to the resource-bounded
    coordinator and is called between every source and model operation.
    """
    try:
        check = _CoordinatedCheck(check)
        snapshot = validate_snapshot(snapshot)
        _preflight_manifest_size(snapshot)
        roots = _validate_roots(original_roots)
        snapshot_digest = hashlib.sha256(canonical(snapshot)).hexdigest()
        if max_new_assets is not None:
            _require(type(max_new_assets) is int and max_new_assets > 0
                and max_new_assets % BATCH_SIZE == 0)
        check()
        image_dict, text_dict, receipt, receipt_digest = _model_state(model)
        image = VectorSpaceIdentity(**image_dict)
        text = VectorSpaceIdentity(**text_dict)
        target_path = Path(output_directory)
        existed = os.path.lexists(target_path)
        target = _private_target(output_directory, roots, resume=resume)
        initial_entries = tuple(target.iterdir()) if existed else ()
        may_initialize = not initial_entries
        _space_available(target, free_space_floor)
        _read_run(target, snapshot, snapshot_digest, roots, image, text, receipt,
            receipt_digest, resume=resume, may_initialize=may_initialize)
        scratch = _ensure_private_tree(target)
        # A crash may leave preparation files with no committed batch receipt.
        # Preserve them for review and refuse to append more work over them.
        if resume:
            _require(not any(scratch.iterdir()))
        identity_digest, vector_directory = _ensure_identity_directory(target, image)
        committed = _read_committed(target, snapshot, snapshot_digest, roots, image,
            identity_digest, receipt_digest, check)
        if os.path.lexists(target / "index.json"):
            _require(resume)
            manifest, _records, _identities = inspect_library_index(
                target, expected_snapshot=snapshot)
            return {"status": "library_index_already_complete",
                "snapshot_sha256": snapshot_digest, "record_count": manifest["record_count"],
                "failure_count": manifest["failure_count"], "activation_approved": False}

        batch_total = (len(snapshot["assets"]) + BATCH_SIZE - 1) // BATCH_SIZE
        next_batch = len(committed)
        newly_processed = 0
        batch_number = next_batch
        while batch_number < batch_total and (max_new_assets is None
                or newly_processed < max_new_assets):
            check()
            _space_available(target, free_space_floor)
            assets = snapshot["assets"][batch_number * BATCH_SIZE:
                batch_number * BATCH_SIZE + BATCH_SIZE]
            results = []
            prepared = []
            prepared_inputs = []
            for asset in assets:
                check()
                # Retained failed preparations are never silently deleted. Keep
                # enough headroom for one worst-case attempt and stop before
                # another source can exceed the fixed eight-image scratch cap.
                _require(_scratch_bytes(scratch)
                    <= MAX_SCRATCH_BYTES - preparation.MAX_COMBINED_BYTES)
                source = (_hash_source(asset["path"], roots, check) if asset["sha256"] is None
                    else _stat_source(asset["path"], roots))
                if source["failure"] is not None:
                    results.append({"status": "failed", "asset_id": asset["asset_id"],
                        "source_path": asset["path"], "code": source["failure"],
                        "source_sha256": source.get("source_sha256"),
                        "source_stat_identity": source["source_stat_identity"]})
                    continue
                expected_sha = asset["sha256"] or source.get("source_sha256")
                try:
                    item = preparation.prepare_image(asset["path"], expected_sha,
                        roots, scratch, check=check)
                    _require(item.source_sha256 == expected_sha
                        and item.original_stat_identity == source["source_stat_identity"]
                        and item.recipe_sha256 == preparation.RECIPE_SHA256)
                    prepared.append(item)
                    prepared_inputs.append((item.derived_path, item.derived_sha256))
                    results.append(None)
                except Exception:
                    if check.failed:
                        raise LibraryIndexUnavailable() from None
                    failed_source = _hash_source(asset["path"], roots, check)
                    if (failed_source["failure"] is None and asset["sha256"] is not None
                            and failed_source["source_sha256"] != asset["sha256"]):
                        code = "source_hash_mismatch"
                    else:
                        code = failed_source["failure"] or "preparation_unavailable"
                    results.append({"status": "failed", "asset_id": asset["asset_id"],
                        "source_path": asset["path"], "code": code,
                        "source_sha256": failed_source["source_sha256"],
                        "source_stat_identity": failed_source["source_stat_identity"]})
            if prepared:
                check()
                vectors = model.encode_prepared_batch(prepared_inputs, check=check)
                _require(type(vectors) in (tuple, list) and len(vectors) == len(prepared))
                prepared_index = 0
                for result_index, result in enumerate(results):
                    if result is not None:
                        continue
                    item = prepared[prepared_index]
                    vector = vectors[prepared_index]
                    prepared_index += 1
                    raw = _npy_bytes(vector)
                    decoded = _decode_npy(raw, DIMENSION)
                    _require(decoded is not None)
                    asset = assets[result_index]
                    record_id = _record_id(snapshot_digest, asset["asset_id"], identity_digest)
                    record = ImmutableVectorArtifact(record_id=record_id,
                        asset_id=asset["asset_id"], source_sha256=item.source_sha256,
                        model_name=MODEL_NAME, artifact_sha256=image.artifact_sha256,
                        preprocessing_sha256=image.preprocessing_sha256,
                        vector_space_id=image.vector_space_id, model_version=image.model_version,
                        dimension=image.dimension, normalization=image.normalization,
                        identity_sha256=identity_digest,
                        relative_path=f"image-vectors/{identity_digest}/{record_id}.npy",
                        file_sha256=hashlib.sha256(raw).hexdigest(),
                        component_sha256=canonical_vector_checksum(decoded), created_at=int(time.time()))
                    _require(validate_artifact(record, image))
                    vector_path = target / record.relative_path
                    metadata_path = vector_directory / f"{record_id}.json"
                    # O_EXCL preserves any partial artifact from an interrupted
                    # previous attempt and refuses to replace it on resume.
                    _write_bytes(vector_path, raw)
                    metadata_digest = _write_json(metadata_path, asdict(record))
                    results[result_index] = {"status": "ready", "asset_id": record.asset_id,
                        "source_path": asset["path"], "source_sha256": record.source_sha256,
                        "source_stat_identity": item.original_stat_identity,
                        "derived_sha256": item.derived_sha256,
                        "preparation_recipe_sha256": item.recipe_sha256,
                        "observed_format": item.observed_format,
                        "observed_width": item.observed_width,
                        "observed_height": item.observed_height,
                        "orientation": item.orientation,
                        "prepared_width": item.prepared_width,
                        "prepared_height": item.prepared_height,
                        "record_id": record_id, "metadata_sha256": metadata_digest}
                    verify_checkpoint(inspect_checkpoint(vector_path, record.file_sha256))
            batch = {"schema": BATCH_SCHEMA, "batch_number": batch_number,
                "snapshot_sha256": snapshot_digest, "identity_sha256": identity_digest,
                "model_receipt_sha256": receipt_digest,
                "asset_ids": [asset["asset_id"] for asset in assets], "results": results}
            batch_path = _batch_path(target, batch_number)
            _write_json(batch_path, batch)
            # Verify every committed source and artifact before releasing any
            # successfully owned preparation files from this process.
            _verify_batch(batch, batch_number, snapshot, snapshot_digest, roots, image,
                identity_digest, receipt_digest, check, verify_sources=False)
            _verify_batch_files(target, batch, image)
            for item in prepared:
                preparation.cleanup_prepared(item, scratch)
            newly_processed += len(assets)
            batch_number += 1
            committed.append(batch)
            if progress is not None:
                progress({"event": "batch_committed", "batch_number": batch_number - 1,
                    "committed_assets": min(batch_number * BATCH_SIZE, len(snapshot["assets"])),
                    "total_assets": len(snapshot["assets"])})

        if batch_number < batch_total:
            return {"status": "library_index_checkpointed_partial",
                "library_id": snapshot["library_id"], "snapshot_sha256": snapshot_digest,
                "committed_assets": min(batch_number * BATCH_SIZE, len(snapshot["assets"])),
                "total_assets": len(snapshot["assets"]), "activation_approved": False}

        records = [result for batch in committed for result in batch["results"]
            if result["status"] == "ready"]
        failures = [result for batch in committed for result in batch["results"]
            if result["status"] == "failed"]
        manifest = {"schema": INDEX_SCHEMA, "library_id": snapshot["library_id"],
            "snapshot_sha256": snapshot_digest, "snapshot_asset_count": len(snapshot["assets"]),
            "image_identity": image_dict, "text_identity": text_dict,
            "model_receipt": receipt, "model_receipt_sha256": receipt_digest,
            "records": records, "failures": failures, "record_count": len(records),
            "failure_count": len(failures), "processing_complete": True,
            "complete": not failures,
            "activation_approved": False, "relevance_accepted": False}
        _write_json(target / "index.json", manifest, limit=MAX_MANIFEST_BYTES)
        inspected, verified, identities = inspect_library_index(target,
            expected_snapshot=snapshot)
        return {"status": "library_index_prepared", "library_id": inspected["library_id"],
            "snapshot_sha256": snapshot_digest, "record_count": len(verified),
            "failure_count": inspected["failure_count"],
            "image_identity": asdict(identities["image"]),
            "text_identity": asdict(identities["text"]), "activation_approved": False}
    except LibraryIndexUnavailable:
        raise
    except Exception:
        raise LibraryIndexUnavailable() from None


def inspect_library_index(path, *, expected_snapshot=None, verify_original_bytes=False):
    """Read-only, model-free verification of a completed private library index.

    Original files are checked by approved-root membership and stable stat
    identity by default. ``verify_original_bytes=True`` also rehashes them for
    an independent native audit; vector and metadata bytes are always verified.
    """
    try:
        _require(type(verify_original_bytes) is bool)
        target = Path(path)
        if target.name == "index.json":
            manifest_path = target
            root = preparation._canonical_path(target.parent, directory=True)
        else:
            root = preparation._canonical_path(target, directory=True)
            manifest_path = root / "index.json"
        require_private_directory(root)
        manifest = _load_json_inspector(manifest_path, MAX_MANIFEST_BYTES)
        required = {"schema", "library_id", "snapshot_sha256", "snapshot_asset_count",
            "image_identity", "text_identity", "model_receipt", "model_receipt_sha256",
            "records", "failures", "record_count", "failure_count", "processing_complete", "complete",
            "activation_approved", "relevance_accepted"}
        _require(type(manifest) is dict and set(manifest) == required
            and manifest["schema"] == INDEX_SCHEMA and manifest["processing_complete"] is True
            and manifest["complete"] is (manifest["failure_count"] == 0)
            and manifest["activation_approved"] is False
            and manifest["relevance_accepted"] is False
            and type(manifest["library_id"]) is str
            and _LIBRARY_ID.fullmatch(manifest["library_id"]) is not None
            and type(manifest["snapshot_sha256"]) is str
            and _SHA.fullmatch(manifest["snapshot_sha256"]) is not None
            and type(manifest["snapshot_asset_count"]) is int
            and 0 <= manifest["snapshot_asset_count"] <= MAX_ASSETS
            and type(manifest["records"]) is list and type(manifest["failures"]) is list
            and len(manifest["records"]) + len(manifest["failures"])
                == manifest["snapshot_asset_count"]
            and manifest["record_count"] == len(manifest["records"])
            and manifest["failure_count"] == len(manifest["failures"])
            and type(manifest["model_receipt_sha256"]) is str
            and _SHA.fullmatch(manifest["model_receipt_sha256"]) is not None
            and hashlib.sha256(canonical(manifest["model_receipt"])).hexdigest()
                == manifest["model_receipt_sha256"])
        if expected_snapshot is not None:
            if type(expected_snapshot) is str:
                expected_digest = expected_snapshot
                _require(_SHA.fullmatch(expected_digest) is not None)
            else:
                expected = validate_snapshot(expected_snapshot)
                _require(expected["library_id"] == manifest["library_id"])
                expected_digest = hashlib.sha256(canonical(expected)).hexdigest()
            _require(expected_digest == manifest["snapshot_sha256"])

        image, text = _verify_model_receipt(manifest["model_receipt"])
        _require(manifest["image_identity"] == asdict(image)
            and manifest["text_identity"] == asdict(text))
        identity_digest = identity_sha256(image)
        run = _load_json_inspector(root / "run.json", MAX_DOCUMENT_BYTES)
        frozen_snapshot = validate_snapshot(_load_json_inspector(root / "snapshot.json", MAX_MANIFEST_BYTES))
        _require(set(run) == {"schema", "library_id", "snapshot_sha256", "asset_count",
                "original_roots", "image_identity", "text_identity", "model_receipt",
                "model_receipt_sha256"}
            and run["schema"] == RUN_SCHEMA
            and run["snapshot_sha256"] == manifest["snapshot_sha256"]
            and run["library_id"] == manifest["library_id"]
            and run["image_identity"] == asdict(image)
            and run["text_identity"] == asdict(text)
            and run["model_receipt_sha256"] == manifest["model_receipt_sha256"]
            and frozen_snapshot["library_id"] == manifest["library_id"]
            and len(frozen_snapshot["assets"]) == manifest["snapshot_asset_count"]
            and hashlib.sha256(canonical(frozen_snapshot)).hexdigest() == manifest["snapshot_sha256"])
        if type(expected_snapshot) is dict:
            _require(frozen_snapshot == validate_snapshot(expected_snapshot))
        roots = _validate_roots(run["original_roots"])
        prepared_dir = preparation._canonical_path(root / "prepared", directory=True)
        require_private_directory(prepared_dir)
        index_dir = root / "image-vectors" / identity_digest
        index_dir = preparation._canonical_path(index_dir, directory=True)
        require_private_directory(index_dir)
        checkpoint_dir = preparation._canonical_path(root / "checkpoints", directory=True)
        expected_batches = (manifest["snapshot_asset_count"] + BATCH_SIZE - 1) // BATCH_SIZE
        _require({item.name for item in checkpoint_dir.iterdir()} == {
            f"batch-{number:08d}.json" for number in range(expected_batches)})
        # Establish complete checkpoint provenance before artifact I/O. Once
        # the full summaries match the manifest, the record loop below performs
        # one artifact-verification pass. Its protected readers still recheck
        # file hashes/identity. Resume continues to use _verify_batch_files.
        checkpoint_records, checkpoint_failures = [], []
        for number in range(expected_batches):
            batch = _load_json_inspector(_batch_path(root, number), MAX_DOCUMENT_BYTES)
            _verify_batch(batch, number, frozen_snapshot, manifest["snapshot_sha256"],
                roots, image, identity_digest, manifest["model_receipt_sha256"],
                lambda: None, verify_sources=False)
            checkpoint_records.extend(result for result in batch["results"]
                if result["status"] == "ready")
            checkpoint_failures.extend(result for result in batch["results"]
                if result["status"] == "failed")
        _require(checkpoint_records == manifest["records"]
            and checkpoint_failures == manifest["failures"])
        expected_artifact_names = {f"{result['record_id']}.{suffix}"
            for result in checkpoint_records for suffix in ("npy", "json")}
        _require({item.name for item in index_dir.iterdir()} == expected_artifact_names
            and {item.name for item in (root / "image-vectors").iterdir()} == {identity_digest})
        _require({item.name for item in root.iterdir()} == {
            "run.json", "snapshot.json", "checkpoints", "image-vectors", "prepared", "index.json"})

        all_ids = set()
        snapshot_by_id = {asset["asset_id"]: asset for asset in frozen_snapshot["assets"]}
        _require(len(snapshot_by_id) == len(frozen_snapshot["assets"]))
        records = []
        for summary in manifest["records"]:
            _require(type(summary) is dict and set(summary) == {"status", "asset_id",
                "source_path", "source_sha256", "source_stat_identity", "derived_sha256",
                "preparation_recipe_sha256", "observed_format", "observed_width",
                "observed_height", "orientation", "prepared_width", "prepared_height",
                "record_id", "metadata_sha256"}
                and summary["status"] == "ready"
                and type(summary["asset_id"]) is str
                and _ASSET_ID.fullmatch(summary["asset_id"]) is not None
                and summary["asset_id"] not in all_ids
                and _SHA.fullmatch(summary["source_sha256"]) is not None
                and _SHA.fullmatch(summary["derived_sha256"]) is not None
                and summary["preparation_recipe_sha256"] == preparation.RECIPE_SHA256
                and summary["observed_format"] in ("JPEG", "PNG")
                and _SHA.fullmatch(summary["record_id"]) is not None
                and _SHA.fullmatch(summary["metadata_sha256"]) is not None)
            source_asset = snapshot_by_id.get(summary["asset_id"])
            _require(source_asset is not None and source_asset["path"] == summary["source_path"]
                and (source_asset["sha256"] is None
                    or source_asset["sha256"] == summary["source_sha256"]))
            all_ids.add(summary["asset_id"])
            if verify_original_bytes:
                _verify_source(summary["source_path"], summary["source_sha256"],
                    summary["source_stat_identity"], roots, lambda: None)
            else:
                _verify_source_stat(summary["source_path"], summary["source_stat_identity"], roots)
            record_id = _record_id(manifest["snapshot_sha256"], summary["asset_id"], identity_digest)
            _require(summary["record_id"] == record_id)
            metadata_path = index_dir / f"{record_id}.json"
            metadata = _load_json_inspector(metadata_path, MAX_DOCUMENT_BYTES,
                expected_sha256=summary["metadata_sha256"])
            _require(hashlib.sha256(canonical(metadata) + b"\n").hexdigest()
                == summary["metadata_sha256"])
            _require(set(metadata) == set(ImmutableVectorArtifact.__dataclass_fields__))
            record = ImmutableVectorArtifact(**metadata)
            _require(validate_artifact(record, image)
                and record.record_id == record_id and record.asset_id == summary["asset_id"]
                and record.source_sha256 == summary["source_sha256"]
                and record.relative_path == f"image-vectors/{identity_digest}/{record_id}.npy")
            pin = inspect_checkpoint(index_dir / f"{record_id}.npy", record.file_sha256)
            verify_checkpoint(pin)
            vector = _read_vector(root, record)
            _require(vector is not None
                and canonical_vector_checksum(vector) == record.component_sha256)
            _canonical_components(VectorRecord(record.asset_id, image, vector,
                record.component_sha256), image)
            records.append(record)

        for failure in manifest["failures"]:
            _require(type(failure) is dict and set(failure) == {"status", "asset_id",
                "source_path", "code", "source_sha256", "source_stat_identity"}
                and failure["status"] == "failed"
                and type(failure["asset_id"]) is str
                and _ASSET_ID.fullmatch(failure["asset_id"]) is not None
                and failure["asset_id"] not in all_ids
                and failure["code"] in {"source_missing", "source_not_approved",
                    "source_size_invalid", "source_hash_mismatch", "source_unavailable",
                    "preparation_unavailable"})
            source_asset = snapshot_by_id.get(failure["asset_id"])
            _require(source_asset is not None and source_asset["path"] == failure["source_path"])
            if failure["code"] == "source_hash_mismatch":
                _require(source_asset["sha256"] is not None
                    and failure["source_sha256"] is not None
                    and failure["source_sha256"] != source_asset["sha256"])
            elif source_asset["sha256"] is not None and failure["source_sha256"] is not None:
                _require(failure["source_sha256"] == source_asset["sha256"])
            all_ids.add(failure["asset_id"])
            state = (_hash_source(failure["source_path"], roots, lambda: None)
                if verify_original_bytes else _stat_source(failure["source_path"], roots))
            if failure["code"] == "source_missing":
                _require(state["failure"] == "source_missing"
                    and failure["source_sha256"] is None
                    and failure["source_stat_identity"] is None)
            elif failure["code"] == "source_not_approved":
                _require(state["failure"] == "source_not_approved"
                    and failure["source_sha256"] is None
                    and failure["source_stat_identity"] is None)
            elif failure["code"] == "source_size_invalid":
                _require(state["failure"] == "source_size_invalid"
                    and failure["source_sha256"] is None
                    and failure["source_stat_identity"] == state["source_stat_identity"])
            elif failure["code"] == "source_unavailable":
                _require(state["failure"] == "source_unavailable"
                    and failure["source_sha256"] is None
                    and failure["source_stat_identity"] is None)
            else:
                _require(state["failure"] is None
                    and state["source_stat_identity"] == failure["source_stat_identity"])
                if verify_original_bytes:
                    _require(state["source_sha256"] == failure["source_sha256"])
        _require(len(all_ids) == manifest["snapshot_asset_count"])
        return manifest, tuple(records), {"image": image, "text": text}
    except LibraryIndexUnavailable:
        raise
    except Exception:
        raise LibraryIndexUnavailable() from None

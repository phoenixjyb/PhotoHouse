"""Small, standard-library checkpoint and recipe receipt helpers.

These receipts bind a load to the exact checkpoint bytes that were inspected.
They do not infer a checkpoint identity from a caller supplied model version.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping


_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_CHUNK_BYTES = 4 * 1024 * 1024
_MAX_CHECKPOINT_BYTES = 8 * 1024**3


class ReceiptError(ValueError):
    """A checkpoint or receipt input failed validation."""


@dataclass(frozen=True)
class CheckpointPin:
    """Immutable path, digest, and filesystem identity captured at inspection."""

    path: str
    sha256: str
    stat_identity: tuple[int, int, int, int, int, int, int]


def _valid_sha256(value: object) -> bool:
    return type(value) is str and _SHA256_RE.fullmatch(value) is not None


def _stat_identity(info: os.stat_result) -> tuple[int, int, int, int, int, int, int]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _checkpoint_path(path: os.PathLike[str] | str) -> Path:
    try:
        candidate = Path(path)
    except (TypeError, ValueError) as error:
        raise ReceiptError("invalid_checkpoint_path") from error
    if not candidate.is_absolute() or candidate == Path(candidate.anchor):
        raise ReceiptError("absolute_checkpoint_path_required")
    try:
        absolute = Path(os.path.abspath(candidate))
        if absolute.parent.resolve(strict=True) != absolute.parent:
            raise ReceiptError("symlinked_checkpoint_parent")
        info = absolute.lstat()
    except OSError as error:
        raise ReceiptError("checkpoint_unavailable") from error
    if stat.S_ISLNK(info.st_mode) or _is_reparse_point(info):
        raise ReceiptError("checkpoint_link_refused")
    if not stat.S_ISREG(info.st_mode):
        raise ReceiptError("checkpoint_not_regular")
    return absolute


def _is_reparse_point(info: os.stat_result) -> bool:
    # st_file_attributes is present on Windows; keep this helper importable on
    # platforms that do not define Windows file attribute constants.
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(info, "st_file_attributes", 0) & reparse_flag)


def _open_pinned(path: Path, expected_identity: tuple[int, int, int, int, int, int, int]):
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise ReceiptError("checkpoint_open_failed") from error
    try:
        opened = os.fstat(descriptor)
        if (_is_reparse_point(opened) or not stat.S_ISREG(opened.st_mode)
                or _stat_identity(opened) != expected_identity):
            raise ReceiptError("checkpoint_changed")
        return os.fdopen(descriptor, "rb")
    except BaseException:
        os.close(descriptor)
        raise


def _digest_file(path: Path, identity: tuple[int, int, int, int, int, int, int]) -> str:
    if not 0 < identity[3] <= _MAX_CHECKPOINT_BYTES:
        raise ReceiptError("checkpoint_byte_budget")
    digest = hashlib.sha256()
    total = 0
    try:
        with _open_pinned(path, identity) as stream:
            while True:
                chunk = stream.read(_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > identity[3]:
                    raise ReceiptError("checkpoint_changed")
                digest.update(chunk)
    except OSError as error:
        raise ReceiptError("checkpoint_read_failed") from error
    return digest.hexdigest()


def inspect_checkpoint(path: os.PathLike[str] | str, expected_sha256: str) -> CheckpointPin:
    """Hash a regular checkpoint and return a pin if its digest matches.

    Hashing is streamed, so large model files do not need to fit in memory.
    The file identity is compared before opening, on the open descriptor, and
    after hashing to detect replacement or mutation during inspection.
    """
    if not _valid_sha256(expected_sha256):
        raise ReceiptError("invalid_expected_sha256")
    checkpoint = _checkpoint_path(path)
    try:
        before_info = checkpoint.lstat()
    except OSError as error:
        raise ReceiptError("checkpoint_unavailable") from error
    before = _stat_identity(before_info)
    digest = _digest_file(checkpoint, before)
    try:
        after_info = checkpoint.lstat()
    except OSError as error:
        raise ReceiptError("checkpoint_changed") from error
    if (_is_reparse_point(after_info) or not stat.S_ISREG(after_info.st_mode)
            or _stat_identity(after_info) != before):
        raise ReceiptError("checkpoint_changed")
    if digest != expected_sha256:
        raise ReceiptError("checkpoint_sha256_mismatch")
    return CheckpointPin(str(checkpoint), digest, before)


def verify_checkpoint(pin: CheckpointPin) -> CheckpointPin:
    """Re-hash a previously inspected checkpoint and require the same identity."""
    if (type(pin) is not CheckpointPin or not _valid_sha256(getattr(pin, "sha256", None))
            or type(getattr(pin, "path", None)) is not str
            or type(getattr(pin, "stat_identity", None)) is not tuple
            or len(pin.stat_identity) != 7
            or any(type(value) is not int for value in pin.stat_identity)):
        raise ReceiptError("invalid_checkpoint_pin")
    checkpoint = _checkpoint_path(pin.path)
    try:
        before_info = checkpoint.lstat()
    except OSError as error:
        raise ReceiptError("checkpoint_changed") from error
    before = _stat_identity(before_info)
    if before != pin.stat_identity:
        raise ReceiptError("checkpoint_changed")
    digest = _digest_file(checkpoint, before)
    try:
        after_info = checkpoint.lstat()
    except OSError as error:
        raise ReceiptError("checkpoint_changed") from error
    if (_is_reparse_point(after_info) or not stat.S_ISREG(after_info.st_mode)
            or _stat_identity(after_info) != pin.stat_identity):
        raise ReceiptError("checkpoint_changed")
    if digest != pin.sha256:
        raise ReceiptError("checkpoint_changed")
    return pin


def _validate_recipe_value(value: Any) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ReceiptError("non_finite_recipe_number")
        return
    if type(value) is list:
        for item in value:
            _validate_recipe_value(item)
        return
    if type(value) is dict:
        if any(type(key) is not str for key in value):
            raise ReceiptError("recipe_keys_must_be_strings")
        for item in value.values():
            _validate_recipe_value(item)
        return
    raise ReceiptError("recipe_must_use_json_primitives")


def recipe_sha256(recipe: Mapping[str, Any]) -> str:
    """Return a canonical SHA-256 for an explicit JSON primitive recipe.

    Object keys are sorted, whitespace is fixed, and non-standard JSON values
    (including NaN and infinities) are refused instead of silently encoded.
    """
    if type(recipe) is not dict:
        raise ReceiptError("recipe_must_be_object")
    _validate_recipe_value(recipe)
    try:
        canonical = json.dumps(
            recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise ReceiptError("invalid_recipe_json") from error
    return hashlib.sha256(canonical).hexdigest()

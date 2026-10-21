"""Prepare bounded, private image representations for the dedicated library worker.

This module is intentionally not an application-server image endpoint. Call it
only from the single-process, resource-capped library indexing worker. Importing
it performs no image-library import, file access, model work, or network access.
Originals are read-only; the worker makes private byte-identical copies before
decoding and writes a separate canonical RGB PNG representation.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import stat
import threading
import warnings


MAX_ORIGINAL_BYTES = 128 * 1024 * 1024
MAX_IMAGE_PIXELS = 256 * 1024 * 1024
MAX_IMAGE_SIDE = 32_768
MAX_PREPARED_SIDE = 2_048
MAX_DERIVED_BYTES = 16 * 1024 * 1024
MAX_COMBINED_BYTES = 144 * 1024 * 1024
COPY_CHUNK_BYTES = 1024 * 1024
PROFILE_SCHEMA = "photohouse.library_image_input_profile.v1"

# Keep this JSON-compatible and deterministic. The owning adapter pins this
# module's source digest separately as part of its image recipe.
PROFILE_RECIPE = {
    "schema": PROFILE_SCHEMA,
    "accepted_formats": ["JPEG", "PNG"],
    "animation": "single_frame_only",
    "max_original_bytes": MAX_ORIGINAL_BYTES,
    "max_original_pixels": MAX_IMAGE_PIXELS,
    "max_original_side": MAX_IMAGE_SIDE,
    "max_prepared_side": MAX_PREPARED_SIDE,
    "max_derived_bytes": MAX_DERIVED_BYTES,
    "max_combined_bytes": MAX_COMBINED_BYTES,
    "orientation": "exif_transpose_then_discard_metadata",
    "jpeg_draft": {"mode": "RGB", "size": [MAX_PREPARED_SIDE, MAX_PREPARED_SIDE]},
    "color": "convert_to_rgb_without_icc_reinterpretation",
    "resize": {"method": "thumbnail", "resample": "LANCZOS", "reducing_gap": 3.0},
    "output": {"format": "PNG", "metadata": "stripped", "mode": "RGB"},
}
RECIPE_SHA256 = hashlib.sha256(json.dumps(
    PROFILE_RECIPE, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
).encode("ascii")).hexdigest()

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_OWNED_NAME = re.compile(r"library-input-([0-9a-f]{32})\.(original|derived\.png)\Z", re.ASCII)
_PRIVATE_LOCK = threading.Lock()
_OWNED: dict[int, tuple[str, str, str, str, str]] = {}


class ImageInputUnavailable(ValueError):
    """Raised when a source or private derivative cannot be safely prepared."""

    def __init__(self) -> None:
        super().__init__("library_image_input_unavailable")


@dataclass(frozen=True, slots=True)
class PreparedImage:
    source_sha256: str
    derived_sha256: str
    original_path: Path
    original_stat_identity: dict[str, int]
    private_original_copy: Path
    derived_path: Path
    original_bytes: int
    observed_format: str
    observed_width: int
    observed_height: int
    orientation: int
    prepared_width: int
    prepared_height: int
    recipe_sha256: str
    recipe: dict


def _stable_identity(info: os.stat_result) -> tuple[int, ...]:
    identity = (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_nlink)
    if os.name == "nt":
        birthtime = getattr(info, "st_birthtime_ns", None)
        if type(birthtime) is not int:
            raise ImageInputUnavailable()
        return identity + (birthtime,)
    return identity + (info.st_ctime_ns,)


def _stat_receipt(info: os.stat_result) -> dict[str, int]:
    receipt = {
        "device": int(info.st_dev),
        "inode": int(info.st_ino),
        "mode": int(info.st_mode),
        "size": int(info.st_size),
        "mtime_ns": int(info.st_mtime_ns),
        "nlink": int(info.st_nlink),
    }
    if os.name == "nt":
        birthtime = getattr(info, "st_birthtime_ns", None)
        if type(birthtime) is not int:
            raise ImageInputUnavailable()
        receipt["birthtime_ns"] = int(birthtime)
    return receipt


def _reparse(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _canonical_path(value: str | os.PathLike, *, directory: bool) -> Path:
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ImageInputUnavailable()
    try:
        if path.resolve(strict=True) != path:
            raise ImageInputUnavailable()
        # lstat every component so a junction/symlink cannot hide behind a
        # successful resolve. Mount points remain valid canonical directories.
        for component in reversed(path.parents):
            info = component.lstat()
            if stat.S_ISLNK(info.st_mode) or _reparse(info):
                raise ImageInputUnavailable()
        info = path.lstat()
        expected = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if not expected or stat.S_ISLNK(info.st_mode) or _reparse(info):
            raise ImageInputUnavailable()
    except (OSError, RuntimeError, ValueError):
        raise ImageInputUnavailable() from None
    return path


def _approved_source(path: str | os.PathLike, roots: object) -> Path:
    source = _canonical_path(path, directory=False)
    if type(roots) not in (list, tuple) or not roots:
        raise ImageInputUnavailable()
    approved = False
    for root_value in roots:
        root = _canonical_path(root_value, directory=True)
        try:
            if os.path.commonpath((str(source), str(root))) == str(root) and source != root:
                approved = True
        except (OSError, ValueError):
            continue
    if not approved:
        raise ImageInputUnavailable()
    return source


def _private_scratch(value: str | os.PathLike, roots: tuple[Path, ...]) -> Path:
    scratch = _canonical_path(value, directory=True)
    # Scratch must live outside the repository source and every source root.
    source_root = Path(__file__).resolve().parents[2]
    for forbidden in (source_root, *roots):
        try:
            common = os.path.commonpath((str(scratch), str(forbidden)))
        except (OSError, ValueError):
            continue
        if common == str(scratch) or common == str(forbidden):
            raise ImageInputUnavailable()
    try:
        from app.access.private_storage import require_private_directory
        require_private_directory(scratch)
    except Exception:
        raise ImageInputUnavailable() from None
    return scratch


def _open_source(path: Path):
    path = _canonical_path(path, directory=False)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
        stream = os.fdopen(descriptor, "rb")
        opened = os.fstat(stream.fileno())
        current = path.lstat()
        if (not stat.S_ISREG(opened.st_mode) or stat.S_ISLNK(current.st_mode) or _reparse(current)
                or _stable_identity(opened) != _stable_identity(current)):
            stream.close()
            raise ImageInputUnavailable()
        return stream, _stable_identity(opened)
    except ImageInputUnavailable:
        raise
    except Exception:
        raise ImageInputUnavailable() from None


def _new_private_file(path: Path):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        stream = os.fdopen(descriptor, "wb")
        try:
            _require_private_file(path)
        except Exception:
            stream.close()
            raise
        return stream
    except Exception:
        raise ImageInputUnavailable() from None


def _require_private_file(path: Path) -> None:
    try:
        from app.access.private_storage import require_private_file
        require_private_file(path)
    except Exception:
        raise ImageInputUnavailable() from None


def _check(check) -> None:
    try:
        check()
    except Exception:
        raise ImageInputUnavailable() from None


@contextmanager
def _bounded_pillow_profile(Image):
    """Raise Pillow's guard only while our own exact header limits are active."""
    with _PRIVATE_LOCK:
        previous = Image.MAX_IMAGE_PIXELS
        try:
            Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                yield
        finally:
            Image.MAX_IMAGE_PIXELS = previous


def _copy_original(source: Path, destination: Path, expected_sha256: str, check) -> tuple[str, int, tuple[int, ...]]:
    digest = hashlib.sha256()
    total = 0
    stream, identity = _open_source(source)
    with stream:
        before = identity
        with _new_private_file(destination) as output:
            while True:
                _check(check)
                block = stream.read(min(COPY_CHUNK_BYTES, MAX_ORIGINAL_BYTES + 1 - total))
                if not block:
                    break
                total += len(block)
                if total > MAX_ORIGINAL_BYTES:
                    raise ImageInputUnavailable()
                digest.update(block)
                output.write(block)
            output.flush()
            os.fsync(output.fileno())
        opened_after = os.fstat(stream.fileno())
        _canonical_path(source, directory=False)
        path_after = source.lstat()
        if (_stable_identity(opened_after) != before or _stable_identity(path_after) != before
                or stat.S_ISLNK(path_after.st_mode) or _reparse(path_after)):
            raise ImageInputUnavailable()
    actual = digest.hexdigest()
    if total <= 0 or actual != expected_sha256:
        raise ImageInputUnavailable()
    _require_private_file(destination)
    return actual, total, before


def _verify_source_unchanged(source: Path, identity: tuple[int, ...], expected_sha256: str, check) -> None:
    digest = hashlib.sha256()
    stream, current_identity = _open_source(source)
    if current_identity != identity:
        stream.close()
        raise ImageInputUnavailable()
    total = 0
    with stream:
        while True:
            _check(check)
            block = stream.read(COPY_CHUNK_BYTES)
            if not block:
                break
            total += len(block)
            if total > MAX_ORIGINAL_BYTES:
                raise ImageInputUnavailable()
            digest.update(block)
        after = os.fstat(stream.fileno())
        _canonical_path(source, directory=False)
        path_after = source.lstat()
        if (_stable_identity(after) != identity or _stable_identity(path_after) != identity
                or stat.S_ISLNK(path_after.st_mode) or _reparse(path_after)):
            raise ImageInputUnavailable()
    if total <= 0 or digest.hexdigest() != expected_sha256:
        raise ImageInputUnavailable()


def _decode_and_encode(original_copy: Path, check):
    try:
        from PIL import Image, ImageOps
    except Exception:
        raise ImageInputUnavailable() from None

    try:
        raw = original_copy.read_bytes()
        if not raw or len(raw) > MAX_ORIGINAL_BYTES:
            raise ImageInputUnavailable()
        with _bounded_pillow_profile(Image):
            with Image.open(io.BytesIO(raw)) as opened:
                observed_format = opened.format
                width, height = opened.size
                if (observed_format not in ("JPEG", "PNG")
                        or not 0 < width <= MAX_IMAGE_SIDE
                        or not 0 < height <= MAX_IMAGE_SIDE
                        or width * height > MAX_IMAGE_PIXELS):
                    raise ImageInputUnavailable()
                opened.verify()
            _check(check)
            with Image.open(io.BytesIO(raw)) as opened:
                frame_count = getattr(opened, "n_frames", 1)
                orientation = int(opened.getexif().get(274, 1))
                if (observed_format not in ("JPEG", "PNG") or frame_count != 1
                        or not 0 < width <= MAX_IMAGE_SIDE or not 0 < height <= MAX_IMAGE_SIDE
                        or width * height > MAX_IMAGE_PIXELS or orientation not in range(1, 9)):
                    raise ImageInputUnavailable()
                if observed_format == "JPEG":
                    opened.draft("RGB", (MAX_PREPARED_SIDE, MAX_PREPARED_SIDE))
                oriented = ImageOps.exif_transpose(opened)
                try:
                    rgb = oriented.convert("RGB")
                finally:
                    oriented.close()
                try:
                    rgb.thumbnail((MAX_PREPARED_SIDE, MAX_PREPARED_SIDE),
                                  Image.Resampling.LANCZOS, reducing_gap=3.0)
                    rgb.info.clear()
                    _check(check)
                    output = io.BytesIO()
                    rgb.save(output, format="PNG", optimize=False)
                    encoded = output.getvalue()
                    if (not encoded or len(encoded) > MAX_DERIVED_BYTES
                            or len(raw) + len(encoded) > MAX_COMBINED_BYTES):
                        raise ImageInputUnavailable()
                    return (observed_format, width, height, orientation,
                            rgb.width, rgb.height, encoded)
                finally:
                    rgb.close()
    except ImageInputUnavailable:
        raise
    except Exception:
        raise ImageInputUnavailable() from None


def prepare_image(source_path, expected_sha256, original_roots, private_scratch, *, check=lambda: None):
    """Copy, hash, decode and canonicalize one approved source without mutation.

    ``original_roots`` must be a non-empty sequence of canonical roots. The
    private scratch directory must already exist, be owner-private, and sit
    outside both the repository and all approved source roots. Hard-linked
    source files are accepted; generated scratch files must be private regular
    files with a single link.
    """
    if type(expected_sha256) is not str or not _SHA256.fullmatch(expected_sha256):
        raise ImageInputUnavailable()
    source = _approved_source(source_path, original_roots)
    roots = tuple(_canonical_path(root, directory=True) for root in original_roots)
    scratch = _private_scratch(private_scratch, roots)
    token = secrets.token_hex(16)
    private_copy = scratch / f"library-input-{token}.original"
    derived = scratch / f"library-input-{token}.derived.png"
    try:
        source_sha, original_bytes, source_identity = _copy_original(source, private_copy, expected_sha256, check)
        source_stat_identity = _stat_receipt(source.lstat())
        observed_format, width, height, orientation, prepared_width, prepared_height, encoded = _decode_and_encode(private_copy, check)
        if original_bytes + len(encoded) > MAX_COMBINED_BYTES:
            raise ImageInputUnavailable()
        with _new_private_file(derived) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _require_private_file(derived)
        _verify_source_unchanged(source, source_identity, source_sha, check)
        derived_sha = hashlib.sha256(encoded).hexdigest()
        # Confirm both immutable source bytes and generated bytes before claiming
        # the returned receipt.
        if hashlib.sha256(private_copy.read_bytes()).hexdigest() != source_sha:
            raise ImageInputUnavailable()
        if hashlib.sha256(derived.read_bytes()).hexdigest() != derived_sha:
            raise ImageInputUnavailable()
        _check(check)
        result = PreparedImage(source_sha, derived_sha, source, source_stat_identity, private_copy, derived,
            original_bytes, observed_format, width, height, orientation,
            prepared_width, prepared_height, RECIPE_SHA256, copy.deepcopy(PROFILE_RECIPE))
        _OWNED[id(result)] = (str(scratch), str(private_copy), source_sha, str(derived), derived_sha)
        return result
    except ImageInputUnavailable:
        raise
    except Exception:
        raise ImageInputUnavailable() from None


def cleanup_prepared(prepared: PreparedImage, private_scratch) -> None:
    """Remove only verified files returned by this process after successful use."""
    if type(prepared) is not PreparedImage:
        raise ImageInputUnavailable()
    ownership = _OWNED.get(id(prepared))
    if ownership is None:
        raise ImageInputUnavailable()
    try:
        scratch = _canonical_path(private_scratch, directory=True)
        from app.access.private_storage import require_private_directory
        require_private_directory(scratch)
        expected_scratch, original_copy, original_sha, derived_path, derived_sha = ownership
        if str(scratch) != expected_scratch or str(prepared.private_original_copy) != original_copy or str(prepared.derived_path) != derived_path:
            raise ImageInputUnavailable()
        original_name = _OWNED_NAME.fullmatch(Path(original_copy).name)
        derived_name = _OWNED_NAME.fullmatch(Path(derived_path).name)
        if (original_name is None or derived_name is None
                or original_name.group(1) != derived_name.group(1)
                or original_name.group(2) != "original" or derived_name.group(2) != "derived.png"):
            raise ImageInputUnavailable()
        source = _canonical_path(prepared.original_path, directory=False)
        if source == scratch or source == Path(original_copy) or source == Path(derived_path):
            raise ImageInputUnavailable()
        original_file, derived_file = Path(original_copy), Path(derived_path)
        for path, expected in ((original_file, original_sha), (derived_file, derived_sha)):
            _require_private_file(path)
            if path.parent != scratch or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise ImageInputUnavailable()
        original_stat, derived_stat = original_file.stat(), derived_file.stat()
        source_stat = source.stat()
        if ((original_stat.st_dev, original_stat.st_ino) == (source_stat.st_dev, source_stat.st_ino)
                or (derived_stat.st_dev, derived_stat.st_ino) == (source_stat.st_dev, source_stat.st_ino)):
            raise ImageInputUnavailable()
        original_file.unlink()
        derived_file.unlink()
        del _OWNED[id(prepared)]
    except ImageInputUnavailable:
        raise
    except Exception:
        raise ImageInputUnavailable() from None

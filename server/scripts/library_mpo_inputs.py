"""Prepare bounded MPO primary-frame pixels for private worker qualification.

This profile is independent from ``library_image_inputs`` and is not wired to
the current index/model adapter. Call it only from a single-process,
resource-capped worker. It treats an MPO as one candidate: frame zero, the
Baseline MP Primary Image. Auxiliary images are bounded container payload and
are never opened or decoded.
"""
from __future__ import annotations

from dataclasses import dataclass
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import struct
import threading

import library_image_inputs as base


PROFILE_SCHEMA = "photohouse.library_mpo_primary_input_profile.v1"
MAX_MPO_FRAMES = 16
_BASE_RECIPE = copy.deepcopy(base.PROFILE_RECIPE)
_BASE_RECIPE_SHA256 = base.RECIPE_SHA256
PROFILE_RECIPE = {
    "schema": PROFILE_SCHEMA,
    "candidate_policy": "frame_zero_baseline_mp_primary_only",
    "auxiliary_policy": "validate_mpf_ranges_but_never_open_or_decode",
    "mpf": {
        "minimum_frames": 2,
        "maximum_frames": MAX_MPO_FRAMES,
        "required_primary_mp_type": "0x030000",
        "image_data_format": "JPEG",
        "reject_overlaps_and_out_of_bounds_ranges": True,
    },
    "base_recipe_schema": base.PROFILE_SCHEMA,
    "base_recipe_sha256": _BASE_RECIPE_SHA256,
    "base_recipe": _BASE_RECIPE,
}
RECIPE_SHA256 = hashlib.sha256(json.dumps(
    PROFILE_RECIPE, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
).encode("ascii")).hexdigest()

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_OWNED_NAME = re.compile(r"library-mpo-input-([0-9a-f]{32})\.(original|derived\.png)\Z", re.ASCII)
_LOCK = threading.Lock()
_OWNED: dict[int, tuple[str, str, str, str, str]] = {}
_KNOWN_MP_TYPES = {0x000000, 0x010001, 0x010002, 0x020001, 0x020002, 0x020003, 0x030000}
_SCAN_CHECK_BYTES = 1024 * 1024


class MpoImageInputUnavailable(base.ImageInputUnavailable):
    """Raised when an MPO cannot be safely admitted under this profile."""

    def __init__(self) -> None:
        ValueError.__init__(self, "library_mpo_image_input_unavailable")


@dataclass(frozen=True, slots=True)
class MpoPreparedImage:
    source_sha256: str
    derived_sha256: str
    original_path: Path
    original_stat_identity: dict[str, int]
    private_original_copy: Path
    derived_path: Path
    original_bytes: int
    observed_format: str
    frame_count: int
    observed_width: int
    observed_height: int
    orientation: int
    prepared_width: int
    prepared_height: int
    recipe_sha256: str
    recipe: dict


@dataclass(frozen=True, slots=True)
class _MpEntry:
    attribute: int
    size: int
    data_offset: int
    dependent_entry_1: int
    dependent_entry_2: int
    start: int
    end: int


def _need(condition: bool) -> None:
    if not condition:
        raise MpoImageInputUnavailable()


def _read_u16(raw: bytes, offset: int, endian: str) -> int:
    _need(0 <= offset <= len(raw) - 2)
    return struct.unpack_from(endian + "H", raw, offset)[0]


def _read_u32(raw: bytes, offset: int, endian: str) -> int:
    _need(0 <= offset <= len(raw) - 4)
    return struct.unpack_from(endian + "I", raw, offset)[0]


def _find_scan_marker(raw: bytes, start: int, end: int, check) -> int:
    while start < end:
        block_end = min(start + _SCAN_CHECK_BYTES, end)
        marker = raw.find(b"\xff", start, block_end)
        base._check(check)
        if marker >= 0:
            return marker
        start = block_end
    return -1


def _jpeg_has_exact_eoi(raw: bytes, start: int, end: int, check) -> bool:
    """Check JPEG marker framing without decoding pixels or following MPF data."""
    if end - start < 4 or raw[start:start + 2] != b"\xff\xd8":
        return False
    position = start + 2
    next_check = position + _SCAN_CHECK_BYTES
    in_scan = False
    while position < end:
        if in_scan:
            marker_start = _find_scan_marker(raw, position, end, check)
            if marker_start < 0:
                return False
            marker_position = marker_start + 1
            fill_check = marker_position + _SCAN_CHECK_BYTES
            while marker_position < end and raw[marker_position] == 0xFF:
                marker_position += 1
                if marker_position >= fill_check:
                    base._check(check)
                    fill_check = marker_position + _SCAN_CHECK_BYTES
            if marker_position >= end:
                return False
            marker = raw[marker_position]
            if marker == 0x00 or 0xD0 <= marker <= 0xD7:
                position = marker_position + 1
                continue
            position = marker_start
            in_scan = False
        if raw[position] != 0xFF:
            return False
        fill_check = position + _SCAN_CHECK_BYTES
        while position < end and raw[position] == 0xFF:
            position += 1
            if position >= fill_check:
                base._check(check)
                fill_check = position + _SCAN_CHECK_BYTES
        if position >= end:
            return False
        marker = raw[position]
        position += 1
        if marker == 0xD9:
            return position == end
        if marker in (0x00, 0xD8) or 0xD0 <= marker <= 0xD7 or marker == 0x01:
            return False
        if position > end - 2:
            return False
        segment_length = struct.unpack_from(">H", raw, position)[0]
        if segment_length < 2 or position + segment_length > end:
            return False
        position += segment_length
        if position >= next_check:
            base._check(check)
            next_check = position + _SCAN_CHECK_BYTES
        if marker == 0xDA:
            in_scan = True
    return False


def _mpf_segment(raw: bytes, check) -> tuple[int, int]:
    """Return the TIFF header start/end from exactly one pre-SOS MPF APP2."""
    _need(len(raw) >= 4 and raw[:2] == b"\xff\xd8")
    offset = 2
    found: tuple[int, int] | None = None
    saw_sos = False
    next_check = _SCAN_CHECK_BYTES
    while offset < len(raw):
        _need(raw[offset] == 0xFF)
        while offset < len(raw) and raw[offset] == 0xFF:
            offset += 1
            if offset >= next_check:
                base._check(check)
                next_check = offset + _SCAN_CHECK_BYTES
        _need(offset < len(raw))
        marker = raw[offset]
        offset += 1
        if marker == 0xDA:
            saw_sos = True
            break
        _need(marker not in (0x00, 0xD8, 0xD9) and not 0xD0 <= marker <= 0xD7 and marker != 0x01)
        _need(offset <= len(raw) - 2)
        segment_length = struct.unpack_from(">H", raw, offset)[0]
        _need(segment_length >= 2 and offset + segment_length <= len(raw))
        payload_start = offset + 2
        payload_end = offset + segment_length
        if marker == 0xE2 and raw[payload_start:payload_start + 4] == b"MPF\x00":
            _need(found is None and payload_start + 4 < payload_end)
            found = (payload_start + 4, payload_end)
        offset += segment_length
        if offset >= next_check:
            base._check(check)
            next_check = offset + _SCAN_CHECK_BYTES
    _need(saw_sos and found is not None)
    return found


def _parse_mpf(raw: bytes, check=lambda: None) -> tuple[_MpEntry, ...]:
    """Bound and validate the MP Index before Pillow parses the container."""
    tiff_start, tiff_end = _mpf_segment(raw, check)
    _need(tiff_end - tiff_start >= 8)
    header = raw[tiff_start:tiff_start + 8]
    if header[:2] == b"II":
        endian = "<"
    elif header[:2] == b"MM":
        endian = ">"
    else:
        raise MpoImageInputUnavailable()
    _need(struct.unpack_from(endian + "H", header, 2)[0] == 42)
    ifd_relative = struct.unpack_from(endian + "I", header, 4)[0]
    _need(8 <= ifd_relative <= tiff_end - tiff_start - 2)
    ifd = tiff_start + ifd_relative
    tag_count = _read_u16(raw, ifd, endian)
    # The APP2 segment is small, but explicitly bound the IFD before walking it.
    # Only the three required MP Index tags are admitted. This prevents Pillow
    # from following attacker-controlled offsets in unknown IFD fields.
    _need(tag_count == 3)
    ifd_end = ifd + 2 + tag_count * 12 + 4
    _need(ifd_end <= tiff_end)
    _need(_read_u32(raw, ifd_end - 4, endian) == 0)

    fields: dict[int, tuple[int, int, int]] = {}
    for index in range(tag_count):
        pos = ifd + 2 + index * 12
        tag = _read_u16(raw, pos, endian)
        kind = _read_u16(raw, pos + 2, endian)
        count = _read_u32(raw, pos + 4, endian)
        value = _read_u32(raw, pos + 8, endian)
        if tag in (0xB000, 0xB001, 0xB002):
            _need(tag not in fields)
            fields[tag] = (kind, count, value)
    _need(set(fields) == {0xB000, 0xB001, 0xB002})

    version_kind, version_count, _ = fields[0xB000]
    version_value_pos = ifd + 2 + next(
        i for i in range(tag_count)
        if _read_u16(raw, ifd + 2 + i * 12, endian) == 0xB000
    ) * 12 + 8
    _need(version_kind == 7 and version_count == 4 and raw[version_value_pos:version_value_pos + 4] == b"0100")

    number_kind, number_count, frame_count = fields[0xB001]
    _need(number_kind == 4 and number_count == 1 and 2 <= frame_count <= MAX_MPO_FRAMES)
    entry_kind, entry_count, entries_relative = fields[0xB002]
    _need(entry_kind == 7 and entry_count == frame_count * 16)
    entries_start = tiff_start + entries_relative
    entries_end = entries_start + entry_count
    _need(entries_start >= ifd_end and entries_end <= tiff_end)

    entries: list[_MpEntry] = []
    for index in range(frame_count):
        attribute, size, data_offset, dep1, dep2 = struct.unpack_from(
            endian + "IIIHH", raw, entries_start + index * 16,
        )
        reserved = (attribute >> 27) & 0x3
        data_format = (attribute >> 24) & 0x7
        mp_type = attribute & 0x00FFFFFF
        _need(reserved == 0 and data_format == 0 and mp_type in _KNOWN_MP_TYPES)
        _need(dep1 <= frame_count and dep2 <= frame_count)
        _need(dep1 != index + 1 and dep2 != index + 1)
        if index == 0:
            _need(mp_type == 0x030000 and data_offset == 0)
            _need((attribute & ((1 << 31) | (1 << 30))) == 0)
            _need(dep1 == 0 and dep2 == 0)
            start = 0
        else:
            start = tiff_start + data_offset
        end = start + size
        _need(size >= 4 and end <= len(raw))
        entries.append(_MpEntry(attribute, size, data_offset, dep1, dep2, start, end))

    intervals = sorted((entry.start, entry.end) for entry in entries)
    _need(all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:])))
    _need(entries[0].start == 0 and all(entry.start >= entries[0].end for entry in entries[1:]))
    # Complete all arithmetic/range/overlap checks before scanning any JPEG
    # bytes. The disjoint intervals make total framing work no greater than the
    # original file size even when the table is attacker supplied.
    for start, end in intervals:
        base._check(check)
        _need(_jpeg_has_exact_eoi(raw, start, end, check))
    return tuple(entries)


def _decode_primary(raw: bytes, entries: tuple[_MpEntry, ...], check):
    # MPF parsing above imposes the frame/table bound before this Pillow open.
    try:
        from PIL import Image, ImageOps
    except Exception:
        raise MpoImageInputUnavailable() from None
    try:
        with base._bounded_pillow_profile(Image):
            with Image.open(io.BytesIO(raw)) as opened:
                if opened.format != "MPO" or opened.n_frames < 2 or opened.n_frames > MAX_MPO_FRAMES:
                    raise MpoImageInputUnavailable()
                width, height = opened.size
                if (not 0 < width <= base.MAX_IMAGE_SIDE
                        or not 0 < height <= base.MAX_IMAGE_SIDE
                        or width * height > base.MAX_IMAGE_PIXELS):
                    raise MpoImageInputUnavailable()
                opened.verify()
            base._check(check)
            with Image.open(io.BytesIO(raw)) as opened:
                if opened.format != "MPO" or opened.n_frames != len(entries) or opened.tell() != 0:
                    raise MpoImageInputUnavailable()
                width, height = opened.size
                orientation = int(opened.getexif().get(274, 1))
                if (not 0 < width <= base.MAX_IMAGE_SIDE
                        or not 0 < height <= base.MAX_IMAGE_SIDE
                        or width * height > base.MAX_IMAGE_PIXELS
                        or orientation not in range(1, 9)):
                    raise MpoImageInputUnavailable()
                opened.draft("RGB", (base.MAX_PREPARED_SIDE, base.MAX_PREPARED_SIDE))
                oriented = ImageOps.exif_transpose(opened)
                try:
                    rgb = oriented.convert("RGB")
                finally:
                    oriented.close()
                try:
                    rgb.thumbnail((base.MAX_PREPARED_SIDE, base.MAX_PREPARED_SIDE),
                                  Image.Resampling.LANCZOS, reducing_gap=3.0)
                    rgb.info.clear()
                    base._check(check)
                    output = io.BytesIO()
                    rgb.save(output, format="PNG", optimize=False)
                    encoded = output.getvalue()
                    if (not encoded or len(encoded) > base.MAX_DERIVED_BYTES
                            or len(raw) + len(encoded) > base.MAX_COMBINED_BYTES):
                        raise MpoImageInputUnavailable()
                    return width, height, orientation, rgb.width, rgb.height, encoded
                finally:
                    rgb.close()
    except MpoImageInputUnavailable:
        raise
    except Exception:
        raise MpoImageInputUnavailable() from None


def prepare_mpo_image(source_path, expected_sha256, original_roots, private_scratch, *, check=lambda: None):
    """Copy, validate and canonicalize only an MPO's primary frame.

    Call from a private, single-process, resource-capped worker. MPF metadata
    and every frame range are bounded before Pillow opens the source. Auxiliary
    images are never selected, sought or decoded.
    """
    if type(expected_sha256) is not str or not _SHA256.fullmatch(expected_sha256):
        raise MpoImageInputUnavailable()
    try:
        source = base._approved_source(source_path, original_roots)
        roots = tuple(base._canonical_path(root, directory=True) for root in original_roots)
        scratch = base._private_scratch(private_scratch, roots)
    except Exception:
        raise MpoImageInputUnavailable() from None
    token = secrets.token_hex(16)
    private_copy = scratch / f"library-mpo-input-{token}.original"
    derived = scratch / f"library-mpo-input-{token}.derived.png"
    try:
        source_sha, original_bytes, source_identity = base._copy_original(
            source, private_copy, expected_sha256, check,
        )
        source_stat_identity = base._stat_receipt(source.lstat())
        raw = private_copy.read_bytes()
        if not raw or len(raw) > base.MAX_ORIGINAL_BYTES:
            raise MpoImageInputUnavailable()
        entries = _parse_mpf(raw, check)
        width, height, orientation, prepared_width, prepared_height, encoded = _decode_primary(raw, entries, check)
        if len(entries) < 2 or original_bytes + len(encoded) > base.MAX_COMBINED_BYTES:
            raise MpoImageInputUnavailable()
        with base._new_private_file(derived) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        base._require_private_file(derived)
        base._verify_source_unchanged(source, source_identity, source_sha, check)
        derived_sha = hashlib.sha256(encoded).hexdigest()
        if (hashlib.sha256(private_copy.read_bytes()).hexdigest() != source_sha
                or hashlib.sha256(derived.read_bytes()).hexdigest() != derived_sha):
            raise MpoImageInputUnavailable()
        base._check(check)
        result = MpoPreparedImage(
            source_sha, derived_sha, source, source_stat_identity,
            private_copy, derived, original_bytes, "MPO", len(entries), width, height,
            orientation, prepared_width, prepared_height, RECIPE_SHA256,
            copy.deepcopy(PROFILE_RECIPE),
        )
        with _LOCK:
            _OWNED[id(result)] = (str(scratch), str(private_copy), source_sha, str(derived), derived_sha)
        return result
    except MpoImageInputUnavailable:
        raise
    except Exception:
        raise MpoImageInputUnavailable() from None


def cleanup_mpo_prepared(prepared: MpoPreparedImage, private_scratch) -> None:
    """Remove only verified private files owned by this process after success."""
    if type(prepared) is not MpoPreparedImage:
        raise MpoImageInputUnavailable()
    with _LOCK:
        ownership = _OWNED.get(id(prepared))
    if ownership is None:
        raise MpoImageInputUnavailable()
    try:
        scratch = base._canonical_path(private_scratch, directory=True)
        from app.access.private_storage import require_private_directory
        require_private_directory(scratch)
        expected_scratch, original_path, original_sha, derived_path, derived_sha = ownership
        if (str(scratch) != expected_scratch
                or str(prepared.private_original_copy) != original_path
                or str(prepared.derived_path) != derived_path):
            raise MpoImageInputUnavailable()
        original_name = _OWNED_NAME.fullmatch(Path(original_path).name)
        derived_name = _OWNED_NAME.fullmatch(Path(derived_path).name)
        if (original_name is None or derived_name is None
                or original_name.group(1) != derived_name.group(1)
                or original_name.group(2) != "original"
                or derived_name.group(2) != "derived.png"):
            raise MpoImageInputUnavailable()
        source = base._canonical_path(prepared.original_path, directory=False)
        if source in (scratch, Path(original_path), Path(derived_path)):
            raise MpoImageInputUnavailable()
        original, derivative = Path(original_path), Path(derived_path)
        for path, expected in ((original, original_sha), (derivative, derived_sha)):
            base._require_private_file(path)
            if (path.parent != scratch or path.stat().st_nlink != 1
                    or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
                raise MpoImageInputUnavailable()
        source_stat = source.stat()
        for path in (original, derivative):
            file_stat = path.stat()
            if (file_stat.st_dev, file_stat.st_ino) == (source_stat.st_dev, source_stat.st_ino):
                raise MpoImageInputUnavailable()
        original.unlink()
        derivative.unlink()
        with _LOCK:
            del _OWNED[id(prepared)]
    except MpoImageInputUnavailable:
        raise
    except Exception:
        raise MpoImageInputUnavailable() from None

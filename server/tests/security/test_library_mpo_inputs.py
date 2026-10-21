"""Generated fixtures for the standalone, primary-only MPO input profile."""
import hashlib
import io
from pathlib import Path
import struct
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
import library_mpo_inputs as mpo


def private_directory(path):
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)
    return path


def fixture_paths(tmp_path):
    root = private_directory(tmp_path / "originals")
    scratch = private_directory(tmp_path / "scratch")
    return root, scratch, root / "synthetic.mpo"


def mpo_bytes(*, primary="red", auxiliary="blue", size=(48, 32), exif=None):
    from PIL import Image

    primary_image = Image.new("RGB", size, primary)
    auxiliary_image = Image.new("RGB", (20, 12), auxiliary)
    buffer = io.BytesIO()
    kwargs = {"quality": 90}
    if exif is not None:
        kwargs["exif"] = exif
    primary_image.save(buffer, format="MPO", save_all=True,
                       append_images=[auxiliary_image], **kwargs)
    primary_image.close()
    auxiliary_image.close()
    return buffer.getvalue()


def _tag(raw, wanted_tag):
    tiff_start, _ = mpo._mpf_segment(raw, lambda: None)
    endian = "<" if raw[tiff_start:tiff_start + 2] == b"II" else ">"
    ifd = tiff_start + struct.unpack_from(endian + "I", raw, tiff_start + 4)[0]
    count = struct.unpack_from(endian + "H", raw, ifd)[0]
    for index in range(count):
        position = ifd + 2 + index * 12
        if struct.unpack_from(endian + "H", raw, position)[0] == wanted_tag:
            return tiff_start, endian, position
    raise AssertionError(f"missing MPF tag {wanted_tag:#x}")


def _mp_entry_field(raw, index, field_offset):
    tiff_start, endian, tag_position = _tag(raw, 0xB002)
    table_relative = struct.unpack_from(endian + "I", raw, tag_position + 8)[0]
    return tiff_start + table_relative + index * 16 + field_offset


def _prepare(raw, source, root, scratch):
    source.write_bytes(raw)
    return mpo.prepare_mpo_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)


def test_primary_only_profile_prepares_frame_zero_and_cleans_only_owned_files(tmp_path, monkeypatch):
    from PIL.MpoImagePlugin import MpoImageFile
    from PIL import Image

    raw = mpo_bytes()
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(raw)
    original_stat = source.stat()
    original_seek = MpoImageFile.seek

    def forbid_auxiliary_seek(image, frame):
        if frame != 0:
            raise AssertionError("auxiliary image must not be sought")
        return original_seek(image, frame)

    monkeypatch.setattr(MpoImageFile, "seek", forbid_auxiliary_seek)
    prepared = mpo.prepare_mpo_image(
        source, hashlib.sha256(raw).hexdigest(), [root], scratch,
    )

    assert prepared.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert prepared.original_stat_identity["size"] == len(raw)
    assert prepared.observed_format == "MPO"
    assert prepared.frame_count == 2
    assert (prepared.observed_width, prepared.observed_height) == (48, 32)
    assert prepared.recipe_sha256 == mpo.RECIPE_SHA256
    assert prepared.recipe["candidate_policy"] == "frame_zero_baseline_mp_primary_only"
    assert prepared.recipe["base_recipe_sha256"] == mpo.base.RECIPE_SHA256
    assert prepared.recipe_sha256 != mpo.base.RECIPE_SHA256
    assert source.read_bytes() == raw
    assert source.stat().st_mtime_ns == original_stat.st_mtime_ns
    with Image.open(prepared.derived_path) as image:
        assert image.format == "PNG" and image.mode == "RGB"
        assert image.getexif() == {}
        assert image.size == (48, 32)
        red, green, blue = image.convert("RGB").resize((1, 1)).getpixel((0, 0))
        assert red > 200 and blue < 50 and green < 50
    original_copy = prepared.private_original_copy
    derivative = prepared.derived_path
    mpo.cleanup_mpo_prepared(prepared, scratch)
    assert not original_copy.exists() and not derivative.exists()
    assert source.read_bytes() == raw


def test_primary_exif_orientation_is_applied_and_metadata_is_stripped(tmp_path):
    from PIL import Image

    exif = Image.Exif()
    exif[274] = 6
    root, scratch, source = fixture_paths(tmp_path)
    prepared = _prepare(mpo_bytes(size=(64, 32), exif=exif), source, root, scratch)
    assert prepared.orientation == 6
    assert (prepared.prepared_width, prepared.prepared_height) == (32, 64)
    with Image.open(prepared.derived_path) as output:
        assert output.size == (32, 64)
        assert output.getexif() == {}
        assert "exif" not in output.info and "mp" not in output.info
    mpo.cleanup_mpo_prepared(prepared, scratch)


def _mutate(raw, mutate):
    data = bytearray(raw)
    mutate(data)
    return bytes(data)


@pytest.mark.parametrize("declared_frames", [1, mpo.MAX_MPO_FRAMES + 1])
def test_invalid_declared_frame_count_is_rejected_before_pillow_open(tmp_path, monkeypatch, declared_frames):
    from PIL import Image

    raw = mpo_bytes()
    _, endian, position = _tag(raw, 0xB001)
    malformed = _mutate(raw, lambda data: struct.pack_into(
        endian + "I", data, position + 8, declared_frames,
    ))
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(malformed)

    def pillow_must_not_open(*_args, **_kwargs):
        raise AssertionError("Pillow opened before bounded MPF preflight")

    monkeypatch.setattr(Image, "open", pillow_must_not_open)
    with pytest.raises(mpo.MpoImageInputUnavailable):
        mpo.prepare_mpo_image(source, hashlib.sha256(malformed).hexdigest(), [root], scratch)
    assert len(list(scratch.glob("*.original"))) == 1
    assert not list(scratch.glob("*.derived.png"))
    assert source.read_bytes() == malformed


@pytest.mark.parametrize("mutator", [
    "bad_ifd",
    "entry_table_count",
    "entry_table_offset",
    "non_primary_first_entry",
    "overlapping_auxiliary",
    "out_of_bounds_auxiliary",
    "truncated_auxiliary",
    "bad_mpf_app2_length",
])
def test_bad_or_truncated_mpf_refuses_and_retains_only_original_copy(tmp_path, mutator):
    raw = mpo_bytes()
    data = bytearray(raw)
    tiff_start, _ = mpo._mpf_segment(raw, lambda: None)
    if mutator == "bad_ifd":
        data[tiff_start + 4:tiff_start + 8] = b"\xff\xff\xff\xff"
    elif mutator == "entry_table_count":
        _, endian, position = _tag(raw, 0xB002)
        struct.pack_into(endian + "I", data, position + 4, 31)
    elif mutator == "entry_table_offset":
        _, endian, position = _tag(raw, 0xB002)
        struct.pack_into(endian + "I", data, position + 8, 0xFFFFFFF0)
    elif mutator == "non_primary_first_entry":
        position = _mp_entry_field(raw, 0, 0)
        struct.pack_into("<I", data, position, 0)
    elif mutator == "overlapping_auxiliary":
        position = _mp_entry_field(raw, 1, 8)
        struct.pack_into("<I", data, position, 0)
    elif mutator == "out_of_bounds_auxiliary":
        position = _mp_entry_field(raw, 1, 4)
        struct.pack_into("<I", data, position, len(raw) * 2)
    elif mutator == "truncated_auxiliary":
        data = data[:-1]
    else:
        # The JPEG APP2 segment length begins immediately before its payload.
        mpf = raw.index(b"MPF\x00")
        data[mpf - 2:mpf] = b"\xff\xff"
    malformed = bytes(data)
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(malformed)

    with pytest.raises(mpo.MpoImageInputUnavailable):
        mpo.prepare_mpo_image(source, hashlib.sha256(malformed).hexdigest(), [root], scratch)
    copies = list(scratch.glob("*.original"))
    assert len(copies) == 1 and copies[0].read_bytes() == malformed
    assert not list(scratch.glob("*.derived.png"))
    assert source.read_bytes() == malformed


def test_unsupported_picture_format_refuses(tmp_path):
    raw = mpo_bytes()
    data = bytearray(raw)
    position = _mp_entry_field(raw, 0, 0)
    attribute = struct.unpack_from("<I", raw, position)[0]
    struct.pack_into("<I", data, position, attribute | (1 << 24))
    malformed = bytes(data)
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(malformed)
    with pytest.raises(mpo.MpoImageInputUnavailable):
        mpo.prepare_mpo_image(source, hashlib.sha256(malformed).hexdigest(), [root], scratch)


def test_overlapping_ranges_refuse_before_any_jpeg_framing_scan(tmp_path, monkeypatch):
    raw = mpo_bytes()
    position = _mp_entry_field(raw, 1, 8)
    malformed = _mutate(raw, lambda data: struct.pack_into("<I", data, position, 0))
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(malformed)

    def framing_scan_must_not_run(*_args, **_kwargs):
        pytest.fail("JPEG framing scan ran before overlap rejection")

    monkeypatch.setattr(mpo, "_jpeg_has_exact_eoi", framing_scan_must_not_run)
    with pytest.raises(mpo.MpoImageInputUnavailable):
        mpo.prepare_mpo_image(source, hashlib.sha256(malformed).hexdigest(), [root], scratch)
    assert len(list(scratch.glob("*.original"))) == 1
    assert not list(scratch.glob("*.derived.png"))


def _mutate_primary_dimensions(raw, *, width, height):
    data = bytearray(raw)
    position = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                   0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while position < len(data):
        assert data[position] == 0xFF
        while data[position] == 0xFF:
            position += 1
        marker = data[position]
        position += 1
        if marker == 0xDA:
            break
        length = struct.unpack_from(">H", data, position)[0]
        if marker in sof_markers:
            struct.pack_into(">HH", data, position + 3, height, width)
            return bytes(data)
        position += length
    raise AssertionError("synthetic primary JPEG has no SOF marker")


@pytest.mark.parametrize("case", ["invalid_orientation", "oversized_primary"])
def test_invalid_primary_metadata_refuses_before_pixel_decode(tmp_path, monkeypatch, case):
    from PIL import Image, ImageFile

    if case == "invalid_orientation":
        exif = Image.Exif()
        exif[274] = 9
        raw = mpo_bytes(exif=exif)
    else:
        raw = _mutate_primary_dimensions(
            mpo_bytes(), width=mpo.base.MAX_IMAGE_SIDE + 1, height=32,
        )
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(raw)
    original_load = ImageFile.ImageFile.load
    calls = []

    def pixel_decode_must_not_run(image, *args, **kwargs):
        calls.append(image)
        raise AssertionError("invalid primary metadata reached pixel decode")

    monkeypatch.setattr(ImageFile.ImageFile, "load", pixel_decode_must_not_run)
    with pytest.raises(mpo.MpoImageInputUnavailable):
        mpo.prepare_mpo_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)
    assert calls == []
    assert len(list(scratch.glob("*.original"))) == 1
    assert not list(scratch.glob("*.derived.png"))
    monkeypatch.setattr(ImageFile.ImageFile, "load", original_load)


def test_cleanup_refuses_modified_private_copy_without_deleting_either_file(tmp_path):
    raw = mpo_bytes()
    root, scratch, source = fixture_paths(tmp_path)
    prepared = _prepare(raw, source, root, scratch)
    source_stat = source.stat()
    private_copy = prepared.private_original_copy
    derivative = prepared.derived_path
    private_copy.write_bytes(b"tampered private copy")
    derivative_before = derivative.read_bytes()

    with pytest.raises(mpo.MpoImageInputUnavailable):
        mpo.cleanup_mpo_prepared(prepared, scratch)
    assert private_copy.exists() and private_copy.read_bytes() == b"tampered private copy"
    assert derivative.exists() and derivative.read_bytes() == derivative_before
    assert source.read_bytes() == raw
    assert hashlib.sha256(source.read_bytes()).hexdigest() == prepared.source_sha256
    assert prepared.original_stat_identity["size"] == source.stat().st_size
    assert source.stat().st_mtime_ns == source_stat.st_mtime_ns


def _add_malformed_nested_mpf_to_auxiliary(raw):
    entries = mpo._parse_mpf(raw)
    nested_payload = b"MPF\x00" + b"not-a-tiff-index"
    nested_segment = b"\xff\xe2" + struct.pack(">H", len(nested_payload) + 2) + nested_payload
    data = bytearray(raw[:entries[1].start + 2] + nested_segment + raw[entries[1].start + 2:])
    size_position = _mp_entry_field(raw, 1, 4)
    struct.pack_into("<I", data, size_position, entries[1].size + len(nested_segment))
    return bytes(data)


def test_auxiliary_nested_mpf_marker_is_opaque_and_never_decoded(tmp_path, monkeypatch):
    from PIL.MpoImagePlugin import MpoImageFile

    raw = _add_malformed_nested_mpf_to_auxiliary(mpo_bytes())
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(raw)
    original_seek = MpoImageFile.seek

    def forbid_auxiliary_seek(image, frame):
        if frame != 0:
            raise AssertionError("auxiliary frame was traversed")
        return original_seek(image, frame)

    monkeypatch.setattr(MpoImageFile, "seek", forbid_auxiliary_seek)
    prepared = mpo.prepare_mpo_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)
    assert prepared.frame_count == 2
    mpo.cleanup_mpo_prepared(prepared, scratch)

"""Generated fixtures for the private library image derivation boundary."""
import hashlib
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
import library_image_inputs as inputs


def private_scratch(path):
    path.mkdir(mode=0o700, parents=True)
    path.chmod(0o700)
    return path


def image_bytes(*, fmt="PNG", size=(64, 48), exif=None, icc=None, png_text=None):
    from PIL import Image, PngImagePlugin
    image = Image.new("RGB", size, (34, 123, 210))
    kwargs = {}
    if fmt == "JPEG":
        if exif is not None:
            kwargs["exif"] = exif
        if icc is not None:
            kwargs["icc_profile"] = icc
    elif png_text is not None:
        info = PngImagePlugin.PngInfo()
        info.add_text("private-note", png_text)
        kwargs["pnginfo"] = info
    import io
    stream = io.BytesIO()
    image.save(stream, format=fmt, **kwargs)
    image.close()
    return stream.getvalue()


def fixture_paths(tmp_path):
    original_root = tmp_path / "originals"
    original_root.mkdir(mode=0o700)
    scratch = private_scratch(tmp_path / "scratch")
    source = original_root / "photo.bin"
    return original_root, scratch, source


def prepare(source, root, scratch, raw=None):
    if raw is not None:
        source.write_bytes(raw)
    content = source.read_bytes()
    return inputs.prepare_image(source, hashlib.sha256(content).hexdigest(), [root], scratch)


def test_jpeg_exif_orientation_is_normalized_and_metadata_is_removed(tmp_path):
    from PIL import Image
    exif = Image.Exif()
    exif[274] = 6
    raw = image_bytes(fmt="JPEG", size=(4096, 1200), exif=exif, icc=b"private icc profile")
    root, scratch, source = fixture_paths(tmp_path)
    prepared = prepare(source, root, scratch, raw)

    assert prepared.source_sha256 == hashlib.sha256(raw).hexdigest()
    assert prepared.derived_sha256 == hashlib.sha256(prepared.derived_path.read_bytes()).hexdigest()
    assert prepared.observed_format == "JPEG"
    assert (prepared.observed_width, prepared.observed_height, prepared.orientation) == (4096, 1200, 6)
    assert (prepared.prepared_width, prepared.prepared_height) == (600, 2048)
    assert prepared.original_stat_identity["nlink"] == 1
    assert prepared.original_stat_identity["size"] == len(raw)
    assert prepared.private_original_copy.read_bytes() == raw
    assert source.read_bytes() == raw
    assert prepared.recipe_sha256 == inputs.RECIPE_SHA256
    assert prepared.recipe["orientation"] == "exif_transpose_then_discard_metadata"
    from PIL import Image as PillowImage
    with PillowImage.open(prepared.derived_path) as output:
        assert output.format == "PNG" and output.mode == "RGB"
        assert output.getexif() == {}
        assert "icc_profile" not in output.info
        assert output.size == (600, 2048)


def test_png_is_canonical_rgb_and_private_text_metadata_is_stripped(tmp_path):
    raw = image_bytes(png_text="do not carry this metadata")
    root, scratch, source = fixture_paths(tmp_path)
    prepared = prepare(source, root, scratch, raw)
    from PIL import Image
    with Image.open(prepared.derived_path) as output:
        assert output.format == "PNG" and output.mode == "RGB"
        assert "private-note" not in output.info
        assert output.size == (64, 48)


def test_prepared_recipe_nested_values_do_not_mutate_module_constants(tmp_path):
    raw = image_bytes(size=(24, 16))
    root, scratch, source = fixture_paths(tmp_path)
    prepared = prepare(source, root, scratch, raw)
    prepared.recipe["resize"]["resample"] = "caller-change"
    assert prepared.recipe["resize"]["resample"] == "caller-change"
    assert inputs.PROFILE_RECIPE["resize"]["resample"] == "LANCZOS"


def test_single_frame_policy_rejects_animated_png(tmp_path):
    from PIL import Image
    import io
    first = Image.new("RGB", (8, 8), "red")
    second = Image.new("RGB", (8, 8), "blue")
    buffer = io.BytesIO()
    first.save(buffer, format="PNG", save_all=True, append_images=[second], duration=50, loop=0)
    first.close()
    second.close()
    raw = buffer.getvalue()
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(raw)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)


def test_hardlinked_original_is_accepted_and_copy_is_not_linked(tmp_path):
    raw = image_bytes()
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(raw)
    hardlink = root / "hardlinked-photo.jpg"
    os.link(source, hardlink)
    prepared = inputs.prepare_image(hardlink, hashlib.sha256(raw).hexdigest(), [root], scratch)
    assert prepared.original_path == hardlink
    assert prepared.private_original_copy.read_bytes() == raw
    assert prepared.private_original_copy.stat().st_ino != hardlink.stat().st_ino


@pytest.mark.parametrize("raw", [b"not an image", b"\x89PNG\r\n\x1a\ntruncated"])
def test_malformed_inputs_refuse_and_leave_failed_private_copy_evidence(tmp_path, raw):
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(raw)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)
    copies = list(scratch.glob("*.original"))
    assert len(copies) == 1 and copies[0].read_bytes() == raw


def test_oversize_original_is_bounded_during_copy(tmp_path, monkeypatch):
    root, scratch, source = fixture_paths(tmp_path)
    source.write_bytes(b"x" * 1025)
    monkeypatch.setattr(inputs, "MAX_ORIGINAL_BYTES", 1024)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(source.read_bytes()).hexdigest(), [root], scratch)
    assert len(list(scratch.glob("*.original"))) == 1
    assert all(path.stat().st_size <= 1025 for path in scratch.iterdir())


def test_wrong_source_hash_refuses_without_touching_source(tmp_path):
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes()
    source.write_bytes(raw)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, "0" * 64, [root], scratch)
    assert source.read_bytes() == raw
    assert len(list(scratch.glob("*.original"))) == 1


def test_source_change_during_preparation_is_detected_after_decode(tmp_path, monkeypatch):
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes()
    source.write_bytes(raw)
    encoded = image_bytes(size=(8, 8))

    def mutate_source(_private_copy, _check):
        source.write_bytes(b"changed after copy")
        return "PNG", 64, 48, 1, 8, 8, encoded

    monkeypatch.setattr(inputs, "_decode_and_encode", mutate_source)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)
    assert source.read_bytes() == b"changed after copy"
    assert len(list(scratch.glob("*.original"))) == 1


def test_source_outside_approved_roots_and_symlink_are_refused(tmp_path):
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes()
    source.write_bytes(raw)
    outside = tmp_path / "outside.png"
    outside.write_bytes(raw)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(outside, hashlib.sha256(raw).hexdigest(), [root], scratch)
    alias = root / "alias.png"
    alias.symlink_to(source)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(alias, hashlib.sha256(raw).hexdigest(), [root], scratch)


def test_invalid_header_dimensions_refuse_before_pixel_decode_and_restore_pillow_limit(tmp_path, monkeypatch):
    from PIL import Image
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes(size=(40, 40))
    source.write_bytes(raw)
    previous_limit = Image.MAX_IMAGE_PIXELS
    monkeypatch.setattr(inputs, "MAX_IMAGE_PIXELS", 1000)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)
    assert Image.MAX_IMAGE_PIXELS == previous_limit


def test_side_limit_refuses_header_without_large_allocation_and_restores_on_decode_error(tmp_path, monkeypatch):
    from PIL import Image
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes(size=(300, 20))
    source.write_bytes(raw)
    previous_limit = Image.MAX_IMAGE_PIXELS
    monkeypatch.setattr(inputs, "MAX_IMAGE_SIDE", 200)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)
    assert Image.MAX_IMAGE_PIXELS == previous_limit


def test_derived_byte_and_total_budget_are_enforced(tmp_path, monkeypatch):
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes(size=(80, 80))
    source.write_bytes(raw)
    monkeypatch.setattr(inputs, "MAX_DERIVED_BYTES", 1)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)
    assert not list(scratch.glob("*.derived.png"))


def test_combined_original_and_derived_budget_is_enforced(tmp_path, monkeypatch):
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes(size=(80, 80))
    source.write_bytes(raw)
    monkeypatch.setattr(inputs, "MAX_COMBINED_BYTES", len(raw) + 1)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)
    assert not list(scratch.glob("*.derived.png"))


def test_200mp_header_uses_bounded_header_path_without_allocating_pixels(tmp_path, monkeypatch):
    from PIL import Image, ImageOps
    root, scratch, source = fixture_paths(tmp_path)
    raw = b"private-source-placeholder"
    source.write_bytes(raw)

    class HeaderOnlyImage:
        format = "PNG"
        size = (15_000, 13_334)  # 200,010,000 pixels; no raster is constructed.
        n_frames = 1

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def verify(self):
            return None

        def getexif(self):
            return {}

    opens = []
    monkeypatch.setattr(Image, "open", lambda *_args, **_kwargs: (opens.append(True), HeaderOnlyImage())[1])
    called = []

    def stop_before_raster(_image):
        called.append(True)
        raise RuntimeError("header accepted; do not allocate test raster")

    monkeypatch.setattr(ImageOps, "exif_transpose", stop_before_raster)
    previous_limit = Image.MAX_IMAGE_PIXELS
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)
    assert len(opens) == 2 and called
    assert Image.MAX_IMAGE_PIXELS == previous_limit


def test_overprofile_header_is_rejected_before_pillow_verify(tmp_path, monkeypatch):
    from PIL import Image
    root, scratch, source = fixture_paths(tmp_path)
    raw = b"private-source-placeholder"
    source.write_bytes(raw)

    class OverprofileHeader:
        format = "PNG"
        size = (inputs.MAX_IMAGE_SIDE + 1, 1)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def verify(self):
            raise AssertionError("out-of-profile header must be rejected before verify")

    monkeypatch.setattr(Image, "open", lambda *_args, **_kwargs: OverprofileHeader())
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)


def test_check_failure_retains_private_work_without_mutating_original(tmp_path):
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes()
    source.write_bytes(raw)

    def stop():
        raise RuntimeError("deadline")

    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch, check=stop)
    assert source.read_bytes() == raw
    assert len(list(scratch.glob("*.original"))) == 1


def test_cleanup_removes_only_owned_private_outputs_and_never_original(tmp_path):
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes()
    prepared = prepare(source, root, scratch, raw)
    original_copy, derivative = prepared.private_original_copy, prepared.derived_path
    inputs.cleanup_prepared(prepared, scratch)
    assert source.read_bytes() == raw
    assert not original_copy.exists() and not derivative.exists()


def test_cleanup_rejects_modified_or_unowned_output_without_deleting_anything(tmp_path):
    root, scratch, source = fixture_paths(tmp_path)
    prepared = prepare(source, root, scratch, image_bytes())
    prepared.derived_path.write_bytes(b"changed")
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.cleanup_prepared(prepared, scratch)
    assert source.exists() and prepared.private_original_copy.exists()
    assert prepared.derived_path.exists()


def test_scratch_must_be_private_and_separate_from_source_tree(tmp_path):
    root, scratch, source = fixture_paths(tmp_path)
    raw = image_bytes()
    source.write_bytes(raw)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], root)
    scratch.chmod(0o755)
    with pytest.raises(inputs.ImageInputUnavailable):
        inputs.prepare_image(source, hashlib.sha256(raw).hexdigest(), [root], scratch)

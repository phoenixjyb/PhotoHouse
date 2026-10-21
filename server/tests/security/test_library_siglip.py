"""Security and batching contract for the private library SigLIP2 wrapper."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path
import sys

import pytest
from PIL import Image, PngImagePlugin

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

import library_siglip as library  # noqa: E402
from app.access.semantic_encoder import JointSpaceBinding, SemanticUnavailable, TextVector  # noqa: E402
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum  # noqa: E402


class FakeTensor:
    def __init__(self, values, shape=None):
        self.values = values
        self.shape = shape or (len(values), len(values[0]) if values else 0)

    def detach(self):
        return self

    def to(self, *_args, **_kwargs):
        return self

    def __getitem__(self, index):
        return FakeTensor([self.values[index]], (1, len(self.values[index])))

    def tolist(self):
        return self.values[0]


class FakeTorch:
    float32 = "float32"

    class inference_mode:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False


class FakeModel:
    def __init__(self):
        self.calls = 0

    def get_image_features(self, *, pixel_values):
        self.calls += 1
        return FakeTensor([[float(index + 1)] + [0.0] * 767 for index in range(8)], (8, 768))


class FakeProcessor:
    def __init__(self):
        self.calls = []

    def __call__(self, *, images, return_tensors):
        self.calls.append((tuple(images), return_tensors))
        return {"pixel_values": FakeTensor([], (8, 3, 256, 256))}


class FakeInner:
    def __init__(self):
        self.image_identity = VectorSpaceIdentity("a" * 64, "b" * 64,
            library.SPACE, library.MODEL_VERSION, 768, "unit_l2")
        self.text_identity = VectorSpaceIdentity("a" * 64, "c" * 64,
            library.SPACE, library.MODEL_VERSION, 768, "unit_l2")
        self._lock = __import__("threading").Lock()
        self._binding = None
        self._pins = ()
        self._packages = {}
        self.processor = FakeProcessor()
        self.model = FakeModel()
        self._handle = {"torch": FakeTorch, "processor": self.processor, "model": self.model}

    def verify(self):
        return None

    def _check(self, check):
        check()

    def receipt(self):
        return {"schema": "base-receipt"}

    def bind(self, binding):
        self._binding = binding
        return self

    def encode(self, query, *, check=lambda: None):
        check()
        vector = (1.0,) + (0.0,) * 767
        return TextVector(self._binding.binding_sha256,
            hashlib.sha256(query.encode("utf-8")).hexdigest(), vector,
            canonical_vector_checksum(vector))


def _private_png(directory, color=(17, 0, 0), *, metadata=False, mode="RGB", fmt="PNG"):
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"{len(list(directory.iterdir())):02d}.{fmt.lower()}"
    image = Image.new(mode, (3, 2), color)
    if metadata:
        info = PngImagePlugin.PngInfo()
        info.add_text("private", "must reject metadata")
        image.save(path, format=fmt, pnginfo=info)
    else:
        image.save(path, format=fmt)
    path.chmod(0o600)
    return path, hashlib.sha256(path.read_bytes()).hexdigest()


def _wrapper(monkeypatch):
    inner = FakeInner()
    monkeypatch.setattr(library.SiglipModel, "load", lambda **_kwargs: inner)
    wrapper = library.LibrarySiglipModel.load(model_directory="unused", artifacts={},
        package_versions={}, preparation_source_sha256=library._source_pin(
            Path(library.preparation.__file__).resolve()).sha256)
    return wrapper, inner


def test_fixed_eight_batch_tail_padding_and_drops_padding_outputs(monkeypatch, tmp_path):
    wrapper, inner = _wrapper(monkeypatch)
    entries = [_private_png(tmp_path, (index, 0, 0)) for index in range(1, 4)]
    vectors = wrapper.encode_prepared_batch(entries)
    assert len(inner.processor.calls) == 1
    images, tensor_kind = inner.processor.calls[0]
    assert tensor_kind == "pt" and len(images) == 8
    assert images[3] is images[4] is images[5] is images[6] is images[7]
    assert images[0] is not images[1] and images[1] is not images[2]
    assert inner.model.calls == 1
    assert len(vectors) == 3
    assert vectors == ((1.0,) + (0.0,) * 767,
        (1.0,) + (0.0,) * 767, (1.0,) + (0.0,) * 767)


@pytest.mark.parametrize("case", ["metadata", "rgba", "animated"])
def test_prepared_png_requires_metadata_free_single_frame_rgb(monkeypatch, tmp_path, case):
    wrapper, _inner = _wrapper(monkeypatch)
    if case == "metadata":
        path, digest = _private_png(tmp_path, metadata=True)
    elif case == "rgba":
        path, digest = _private_png(tmp_path, mode="RGBA", color=(1, 2, 3, 4))
    else:
        path = tmp_path / "animated.gif"
        first = Image.new("RGB", (2, 2), (1, 2, 3))
        second = Image.new("RGB", (2, 2), (4, 5, 6))
        first.save(path, format="GIF", save_all=True, append_images=[second])
        path.chmod(0o600)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(SemanticUnavailable):
        wrapper.encode_prepared_batch([(path, digest)])


def test_batch_refuses_bad_hash_shape_limits_and_invalid_batch(monkeypatch, tmp_path):
    wrapper, inner = _wrapper(monkeypatch)
    path, digest = _private_png(tmp_path)
    with pytest.raises(SemanticUnavailable):
        wrapper.encode_prepared_batch([(path, "0" * 64)])
    with pytest.raises(SemanticUnavailable):
        wrapper.encode_prepared_batch([])
    with pytest.raises(SemanticUnavailable):
        wrapper.encode_prepared_batch([(path, digest)] * 9)
    inner.model.get_image_features = lambda **_kwargs: FakeTensor([[1.0] * 768], (1, 768))
    with pytest.raises(SemanticUnavailable):
        wrapper.encode_prepared_batch([(path, digest)])


def test_prepared_file_size_is_checked_before_generic_hash(monkeypatch, tmp_path):
    wrapper, inner = _wrapper(monkeypatch)
    path = tmp_path / "oversized.png"
    with path.open("wb") as stream:
        stream.truncate(library.PREPARED_MAX_BYTES + 1)
    path.chmod(0o600)
    called = []

    def forbidden_hash(*_args, **_kwargs):
        called.append(True)
        raise AssertionError("oversized input must be rejected before hashing")

    monkeypatch.setattr(library.receipts, "inspect_checkpoint", forbidden_hash)
    with pytest.raises(SemanticUnavailable):
        wrapper.encode_prepared_batch([(path, "a" * 64)])
    assert not called and inner.model.calls == 0


def test_aggregate_prepared_batch_byte_cap_is_enforced_before_decode(monkeypatch, tmp_path):
    from types import SimpleNamespace
    wrapper, inner = _wrapper(monkeypatch)
    monkeypatch.setattr(library, "PREPARED_MAX_BYTES", 32 * 1024**2)
    size = 30 * 1024**2
    monkeypatch.setattr(library, "_prepared_file", lambda path, _sha: SimpleNamespace(
        path=str(path), stat_identity=(1, 2, 0, size, 3, 4, 1)))
    entries = [(tmp_path / f"{index}.png", "b" * 64) for index in range(5)]
    with pytest.raises(SemanticUnavailable):
        wrapper.encode_prepared_batch(entries)
    assert inner.model.calls == 0


def test_pins_are_reverified_after_decode_before_inference(monkeypatch, tmp_path):
    wrapper, inner = _wrapper(monkeypatch)
    path, digest = _private_png(tmp_path)
    decode = library._decode_prepared

    def mutate_after_decode(pin, ImageModule):
        image = decode(pin, ImageModule)
        path.write_bytes(b"changed after initial hash")
        return image

    monkeypatch.setattr(library, "_decode_prepared", mutate_after_decode)
    with pytest.raises(SemanticUnavailable):
        wrapper.encode_prepared_batch([(path, digest)])
    assert inner.model.calls == 0


def test_source_change_after_load_withholds_vectors(monkeypatch, tmp_path):
    wrapper, inner = _wrapper(monkeypatch)
    path, digest = _private_png(tmp_path)
    real_current = library._current

    def changing_source(pin):
        if (pin.path == str(Path(library.preparation.__file__).resolve())
                and inner.model.calls > 0):
            raise SemanticUnavailable()
        return real_current(pin)

    monkeypatch.setattr(library, "_current", changing_source)
    with pytest.raises(SemanticUnavailable):
        wrapper.encode_prepared_batch([(path, digest)])


def test_lock_excludes_base_text_encode_and_outer_text_binding_is_rewrapped(monkeypatch):
    wrapper, inner = _wrapper(monkeypatch)
    original_text_identity = inner.text_identity
    binding = JointSpaceBinding(wrapper.image_identity, wrapper.text_identity, "d" * 64)
    wrapper.bind(binding)
    assert inner.text_identity == original_text_identity
    assert inner._binding.image_identity == inner.image_identity
    assert inner._binding.image_identity != wrapper.image_identity

    wrapper._lock.acquire()
    try:
        with pytest.raises(SemanticUnavailable):
            wrapper.encode_prepared_batch([(Path("/private/a.png"), "e" * 64)])
    finally:
        wrapper._lock.release()

    inner._lock.acquire()
    try:
        with pytest.raises(SemanticUnavailable):
            wrapper.encode_prepared_batch([] if False else [(Path("/private/a.png"), "e" * 64)])
    finally:
        inner._lock.release()

    text = wrapper.encode("a query")
    assert text.binding_sha256 == binding.binding_sha256
    assert text.query_sha256 == hashlib.sha256(b"a query").hexdigest()
    assert text.checksum_sha256 == canonical_vector_checksum(text.vector)


def test_library_recipe_changes_image_identity_only(monkeypatch):
    wrapper, inner = _wrapper(monkeypatch)
    before = wrapper.image_identity
    text_before = wrapper.text_identity
    changed, _recipe = library._image_identity(inner.image_identity,
        inner.text_identity, {**library.preparation.PROFILE_RECIPE, "test_change": True},
        wrapper._wrapper_pin.sha256, wrapper._preparation_pin.sha256)
    assert changed != before
    assert wrapper.text_identity == text_before == inner.text_identity


def test_load_rejects_preparation_source_digest_mismatch(monkeypatch):
    inner = FakeInner()
    monkeypatch.setattr(library.SiglipModel, "load", lambda **_kwargs: inner)
    with pytest.raises(SemanticUnavailable):
        library.LibrarySiglipModel.load(model_directory="unused", artifacts={},
            package_versions={}, preparation_source_sha256="0" * 64)


def test_receipt_is_inactive_and_contains_separate_base_evidence(monkeypatch):
    wrapper, _inner = _wrapper(monkeypatch)
    receipt = wrapper.receipt()
    assert receipt["schema"] == "photohouse.siglip2_library_recipe_receipt.v1"
    assert receipt["base_model_receipt"] == {"schema": "base-receipt"}
    assert receipt["activation_approved"] is False
    assert receipt["relevance_accepted"] is False
    assert receipt["cpu_threads"] == 2

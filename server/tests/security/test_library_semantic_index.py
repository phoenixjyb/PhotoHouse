"""Offline snapshot indexing, resume, and receipt validation contracts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import threading

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))

import library_semantic_index as index  # noqa: E402
import library_siglip  # noqa: E402
import qualify_multilingual_scenes as qualification  # noqa: E402
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum  # noqa: E402


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_identity(role):
    recipe = {
        "schema": "photohouse.siglip2_recipe.v1",
        "model_id": qualification.MODEL_ID,
        "revision": qualification.REVISION,
        "artifacts": qualification.OFFICIAL_ARTIFACTS,
        "package_versions": qualification.EXPECTED_PACKAGES,
        "source_digests": {"fixture": "a" * 64},
        "device": "cpu", "dtype": "float32", "dimension": 768,
        "output": "float32_unit_l2", "role": role,
    }
    if role == "image":
        recipe.update(input_profile="private_single_frame_jpeg_png_exif_rgb_v1",
            preprocessor={"fixture": True})
    else:
        recipe.update(normalization="unicode_lowercase", max_length=64,
            padding="max_length", truncation=False, overflow="refuse",
            attention_mask="not_supplied", add_bos_token=False, add_eos_token=True,
            original_query_binding="sha256_utf8_before_normalization")
    return VectorSpaceIdentity(
        qualification.OFFICIAL_ARTIFACTS["model.safetensors"]["sha256"],
        index.recipe_sha256(recipe), library_siglip.SPACE,
        library_siglip.MODEL_VERSION, 768, "unit_l2"), recipe


class FakeModel:
    def __init__(self):
        self.base_image, image_recipe = _base_identity("image")
        self.base_text, text_recipe = _base_identity("text")
        self.image_identity, self.image_recipe = library_siglip._image_identity(
            self.base_image, self.base_text, index.preparation.PROFILE_RECIPE,
            index._source_pin(Path(library_siglip.__file__).resolve()).sha256,
            index._source_pin(Path(index.preparation.__file__).resolve()).sha256)
        self.text_identity = self.base_text
        self.base_receipt = {"schema": "photohouse.siglip2_adapter_receipt.v1",
            "image_identity": {k: getattr(self.base_image, k)
                for k in self.base_image.__dataclass_fields__},
            "text_identity": {k: getattr(self.base_text, k)
                for k in self.base_text.__dataclass_fields__},
            "recipes": {"image": image_recipe, "text": text_recipe},
            "cpu_threads": 2, "relevance_accepted": False, "activation_approved": False}
        self.calls = 0
        self.binding = None

    def verify(self):
        return None

    def receipt(self):
        return {"schema": "photohouse.siglip2_library_recipe_receipt.v1",
            "image_identity": {k: getattr(self.image_identity, k)
                for k in self.image_identity.__dataclass_fields__},
            "text_identity": {k: getattr(self.text_identity, k)
                for k in self.text_identity.__dataclass_fields__},
            "base_model_receipt": self.base_receipt,
            "image_recipe": self.image_recipe, "cpu_threads": 2,
            "activation_approved": False, "relevance_accepted": False}

    def encode_prepared_batch(self, paths_and_sha, *, check=lambda: None):
        check()
        self.calls += 1
        return tuple((1.0,) + (0.0,) * 767 for _ in paths_and_sha)


def _fixture(tmp_path, count):
    source_root = tmp_path / "originals"
    source_root.mkdir(mode=0o700)
    source_root.chmod(0o700)
    image = Image.new("RGB", (12, 7), (38, 72, 105))
    blob = tmp_path / "source.jpg"
    image.save(blob, format="JPEG", quality=85)
    assets = []
    for number in range(count):
        path = source_root / f"photo-{number:05d}.jpg"
        path.write_bytes(blob.read_bytes())
        path.chmod(0o600)
        assets.append({"asset_id": str(number + 1), "path": str(path),
            "sha256": _digest(path), "mime": "image/jpeg",
            "width": 0, "height": -1})
    output_parent = tmp_path / "private-output"
    output_parent.mkdir(mode=0o700)
    output_parent.chmod(0o700)
    return ({"schema": index.SCHEMA, "library_id": "library-test", "assets": assets},
        source_root, output_parent)


def test_full_library_resume_batches_and_tail_padding(tmp_path):
    snapshot, roots, parent = _fixture(tmp_path, 515)
    model = FakeModel()
    output = parent / "index-run"
    first = index.execute(snapshot, output, model=model, original_roots=[roots],
        resume=False, free_space_floor=0, max_new_assets=8)
    assert first["status"] == "library_index_checkpointed_partial"
    assert model.calls == 1
    second = index.execute(snapshot, output, model=model, original_roots=[roots],
        resume=True, free_space_floor=0, max_new_assets=8)
    assert second["committed_assets"] == 16
    assert model.calls == 2  # the first immutable checkpoint was not re-encoded
    result = index.execute(snapshot, output, model=model, original_roots=[roots],
        resume=True, free_space_floor=0)
    assert result["status"] == "library_index_prepared"
    assert result["record_count"] == 515
    assert model.calls == 65  # 64 full batches plus one padded 3-image tail
    manifest, records, identities = index.inspect_library_index(output,
        expected_snapshot=snapshot)
    assert manifest["processing_complete"] is True
    assert manifest["complete"] is True and manifest["failure_count"] == 0
    assert len(records) == 515
    assert identities["image"] == model.image_identity
    assert identities["text"] == model.text_identity
    assert manifest["records"][0]["observed_width"] == 12
    assert manifest["records"][0]["prepared_width"] == 12


def test_missing_source_is_explicit_and_completed_manifest_is_not_complete(tmp_path):
    snapshot, roots, parent = _fixture(tmp_path, 8)
    missing = roots / "gone.jpg"
    snapshot["assets"][-1]["path"] = str(missing)
    snapshot["assets"][-1]["sha256"] = None
    model = FakeModel()
    output = parent / "index-run"
    result = index.execute(snapshot, output, model=model, original_roots=[roots],
        free_space_floor=0)
    assert result["failure_count"] == 1
    manifest, records, _identities = index.inspect_library_index(output,
        expected_snapshot=snapshot)
    assert manifest["processing_complete"] is True
    assert manifest["complete"] is False
    assert manifest["failures"] == [{"status": "failed", "asset_id": "8",
        "source_path": str(missing), "code": "source_missing",
        "source_sha256": None, "source_stat_identity": None}]
    assert len(records) == 7 and model.calls == 1


def test_resume_and_inspector_refuse_source_drift_and_orphan_artifacts(tmp_path):
    snapshot, roots, parent = _fixture(tmp_path, 8)
    model = FakeModel()
    output = parent / "index-run"
    index.execute(snapshot, output, model=model, original_roots=[roots],
        free_space_floor=0, max_new_assets=8)
    source = Path(snapshot["assets"][0]["path"])
    source.write_bytes(source.read_bytes() + b"changed")
    source.chmod(0o600)
    with pytest.raises(index.LibraryIndexUnavailable):
        index.inspect_library_index(output)
    with pytest.raises(index.LibraryIndexUnavailable):
        index.execute(snapshot, output, model=model, original_roots=[roots],
            resume=True, free_space_floor=0)


def test_snapshot_membership_and_vector_tampering_fail_closed(tmp_path):
    snapshot, roots, parent = _fixture(tmp_path, 8)
    model = FakeModel()
    output = parent / "index-run"
    index.execute(snapshot, output, model=model, original_roots=[roots], free_space_floor=0)
    changed_snapshot = json.loads(json.dumps(snapshot))
    changed_snapshot["assets"][0]["path"] = str(roots / "another.jpg")
    with pytest.raises(index.LibraryIndexUnavailable):
        index.inspect_library_index(output, expected_snapshot=changed_snapshot)
    record = next(output.glob("image-vectors/*/*.npy"))
    record.write_bytes(record.read_bytes()[:-1] + b"\x01")
    record.chmod(0o600)
    with pytest.raises(index.LibraryIndexUnavailable):
        index.inspect_library_index(output)


def _completed_index(tmp_path, count=2):
    snapshot, roots, parent = _fixture(tmp_path, count)
    output = parent / "index-run"
    index.execute(snapshot, output, model=FakeModel(), original_roots=[roots],
        free_space_floor=0)
    return snapshot, roots, output


def _replace_json(path, value):
    path.write_bytes(index.canonical(value) + b"\n")
    path.chmod(0o600)


def test_each_independent_audit_verifies_every_artifact_once(monkeypatch, tmp_path):
    snapshot, _roots, output = _completed_index(tmp_path, count=9)
    read_vector = index._read_vector
    reads = []

    def observed(root, record):
        reads.append(record.asset_id)
        return read_vector(root, record)

    monkeypatch.setattr(index, "_read_vector", observed)
    first = index.inspect_library_index(output, expected_snapshot=snapshot)
    assert reads == [str(number) for number in range(1, 10)]
    reads.clear()
    second = index.inspect_library_index(output, expected_snapshot=snapshot)
    assert reads == [str(number) for number in range(1, 10)]
    assert first == second
    # No result survives into another audit: fresh byte tampering is refused.
    target = next(output.glob("image-vectors/*/*.npy"))
    target.write_bytes(target.read_bytes()[:-1] + b"\x01")
    with pytest.raises(index.LibraryIndexUnavailable):
        index.inspect_library_index(output, expected_snapshot=snapshot)


def test_checkpoint_manifest_mismatch_refuses_before_any_artifact_read(monkeypatch, tmp_path):
    _snapshot, _roots, output = _completed_index(tmp_path, count=9)
    path = output / "index.json"
    manifest = json.loads(path.read_bytes())
    manifest["records"][-1]["metadata_sha256"] = "a" * 64
    _replace_json(path, manifest)
    reads = []
    monkeypatch.setattr(index, "_read_vector", lambda *args: reads.append(args))
    with pytest.raises(index.LibraryIndexUnavailable):
        index.inspect_library_index(output)
    assert reads == []


@pytest.mark.parametrize("field,value", [
    ("asset_id", "999"),
    ("source_sha256", "a" * 64),
    ("identity_sha256", "a" * 64),
    ("file_sha256", "a" * 64),
    ("component_sha256", "a" * 64),
    ("relative_path", "image-vectors/" + "a" * 64 + "/" + "b" * 64 + ".npy"),
])
def test_rebound_metadata_still_requires_artifact_and_source_identity(tmp_path, field, value):
    _snapshot, _roots, output = _completed_index(tmp_path)
    manifest_path = output / "index.json"
    manifest = json.loads(manifest_path.read_bytes())
    summary = manifest["records"][0]
    metadata_path = next(output.glob(f"image-vectors/*/{summary['record_id']}.json"))
    metadata = json.loads(metadata_path.read_bytes())
    metadata[field] = value
    _replace_json(metadata_path, metadata)
    summary["metadata_sha256"] = _digest(metadata_path)
    batch_path = output / "checkpoints" / "batch-00000000.json"
    batch = json.loads(batch_path.read_bytes())
    batch["results"][0]["metadata_sha256"] = summary["metadata_sha256"]
    _replace_json(batch_path, batch)
    _replace_json(manifest_path, manifest)
    # Even agreement between the manifest and checkpoint does not authorize
    # stale source/identity bindings, an alias path, or wrong vector checksums.
    with pytest.raises(index.LibraryIndexUnavailable):
        index.inspect_library_index(output)


def test_canonical_metadata_change_requires_original_checkpoint_digest(tmp_path):
    _snapshot, _roots, output = _completed_index(tmp_path)
    path = next(output.glob("image-vectors/*/*.json"))
    metadata = json.loads(path.read_bytes())
    metadata["created_at"] += 1
    _replace_json(path, metadata)
    with pytest.raises(index.LibraryIndexUnavailable):
        index.inspect_library_index(output)


@pytest.mark.parametrize("suffix,alias", [("json", "symlink"), ("npy", "symlink"),
                                         ("json", "hardlink"), ("npy", "hardlink")])
def test_audit_refuses_linked_artifacts(tmp_path, suffix, alias):
    _snapshot, _roots, output = _completed_index(tmp_path)
    path = next(output.glob(f"image-vectors/*/*.{suffix}"))
    other = output.parent / f"alias.{suffix}"
    if alias == "symlink":
        other.write_bytes(path.read_bytes())
        other.chmod(0o600)
        path.unlink()
        path.symlink_to(other)
    else:
        os.link(path, other)
    with pytest.raises(index.LibraryIndexUnavailable):
        index.inspect_library_index(output)


def test_source_drift_after_checkpoint_validation_is_still_refused(monkeypatch, tmp_path):
    snapshot, _roots, output = _completed_index(tmp_path)
    verify_batch = index._verify_batch

    def change_after_batch(*args, **kwargs):
        verify_batch(*args, **kwargs)
        source = Path(snapshot["assets"][0]["path"])
        source.write_bytes(source.read_bytes() + b"changed")

    monkeypatch.setattr(index, "_verify_batch", change_after_batch)
    with pytest.raises(index.LibraryIndexUnavailable):
        index.inspect_library_index(output)


def test_uncommitted_orphan_is_preserved_and_resume_refuses_it(tmp_path):
    snapshot, roots, parent = _fixture(tmp_path, 8)
    model = FakeModel()
    output = parent / "index-run"
    index.execute(snapshot, output, model=model, original_roots=[roots],
        free_space_floor=0, max_new_assets=8)
    orphan = output / "checkpoints" / "batch-99999999.json"
    orphan.write_text("unknown", encoding="utf-8")
    orphan.chmod(0o600)
    with pytest.raises(index.LibraryIndexUnavailable):
        index.execute(snapshot, output, model=model, original_roots=[roots],
            resume=True, free_space_floor=0)
    assert orphan.read_text(encoding="utf-8") == "unknown"


def test_check_cancellation_aborts_without_recording_asset_failure(tmp_path):
    snapshot, roots, parent = _fixture(tmp_path, 8)
    model = FakeModel()
    counter = {"calls": 0}

    def cancelled():
        counter["calls"] += 1
        if counter["calls"] > 12:
            raise TimeoutError("coordinator deadline")

    output = parent / "index-run"
    with pytest.raises(index.LibraryIndexUnavailable):
        index.execute(snapshot, output, model=model, original_roots=[roots],
            check=cancelled, free_space_floor=0)
    assert not (output / "checkpoints" / "batch-00000000.json").exists()


def test_retained_failed_scratch_is_capped_before_next_preparation(monkeypatch, tmp_path):
    snapshot, roots, parent = _fixture(tmp_path, 8)
    model = FakeModel()
    monkeypatch.setattr(index, "_scratch_bytes", lambda _path: index.MAX_SCRATCH_BYTES)
    output = parent / "index-run"
    with pytest.raises(index.LibraryIndexUnavailable):
        index.execute(snapshot, output, model=model, original_roots=[roots],
            free_space_floor=0)
    assert model.calls == 0
    assert not (output / "checkpoints" / "batch-00000000.json").exists()



def _private_json(path, raw):
    path.write_bytes(raw)
    path.chmod(0o600)
    return path


def test_inspector_json_reader_is_bounded_single_descriptor_and_preserves_value(monkeypatch, tmp_path):
    path = _private_json(tmp_path / "inspector.json", b'{"a":1}\n')
    original = index._open_pinned
    reads = []

    class Tracked:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def fileno(self): return self.stream.fileno()
        def read(self, size):
            reads.append(size)
            return self.stream.read(size)

    monkeypatch.setattr(index, "_open_pinned", lambda *args: Tracked(original(*args)))
    monkeypatch.setattr(Path, "read_bytes", lambda _self: (_ for _ in ()).throw(AssertionError("path reread")))
    assert index._load_json_inspector(path, 64) == {"a": 1}
    assert reads == [65]


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}\n', b'{"a":NaN}\n', b'{ "a": 1 }\n', b'{"a":1}'])
def test_inspector_json_reader_rejects_duplicate_nonfinite_noncanonical_and_truncated(raw, tmp_path):
    path = _private_json(tmp_path / "invalid.json", raw)
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(path, 64)


def test_inspector_json_reader_binds_expected_metadata_digest_to_loaded_bytes(tmp_path):
    path = _private_json(tmp_path / "metadata.json", b'{"a":1}\n')
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(path, 64, expected_sha256="0" * 64)
    assert index._load_json_inspector(path, 64,
        expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest()) == {"a": 1}


@pytest.mark.parametrize("race", ["before_open", "after_open_before_read", "after_read"])
def test_inspector_json_reader_rejects_pre_open_and_descriptor_mutations(monkeypatch, tmp_path, race):
    path = _private_json(tmp_path / "raced.json", b'{"a":1}\n')
    original_open = index._open_pinned
    original = b'{"a":1}\n'
    changed = b'{"a":2}\n'

    def mutate():
        path.write_bytes(changed)
        path.chmod(0o600)

    if race == "before_open":
        def open_after_mutation(*args):
            mutate()
            return original_open(*args)
        monkeypatch.setattr(index, "_open_pinned", open_after_mutation)
    elif race == "after_open_before_read":
        class MutateBeforeRead:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def fileno(self): return self.stream.fileno()
            def read(self, size): mutate(); return self.stream.read(size)
        monkeypatch.setattr(index, "_open_pinned", lambda *args: MutateBeforeRead(original_open(*args)))
    else:
        class MutateAfterRead:
            def __init__(self, stream): self.stream = stream
            def __enter__(self): return self
            def __exit__(self, *args): return self.stream.__exit__(*args)
            def fileno(self): return self.stream.fileno()
            def read(self, size):
                data = self.stream.read(size)
                mutate()
                return data
        monkeypatch.setattr(index, "_open_pinned", lambda *args: MutateAfterRead(original_open(*args)))
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(path, 64)



def test_inspector_growth_after_open_stays_bounded_and_refuses(monkeypatch, tmp_path):
    path = _private_json(tmp_path / "growth-race.json", b'{"a":1}\n')
    original_open = index._open_pinned
    sizes = []

    class GrowBeforeRead:
        def __init__(self, stream): self.stream = stream
        def __enter__(self): return self
        def __exit__(self, *args): return self.stream.__exit__(*args)
        def fileno(self): return self.stream.fileno()
        def read(self, size):
            sizes.append(size)
            path.write_bytes(b'{"a":1}\n' + b' ' * 4096)
            path.chmod(0o600)
            return self.stream.read(size)

    monkeypatch.setattr(index, "_open_pinned", lambda *args: GrowBeforeRead(original_open(*args)))
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(path, 64)
    assert sizes == [65]


def test_inspector_final_digest_rejects_same_size_restored_mtime_mutation(monkeypatch, tmp_path):
    import image_embedding_receipts as receipts
    path = _private_json(tmp_path / "final-race.json", b'{"a":1}\n')
    identity = receipts._stat_identity(path.stat())
    monkeypatch.setattr(receipts, "_stat_identity", lambda _info: identity)
    monkeypatch.setattr(index, "_stat_identity", lambda _info: identity)
    verify = index.verify_checkpoint

    def mutate_before_final_verify(pin):
        info = path.stat()
        path.write_bytes(b'{"a":2}\n')
        path.chmod(0o600)
        os.utime(path, ns=(info.st_atime_ns, info.st_mtime_ns))
        return verify(pin)

    monkeypatch.setattr(index, "verify_checkpoint", mutate_before_final_verify)
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(path, 64)


def test_inspector_json_reader_refuses_links_reparse_and_private_gate_failure(monkeypatch, tmp_path):
    target = _private_json(tmp_path / "target.json", b'{"a":1}\n')
    hardlink = tmp_path / "hardlink.json"
    os.link(target, hardlink)
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(hardlink, 64)
    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(target)
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(symlink, 64)
    hardlink.unlink()  # Restore the original single-link precondition.
    calls = []
    def refuse_reparse(_path):
        calls.append(1)
        raise ValueError("reparse")
    monkeypatch.setattr(index, "_checkpoint_path", refuse_reparse)
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(target, 64)
    assert calls == [1]


def test_inspector_json_reader_requires_private_file_gate(monkeypatch, tmp_path):
    path = _private_json(tmp_path / "acl.json", b'{"a":1}\n')
    calls = []
    def refuse(_path):
        calls.append(1)
        raise ValueError("ACL refusal")
    monkeypatch.setattr(index, "require_private_file", refuse)
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(path, 64)
    assert calls == [1]



def test_inspector_rechecks_private_file_gate_after_final_digest(monkeypatch, tmp_path):
    path = _private_json(tmp_path / "final-acl.json", b'{"a":1}\n')
    original_gate = index.require_private_file
    calls = []
    def refuse_third_gate(selected):
        calls.append(selected)
        if len(calls) == 3:
            raise ValueError("final ACL refusal")
        return original_gate(selected)
    monkeypatch.setattr(index, "require_private_file", refuse_third_gate)
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(path, 64)
    assert len(calls) == 3


def test_inspector_json_reader_rejects_size_before_open(monkeypatch, tmp_path):
    path = _private_json(tmp_path / "large.json", b'{"a":1}\n')
    opened = []
    monkeypatch.setattr(index, "_open_pinned", lambda *_: opened.append(True))
    with pytest.raises(index.LibraryIndexUnavailable):
        index._load_json_inspector(path, 4)
    assert opened == []

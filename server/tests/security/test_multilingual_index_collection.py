"""Generated private documents exercise collection boundaries without media or models."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "backend"))
import multilingual_index_collection as collection
from multilingual_library_coverage import plan_snapshot


@dataclass(frozen=True)
class Identity:
    artifact_sha256: str = "a" * 64
    preprocessing_sha256: str = "b" * 64
    vector_space_id: str = "siglip2-base-p16-256"
    model_version: str = "siglip2-base-p16-256-v1"
    dimension: int = 768
    normalization: str = "unit_l2"


def private_json(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")), encoding="utf-8")
    path.chmod(0o600)
    return path


def private_bytes(path, content):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(0o600)
    return path


def make_snapshot(count):
    return {
        "schema": "photohouse.multilingual_library_snapshot.v1",
        "library_id": "fixture-family",
        "source_revision_sha256": "c" * 64,
        "assets": [{
            "asset_id": index,
            "path": f"/private/library/image-{index}.jpg",
            "db_source_sha256": hashlib.sha256(f"source:{index}".encode()).hexdigest(),
            "mime": "image/jpeg", "width": 32, "height": 32, "bytes": 128,
            "file_status": "available",
        } for index in range(1, count + 1)],
    }


def fake_batches(tmp_path, snapshot, *, split=None):
    plan = plan_snapshot(snapshot)
    groups = [batch["asset_ids"] for batch in plan["batches"]]
    if split is not None:
        groups = split
    refs = []
    for number, group in enumerate(groups, 1):
        assets = [{"asset_id": str(asset_id),
                   # The reviewed builder cohort points at its scoped private
                   # input copy, which can differ from the library source path.
                   "path": f"/private/builder-input/batch-{number}/asset-{asset_id}.jpg",
                   "sha256": snapshot["assets"][asset_id - 1]["db_source_sha256"]}
                  for asset_id in group]
        cohort = {"schema": "photohouse.multilingual_image_cohort.v1",
                  "library_id": snapshot["library_id"], "reviewed": True, "assets": assets}
        cohort_path = private_json(tmp_path / f"batch-{number}" / "cohort.json", cohort)
        content = {**cohort, "assets": [{"asset_id": item["asset_id"], "sha256": item["sha256"]}
                                        for item in assets]}
        cohort_digest = hashlib.sha256(json.dumps(content, sort_keys=True,
            separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()
        index_path = private_json(tmp_path / f"batch-{number}" / "index.json",
            {"schema": "fixture-index", "cohort_sha256": cohort_digest, "batch": number})
        refs.append({"cohort_path": str(cohort_path), "index_path": str(index_path)})
    return refs


def inspector_factory(*, mixed_identity_batch=None, corrupt_batch=None):
    def inspect(path, *, expected_library, expected_cohort):
        manifest = json.loads(Path(path).read_text(encoding="utf-8"))
        assert expected_library == "fixture-family"
        identity = Identity()
        if corrupt_batch == Path(path).parent.name:
            raise ValueError("corrupt tail")
        if mixed_identity_batch == Path(path).parent.name:
            identity = Identity(artifact_sha256="d" * 64)
        return manifest, tuple(SimpleNamespace(asset_id=int(row["asset_id"]))
                               for row in expected_cohort["assets"]), {
            "image": identity, "text": identity,
        }
    return inspect


def install_inspector(monkeypatch, inspector):
    monkeypatch.setattr(collection, "_indexer",
                        lambda: SimpleNamespace(inspect_index=inspector))


def test_collection_handles_1025_assets_as_three_verified_batches(tmp_path, monkeypatch):
    snapshot = make_snapshot(1025)
    refs = fake_batches(tmp_path, snapshot)
    install_inspector(monkeypatch, inspector_factory())
    result = collection.assemble_collection(snapshot, refs, tmp_path / "collection")
    manifest = collection.inspect_collection(tmp_path / "collection" / "collection.json")
    assert result["indexed_asset_count"] == 1025
    assert result["batch_count"] == 3
    assert [len(batch["asset_ids"]) for batch in manifest["batches"]] == [512, 512, 1]
    assert len(manifest["roster"]["assets"]) == manifest["roster_count"] == 1025
    assert all(len(batch["cohort_file_sha256"]) == len(batch["index_file_sha256"]) == 64
               for batch in manifest["batches"])
    assert manifest["production_published"] is False
    assert manifest["activation_performed"] is False


def test_collection_batch_bound_allows_byte_budgeted_276_batch_household():
    snapshot = make_snapshot(21_804)
    for row in snapshot["assets"]:
        row["bytes"] = 3_360_000
    groups = collection._expected_batches(collection.validate_roster(snapshot))
    assert len(groups) == 276
    assert all(len(group) == 79 for group in groups)
    assert collection.MAX_BATCHES >= len(groups)


@pytest.mark.parametrize("damage", ["duplicate", "omitted", "foreign", "stale", "mixed", "corrupt_tail"])
def test_collection_refuses_non_exact_or_mixed_batch_cohorts(tmp_path, damage, monkeypatch):
    snapshot = make_snapshot(513)
    refs = fake_batches(tmp_path, snapshot)
    inspector = inspector_factory()
    if damage == "duplicate":
        refs[1] = refs[0]
    elif damage == "omitted":
        refs = refs[:1]
    elif damage == "foreign":
        cohort_path = Path(refs[1]["cohort_path"])
        cohort = json.loads(cohort_path.read_text())
        cohort["assets"][0]["asset_id"] = "9999"
        private_json(cohort_path, cohort)
    elif damage == "stale":
        cohort_path = Path(refs[0]["cohort_path"])
        cohort = json.loads(cohort_path.read_text())
        cohort["assets"][0]["sha256"] = "f" * 64
        private_json(cohort_path, cohort)
    elif damage == "mixed":
        inspector = inspector_factory(mixed_identity_batch="batch-2")
    elif damage == "corrupt_tail":
        inspector = inspector_factory(corrupt_batch="batch-2")
    install_inspector(monkeypatch, inspector)
    with pytest.raises(ValueError):
        collection.assemble_collection(snapshot, refs, tmp_path / "collection")
    assert not (tmp_path / "collection" / "collection.json").exists()


def test_collection_inspection_detects_changed_batch_tail_and_bad_paths(tmp_path, monkeypatch):
    snapshot = make_snapshot(513)
    refs = fake_batches(tmp_path, snapshot)
    install_inspector(monkeypatch, inspector_factory())
    collection.assemble_collection(snapshot, refs, tmp_path / "collection")
    tail_index = Path(refs[1]["index_path"])
    index = json.loads(tail_index.read_text())
    index["batch"] = 9
    private_json(tail_index, index)
    with pytest.raises(ValueError):
        collection.inspect_collection(tmp_path / "collection" / "collection.json")

    malformed = [{"cohort_path": refs[0]["cohort_path"],
                  "index_path": str(Path(refs[0]["index_path"]).parent / ".." / "batch-2" / "index.json")}, refs[1]]
    with pytest.raises(ValueError):
        collection.assemble_collection(snapshot, malformed, tmp_path / "other")


def test_stage_export_copies_only_verified_derived_vectors_and_emits_future_rows(monkeypatch, tmp_path):
    from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
    from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256
    snapshot = make_snapshot(2)
    snapshot["assets"][1]["file_status"] = "missing"
    refs = fake_batches(tmp_path, snapshot)
    collection_dir = tmp_path / "collection"
    identity = VectorSpaceIdentity("a" * 64, "b" * 64, "siglip2-base-p16-256",
                                   "siglip2-base-p16-256-v1", 768, "unit_l2")
    identity_digest = identity_sha256(identity)
    vector = (1.0,) + (0.0,) * 767
    real_indexer = collection._indexer()
    raw_vector = real_indexer.npy_bytes(vector)
    vectors_by_path = {}

    def inspect_index(index_path, *, expected_library, expected_cohort):
        assert expected_library == "fixture-family"
        records = []
        for asset in expected_cohort["assets"]:
            aid = int(asset["asset_id"])
            record_id = hashlib.sha256(f"record:{aid}".encode()).hexdigest()
            relative_path = f"image-vectors/{identity_digest}/{record_id}.npy"
            source_vector = Path(index_path).parent / relative_path
            vectors_by_path[str(source_vector)] = raw_vector
            records.append(ImmutableVectorArtifact(
                record_id=record_id, asset_id=str(aid), source_sha256=asset["sha256"],
                model_name="siglip2-base-p16-256", artifact_sha256=identity.artifact_sha256,
                preprocessing_sha256=identity.preprocessing_sha256,
                vector_space_id=identity.vector_space_id, model_version=identity.model_version,
                dimension=768, normalization="unit_l2", identity_sha256=identity_digest,
                relative_path=relative_path, file_sha256=hashlib.sha256(raw_vector).hexdigest(),
                component_sha256=canonical_vector_checksum(vector), created_at=1))
        return json.loads(Path(index_path).read_text()), tuple(records), {"image": identity, "text": identity}

    monkeypatch.setattr(real_indexer, "inspect_index", inspect_index)
    monkeypatch.setattr(collection, "_copy_verified_vector",
        lambda source, destination, _digest: private_bytes(destination, vectors_by_path[str(source)]))
    output = tmp_path / "flat-private-vectors"
    collection.assemble_collection(snapshot, refs, collection_dir)
    collection_manifest = collection.inspect_collection(collection_dir / "collection.json")
    result = collection.stage_collection_vectors(collection_dir / "collection.json", output)
    stage = json.loads((output / "collection-stage.json").read_text())
    assert result["record_count"] == 1
    assert result["database_rows_written"] is False
    assert stage["complete"] is True and stage["activation_performed"] is False
    assert {row["record"]["asset_id"] for row in stage["records"]} == {"1"}
    assert collection_manifest["complete"] is True
    assert collection_manifest["candidate_coverage"] is result["candidate_coverage"] is True
    assert collection_manifest["whole_library_coverage"] is result["whole_library_coverage"] is False
    assert collection_manifest["blocker_count"] == result["blocker_count"] == 1
    assert stage["candidate_coverage"] is True and stage["whole_library_coverage"] is False
    assert stage["blocker_count"] == 1
    assert len(list(output.rglob("*.npy"))) == 1
    assert len(list(output.rglob("*.json"))) == 2
    assert not list(output.rglob("*.jpg"))


def test_roster_validation_is_pure_and_collection_plan_is_inert(monkeypatch):
    snapshot = make_snapshot(2)
    monkeypatch.setattr(collection, "_load_private_document",
                        lambda *_a, **_k: pytest.fail("private file read"))
    assert collection.validate_roster(snapshot)["assets"][0]["asset_id"] == 1
    assert collection.plan()["private_files_read"] is False
    with pytest.raises(ValueError):
        collection.validate_roster({**snapshot, "assets": snapshot["assets"] + [snapshot["assets"][0]]})


def test_default_cli_imports_without_optional_models_or_private_reads():
    script = """
import builtins, sys
sys.path.insert(0, %r)
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'torch', 'transformers', 'PIL', 'numpy'}:
        raise AssertionError('optional model import')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import multilingual_index_collection as module
module._load_private_document = lambda *a, **k: (_ for _ in ()).throw(AssertionError('private read'))
assert module.run([]) == 0
""" % str(ROOT / "scripts")
    result = subprocess.run([sys.executable, "-I", "-B", "-c", script],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert '"private_files_read": false' in result.stdout


def test_real_generated_batch_manifests_join_and_stage_513_without_inspector_override(tmp_path, monkeypatch):
    """Exercise the actual builder+inspector+exporter seam; only inference is fake."""
    import test_multilingual_index_provider as fixture
    import build_multilingual_image_index as builder
    model = fixture.model.__wrapped__(monkeypatch, tmp_path)
    config = fixture.index_configuration(tmp_path)
    base_config = json.loads(config.read_bytes())
    template = json.loads((tmp_path / 'cohort.json').read_bytes())['assets'][0]
    snapshot = make_snapshot(513)
    snapshot['library_id'] = 'fixture-library'
    for row in snapshot['assets']:
        row.update(path=template['path'], db_source_sha256=template['sha256'],
                   mime='image/png', width=16, height=16,
                   bytes=Path(template['path']).stat().st_size)
    refs = []
    for index, batch in enumerate(plan_snapshot(snapshot)['batches']):
        root = tmp_path / ('batch-real-' + str(index)); root.mkdir(mode=0o700)
        cohort = {'schema': 'photohouse.multilingual_image_cohort.v1',
                  'library_id': 'fixture-library', 'reviewed': True,
                  'assets': [{**template, 'asset_id': str(aid)} for aid in batch['asset_ids']]}
        cp = private_json(root / 'cohort.json', cohort)
        cfg = private_json(root / 'config.json', {**base_config, 'cohort': str(cp)})
        builder.execute(cfg, root / 'vectors', model_loader=lambda **_kwargs: model)
        refs.append({'cohort_path': str(cp), 'index_path': str(root / 'vectors/index.json')})
    result = collection.assemble_collection(snapshot, refs, tmp_path / 'real-collection')
    assert result['indexed_asset_count'] == 513 and result['batch_count'] == 2
    staged = collection.stage_collection_vectors(tmp_path / 'real-collection/collection.json',
                                                tmp_path / 'real-stage')
    assert staged['record_count'] == 513 and staged['database_rows_written'] is False

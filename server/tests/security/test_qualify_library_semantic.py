"""Generated-fixture checks for the disabled-by-default library canary."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

import qualify_library_semantic as subject
from app.access.semantic_encoder import TextVector
from app.access.semantic_bulk_vectors import BulkVectorStore, BulkVectorUnavailable
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256


def _npy(vector):
    header = repr({"descr": "<f4", "fortran_order": False,
        "shape": (len(vector),)}).encode("ascii")
    padding = (-(10 + len(header) + 1)) % 16
    header += b" " * padding + b"\n"
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header + struct.pack(
        f"<{len(vector)}f", *vector)


class FakeLibraryModel:
    def __init__(self, image, text):
        self.image_identity = image
        self.text_identity = text
        self.binding = None
        self.bind_count = 0
        self.encode_count = 0

    def receipt(self):
        return {"schema": "generated-library-model-receipt.v1",
            "image_identity": asdict(self.image_identity),
            "text_identity": asdict(self.text_identity)}

    def bind(self, binding):
        assert self.binding is None
        if getattr(self, "raise_on_bind", False):
            raise RuntimeError("injected_model_bind_failure")
        self.bind_count += 1
        self.binding = binding

    def verify(self):
        assert self.binding is not None

    def encode(self, query, *, check):
        check()
        self.encode_count += 1
        vector = (1.0,) + (0.0,) * 767
        return TextVector(self.binding.binding_sha256,
            hashlib.sha256(query.encode("utf-8")).hexdigest(), vector,
            canonical_vector_checksum(vector))


@pytest.fixture
def generated_index(monkeypatch, tmp_path):
    image = VectorSpaceIdentity("a" * 64, "b" * 64,
        "siglip2-base-p16-256-3f9f96c", "siglip2-3f9f96c-v1", 768, "unit_l2")
    text = VectorSpaceIdentity("a" * 64, "c" * 64,
        "siglip2-base-p16-256-3f9f96c", "siglip2-3f9f96c-v1", 768, "unit_l2")
    model = FakeLibraryModel(image, text)
    identity_digest = identity_sha256(image)
    vector = (1.0,) + (0.0,) * 767
    raw = _npy(vector)
    vector_root = tmp_path / "verified-index"
    vector_path = vector_root / f"image-vectors/{identity_digest}"
    vector_path.mkdir(parents=True)
    index_path = vector_root / "library-index.json"
    manifest = {"schema": "photohouse.library_semantic_index.v1",
        "library_id": "fixture-family", "snapshot_sha256": "f" * 64,
        "snapshot_asset_count": 516, "record_count": 515, "failure_count": 1,
        "model_receipt": model.receipt(), "processing_complete": True, "complete": False,
        "failures": [{"kind": "missing_source"}]}
    index_path.write_text(json.dumps(manifest))
    records = []
    for number in range(1, 516):
        asset_id = str(number)
        source_sha = hashlib.sha256(f"synthetic-source-{number}".encode()).hexdigest()
        record_id = hashlib.sha256(f"record-{number}".encode()).hexdigest()
        relative = f"image-vectors/{identity_digest}/{record_id}.npy"
        path = vector_root / relative
        path.write_bytes(raw)
        records.append(ImmutableVectorArtifact(
            record_id=record_id, asset_id=asset_id, source_sha256=source_sha,
            model_name="library-siglip2", artifact_sha256=image.artifact_sha256,
            preprocessing_sha256=image.preprocessing_sha256,
            vector_space_id=image.vector_space_id, model_version=image.model_version,
            dimension=image.dimension, normalization=image.normalization,
            identity_sha256=identity_digest, relative_path=relative,
            file_sha256=hashlib.sha256(raw).hexdigest(),
            component_sha256=canonical_vector_checksum(vector), created_at=1))

    index_module = SimpleNamespace(inspect_library_index=lambda path, **kwargs:
        (manifest, tuple(records), {"image": image, "text": text}))
    monkeypatch.setitem(sys.modules, "library_semantic_index", index_module)
    return index_path, model, manifest, tuple(records), vector_root


def test_plan_and_query_refusal_are_io_free(capsys):
    assert subject.run([]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan == {"status": "library_semantic_plan", "private_files_read": False,
        "models_loaded": False, "listener_started": False, "activation_performed": False}
    with pytest.raises(subject.LibrarySemanticRefused):
        subject._valid_queries([{"id": "x", "language": "en", "text": "no people"}])


def test_measurement_uses_synthetic_515_record_cohort_and_keeps_semantic_off(
        generated_index, tmp_path):
    index_path, model, manifest, records, vector_root = generated_index
    output = tmp_path / "private-output"
    result = subject.measure(index_path, output, model=model,
        queries=[{"id": "q1", "language": "en", "text": "a quiet family garden"}],
        repetitions=1)

    assert len(records) == result["available_image_count"] == 515
    assert result["index_failure_count"] == 1
    assert result["full_family_index_complete"] is False
    assert result["family_relevance_accepted"] is False
    assert result["human_relevance_measured"] is False
    assert result["activation_performed"] is False
    assert result["production_database_opened"] is False
    assert result["resources_closed"] is True
    assert result["read_limits"] == {
        "candidate_limit": 100000, "source_rows": 1000000,
        "source_bytes": 256 * 1024**2, "search_seconds": 120.0,
        "vector_read_bytes": 256 * 1024**2, "batch_size": 128,
        "shared_admission_pool": True}
    assert result["transport_boundary"] == "listener_free_asgi_api_and_authenticated_provider_cpu"
    assert result["model_encode_calls"] == result["provider_calls"] >= 2
    assert result["vector_reads"] > 0
    assert result["latency_ms"]["count"] == 1
    assert result["warmup_ms"] >= 0
    assert result["samples"][0]["candidate_count"] == 515
    assert {"query_id", "language", "query_sha256", "elapsed_ms"} <= set(result["samples"][0])
    assert {
        "provider_bad_bearer_denied_before_model",
        "viewer_denied_before_model_and_vector_reads",
        "other_owner_denied_before_model_and_vector_reads",
        "invalid_denied_before_model_and_vector_reads",
        "three_language_exclusions_clarified_before_provider_and_vectors",
        "synthetic_date_filter_remains_hard_filter",
        "synthetic_source_change_refused_and_restored_separately",
    } <= set(result["protected_checks"])
    assert model.bind_count == 1
    assert json.loads((output / "measurement.json").read_text()) == result
    for record in records:
        assert hashlib.sha256((vector_root / record.relative_path).read_bytes()).hexdigest() == record.file_sha256


def test_measurement_refuses_rebound_model_before_output(generated_index, tmp_path):
    index_path, model, _manifest, _records, _root = generated_index
    model.binding = object()
    output = tmp_path / "never-created"
    with pytest.raises(subject.LibrarySemanticRefused, match="model_already_bound"):
        subject.measure(index_path, output, model=model,
            queries=[{"id": "q1", "language": "zh", "text": "花园里的家人"}])
    assert not output.exists()


def _loopback_tls_files(directory):
    openssl = shutil.which("openssl")
    if openssl is None:
        pytest.skip("openssl is required for the real loopback TLS test")
    certificate = directory / "loopback-cert.pem"
    private_key = directory / "loopback-key.pem"
    completed = subprocess.run([
        openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256",
        "-days", "1", "-keyout", str(private_key), "-out", str(certificate),
        "-subj", "/CN=127.0.0.1", "-addext", "subjectAltName=IP:127.0.0.1",
        "-addext", "basicConstraints=critical,CA:TRUE",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=False)
    assert completed.returncode == 0, completed.stderr.decode("utf-8", "replace")
    certificate.chmod(0o600)
    private_key.chmod(0o600)
    return certificate, private_key


def _track_loopback_sockets(monkeypatch, loopback):
    reserved = []
    real_reserve = loopback.reserve_socket

    def validate_real_socket(sock):
        # macOS may reject SO_ACCEPTCONN getsockopt with ENOPROTOOPT; these
        # checks still prove the acquired descriptor is IPv4 loopback-only.
        address = sock.getsockname()
        assert sock.family == loopback.socket.AF_INET
        assert sock.type & loopback.socket.SOCK_STREAM == loopback.socket.SOCK_STREAM
        assert address[0] == "127.0.0.1" and 1024 <= address[1] <= 65535
        assert sock.fileno() >= 0
        return address[1]

    if sys.platform == "darwin":
        monkeypatch.setattr(loopback, "_validate_socket", validate_real_socket)

    def track_socket():
        sock = real_reserve()
        reserved.append(sock)
        return sock

    monkeypatch.setattr(loopback, "reserve_socket", track_socket)
    return reserved


def test_network_measurement_uses_real_loopback_https_and_tcp_and_closes_listeners(
        generated_index, tmp_path, monkeypatch):
    import semantic_loopback_network as loopback

    index_path, model, _manifest, _records, _root = generated_index
    certificate, private_key = _loopback_tls_files(tmp_path)
    reserved = _track_loopback_sockets(monkeypatch, loopback)
    real_http_client = loopback.http_client
    read_timeouts = []

    def track_http_client(origin, ca_file=None, *, read_timeout_seconds=2.0):
        read_timeouts.append(read_timeout_seconds)
        return real_http_client(origin, ca_file,
            read_timeout_seconds=read_timeout_seconds)

    monkeypatch.setattr(loopback, "http_client", track_http_client)
    import httpx
    monkeypatch.setattr(httpx, "MockTransport", lambda *_args, **_kwargs:
        pytest.fail("network qualification must use an actual provider TCP connection"))
    result = subject.measure(index_path, tmp_path / "network-output", model=model,
        queries=[{"id": "q1", "language": "zh-en", "text": "family dinner at home"}],
        network={"transport": "loopback_https_tcp", "certificate": certificate,
            "private_key": private_key, "ca_file": certificate})

    assert result["transport_boundary"] == "loopback_https_api_and_authenticated_tcp_provider_cpu"
    assert result["network_listener_started"] is True
    assert result["resources_closed"] is True
    assert result["model_encode_calls"] == result["provider_calls"] >= 2
    assert result["vector_reads"] > 0
    assert {
        "provider_bad_bearer_denied_before_model",
        "viewer_denied_before_model_and_vector_reads",
        "other_owner_denied_before_model_and_vector_reads",
        "invalid_denied_before_model_and_vector_reads",
        "three_language_exclusions_clarified_before_provider_and_vectors",
    } <= set(result["protected_checks"])
    assert len(reserved) == 2
    assert all(sock.fileno() == -1 for sock in reserved)
    assert read_timeouts == [2.0, 120.0]


def test_second_socket_reservation_failure_closes_first_and_preserves_fixture(
        generated_index, tmp_path, monkeypatch):
    import semantic_loopback_network as loopback

    index_path, model, _manifest, _records, _root = generated_index
    certificate, private_key = _loopback_tls_files(tmp_path)
    reserved = _track_loopback_sockets(monkeypatch, loopback)
    real_reserve = loopback.reserve_socket
    attempts = 0

    def reserve_then_fail():
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError("injected_second_reservation_failure")
        return real_reserve()

    monkeypatch.setattr(loopback, "reserve_socket", reserve_then_fail)
    output = tmp_path / "second-reservation-output"
    with pytest.raises(RuntimeError, match="injected_second_reservation_failure"):
        subject.measure(index_path, output, model=model,
            queries=[{"id": "q1", "language": "en", "text": "a quiet family garden"}],
            network={"transport": "loopback_https_tcp", "certificate": certificate,
                "private_key": private_key, "ca_file": certificate})

    assert attempts == 2
    assert len(reserved) == 1
    assert reserved[0].fileno() == -1
    assert (output / "synthetic.sqlite").is_file()
    assert not (output / "measurement.json").exists()
    assert model.bind_count == 0


def test_bind_failure_after_socket_reservation_closes_both_sockets_and_preserves_fixture(
        generated_index, tmp_path, monkeypatch):
    import semantic_loopback_network as loopback

    index_path, model, _manifest, _records, _root = generated_index
    certificate, private_key = _loopback_tls_files(tmp_path)
    reserved = _track_loopback_sockets(monkeypatch, loopback)
    model.raise_on_bind = True
    output = tmp_path / "bind-failure-output"

    with pytest.raises(RuntimeError, match="injected_model_bind_failure"):
        subject.measure(index_path, output, model=model,
            queries=[{"id": "q1", "language": "zh", "text": "花园里的家人"}],
            network={"transport": "loopback_https_tcp", "certificate": certificate,
                "private_key": private_key, "ca_file": certificate})

    assert len(reserved) == 2
    assert all(sock.fileno() == -1 for sock in reserved)
    assert (output / "synthetic.sqlite").is_file()
    assert not (output / "measurement.json").exists()
    assert model.bind_count == 0
    assert model.binding is None


def test_explicit_bulk_canary_keeps_protection_checks_and_old_vectors_unchanged(generated_index, tmp_path):
    index_path, model, manifest, records, vector_root = generated_index
    before = {record.relative_path: hashlib.sha256((vector_root / record.relative_path).read_bytes()).hexdigest()
              for record in records}
    result = subject.measure(index_path, tmp_path / 'bulk-canary', model=model,
        queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'}], bulk_vectors=True)
    assert result['vector_storage'] == 'pinned_bulk_v1'
    assert result['vector_reads'] == 0
    assert result['bulk_snapshot_calls'] > 0
    assert result['available_image_count'] == 515
    assert {
        'owner_revocation_denied_before_bulk_provider_or_vector_io_and_restore_succeeded',
        'soft_deleted_asset_refused_by_stale_bulk_cohort_before_inference',
        'scoped_artifact_removal_refused_by_stale_bulk_cohort_before_inference',
    } <= set(result['protected_checks'])
    assert result['activation_performed'] is False
    assert before == {record.relative_path: hashlib.sha256((vector_root / record.relative_path).read_bytes()).hexdigest()
                      for record in records}


def test_bulk_canary_rejects_an_injected_stale_cohort_serving_bug(generated_index, tmp_path,
        monkeypatch):
    index_path, model, _manifest, records, vector_root = generated_index
    index_hash = hashlib.sha256(index_path.read_bytes()).hexdigest()
    vector_hashes = {row.relative_path: hashlib.sha256(
        (vector_root / row.relative_path).read_bytes()).hexdigest() for row in records}
    original_snapshot = BulkVectorStore.snapshot
    good_snapshots = {}
    stale_acceptances = []

    def incorrectly_accept_stale_cohort(store, artifacts, **kwargs):
        try:
            snapshot = original_snapshot(store, artifacts, **kwargs)
        except BulkVectorUnavailable:
            # Simulate a serving regression that reuses a previously validated
            # full snapshot after the live cohort has changed.
            if store not in good_snapshots:
                raise
            stale_acceptances.append(True)
            return good_snapshots[store]
        good_snapshots[store] = snapshot
        return snapshot

    monkeypatch.setattr(BulkVectorStore, 'snapshot', incorrectly_accept_stale_cohort)
    with pytest.raises(subject.LibrarySemanticRefused,
            match='synthetic_asset_soft_delete_stale_bulk_cohort_reached_inference_or_released_cards'):
        subject.measure(index_path, tmp_path / 'stale-cohort-injection', model=model,
            queries=[{'id': 'en', 'language': 'en', 'text': 'a garden scene'}],
            bulk_vectors=True)
    assert stale_acceptances
    # The harness owns only its temporary synthetic DB and always restores the
    # source revision before it raises; the supplied index remains untouched.
    assert model.encode_count > 0
    assert all((vector_root / row.relative_path).is_file() for row in records)
    with sqlite3.connect(tmp_path / 'stale-cohort-injection' / 'synthetic.sqlite') as db:
        assert db.execute("SELECT status FROM assets WHERE id=1").fetchone() == ('active',)
        assert db.execute("SELECT status FROM access_memberships WHERE account_id='pilot-owner'").fetchone() == ('approved',)
        assert db.execute("SELECT count(*) FROM image_vector_artifacts WHERE status='ready'").fetchone() == (515,)
        assert db.execute("SELECT count(*) FROM access_asset_libraries WHERE asset_id=1").fetchone() == (1,)
    assert hashlib.sha256(index_path.read_bytes()).hexdigest() == index_hash
    assert vector_hashes == {row.relative_path: hashlib.sha256(
        (vector_root / row.relative_path).read_bytes()).hexdigest() for row in records}

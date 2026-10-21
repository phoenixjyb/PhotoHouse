"""Sanitized, provider-only semantic readiness checks."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import httpx
import pytest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "semantic_provider_readiness.py"
sys.path.insert(0, str(ROOT / "backend"))
spec = importlib.util.spec_from_file_location("semantic_provider_readiness", SCRIPT)
readiness = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(readiness)

from app.access.semantic_encoder import JointSpaceBinding
from app.access.discovery import ReadBudget
from app.access.discovery_transport import DiscoveryRuntime
from app.access.transport import AccessRuntime
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum


def _ident(artifact: str, preprocessing: str, model: str) -> VectorSpaceIdentity:
    return VectorSpaceIdentity(artifact, preprocessing, "photohouse-siglip2-v1",
                               model, 768, "unit_l2")


class ReadinessFixture:
    def __init__(self, root: Path):
        self.root = root
        self.config = root / "semantic.json"
        self.credential = root / "credential.json"
        self.vectors = root / "vectors"
        self.vectors.mkdir(mode=0o700)
        image = _ident("a" * 64, "b" * 64, "siglip2-image-v1")
        text = _ident("c" * 64, "d" * 64, "siglip2-text-v1")
        self.binding = JointSpaceBinding(image, text, "e" * 64)
        self.document = {
            "format_version": 2,
            "pilot_owner_account_id": "readiness-owner",
            "vector_root": str(self.vectors),
            "encoder_url": "http://127.0.0.1:43210/v1/encode-text",
            "encoder_timeout_seconds": 1.5,
            "credential_file": str(self.credential),
            "binding": {"image_identity": asdict(image), "text_identity": asdict(text),
                        "qualification_sha256": "e" * 64},
            "binding_sha256": self.binding.binding_sha256,
            "operator_reviewed": True,
        }
        self.write_config()
        self.write_credential()

    def write_config(self, document=None):
        payload = json.dumps(self.document if document is None else document,
                             sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        self.config.write_text(payload, encoding="utf-8")
        self.config.chmod(0o600)

    def write_credential(self, token="a" * 40):
        self.credential.write_text(json.dumps({"token": token}), encoding="utf-8")
        self.credential.chmod(0o600)

    @property
    def pin(self):
        canonical = json.dumps(self.document, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False, allow_nan=False).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


def _success(binding, vector=None, **changes):
    vector = [1.0] + [0.0] * 767 if vector is None else vector
    payload = {"version": 1, "binding_sha256": binding.binding_sha256,
               "query_sha256": hashlib.sha256(readiness.SYNTHETIC_QUERY.encode()).hexdigest(),
               "vector": vector, "checksum_sha256": canonical_vector_checksum(vector)}
    payload.update(changes)
    return httpx.Response(200, json=payload)


def _mock_client(handler):
    real_client = httpx.Client

    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    return patch("httpx.Client", side_effect=client)


def _run(fixture, pin=None):
    return readiness._check(fixture.config, fixture.pin if pin is None else pin)


def test_no_argument_plan_does_not_import_runtime_or_read_private_files(capsys):
    with patch("builtins.__import__", side_effect=AssertionError("unexpected import")):
        assert readiness.main([]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "plan_only"
    assert report["private_file_reads"] is False
    assert report["network_requests"] is False
    assert report["activation"] is False


def test_wrong_pin_refuses_before_loading_credentials_or_transport(tmp_path):
    fixture = ReadinessFixture(tmp_path)
    with patch("app.access.semantic_configuration.load_semantic_runtime",
               side_effect=AssertionError("credential must not load")) as loader, \
            patch("httpx.Client", side_effect=AssertionError("network must not start")):
        with pytest.raises(readiness.Refused) as refused:
            _run(fixture, "0" * 64)
    assert refused.value.code == "config_pin_mismatch"
    loader.assert_not_called()


def test_cli_pin_refusal_is_exactly_sanitized(tmp_path, capsys):
    fixture = ReadinessFixture(tmp_path)
    result = readiness.main(["--check", "--config", str(fixture.config),
                             "--config-sha256", "0" * 64])
    captured = capsys.readouterr()
    assert result == 2
    assert captured.err == ""
    assert captured.out == '{"error":"config_pin_mismatch","status":"refused","version":1}\n'
    assert str(fixture.config) not in captured.out
    assert "credential" not in captured.out


def test_success_is_one_fixed_authenticated_encode_and_sanitized(tmp_path, capsys):
    fixture = ReadinessFixture(tmp_path)
    seen = []

    def handle(request):
        seen.append(request)
        return _success(fixture.binding)

    with _mock_client(handle):
        result = readiness.main(["--check", "--config", str(fixture.config),
                                 "--config-sha256", fixture.pin])
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    encoded = captured.out
    assert result == 0
    assert captured.err == ""
    assert report["status"] == "ready"
    assert report["scope"] == "provider_only_synthetic_protocol_check"
    assert report["inference_requests"] == 1
    assert report["library_authorized"] is False
    assert report["index_or_policy_audited"] is False
    assert report["activation"] is False
    assert report["query_sha256"] == readiness.SYNTHETIC_QUERY_SHA256
    assert report["checksum_validated"] is True
    assert set(report) == {"version", "status", "scope", "config_sha256", "binding_sha256",
                           "query_sha256", "checksum_validated", "dimension",
                           "inference_requests", "library_authorized",
                           "index_or_policy_audited", "activation", "service_management"}
    assert len(seen) == 1
    body = json.loads(seen[0].content)
    assert body == {"version": 1, "binding_sha256": fixture.binding.binding_sha256,
                    "query": readiness.SYNTHETIC_QUERY}
    assert seen[0].url == "http://127.0.0.1:43210/v1/encode-text"
    assert seen[0].headers["authorization"] == "Bearer " + "a" * 40
    assert ("a" * 40) not in encoded
    assert "43210" not in encoded
    assert readiness.SYNTHETIC_QUERY not in encoded
    assert "vector" not in encoded
    assert str(fixture.config) not in encoded


@pytest.mark.parametrize("response_factory", [
    lambda fixture: httpx.Response(422, json={"version": 1, "error": "unsupported_query",
        "binding_sha256": fixture.binding.binding_sha256,
        "query_sha256": hashlib.sha256(readiness.SYNTHETIC_QUERY.encode()).hexdigest()}),
    lambda fixture: _success(fixture.binding, binding_sha256="0" * 64),
    lambda fixture: _success(fixture.binding, checksum_sha256="0" * 64),
])
def test_unsupported_or_invalid_protocol_reply_never_reports_ready(tmp_path, response_factory):
    fixture = ReadinessFixture(tmp_path)
    with _mock_client(lambda _request: response_factory(fixture)):
        with pytest.raises(readiness.Refused) as refused:
            _run(fixture)
    assert refused.value.code in {"provider_unsupported", "provider_unavailable"}


def test_timeout_is_redacted_and_never_reports_ready(tmp_path):
    fixture = ReadinessFixture(tmp_path)

    def timeout(_request):
        raise httpx.ReadTimeout("secret endpoint and token detail")

    with _mock_client(timeout):
        with pytest.raises(readiness.Refused) as refused:
            _run(fixture)
    assert refused.value.code == "provider_unavailable"
    assert "secret" not in str(refused.value)


@pytest.mark.parametrize("mutation", ["config", "credential"])
def test_config_or_credential_change_during_exchange_refuses_ready(tmp_path, mutation):
    fixture = ReadinessFixture(tmp_path)

    def change_then_succeed(_request):
        if mutation == "config":
            fixture.write_config(fixture.document | {"encoder_timeout_seconds": 1.4})
        else:
            fixture.write_credential("b" * 40)
        return _success(fixture.binding)

    with _mock_client(change_then_succeed):
        with pytest.raises(readiness.Refused) as refused:
            _run(fixture)
    expected = "config_pin_mismatch" if mutation == "config" else "runtime_changed"
    assert refused.value.code == expected


def test_loader_race_from_pinned_document_a_to_runtime_document_b_is_refused(tmp_path):
    fixture = ReadinessFixture(tmp_path)
    changed = fixture.document | {"encoder_timeout_seconds": 1.4}
    calls = []

    def loader(path, *, source_root):
        calls.append((path, source_root))
        return changed

    with patch("app.access.semantic_configuration._load_private_document", side_effect=loader), \
            patch("httpx.Client", side_effect=AssertionError("transport must not start")):
        with pytest.raises(readiness.Refused) as refused:
            _run(fixture)
    assert refused.value.code == "readiness_unavailable"
    # The CLI's outer pin read sees A. The loader sees B and rejects it before
    # asking the same private-document reader for the credential file.
    assert len(calls) == 1


def test_inert_discovery_never_opens_database_or_reads_index(tmp_path):
    fixture = ReadinessFixture(tmp_path)
    calls = []

    def refuse_connection():
        calls.append("db")
        raise AssertionError("readiness must not open the database")

    class EmptyProvider:
        def get(self, _library):
            calls.append("index")
            return None

    discovery = DiscoveryRuntime(AccessRuntime(refuse_connection, "https://readiness.invalid"),
                                 EmptyProvider(), ReadBudget())
    with patch.object(readiness, "_inert_discovery", return_value=discovery):
        with _mock_client(lambda _request: _success(fixture.binding)):
            report = _run(fixture)
    assert report["status"] == "ready"
    assert calls == []

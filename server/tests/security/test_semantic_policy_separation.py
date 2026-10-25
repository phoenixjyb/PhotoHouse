"""R134 red coverage for policy-3 reachability beyond semantic search.

Generated providers, private test configuration and synthetic image bytes only;
no model, host, or external network is involved.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
import httpx
from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.access.search_policy import requires_semantic_clarification  # noqa: E402
from app.access.search_policy_binding import (  # noqa: E402
    QueryPolicyUnavailable,
    capture_current_query_policy_binding,
    verify_query_policy_binding,
)
import app.access.search_policy_binding as policy_binding_module  # noqa: E402
from app.access.semantic_encoder import (  # noqa: E402
    JointSpaceBinding, LocalSemanticEncoder, SemanticUnavailable, SemanticUnsupported, TextVector,
)
from app.access.semantic_provider_transport import create_provider_app  # noqa: E402
from app.access.visual_candidates import (  # noqa: E402
    VectorSpaceIdentity,
    canonical_vector_checksum,
)
from semantic_openclip import OpenClipTextModel  # noqa: E402
from semantic_siglip import SiglipModel  # noqa: E402
from semantic_reviewed_projection import (  # noqa: E402
    ReviewedProjection,
    ReviewedSemanticProvider,
    reviewed_document_sha256,
)
import qualify_multilingual_scenes as multilingual  # noqa: E402


TOKEN = "r134-generated-provider-credential-" + "t" * 32
QUERIES = ("people omitting hats", "除了戴帽子的人")


def test_policy_binding_is_separate_from_the_unchanged_encoder_receipt():
    binding = capture_current_query_policy_binding()
    assert binding["schema"] == "photohouse.semantic_query_policy_binding.v1"
    assert binding["policy_version"] == 3
    assert binding["policy_source_sha256"] == "cb7aeb07d6e1642de82acd764ad089e46471d1d9cb589e5fd8ab2b4ac6ec4444"
    assert binding["public_guard_source_sha256"] == hashlib.sha256(
        (ROOT / "scripts" / "semantic_siglip.py").read_bytes()).hexdigest()
    assert hashlib.sha256((ROOT / "scripts" / "_semantic_siglip_encoding.py").read_bytes()).hexdigest() == (
        "22419b729d665f43c99e75eb4587a5f4540bcf0e8f1a8ede24b45aba2101e489"
    )
    assert hashlib.sha256((ROOT / "backend" / "app" / "access" / "search_exclusions.py").read_bytes()).hexdigest() == (
        "248e8722470ae6e5b1f95b5b8dced59dc1353af234a9d380fcaef6310f18017d"
    )
    assert verify_query_policy_binding(binding) == binding
    class KeyAlias(str):
        pass

    for mutated in (
        {**binding, "policy_version": 4},
        {**binding, "policy_version": 3.0},
        {**binding, "policy_version": True},
        {**binding, "binding_sha256": "0" * 64},
        {**binding, "unexpected": 1},
        {key: value for key, value in binding.items() if key != "binding_sha256"},
        {KeyAlias(key): value for key, value in binding.items()},
    ):
        with pytest.raises(QueryPolicyUnavailable):
            verify_query_policy_binding(mutated)


def test_policy_binding_refuses_changed_policy_or_public_guard_sources(tmp_path, monkeypatch):
    policy_path = tmp_path / "search_policy.py"
    policy_path.write_bytes(policy_binding_module._POLICY_PATH.read_bytes() + b"\n# changed\n")
    monkeypatch.setattr(policy_binding_module, "_POLICY_PATH", policy_path)
    with pytest.raises(QueryPolicyUnavailable):
        capture_current_query_policy_binding()
    monkeypatch.undo()

    guard_path = tmp_path / "semantic_siglip.py"
    guard_path.write_bytes(policy_binding_module._PUBLIC_GUARD_PATH.read_bytes() + b"\n# changed\n")
    monkeypatch.setattr(policy_binding_module, "_PUBLIC_GUARD_PATH", guard_path)
    with pytest.raises(QueryPolicyUnavailable):
        capture_current_query_policy_binding()


def _redirect_policy_binding_to_generated_files(tmp_path, monkeypatch):
    policy_path = (tmp_path.resolve() / "search_policy.py")
    guard_path = (tmp_path.resolve() / "semantic_siglip.py")
    policy_path.write_bytes(policy_binding_module._POLICY_PATH.read_bytes())
    guard_path.write_bytes(policy_binding_module._PUBLIC_GUARD_PATH.read_bytes())
    policy_path.chmod(0o600)
    guard_path.chmod(0o600)
    expected = policy_binding_module._capture(
        policy_path, guard_path, policy_binding_module._HERE,
        expected_policy_sha256=policy_binding_module.EXPECTED_POLICY_SOURCE_SHA256,
    )
    monkeypatch.setattr(policy_binding_module, "_POLICY_PATH", policy_path)
    monkeypatch.setattr(policy_binding_module, "_PUBLIC_GUARD_PATH", guard_path)
    monkeypatch.setattr(policy_binding_module, "_PROCESS_BINDING", expected)
    return policy_path, guard_path, expected


def _binding() -> JointSpaceBinding:
    image = VectorSpaceIdentity("a" * 64, "b" * 64, "generated-r134", "image-v1", 2, "unit_l2")
    text = VectorSpaceIdentity("c" * 64, "d" * 64, "generated-r134", "text-v1", 2, "unit_l2")
    return JointSpaceBinding(image, text, "e" * 64)


class PermissiveGeneratedProvider:
    """A correctly bound provider that returns a valid vector for every query."""

    def __init__(self):
        self.binding = _binding()
        self.calls: list[str] = []

    def encode(self, query: str, *, check=lambda: None) -> TextVector:
        check()
        self.calls.append(query)
        vector = (1.0, 0.0)
        return TextVector(
            self.binding.binding_sha256,
            hashlib.sha256(query.encode("utf-8")).hexdigest(),
            vector,
            canonical_vector_checksum(vector),
        )


@pytest.mark.parametrize("query", QUERIES)
def test_authenticated_provider_route_refuses_policy3_query_before_provider_call(query):
    assert requires_semantic_clarification(query), "fixture must hit policy-3 negative grammar"
    provider = PermissiveGeneratedProvider()
    app = create_provider_app(provider, bearer_token=TOKEN, port=43891)
    with TestClient(app, base_url="http://127.0.0.1:43891", client=("127.0.0.1", 51000)) as client:
        payload = {"version": 1, "binding_sha256": provider.binding.binding_sha256,
                   "query": query}
        response = client.post("/v1/encode-text", json=payload, headers={
            "authorization": f"Bearer {TOKEN}",
            "x-photohouse-semantic-refusal": "1",
        })
        assert response.status_code == 422
        assert response.json() == {
            "version": 1,
            "error": "unsupported_query",
            "binding_sha256": provider.binding.binding_sha256,
            "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
        }
        # A product caller cannot select the private diagnostic purpose with a
        # query/header. Unsupported requests remain unavailable without the
        # explicit refusal protocol header, and never invoke the provider.
        response = client.post("/v1/encode-text", json=payload, headers={
            "authorization": f"Bearer {TOKEN}",
            "x-photohouse-semantic-purpose": "diagnostic",
        })
    assert provider.calls == [], "policy-3 route reached the bound provider"
    assert response.status_code == 503
    assert response.json() == {"error": "provider_unavailable"}


@pytest.mark.parametrize("status", [200, 422])
def test_local_encoder_rejects_provider_result_when_policy_changes_in_response(
        status, tmp_path, monkeypatch):
    _policy_path, guard_path, _expected = _redirect_policy_binding_to_generated_files(
        tmp_path, monkeypatch)
    original_guard = guard_path.read_bytes()
    changed = {"done": False}
    calls = []
    binding = _binding()
    vector = (1.0, 0.0)

    def respond(request):
        calls.append(request)
        query = json.loads(request.content)["query"]
        if not changed["done"]:
            guard_path.write_bytes(original_guard + b"\n# changed during provider response\n")
            changed["done"] = True
        if status == 422:
            payload = {"version": 1, "error": "unsupported_query",
                "binding_sha256": binding.binding_sha256,
                "query_sha256": hashlib.sha256(query.encode()).hexdigest()}
            return httpx.Response(422, json=payload,
                headers={"content-type": "application/json"})
        payload = {"version": 1, "binding_sha256": binding.binding_sha256,
            "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
            "vector": list(vector), "checksum_sha256": canonical_vector_checksum(vector)}
        return httpx.Response(200, json=payload,
            headers={"content-type": "application/json"})

    encoder = LocalSemanticEncoder(binding, "http://127.0.0.1:43893/v1/encode-text",
                                   transport=httpx.MockTransport(respond))
    with pytest.raises(SemanticUnavailable):
        encoder.encode("a quiet family garden")
    assert len(calls) == 1

    guard_path.write_bytes(original_guard)
    if status == 422:
        with pytest.raises(SemanticUnsupported):
            encoder.encode("a quiet family garden")
    else:
        result = encoder.encode("a quiet family garden")
        assert result.vector == vector
    assert len(calls) == 2


@pytest.mark.parametrize("outcome", ["vector", "unsupported"])
def test_provider_route_rejects_result_or_refusal_when_policy_changes_during_encode(
        outcome, tmp_path, monkeypatch):
    _policy_path, guard_path, _expected = _redirect_policy_binding_to_generated_files(
        tmp_path, monkeypatch)
    original_guard = guard_path.read_bytes()
    changed = {"done": False}
    vector = (1.0, 0.0)

    class DriftingProvider:
        def __init__(self):
            self.binding = _binding()
            self.calls = 0

        def encode(self, query, *, check=lambda: None):
            check()
            self.calls += 1
            if not changed["done"]:
                guard_path.write_bytes(original_guard + b"\n# changed during provider encode\n")
                changed["done"] = True
            if outcome == "unsupported":
                raise SemanticUnsupported()
            return TextVector(self.binding.binding_sha256,
                hashlib.sha256(query.encode()).hexdigest(), vector,
                canonical_vector_checksum(vector))

    provider = DriftingProvider()
    app = create_provider_app(provider, bearer_token=TOKEN, port=43894)
    payload = {"version": 1, "binding_sha256": provider.binding.binding_sha256,
               "query": "a quiet family garden"}
    headers = {"authorization": f"Bearer {TOKEN}",
               "x-photohouse-semantic-refusal": "1"}
    with TestClient(app, base_url="http://127.0.0.1:43894",
                    client=("127.0.0.1", 51001)) as client:
        response = client.post("/v1/encode-text", json=payload, headers=headers)
        assert response.status_code == 503
        assert response.json() == {"error": "provider_unavailable"}
        assert provider.calls == 1
        guard_path.write_bytes(original_guard)
        response = client.post("/v1/encode-text", json=payload, headers=headers)
        if outcome == "unsupported":
            assert response.status_code == 422
            assert response.json()["error"] == "unsupported_query"
        else:
            assert response.status_code == 200
            assert response.json()["vector"] == list(vector)
        assert provider.calls == 2


@pytest.mark.parametrize("query", QUERIES)
def test_supported_public_siglip_encode_admits_policy3_before_model_work(query):
    model = object.__new__(SiglipModel)
    model._query_policy_binding = capture_current_query_policy_binding()
    assert model.query_policy_binding["policy_version"] == 3
    with pytest.raises(SemanticUnsupported):
        model.encode(query)


@pytest.mark.parametrize("query", QUERIES)
def test_supported_public_openclip_encode_admits_policy3_before_model_work(query):
    model = object.__new__(OpenClipTextModel)
    model._query_policy_binding = capture_current_query_policy_binding()
    model._binding = _binding()
    model._lock = __import__("threading").Lock()
    model._vector = lambda *_args: pytest.fail("policy refusal reached OpenCLIP model work")
    assert model.query_policy_binding["policy_version"] == 3
    with pytest.raises(SemanticUnsupported):
        model.encode(query)


@pytest.mark.parametrize("query", QUERIES)
def test_supported_local_encoder_admits_policy3_before_http_transport(query):
    calls = []
    encoder = LocalSemanticEncoder(
        _binding(), "http://127.0.0.1:43892/v1/encode-text",
        transport=httpx.MockTransport(lambda request: calls.append(request) or
            pytest.fail("policy refusal reached provider transport")),
    )
    assert encoder.query_policy_binding["policy_version"] == 3
    with pytest.raises(SemanticUnsupported):
        encoder.encode(query)
    assert calls == []


@pytest.mark.parametrize("query", QUERIES)
def test_reviewed_provider_policy3_refusal_precedes_projection_and_inner_encode(query):
    inner_binding = _binding()
    original = query
    mapped = "a family in a garden"
    document = {
        "schema": "photohouse.reviewed_scene_projection.v1",
        "policy": "exact_reviewed_only",
        "review": {"status": "operator_reviewed", "reference_sha256": "f" * 64},
        "entries": [{"original": original, "model_input": mapped}],
    }
    projection = ReviewedProjection(document, expected_sha256=reviewed_document_sha256(document))
    from semantic_reviewed_projection import composition_recipe
    recipe = composition_recipe(inner_binding, projection, "a" * 64)
    from dataclasses import replace
    expected_text = replace(inner_binding.text_identity,
        preprocessing_sha256=recipe["recipe_sha256"])
    outer = JointSpaceBinding(inner_binding.image_identity, expected_text, "b" * 64)

    class Inner:
        binding = inner_binding

        def encode(self, *_args, **_kwargs):
            pytest.fail("policy refusal reached reviewed inner encoder")

    provider = ReviewedSemanticProvider(Inner(), projection, outer,
                                       adapter_source_sha256="a" * 64)
    assert provider.query_policy_binding["policy_version"] == 3
    assert provider.probe()["query_policy_binding"] == provider.query_policy_binding
    with pytest.raises(SemanticUnsupported):
        provider.encode(query)


def _write_private_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    path.chmod(0o600)


def _generated_cli_fixture(root: Path):
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    model_dir = root / "generated-model-directory"
    model_dir.mkdir(mode=0o700)
    model_dir.chmod(0o700)

    image_rows = []
    for index in range(1, 5):
        path = root / f"synthetic-image-{index}.png"
        color = (index * 31, index * 47, index * 59)
        Image.new("RGB", (8, 8), color).save(path, format="PNG", optimize=False)
        path.chmod(0o600)
        with Image.open(path) as generated:
            generated.verify()
        payload = path.read_bytes()
        image_rows.append({"id": f"image-{index}", "path": str(path),
                           "sha256": hashlib.sha256(payload).hexdigest()})

    queries = {"en": QUERIES[0], "zh": QUERIES[1], "zh-en": "people 除了戴帽子的人"}
    scenes = {
        "schema": "photohouse.semantic_scene_cases.v1",
        "review": {"natural_scenes": True, "labels_reviewed": True},
        "images": image_rows,
        "cases": [
            {"id": f"case-{case}", "relevant_images": ["image-1"], "queries": queries}
            for case in (1, 2)
        ],
    }
    # Real validators and image-file hashing run against these private files.
    normalized = multilingual.validate_dataset(scenes)
    assert normalized["review"] == {"natural_scenes": True, "labels_reviewed": True}
    for query in normalized["cases"][0]["queries"].values():
        assert requires_semantic_clarification(query)

    labels = {
        "schema": "photohouse.semantic_exclusion_cases.v1",
        "images": [row["id"] for row in image_rows],
        "cases": [
            {"id": case["id"], "relevant_images": list(case["relevant_images"]),
             "forbidden_images": ["image-2"], "queries": dict(case["queries"])}
            for case in scenes["cases"]
        ],
    }
    envelope = {"schema": "photohouse.multilingual_exclusion_labels.v1",
                "scene_dataset_sha256": multilingual.dataset_sha256(scenes),
                "dataset": labels}
    config = {
        "schema": "photohouse.multilingual_scene_run.v1",
        "model_directory": str(model_dir.resolve()),
        "artifacts": multilingual.OFFICIAL_ARTIFACTS,
        "package_versions": multilingual.EXPECTED_PACKAGES,
        "dataset": str((root / "scene-dataset.private.json").resolve()),
        "max_elapsed_seconds": 30,
    }
    config_path = root / "configuration.private.json"
    dataset_path = root / "scene-dataset.private.json"
    exclusion_path = root / "exclusion-labels.private.json"
    _write_private_json(config_path, config)
    _write_private_json(dataset_path, scenes)
    _write_private_json(exclusion_path, envelope)
    return config_path, exclusion_path


def test_explicit_private_diagnostic_cli_remains_reachable_for_policy3_cases(
        tmp_path, monkeypatch, capsys):
    fixture_root = tmp_path.resolve() / "r134-generated-private-fixture"
    config_path, exclusion_path = _generated_cli_fixture(fixture_root)
    stages = {"configuration": 0, "image_files": 0, "exclusions": 0}
    loader_calls = []

    original_configuration = multilingual.configuration
    def observed_configuration(path):
        result = original_configuration(path)
        stages["configuration"] += 1
        assert result[2]["review"] == {"natural_scenes": True, "labels_reviewed": True}
        assert result[2]["cases"][0]["queries"] == {
            "en": QUERIES[0], "zh": QUERIES[1], "zh-en": "people 除了戴帽子的人"}
        return result

    original_inspect_images = multilingual.inspect_images
    def observed_inspect_images(dataset):
        pins = original_inspect_images(dataset)
        stages["image_files"] += 1
        assert set(pins) == {f"image-{index}" for index in range(1, 5)}
        return pins

    original_bind_exclusions = multilingual.bind_exclusions
    def observed_bind_exclusions(dataset, envelope):
        result = original_bind_exclusions(dataset, envelope)
        stages["exclusions"] += 1
        return result

    def sentinel_model_loader(*args, **kwargs):
        loader_calls.append((args, kwargs))
        raise RuntimeError("generated diagnostic loader sentinel")

    original_execute = multilingual.execute
    def execute_with_sentinel(*args, **kwargs):
        kwargs["model_loader"] = sentinel_model_loader
        return original_execute(*args, **kwargs)

    monkeypatch.setattr(multilingual, "configuration", observed_configuration)
    monkeypatch.setattr(multilingual, "inspect_images", observed_inspect_images)
    monkeypatch.setattr(multilingual, "bind_exclusions", observed_bind_exclusions)
    monkeypatch.setattr(multilingual, "installed_versions", lambda: multilingual.EXPECTED_PACKAGES)
    monkeypatch.setattr(multilingual, "inspect_model_files",
                        lambda _directory, _artifacts: {name: object() for name in multilingual.MODEL_FILES})
    monkeypatch.setattr(multilingual, "execute", execute_with_sentinel)

    result = multilingual.run([
        "--run", "--configuration", str(config_path),
        "--output-directory", str(fixture_root / "output"),
        "--exclusion-dataset", str(exclusion_path),
    ])
    captured = capsys.readouterr()
    assert result == 2
    assert captured.out == ""
    assert json.loads(captured.err) == {"error": "multilingual_scene_measurement_unavailable"}
    assert stages == {"configuration": 1, "image_files": 1, "exclusions": 1}
    assert len(loader_calls) == 1, "explicit private diagnostic CLI was unexpectedly disabled"
    args, kwargs = loader_calls[0]
    assert kwargs == {}
    assert args[0] == fixture_root / "generated-model-directory"
    assert set(args[1]) == set(multilingual.MODEL_FILES)
    assert args[2] == multilingual.EXPECTED_PACKAGES

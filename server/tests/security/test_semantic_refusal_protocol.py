"""Exact, opt-in semantic refusal protocol tests.

All provider and encoder calls use in-process ASGI or HTTPX transports. No model,
socket, network service, or external runtime is involved.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.access.semantic_encoder import (  # noqa: E402
    JointSpaceBinding,
    LocalSemanticEncoder,
    SemanticUnsupported,
    SemanticUnavailable,
    TextVector,
)
from app.access.semantic_provider_transport import create_provider_app  # noqa: E402
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum  # noqa: E402
from semantic_reviewed_projection import (  # noqa: E402
    ReviewedProjection,
    ReviewedSemanticProvider,
    composition_recipe,
    reviewed_document_sha256,
)


QUERY = "blue sky"
TOKEN = "synthetic_protocol_token_" + "x" * 32


@pytest.fixture
def binding():
    image = VectorSpaceIdentity("a" * 64, "b" * 64, "shared-v1", "image-v1", 2, "unit_l2")
    text = VectorSpaceIdentity("c" * 64, "d" * 64, "shared-v1", "text-v1", 2, "unit_l2")
    return JointSpaceBinding(image, text, "e" * 64)


def refusal(binding, query=QUERY, **changes):
    body = {
        "version": 1,
        "error": "unsupported_query",
        "binding_sha256": binding.binding_sha256,
        "query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
    }
    body.update(changes)
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def make_encoder(binding, handler, **kwargs):
    return LocalSemanticEncoder(
        binding,
        "http://127.0.0.1:8912/v1/encode-text",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_encoder_sends_refusal_opt_in_and_accepts_exact_refusal(binding):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(422, headers={"content-type": "application/json; charset=utf-8"},
                              content=refusal(binding))

    with pytest.raises(SemanticUnsupported) as raised:
        make_encoder(binding, handler).encode(QUERY)
    assert str(raised.value) == "semantic_query_unsupported"
    assert len(seen) == 1
    assert seen[0].headers.get_list("x-photohouse-semantic-refusal") == ["1"]
    assert json.loads(seen[0].content) == {
        "version": 1, "binding_sha256": binding.binding_sha256, "query": QUERY,
    }


@pytest.mark.parametrize("status", [400, 401, 403, 408, 429, 500, 503])
def test_encoder_keeps_other_statuses_unavailable(binding, status):
    with pytest.raises(SemanticUnavailable) as raised:
        make_encoder(binding, lambda _request: httpx.Response(status, content=refusal(binding))).encode(QUERY)
    assert type(raised.value) is SemanticUnavailable
    assert str(raised.value) == "semantic_unavailable"


@pytest.mark.parametrize("body", [
    lambda b: refusal(b, binding_sha256="0" * 64),
    lambda b: refusal(b, query_sha256="0" * 64),
    lambda b: refusal(b, error="provider_unavailable"),
    lambda b: refusal(b, version=True),
    lambda b: refusal(b, version=2),
    lambda b: refusal(b, extra="no"),
    lambda b: refusal(b)[:-1] + b',"version":1}',
    lambda b: b"\xff",
])
def test_encoder_rejects_tampered_or_noncanonical_refusal_body(binding, body):
    with pytest.raises(SemanticUnavailable) as raised:
        make_encoder(binding, lambda _request: httpx.Response(
            422, headers={"content-type": "application/json"}, content=body(binding))).encode(QUERY)
    assert type(raised.value) is SemanticUnavailable
    assert str(raised.value) == "semantic_unavailable"


@pytest.mark.parametrize("headers", [
    {"content-type": "text/plain"},
    {"content-type": "application/json", "content-encoding": "gzip"},
])
def test_encoder_rejects_wrong_refusal_content_metadata(binding, headers):
    with pytest.raises(SemanticUnavailable):
        make_encoder(binding, lambda _request: httpx.Response(
            422, headers=headers, content=refusal(binding))).encode(QUERY)


def test_encoder_rejects_oversized_refusal_body(binding):
    with pytest.raises(SemanticUnavailable):
        make_encoder(binding, lambda _request: httpx.Response(
            422, headers={"content-type": "application/json"},
            content=refusal(binding) + b" " * (64 * 1024))).encode(QUERY)


def test_encoder_caller_check_and_deadline_suppress_refusal(binding):
    class Cancelled(Exception):
        pass

    with pytest.raises(Cancelled, match="cancelled"):
        make_encoder(binding, lambda _request: httpx.Response(
            422, headers={"content-type": "application/json"}, content=refusal(binding)))\
            .encode(QUERY, check=lambda: (_ for _ in ()).throw(Cancelled("cancelled")))

    times = iter((0.0, 0.0, 0.0, 2.1))
    with pytest.raises(SemanticUnavailable):
        make_encoder(binding, lambda _request: httpx.Response(
            422, headers={"content-type": "application/json"}, content=refusal(binding)),
            monotonic=lambda: next(times)).encode(QUERY)


class _FakeProvider:
    def __init__(self, binding):
        self.binding = binding
        self.calls = []
        self.mode = "unsupported"
        self.delay = 0.0
        self.change_binding = False

    def encode(self, query, *, check=lambda: None):
        self.calls.append(query)
        check()
        if self.delay:
            time.sleep(self.delay)
        if self.change_binding:
            self.binding = None
        if self.mode == "unsupported":
            raise SemanticUnsupported()
        if self.mode == "unavailable":
            raise RuntimeError("private provider detail")
        vector = (1.0, 0.0)
        return TextVector(self.binding.binding_sha256,
                          hashlib.sha256(query.encode("utf-8")).hexdigest(),
                          vector, canonical_vector_checksum(vector))


@pytest.fixture
def provider_client(binding):
    provider = _FakeProvider(binding)
    app = create_provider_app(provider, bearer_token=TOKEN, port=8912, seconds=0.2)
    client = TestClient(app, base_url="http://127.0.0.1:8912", client=("127.0.0.1", 50000))
    try:
        yield provider, client
    finally:
        client.close()


def provider_request(client, binding, *, headers=(), payload=None):
    merged = [("authorization", "Bearer " + TOKEN),
              ("content-type", "application/json"), *headers]
    body = payload if payload is not None else json.dumps({
        "version": 1, "binding_sha256": binding.binding_sha256, "query": QUERY,
    })
    return client.post("/v1/encode-text", headers=merged, content=body)


def test_provider_refusal_is_closed_and_requires_exact_opt_in(provider_client, binding):
    provider, client = provider_client
    opted_in = provider_request(client, binding, headers=[("x-photohouse-semantic-refusal", "1")])
    assert opted_in.status_code == 422
    assert opted_in.json() == {
        "version": 1,
        "error": "unsupported_query",
        "binding_sha256": binding.binding_sha256,
        "query_sha256": hashlib.sha256(QUERY.encode()).hexdigest(),
    }
    no_opt_in = provider_request(client, binding)
    assert no_opt_in.status_code == 503
    assert no_opt_in.json() == {"error": "provider_unavailable"}
    assert provider.calls == [QUERY, QUERY]


@pytest.mark.parametrize("values", [["0"], ["1", "1"], ["true"], [""]])
def test_provider_rejects_malformed_or_duplicate_opt_in(provider_client, binding, values):
    _provider, client = provider_client
    response = provider_request(client, binding,
                                headers=[("x-photohouse-semantic-refusal", value) for value in values])
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_request"}


def test_provider_authorizes_before_call_and_preserves_generic_failures(provider_client, binding):
    provider, client = provider_client
    unauthorized = client.post("/v1/encode-text", headers=[
        ("authorization", "Bearer " + "z" * 40),
        ("content-type", "application/json"), ("x-photohouse-semantic-refusal", "1")],
        json={"version": 1, "binding_sha256": binding.binding_sha256, "query": QUERY})
    assert unauthorized.status_code == 401
    assert provider.calls == []

    provider.mode = "unavailable"
    generic = provider_request(client, binding, headers=[("x-photohouse-semantic-refusal", "1")])
    assert generic.status_code == 503
    assert generic.json() == {"error": "provider_unavailable"}


def test_provider_suppresses_refusal_after_binding_change_or_deadline(provider_client, binding):
    provider, client = provider_client
    provider.change_binding = True
    changed = provider_request(client, binding, headers=[("x-photohouse-semantic-refusal", "1")])
    assert changed.status_code == 503
    assert changed.json() == {"error": "provider_unavailable"}

    provider.binding = binding
    provider.change_binding = False
    provider.delay = 0.25
    timed_out = provider_request(client, binding,
                                 headers=[("x-photohouse-semantic-refusal", "1")])
    assert timed_out.status_code == 504
    assert timed_out.json() == {"error": "request_timeout"}


def test_provider_lease_recovers_after_failure(provider_client, binding):
    provider, client = provider_client
    failed = provider_request(client, binding, headers=[("x-photohouse-semantic-refusal", "1")])
    assert failed.status_code == 422
    provider.mode = "ok"
    recovered = provider_request(client, binding,
                                headers=[("x-photohouse-semantic-refusal", "1")])
    assert recovered.status_code == 200
    assert recovered.json()["version"] == 1


def test_reviewed_unknown_source_does_not_become_an_unsupported_refusal(binding):
    document = {
        "schema": "photohouse.reviewed_scene_projection.v1",
        "policy": "exact_reviewed_only",
        "review": {"status": "operator_reviewed", "reference_sha256": "f" * 64},
        "entries": [{"original": "reviewed phrase", "model_input": "blue sky"}],
    }
    projection = ReviewedProjection(document, expected_sha256=reviewed_document_sha256(document))
    recipe = composition_recipe(binding, projection, "9" * 64)
    outer_text = VectorSpaceIdentity("c" * 64, recipe["recipe_sha256"], "shared-v1",
                                     "text-v1", 2, "unit_l2")
    outer_binding = JointSpaceBinding(binding.image_identity, outer_text, "8" * 64)
    inner = _FakeProvider(binding)
    reviewed = ReviewedSemanticProvider(inner, projection, outer_binding,
                                        adapter_source_sha256="9" * 64,
                                        source_check=lambda: (_ for _ in ()).throw(RuntimeError("stale source")))
    with pytest.raises(SemanticUnavailable) as raised:
        reviewed.encode("unreviewed query")
    assert type(raised.value) is SemanticUnavailable
    assert inner.calls == []

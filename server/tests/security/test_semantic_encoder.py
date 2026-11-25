from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.access.semantic_encoder import (  # noqa: E402
    JointSpaceBinding,
    LocalSemanticEncoder,
    SemanticInvalid,
    SemanticUnavailable,
    TextVector,
    rank_semantic,
)
from app.access.visual_candidates import (  # noqa: E402
    VectorRecord,
    VectorSpaceIdentity,
    canonical_vector_checksum,
)


def identity(*, artifact: str, preprocessing: str, space: str = "shared-v1",
             model: str, dimension: int = 2) -> VectorSpaceIdentity:
    return VectorSpaceIdentity(artifact, preprocessing, space, model, dimension, "unit_l2")


@pytest.fixture
def binding() -> JointSpaceBinding:
    return JointSpaceBinding(
        image_identity=identity(artifact="a" * 64, preprocessing="b" * 64, model="image-v1"),
        text_identity=identity(artifact="c" * 64, preprocessing="d" * 64, model="text-v1"),
        qualification_sha256="e" * 64,
    )


def vector_record(asset_id: str, vector: tuple[float, ...], ident: VectorSpaceIdentity) -> VectorRecord:
    return VectorRecord(asset_id, ident, vector, canonical_vector_checksum(vector))


def response(binding: JointSpaceBinding, query: str = "blue sky", vector=(1.0, 0.0), **changes):
    body = {
        "version": 1,
        "binding_sha256": binding.binding_sha256,
        "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        "vector": list(vector),
        "checksum_sha256": canonical_vector_checksum(vector),
    }
    body.update(changes)
    return json.dumps(body, allow_nan=True).encode()


def encoder(binding, handler, **kwargs):
    return LocalSemanticEncoder(
        binding, "http://127.0.0.1:8912/v1/encode-text",
        transport=httpx.MockTransport(handler), **kwargs,
    )


def test_bearer_credential_is_header_only_and_invalid_credentials_are_refused(binding):
    token = 'synthetic_private_token_' + 'x'*24
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=response(binding))
    encoder(binding, handler, bearer_token=token).encode('blue sky')
    assert seen[0].headers['authorization'] == 'Bearer '+token
    assert token.encode() not in seen[0].content
    assert token not in str(seen[0].url)
    for invalid in ('short', 'x'*129, 'x'*32+'\n', True):
        with pytest.raises(ValueError):
            encoder(binding, handler, bearer_token=invalid)


def test_binding_is_domain_separated_and_allows_reviewed_distinct_artifacts(binding):
    assert binding.image_identity.artifact_sha256 != binding.text_identity.artifact_sha256
    assert len(binding.binding_sha256) == 64
    assert binding.binding_sha256 == binding.binding_sha256
    with pytest.raises(ValueError, match="invalid_joint_space_binding"):
        JointSpaceBinding(binding.image_identity, identity(
            artifact="f" * 64, preprocessing="d" * 64, space="other-space", model="text-v1"),
            "e" * 64)
    with pytest.raises(ValueError, match="invalid_joint_space_binding"):
        JointSpaceBinding(binding.image_identity, binding.text_identity, "not-a-digest")


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:8912/v1/encode-text",
    "http://example.com:8912/v1/encode-text",
    "http://127.0.0.1/v1/encode-text",
    "http://127.0.0.1:8912/wrong",
    "http://user:pass@127.0.0.1:8912/v1/encode-text",
    "http://127.0.0.1:8912/v1/encode-text?x=y",
    "http://127.0.0.1:8912/v1/encode-text#fragment",
])
def test_encoder_rejects_non_explicit_loopback_url(binding, url):
    with pytest.raises(ValueError, match="invalid_encoder_configuration"):
        LocalSemanticEncoder(binding, url)


def test_encode_posts_exact_query_and_returns_verified_text_vector(binding):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=response(binding))

    result = encoder(binding, handler).encode("blue sky")
    assert len(seen) == 1
    sent = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/encode-text"
    assert sent == {"version": 1, "binding_sha256": binding.binding_sha256, "query": "blue sky"}
    assert result.binding_sha256 == binding.binding_sha256
    assert result.vector == (1.0, 0.0)


@pytest.mark.parametrize("query", ["", " \t", "a\x00b", "a\nb", "é" * 257, "\ud800"])
def test_invalid_query_fails_before_any_request(binding, query):
    calls = []
    with pytest.raises(SemanticInvalid):
        encoder(binding, lambda request: calls.append(request)).encode(query)
    assert calls == []


@pytest.mark.parametrize("body", [
    lambda b: response(b, binding_sha256="0" * 64),
    lambda b: response(b, query_sha256="0" * 64),
    lambda b: response(b, checksum_sha256="0" * 64),
    lambda b: response(b, vector=[1.0, 1.0]),
    lambda b: response(b, vector=[float("nan"), 0.0]),
    lambda b: response(b, vector=[True, 0.0]),
    lambda b: response(b, version=True),
])
def test_encoder_rejects_wrong_binding_query_checksum_and_invalid_vector(binding, body):
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(200, content=body(binding))).encode("blue sky")


def test_encoder_bounds_streamed_body_and_rejects_redirect(binding):
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(200, content=b"{" + b" " * (64 * 1024))).encode("blue sky")
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(307, headers={"location": "http://example.com/"})).encode("blue sky")


def test_encoder_requires_utf8_and_identity_content_encoding(binding):
    utf16 = response(binding).decode().encode("utf-16")
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(200, content=utf16)).encode("blue sky")
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(
            200, headers={"content-encoding": "gzip"}, content=response(binding),
        )).encode("blue sky")


def test_encoder_enforces_monotonic_total_deadline(binding):
    times = iter((0.0, 2.01))
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(200, content=response(binding)),
                monotonic=lambda: next(times)).encode("blue sky")


@pytest.mark.parametrize("times", [
    (0.0, 0.0, float("nan")),
    (0.0, 0.0, float("inf")),
    (0.0, 0.0, -0.1),
])
def test_encoder_rejects_nonfinite_or_backwards_clock(binding, times):
    values = iter(times)
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(200, content=response(binding)),
                monotonic=lambda: next(values)).encode("blue sky")


def test_encoder_checks_deadline_after_json_validation(binding):
    values = iter((0.0, 0.0, 0.0, 0.0, 2.01))
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(200, content=response(binding)),
                monotonic=lambda: next(values)).encode("blue sky")


def test_encoder_rejects_duplicate_keys_and_nonfinite_json(binding):
    valid = response(binding).decode()
    duplicate = valid.replace('{', '{"version":1,', 1)
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(200, content=duplicate)).encode("blue sky")
    nonfinite = valid.replace("1.0", "NaN")
    with pytest.raises(SemanticUnavailable):
        encoder(binding, lambda request: httpx.Response(200, content=nonfinite)).encode("blue sky")


def test_check_exception_during_stream_propagates(binding):
    class Cancelled(Exception):
        pass

    calls = 0

    def check():
        nonlocal calls
        calls += 1
        if calls == 3:
            raise Cancelled("cancel")

    with pytest.raises(Cancelled, match="cancel"):
        encoder(binding, lambda request: httpx.Response(200, content=response(binding))).encode("blue sky", check=check)


def test_check_exception_after_vector_validation_propagates(binding):
    class Cancelled(Exception):
        pass

    calls = 0

    def check():
        nonlocal calls
        calls += 1
        if calls == 6:
            raise Cancelled("late cancel")

    with pytest.raises(Cancelled, match="late cancel"):
        encoder(binding, lambda request: httpx.Response(200, content=response(binding))).encode("blue sky", check=check)


def test_rank_validates_entire_cohort_and_sorts_equal_scores_by_numeric_id(binding):
    query = (1.0, 0.0)
    text = TextVector(binding.binding_sha256, "f" * 64, query, canonical_vector_checksum(query))
    records = (
        vector_record("11", (0.0, 1.0), binding.image_identity),
        vector_record("2", (0.0, 1.0), binding.image_identity),
        vector_record("1", (1.0, 0.0), binding.image_identity),
    )
    assert rank_semantic(text, binding, records) == (("1", 1.0), ("2", 0.0), ("11", 0.0))
    broken = records[:-1] + (VectorRecord("1", binding.image_identity, (1.0, 0.0), "0" * 64),)
    with pytest.raises(SemanticUnavailable):
        rank_semantic(text, binding, broken)
    with pytest.raises(SemanticUnavailable):
        rank_semantic(text, binding, records + (records[0],))


def test_rank_refuses_wrong_binding_and_propagates_cancellation(binding):
    query = (1.0, 0.0)
    text = TextVector("0" * 64, "f" * 64, query, canonical_vector_checksum(query))
    with pytest.raises(SemanticUnavailable):
        rank_semantic(text, binding, ())

    class Cancelled(Exception):
        pass

    with pytest.raises(Cancelled):
        rank_semantic(TextVector(binding.binding_sha256, "f" * 64, query,
                                 canonical_vector_checksum(query)), binding, (),
                      check=lambda: (_ for _ in ()).throw(Cancelled()))


def test_rank_checks_cancellation_for_each_scored_candidate(binding):
    class Cancelled(Exception):
        pass

    query = (1.0, 0.0)
    text = TextVector(binding.binding_sha256, "f" * 64, query, canonical_vector_checksum(query))
    records = (vector_record("1", (1.0, 0.0), binding.image_identity),
               vector_record("2", (0.0, 1.0), binding.image_identity))
    calls = 0

    def check():
        nonlocal calls
        calls += 1
        if calls == 8:
            raise Cancelled("score cancel")

    with pytest.raises(Cancelled, match="score cancel"):
        rank_semantic(text, binding, records, check=check)


def test_explicit_cpu_timeout_accepts_slow_valid_response(binding):
    now = [0.0]
    def slow_response(request):
        now[0] = 3.0
        return httpx.Response(200, content=response(binding))
    result = encoder(binding, slow_response, timeout=30.0,
                     monotonic=lambda: now[0]).encode("blue sky")
    assert result.vector == (1.0, 0.0)
    now[0] = 0.0
    with pytest.raises(SemanticUnavailable):
        encoder(binding, slow_response, monotonic=lambda: now[0]).encode("blue sky")


def test_explicit_cpu_timeout_still_has_a_hard_total_deadline(binding):
    now = [0.0]
    def expired_response(request):
        now[0] = 30.01
        return httpx.Response(200, content=response(binding))
    with pytest.raises(SemanticUnavailable):
        encoder(binding, expired_response, timeout=30.0,
                monotonic=lambda: now[0]).encode("blue sky")


@pytest.mark.parametrize("timeout", [30.01, float("inf"), float("nan"), -1, 0, True])
def test_explicit_cpu_timeout_refuses_invalid_or_unbounded_values(binding, timeout):
    with pytest.raises(ValueError, match="invalid_encoder_configuration"):
        encoder(binding, lambda request: None, timeout=timeout)

"""Bounded semantic text encoding and ranking primitives.

This module only calls an explicitly configured loopback encoder. A binding is
an operator-reviewed compatibility attestation; it does not claim that either
model artifact was measured or independently qualified here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import struct
import time
from typing import Callable
from urllib.parse import urlsplit

import httpx

from app.access.visual_candidates import (
    MAX_CANDIDATES,
    VectorRecord,
    VectorSpaceIdentity,
    _SHA256,
    _asset_id,
    _canonical_components,
    _score,
    _valid_identity,
    canonical_vector_checksum,
)
from app.access.search_policy import requires_semantic_clarification
from app.access.search_policy_binding import (
    QueryPolicyUnavailable,
    capture_current_query_policy_binding,
    verify_query_policy_binding,
)


_BINDING_PREFIX = b"photohouse-joint-space-binding-v1\0"
_MAX_QUERY_BYTES = 512
_MAX_RESPONSE_BYTES = 64 * 1024
_MAX_TIMEOUT = 2.0
_ENCODE_PATH = "/v1/encode-text"
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class SemanticUnavailable(Exception):
    """Fixed safe failure for an encoder or vector cohort refusal."""

    def __init__(self) -> None:
        super().__init__("semantic_unavailable")


class SemanticUnsupported(SemanticUnavailable):
    """A bound provider explicitly refused the exact query's supported meaning."""

    def __init__(self) -> None:
        Exception.__init__(self, "semantic_query_unsupported")


class SemanticInvalid(Exception):
    """Fixed safe failure for invalid caller-supplied query text."""

    def __init__(self) -> None:
        super().__init__("semantic_invalid")


class _CheckFailure(Exception):
    def __init__(self, error: BaseException) -> None:
        self.error = error


def _checked(check: Callable[[], None]) -> None:
    try:
        check()
    except BaseException as error:
        raise _CheckFailure(error) from None


@dataclass(frozen=True)
class JointSpaceBinding:
    image_identity: VectorSpaceIdentity
    text_identity: VectorSpaceIdentity
    qualification_sha256: str

    def __post_init__(self) -> None:
        image = self.image_identity
        text = self.text_identity
        if (not _valid_identity(image) or not _valid_identity(text)
                or image.vector_space_id != text.vector_space_id
                or image.dimension != text.dimension
                or image.normalization != text.normalization
                or type(self.qualification_sha256) is not str
                or _SHA256.fullmatch(self.qualification_sha256) is None):
            raise ValueError("invalid_joint_space_binding")

    @property
    def binding_sha256(self) -> str:
        canonical = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(_BINDING_PREFIX + canonical).hexdigest()


@dataclass(frozen=True)
class TextVector:
    binding_sha256: str
    query_sha256: str
    vector: tuple[float, ...]
    checksum_sha256: str

    def __post_init__(self) -> None:
        try:
            if type(self.vector) not in (tuple, list) or len(self.vector) > 4096:
                object.__setattr__(self, "vector", ())
            else:
                object.__setattr__(self, "vector", tuple(self.vector))
        except (TypeError, ValueError):
            object.__setattr__(self, "vector", ())


def _query_digest(query: str) -> str:
    encoded = query.encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _valid_query(query: object) -> bool:
    if type(query) is not str or not query.strip() or _CONTROL.search(query):
        return False
    try:
        return len(query.encode("utf-8")) <= _MAX_QUERY_BYTES
    except UnicodeEncodeError:
        return False


def _reject_json_constant(_value: str) -> None:
    raise ValueError("invalid_json")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid_json")
        result[key] = value
    return result


class LocalSemanticEncoder:
    """HTTP adapter for a deliberately configured loopback text encoder."""

    def __init__(self, binding: JointSpaceBinding, url: str, timeout: float = 2.0,
                 transport: httpx.BaseTransport | None = None,
                 monotonic: Callable[[], float] | None = None,
                 bearer_token: str | None = None) -> None:
        if type(binding) is not JointSpaceBinding:
            raise ValueError("invalid_encoder_configuration")
        try:
            parsed = urlsplit(url)
            hostname = parsed.hostname
            port = parsed.port
        except (TypeError, ValueError):
            raise ValueError("invalid_encoder_configuration") from None
        if (parsed.scheme != "http" or hostname not in ("127.0.0.1", "localhost")
                or port is None or parsed.path != _ENCODE_PATH or parsed.query
                or parsed.fragment or parsed.username is not None or parsed.password is not None):
            raise ValueError("invalid_encoder_configuration")
        if (type(timeout) not in (int, float) or not math.isfinite(float(timeout))
                or not 0 < float(timeout) <= _MAX_TIMEOUT):
            raise ValueError("invalid_encoder_configuration")
        if bearer_token is not None and (type(bearer_token) is not str or
                re.fullmatch(r'[A-Za-z0-9_-]{32,128}', bearer_token, flags=re.ASCII) is None):
            raise ValueError("invalid_encoder_configuration")
        try:
            query_policy_binding = capture_current_query_policy_binding()
        except QueryPolicyUnavailable:
            raise ValueError("invalid_encoder_configuration") from None
        self._binding = binding
        self._url = url
        self._timeout = float(timeout)
        self._transport = transport
        self._bearer_token = bearer_token
        self._monotonic = monotonic or time.monotonic
        self._query_policy_binding = query_policy_binding

    @property
    def binding(self) -> JointSpaceBinding:
        return self._binding

    @property
    def query_policy_binding(self) -> dict:
        try:
            return verify_query_policy_binding(self._query_policy_binding)
        except QueryPolicyUnavailable:
            raise SemanticUnavailable() from None

    def encode(self, query: str, *, check: Callable[[], None] = lambda: None) -> TextVector:
        if not _valid_query(query):
            raise SemanticInvalid()
        query_sha256 = _query_digest(query)
        request_body = json.dumps(
            {"version": 1, "binding_sha256": self._binding.binding_sha256, "query": query},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")
        last_clock: float | None = None

        def read_clock() -> float:
            nonlocal last_clock
            value = self._monotonic()
            if type(value) not in (int, float) or not math.isfinite(float(value)):
                raise SemanticUnavailable()
            current = float(value)
            if last_clock is not None and current < last_clock:
                raise SemanticUnavailable()
            last_clock = current
            return current

        started = read_clock()
        deadline = started + self._timeout
        if not math.isfinite(deadline):
            raise SemanticUnavailable()

        def check_deadline() -> float:
            current = read_clock()
            if current >= deadline:
                raise SemanticUnavailable()
            return deadline - current

        def verify_policy_binding() -> None:
            check_deadline()
            try:
                verify_query_policy_binding(
                    self._query_policy_binding,
                    check=lambda: (_checked(check), check_deadline()),
                )
            except QueryPolicyUnavailable:
                raise SemanticUnavailable() from None
            check_deadline()

        try:
            _checked(check)
            verify_policy_binding()
            if requires_semantic_clarification(query):
                verify_policy_binding()
                raise SemanticUnsupported()
            remaining = check_deadline()
            timeout = httpx.Timeout(remaining)
            with httpx.Client(transport=self._transport, timeout=timeout,
                              follow_redirects=False, trust_env=False) as client:
                headers = {"content-type": "application/json",
                           "x-photohouse-semantic-refusal": "1"}
                if self._bearer_token is not None:
                    headers['authorization'] = 'Bearer ' + self._bearer_token
                with client.stream("POST", self._url, content=request_body, headers=headers) as response:
                    _checked(check)
                    status = response.status_code
                    if status not in (200, 422):
                        raise SemanticUnavailable()
                    if status == 422 and response.headers.get('content-type', '').lower().replace(' ', '') not in (
                            'application/json', 'application/json;charset=utf-8'):
                        raise SemanticUnavailable()
                    content_encoding = response.headers.get("content-encoding")
                    if (content_encoding is not None
                            and content_encoding.strip().lower() != "identity"):
                        raise SemanticUnavailable()
                    body = bytearray()
                    for chunk in response.iter_bytes(chunk_size=8192):
                        _checked(check)
                        check_deadline()
                        if len(body) + len(chunk) > _MAX_RESPONSE_BYTES:
                            raise SemanticUnavailable()
                        body.extend(chunk)
                    _checked(check)
                    check_deadline()
            data = json.loads(body.decode("utf-8", errors="strict"), object_pairs_hook=_unique_object,
                              parse_constant=_reject_json_constant)
            _checked(check)
            check_deadline()
            if status == 422:
                if (type(data) is not dict
                        or set(data) != {'version', 'error', 'binding_sha256', 'query_sha256'}
                        or type(data['version']) is not int or data['version'] != 1
                        or data['error'] != 'unsupported_query'
                        or data['binding_sha256'] != self._binding.binding_sha256
                        or data['query_sha256'] != query_sha256):
                    raise SemanticUnavailable()
                verify_policy_binding()
                raise SemanticUnsupported()
            if (type(data) is not dict
                    or set(data) != {"version", "binding_sha256", "query_sha256", "vector", "checksum_sha256"}
                    or type(data["version"]) is not int or data["version"] != 1
                    or type(data["binding_sha256"]) is not str
                    or data["binding_sha256"] != self._binding.binding_sha256
                    or type(data["query_sha256"]) is not str
                    or data["query_sha256"] != query_sha256
                    or type(data["checksum_sha256"]) is not str
                    or _SHA256.fullmatch(data["checksum_sha256"]) is None
                    or type(data["vector"]) is not list
                    or any(type(value) not in (int, float) for value in data["vector"])):
                raise SemanticUnavailable()
            vector = tuple(data["vector"])
            record = VectorRecord("1", self._binding.text_identity, vector, data["checksum_sha256"])
            _canonical_components(record, self._binding.text_identity)
            _checked(check)
            check_deadline()
            result = TextVector(self._binding.binding_sha256, query_sha256, vector,
                                data["checksum_sha256"])
            _checked(check)
            check_deadline()
            verify_policy_binding()
            return result
        except SemanticUnavailable:
            raise
        except _CheckFailure as failure:
            raise failure.error
        except Exception:
            raise SemanticUnavailable() from None


def rank_semantic(
    query_vector: TextVector,
    binding: JointSpaceBinding,
    candidate_records: tuple[VectorRecord, ...],
    *,
    check: Callable[[], None] = lambda: None,
) -> tuple[tuple[str, float], ...]:
    """Validate one complete authorized image-vector cohort, then rank it."""
    try:
        _checked(check)
        if (type(binding) is not JointSpaceBinding or type(query_vector) is not TextVector
                or type(candidate_records) is not tuple or len(candidate_records) > MAX_CANDIDATES
                or type(query_vector.binding_sha256) is not str
                or query_vector.binding_sha256 != binding.binding_sha256
                or type(query_vector.query_sha256) is not str
                or _SHA256.fullmatch(query_vector.query_sha256) is None
                or type(query_vector.checksum_sha256) is not str
                or _SHA256.fullmatch(query_vector.checksum_sha256) is None):
            raise SemanticUnavailable()
        query_record = VectorRecord("1", binding.text_identity, query_vector.vector,
                                    query_vector.checksum_sha256)
        query = _canonical_components(query_record, binding.text_identity)
        _checked(check)
        ids: set[str] = set()
        vectors: list[tuple[str, tuple[float, ...]]] = []
        for record in candidate_records:
            _checked(check)
            if (type(record) is not VectorRecord or not _asset_id(record.asset_id)
                    or record.asset_id in ids):
                raise SemanticUnavailable()
            ids.add(record.asset_id)
            candidate_vector = _canonical_components(record, binding.image_identity)
            _checked(check)
            vectors.append((record.asset_id, candidate_vector))
        _checked(check)
        ranked = []
        for asset_id, vector in vectors:
            _checked(check)
            ranked.append((asset_id, _score(query, vector)))
        ranked.sort(key=lambda item: (-item[1], int(item[0])))
        _checked(check)
        return tuple(ranked)
    except SemanticUnavailable:
        raise
    except _CheckFailure as failure:
        raise failure.error
    except (TypeError, ValueError, OverflowError, RecursionError, struct.error):
        raise SemanticUnavailable() from None

"""Exact, operator-reviewed scene-query projection for explicitly configured providers.

This module performs no semantic inference. A query is adapted only when its
exact UTF-8 text is present in an immutable, digest-pinned review document.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import hashlib
import json
import re
import threading
from types import MappingProxyType
from typing import Callable

from app.access.semantic_encoder import (
    JointSpaceBinding,
    SemanticInvalid,
    SemanticUnavailable,
    TextVector,
)
from app.access.visual_candidates import (
    VectorRecord,
    _canonical_components,
    _valid_identity,
)


_DOCUMENT_SCHEMA = "photohouse.reviewed_scene_projection.v1"
_POLICY = "exact_reviewed_only"
_REVIEW_STATUS = "operator_reviewed"
_RECIPE_SCHEMA = "photohouse.reviewed_semantic_projection_recipe.v1"
_SOURCE_QUERY_MAX_BYTES = 512
_MODEL_INPUT_MAX_BYTES = 512
_ORIGINAL_CONTROLS = frozenset(range(0x00, 0x20)) | frozenset(range(0x7f, 0xa0))
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _original_is_valid(value: object) -> bool:
    if type(value) is not str or not value.strip():
        return False
    try:
        if len(value.encode("utf-8", errors="strict")) > _SOURCE_QUERY_MAX_BYTES:
            return False
    except UnicodeError:
        return False
    return not any(ord(char) in _ORIGINAL_CONTROLS or char in "\u2028\u2029"
                   for char in value)


def _model_input_is_valid(value: object) -> bool:
    return (type(value) is str and bool(value) and len(value) <= _MODEL_INPUT_MAX_BYTES
            and any("A" <= char <= "Z" or "a" <= char <= "z" for char in value)
            and all(" " <= char <= "~" for char in value))


def _canonical_document(document: object) -> tuple[dict[str, object], str]:
    """Validate and copy the exact primitive document, then hash canonical JSON."""
    if (type(document) is not dict
            or any(type(key) is not str for key in document)
            or set(document) != {"schema", "policy", "review", "entries"}):
        raise ValueError("invalid_reviewed_projection_document")
    if (type(document.get("schema")) is not str or document["schema"] != _DOCUMENT_SCHEMA
            or type(document.get("policy")) is not str or document["policy"] != _POLICY):
        raise ValueError("invalid_reviewed_projection_document")
    review = document.get("review")
    if (type(review) is not dict
            or any(type(key) is not str for key in review)
            or set(review) != {"status", "reference_sha256"}
            or type(review.get("status")) is not str
            or review["status"] != _REVIEW_STATUS
            or type(review.get("reference_sha256")) is not str
            or _HEX.fullmatch(review["reference_sha256"]) is None):
        raise ValueError("invalid_reviewed_projection_document")
    entries = document.get("entries")
    if type(entries) is not list or not 1 <= len(entries) <= 256:
        raise ValueError("invalid_reviewed_projection_document")
    copied_entries: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        if (type(entry) is not dict
                or any(type(key) is not str for key in entry)
                or set(entry) != {"original", "model_input"}):
            raise ValueError("invalid_reviewed_projection_document")
        original, model_input = entry.get("original"), entry.get("model_input")
        if (not _original_is_valid(original) or not _model_input_is_valid(model_input)
                or original in seen):
            raise ValueError("invalid_reviewed_projection_document")
        seen.add(original)
        copied_entries.append({"original": original, "model_input": model_input})
    snapshot: dict[str, object] = {
        "schema": _DOCUMENT_SCHEMA,
        "policy": _POLICY,
        "review": {"status": _REVIEW_STATUS,
                   "reference_sha256": review["reference_sha256"]},
        "entries": copied_entries,
    }
    try:
        encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("invalid_reviewed_projection_document") from None
    return snapshot, hashlib.sha256(encoded).hexdigest()


def reviewed_document_sha256(document: object) -> str:
    """Return the canonical digest of a structurally valid review document."""
    return _canonical_document(document)[1]


class ReviewedProjection:
    """Immutable exact-match mapping whose representation contains no query text."""

    __slots__ = ("_entries", "_projection_sha256", "_reference_sha256", "_count", "_sealed")

    def __init__(self, document: object, *, expected_sha256: str):
        if type(expected_sha256) is not str or _HEX.fullmatch(expected_sha256) is None:
            raise ValueError("invalid_reviewed_projection_digest")
        snapshot, digest = _canonical_document(document)
        if digest != expected_sha256:
            raise ValueError("invalid_reviewed_projection_digest")
        pairs = {entry["original"]: entry["model_input"] for entry in snapshot["entries"]}
        object.__setattr__(self, "_entries", MappingProxyType(pairs))
        object.__setattr__(self, "_projection_sha256", digest)
        object.__setattr__(self, "_reference_sha256", snapshot["review"]["reference_sha256"])
        object.__setattr__(self, "_count", len(pairs))
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError("reviewed_projection_is_immutable")
        object.__setattr__(self, name, value)

    @property
    def projection_sha256(self) -> str:
        return self._projection_sha256

    @property
    def review_reference_sha256(self) -> str:
        return self._reference_sha256

    @property
    def entry_count(self) -> int:
        return self._count

    def project(self, query: object) -> str:
        if not _original_is_valid(query):
            raise SemanticInvalid()
        try:
            return self._entries[query]
        except KeyError:
            raise SemanticUnavailable() from None

    def provenance(self, query: object) -> dict[str, str]:
        model_input = self.project(query)
        return {
            "original_query_sha256": hashlib.sha256(query.encode("utf-8")).hexdigest(),
            "model_input_sha256": hashlib.sha256(model_input.encode("ascii")).hexdigest(),
            "projection_sha256": self._projection_sha256,
        }

    def probe(self) -> dict[str, object]:
        return {
            "schema": _DOCUMENT_SCHEMA,
            "policy": _POLICY,
            "review_status": _REVIEW_STATUS,
            "review_reference_sha256": self._reference_sha256,
            "projection_sha256": self._projection_sha256,
            "entry_count": self._count,
            "semantic_faithfulness_qualified": False,
        }

    def __repr__(self) -> str:
        return (f"ReviewedProjection(entry_count={self._count}, "
                f"projection_sha256='{self._projection_sha256}', "
                f"review_reference_sha256='{self._reference_sha256}')")


def _canonical_recipe(recipe: dict[str, object]) -> tuple[dict[str, object], str]:
    try:
        encoded = json.dumps(recipe, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode("ascii")
    except (TypeError, ValueError, UnicodeError):
        raise ValueError("invalid_reviewed_projection_recipe") from None
    return recipe, hashlib.sha256(encoded).hexdigest()


def composition_recipe(inner_binding: object, projection: object,
                       adapter_source_sha256: object) -> dict[str, object]:
    """Bind an exact projection to the complete unchanged inner space identity."""
    if (type(inner_binding) is not JointSpaceBinding
            or type(projection) is not ReviewedProjection
            or type(adapter_source_sha256) is not str
            or _HEX.fullmatch(adapter_source_sha256) is None):
        raise ValueError("invalid_reviewed_projection_composition")
    image = inner_binding.image_identity
    text = inner_binding.text_identity
    if not _valid_identity(image) or not _valid_identity(text):
        raise ValueError("invalid_reviewed_projection_composition")
    recipe: dict[str, object] = {
        "schema": _RECIPE_SCHEMA,
        "policy": _POLICY,
        "inner_binding": asdict(inner_binding),
        "projection_sha256": projection.projection_sha256,
        "review_reference_sha256": projection.review_reference_sha256,
        "adapter_source_sha256": adapter_source_sha256,
    }
    _, digest = _canonical_recipe(recipe)
    return {**recipe, "recipe_sha256": digest}


def validate_projection_binding(inner_binding: object, projection: object,
                                binding: object, adapter_source_sha256: object
                                ) -> dict[str, object]:
    """Validate an outer binding before model loading and return its recipe."""
    if type(binding) is not JointSpaceBinding:
        raise ValueError("invalid_reviewed_projection_composition")
    recipe = composition_recipe(inner_binding, projection, adapter_source_sha256)
    expected_text = replace(inner_binding.text_identity,
                             preprocessing_sha256=recipe["recipe_sha256"])
    if (binding.image_identity != inner_binding.image_identity
            or binding.text_identity != expected_text
            or binding.qualification_sha256 == inner_binding.qualification_sha256):
        raise ValueError("invalid_reviewed_projection_composition")
    return recipe


class ReviewedSemanticProvider:
    """Compose a pinned reviewed mapping with an already bound text encoder."""

    def __init__(self, inner: object, projection: ReviewedProjection,
                 binding: JointSpaceBinding, *, adapter_source_sha256: str,
                 source_check: Callable[[], None] = lambda: None):
        if (inner is None or type(projection) is not ReviewedProjection
                or type(binding) is not JointSpaceBinding
                or not callable(source_check)):
            raise ValueError("invalid_reviewed_semantic_provider")
        try:
            if not callable(getattr(inner, "encode", None)):
                raise ValueError("invalid_reviewed_semantic_provider")
            inner_binding = inner.binding
            recipe = validate_projection_binding(inner_binding, projection, binding,
                                                 adapter_source_sha256)
        except Exception:
            raise ValueError("invalid_reviewed_semantic_provider") from None
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_projection", projection)
        object.__setattr__(self, "_inner_binding", inner_binding)
        object.__setattr__(self, "_binding", binding)
        object.__setattr__(self, "_recipe_sha256", recipe["recipe_sha256"])
        object.__setattr__(self, "_source_check", source_check)
        object.__setattr__(self, "_lease", threading.Lock())
        object.__setattr__(self, "_sealed", True)

    def __setattr__(self, name, value):
        if getattr(self, "_sealed", False):
            raise AttributeError("reviewed_semantic_provider_is_immutable")
        object.__setattr__(self, name, value)

    @property
    def binding(self) -> JointSpaceBinding:
        return self._binding

    @property
    def inner_binding(self) -> JointSpaceBinding:
        return self._inner_binding

    def probe(self) -> dict[str, object]:
        return {
            "schema": _RECIPE_SCHEMA,
            "policy": _POLICY,
            "recipe_sha256": self._recipe_sha256,
            "projection_sha256": self._projection.projection_sha256,
            "review_reference_sha256": self._projection.review_reference_sha256,
            "entry_count": self._projection.entry_count,
            "inner_binding_sha256": self._inner_binding.binding_sha256,
            "binding_sha256": self._binding.binding_sha256,
            "activation_approved": False,
            "semantic_faithfulness_qualified": False,
        }

    def __repr__(self) -> str:
        return (f"ReviewedSemanticProvider(binding_sha256='{self._binding.binding_sha256}', "
                f"recipe_sha256='{self._recipe_sha256}', "
                f"entry_count={self._projection.entry_count})")

    def _check_inner_binding(self) -> None:
        current = self._inner.binding
        if (type(current) is not JointSpaceBinding or current is not self._inner_binding
                or current != self._inner_binding):
            raise SemanticUnavailable()

    @staticmethod
    def _run_check(check: Callable[[], None]) -> None:
        if not callable(check):
            raise SemanticUnavailable()
        try:
            check()
        except Exception:
            raise SemanticUnavailable() from None

    def _run_source_check(self) -> None:
        try:
            self._source_check()
        except Exception:
            raise SemanticUnavailable() from None

    def encode(self, query: object, *, check: Callable[[], None] = lambda: None) -> TextVector:
        if not self._lease.acquire(blocking=False):
            raise SemanticUnavailable()
        try:
            # Projection validates before invoking any inner provider. Exact
            # strings are neither trimmed nor normalized.
            model_input = self._projection.project(query)
            self._check_inner_binding()
            self._run_source_check()
            self._run_check(check)
            self._check_inner_binding()
            original_digest = hashlib.sha256(query.encode("utf-8")).hexdigest()
            derived_digest = hashlib.sha256(model_input.encode("ascii")).hexdigest()
            try:
                result = self._inner.encode(model_input, check=check)
            except Exception:
                raise SemanticUnavailable() from None
            if type(result) is not TextVector:
                raise SemanticUnavailable()
            if (type(result.binding_sha256) is not str
                    or result.binding_sha256 != self._inner_binding.binding_sha256
                    or type(result.query_sha256) is not str
                    or result.query_sha256 != derived_digest
                    or type(result.checksum_sha256) is not str
                    or _HEX.fullmatch(result.checksum_sha256) is None
                    or type(result.vector) is not tuple):
                raise SemanticUnavailable()
            try:
                _canonical_components(
                    VectorRecord("1", self._inner_binding.text_identity,
                                 result.vector, result.checksum_sha256),
                    self._inner_binding.text_identity,
                )
            except Exception:
                raise SemanticUnavailable() from None
            self._run_check(check)
            self._run_source_check()
            self._check_inner_binding()
            # Bind the preserved components to the reviewed outer space, while
            # exposing only the caller's original-query digest.
            return TextVector(self._binding.binding_sha256, original_digest,
                              result.vector, result.checksum_sha256)
        except (SemanticInvalid, SemanticUnavailable):
            raise
        except Exception:
            raise SemanticUnavailable() from None
        finally:
            self._lease.release()

"""Bounded all-or-nothing normalization for simple bilingual clothing queries.

This module has no model or filesystem work at import time. It only rewrites a
closed, fully recognized color + garment + wearer construction; every other
valid query is passed through unchanged for the caller's existing safeguards.
"""
from __future__ import annotations

from dataclasses import asdict, replace
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import threading
from typing import Callable

from app.access.search_exclusions import requires_semantic_clarification
from app.access.semantic_encoder import (
    JointSpaceBinding,
    SemanticInvalid,
    SemanticUnavailable,
    SemanticUnsupported,
    TextVector,
    _valid_query,
)
from app.access.visual_candidates import (
    VectorRecord,
    _canonical_components,
    _valid_identity,
    canonical_vector_checksum,
)


POLICY = "photohouse.bilingual_clothing_normalization.v1"
_RECIPE_SCHEMA = "photohouse.bilingual_clothing_composition_recipe.v1"
_HEX = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_CHINESE_COLORS = {
    "红": "red", "红色": "red", "蓝": "blue", "蓝色": "blue",
    "绿": "green", "绿色": "green", "紫": "purple", "紫色": "purple",
    "黄": "yellow", "黄色": "yellow", "黑": "black", "黑色": "black",
    "白": "white", "白色": "white", "粉": "pink", "粉色": "pink",
    "橙": "orange", "橙色": "orange", "棕": "brown", "棕色": "brown",
    "灰": "gray", "灰色": "gray",
}
_ENGLISH_COLORS = {
    name: name for name in (
        "red", "blue", "green", "purple", "yellow", "black", "white",
        "pink", "orange", "brown", "gray",
    )
}
_CHINESE_GARMENTS = {
    "衣服": ("clothing", False), "服装": ("clothing", False),
    "连衣裙": ("dress", True), "外套": ("coat", True),
    "衬衫": ("shirt", True), "T恤": ("t-shirt", True),
    "戏服": ("costume", True), "戏装": ("costume", True),
    "裤子": ("trousers", False),
}
_ENGLISH_GARMENTS = {
    "clothing": ("clothing", False), "clothes": ("clothing", False),
    "dress": ("dress", True), "coat": ("coat", True),
    "shirt": ("shirt", True), "t-shirt": ("t-shirt", True),
    "costume": ("costume", True), "trousers": ("trousers", False),
}
_CHINESE_WEARERS = {
    "孩子": "child", "小孩": "child", "儿童": "child",
    "女人": "woman", "男人": "man", "人": "person",
    "女孩": "girl", "男孩": "boy",
}
_ENGLISH_WEARERS = {
    name: name for name in ("child", "woman", "man", "person", "girl", "boy")
}


def _alternation(values: object) -> str:
    return "(?:" + "|".join(
        re.escape(value) for value in sorted(values, key=len, reverse=True)
    ) + ")"


_ZH_PATTERN = re.compile(
    r"穿(?:着)?(?P<color>" + _alternation(_CHINESE_COLORS) + r")"
    r"(?P<garment>" + _alternation(_CHINESE_GARMENTS) + r")的"
    r"(?P<wearer>" + _alternation(_CHINESE_WEARERS) + r")\Z"
)
_MIXED_PATTERN = re.compile(
    r"穿(?:着)?(?P<color>" + _alternation(_ENGLISH_COLORS) + r") "
    r"(?P<garment>" + _alternation(_ENGLISH_GARMENTS) + r")的"
    r"(?P<wearer>" + _alternation(_CHINESE_WEARERS) + r")\Z",
    re.IGNORECASE | re.ASCII,
)
_ENGLISH_PATTERN = re.compile(
    r"(?:(?:a|an) )?(?P<wearer>child|woman|man|person|girl|boy) "
    r"wearing (?:(?:a|an) )?(?P<color>red|blue|green|purple|yellow|black|white|"
    r"pink|orange|brown|gray) (?P<garment>t-shirt|clothing|clothes|dress|coat|"
    r"shirt|costume|trousers)\Z",
    re.IGNORECASE | re.ASCII,
)


def _valid_original(query: object) -> bool:
    return (_valid_query(query) and not _CONTROL.search(query)
            and "\u2028" not in query and "\u2029" not in query)


def model_input(query: str) -> str:
    """Normalize a complete supported clothing phrase, otherwise preserve it."""
    if not _valid_original(query):
        raise SemanticInvalid()

    match = _ZH_PATTERN.fullmatch(query)
    colors, garments, wearers = _CHINESE_COLORS, _CHINESE_GARMENTS, _CHINESE_WEARERS
    if match is None:
        match = _MIXED_PATTERN.fullmatch(query)
        colors, garments, wearers = _ENGLISH_COLORS, _ENGLISH_GARMENTS, _CHINESE_WEARERS
    if match is not None:
        color_key = match.group("color")
        garment_key = match.group("garment")
        if colors is _ENGLISH_COLORS:
            color_key, garment_key = color_key.lower(), garment_key.lower()
        color = colors[color_key]
        garment, article = garments[garment_key]
        wearer = wearers[match.group("wearer")]
        garment_phrase = f"{color} {garment}"
        if article:
            garment_phrase = f"a {garment_phrase}"
        return f"a {wearer} wearing {garment_phrase}"

    match = _ENGLISH_PATTERN.fullmatch(query)
    if match is None:
        return query
    color = _ENGLISH_COLORS[match.group("color").lower()]
    garment, article = _ENGLISH_GARMENTS[match.group("garment").lower()]
    wearer = _ENGLISH_WEARERS[match.group("wearer").lower()]
    garment_phrase = f"{color} {garment}"
    if article:
        garment_phrase = f"a {garment_phrase}"
    return f"a {wearer} wearing {garment_phrase}"


def composition_recipe(inner_binding: object, adapter_source_sha256: object
                       ) -> dict[str, object]:
    """Bind the complete text transformation to an unchanged inner space."""
    if (type(inner_binding) is not JointSpaceBinding
            or type(adapter_source_sha256) is not str
            or _HEX.fullmatch(adapter_source_sha256) is None):
        raise ValueError("invalid_bilingual_clothing_composition")
    if (not _valid_identity(inner_binding.image_identity)
            or not _valid_identity(inner_binding.text_identity)):
        raise ValueError("invalid_bilingual_clothing_composition")
    module_sha256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    recipe: dict[str, object] = {
        "schema": _RECIPE_SCHEMA,
        "policy": POLICY,
        "inner_binding": asdict(inner_binding),
        "module_sha256": module_sha256,
        "adapter_source_sha256": adapter_source_sha256,
    }
    encoded = json.dumps(recipe, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False).encode("ascii")
    return {**recipe, "recipe_sha256": hashlib.sha256(encoded).hexdigest()}


class BilingualClothingProvider:
    """Compose a bounded text normalizer with an already bound encoder."""

    def __init__(self, inner: object, binding: object, *, adapter_source_sha256: str,
                 source_check: Callable[[], None] = lambda: None) -> None:
        inner_binding = getattr(inner, "binding", None)
        if (inner is None or type(inner_binding) is not JointSpaceBinding
                or type(binding) is not JointSpaceBinding or not callable(source_check)):
            raise ValueError("invalid_bilingual_clothing_provider")
        try:
            if not callable(getattr(inner, "encode", None)):
                raise ValueError()
            recipe = composition_recipe(inner_binding, adapter_source_sha256)
            expected_text = replace(
                inner_binding.text_identity,
                preprocessing_sha256=recipe["recipe_sha256"],
            )
            if (binding.image_identity != inner_binding.image_identity
                    or binding.text_identity != expected_text
                    or binding.qualification_sha256 == inner_binding.qualification_sha256):
                raise ValueError()
        except Exception:
            raise ValueError("invalid_bilingual_clothing_provider") from None
        self._inner = inner
        self._inner_binding = inner_binding
        self._binding = binding
        self._recipe = recipe
        self._source_check = source_check
        self._lease = threading.BoundedSemaphore(1)

    @property
    def binding(self) -> JointSpaceBinding:
        return self._binding

    @property
    def inner_binding(self) -> JointSpaceBinding:
        return self._inner_binding

    @property
    def recipe(self) -> dict[str, object]:
        return deepcopy(self._recipe)

    def _check_binding(self) -> None:
        current = getattr(self._inner, "binding", None)
        if (type(current) is not JointSpaceBinding or current is not self._inner_binding
                or current != self._inner_binding):
            raise SemanticUnavailable()

    def _check_callbacks(self, check: Callable[[], None]) -> None:
        if not callable(check):
            raise SemanticUnavailable()
        try:
            self._source_check()
            check()
        except Exception:
            raise SemanticUnavailable() from None

    def encode(self, query: object, *, check: Callable[[], None] = lambda: None) -> TextVector:
        if not _valid_original(query):
            raise SemanticInvalid()
        # Admission precedes normalization and every inner call, including the
        # unchanged-query fallback path.
        if requires_semantic_clarification(query):
            raise SemanticUnsupported()
        if not self._lease.acquire(blocking=False):
            raise SemanticUnavailable()
        try:
            self._check_binding()
            self._check_callbacks(check)
            projected = model_input(query)
            if requires_semantic_clarification(projected):
                raise SemanticUnsupported()
            self._check_binding()
            self._check_callbacks(check)
            original_sha256 = hashlib.sha256(query.encode("utf-8")).hexdigest()
            projected_sha256 = hashlib.sha256(projected.encode("utf-8")).hexdigest()
            try:
                result = self._inner.encode(projected, check=check)
            except SemanticUnsupported:
                raise
            except Exception:
                raise SemanticUnavailable() from None
            if (type(result) is not TextVector
                    or result.binding_sha256 != self._inner_binding.binding_sha256
                    or result.query_sha256 != projected_sha256
                    or type(result.checksum_sha256) is not str
                    or _HEX.fullmatch(result.checksum_sha256) is None):
                raise SemanticUnavailable()
            try:
                record = VectorRecord("1", self._inner_binding.text_identity,
                                      result.vector, result.checksum_sha256)
                _canonical_components(record, self._inner_binding.text_identity)
                if canonical_vector_checksum(record.vector) != result.checksum_sha256:
                    raise ValueError()
            except Exception:
                raise SemanticUnavailable() from None
            self._check_binding()
            self._check_callbacks(check)
            return TextVector(self._binding.binding_sha256, original_sha256,
                              record.vector, result.checksum_sha256)
        finally:
            self._lease.release()

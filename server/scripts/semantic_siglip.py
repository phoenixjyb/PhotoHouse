"""Supported public SigLIP adapter with the current search-policy guard.

The exact indexed encoder implementation lives in the private
``_semantic_siglip_encoding`` module. Its historical model receipt and legacy
dependency stay separate from this public query-policy binding.
"""
from __future__ import annotations

from _semantic_siglip_encoding import (
    DIMENSION,
    MODEL_VERSION,
    SPACE,
    SiglipModel as _EncodingSiglipModel,
    qualification,
)
from app.access.semantic_encoder import (
    SemanticInvalid,
    SemanticUnavailable,
    SemanticUnsupported,
    _valid_query,
)
from app.access.search_policy import requires_semantic_clarification
from app.access.search_policy_binding import (
    QueryPolicyUnavailable,
    capture_current_query_policy_binding,
    verify_query_policy_binding,
)


class SiglipModel(_EncodingSiglipModel):
    """Public adapter; current policy binding is independent of model identity."""

    def __init__(self):
        # The frozen loader constructs ``cls`` and calls virtual ``verify``
        # before returning, so establish the policy pin in the constructor.
        self._query_policy_binding = capture_current_query_policy_binding()

    @property
    def query_policy_binding(self):
        self._verify_query_policy()
        return dict(self._query_policy_binding)

    def _verify_query_policy(self, check=lambda: None):
        try:
            return verify_query_policy_binding(self._query_policy_binding, check=check)
        except QueryPolicyUnavailable:
            raise SemanticUnavailable() from None

    def verify(self):
        super().verify()
        self._verify_query_policy()

    def bind(self, binding):
        self._verify_query_policy()
        return super().bind(binding)

    def _check(self, check):
        super()._check(check)
        self._verify_query_policy(check)

    def encode(self, query, *, check=lambda: None):
        # Keep the frozen adapter's invalid-query semantics and original bytes.
        if (not _valid_query(query)
                or any(0x7f <= ord(char) < 0xa0 or char in "\u2028\u2029" for char in query)):
            raise SemanticInvalid()
        self._verify_query_policy(check)
        if requires_semantic_clarification(query):
            raise SemanticUnsupported()
        return super().encode(query, check=check)


def query_policy_binding_for(model):
    """Read explicit current-policy metadata from a public or library model."""
    target = model if type(model) is SiglipModel else getattr(model, "_inner", None)
    if type(target) is SiglipModel:
        expected = target.query_policy_binding
    else:
        # Explicit synthetic adapters may participate in local qualification,
        # but must still present a complete, freshly verifiable binding.
        expected = getattr(model, "query_policy_binding", None)
    try:
        return verify_query_policy_binding(expected)
    except QueryPolicyUnavailable:
        raise SemanticUnavailable() from None

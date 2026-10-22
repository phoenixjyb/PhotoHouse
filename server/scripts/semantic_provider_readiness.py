#!/usr/bin/env python3
"""Plan or explicitly probe one configured local semantic text provider.

The probe makes one fixed synthetic encode request. It does not activate
semantic search, authorize a library owner, read an index or policy, or manage
the provider process. With no arguments, it prints a plan without importing
PhotoHouse modules or reading private files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


SERVER = Path(__file__).resolve().parents[1]
SOURCE_ROOT = SERVER.parent
EXPECTED_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
SYNTHETIC_QUERY = "synthetic semantic provider readiness probe"
SYNTHETIC_QUERY_SHA256 = hashlib.sha256(SYNTHETIC_QUERY.encode("utf-8")).hexdigest()
PLAN = {
    "version": 1,
    "status": "plan_only",
    "scope": "provider_only_synthetic_protocol_check",
    "explicit_check_required": True,
    "private_file_reads": False,
    "network_requests": False,
    "model_loading": False,
    "activation": False,
    "service_management": False,
}


class Refused(Exception):
    def __init__(self, code: str = "readiness_unavailable") -> None:
        self.code = code
        super().__init__(code)


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise Refused("invalid_arguments") from None


def _canonical_digest(document: object) -> str:
    try:
        payload = json.dumps(document, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise Refused("invalid_configuration") from None
    return hashlib.sha256(payload).hexdigest()


def _load_pinned_document(config_path: Path, expected_sha256: str, load_document):
    document = load_document(config_path, source_root=SOURCE_ROOT)
    if _canonical_digest(document) != expected_sha256:
        raise Refused("config_pin_mismatch")
    return document


def _runtime_descriptor(runtime):
    # Keep the secret in memory only for equality comparison. Never serialize
    # this descriptor or an exception originating from its private values.
    from app.access.semantic_encoder import LocalSemanticEncoder
    from app.access.semantic_search import SemanticSearchRuntime

    if (type(runtime) is not SemanticSearchRuntime or
            type(runtime.encoder) is not LocalSemanticEncoder or
            runtime.pilot_owner_account_id is None or
            runtime.encoder.binding.image_identity.dimension != 768 or
            runtime.encoder.binding.text_identity.dimension != 768):
        raise Refused("unsupported_binding")
    encoder = runtime.encoder
    return (encoder.binding.binding_sha256, encoder._url, encoder._timeout,
            encoder._bearer_token, runtime.pilot_owner_account_id,
            encoder.binding.image_identity, encoder.binding.text_identity)


def _inert_discovery():
    from app.access.discovery import ReadBudget
    from app.access.discovery_transport import DiscoveryRuntime
    from app.access.transport import AccessRuntime

    def refuse_connection():
        raise RuntimeError("readiness has no database connection")

    class EmptyProvider:
        def get(self, _library):
            return None

    access = AccessRuntime(refuse_connection, "https://readiness.invalid")
    return DiscoveryRuntime(access, EmptyProvider(), ReadBudget())


def _check(config_path: Path, expected_sha256: str) -> dict[str, object]:
    if (not isinstance(config_path, Path) or not config_path.is_absolute() or
            ".." in config_path.parts or type(expected_sha256) is not str or
            not EXPECTED_SHA256.fullmatch(expected_sha256)):
        raise Refused("invalid_arguments")

    try:
        # Import only after an explicit, well-shaped check request. The first
        # private read is the pinned config; credentials are loaded only after its
        # canonical digest matches the operator-supplied value.
        backend = str(SERVER / "backend")
        if backend not in sys.path:
            sys.path.insert(0, backend)
        from app.access.model_deployment import _load_private_document
        from app.access.semantic_configuration import load_semantic_runtime
        from app.access.semantic_encoder import SemanticUnsupported, SemanticUnavailable

        _load_pinned_document(config_path, expected_sha256, _load_private_document)
        discovery = _inert_discovery()
        runtime = load_semantic_runtime(config_path, discovery=discovery,
            source_root=SOURCE_ROOT, expected_document_sha256=expected_sha256)
        descriptor = _runtime_descriptor(runtime)

        # Re-read both config and credential-backed runtime immediately before
        # the single fixed request. Use this freshly loaded encoder for it.
        _load_pinned_document(config_path, expected_sha256, _load_private_document)
        current = load_semantic_runtime(config_path, discovery=discovery,
            source_root=SOURCE_ROOT, expected_document_sha256=expected_sha256)
        if _runtime_descriptor(current) != descriptor:
            raise Refused("runtime_changed")
        encoder = current.encoder

        provider_failure = None
        vector = None
        try:
            vector = encoder.encode(SYNTHETIC_QUERY)
        except SemanticUnsupported:
            provider_failure = "provider_unsupported"
        except SemanticUnavailable:
            provider_failure = "provider_unavailable"
        except Exception:
            provider_failure = "provider_unavailable"

        # A provider reply is not ready evidence unless the exact private pin
        # and credential/runtime descriptor remain current after the exchange.
        _load_pinned_document(config_path, expected_sha256, _load_private_document)
        after = load_semantic_runtime(config_path, discovery=discovery,
            source_root=SOURCE_ROOT, expected_document_sha256=expected_sha256)
        if _runtime_descriptor(after) != descriptor:
            raise Refused("runtime_changed")
        if provider_failure is not None:
            raise Refused(provider_failure)

        from app.access.semantic_encoder import TextVector
        if (type(vector) is not TextVector or
                vector.binding_sha256 != current.encoder.binding.binding_sha256):
            raise Refused("provider_unavailable")
        return {
            "version": 1,
            "status": "ready",
            "scope": "provider_only_synthetic_protocol_check",
            "config_sha256": expected_sha256,
            "binding_sha256": current.encoder.binding.binding_sha256,
            "query_sha256": SYNTHETIC_QUERY_SHA256,
            "checksum_validated": True,
            "dimension": 768,
            "inference_requests": 1,
            "library_authorized": False,
            "index_or_policy_audited": False,
            "activation": False,
            "service_management": False,
        }
    except Refused:
        raise
    except Exception:
        # Configuration, filesystem, and provider exceptions may contain
        # private paths, endpoint values, query text, vectors or credentials.
        raise Refused("readiness_unavailable") from None


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        print(json.dumps(PLAN, sort_keys=True, separators=(",", ":")))
        return 0

    parser = Parser(add_help=True, description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--config-sha256")
    try:
        args = parser.parse_args(arguments)
        if (not args.check or args.config is None or args.config_sha256 is None):
            raise Refused("invalid_arguments")
        report = _check(args.config, args.config_sha256)
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 0
    except Refused as error:
        print(json.dumps({"version": 1, "status": "refused", "error": error.code},
                         sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

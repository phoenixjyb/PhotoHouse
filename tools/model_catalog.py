#!/usr/bin/env python3
"""Check the offline model inventory without importing or contacting providers."""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path, PurePosixPath
import re

ROOT = Path(__file__).resolve().parents[1]
ROLES = frozenset({
    "vlm_caption", "assistant_asr", "memory_asr", "annotation_polish",
    "narrative", "title_suggestions", "assistant_tts", "face_detection",
    "face_embedding", "image_embedding", "video_embedding", "text_embedding", "image_tags",
})
MODES = {"http_service", "loopback_http", "bounded_child", "in_process"}
MAX_METADATA_BYTES = 512 * 1024
MAX_SOURCE_BYTES = 2 * 1024 * 1024
WEIGHT_SUFFIXES = {".onnx", ".safetensors", ".gguf", ".pt", ".pth", ".ckpt", ".bin", ".tflite", ".engine"}


class CatalogError(ValueError):
    """A fixed reason; never include private configuration or source contents."""


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise CatalogError("duplicate_json_key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise CatalogError("nonfinite_json")


def _read(root: Path, relative: str, limit: int) -> bytes:
    if (type(relative) is not str or not relative or "\\" in relative
            or any(ord(c) < 32 for c in relative)
            or any(p in {"", ".", ".."} for p in relative.split("/"))
            or PurePosixPath(relative).is_absolute() or ":" in relative):
        raise CatalogError("unsafe_source_path")
    path = root
    for part in relative.split("/"):
        path = path / part
        if path.is_symlink():
            raise CatalogError("symlink_source")
    try:
        if not path.is_file() or path.stat().st_size > limit:
            raise CatalogError("missing_or_oversized_source")
        payload = path.read_bytes()
    except OSError:
        raise CatalogError("unreadable_source") from None
    if len(payload) > limit:
        raise CatalogError("oversized_source")
    return payload


def _load(root: Path, name: str):
    try:
        return json.loads(_read(root, name, MAX_METADATA_BYTES).decode("utf-8"),
                          object_pairs_hook=_object_pairs,
                          parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError):
        raise CatalogError("invalid_catalog_json") from None


def verify(root: Path = ROOT) -> dict:
    root = Path(root).resolve()
    catalog = _load(root, "models/catalog.json")
    if (type(catalog) is not dict or type(catalog.get("schema")) is not int or catalog.get("schema") != 1
            or catalog.get("kind") != "offline-source-inventory"
            or catalog.get("weights_in_repository") is not False
            or catalog.get("runtime_controller") is not False):
        raise CatalogError("catalog_boundary")
    capabilities = catalog.get("capabilities")
    if (type(capabilities) is not list or len(capabilities) != len(ROLES)
            or any(type(role) is not dict or type(role.get("id")) is not str for role in capabilities)
            or {role.get("id") for role in capabilities} != ROLES):
        raise CatalogError("capability_inventory")
    trees = {}
    by_id = {}
    for role in capabilities:
        if (not isinstance(role.get("contract"), str) or not role["contract"]
                or not isinstance(role.get("purpose"), str) or not role["purpose"]
                or not isinstance(role.get("runtime_requirements"), list)
                or not role["runtime_requirements"]
                or not isinstance(role.get("execution_modes"), list)
                or not role["execution_modes"] or not set(role["execution_modes"]) <= MODES):
            raise CatalogError("capability_contract")
        adapters = role.get("adapters")
        if not isinstance(adapters, list) or not adapters:
            raise CatalogError("adapter_inventory")
        for adapter in adapters:
            if type(adapter) is not dict or set(adapter) != {"source", "symbol"}:
                raise CatalogError("adapter_reference")
            source, symbol = adapter["source"], adapter["symbol"]
            if (type(source) is not str or not source.startswith("server/")
                    or not source.endswith(".py") or type(symbol) is not str
                    or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", symbol) is None):
                raise CatalogError("adapter_reference")
            if source not in trees:
                try:
                    tree = ast.parse(_read(root, source, MAX_SOURCE_BYTES))
                except SyntaxError:
                    raise CatalogError("invalid_adapter_source") from None
                trees[source] = {node.name for node in tree.body
                                 if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))}
            if symbol not in trees[source]:
                raise CatalogError("adapter_symbol_missing")
        references = role.get("configuration_sources")
        if not isinstance(references, list) or not references:
            raise CatalogError("configuration_inventory")
        for source in references:
            if type(source) is not str or not source.startswith("server/"):
                raise CatalogError("configuration_reference")
            _read(root, source, MAX_SOURCE_BYTES)
        by_id[role["id"]] = role

    template = _load(root, "models/providers.example.json")
    if (type(template) is not dict or type(template.get("schema")) is not int or template.get("schema") != 1
            or template.get("kind") != "disabled-private-selection-template"
            or template.get("loaded_by_runtime") is not False):
        raise CatalogError("template_boundary")
    providers = template.get("providers")
    if (type(providers) is not list or len(providers) != len(ROLES)
            or any(type(provider) is not dict or type(provider.get("id")) is not str for provider in providers)
            or {provider.get("id") for provider in providers} != ROLES):
        raise CatalogError("template_inventory")
    for provider in providers:
        if set(provider) != {"id", "contract", "enabled", "adapter", "execution_mode",
                            "endpoint", "model", "model_version", "runtime_version",
                            "checkpoint_sha256", "license_source", "resource_budget"}:
            raise CatalogError("template_fields")
        role = by_id[provider["id"]]
        if (provider.get("enabled") is not False or provider.get("contract") != role["contract"]
                or provider.get("adapter") not in {a["symbol"] for a in role["adapters"]}
                or provider.get("execution_mode") not in role["execution_modes"]):
            raise CatalogError("template_adapter_mismatch")
        for field in ("endpoint", "model", "model_version", "runtime_version", "checkpoint_sha256", "license_source"):
            if field not in provider or provider[field] is not None:
                raise CatalogError("template_contains_installation")
        budget = provider.get("resource_budget")
        if (type(budget) is not dict or set(budget) != {
                "max_concurrent_requests", "ram_limit_mib", "vram_floor_mib", "deadline_seconds"}
                or any(value is not None for value in budget.values())):
            raise CatalogError("template_resource_budget")
    for path in (root / "models").rglob("*"):
        if path.suffix.lower() in WEIGHT_SUFFIXES:
            raise CatalogError("weights_in_source_directory")
    return {"status": "source_inventory_verified", "capabilities": sorted(ROLES),
            "adapter_sources_checked": len(trees), "runtime_controller": False,
            "availability": "not_probed", "model_quality": "not_evaluated",
            "providers_contacted": False, "weights_loaded": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        result = verify()
    except (CatalogError, TypeError, ValueError) as error:
        reason = str(error) if isinstance(error, CatalogError) else "invalid_catalog_shape"
        print(json.dumps({"status": "refused", "reason": reason}))
        return 1
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print("Model source inventory verified; runtime availability and quality not checked.")
        for role in result["capabilities"]:
            print("- " + role)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

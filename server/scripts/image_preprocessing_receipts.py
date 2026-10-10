"""Observe an already-created OpenCLIP evaluation preprocessing pipeline.

This module does not import torchvision, Pillow, torch, OpenCLIP, or model
weights. It records the inspected transform snapshot and its declared source
and package digests; the result is not native-runtime qualification. Transform
recognition uses reported Python module and class names in the trusted worker
process; those names are not cryptographic proofs of implementation identity.
"""
from __future__ import annotations

from collections import OrderedDict
from enum import Enum
import math
import re
from types import FunctionType
from typing import Any


_REQUIRED_PACKAGES = {"open_clip_torch", "torch", "torchvision", "Pillow", "numpy"}
_REQUIRED_SOURCES = {"decoder", "embedding_service", "worker"}
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_INTERPOLATION_NAMES = {
    "NEAREST", "NEAREST_EXACT", "BOX", "BILINEAR", "HAMMING", "BICUBIC", "LANCZOS",
}
_PIL_INTERPOLATION_VALUES = {
    "NEAREST": 0, "LANCZOS": 1, "BILINEAR": 2, "BICUBIC": 3,
    "BOX": 4, "HAMMING": 5,
}
_ALLOWED_TRANSFORMS = {
    ("torchvision.transforms.transforms", "Compose"): "compose",
    ("torchvision.transforms.transforms", "Resize"): "resize",
    ("torchvision.transforms.transforms", "CenterCrop"): "center_crop",
    ("torchvision.transforms.transforms", "ToTensor"): "to_tensor",
    ("torchvision.transforms.transforms", "Normalize"): "normalize",
}
_TORCH_MODULE_INTERNALS = {
    "_parameters", "_buffers", "_non_persistent_buffers_set", "_backward_hooks",
    "_backward_pre_hooks", "_forward_hooks", "_forward_hooks_with_kwargs",
    "_forward_hooks_always_called", "_forward_pre_hooks", "_forward_pre_hooks_with_kwargs",
    "_state_dict_hooks", "_state_dict_pre_hooks", "_load_state_dict_pre_hooks",
    "_load_state_dict_post_hooks", "_modules", "_is_full_backward_hook",
    "_compiled_call_impl",
}


class PreprocessingReceiptError(ValueError):
    """The supplied pipeline or metadata cannot be represented safely."""


def _fail(reason: str) -> None:
    raise PreprocessingReceiptError(reason)


def _mapping_of_strings(value: object, *, field: str, required: set[str], digests: bool):
    if type(value) is not dict or any(type(key) is not str for key in value):
        _fail(f"invalid_{field}")
    if not required <= set(value):
        _fail(f"missing_{field}")
    result = {}
    for key, item in value.items():
        if not key or len(key) > 80 or any(ord(ch) < 33 for ch in key):
            _fail(f"invalid_{field}")
        if type(item) is not str or not item or len(item) > (64 if digests else 128):
            _fail(f"invalid_{field}")
        if digests and _SHA256_RE.fullmatch(item) is None:
            _fail(f"invalid_{field}_sha256")
        result[key] = item
    return dict(sorted(result.items()))


def _instance_kind(value: object) -> str:
    cls = type(value)
    return _ALLOWED_TRANSFORMS.get((cls.__module__, cls.__name__), "")


def _attributes(value: object, expected: set[str], label: str) -> dict[str, Any]:
    try:
        attrs = vars(value)
    except TypeError:
        _fail(f"invalid_{label}_attributes")
    if type(attrs) is not dict:
        _fail(f"unexpected_{label}_attributes")
    training = attrs.get("training", None)
    if "training" in attrs and type(training) is not bool:
        _fail(f"invalid_{label}_training")
    config = {
        key: item for key, item in attrs.items()
        if key not in _TORCH_MODULE_INTERNALS and key != "training"
    }
    if set(config) != expected:
        _fail(f"unexpected_{label}_attributes")
    for key in set(attrs) & _TORCH_MODULE_INTERNALS:
        value = attrs[key]
        if value is None:
            continue
        if type(value) in (dict, OrderedDict, set, list) and not value:
            continue
        _fail(f"unexpected_{label}_attributes")
    if "training" in attrs:
        config["training"] = training
    return config


def _positive_int(value: object, label: str, maximum: int = 4096) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        _fail(f"invalid_{label}")
    return value


def _size(value: object, label: str, *, lengths: tuple[int, ...] = (1, 2)) -> list[int]:
    if type(value) is int:
        values = [value]
    elif type(value) in (list, tuple) and len(value) in lengths:
        values = list(value)
    else:
        _fail(f"invalid_{label}")
    return [_positive_int(item, label) for item in values]


def _interpolation(value: object) -> dict[str, str | int]:
    if not isinstance(value, Enum):
        _fail("invalid_resize_interpolation")
    enum_type = type(value)
    enum_source = (enum_type.__module__, enum_type.__name__)
    if enum_source not in {
        ("PIL.Image", "Resampling"),
        ("torchvision.transforms.functional", "InterpolationMode"),
    }:
        _fail("invalid_resize_interpolation")
    name = value.name
    enum_value = value.value
    if type(name) is not str or name not in _INTERPOLATION_NAMES:
        _fail("invalid_resize_interpolation")
    if type(enum_value) is str:
        if enum_value != name.lower():
            _fail("invalid_resize_interpolation")
    elif type(enum_value) is int:
        if _PIL_INTERPOLATION_VALUES.get(name) != enum_value:
            _fail("invalid_resize_interpolation")
    else:
        _fail("invalid_resize_interpolation")
    return {"name": name, "value": enum_value}


def _resize(attrs: dict[str, Any]) -> dict[str, Any]:
    training = attrs.pop("training", None)
    if set(attrs) != {"size", "max_size", "interpolation", "antialias"}:
        _fail("unexpected_resize_attributes")
    size = _size(attrs["size"], "resize_size")
    max_size = attrs["max_size"]
    if max_size is not None:
        max_size = _positive_int(max_size, "resize_max_size")
    antialias = attrs["antialias"]
    if antialias is not None and type(antialias) is not bool:
        _fail("invalid_resize_antialias")
    result = {
        "type": "Resize", "size": size, "max_size": max_size,
        "interpolation": _interpolation(attrs["interpolation"]), "antialias": antialias,
    }
    if training is not None:
        result["training"] = training
    return result


def _normalize(attrs: dict[str, Any]) -> dict[str, Any]:
    training = attrs.pop("training", None)
    if set(attrs) != {"mean", "std", "inplace"}:
        _fail("unexpected_normalize_attributes")
    mean, std = attrs["mean"], attrs["std"]
    if (type(mean) not in (list, tuple) or type(std) not in (list, tuple)
            or len(mean) != 3 or len(std) != 3):
        _fail("normalize_requires_three_channels")
    def channel(value: object, label: str, *, positive: bool = False) -> float:
        if type(value) not in (int, float):
            _fail(f"invalid_normalize_{label}")
        numeric = float(value)
        if not math.isfinite(numeric) or abs(numeric) > 10 or (positive and numeric <= 0):
            _fail(f"invalid_normalize_{label}")
        return numeric
    inplace = attrs["inplace"]
    if type(inplace) is not bool:
        _fail("invalid_normalize_inplace")
    result = {
        "type": "Normalize",
        "mean": [channel(item, "mean") for item in mean],
        "std": [channel(item, "std", positive=True) for item in std],
        "inplace": inplace,
    }
    if training is not None:
        result["training"] = training
    return result


def _observe_transform(value: object) -> dict[str, Any]:
    kind = _instance_kind(value)
    if not kind:
        if (type(value) is FunctionType and value.__module__ == "open_clip.transform"
                and value.__name__ == "_convert_to_rgb"):
            return {"type": "_convert_to_rgb"}
        _fail("unsupported_preprocessing_transform")
    if kind == "compose":
        _fail("nested_compose_refused")
    if kind == "resize":
        return _resize(_attributes(value, {"size", "max_size", "interpolation", "antialias"}, "resize"))
    if kind == "center_crop":
        attrs = _attributes(value, {"size"}, "center_crop")
        training = attrs.pop("training", None)
        result = {"type": "CenterCrop", "size": _size(attrs["size"], "center_crop_size")}
        if training is not None:
            result["training"] = training
        return result
    if kind == "to_tensor":
        attrs = _attributes(value, set(), "to_tensor")
        training = attrs.pop("training", None)
        result = {"type": "ToTensor"}
        if training is not None:
            result["training"] = training
        return result
    attrs = _attributes(value, {"mean", "std", "inplace"}, "normalize")
    return _normalize(attrs)


def observe_preprocessing(
    transform: object,
    *,
    package_versions: dict[str, str],
    source_digests: dict[str, str],
) -> dict[str, Any]:
    """Return a primitive snapshot of a bounded OpenCLIP evaluation pipeline.

    Transform types are matched by their exact defining module and class name;
    subclasses, stochastic operations, arbitrary callables, and nested Compose
    objects are refused. The caller can hash this result with ``recipe_sha256``.
    """
    if _instance_kind(transform) != "compose":
        _fail("openclip_compose_required")
    attrs = _attributes(transform, {"transforms"}, "compose")
    sequence = attrs["transforms"]
    if type(sequence) not in (list, tuple) or not 1 <= len(sequence) <= 16:
        _fail("invalid_compose_transforms")
    observed = [_observe_transform(item) for item in sequence]
    types = [item["type"] for item in observed]
    if (types.count("_convert_to_rgb") != 1 or types.count("Resize") != 1
            or types.count("CenterCrop") != 1 or types.count("ToTensor") != 1
            or types.count("Normalize") != 1):
        _fail("required_evaluation_transforms_once")
    to_tensor_index = types.index("ToTensor")
    if to_tensor_index >= types.index("Normalize"):
        _fail("to_tensor_must_precede_normalize")
    if (types.index("_convert_to_rgb") >= to_tensor_index
            or types.index("Resize") >= to_tensor_index
            or types.index("CenterCrop") >= to_tensor_index):
        _fail("rgb_resize_crop_must_precede_to_tensor")
    if types.index("Normalize") != len(types) - 1:
        _fail("normalize_must_be_last")
    packages = _mapping_of_strings(
        package_versions, field="package_versions", required=_REQUIRED_PACKAGES, digests=False,
    )
    sources = _mapping_of_strings(
        source_digests, field="source_digests", required=_REQUIRED_SOURCES, digests=True,
    )
    return {
        "schema": "photohouse.image_preprocessing_recipe.v1",
        "input_profile": "bounded_rgb_jpeg",
        "output_profile": "float32_unit_l2",
        "package_versions": packages,
        "source_digests": sources,
        "transforms": observed,
    }

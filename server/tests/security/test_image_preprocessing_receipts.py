from enum import Enum
import hashlib
import json
from pathlib import Path
import sys
from collections import OrderedDict

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import image_preprocessing_receipts as receipts


TRANSFORMS_MODULE = "torchvision.transforms.transforms"


def _synthetic_class(name, module=TRANSFORMS_MODULE):
    return type(name, (), {"__module__": module})


def _instance(name, **attrs):
    value = _synthetic_class(name)()
    vars(value).update(attrs)
    return value


class InterpolationMode(Enum):
    BICUBIC = "bicubic"
    BILINEAR = "bilinear"


InterpolationMode.__module__ = "torchvision.transforms.functional"


def _convert_to_rgb(image):
    return image


_convert_to_rgb.__module__ = "open_clip.transform"


def _packages(**overrides):
    values = {
        "open_clip_torch": "2.29.0", "torch": "2.4.1", "torchvision": "0.19.1",
        "Pillow": "10.4.0", "numpy": "2.1.1",
    }
    return {**values, **overrides}


def _sources(**overrides):
    values = {"decoder": "a" * 64, "embedding_service": "b" * 64, "worker": "c" * 64}
    return {**values, **overrides}


def _pipeline(*, size=(224, 224), mean=(0.48, 0.46, 0.41),
              std=(0.27, 0.26, 0.28), interpolation=InterpolationMode.BICUBIC,
              antialias=True, inplace=False):
    transforms = [
        _instance("Resize", size=size, max_size=None, interpolation=interpolation, antialias=antialias),
        _instance("CenterCrop", size=(224, 224)),
        _convert_to_rgb,
        _instance("ToTensor"),
        _instance("Normalize", mean=mean, std=std, inplace=inplace),
    ]
    return _instance("Compose", transforms=transforms)


def _torch_module_state(value, *, training=True):
    vars(value).update({
        "training": training,
        "_parameters": OrderedDict(),
        "_buffers": OrderedDict(),
        "_non_persistent_buffers_set": set(),
        "_backward_hooks": OrderedDict(),
        "_backward_pre_hooks": OrderedDict(),
        "_forward_hooks": OrderedDict(),
        "_forward_hooks_with_kwargs": OrderedDict(),
        "_forward_hooks_always_called": OrderedDict(),
        "_forward_pre_hooks": OrderedDict(),
        "_forward_pre_hooks_with_kwargs": OrderedDict(),
        "_state_dict_hooks": OrderedDict(),
        "_state_dict_pre_hooks": OrderedDict(),
        "_load_state_dict_pre_hooks": OrderedDict(),
        "_load_state_dict_post_hooks": OrderedDict(),
        "_modules": OrderedDict(),
        "_is_full_backward_hook": None,
        "_compiled_call_impl": None,
    })
    return value


def _module_pipeline(*, training=True):
    transforms = [
        _torch_module_state(_instance(
            "Resize", size=(224, 224), max_size=None,
            interpolation=InterpolationMode.BICUBIC, antialias=True,
        ), training=training),
        _torch_module_state(_instance("CenterCrop", size=(224, 224)), training=training),
        _convert_to_rgb,
        _instance("ToTensor"),
        _torch_module_state(_instance(
            "Normalize", mean=(0.48, 0.46, 0.41), std=(0.27, 0.26, 0.28), inplace=False,
        ), training=training),
    ]
    return _instance("Compose", transforms=transforms)


def _observe(transform=None, *, package_versions=None, source_digests=None):
    return receipts.observe_preprocessing(
        _pipeline() if transform is None else transform,
        package_versions=_packages() if package_versions is None else package_versions,
        source_digests=_sources() if source_digests is None else source_digests,
    )


def _digest(recipe):
    body = json.dumps(recipe, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(body).hexdigest()


def test_observer_returns_primitive_ordered_snapshot_without_importing_providers():
    recipe = _observe()

    assert recipe["schema"] == "photohouse.image_preprocessing_recipe.v1"
    assert recipe["input_profile"] == "bounded_rgb_jpeg"
    assert recipe["output_profile"] == "float32_unit_l2"
    assert [item["type"] for item in recipe["transforms"]] == [
        "Resize", "CenterCrop", "_convert_to_rgb", "ToTensor", "Normalize",
    ]
    assert recipe["transforms"][0]["interpolation"] == {"name": "BICUBIC", "value": "bicubic"}
    assert recipe["transforms"][-1]["mean"] == [0.48, 0.46, 0.41]


def test_observer_accepts_realistic_torch_module_bookkeeping_and_records_training():
    recipe = _observe(_module_pipeline(training=True))

    assert recipe["transforms"][0]["training"] is True
    assert recipe["transforms"][1]["training"] is True
    assert recipe["transforms"][-1]["training"] is True
    assert _digest(recipe) != _digest(_observe(_module_pipeline(training=False)))


@pytest.mark.parametrize(
    "change",
    [
        {"size": (256, 256)},
        {"mean": (0.5, 0.5, 0.5)},
        {"std": (0.25, 0.25, 0.25)},
        {"interpolation": InterpolationMode.BILINEAR},
        {"antialias": False},
        {"inplace": True},
    ],
)
def test_digest_changes_when_evaluation_recipe_changes(change):
    original = _observe()
    altered = _observe(_pipeline(**change))

    assert _digest(altered) != _digest(original)


def test_digest_changes_when_declared_package_or_source_changes():
    original = _observe()
    package_changed = _observe(package_versions=_packages(torch="2.5.0"))
    source_changed = _observe(source_digests=_sources(worker="d" * 64))

    assert _digest(package_changed) != _digest(original)
    assert _digest(source_changed) != _digest(original)


def test_rejects_unknown_subclass_nested_compose_and_extra_attributes():
    resize_base = _synthetic_class("Resize")
    subclass = type("ResizeSubclass", (resize_base,), {"__module__": TRANSFORMS_MODULE})
    with pytest.raises(receipts.PreprocessingReceiptError, match="unsupported_preprocessing_transform"):
        _observe(_instance("Compose", transforms=[subclass()]))
    with pytest.raises(receipts.PreprocessingReceiptError, match="nested_compose_refused"):
        _observe(_instance("Compose", transforms=[_instance("Compose", transforms=[])]))
    bad_to_tensor = _instance("ToTensor", surprise=True)
    with pytest.raises(receipts.PreprocessingReceiptError, match="unexpected_to_tensor_attributes"):
        _observe(_instance("Compose", transforms=[bad_to_tensor, _instance("Normalize", mean=(0, 0, 0), std=(1, 1, 1), inplace=False)]))


@pytest.mark.parametrize(
    "transform",
    [
        _pipeline(size=(0, 224)),
        _pipeline(size=(5000, 224)),
        _pipeline(mean=(0.0, float("nan"), 0.0)),
        _pipeline(std=(1.0, 0.0, 1.0)),
        _pipeline(interpolation="bicubic"),
        _pipeline(antialias=1),
        _pipeline(inplace=1),
    ],
)
def test_rejects_malformed_resize_and_normalize_parameters(transform):
    with pytest.raises(receipts.PreprocessingReceiptError):
        _observe(transform)


def test_to_tensor_must_precede_normalize():
    pipeline = _pipeline()
    pipeline.transforms[3], pipeline.transforms[4] = pipeline.transforms[4], pipeline.transforms[3]
    with pytest.raises(receipts.PreprocessingReceiptError, match="to_tensor_must_precede_normalize"):
        _observe(pipeline)


def test_preprocessing_stages_must_precede_tensor_and_normalize_must_be_last():
    resize = _instance("Resize", size=(224, 224), max_size=None, interpolation=InterpolationMode.BICUBIC, antialias=True)
    crop = _instance("CenterCrop", size=(224, 224))
    converter = _convert_to_rgb
    tensor = _instance("ToTensor")
    normalize = _instance("Normalize", mean=(0, 0, 0), std=(1, 1, 1), inplace=False)
    with pytest.raises(receipts.PreprocessingReceiptError, match="rgb_resize_crop_must_precede_to_tensor"):
        _observe(_instance("Compose", transforms=[resize, crop, tensor, converter, normalize]))
    with pytest.raises(receipts.PreprocessingReceiptError, match="to_tensor_must_precede_normalize"):
        _observe(_instance("Compose", transforms=[resize, crop, converter, normalize, tensor]))


def test_resize_and_center_crop_must_each_appear_once():
    pipeline = _pipeline()
    pipeline.transforms.append(_instance("CenterCrop", size=(224, 224)))
    with pytest.raises(receipts.PreprocessingReceiptError, match="required_evaluation_transforms_once"):
        _observe(pipeline)


def test_requires_explicit_bounded_version_and_source_metadata():
    with pytest.raises(receipts.PreprocessingReceiptError, match="missing_package_versions"):
        _observe(package_versions={"torch": "2.4.1"})
    with pytest.raises(receipts.PreprocessingReceiptError, match="invalid_source_digests_sha256"):
        _observe(source_digests=_sources(worker="not-a-digest"))
    with pytest.raises(receipts.PreprocessingReceiptError, match="invalid_package_versions"):
        _observe(package_versions=_packages(torch=2.4))

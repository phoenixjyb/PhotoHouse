"""Explicit optional byte-buffer kernel; no installation or activation behavior."""
import importlib
import os


def backend():
    engine = os.environ.get("PHOTOHOUSE_VECTOR_ENGINE", "python")
    if engine == "python":
        return None
    if engine != "rust":
        raise ValueError("invalid_vector_engine")
    return load_kernel()


def load_kernel():
    """Load a separately selected consumer's exact base byte-buffer capability."""
    try:
        module = importlib.import_module("photohouse_vector_kernel")
    except ImportError:
        raise ValueError("vector_kernel_unavailable") from None
    if (type(getattr(module, "KERNEL_VERSION", None)) is not int or module.KERNEL_VERSION != 1
            or getattr(module, "POLICY_FINGERPRINT", None) != "canonical-f32-fsum-v1:4096:4194304"):
        raise ValueError("vector_kernel_identity_mismatch")
    return module


def visual_backend():
    engine = os.environ.get("PHOTOHOUSE_VISUAL_ENGINE", "python")
    if engine == "python":
        return None
    if engine != "rust":
        raise ValueError("invalid_visual_engine")
    module = load_kernel()
    if (getattr(module, "VISUAL_POLICY_FINGERPRINT", None)
            != "best-seed-fsum-v1:24:512:4096:4194304"
            or not callable(getattr(module, "best_seed", None))):
        raise ValueError("visual_kernel_identity_mismatch")
    return module

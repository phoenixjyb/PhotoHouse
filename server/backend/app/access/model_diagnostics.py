"""Privacy-safe summaries of bounded local model-provider output.

This module is deliberately pure: it performs no logging, imports no provider
client, and never returns matched text. Its signals describe recognized log
phrases only; a generic CUDA error is not evidence of its root cause.
"""
from __future__ import annotations

import re

MAX_CAPTURE_BYTES = 65_536
MAX_CUDA_NUMERIC_CODES = 8

_SIGNAL_PATTERNS: tuple[tuple[str, tuple[bytes, ...]], ...] = (
    ("cuda_failure", (b"cuda error", b"cuda_error", b"cuda failure",
                       b"cuda initialization failed")),
    ("gpu_not_compatible", (b"no compatible gpu", b"unsupported gpu",
                             b"unsupported compute capability")),
    ("runner_exited", (b"runner process has terminated", b"runner process exited",
                        b"model runner exited")),
    ("model_load_failed", (b"failed to load model", b"error loading model",
                            b"unable to load model", b"model load failed")),
)

_CUDA_SPECIFIC_PATTERNS: tuple[tuple[str, tuple[bytes, ...]], ...] = (
    ("illegal_address", (b"cudaerrorillegaladdress", b"cuda_error_illegal_address",
                          b"illegal memory access")),
    ("device_side_assert", (b"device-side assert", b"device side assert")),
    ("launch_failure", (b"cudaerrorlaunchfailure", b"cuda_error_launch_failure",
                         b"launch failed", b"launch failure")),
    ("no_kernel_image", (b"no kernel image is available", b"no kernel image available")),
    ("insufficient_driver", (b"cudaerrorinsufficientdriver",
                              b"cuda_error_insufficient_driver", b"insufficient driver",
                              b"driver version is insufficient")),
    ("out_of_memory", (b"cuda out of memory", b"cuda_error_out_of_memory",
                        b"cudaerroroutofmemory", b"cublas_status_alloc_failed",
                        b"cuda allocation failed")),
)

_CUDA_NUMBER_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    rb"\bcuda_error_(\d{1,4})\b",
    rb"\bcuda(?:\s+error|_error)(?:\s*[:=])?\s*(\d{1,4})\b",
    rb"\bcuda_error_[a-z0-9_]+\s*\(?(\d{1,4})\)?\b",
    rb"\bcudaerror[a-z]*\s*\(?(\d{1,4})\)?\b",
))


def summarize_model_output(raw: bytes) -> dict[str, object]:
    """Summarize only recognized fixed signals and small numeric CUDA codes.

    Inputs longer than ``MAX_CAPTURE_BYTES`` are scanned only through the
    bounded prefix and reported with ``overflow=True``. ``captured_bytes`` is
    the input length, while no portion of the input is returned.
    """
    if type(raw) is not bytes:
        raise TypeError("raw model output must be bytes")

    sample = raw[:MAX_CAPTURE_BYTES].lower()
    signals = [name for name, needles in _SIGNAL_PATTERNS
               if any(needle in sample for needle in needles)]
    specific = [name for name, needles in _CUDA_SPECIFIC_PATTERNS
                if any(needle in sample for needle in needles)]
    codes: set[int] = set()
    for pattern in _CUDA_NUMBER_PATTERNS:
        for match in pattern.finditer(sample):
            codes.add(int(match.group(1)))
    return {
        "captured_bytes": len(raw),
        "signal_codes": signals,
        "cuda_numeric_codes": sorted(codes)[:MAX_CUDA_NUMERIC_CODES],
        "cuda_specific_signals": specific,
        "overflow": len(raw) > MAX_CAPTURE_BYTES,
    }

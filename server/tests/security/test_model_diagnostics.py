from __future__ import annotations

import unittest

from app.access.model_diagnostics import MAX_CAPTURE_BYTES, summarize_model_output


class ModelDiagnosticsTests(unittest.TestCase):
    def test_recognizes_cuda_variants_and_returns_only_fixed_codes(self):
        raw = (
            b"CUDA error: 700: illegal memory access\n"
            b"CUDA_ERROR_LAUNCH_FAILURE (719)\n"
            b"cudaErrorIllegalAddress\n"
            b"device-side assert triggered; launch failed"
        )
        result = summarize_model_output(raw)
        self.assertEqual(result, {
            "captured_bytes": len(raw),
            "signal_codes": ["cuda_failure"],
            "cuda_numeric_codes": [700, 719],
            "cuda_specific_signals": ["illegal_address", "device_side_assert", "launch_failure"],
            "overflow": False,
        })
        self.assertNotIn(raw.decode(), repr(result))

    def test_recognizes_cuda_environment_and_runner_failures_without_claiming_cause(self):
        raw = (b"CUDA_ERROR_OUT_OF_MEMORY; insufficient driver; no kernel image available; "
               b"runner process has terminated after model load failed")
        result = summarize_model_output(raw)
        self.assertEqual(result["signal_codes"], ["cuda_failure", "runner_exited", "model_load_failed"])
        self.assertEqual(result["cuda_specific_signals"], [
            "no_kernel_image", "insufficient_driver", "out_of_memory",
        ])
        # None of these summaries infer that the generic CUDA marker is OOM.
        self.assertNotIn("memory_shortage", result["signal_codes"])
        self.assertEqual(result["cuda_numeric_codes"], [])

    def test_codes_are_sorted_unique_bounded_and_ignore_out_of_range_values(self):
        raw = b" ".join(f"CUDA error: {n}".encode() for n in
                         (9, 3, 9, 700, 42, 6, 5, 4, 3, 2, 1, 10000))
        result = summarize_model_output(raw)
        self.assertEqual(result["cuda_numeric_codes"], [1, 2, 3, 4, 5, 6, 9, 42])

    def test_oversize_input_scans_only_cap_and_never_returns_private_text(self):
        private = b"user prompt /private/family/photo-123 https://private.invalid token=secret"
        raw = b"x" * MAX_CAPTURE_BYTES + b" CUDA error: 719 " + private
        result = summarize_model_output(raw)
        self.assertEqual(result["captured_bytes"], len(raw))
        self.assertTrue(result["overflow"])
        self.assertEqual(result["signal_codes"], [])
        self.assertEqual(result["cuda_numeric_codes"], [])
        self.assertEqual(result["cuda_specific_signals"], [])
        serialized = repr(result)
        for marker in ("user prompt", "/private/family", "photo-123", "private.invalid", "secret"):
            self.assertNotIn(marker, serialized)

    def test_wrong_types_are_rejected(self):
        for raw in (None, "CUDA error: 700", bytearray(b"CUDA error: 700"), memoryview(b"x")):
            with self.subTest(raw_type=type(raw).__name__), self.assertRaises(TypeError):
                summarize_model_output(raw)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "model_gpu_evidence", ROOT / "scripts" / "model_gpu_evidence.py"
)
gpu_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gpu_evidence)

GPU_A = "GPU-01324550-EBC9-AFF9-A14E-A25441413492"
GPU_B = "GPU-10203040-5060-7080-90AB-CDEF12345678"


class ModelGPUEvidenceTests(unittest.TestCase):
    def assert_code(self, code, *args):
        with self.assertRaises(gpu_evidence.GPUEvidenceError) as raised:
            gpu_evidence.qualify_owned_compute_pids(*args)
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(str(raised.exception), code)

    def test_maps_only_owned_compute_pids_and_ignores_foreign_processes(self):
        sample = (
            "\r\n"
            f"{GPU_B}, 9000\r\n\r\n"
            f"{GPU_A}, 101\r\n"
            f"{GPU_A}, 101\r\n"  # identical duplicate is harmless
            f"{GPU_A}, 103\r\n"
        ).encode("utf-8")
        evidence = gpu_evidence.qualify_owned_compute_pids(
            sample, frozenset({101, 102, 103}), GPU_A.lower()
        )
        self.assertEqual(evidence, {101: GPU_A, 103: GPU_A})
        self.assertEqual(list(evidence), [101, 103])
        self.assertNotIn(102, evidence)  # owned helper need not be a compute process
        self.assertNotIn(9000, evidence)

    def test_owned_child_reported_on_both_gpus_is_refused(self):
        sample = f"{GPU_A}, 101\n{GPU_B}, 101\n"
        self.assert_code(
            "gpu_owned_process_on_unexpected_gpu", sample, {101}, GPU_A
        )

    def test_foreign_pid_on_multiple_gpus_is_ignored(self):
        sample = f"{GPU_A}, 9000\n{GPU_B}, 9000\n{GPU_A}, 101\n"
        self.assertEqual(
            gpu_evidence.qualify_owned_compute_pids(sample, {101}, GPU_A),
            {101: GPU_A},
        )

    def test_stale_output_without_owned_compute_match_is_refused(self):
        sample = f"{GPU_A}, 9000\n{GPU_B}, 101\n"
        self.assert_code(
            "gpu_owned_compute_match_missing", sample, {102}, GPU_A
        )

    def test_output_size_is_bounded_before_parsing(self):
        sample = b" " * (gpu_evidence.MAX_NVIDIA_SMI_OUTPUT_BYTES + 1)
        self.assert_code("gpu_output_oversize", sample, {1}, GPU_A)
        multibyte_sample = "é" * (gpu_evidence.MAX_NVIDIA_SMI_OUTPUT_BYTES // 2 + 1)
        self.assert_code("gpu_output_oversize", multibyte_sample, {1}, GPU_A)

    def test_invalid_utf8_is_refused_without_echoing_output(self):
        self.assert_code("gpu_output_invalid_utf8", b"\xff", {1}, GPU_A)

    def test_malformed_rows_and_pids_are_refused(self):
        for sample in (
            f"{GPU_A}, 1, unexpected\n",
            f'"{GPU_A}, 1\n',  # unterminated CSV quote
            f"not-a-gpu, 1\n",
            f"{GPU_A}, 0\n",
            f"{GPU_A}, 4294967296\n",
            f"{GPU_A}, +1\n",
        ):
            with self.subTest(sample=sample):
                self.assert_code("gpu_output_malformed", sample, {1}, GPU_A)

    def test_invalid_expected_gpu_and_owned_pid_set_are_refused(self):
        self.assert_code("gpu_expected_uuid_invalid", f"{GPU_A}, 1\n", {1}, "gpu-1")
        for owned in (set(), {True}, {0}, {-1}, {2**32}):
            with self.subTest(owned=owned):
                self.assert_code("gpu_owned_pid_set_invalid", f"{GPU_A}, 1\n", owned, GPU_A)
        self.assert_code("gpu_owned_pid_set_invalid", f"{GPU_A}, 1\n", [1], GPU_A)
        too_many = frozenset(range(1, gpu_evidence.MAX_OWNED_JOB_PIDS + 2))
        self.assert_code("gpu_owned_pid_set_invalid", f"{GPU_A}, 1\n", too_many, GPU_A)


if __name__ == "__main__":
    unittest.main()

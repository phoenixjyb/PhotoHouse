"""Entry-point checks for the source-only vector erasure qualification runner."""
import os
from pathlib import Path, PureWindowsPath
import sys
import tempfile
import unittest
import json
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import qualify_vector_erasure as qualification
import bounded_windows_job as controller


class VectorErasureQualificationTests(unittest.TestCase):
    def test_windows_fixture_budget_refuses_before_output_or_child_creation(self):
        with tempfile.TemporaryDirectory(prefix="vector-path-budget-") as temporary:
            parent = Path(temporary).resolve() / ("p" * 80)
            parent.mkdir(mode=0o700)
            target = parent / "review"
            check = qualification._check_windows_paths
            with patch.object(qualification, "_check_windows_paths", side_effect=lambda path: check(path, windows=True)), \
                    patch.object(qualification, "_private_dir") as mkdir, \
                    patch.object(controller, "run_bounded") as launch:
                for entry in (qualification.run, qualification._bounded_report):
                    with self.assertRaisesRegex(ValueError, "windows_fixture_path_too_long"):
                        entry(target)
                mkdir.assert_not_called()
                launch.assert_not_called()
            self.assertFalse(target.exists())

    def test_windows_path_budget_counts_utf16_and_all_digest_names(self):
        # The longest path is the completed vector, including its 64-char
        # identity directory and 64-char record filename, in the first case.
        tail = PureWindowsPath("complete-and-crash/vectors/image-vectors") / ("a"*64) / ("a"*64+".npy")
        root = PureWindowsPath("C:/" + "p"*(259 - len(str(tail)) - 4))
        self.assertEqual(len(str(root / tail)), 259)
        qualification._check_windows_paths(root, windows=True)
        with self.assertRaisesRegex(ValueError, "windows_fixture_path_too_long"):
            qualification._check_windows_paths(PureWindowsPath(str(root)+"x"), windows=True)
        # One non-BMP character occupies two UTF-16 units, not one.
        with self.assertRaisesRegex(ValueError, "windows_fixture_path_too_long"):
            qualification._check_windows_paths(PureWindowsPath(str(root)[:-1]+"\U0001f3e0"), windows=True)

    def test_fixture_failure_retains_only_safe_fields_and_parent_surfaces_them(self):
        with tempfile.TemporaryDirectory(prefix="vector-safe-failure-") as temporary:
            parent = Path(temporary).resolve()
            parent.chmod(0o700)
            target = parent / "review"
            error = OSError("private-recording-name and private-endpoint")
            error.winerror = 206
            with patch.object(qualification, "_case_crash", side_effect=error):
                with self.assertRaises(OSError) as raised:
                    qualification.run(target)
            self.assertIs(raised.exception, error)
            receipt = qualification._read_failure(target)
            self.assertEqual(receipt, {"status": "failed", "source_only": True,
                "phase": "complete-and-crash", "exception_class": "OSError", "winerror": 206})
            self.assertNotIn("private-", (target / "qualification-failure.json").read_text())
            # A separate new target belongs to the simulated supervised child.
            supervised = parent / "supervised"
            def fail_child(*args, **kwargs):
                supervised.mkdir(mode=0o700)
                qualification._failure_receipt(supervised, "complete-and-crash", error)
                return 1
            with patch.dict(os.environ, {"SystemRoot": "synthetic-system"}), \
                    patch.object(controller, "WindowsAPI", return_value=object()), \
                    patch.object(controller, "run_bounded", side_effect=fail_child):
                with self.assertRaisesRegex(controller.CheckRefused, '"winerror":206'):
                    qualification._bounded_report(supervised)

    def test_diagnostic_failure_preserves_original_error_and_existing_receipt(self):
        with tempfile.TemporaryDirectory(prefix="vector-diagnostic-preserve-") as temporary:
            parent = Path(temporary).resolve()
            parent.chmod(0o700)
            target = parent / "review"
            error = RuntimeError("fixture refused")
            with patch.object(qualification, "_case_crash", side_effect=error), \
                    patch.object(qualification, "_failure_receipt", side_effect=OSError("receipt refused")):
                with self.assertRaises(RuntimeError) as raised:
                    qualification.run(target)
            self.assertIs(raised.exception, error)
            qualification._failure_receipt(target, "complete-and-crash", error)
            before = (target / "qualification-failure.json").read_bytes()
            with self.assertRaises(FileExistsError):
                qualification._failure_receipt(target, "catalog-restore", ValueError("another failure"))
            self.assertEqual((target / "qualification-failure.json").read_bytes(), before)

    def test_report_write_failure_retains_failed_status_and_partial_report(self):
        with tempfile.TemporaryDirectory(prefix="vector-report-failure-") as temporary:
            parent = Path(temporary).resolve()
            parent.chmod(0o700)
            target = parent / "review"
            real_dump = json.dump
            error = OSError("private report destination")
            def fail_report(value, stream, **kwargs):
                if "cases_passed" in value:
                    stream.write('{"partial":')
                    raise error
                return real_dump(value, stream, **kwargs)
            with patch.object(qualification.json, "dump", side_effect=fail_report):
                with self.assertRaises(OSError) as raised:
                    qualification.run(target)
            self.assertIs(raised.exception, error)
            self.assertEqual((target / "qualification-report.json").read_text(), '{"partial":')
            self.assertEqual(qualification._read_failure(target)["phase"], "report")

    def test_malformed_failure_receipts_cannot_surface_private_messages(self):
        with tempfile.TemporaryDirectory(prefix="vector-malformed-failure-") as temporary:
            target = Path(temporary).resolve()
            target.chmod(0o700)
            path = target / "qualification-failure.json"
            for raw in (b'{"message":"private-name"}', b"["*2000+b"]"*2000,
                        b"x"*4097, b'{"status":"failed","source_only":true,"phase":"complete-and-crash",'
                        b'"exception_class":"OSError","winerror":true}'):
                path.write_bytes(raw)
                path.chmod(0o600)
                self.assertIsNone(qualification._read_failure(target))

    def test_supervisor_pins_limits_and_excludes_inherited_provider_settings(self):
        with tempfile.TemporaryDirectory(prefix="vector-supervisor-") as temporary:
            parent = Path(temporary).resolve()
            parent.chmod(0o700)
            target = parent / "candidate"
            report = {"source_only": True, "models_loaded": False, "services_changed": False,
                      "native_windows": True, "power_loss_qualified": False,
                      "cases_passed": ["complete_manifest_catalog_and_quarantine_link_process_recovery",
                          "restore_older_primary_from_archived_closure_and_resume", "corrupt_quarantine_refused"]}
            def fake_run(api, executable, argv, environment, cwd, **limits):
                self.assertEqual(limits, {"timeout_seconds": 900, "memory_limit": 2*1024**3,
                                         "process_limit": 4, "minimum_free_ram": 8*1024**3})
                self.assertEqual(argv[:3], [executable, "-I", "-B"])
                self.assertIn("--bounded-child", argv)
                self.assertEqual(cwd, str(parent))
                self.assertNotIn("OLLAMA_MODEL", environment)
                self.assertEqual(environment["PHOTOHOUSE_GENERATED_QUALIFICATION_CHILD"], "1")
                self.assertEqual(environment["PHOTOHOUSE_NO_DOTENV"], "1")
                target.mkdir(mode=0o700)
                fd = os.open(target / "qualification-report.json", os.O_CREAT|os.O_EXCL|os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w") as stream:json.dump(report, stream)
                return 0
            with patch.dict(os.environ, {"SystemRoot": "synthetic-system", "OLLAMA_MODEL": "ignored"}), \
                    patch.object(controller, "WindowsAPI", return_value=object()), \
                    patch.object(controller, "run_bounded", side_effect=fake_run):
                self.assertEqual(qualification._bounded_report(target), report)

    def test_supervisor_nonzero_child_refuses_and_child_flag_requires_controller(self):
        with tempfile.TemporaryDirectory(prefix="vector-supervisor-failure-") as temporary:
            parent = Path(temporary).resolve()
            parent.chmod(0o700)
            target = parent / "candidate"
            with patch.dict(os.environ, {"SystemRoot": "synthetic-system"}), \
                    patch.object(controller, "WindowsAPI", return_value=object()), \
                    patch.object(controller, "run_bounded", return_value=23):
                with self.assertRaises(controller.CheckRefused):
                    qualification._bounded_report(target)
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ValueError):
                    qualification.main(["--out", str(target), "--bounded-child"])
            self.assertFalse(target.exists())

    def test_generated_source_only_qualification(self):
        with tempfile.TemporaryDirectory(prefix="vector-erasure-qualification-") as temporary:
            parent = Path(temporary).resolve()
            if os.name != "nt":
                parent.chmod(0o700)
            output = parent / "review"
            report = qualification.run(output)
            self.assertTrue(report["source_only"])
            self.assertFalse(report["models_loaded"])
            self.assertFalse(report["services_changed"])
            self.assertFalse(report["power_loss_qualified"])
            self.assertEqual(len(report["cases_passed"]), 3)
            self.assertTrue(output.is_dir())
            self.assertTrue((output / "qualification-report.json").is_file())
            self.assertTrue((output / "complete-and-crash" / "catalog").is_dir())
            self.assertTrue((output / "catalog-restore" / "restored-primary.sqlite").is_file())

    def test_existing_output_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="vector-erasure-existing-") as temporary:
            parent = Path(temporary).resolve()
            if os.name != "nt":
                parent.chmod(0o700)
            output = parent / "existing"
            output.mkdir()
            with self.assertRaises(ValueError):
                qualification.run(output)

    def test_nonprivate_parent_is_refused(self):
        with tempfile.TemporaryDirectory(prefix="vector-erasure-parent-") as temporary:
            parent = Path(temporary).resolve()
            if os.name != "nt":
                parent.chmod(0o755)
                with self.assertRaises(ValueError):
                    qualification.run(parent / "review")
            else:
                with patch.object(qualification, "require_private_directory", side_effect=ValueError):
                    with self.assertRaises(ValueError):
                        qualification.run(parent / "review")
            self.assertFalse((parent / "review").exists())


if __name__ == "__main__":
    unittest.main()

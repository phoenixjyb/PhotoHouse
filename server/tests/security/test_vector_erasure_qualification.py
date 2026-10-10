"""Entry-point checks for the source-only vector erasure qualification runner."""
import os
from pathlib import Path
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

import json
import struct
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools.android_ui_qualification import (
    ABI, API_LEVEL, QA_PACKAGE, SCREENSHOTS, SERIAL, TEST_CLASS,
    QualificationError, _run, device_rows, package_from_badging,
    parse_instrumentation, validate_png,
)


class AndroidUiQualificationTests(unittest.TestCase):
    def test_fixed_qa_identity_and_exact_fixture_scope(self):
        self.assertEqual((SERIAL, API_LEVEL, ABI, QA_PACKAGE),
                         ("emulator-5560", "34", "x86_64", "dev.photohouse.connected.qa"))
        self.assertEqual(len(SCREENSHOTS), 7)
        self.assertEqual(len(set(SCREENSHOTS)), 7)
        self.assertIn("AssistantSceneUiTest", TEST_CLASS)
        self.assertEqual(TEST_CLASS.count(","), 2)
        self.assertNotIn("*", TEST_CLASS)

    def test_package_reader_rejects_ambiguous_or_unexpected_badging(self):
        self.assertEqual(package_from_badging("package: name='dev.photohouse.connected.qa' versionCode='75'"),
                         "dev.photohouse.connected.qa")
        self.assertIsNone(package_from_badging("package: name='a'\npackage: name='b'"))
        self.assertIsNone(package_from_badging("badging unavailable"))

    def test_device_rows_keeps_serial_and_state_explicit(self):
        self.assertEqual(device_rows("List of devices attached\nemulator-5560\tdevice\n"),
                         [("emulator-5560", "device")])
        self.assertEqual(device_rows("List of devices attached\nphysical-123\tdevice\n"),
                         [("physical-123", "device")])

    def test_png_signature_and_bounded_dimensions(self):
        png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 1080, 1920)
        self.assertEqual(validate_png(png), (1080, 1920))
        with self.assertRaisesRegex(QualificationError, "png_invalid"):
            validate_png(b"not a png")
        with self.assertRaisesRegex(QualificationError, "dimensions_invalid"):
            validate_png(b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + struct.pack(">II", 0, 99))

    def test_instrumentation_summary_requires_exact_seven_complete_passes(self):
        lines = []
        for index in range(1, 8):
            fields = {"current": str(index), "numtests": "7", "id": "AndroidJUnitRunner",
                      "test": f"test{index}", "class": "dev.photohouse.connected.FixtureUiTest"}
            for code in (1, 0):
                lines.extend(f"INSTRUMENTATION_STATUS: {key}={value}" for key, value in fields.items())
                lines.append(f"INSTRUMENTATION_STATUS_CODE: {code}")
        lines.extend(["OK (7 tests)", "INSTRUMENTATION_CODE: -1", ""])
        result = parse_instrumentation("\n".join(lines).encode())
        self.assertEqual((result["status"], result["passed"], result["tests"]), ("passed", 7, 7))
        with self.assertRaisesRegex(QualificationError, "strict_instrumentation_report_failed"):
            parse_instrumentation("\n".join(lines).replace("OK (7 tests)", "OK (6 tests)").encode())

    def test_command_failure_artifact_is_actionable_without_raw_output_or_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            artifacts = Path(temp)
            failure = subprocess.CalledProcessError(
                1, ["/sdk/platform-tools/adb", "-s", "emulator-5560", "shell", "getprop"],
                output="private stdout", stderr="private stderr")
            with patch("tools.android_ui_qualification.subprocess.run", side_effect=failure):
                with self.assertRaisesRegex(QualificationError, "android_ui_command_failed"):
                    _run(["/private/sdk/platform-tools/adb", "-s", "emulator-5560",
                          "shell", "getprop"], failure_artifacts=artifacts)
            record = json.loads((artifacts / "command-failure.json").read_text())
            self.assertEqual(record["reason"], "android_ui_command_failed")
            self.assertEqual(record["command"]["tool"], "adb")
            self.assertNotIn("/private", json.dumps(record))
            self.assertNotIn("stdout", record)
            self.assertNotIn("private", json.dumps(record))


if __name__ == "__main__": unittest.main()

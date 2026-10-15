import argparse
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.android_emulator_test import execute, Refused


class EmulatorBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.apk = root / "app.apk"
        self.test = root / "test.apk"
        self.apk.write_bytes(b"synthetic")
        self.test.write_bytes(b"synthetic")
        self.calls = []
        self.app_id = "dev.photohouse.connected.qa"
        self.qemu = "1"
        self.result = "OK (4 tests)"

    def args(self, **changes):
        values = dict(serial="emulator-5554", apk=self.apk, test_apk=self.test,
                      aapt="aapt", adb="adb", test_class="dev.photohouse.connected.DraftTest", dry_run=False)
        values.update(changes)
        return argparse.Namespace(**values)

    def run_command(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[0] == "aapt":
            package = self.app_id + (".test" if argv[-1] == str(self.test) else "")
            output = "package: name='" + package + "' versionCode='1'"
        elif argv[-1] == "get-state":
            output = "device"
        elif argv[-1] == "get-serialno":
            output = "emulator-5554"
        elif argv[-1] == "ro.kernel.qemu":
            output = self.qemu
        elif "install" in argv:
            output = "Success"
        else:
            output = self.result
        return subprocess.CompletedProcess(argv, 0, output, "")

    def test_physical_serial_rejected_before_any_command(self):
        with self.assertRaises(Refused):
            execute(self.args(serial="physical-device"), self.run_command)
        self.assertEqual([], self.calls)

    def test_production_package_rejected_before_device_writes(self):
        self.app_id = "dev.photohouse.connected"
        with self.assertRaises(Refused):
            execute(self.args(), self.run_command)
        self.assertFalse(any("install" in argv for argv in self.calls))

    def test_non_emulator_property_refuses_install(self):
        self.qemu = "0"
        with self.assertRaises(Refused):
            execute(self.args(), self.run_command)
        self.assertFalse(any("install" in argv for argv in self.calls))

    def test_explicit_serial_and_identity_checked_before_every_write(self):
        result = execute(self.args(), self.run_command)
        self.assertEqual(4, result["tests"])
        adb_calls = [argv for argv in self.calls if argv[0] == "adb"]
        self.assertTrue(all(argv[1:3] == ["-s", "emulator-5554"] for argv in adb_calls))
        self.assertEqual(4, sum(argv[-1] == "ro.kernel.qemu" for argv in adb_calls))

    def test_dry_run_never_installs_or_runs_instrumentation(self):
        result = execute(self.args(dry_run=True), self.run_command)
        self.assertEqual("qa_emulator_preflight_passed", result["status"])
        self.assertFalse(any("install" in argv or "instrument" in argv for argv in self.calls))

    def test_crash_and_zero_tests_are_failures(self):
        for output in ("OK (0 tests)", "OK (4 tests)\nProcess crashed", "INSTRUMENTATION_FAILED"):
            with self.subTest(output=output), self.assertRaises(Refused):
                self.result = output
                execute(self.args(), self.run_command)


if __name__ == "__main__":
    unittest.main()

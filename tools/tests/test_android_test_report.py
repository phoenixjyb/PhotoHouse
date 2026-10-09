from pathlib import Path
from contextlib import redirect_stdout
import io
import json
import tempfile
import unittest
from unittest import mock

from tools import android_test_report as report


def xml(cases="<testcase name='synthetic'/>", tests=1, failures=0, errors=0, skipped=0):
    return (f"<testsuite tests='{tests}' failures='{failures}' errors='{errors}' skipped='{skipped}'>"
            f"{cases}<system-out>synthetic output</system-out></testsuite>").encode()


class AndroidReportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, module, raw=None):
        task = "testDebugUnitTest" if module in ("connected", "tv") else "test"
        path = self.root / module / "build/test-results" / task / "TEST-synthetic.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(xml() if raw is None else raw)
        return path

    def test_complete_inventory_keeps_no_report_distinct_from_executed_tests(self):
        for module in report.MODULES:
            if module != "protocol": self.write(module)
        with mock.patch("subprocess.run", side_effect=AssertionError("must not execute")):
            result = report.collect(self.root)
        self.assertTrue(result["complete_required_reports"])
        self.assertEqual(result["totals"], {"tests": 7, "failures": 0, "errors": 0, "skipped": 0})
        self.assertEqual(result["modules"][1]["state"], "no_report")
        self.assertFalse(result["tests_run_by_this_tool"])
        self.assertFalse(result["source_revision_bound"])
        self.assertFalse(result["artifact_or_device_qualified"])

    def test_missing_required_reports_are_visible(self):
        self.write("connected")
        result = report.collect(self.root)
        self.assertFalse(result["complete_required_reports"])
        self.assertIn("tv", result["missing_modules"])
        self.assertNotIn("protocol", result["missing_modules"])

    def test_failed_errored_and_skipped_cases_are_never_counted_as_passes(self):
        raw = xml("<testcase><failure/></testcase><testcase><error/></testcase>"
                  "<testcase><skipped/></testcase>", tests=3, failures=1, errors=1, skipped=1)
        self.write("core", raw)
        self.assertEqual(report.collect(self.root)["totals"],
                         {"tests": 3, "failures": 1, "errors": 1, "skipped": 1})

    def test_malformed_counts_or_xml_are_refused(self):
        for raw in (xml(tests=2), xml().replace(b"tests='1'", b"tests='-1'"),
                    b"<invalid", b"<testsuites/>"):
            with self.subTest(raw=raw):
                with self.assertRaises(report.ReportError): report.counts(raw)

    def test_external_or_expanding_entities_are_refused_before_parsing(self):
        for raw in (b"<!DOCTYPE testsuite [<!ENTITY x 'synthetic'>]>" + xml(),
                    b"<!ENTITY x SYSTEM 'file:///synthetic'>" + xml(), b"\x00" + xml()):
            with self.subTest(raw=raw):
                with self.assertRaisesRegex(report.ReportError, "declaration_refused"):
                    report.counts(raw)

    def test_symlink_file_and_directory_are_refused(self):
        path = self.write("core"); original = self.root / "original.xml"
        path.replace(original);path.symlink_to(original)
        with self.assertRaisesRegex(report.ReportError, "file_refused"): report.collect(self.root)
        path.unlink();path.write_bytes(xml())
        directory = self.root / "alias";directory.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(report.ReportError, "directory_not_regular"):
            report.collect(directory)

    def test_per_file_total_bytes_and_report_count_limits(self):
        self.write("core")
        for name, limit, reason in (("MAX_REPORT_BYTES", 1, "file_refused"),
                                    ("MAX_TOTAL_BYTES", 1, "bytes_limit"),
                                    ("MAX_REPORTS", 0, "count_limit")):
            with self.subTest(limit=name), mock.patch.object(report, name, limit):
                with self.assertRaisesRegex(report.ReportError, reason): report.collect(self.root)

    def test_report_changes_during_read_are_refused(self):
        path = self.write("core")
        real_lstat = Path.lstat; calls = 0
        def changed(candidate):
            nonlocal calls
            if candidate == path:
                calls += 1
                if calls == 2: candidate.write_bytes(xml(tests=2))
            return real_lstat(candidate)
        with mock.patch.object(Path, "lstat", changed):
            with self.assertRaisesRegex(report.ReportError, "changed_or_oversized"):
                report.read_report(path)

    def test_cli_failure_prints_only_fixed_reason_without_raw_xml_or_paths(self):
        self.write("core", b"<private-sentinel-and-invalid-xml")
        output = io.StringIO()
        with mock.patch("sys.argv", ["report", "--project-root", str(self.root)]), redirect_stdout(output):
            status = report.main()
        self.assertEqual(status, 1)
        self.assertEqual(json.loads(output.getvalue())["reason"], "report_xml_invalid")
        self.assertNotIn("private-sentinel", output.getvalue())
        self.assertNotIn(str(self.root), output.getvalue())

    def test_cli_complete_inventory_can_contain_failures_without_claiming_execution(self):
        for module in report.MODULES:
            if module != "protocol": self.write(module)
        self.write("core", xml("<testcase><failure/></testcase>", failures=1))
        output = io.StringIO()
        with mock.patch("sys.argv", ["report", "--project-root", str(self.root)]), redirect_stdout(output):
            status = report.main()
        result = json.loads(output.getvalue())
        self.assertEqual(status, 0, "exit status describes a complete inventory, not passing tests")
        self.assertEqual(result["totals"]["failures"], 1)
        self.assertFalse(result["tests_run_by_this_tool"])


if __name__ == "__main__":
    unittest.main()

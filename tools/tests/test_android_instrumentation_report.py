from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools import android_instrumentation_report as report


def status_event(index, total, code, test_name="private.synthetic.Test.test_private", runner="AndroidJUnitRunner"):
    base = (f"INSTRUMENTATION_STATUS: class=private.synthetic.Test\n"
            f"INSTRUMENTATION_STATUS: current={index}\n"
            f"INSTRUMENTATION_STATUS: id={runner}\n"
            f"INSTRUMENTATION_STATUS: numtests={total}\n"
            f"INSTRUMENTATION_STATUS: test={test_name}\n")
    return base + f"INSTRUMENTATION_STATUS_CODE: {code}\n"


def status_block(index, total, completion=0, test_name="private.synthetic.Test.test_private"):
    return (status_event(index, total, 1, test_name) +
            status_event(index, total, completion, test_name))


def passing_log(total=2):
    blocks = "".join(status_block(i, total) for i in range(1, total + 1))
    return (blocks + "INSTRUMENTATION_RESULT: stream=\nTime: 0.25\n" +
            f"OK ({total} tests)\nINSTRUMENTATION_CODE: -1\n").encode()


class AndroidInstrumentationReportTests(unittest.TestCase):
    def test_complete_passing_run_requires_all_consistent_markers(self):
        result = report.summarize(passing_log())
        self.assertEqual(result, {
            "kind": "existing_android_instrumentation_run", "status": "passed", "complete": True,
            "tests": 2, "passed": 2, "failures": 0, "errors": 0, "skipped": 0,
            "unknown_statuses": 0, "instrumentation_code": -1,
        })

    def test_failure_and_error_statuses_fail_closed_without_echoing_test_names(self):
        for code in (-1, -2):
            with self.subTest(code=code):
                raw = (status_block(1, 1, completion=code) +
                       "INSTRUMENTATION_RESULT: stream=private stack and input\nFAILURES!!!\n"
                       "INSTRUMENTATION_CODE: -1\n").encode()
                output = json.dumps(report.summarize(raw))
                self.assertIn('"status": "unavailable"', output)
                self.assertNotIn("private.synthetic", output)
                self.assertNotIn("private stack", output)

    def test_skip_assumption_and_unknown_statuses_are_rejected(self):
        for code, reason in ((-3, "test_skipped_or_assumption_failed"),
                             (-4, "test_skipped_or_assumption_failed"),
                             (7, "unknown_test_status")):
            with self.subTest(code=code):
                raw = (status_block(1, 1, completion=code) +
                       "INSTRUMENTATION_RESULT: stream=\nOK (1 test)\nINSTRUMENTATION_CODE: -1\n").encode()
                self.assertEqual(report.summarize(raw)["reason"], reason)

    def test_truncation_empty_zero_and_missing_terminal_are_rejected(self):
        cases = (
            (passing_log()[:-1], "log_truncated"),
            (b"", "log_empty_or_invalid"),
            ((status_block(1, 0) + "OK (0 tests)\nINSTRUMENTATION_CODE: -1\n").encode(), "zero_tests"),
            (passing_log().replace(b"INSTRUMENTATION_CODE: -1\n", b""),
             "instrumentation_terminal_missing_or_conflicting"),
        )
        for raw, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(report.summarize(raw)["reason"], reason)

    def test_oversized_and_invalid_utf8_logs_fail_closed(self):
        self.assertEqual(report.summarize(b"x" * (report.MAX_LOG_BYTES + 1))["reason"], "log_empty_or_invalid")
        self.assertEqual(report.summarize(b"\xff\n")["reason"], "log_encoding_invalid")

    def test_duplicate_summary_and_conflicting_counts_are_rejected(self):
        duplicate = passing_log()[:-len(b"INSTRUMENTATION_CODE: -1\n")] + b"OK (2 tests)\nINSTRUMENTATION_CODE: -1\n"
        conflict = passing_log().replace(b"OK (2 tests)", b"OK (1 test)")
        numtests_conflict = passing_log().replace(b"numtests=2", b"numtests=3", 1)
        mismatch = passing_log().replace(b"INSTRUMENTATION_STATUS_CODE: 0", b"INSTRUMENTATION_STATUS_CODE: 1", 1)
        for raw, reason in ((duplicate, "summary_missing_or_conflicting"),
                            (conflict, "summary_count_mismatch"),
                            (numtests_conflict, "numtests_conflict"),
                            (mismatch, "test_status_order_invalid")):
            with self.subTest(reason=reason):
                self.assertEqual(report.summarize(raw)["reason"], reason)

    def test_short_message_and_abort_marker_reject_otherwise_passing_summary(self):
        for marker in ("INSTRUMENTATION_RESULT: shortMsg=private detail\n",
                       "INSTRUMENTATION_FAILED: private detail\n"):
            raw = passing_log().replace(b"INSTRUMENTATION_CODE: -1", marker.encode() + b"INSTRUMENTATION_CODE: -1")
            self.assertEqual(report.summarize(raw)["reason"], "instrumentation_aborted")

    def test_status_order_current_pair_and_runner_identity_are_required(self):
        valid_tail = "INSTRUMENTATION_RESULT: stream=\nOK (2 tests)\nINSTRUMENTATION_CODE: -1\n"
        cases = (
            (status_block(2, 2) + status_block(1, 2) + valid_tail, "test_current_mismatch"),
            (status_block(1, 2) + status_block(1, 2) + valid_tail, "test_current_mismatch"),
            (status_event(1, 2, 1) + status_event(2, 2, 0) +
             status_block(2, 2) + valid_tail, "test_status_pair_mismatch"),
            (status_block(1, 2).replace("INSTRUMENTATION_STATUS_CODE: 1", "INSTRUMENTATION_STATUS_CODE: 0", 1) +
             status_block(2, 2) + valid_tail, "test_status_order_invalid"),
            (status_event(1, 2, 1, runner="UntrustedRunner") + status_event(1, 2, 0, runner="UntrustedRunner") +
             status_block(2, 2) + valid_tail, "runner_id_invalid"),
        )
        for raw, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(report.summarize(raw.encode())["reason"], reason)

    def test_malformed_and_unbounded_control_numbers_fail_closed(self):
        cases = (
            (passing_log().replace(b"INSTRUMENTATION_STATUS_CODE: 0", b"INSTRUMENTATION_STATUS_CODE: " + b"9" * 5000),
             "status_control_invalid"),
            (passing_log().replace(b"INSTRUMENTATION_STATUS: current=1", b"INSTRUMENTATION_STATUS: current=" + b"9" * 5000),
             "test_current_mismatch"),
            (passing_log().replace(b"INSTRUMENTATION_STATUS: numtests=2", b"INSTRUMENTATION_STATUS: numtests=" + b"9" * 5000),
             "numtests_missing_or_invalid"),
            (passing_log().replace(b"INSTRUMENTATION_CODE: -1", b"INSTRUMENTATION_CODE: enormous"),
             "terminal_control_invalid"),
        )
        for raw, reason in cases:
            with self.subTest(reason=reason):
                self.assertEqual(report.summarize(raw)["reason"], reason)

    def test_cli_exit_status_and_json_are_derived_from_log_without_paths_or_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "private-log.txt"
            path.write_bytes(passing_log())
            stdout = io.StringIO()
            with mock.patch("sys.argv", ["report", str(path)]), redirect_stdout(stdout):
                status = report.main()
            self.assertEqual(status, 0)
            result = json.loads(stdout.getvalue())
            self.assertEqual(result["tests"], 2)
            self.assertNotIn(str(path), stdout.getvalue())
            self.assertNotIn("private.synthetic", stdout.getvalue())

            path.write_bytes(passing_log()[:-len(b"INSTRUMENTATION_CODE: -1\n")])
            stdout = io.StringIO()
            with mock.patch("sys.argv", ["report", str(path)]), redirect_stdout(stdout):
                status = report.main()
            self.assertEqual(status, 1)
            self.assertEqual(json.loads(stdout.getvalue())["reason"], "instrumentation_terminal_missing_or_conflicting")
            self.assertNotIn(str(path), stdout.getvalue())


if __name__ == "__main__":
    unittest.main()

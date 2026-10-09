import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import plan_bad_video_recovery as planner


class BadVideoRecoveryPlanTests(unittest.TestCase):
    def test_classifies_zero_byte_source_without_claiming_reconstruction(self):
        result = planner.build_plan({"rows": [
            {"id": 1, "reason": "source_empty", "source_size": 0}
        ]})["rows"][0]
        self.assertEqual(result["class"], "source_empty")
        self.assertFalse(result["recoverable_from_current_bytes"])
        self.assertIn("independent original or backup", result["recovery"])

    def test_recognizes_appledouble_as_metadata_not_a_truncated_video(self):
        result = planner.build_plan({"rows": [
            {"id": 2, "reason": "preparation_failed", "source_size": 4096,
             "header_hex": "00051607000200004d6163204f532058"}
        ]})["rows"][0]
        self.assertEqual(result["class"], "container_metadata_artifact")
        self.assertIn("separately cataloged real video", result["recovery"])

    def test_appledouble_magic_without_v2_header_is_not_accepted(self):
        result = planner.build_plan({"rows": [
            {"id": 6, "reason": "preparation_failed", "source_size": 4096,
             "header_hex": "00051607000100004d6163204f532058"}
        ]})["rows"][0]
        self.assertEqual(result["class"], "source_suspiciously_small")

    def test_decode_failure_stays_unresolved_and_recommends_isolated_review(self):
        result = planner.build_plan({"rows": [
            {"id": 3, "reason": "source_decode_failed", "source_size": 81003212,
             "header_hex": "00000018667479706d703432"}
        ]})["rows"][0]
        self.assertEqual(result["class"], "source_decode_failure")
        self.assertEqual(result["recoverable_from_current_bytes"],
                         "unknown_without_a_separate_decode_review")

    def test_refuses_duplicate_ids_and_path_or_extra_fields(self):
        row = {"id": 4, "reason": "source_empty", "source_size": 0}
        with self.assertRaisesRegex(ValueError, "duplicate_asset_id"):
            planner.build_plan({"rows": [row, dict(row)]})
        with self.assertRaisesRegex(ValueError, "invalid_snapshot"):
            planner.build_plan({"rows": [], "path": "private"})
        with self.assertRaisesRegex(ValueError, "invalid_row"):
            planner.build_plan({"rows": [dict(row, source_path="private")]})

    def test_refuses_unknown_reasons_invalid_ids_and_conflicting_sizes(self):
        bad_rows = [
            {"id": 7, "reason": "private filename", "source_size": 12},
            {"id": 7, "reason": ["preparation_failed"], "source_size": 12},
            {"id": 0, "reason": "preparation_failed", "source_size": 12},
            {"id": 8, "reason": "source_empty", "source_size": 12},
            {"id": 9, "reason": "source_decode_failed", "source_size": 0},
        ]
        for row in bad_rows:
            with self.subTest(row=row), self.assertRaises(ValueError):
                planner.build_plan({"rows": [row]})

    def test_refuses_nonstring_oversized_or_malformed_header_hex(self):
        for header in (12, "xyz", "0", "aa" * 65):
            with self.subTest(header=header), self.assertRaisesRegex(ValueError, "invalid_header_hex"):
                planner.build_plan({"rows": [
                    {"id": 10, "reason": "preparation_failed", "source_size": 4096,
                     "header_hex": header}
                ]})

    def test_cli_consumes_sanitized_stdin_and_emits_path_free_plan(self):
        script = Path(planner.__file__)
        result = subprocess.run([sys.executable, str(script)], input=json.dumps({
            "rows": [{"id": 5, "reason": "source_empty", "source_size": 0}]
        }), text=True, capture_output=True, check=True)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["mode"], "read_only_recovery_plan")
        self.assertNotIn("path", plan["rows"][0])

    def test_numeric_and_row_limits(self):
        maximum = planner.MAX_SQLITE_INTEGER
        result = planner.build_plan({"rows": [
            {"id": maximum, "reason": "preparation_failed", "source_size": maximum}
        ]})
        self.assertEqual(result["rows"][0]["id"], maximum)

        for row in (
            {"id": maximum + 1, "reason": "preparation_failed", "source_size": 8192},
            {"id": 11, "reason": "preparation_failed", "source_size": maximum + 1},
        ):
            with self.subTest(row="numeric-overflow"), self.assertRaisesRegex(ValueError, "invalid_row"):
                planner.build_plan({"rows": [row]})

        rows = [
            {"id": index + 1, "reason": "preparation_failed", "source_size": 8192}
            for index in range(planner.MAX_ROWS + 1)
        ]
        with self.assertRaisesRegex(ValueError, "too_many_rows"):
            planner.build_plan({"rows": rows})

    def test_cli_missing_file_error_does_not_echo_private_path(self):
        script = Path(planner.__file__)
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "PRIVATE_PATH_CANARY_missing_snapshot.json"
            result = subprocess.run(
                [sys.executable, str(script), str(missing)],
                capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, "refused: unable to read snapshot\n")
        self.assertNotIn("PRIVATE_PATH_CANARY", result.stderr + result.stdout)

    def test_cli_malformed_json_error_does_not_echo_snapshot_content(self):
        script = Path(planner.__file__)
        content = b'{"rows":[{"path":"PRIVATE_CONTENT_CANARY",'
        result = subprocess.run(
            [sys.executable, str(script)], input=content,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, b"refused: malformed JSON snapshot\n")
        self.assertNotIn(b"PRIVATE_CONTENT_CANARY", result.stderr + result.stdout)

    def test_cli_rejects_duplicate_json_keys(self):
        script = Path(planner.__file__)
        cases = (
            b'{"rows":[],"rows":[]}',
            b'{"rows":[{"id":1,"reason":"preparation_failed","source_size":8192,"extra":{"x":1,"x":2}}]}',
        )
        for content in cases:
            with self.subTest(nesting="top-level" if b'"rows":[],"rows"' in content else "nested"):
                result = subprocess.run(
                    [sys.executable, str(script)], input=content, capture_output=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, b"refused: malformed JSON snapshot\n")

    def test_cli_malformed_encoding_constant_and_deep_json_use_fixed_error(self):
        script = Path(planner.__file__)
        deep_depth = 10_000
        deep = b'{"rows":' + (b"[" * deep_depth) + (b"]" * deep_depth) + b"}"
        for label, content in (
            ("invalid-utf8", b'{"rows":[]}' + b"\xff"),
            ("nonstandard-nan", b'{"rows":[{"id":1,"reason":"preparation_failed","source_size":NaN}]}'),
            ("deep-json", deep),
        ):
            with self.subTest(case=label):
                result = subprocess.run(
                    [sys.executable, str(script)], input=content, capture_output=True,
                )
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stderr, b"refused: malformed JSON snapshot\n")
                self.assertNotIn(b"Traceback", result.stderr + result.stdout)

    def test_cli_rejects_oversized_snapshot_without_echoing_content(self):
        script = Path(planner.__file__)
        content = b"X" * (planner.MAX_SNAPSHOT_BYTES + 1) + b"PRIVATE_CONTENT_CANARY"
        result = subprocess.run(
            [sys.executable, str(script)], input=content,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, b"refused: snapshot exceeds the input limit\n")
        self.assertNotIn(b"PRIVATE_CONTENT_CANARY", result.stderr + result.stdout)

    def test_cli_rejects_unknown_argument_without_echoing_it(self):
        script = Path(planner.__file__)
        result = subprocess.run(
            [sys.executable, str(script), "--private-path-canary"],
            input=b'{"rows":[]}', capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stderr, b"refused: expected at most one snapshot path\n")
        self.assertNotIn(b"private-path-canary", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()

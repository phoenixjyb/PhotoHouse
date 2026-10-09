import json
from pathlib import Path
import subprocess
import sys
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


if __name__ == "__main__":
    unittest.main()

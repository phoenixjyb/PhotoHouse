import copy
import unittest

from multilingual_library_coverage import (
    CoverageInputError,
    MAX_BATCH_BYTES,
    MAX_BATCH_IMAGES,
    MAX_IMAGE_BYTES,
    MAX_IMAGE_DIMENSION,
    MAX_IMAGE_PIXELS,
    MAX_PATH_LENGTH,
    plan_snapshot,
    coverage_summary,
    validate_snapshot,
)


LIBRARY = "family-test"
REVISION = "a" * 64
SOURCE_A = "b" * 64
SOURCE_B = "c" * 64
IDENTITY = {
    "artifact_sha256": "d" * 64,
    "preprocessing_sha256": "e" * 64,
    "vector_space_id": "siglip2-base-p16-256",
    "model_version": "siglip2-base-p16-256-v1",
    "dimension": 768,
    "normalization": "unit_l2",
}


def asset(asset_id, **overrides):
    row = {
        "asset_id": asset_id,
        "path": f"/private/library/photo-{asset_id}.jpg",
        "db_source_sha256": SOURCE_A,
        "mime": "image/jpeg",
        "width": 4000,
        "height": 3000,
        "bytes": 1024,
        "file_status": "available",
    }
    row.update(overrides)
    return row


def snapshot(rows):
    return {
        "schema": "photohouse.multilingual_library_snapshot.v1",
        "library_id": LIBRARY,
        "source_revision_sha256": REVISION,
        "assets": rows,
    }


class MultilingualLibraryCoverageTests(unittest.TestCase):
    def test_snapshot_validation_orders_roster_and_plan_is_deterministic(self):
        first = plan_snapshot(snapshot([asset(9), asset(2)]))
        second = plan_snapshot(snapshot([asset(2), asset(9)]))
        self.assertEqual(first, second)
        self.assertEqual(first["candidate_asset_ids"], [2, 9])
        self.assertEqual(first["batches"], [{"batch_number": 1, "asset_ids": [2, 9], "bytes": 2048}])
        self.assertEqual(first["asset_count"], 2)
        self.assertFalse(first["reviewed"])
        self.assertFalse(first["source_hashes_verified"])
        self.assertFalse(first["builder_accepted_cohort"])
        self.assertFalse(first["production_coverage"])
        self.assertFalse(first["activation_performed"])
        self.assertEqual(validate_snapshot(snapshot([asset(9), asset(2)]))["assets"][0]["asset_id"], 2)

    def test_count_and_byte_limits_create_complete_ordered_batches(self):
        rows = [asset(i + 1) for i in range(MAX_BATCH_IMAGES + 2)]
        count_plan = plan_snapshot(snapshot(rows))
        self.assertEqual([len(batch["asset_ids"]) for batch in count_plan["batches"]],
                         [MAX_BATCH_IMAGES, 2])
        self.assertEqual([asset_id for batch in count_plan["batches"]
                          for asset_id in batch["asset_ids"]], list(range(1, MAX_BATCH_IMAGES + 3)))

        byte_plan = plan_snapshot(snapshot([asset(i, bytes=MAX_IMAGE_BYTES) for i in range(1, 10)]))
        self.assertEqual([len(batch["asset_ids"]) for batch in byte_plan["batches"]], [8, 1])
        self.assertEqual([batch["bytes"] for batch in byte_plan["batches"]],
                         [MAX_BATCH_BYTES, MAX_IMAGE_BYTES])

    def test_blockers_have_fixed_reasons_and_remain_in_full_roster_digest(self):
        plan = plan_snapshot(snapshot([
            asset(1, file_status="missing"),
            asset(2, file_status="outside_roots"),
            asset(3, file_status="unsafe_path"),
            asset(4, file_status="unreadable"),
            asset(5, mime="image/heic"),
            asset(6, bytes=MAX_IMAGE_BYTES + 1),
            asset(7, width=0),
            asset(8, width=5000, height=4000),
            asset(9, width=MAX_IMAGE_DIMENSION + 1, height=1),
            asset(10, bytes=0),
            asset(11),
        ]))
        self.assertEqual(plan["blockers"], [
            {"asset_id": 1, "reason": "file_missing"},
            {"asset_id": 2, "reason": "outside_roots"},
            {"asset_id": 3, "reason": "unsafe_path"},
            {"asset_id": 4, "reason": "unreadable"},
            {"asset_id": 5, "reason": "unsupported_mime"},
            {"asset_id": 6, "reason": "image_byte_limit"},
            {"asset_id": 7, "reason": "invalid_dimensions"},
            {"asset_id": 8, "reason": "image_pixel_limit"},
            {"asset_id": 9, "reason": "image_dimension_limit"},
            {"asset_id": 10, "reason": "empty_image"},
        ])
        self.assertEqual(plan["candidate_asset_ids"], [11])
        changed = copy.deepcopy(plan["snapshot"])
        changed["assets"][0]["db_source_sha256"] = SOURCE_B
        self.assertNotEqual(plan_snapshot(changed)["snapshot_digest_sha256"],
                            plan["snapshot_digest_sha256"])

    def test_decoder_boundaries_for_image_bytes_dimensions_and_pixels(self):
        plan = plan_snapshot(snapshot([
            asset(1, bytes=MAX_IMAGE_BYTES),
            asset(2, bytes=MAX_IMAGE_BYTES + 1),
            asset(3, width=MAX_IMAGE_DIMENSION, height=MAX_IMAGE_PIXELS // MAX_IMAGE_DIMENSION),
            asset(4, width=MAX_IMAGE_DIMENSION, height=MAX_IMAGE_PIXELS // MAX_IMAGE_DIMENSION + 1),
            asset(5, width=MAX_IMAGE_DIMENSION + 1, height=1),
        ]))
        self.assertEqual(plan["candidate_asset_ids"], [1, 3])
        self.assertEqual(plan["blockers"], [
            {"asset_id": 2, "reason": "image_byte_limit"},
            {"asset_id": 4, "reason": "image_pixel_limit"},
            {"asset_id": 5, "reason": "image_dimension_limit"},
        ])

    def test_snapshot_and_path_lengths_are_explicitly_bounded(self):
        with self.assertRaises(CoverageInputError) as caught:
            validate_snapshot(snapshot([{}] * 100_001))
        self.assertEqual(caught.exception.reason, "assets")
        accepted_path = "/" + "x" * (MAX_PATH_LENGTH - 1)
        self.assertEqual(len(accepted_path), MAX_PATH_LENGTH)
        self.assertEqual(len(plan_snapshot(snapshot([asset(1, path=accepted_path)]))["candidate_asset_ids"]), 1)
        rejected_path = accepted_path + "x"
        with self.assertRaises(CoverageInputError) as caught:
            plan_snapshot(snapshot([asset(1, path=rejected_path)]))
        self.assertEqual(caught.exception.reason, "asset_path")

    def test_invalid_or_ambiguous_snapshot_is_rejected_whole(self):
        cases = []
        malformed = snapshot([asset(1)])
        malformed["unexpected"] = True
        cases.append((malformed, "snapshot_schema"))
        cases.append((snapshot([asset(1), asset(1)]), "duplicate_asset_id"))
        bad_hash = asset(1, db_source_sha256="A" * 64)
        cases.append((snapshot([bad_hash]), "db_source_sha256"))
        bad_path = asset(1, path="/private/../outside/photo.jpg")
        cases.append((snapshot([bad_path]), "asset_path"))
        relative_path = asset(1, path="private/photo.jpg")
        cases.append((snapshot([relative_path]), "asset_path"))
        bool_id = asset(True)
        cases.append((snapshot([bool_id]), "asset_id"))
        extra_asset = asset(1, private_note="must not be silently dropped")
        cases.append((snapshot([extra_asset]), "asset_schema"))
        for value, reason in cases:
            with self.subTest(reason=reason, value=value), self.assertRaises(CoverageInputError) as caught:
                plan_snapshot(value)
            self.assertEqual(caught.exception.reason, reason)

    def test_candidate_coverage_requires_exact_sources_and_common_768_identity(self):
        plan = plan_snapshot(snapshot([asset(1), asset(2)]))
        rows = [
            {"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
            {"asset_id": 2, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
        ]
        result = coverage_summary(plan, rows)
        self.assertTrue(result["candidate_coverage"])
        self.assertTrue(result["whole_library_coverage"])
        self.assertEqual(result["candidate_covered_count"], 2)
        self.assertEqual(result["image_identity"], IDENTITY)
        self.assertFalse(result["reviewed"])
        self.assertFalse(result["production_coverage"])
        self.assertFalse(result["activation_performed"])

        explicit = coverage_summary(plan, [
            {"asset_id": 1, "source_sha256": SOURCE_A},
            {"asset_id": 2, "source_sha256": SOURCE_A},
        ], image_identity=IDENTITY)
        self.assertTrue(explicit["candidate_coverage"])

    def test_missing_stale_duplicate_foreign_and_wrong_identity_never_count(self):
        plan = plan_snapshot(snapshot([asset(1), asset(2)]))
        cases = [
            ([{"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY}], "missing_artifact"),
            ([{"asset_id": 1, "source_sha256": SOURCE_B, "image_identity": IDENTITY},
              {"asset_id": 2, "source_sha256": SOURCE_A, "image_identity": IDENTITY}], "stale_source"),
            ([{"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
              {"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
              {"asset_id": 2, "source_sha256": SOURCE_A, "image_identity": IDENTITY}], "duplicate_artifact"),
            ([{"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
              {"asset_id": 2, "source_sha256": SOURCE_A, "image_identity": {**IDENTITY, "dimension": 512}}],
             "invalid_image_identity"),
            ([{"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
              {"asset_id": 2, "source_sha256": SOURCE_A, "image_identity": {**IDENTITY, "model_version": "foreign"}}],
             "mixed_image_identity"),
            ([{"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
              {"asset_id": 2, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
              {"asset_id": 99, "source_sha256": SOURCE_A, "image_identity": IDENTITY}], "foreign_artifact"),
        ]
        for rows, reason in cases:
            with self.subTest(reason=reason):
                result = coverage_summary(plan, rows)
                self.assertFalse(result["candidate_coverage"])
                self.assertFalse(result["whole_library_coverage"])
                self.assertIn(reason, {item["reason"] for item in result["issues"]})

    def test_partial_coverage_counts_only_unique_current_source_rows(self):
        plan = plan_snapshot(snapshot([asset(1), asset(2), asset(3)]))
        partial = coverage_summary(plan, [
            {"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
            {"asset_id": 2, "source_sha256": SOURCE_B, "image_identity": IDENTITY},
        ])
        self.assertFalse(partial["candidate_coverage"])
        self.assertEqual(partial["candidate_covered_count"], 1)

        duplicate = coverage_summary(plan, [
            {"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
            {"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
            {"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
        ])
        self.assertFalse(duplicate["candidate_coverage"])
        self.assertEqual(duplicate["candidate_covered_count"], 0)
        self.assertIn("duplicate_artifact", {row["reason"] for row in duplicate["issues"]})

    def test_blocked_assets_prevent_whole_library_coverage_even_if_candidates_complete(self):
        plan = plan_snapshot(snapshot([asset(1), asset(2, file_status="missing")]))
        result = coverage_summary(plan, [
            {"asset_id": 1, "source_sha256": SOURCE_A, "image_identity": IDENTITY},
        ])
        self.assertTrue(result["candidate_coverage"])
        self.assertFalse(result["whole_library_coverage"])
        self.assertEqual(result["blocker_count"], 1)

    def test_tampered_plan_and_unbound_identity_are_refused(self):
        plan = plan_snapshot(snapshot([asset(1)]))
        altered = copy.deepcopy(plan)
        altered["batches"][0]["asset_ids"] = []
        with self.assertRaises(CoverageInputError) as caught:
            coverage_summary(altered, [], image_identity=IDENTITY)
        self.assertEqual(caught.exception.reason, "plan_digest_or_contents")
        with self.assertRaises(CoverageInputError) as caught:
            coverage_summary(plan, [{"asset_id": 1, "source_sha256": SOURCE_A}])
        self.assertEqual(caught.exception.reason, "image_identity_required")


if __name__ == "__main__":
    unittest.main()

"""Synthetic validation of the pinned semantic eligibility policy."""
from dataclasses import FrozenInstanceError
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.access.semantic_eligibility import (  # noqa: E402
    SemanticEligibilityStore,
    SemanticEligibilityUnavailable,
)
from app.access.visual_vector_artifacts import ImmutableVectorArtifact  # noqa: E402


def sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def artifact(asset_id, source_hash, record_id):
    digest = "a" * 64
    return ImmutableVectorArtifact(
        record_id, asset_id, source_hash, "synthetic-model", digest, "b" * 64,
        "synthetic-space", "synthetic-v1", 2, "unit_l2", "c" * 64,
        f"image-vectors/{'c' * 64}/{record_id}.npy", "d" * 64, "e" * 64, 1, "ready",
    )


class SemanticEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="semantic-eligibility-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.base.chmod(0o700)
        self.source_root = self.base / "source"
        self.source_root.mkdir(mode=0o700)
        self.policy_path = self.base / "policy.json"
        self.binding, self.bulk = "b" * 64, "c" * 64

    def make_document(self, count=65, *, omitted=0):
        hashes = {str(i): sha(f"source-{i}") for i in range(1, count + 1)}
        eligible_count = count - omitted
        eligible = [{"asset_id": str(i), "source_sha256": hashes[str(i)],
                     "record_id": sha(f"record-{i}")} for i in range(1, eligible_count + 1)]
        omitted_rows = [{"asset_id": str(i), "source_sha256": hashes[str(i)],
                         "reason": "preparation_unavailable"}
                        for i in range(eligible_count + 1, count + 1)]
        document = {"format_version": 1, "operator_reviewed": True,
                    "library_id": "family-a", "binding_sha256": self.binding,
                    "bulk_sha256": self.bulk, "index_evidence_sha256": "f" * 64,
                    "eligible": eligible, "omitted": omitted_rows}
        return hashes, {item["asset_id"]: artifact(item["asset_id"], item["source_sha256"],
                                                    item["record_id"]) for item in eligible}, document

    def write(self, document, raw=None):
        raw = json.dumps(document, separators=(",", ":")).encode() if raw is None else raw
        self.policy_path.write_bytes(raw)
        self.policy_path.chmod(0o600)
        return hashlib.sha256(raw).hexdigest()

    def store(self, digest):
        return SemanticEligibilityStore(self.policy_path, digest, "family-a", self.binding,
                                        self.bulk, self.source_root)

    def validate(self, hashes, artifacts, digest, **kwargs):
        return self.store(digest).read_and_validate(hashes, artifacts,
                                                    library_id="family-a", **kwargs)

    def test_complete_and_partial_65_catalogs_have_immutable_closed_coverage(self):
        hashes, artifacts, document = self.make_document()
        digest = self.write(document)
        policy = self.validate(hashes, artifacts, digest)
        self.assertEqual(len(policy.eligible_ids), 65)
        self.assertEqual(policy.omitted_ids, frozenset())
        self.assertEqual(policy.coverage(0), {"version": 1, "policy_sha256": digest,
            "state": "complete", "catalog_images": 65, "searchable_images": 65,
            "omitted_images": 0, "matched_omitted_images": 0})
        with self.assertRaises(FrozenInstanceError):
            policy.library_id = "other"
        with self.assertRaises(SemanticEligibilityUnavailable):
            policy.coverage(1)

        hashes, artifacts, document = self.make_document(65, omitted=1)
        digest = self.write(document)
        policy = self.validate(hashes, artifacts, digest)
        self.assertEqual((len(policy.eligible_ids), len(policy.omitted_ids)), (64, 1))
        self.assertEqual(policy.coverage(0)["state"], "partial")
        self.assertEqual(policy.coverage(1)["matched_omitted_images"], 1)

    def test_descriptor_is_closed_and_constructor_does_not_read(self):
        digest = "1" * 64
        store = self.store(digest)
        self.assertFalse(self.policy_path.exists())
        self.assertEqual(store.descriptor, {"policy_sha256": digest, "library_id": "family-a",
            "binding_sha256": self.binding, "bulk_sha256": self.bulk})
        with self.assertRaises(SemanticEligibilityUnavailable):
            SemanticEligibilityStore(self.source_root / "inside.json", digest, "family-a",
                                     self.binding, self.bulk, self.source_root)
        with self.assertRaises(SemanticEligibilityUnavailable):
            SemanticEligibilityStore(self.base, digest,
                                     "family-a", self.binding, self.bulk, self.source_root)

    def test_refuses_changed_hash_stale_partition_and_artifact_mismatches(self):
        hashes, artifacts, document = self.make_document(4, omitted=1)
        digest = self.write(document)
        variants = []
        stale = dict(hashes); stale["1"] = "0" * 64; variants.append((stale, artifacts))
        added = dict(hashes); added["5"] = sha("source-5"); variants.append((added, artifacts))
        removed = dict(hashes); removed.pop("1"); variants.append((removed, artifacts))
        variants.append((hashes, {**artifacts, "4": artifact("4", hashes["4"], "record-4")}))
        variants.append((hashes, {**artifacts, "1": artifact("1", hashes["1"], sha("wrong-record"))}))
        missing = dict(artifacts); missing.pop('1'); variants.append((hashes, missing))
        for current_hashes, current_artifacts in variants:
            with self.subTest(size=len(current_hashes)), self.assertRaises(SemanticEligibilityUnavailable):
                self.validate(current_hashes, current_artifacts, digest)

    def test_refuses_duplicate_partition_wrong_review_reason_or_document_hash(self):
        hashes, artifacts, original = self.make_document(3, omitted=1)
        variants = []
        duplicate = json.loads(json.dumps(original)); duplicate["eligible"].append(duplicate["eligible"][0]); variants.append(duplicate)
        crossed = json.loads(json.dumps(original)); crossed["omitted"][0]["asset_id"] = "1"; variants.append(crossed)
        unreviewed = json.loads(json.dumps(original)); unreviewed["operator_reviewed"] = False; variants.append(unreviewed)
        bad_reason = json.loads(json.dumps(original)); bad_reason["omitted"][0]["reason"] = "unknown"; variants.append(bad_reason)
        wrong_binding = json.loads(json.dumps(original)); wrong_binding["binding_sha256"] = "0" * 64; variants.append(wrong_binding)
        for document in variants:
            with self.subTest(document=document["operator_reviewed"]), self.assertRaises(SemanticEligibilityUnavailable):
                digest = self.write(document)
                self.validate(hashes, artifacts, digest)

        raw = (b'{"format_version":1,"format_version":1}')
        digest = self.write(original, raw)
        with self.assertRaises(SemanticEligibilityUnavailable):
            self.validate(hashes, artifacts, digest)
        raw = json.dumps(original).replace("\"format_version\": 1", "\"format_version\": NaN", 1).encode()
        digest = self.write(original, raw)
        with self.assertRaises(SemanticEligibilityUnavailable):
            self.validate(hashes, artifacts, digest)

    def test_hash_pin_permissions_symlink_and_hardlink_are_checked_per_read(self):
        hashes, artifacts, document = self.make_document(2)
        digest = self.write(document)
        self.assertEqual(len(self.validate(hashes, artifacts, digest).eligible_ids), 2)
        with self.assertRaises(SemanticEligibilityUnavailable):
            self.validate(hashes, artifacts, "0" * 64)
        self.policy_path.chmod(0o644)
        with self.assertRaises(SemanticEligibilityUnavailable):
            self.validate(hashes, artifacts, digest)
        self.policy_path.chmod(0o600)
        alias = self.base / "alias.json"
        alias.symlink_to(self.policy_path)
        with self.assertRaises(SemanticEligibilityUnavailable):
            SemanticEligibilityStore(alias, digest, "family-a", self.binding, self.bulk,
                                     self.source_root).read_and_validate(
                hashes, artifacts, library_id="family-a")
        alias.unlink()
        os.link(self.policy_path, alias)
        with self.assertRaises(SemanticEligibilityUnavailable):
            self.validate(hashes, artifacts, digest)

    def test_post_read_acl_race_and_source_root_alias_are_refused(self):
        hashes, artifacts, document = self.make_document(2)
        digest = self.write(document)
        import app.access.semantic_eligibility as eligibility_module
        original = eligibility_module.require_private_file
        calls = 0

        def change_after_acl(path):
            nonlocal calls
            calls += 1
            original(path)
            if calls == 2:
                path.chmod(0o644)

        with patch.object(eligibility_module, "require_private_file", side_effect=change_after_acl):
            with self.assertRaises(SemanticEligibilityUnavailable):
                self.validate(hashes, artifacts, digest)
        self.policy_path.chmod(0o600)

        alias = self.base / "source-alias"
        alias.symlink_to(self.source_root, target_is_directory=True)
        store = SemanticEligibilityStore(self.policy_path, digest, "family-a", self.binding,
                                         self.bulk, alias)
        with self.assertRaises(SemanticEligibilityUnavailable):
            store.read_and_validate(hashes, artifacts, library_id="family-a")

    def test_read_checks_cancellation_and_charges_each_bounded_chunk_before_read(self):
        hashes, artifacts, document = self.make_document(3)
        digest = self.write(document)
        checks, charges = [], []
        self.validate(hashes, artifacts, digest, check=lambda: checks.append(1),
                      charge=lambda amount: charges.append(amount))
        self.assertGreaterEqual(len(checks), 3)
        self.assertEqual(sum(charges), self.policy_path.stat().st_size)
        self.assertTrue(all(0 < item <= 64 * 1024 for item in charges))
        def cancel():
            raise RuntimeError("cancelled")
        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            self.validate(hashes, artifacts, digest, check=cancel)
        with self.assertRaisesRegex(RuntimeError, "budget"):
            self.validate(hashes, artifacts, digest,
                          charge=lambda _amount: (_ for _ in ()).throw(RuntimeError("budget")))

    def test_closed_document_and_numeric_identity_boundaries(self):
        hashes, artifacts, original = self.make_document(3, omitted=1)
        changes = [('format_version', True), ('format_version', 1.0),
                   ('operator_reviewed', 1), ('library_id', 'family-b'),
                   ('binding_sha256', 'a' * 64), ('bulk_sha256', 'a' * 64),
                   ('index_evidence_sha256', 'A' * 64), ('eligible', []),
                   ('omitted', {}), ('unknown', True)]
        variants = []
        for field, value in changes:
            variants.append({**original, field: value})
        for field, value in (('asset_id', True), ('asset_id', '01'), ('asset_id', '0'),
                             ('asset_id', str(2**63)), ('source_sha256', None),
                             ('record_id', 'not-a-record'), ('unknown', True)):
            document = deepcopy(original)
            document['eligible'][0][field] = value
            variants.append(document)
        document = deepcopy(original)
        document['omitted'][0]['reason'] = True
        variants.append(document)
        for position, document in enumerate(variants):
            with self.subTest(case=position), self.assertRaises(SemanticEligibilityUnavailable):
                self.validate(hashes, artifacts, self.write(document))
        digest = self.write(original)
        for value in (-1, True, 1.0, 2):
            with self.subTest(matched=value), self.assertRaises(SemanticEligibilityUnavailable):
                self.validate(hashes, artifacts, digest).coverage(value)

    def test_size_and_cohort_limits_refuse_without_unbounded_payload_reads(self):
        hashes, artifacts, document = self.make_document(3, omitted=1)
        digest = self.write(document)
        with patch('app.access.semantic_eligibility.MAX_POLICY_BYTES', 1), \
             patch('app.access.semantic_eligibility.os.read', side_effect=AssertionError('oversized read')):
            with self.assertRaises(SemanticEligibilityUnavailable):
                self.validate(hashes, artifacts, digest)
        with patch('app.access.semantic_eligibility.MAX_ENTRIES', 2):
            with self.assertRaises(SemanticEligibilityUnavailable):
                self.validate(hashes, artifacts, digest)


if __name__ == "__main__":
    unittest.main()

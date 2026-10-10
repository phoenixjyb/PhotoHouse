"""Synthetic read-only planning checks for tombstoned image vectors."""
from dataclasses import FrozenInstanceError
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_access_foundation import database
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256
from app.access.visual_vector_cleanup import (
    VectorCleanupPlan,
    VectorCleanupRefused,
    plan_asset_vector_cleanup,
)
from app.access.visual_vector_schema import create_visual_vector_schema


ARTIFACT_SHA = "a" * 64
PREPROCESS_SHA = "b" * 64
SOURCE_DELETED = "d" * 64
SOURCE_ACTIVE = "e" * 64
VECTOR = (1.0, 0.0)


def npy_bytes(vector):
    header = repr({"descr": "<f4", "fortran_order": False,
                   "shape": (len(vector),)}).encode("ascii")
    padding = (-(10 + len(header) + 1)) % 16
    header += b" " * padding + b"\n"
    return (b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header
            + struct.pack(f"<{len(vector)}f", *vector))


class VisualVectorCleanupTests(unittest.TestCase):
    def setUp(self):
        self.db = database()
        create_visual_vector_schema(self.db)
        self.db.commit()
        directory = tempfile.TemporaryDirectory(prefix="visual-vector-cleanup-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve(strict=True)

    def tearDown(self):
        self.db.close()

    def identity(self, version):
        return VectorSpaceIdentity(
            ARTIFACT_SHA, PREPROCESS_SHA, "synthetic-space", version, 2, "unit_l2"
        )

    def add_vector(self, asset_id, version, *, vector=VECTOR, source_hash=None,
                   raw=None, component_hash=None, record_id=None):
        identity = self.identity(version)
        digest = identity_sha256(identity)
        raw = npy_bytes(vector) if raw is None else raw
        record_id = record_id or hashlib.sha256(f"{asset_id}/{version}".encode()).hexdigest()
        relative_path = f"image-vectors/{digest}/{record_id}.npy"
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        component_hash = component_hash or canonical_vector_checksum(vector)
        record = ImmutableVectorArtifact(
            record_id, str(asset_id), source_hash or (SOURCE_DELETED if asset_id == 102 else SOURCE_ACTIVE),
            "synthetic-model", identity.artifact_sha256, identity.preprocessing_sha256,
            identity.vector_space_id, identity.model_version, identity.dimension,
            identity.normalization, digest, relative_path, hashlib.sha256(raw).hexdigest(),
            component_hash, 1_800_000_000, "ready",
        )
        self.db.execute(
            """INSERT INTO image_vector_artifacts(
                record_id,asset_id,source_sha256,model_name,artifact_sha256,preprocessing_sha256,
                vector_space_id,model_version,dimension,normalization,identity_sha256,relative_path,
                file_sha256,component_sha256,created_at,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record.record_id, int(record.asset_id), record.source_sha256, record.model_name,
             record.artifact_sha256, record.preprocessing_sha256, record.vector_space_id,
             record.model_version, record.dimension, record.normalization, record.identity_sha256,
             record.relative_path, record.file_sha256, record.component_sha256,
             record.created_at, record.status),
        )
        return path, record

    def plan(self, asset_id=102, root=None):
        if not self.db.in_transaction:
            self.db.execute("BEGIN")
        return plan_asset_vector_cleanup(self.db, self.root if root is None else root, asset_id)

    def test_plans_every_version_and_retains_metadata_and_bytes(self):
        first_path, first = self.add_vector(102, "v1")
        second_path, second = self.add_vector(102, "v2")
        unaffected_path, unaffected = self.add_vector(101, "v1")
        self.db.commit()
        before_changes = self.db.total_changes
        before_bytes = {path: path.read_bytes() for path in (first_path, second_path, unaffected_path)}

        plan = self.plan()

        self.assertIs(type(plan), VectorCleanupPlan)
        self.assertEqual(
            {(item.record_id, item.relative_path, item.file_sha256, item.missing)
             for item in plan.items},
            {(first.record_id, first.relative_path, first.file_sha256, False),
             (second.record_id, second.relative_path, second.file_sha256, False)},
        )
        self.assertEqual(self.db.total_changes, before_changes)
        self.assertEqual({row[0] for row in self.db.execute(
            "SELECT record_id FROM image_vector_artifacts WHERE asset_id=?", (102,)
        ).fetchall()}, {first.record_id, second.record_id})
        self.assertEqual(self.db.execute(
            "SELECT record_id FROM image_vector_artifacts WHERE asset_id=101"
        ).fetchone(), (unaffected.record_id,))
        self.assertEqual({path: path.read_bytes() for path in before_bytes}, before_bytes)
        with self.assertRaises(FrozenInstanceError):
            plan.items = ()

    def test_active_unassigned_missing_and_invalid_parent_refuse_before_filesystem(self):
        self.db.execute("BEGIN")
        with patch("app.access.visual_vector_cleanup._checked_root",
                   side_effect=AssertionError("filesystem touched before tombstone check")):
            for asset_id in (101, 999, 1000, True):
                with self.subTest(asset_id=asset_id):
                    with self.assertRaisesRegex(VectorCleanupRefused, "^Vector cleanup unavailable$"):
                        plan_asset_vector_cleanup(self.db, self.root, asset_id)

    def test_caller_must_own_transaction(self):
        with self.assertRaisesRegex(VectorCleanupRefused, "^Vector cleanup unavailable$"):
            plan_asset_vector_cleanup(self.db, self.root, 102)

    def test_absent_optional_schema_returns_empty_without_filesystem_read(self):
        self.db.execute("DROP TABLE image_vector_artifacts")
        self.db.commit()
        self.db.execute("BEGIN")
        with patch("app.access.visual_vector_cleanup._checked_root",
                   side_effect=AssertionError("filesystem touched for absent schema")):
            self.assertEqual(plan_asset_vector_cleanup(self.db, self.root, 102),
                             VectorCleanupPlan(()))

    def test_schema_drift_refuses(self):
        self.db.execute("DROP TRIGGER trg_image_vector_artifacts_immutable_update")
        self.db.commit()
        self.add_vector(102, "v1")
        self.db.commit()
        self.db.execute("BEGIN")
        with self.assertRaisesRegex(VectorCleanupRefused, "^Vector cleanup unavailable$"):
            plan_asset_vector_cleanup(self.db, self.root, 102)

    def test_artifact_cap_refuses_instead_of_truncating(self):
        for number in range(129):
            version = f"v{number:03d}"
            identity = self.identity(version)
            digest = identity_sha256(identity)
            record_id = hashlib.sha256(f"cap-{number}".encode()).hexdigest()
            relative = f"image-vectors/{digest}/{record_id}.npy"
            self.db.execute(
                """INSERT INTO image_vector_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, 102, SOURCE_DELETED, "synthetic-model", ARTIFACT_SHA,
                 PREPROCESS_SHA, "synthetic-space", version, 2, "unit_l2", digest,
                 relative, "f" * 64, "e" * 64, 1_800_000_000, "ready"),
            )
        self.db.commit()
        self.db.execute("BEGIN")
        with patch("app.access.visual_vector_cleanup._checked_root",
                   side_effect=AssertionError("filesystem touched before cap check")):
            with self.assertRaisesRegex(VectorCleanupRefused, "^Vector cleanup unavailable$"):
                plan_asset_vector_cleanup(self.db, self.root, 102)

    def test_safely_missing_file_is_idempotently_marked_missing(self):
        path, record = self.add_vector(102, "v1")
        path.unlink()
        self.db.commit()

        plan = self.plan()

        self.assertEqual(len(plan.items), 1)
        self.assertEqual((plan.items[0].record_id, plan.items[0].relative_path,
                          plan.items[0].file_sha256, plan.items[0].missing),
                         (record.record_id, record.relative_path, record.file_sha256, True))

    def test_symlink_and_tampered_file_refuse(self):
        path, _record = self.add_vector(102, "v1")
        other = self.root / "outside.npy"
        other.write_bytes(npy_bytes(VECTOR))
        path.unlink()
        path.symlink_to(other)
        self.db.commit()
        with self.assertRaisesRegex(VectorCleanupRefused, "^Vector cleanup unavailable$"):
            self.plan()

        path.unlink()
        path.write_bytes(npy_bytes((0.0, 1.0)))
        with self.assertRaisesRegex(VectorCleanupRefused, "^Vector cleanup unavailable$"):
            self.plan()

    def test_hardlinked_file_refuses(self):
        path, _record = self.add_vector(102, "v1")
        other = self.root / "linked.npy"
        other.hardlink_to(path)
        self.db.commit()
        with self.assertRaisesRegex(VectorCleanupRefused, "^Vector cleanup unavailable$"):
            self.plan()

    def test_invalid_component_checksum_or_nonunit_vector_refuses(self):
        self.add_vector(102, "v1", component_hash="0" * 64)
        self.db.commit()
        with self.assertRaisesRegex(VectorCleanupRefused, "^Vector cleanup unavailable$"):
            self.plan()

        self.db.execute("DROP TABLE image_vector_artifacts")
        self.db.commit()
        create_visual_vector_schema(self.db)
        self.add_vector(102, "v2", vector=(2.0, 0.0))
        self.db.commit()
        with self.assertRaisesRegex(VectorCleanupRefused, "^Vector cleanup unavailable$"):
            self.plan()


if __name__ == "__main__":
    unittest.main()

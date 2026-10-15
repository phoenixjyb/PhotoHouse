"""Synthetic validation and immutable SQLite contract checks for vector artifacts."""
from dataclasses import replace
import sqlite3
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from app.access.visual_candidates import VectorSpaceIdentity
from app.access.visual_vector_artifacts import (
    ImmutableVectorArtifact,
    identity_sha256,
    validate_artifact,
)
from app.access.visual_vector_schema import (
    create_visual_vector_schema,
    sqlite_visual_vector_contract,
    verify_visual_vector_schema,
)


IDENTITY = VectorSpaceIdentity(
    artifact_sha256="a" * 64,
    preprocessing_sha256="b" * 64,
    vector_space_id="synthetic-clip-space-v1",
    model_version="synthetic-v1",
    dimension=2,
    normalization="unit_l2",
)


def artifact(identity=IDENTITY, **changes):
    digest = identity_sha256(identity)
    values = {
        "record_id": "c" * 64,
        "asset_id": "1",
        "source_sha256": "d" * 64,
        "model_name": "synthetic-clip",
        "artifact_sha256": identity.artifact_sha256,
        "preprocessing_sha256": identity.preprocessing_sha256,
        "vector_space_id": identity.vector_space_id,
        "model_version": identity.model_version,
        "dimension": identity.dimension,
        "normalization": identity.normalization,
        "identity_sha256": digest,
        "relative_path": f"image-vectors/{digest}/{'c' * 64}.npy",
        "file_sha256": "e" * 64,
        "component_sha256": "f" * 64,
        "created_at": 1_800_000_000,
        "status": "ready",
    }
    values.update(changes)
    return ImmutableVectorArtifact(**values)


def insert_artifact(db, record):
    names = (
        "record_id", "asset_id", "source_sha256", "model_name", "artifact_sha256",
        "preprocessing_sha256", "vector_space_id", "model_version", "dimension",
        "normalization", "identity_sha256", "relative_path", "file_sha256",
        "component_sha256", "created_at", "status",
    )
    db.execute(
        f"INSERT INTO image_vector_artifacts ({','.join(names)}) "
        f"VALUES ({','.join('?' for _ in names)})",
        tuple(getattr(record, name) for name in names),
    )


class VisualVectorArtifactTests(unittest.TestCase):
    def test_identity_hash_is_stable_and_versioned(self):
        self.assertEqual(identity_sha256(IDENTITY), identity_sha256(IDENTITY))
        changed = replace(IDENTITY, model_version="synthetic-v2")
        self.assertNotEqual(identity_sha256(IDENTITY), identity_sha256(changed))
        with self.assertRaisesRegex(ValueError, "invalid_vector_identity"):
            identity_sha256(replace(IDENTITY, normalization="none"))

    def test_valid_record_binds_identity_source_and_rigid_relative_path(self):
        record = artifact()
        self.assertTrue(validate_artifact(record))
        self.assertTrue(validate_artifact(record, IDENTITY))
        self.assertFalse(validate_artifact(record, replace(IDENTITY, model_version="other-v1")))
        self.assertFalse(validate_artifact(replace(record, relative_path="/tmp/vector.npy")))
        self.assertFalse(validate_artifact(replace(record, relative_path=f"image-vectors/{record.identity_sha256}/other.npy")))

    def test_malformed_metadata_profiles_fail_closed(self):
        good = artifact()
        malformed = [
            replace(good, asset_id="01"),
            replace(good, asset_id="9223372036854775808"),
            replace(good, source_sha256="D" * 64),
            replace(good, record_id="g" * 64),
            replace(good, model_name="Clip Model"),
            replace(good, model_name="é"),
            replace(good, artifact_sha256="0" * 63),
            replace(good, vector_space_id="Upper-v1"),
            replace(good, model_version="../model"),
            replace(good, dimension=0),
            replace(good, dimension=True),
            replace(good, normalization="none"),
            replace(good, identity_sha256="0" * 64),
            replace(good, file_sha256="z" * 64),
            replace(good, component_sha256="A" * 64),
            replace(good, created_at=-1),
            replace(good, created_at=True),
            replace(good, status="pending"),
        ]
        self.assertTrue(all(not validate_artifact(row) for row in malformed))

    def test_contract_is_descriptive_and_verification_is_read_only(self):
        db = sqlite3.connect(":memory:")
        try:
            self.assertEqual(5, len(sqlite_visual_vector_contract()))
            self.assertFalse(verify_visual_vector_schema(db))
            self.assertEqual([], db.execute(
                "SELECT name FROM sqlite_master WHERE name='image_vector_artifacts'"
            ).fetchall())
            db.execute("CREATE TABLE assets(id INTEGER PRIMARY KEY)")
            create_visual_vector_schema(db)
            self.assertTrue(verify_visual_vector_schema(db))
            db.execute("PRAGMA query_only=ON")
            self.assertTrue(verify_visual_vector_schema(db))
        finally:
            db.close()

    def test_sql_enforces_unique_ready_fk_and_immutable_records(self):
        db = sqlite3.connect(":memory:")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("CREATE TABLE assets(id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO assets(id) VALUES (1)")
        create_visual_vector_schema(db)
        self.assertTrue(verify_visual_vector_schema(db))
        record = artifact()
        insert_artifact(db, record)
        with self.assertRaises(sqlite3.IntegrityError):
            insert_artifact(db, record)
        duplicate_identity = replace(record, record_id="9" * 64,
                                     relative_path=f"image-vectors/{record.identity_sha256}/{'9' * 64}.npy")
        with self.assertRaises(sqlite3.IntegrityError):
            insert_artifact(db, duplicate_identity)
        second_identity = replace(IDENTITY, model_version="synthetic-v2")
        second = artifact(second_identity, record_id="1" * 64, source_sha256="2" * 64,
                          identity_sha256=identity_sha256(second_identity),
                          relative_path=f"image-vectors/{identity_sha256(second_identity)}/{'1' * 64}.npy")
        insert_artifact(db, second)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("UPDATE image_vector_artifacts SET status='pending' WHERE record_id=?",
                       (record.record_id,))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("DELETE FROM image_vector_artifacts WHERE record_id=?", (record.record_id,))
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("INSERT INTO image_vector_artifacts SELECT * FROM image_vector_artifacts WHERE record_id=?",
                       (record.record_id,))
        bad = replace(record, record_id="3" * 64, asset_id="2",
                      relative_path=f"image-vectors/{record.identity_sha256}/{'3' * 64}.npy")
        with self.assertRaises(sqlite3.IntegrityError):
            insert_artifact(db, bad)
        with self.assertRaises(sqlite3.IntegrityError):
            db.execute("DELETE FROM assets WHERE id=1")
        missing_parent = replace(record, record_id="8" * 64, asset_id="2",
                                 relative_path=f"image-vectors/{record.identity_sha256}/{'8' * 64}.npy")
        with self.assertRaises(sqlite3.IntegrityError):
            insert_artifact(db, missing_parent)
        db.close()

    def test_schema_verification_rejects_missing_changed_and_extra_objects(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE assets(id INTEGER PRIMARY KEY)")
        create_visual_vector_schema(db)
        self.assertTrue(verify_visual_vector_schema(db))
        db.execute("CREATE TRIGGER injected_mutator AFTER INSERT ON image_vector_artifacts "
                   "BEGIN UPDATE image_vector_artifacts SET created_at=0; END")
        self.assertFalse(verify_visual_vector_schema(db))
        db.execute("DROP TRIGGER injected_mutator")
        db.execute("DROP INDEX uq_image_vector_relative_path")
        db.execute("CREATE INDEX uq_image_vector_relative_path "
                   "ON image_vector_artifacts(relative_path)")
        self.assertFalse(verify_visual_vector_schema(db))
        db.close()

    def test_schema_verification_rejects_wrong_foreign_key_and_trigger_sql(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE assets(id INTEGER PRIMARY KEY)")
        create_visual_vector_schema(db)
        self.assertTrue(verify_visual_vector_schema(db))
        db.execute("DROP TRIGGER trg_image_vector_artifacts_immutable_delete")
        db.execute("CREATE TRIGGER trg_image_vector_artifacts_immutable_delete "
                   "BEFORE DELETE ON image_vector_artifacts BEGIN "
                   "SELECT RAISE(ABORT, 'Image  vector artifact is immutable'); END")
        self.assertFalse(verify_visual_vector_schema(db))
        db.close()

        wrong_fk = sqlite3.connect(":memory:")
        wrong_fk.execute("CREATE TABLE assets(id INTEGER PRIMARY KEY)")
        wrong_fk.execute("CREATE TABLE image_vector_artifacts (record_id TEXT PRIMARY KEY, "
                         "asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE)")
        self.assertFalse(verify_visual_vector_schema(wrong_fk))
        wrong_fk.close()


if __name__ == "__main__":
    unittest.main()

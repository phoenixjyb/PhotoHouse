"""Synthetic filesystem and SQLite checks for journaled vector publication."""
import hashlib
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256
from app.access.visual_vector_schema import create_visual_vector_schema
from app.access.visual_vector_publication import (
    VectorPublicationRefused,
    VectorPublicationStore,
    create_visual_publication_schema,
    verify_visual_publication_schema,
)


IDENTITY = VectorSpaceIdentity(
    artifact_sha256="a" * 64,
    preprocessing_sha256="b" * 64,
    vector_space_id="synthetic-space-v1",
    model_version="synthetic-v1",
    dimension=2,
    normalization="unit_l2",
)
VECTOR = (1.0, 0.0)


def npy_bytes(vector=VECTOR):
    """Encode one exact NPY v1 little-endian float32 vector without NumPy."""
    header = repr({"descr": "<f4", "fortran_order": False,
                   "shape": (len(vector),)}).encode("ascii")
    header += b" " * (-(10 + len(header) + 1) % 16) + b"\n"
    return (b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header
            + struct.pack(f"<{len(vector)}f", *vector))


RAW = npy_bytes()
FILE_SHA = hashlib.sha256(RAW).hexdigest()
IDENTITY_SHA = identity_sha256(IDENTITY)
RECORD_ID = hashlib.sha256(b"synthetic-publication-record").hexdigest()
CLAIM_SHA = "d" * 64


def artifact(**changes):
    fields = {
        "record_id": RECORD_ID,
        "asset_id": "1",
        "source_sha256": "c" * 64,
        "model_name": "synthetic-model",
        "artifact_sha256": IDENTITY.artifact_sha256,
        "preprocessing_sha256": IDENTITY.preprocessing_sha256,
        "vector_space_id": IDENTITY.vector_space_id,
        "model_version": IDENTITY.model_version,
        "dimension": IDENTITY.dimension,
        "normalization": IDENTITY.normalization,
        "identity_sha256": IDENTITY_SHA,
        "relative_path": f"image-vectors/{IDENTITY_SHA}/{RECORD_ID}.npy",
        "file_sha256": FILE_SHA,
        "component_sha256": canonical_vector_checksum(VECTOR),
        "created_at": 1_800_000_000,
        "status": "ready",
    }
    fields.update(changes)
    return ImmutableVectorArtifact(**fields)


def connect(path):
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys=ON")
    return db


def base_schema(db):
    db.execute("CREATE TABLE assets(id INTEGER PRIMARY KEY)")
    db.execute("INSERT INTO assets(id) VALUES(1)")
    db.execute("CREATE TABLE synthetic_tasks(record_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, "
               "claim_sha256 TEXT NOT NULL, status TEXT NOT NULL)")
    db.execute("INSERT INTO synthetic_tasks VALUES(?,?,?,'approved')",
               (RECORD_ID, "1", CLAIM_SHA))
    create_visual_vector_schema(db)
    create_visual_publication_schema(db)
    db.commit()


class VisualVectorPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vector-publication-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve(strict=True)
        self.db_path = self.base / "state.sqlite"
        self.root = self.base / "vectors"
        self.root.mkdir()
        self.db = connect(self.db_path)
        base_schema(self.db)
        self.allowed = True
        self.finalize_calls = []
        self.finalize_error = None
        self.store = self.make_store()

    def tearDown(self):
        self.db.close()

    def guard(self, db, record, claim_sha256):
        task = db.execute(
            "SELECT asset_id,claim_sha256,status FROM synthetic_tasks WHERE record_id=?",
            (record.record_id,),
        ).fetchone()
        return (self.allowed and task is not None and task[:2] ==
                (record.asset_id, claim_sha256) and task[2] in ("approved", "finished"))

    def finalize(self, db, record, claim_sha256):
        self.finalize_calls.append((record.record_id, claim_sha256))
        changed = db.execute(
            "UPDATE synthetic_tasks SET status='finished' WHERE record_id=? AND asset_id=? "
            "AND claim_sha256=? AND status='approved'",
            (record.record_id, record.asset_id, claim_sha256),
        ).rowcount
        if changed != 1:
            raise RuntimeError("synthetic task binding changed")
        if self.finalize_error is not None:
            error, self.finalize_error = self.finalize_error, None
            raise error

    def make_store(self, *, guard=None, finalize=None):
        return VectorPublicationStore(
            self.db, self.root, IDENTITY,
            guard=self.guard if guard is None else guard,
            finalize=self.finalize if finalize is None else finalize,
        )

    def final_path(self, record=None):
        record = record or artifact()
        return self.root / record.relative_path

    def ready_rows(self):
        return self.db.execute(
            "SELECT record_id,relative_path,file_sha256,status FROM image_vector_artifacts"
        ).fetchall()

    def intent_state(self, record_id=RECORD_ID):
        row = self.db.execute(
            "SELECT state FROM image_vector_publications WHERE record_id=?", (record_id,)
        ).fetchone()
        return None if row is None else row[0]

    def assert_no_publication_files(self):
        self.assertEqual(list(self.root.iterdir()), [])

    def test_publish_is_atomic_and_repeat_is_idempotent_without_rewriting(self):
        record = artifact()
        self.assertEqual(self.store.prepare(record, CLAIM_SHA), "prepared")
        self.assertEqual(self.store.publish(RECORD_ID, RAW), "committed")
        final = self.final_path(record)
        self.assertEqual(final.read_bytes(), RAW)
        before = final.stat()
        self.assertEqual(self.ready_rows(), [(RECORD_ID, record.relative_path, FILE_SHA, "ready")])
        self.assertEqual(self.intent_state(), "committed")
        self.assertEqual(self.db.execute("SELECT status FROM synthetic_tasks WHERE record_id=?",
                                         (RECORD_ID,)).fetchone(), ("finished",))
        self.assertEqual(self.store.prepare(record, CLAIM_SHA), "committed")
        self.assertEqual(self.store.publish(RECORD_ID, RAW), "committed")
        self.assertEqual(final.read_bytes(), RAW)
        self.assertEqual((final.stat().st_ino, final.stat().st_mtime_ns),
                         (before.st_ino, before.st_mtime_ns))
        self.assertEqual(len(self.ready_rows()), 1)
        self.assertEqual(len(self.finalize_calls), 1)

    def test_schema_absence_or_drift_refuses_before_any_file_write(self):
        self.db.execute("DROP TABLE image_vector_publications")
        self.db.commit()
        self.assertFalse(verify_visual_publication_schema(self.db))
        with self.assertRaises(VectorPublicationRefused):
            with patch("app.access.visual_vector_publication._checked_root",
                       side_effect=AssertionError("filesystem inspected before schema check")):
                self.store.prepare(artifact(), CLAIM_SHA)
        self.assert_no_publication_files()

        self.db.close()
        self.db = connect(self.db_path)
        create_visual_publication_schema(self.db)
        self.db.commit()
        self.store = self.make_store()
        self.db.execute("DROP TRIGGER trg_image_vector_publication_binding")
        self.db.execute("CREATE TRIGGER trg_image_vector_publication_binding "
                        "BEFORE UPDATE ON image_vector_publications BEGIN SELECT 1; END")
        self.db.commit()
        self.assertFalse(verify_visual_publication_schema(self.db))
        with self.assertRaises(VectorPublicationRefused):
            self.store.prepare(artifact(), CLAIM_SHA)
        self.assert_no_publication_files()

    def test_rejects_non_idle_connection_without_writing(self):
        self.db.execute("BEGIN")
        with self.assertRaises(VectorPublicationRefused):
            self.store.prepare(artifact(), CLAIM_SHA)
        self.db.rollback()
        self.assert_no_publication_files()

    def test_guard_and_finalizer_cannot_commit_the_store_transaction(self):
        def committing_guard(db, _record, _claim):
            db.commit()
            return True

        hostile_guard = self.make_store(guard=committing_guard)
        with self.assertRaises(sqlite3.DatabaseError):
            hostile_guard.prepare(artifact(), CLAIM_SHA)
        self.assertEqual(self.intent_state(), None)
        self.assert_no_publication_files()

        self.assertEqual(self.store.prepare(artifact(), CLAIM_SHA), "prepared")

        def committing_finalizer(db, _record, _claim):
            db.commit()

        hostile_finalizer = self.make_store(finalize=committing_finalizer)
        with self.assertRaises(sqlite3.DatabaseError):
            hostile_finalizer.publish(RECORD_ID, RAW)
        self.assertEqual(self.ready_rows(), [])
        self.assertEqual(self.intent_state(), "prepared")
        self.assertEqual(self.db.execute("SELECT status FROM synthetic_tasks WHERE record_id=?",
                                         (RECORD_ID,)).fetchone(), ("approved",))

        self.db.close()
        self.db = connect(self.db_path)
        self.store = self.make_store()
        recovered = self.store.recover()
        self.assertEqual([(item.record_id, item.status) for item in recovered],
                         [(RECORD_ID, "committed")])
        self.assertEqual(self.ready_rows()[0][0], RECORD_ID)

    def test_guard_denies_scope_before_creating_any_directory_or_file(self):
        self.allowed = False
        with self.assertRaises(VectorPublicationRefused), patch(
                "app.access.visual_vector_publication._checked_root",
                side_effect=AssertionError("filesystem inspected before guard")):
            self.store.prepare(artifact(), CLAIM_SHA)
        self.assert_no_publication_files()
        self.assertEqual(self.ready_rows(), [])
        self.assertIsNone(self.intent_state())

    def test_artifact_profile_claim_and_vector_bytes_are_strictly_bound(self):
        bad_records = (
            artifact(asset_id="2"),
            artifact(model_version="other-v1"),
            artifact(relative_path="image-vectors/elsewhere.npy"),
            artifact(normalization="none"),
        )
        for record in bad_records:
            with self.subTest(record=record):
                with self.assertRaises(VectorPublicationRefused):
                    self.store.prepare(record, CLAIM_SHA)
        with self.assertRaises(VectorPublicationRefused):
            self.store.prepare(artifact(), "e" * 64)
        with self.assertRaises(VectorPublicationRefused):
            self.store.prepare(artifact(), "E" * 64)
        self.assert_no_publication_files()

        record = artifact()
        self.store.prepare(record, CLAIM_SHA)
        for record, claim, raw in (
            (record, CLAIM_SHA, RAW + b"trailing"),
            (record, CLAIM_SHA, npy_bytes((float("nan"), 0.0))),
            (artifact(record_id="7" * 64,
                      relative_path=f"image-vectors/{IDENTITY_SHA}/{'7' * 64}.npy",
                      file_sha256="0" * 64), "3" * 64, RAW),
            (artifact(record_id="6" * 64,
                      relative_path=f"image-vectors/{IDENTITY_SHA}/{'6' * 64}.npy",
                      component_sha256="0" * 64), "4" * 64, RAW),
            (artifact(record_id="5" * 64,
                      relative_path=f"image-vectors/{IDENTITY_SHA}/{'5' * 64}.npy",
                      file_sha256=hashlib.sha256(npy_bytes((0.8, 0.0))).hexdigest(),
                      component_sha256=canonical_vector_checksum((0.8, 0.0))),
             "5" * 64, npy_bytes((0.8, 0.0))),
        ):
            if record.record_id != RECORD_ID:
                self.db.execute("INSERT INTO synthetic_tasks VALUES(?,?,?,'approved')",
                                (record.record_id, record.asset_id, claim))
                self.db.commit()
                self.store.prepare(record, claim)
            with self.subTest(record_id=record.record_id, raw=raw[:16]):
                # Digest, component checksum, and unit-norm failures remain unavailable.
                with self.assertRaises(VectorPublicationRefused):
                    self.store.publish(record.record_id, raw)
                self.assertEqual(self.ready_rows(), [])

    def test_conflicting_preexisting_final_is_never_overwritten(self):
        record = artifact()
        final = self.final_path(record)
        final.parent.mkdir(parents=True)
        final.write_bytes(b"owner data")
        before = final.stat()
        self.store.prepare(record, CLAIM_SHA)
        with self.assertRaises(VectorPublicationRefused):
            self.store.publish(RECORD_ID, RAW)
        self.assertEqual(final.read_bytes(), b"owner data")
        self.assertEqual((final.stat().st_ino, final.stat().st_mtime_ns),
                         (before.st_ino, before.st_mtime_ns))
        self.assertEqual(self.ready_rows(), [])

    def test_linked_file_survives_finalize_interruption_and_fresh_store_recovers(self):
        self.store.prepare(artifact(), CLAIM_SHA)
        self.finalize_error = RuntimeError("synthetic finalize interruption")
        with self.assertRaisesRegex(RuntimeError, "synthetic finalize interruption"):
            self.store.publish(RECORD_ID, RAW)
        final = self.final_path()
        self.assertEqual(final.read_bytes(), RAW)
        # The SQLite transaction rolled back; recovery sees only a prepared intent.
        self.assertEqual(self.ready_rows(), [])
        self.assertEqual(self.intent_state(), "prepared")
        self.assertEqual(self.db.execute("SELECT status FROM synthetic_tasks WHERE record_id=?",
                                         (RECORD_ID,)).fetchone(), ("approved",))
        self.db.close()
        self.db = connect(self.db_path)
        self.store = self.make_store()
        recovered = self.store.recover()
        self.assertEqual([(item.record_id, item.status) for item in recovered],
                         [(RECORD_ID, "committed")])
        self.assertEqual(self.ready_rows()[0][0], RECORD_ID)
        self.assertEqual(self.final_path().read_bytes(), RAW)
        self.assertEqual(self.store.recover(), ())

    def test_process_death_after_link_recovers_both_links_without_new_vector(self):
        self.store.prepare(artifact(), CLAIM_SHA)
        self.db.close()
        program = f"""
import os, sqlite3, sys
from pathlib import Path
sys.path.insert(0, {str(ROOT / 'backend')!r})
import app.access.visual_vector_publication as publication
from app.access.visual_candidates import VectorSpaceIdentity
db=sqlite3.connect({str(self.db_path)!r})
db.execute('PRAGMA foreign_keys=ON')
identity=VectorSpaceIdentity('a'*64,'b'*64,'synthetic-space-v1','synthetic-v1',2,'unit_l2')
real_link=os.link
def link_then_die(*args, **kwargs):
    real_link(*args, **kwargs)
    os._exit(73)
publication.os.link=link_then_die
store=publication.VectorPublicationStore(db,Path({str(self.root)!r}),identity,
    guard=lambda *args: True,finalize=lambda *args: None)
store.publish({RECORD_ID!r},{RAW!r})
"""
        try:
            result = subprocess.run([sys.executable, "-I", "-B", "-c", program],
                                    capture_output=True, timeout=20)
        finally:
            self.db = connect(self.db_path)
            self.store = self.make_store()
        self.assertEqual(result.returncode, 73, result.stderr)
        stage = self.root / "image-vectors" / ".staging" / f"{RECORD_ID}.npy"
        self.assertEqual(stage.stat().st_nlink, 2)
        self.assertEqual(self.final_path().stat().st_nlink, 2)
        self.assertEqual(self.ready_rows(), [])
        self.assertEqual(self.intent_state(), "prepared")
        recovered = self.store.recover()
        self.assertEqual([(item.record_id, item.status) for item in recovered],
                         [(RECORD_ID, "committed")])
        self.assertFalse(stage.exists())
        self.assertEqual(self.final_path().stat().st_nlink, 1)
        self.assertEqual(self.final_path().read_bytes(), RAW)

    def test_recovery_rechecks_guard_and_keeps_cancelled_intent_unavailable(self):
        self.store.prepare(artifact(), CLAIM_SHA)
        staging = self.root / "image-vectors" / ".staging" / f"{RECORD_ID}.npy"
        staging.parent.mkdir(parents=True)
        staging.write_bytes(RAW)
        self.allowed = False
        self.db.close()
        self.db = connect(self.db_path)
        self.store = self.make_store()
        recovered = self.store.recover()
        self.assertEqual([(item.record_id, item.status) for item in recovered],
                         [(RECORD_ID, "unavailable")])
        self.assertEqual(self.ready_rows(), [])
        self.assertEqual(self.intent_state(), "prepared")
        self.assertFalse(self.final_path().exists())

    def test_recovery_scans_only_prepared_and_missing_or_partial_stage_is_unavailable(self):
        self.store.prepare(artifact(), CLAIM_SHA)
        committed_record = artifact(record_id="9" * 64,
                                    relative_path=f"image-vectors/{IDENTITY_SHA}/{'9' * 64}.npy",
                                    source_sha256="1" * 64)
        committed_claim = "1" * 64
        self.db.execute("INSERT INTO synthetic_tasks VALUES(?,?,?,'approved')",
                        (committed_record.record_id, committed_record.asset_id, committed_claim))
        self.db.commit()
        self.store.prepare(committed_record, committed_claim)
        self.assertEqual(self.store.publish(committed_record.record_id, RAW), "committed")
        partial_record = artifact(record_id="8" * 64,
                                  relative_path=f"image-vectors/{IDENTITY_SHA}/{'8' * 64}.npy",
                                  source_sha256="2" * 64)
        partial_claim = "2" * 64
        self.db.execute("INSERT INTO synthetic_tasks VALUES(?,?,?,'approved')",
                        (partial_record.record_id, partial_record.asset_id, partial_claim))
        self.db.commit()
        self.store.prepare(partial_record, partial_claim)
        stage = self.root / "image-vectors" / ".staging" / f"{'8' * 64}.npy"
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_bytes(RAW[:16])
        self.db.close()
        self.db = connect(self.db_path)
        self.store = self.make_store()
        recovered = self.store.recover()
        self.assertEqual({(item.record_id, item.status) for item in recovered},
                         {(RECORD_ID, "unavailable"), ("8" * 64, "unavailable")})
        self.assertEqual(self.intent_state("9" * 64), "committed")
        self.assertFalse(self.final_path().exists())
        self.assertFalse(self.final_path(partial_record).exists())
        self.assertEqual(stage.read_bytes(), RAW[:16])

    def test_symlink_and_hardlink_collisions_are_refused_without_following_or_replacing(self):
        record = artifact()
        final = self.final_path(record)
        outside = self.base / "outside.npy"
        outside.write_bytes(b"preserve me")
        final.parent.mkdir(parents=True)
        final.symlink_to(outside)
        self.store.prepare(record, CLAIM_SHA)
        with self.assertRaises(VectorPublicationRefused):
            self.store.publish(RECORD_ID, RAW)
        self.assertTrue(final.is_symlink())
        self.assertEqual(outside.read_bytes(), b"preserve me")
        final.unlink()

        other = self.base / "other-hardlink.npy"
        other.write_bytes(b"hardlink owner")
        os.link(other, final)
        with self.assertRaises(VectorPublicationRefused):
            self.store.publish(RECORD_ID, RAW)
        self.assertEqual(final.read_bytes(), b"hardlink owner")
        self.assertEqual(other.read_bytes(), b"hardlink owner")

    def test_recovery_cursor_advances_past_missing_intent(self):
        self.store.prepare(artifact(), CLAIM_SHA)
        later = artifact(record_id="f" * 64, source_sha256="2" * 64,
                         relative_path=f"image-vectors/{IDENTITY_SHA}/{'f' * 64}.npy")
        self.db.execute("INSERT INTO synthetic_tasks VALUES(?,?,?,'approved')",
                        (later.record_id, later.asset_id, "f" * 64))
        self.db.commit()
        self.store.prepare(later, "f" * 64)
        stage = self.root / "image-vectors" / ".staging" / f"{later.record_id}.npy"
        stage.parent.mkdir(parents=True)
        stage.write_bytes(RAW)
        first = self.store.recover(limit=1)
        self.assertEqual([(item.record_id, item.status) for item in first], [(RECORD_ID, "unavailable")])
        second = self.store.recover(limit=1, after_record_id=first[-1].record_id)
        self.assertEqual([(item.record_id, item.status) for item in second], [(later.record_id, "committed")])
        self.assertEqual(self.intent_state(), "prepared")


if __name__ == "__main__":
    unittest.main()

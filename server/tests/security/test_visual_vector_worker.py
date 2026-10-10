import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import struct
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from app.access.visual_vector_schema import create_visual_vector_schema
from app.access.visual_vector_publication import (
    create_visual_publication_schema, VectorPublicationRefused,
)
from app.access.visual_vector_worker import (
    ApprovedImageClaim, approved_vector_store, build_artifact, claim_sha256,
    publication_record_id,
)


class ApprovedVisualVectorWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.originals = self.base / "originals"
        self.originals.mkdir()
        self.source = self.originals / "photo.jpg"
        self.source.write_bytes(b"approved image source")
        self.source_hash = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.root = (self.base / "derived").resolve()
        self.root.mkdir()
        self.db = sqlite3.connect(":memory:")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT,file_size INTEGER,hash_sha256 TEXT,mime TEXT,status TEXT);
            CREATE TABLE access_uploads(asset_id INTEGER,state TEXT,sha256 TEXT,bytes INTEGER);
            CREATE TABLE access_asset_libraries(asset_id INTEGER,library_id TEXT);
            CREATE TABLE access_libraries(id TEXT,state TEXT);
            CREATE TABLE tasks(id INTEGER PRIMARY KEY,type TEXT,state TEXT,payload_json TEXT,
                retry_count INTEGER,cancel_requested INTEGER,started_at TEXT,finished_at TEXT,last_error TEXT);
            CREATE TABLE embeddings(asset_id INTEGER,modality TEXT,model TEXT,dim INTEGER,
                storage_path TEXT,vector_checksum TEXT,device TEXT,model_version TEXT);
        """)
        self.identity = VectorSpaceIdentity(
            artifact_sha256="a" * 64, preprocessing_sha256="b" * 64,
            vector_space_id="clip.test", model_version="v1", dimension=2,
            normalization="unit_l2")
        self.raw = self.npy((0.6, 0.8))
        self.insert_claimed_rows()
        self.claim = ApprovedImageClaim.from_candidate({
            "task_id": 7, "asset_id": 11, "path": str(self.source),
            "sha256": self.source_hash, "bytes": self.source.stat().st_size,
            "mime": "image/jpeg", "library_id": "family",
            "claimed_payload_json": '{"asset_id": 11, "modality": "image"}',
            "claim_started_at": "2026-10-10 12:34:56", "claim_retry_count": 2,
        })

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    @staticmethod
    def npy(values):
        shape = f"(2,)"
        header = ("{'descr': '<f4', 'fortran_order': False, 'shape': " + shape + ", }\n").encode()
        padding = (16 - ((10 + len(header)) % 16)) % 16
        header = header[:-1] + b" " * padding + b"\n"
        return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header + struct.pack("<2f", *values)

    def insert_claimed_rows(self):
        content = self.source.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        self.db.execute("INSERT INTO assets VALUES (11,?,?,?,?,?)",
                        (str(self.source), len(content), digest, "image/jpeg", "active"))
        self.db.execute("INSERT INTO access_uploads VALUES (11,'assigned',?,?)", (digest, len(content)))
        self.db.execute("INSERT INTO access_libraries VALUES ('family','active')")
        self.db.execute("INSERT INTO access_asset_libraries VALUES (11,'family')")
        self.db.execute("INSERT INTO tasks VALUES (7,'embed','running',?,2,0,'2026-10-10 12:34:56',NULL,NULL)",
                        ('{"asset_id": 11, "modality": "image"}',))
        create_visual_vector_schema(self.db)
        create_visual_publication_schema(self.db)
        self.db.commit()

    def store(self, *, source_check=None):
        return approved_vector_store(
            self.db, self.root, self.claim, self.identity, model_name="clip.test",
            source_is_current=source_check or self.source_current)

    def source_current(self):
        return (self.source.is_file()
                and hashlib.sha256(self.source.read_bytes()).hexdigest() == self.claim.sha256)

    def prepared(self):
        record = build_artifact(self.claim, self.identity, "clip.test", self.raw)
        store = self.store()
        self.assertEqual(store.prepare(record, claim_sha256(self.claim)), "prepared")
        return store, record

    def test_claim_and_artifact_are_canonical_immutable_bindings(self):
        self.assertEqual(len(claim_sha256(self.claim)), 64)
        self.assertEqual(publication_record_id(self.claim, self.identity),
                         build_artifact(self.claim, self.identity, "clip.test", self.raw).record_id)
        record = build_artifact(self.claim, self.identity, "clip.test", self.raw)
        self.assertEqual(record.component_sha256, canonical_vector_checksum((0.6, 0.8)))
        self.assertEqual(record.created_at, 1791635696)
        with self.assertRaises((AttributeError, TypeError)):
            self.claim.asset_id = 12
        for mutate in (
            lambda c: {**c, "claimed_payload_json": '{"asset_id":11,"modality":"legacy"}'},
            lambda c: {**c, "sha256": "A" * 64},
            lambda c: {**c, "bytes": True},
            lambda c: {**c, "path": str(self.originals / ".." / "escape.jpg")},
        ):
            with self.assertRaises(ValueError):
                ApprovedImageClaim.from_candidate(mutate({
                    **self.claim.__dict__} if hasattr(self.claim, "__dict__") else {
                    name: getattr(self.claim, name) for name in self.claim.__dataclass_fields__}))
        with self.assertRaises(ValueError):
            build_artifact(self.claim, self.identity, "clip.test", b"not npy")

    def test_non_unit_vectors_are_rejected_before_intent_creation(self):
        for vector in ((0., 0.), (3., 4.), (float('nan'), 0.), (float('inf'), 0.)):
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                build_artifact(self.claim, self.identity, "clip.test", self.npy(vector))
        self.assertEqual(self.db.execute('SELECT count(*) FROM image_vector_publications').fetchone()[0], 0)

    def test_revoked_task_or_approval_or_source_blocks_pending_publication(self):
        mutations = (
            ("UPDATE tasks SET state='failed' WHERE id=7",),
            ("UPDATE tasks SET cancel_requested=1 WHERE id=7",),
            ("UPDATE tasks SET retry_count=3 WHERE id=7",),
            ("UPDATE tasks SET payload_json='{}' WHERE id=7",),
            ("UPDATE access_uploads SET state='incoming' WHERE asset_id=11",),
            ("UPDATE assets SET path='elsewhere.jpg' WHERE id=11",),
            ("UPDATE assets SET hash_sha256=? WHERE id=11", "0" * 64),
            ("UPDATE assets SET file_size=file_size+1 WHERE id=11",),
            ("UPDATE access_libraries SET state='closed' WHERE id='family'",),
        )
        for index, item in enumerate(mutations):
            if index:
                self.tearDown()
                self.setUp()
            with self.subTest(mutation=item[0]):
                store, record = self.prepared()
                self.db.execute(item[0], item[1:])
                self.db.commit()
                with self.assertRaises(VectorPublicationRefused):
                    store.publish(record.record_id, self.raw)
                expected_state = "failed" if "state='failed'" in item[0] else "running"
                self.assertEqual(self.db.execute("SELECT state FROM tasks WHERE id=7").fetchone()[0], expected_state)
                self.assertEqual(self.db.execute("SELECT count(*) FROM image_vector_artifacts").fetchone()[0], 0)
        self.tearDown()
        self.setUp()

    def test_source_callback_runs_only_after_database_claim_is_approved(self):
        store, record = self.prepared()
        called = []
        guarded = self.store(source_check=lambda: called.append(True) or False)
        self.assertEqual(called, [])
        with self.assertRaises(VectorPublicationRefused):
            guarded.publish(record.record_id, self.raw)
        self.assertEqual(called, [True])
        called.clear()
        self.db.execute("UPDATE tasks SET cancel_requested=1 WHERE id=7")
        self.db.commit()
        with self.assertRaises(VectorPublicationRefused):
            self.store(source_check=lambda: called.append(True) or True).publish(record.record_id, self.raw)
        self.assertEqual(called, [])

    def test_multiple_library_mappings_and_legacy_image_row_are_refused_untouched(self):
        store, record = self.prepared()
        self.db.execute("INSERT INTO access_libraries VALUES ('other','active')")
        self.db.execute("INSERT INTO access_asset_libraries VALUES (11,'other')")
        self.db.commit()
        with self.assertRaises(VectorPublicationRefused):
            store.publish(record.record_id, self.raw)
        self.assertEqual(self.db.execute("SELECT count(*) FROM image_vector_artifacts").fetchone()[0], 0)
        self.db.execute("DELETE FROM access_asset_libraries WHERE library_id='other'")
        self.db.execute("INSERT INTO embeddings VALUES (11,'image','legacy',2,'old.npy','x','cpu','old')")
        self.db.commit()
        with self.assertRaises(VectorPublicationRefused):
            self.store().publish(record.record_id, self.raw)
        self.assertEqual(self.db.execute("SELECT count(*) FROM embeddings").fetchone()[0], 1)

    def test_pending_publish_and_task_ready_intent_commit_atomically(self):
        store, record = self.prepared()
        self.assertEqual(store.publish(record.record_id, self.raw), "committed")
        self.assertEqual(self.db.execute("SELECT state FROM tasks WHERE id=7").fetchone()[0], "finished")
        self.assertEqual(self.db.execute("SELECT status FROM image_vector_artifacts WHERE record_id=?",
                                         (record.record_id,)).fetchone()[0], "ready")
        self.assertEqual(self.db.execute("SELECT state FROM image_vector_publications WHERE record_id=?",
                                         (record.record_id,)).fetchone()[0], "committed")
        self.assertTrue((self.root / record.relative_path).is_file())

    def test_finalizer_failure_rolls_back_ready_row_task_and_intent(self):
        store, record = self.prepared()
        self.db.execute("CREATE TRIGGER abort_finish BEFORE UPDATE OF state ON tasks "
                        "WHEN NEW.state='finished' BEGIN SELECT RAISE(ABORT,'injected'); END")
        self.db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            store.publish(record.record_id, self.raw)
        self.assertEqual(self.db.execute("SELECT state FROM tasks WHERE id=7").fetchone()[0], "running")
        self.assertEqual(self.db.execute("SELECT count(*) FROM image_vector_artifacts").fetchone()[0], 0)
        self.assertEqual(self.db.execute("SELECT state FROM image_vector_publications WHERE record_id=?",
                                         (record.record_id,)).fetchone()[0], "prepared")

    def test_committed_intent_is_idempotent_only_with_exact_finished_claim(self):
        store, record = self.prepared()
        store.publish(record.record_id, self.raw)
        self.assertEqual(self.store().publish(record.record_id, self.raw), "committed")
        self.db.execute("UPDATE tasks SET retry_count=3 WHERE id=7")
        self.db.commit()
        with self.assertRaises(VectorPublicationRefused):
            self.store().publish(record.record_id, self.raw)

    def test_artifact_paths_are_identity_scoped_and_legacy_files_are_untouched(self):
        legacy = self.root / "embeddings" / "11.npy"
        legacy.parent.mkdir()
        legacy.write_bytes(b"legacy remains")
        store, record = self.prepared()
        store.publish(record.record_id, self.raw)
        self.assertEqual(record.relative_path,
                         f"image-vectors/{record.identity_sha256}/{record.record_id}.npy")
        self.assertEqual(legacy.read_bytes(), b"legacy remains")
        self.assertFalse((self.root / "embeddings").joinpath("11.npy").read_bytes() == self.raw)


if __name__ == "__main__":
    unittest.main()

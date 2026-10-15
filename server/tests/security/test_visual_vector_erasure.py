"""Synthetic receipt-bound erasure checks for immutable image vectors."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import struct
import subprocess
import sys
import threading
import unittest
from unittest.mock import patch
from dataclasses import asdict, replace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import test_asset_tombstones as asset_fixtures
from test_asset_tombstones import IDENTITY, NOW, SOURCE_SHA, _npy
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256
from app.access.visual_vector_erasure import (
    VectorErasureRefused,
    VectorErasureStore,
    create_visual_erasure_schema,
    verify_visual_erasure_schema,
)
from app.access.visual_vector_publication import (
    VectorPublicationRefused,
    VectorPublicationStore,
    create_visual_publication_schema,
)


CLAIM = "d" * 64


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _record(asset_id, version, *, record_suffix="", raw=None):
    identity = VectorSpaceIdentity(
        IDENTITY.artifact_sha256, IDENTITY.preprocessing_sha256,
        IDENTITY.vector_space_id, version, IDENTITY.dimension, IDENTITY.normalization,
    )
    raw = _npy((1.0, 0.0)) if raw is None else raw
    record_id = _sha(f"asset-{asset_id}-{version}-{record_suffix}".encode())
    identity_digest = identity_sha256(identity)
    relative = f"image-vectors/{identity_digest}/{record_id}.npy"
    return ImmutableVectorArtifact(
        record_id, str(asset_id), SOURCE_SHA, "synthetic-model",
        identity.artifact_sha256, identity.preprocessing_sha256,
        identity.vector_space_id, identity.model_version, identity.dimension,
        identity.normalization, identity_digest, relative, _sha(raw),
        canonical_vector_checksum((1.0, 0.0)), NOW, "ready",
    ), raw


class VisualVectorErasureTests(unittest.TestCase):
    def setUp(self):
        self.fixture = asset_fixtures.AssetTombstoneTests(
            "test_exact_retry_succeeds_but_changed_binding_is_refused")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.db = self.fixture.db
        self.base = self.fixture.root
        self.vector_root = self.fixture.vector_root
        self.private_root = self.vector_root
        self.private_root.chmod(0o700)
        self._add_asset(102)
        create_visual_publication_schema(self.db)
        create_visual_erasure_schema(self.db)
        self.db.commit()
        self.journal = self.fixture.journal
        self.fixture._append_and_apply(self.db, 102)
        self.db.commit()

    def _add_asset(self, asset_id):
        self.fixture._add_asset(self.db, asset_id)

    def store(self, db=None):
        return VectorErasureStore(self.db if db is None else db, self.private_root, self.journal)

    def final_path(self, record):
        return self.vector_root / record.relative_path

    def add_ready(self, asset_id, version, suffix=""):
        record, raw = _record(asset_id, version, record_suffix=suffix)
        target = self.final_path(record)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        self.db.execute(
            "INSERT INTO image_vector_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (record.record_id, int(record.asset_id), record.source_sha256, record.model_name,
             record.artifact_sha256, record.preprocessing_sha256, record.vector_space_id,
             record.model_version, record.dimension, record.normalization, record.identity_sha256,
             record.relative_path, record.file_sha256, record.component_sha256,
             record.created_at, record.status),
        )
        return record, target, raw

    def add_intent(self, asset_id, version, state="prepared", suffix=""):
        record, raw = _record(asset_id, version, record_suffix=suffix)
        raw_json = json.dumps(record.__dict__ if hasattr(record, "__dict__") else {
            name: getattr(record, name) for name in record.__dataclass_fields__
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.db.execute(
            "INSERT INTO image_vector_publications VALUES (?,?,?,?,?,?)",
            (record.record_id, asset_id, _sha(record.record_id.encode()), raw_json, state, record.created_at),
        )
        return record, raw

    def add_stage(self, record, raw):
        stage = self.vector_root / "image-vectors" / ".staging" / f"{record.record_id}.npy"
        stage.parent.mkdir(parents=True, exist_ok=True)
        stage.write_bytes(raw)
        return stage

    def quarantine(self, job_id, index=0):
        return self.vector_root / "image-vectors" / ".erasing" / job_id / f"{index:03d}.npy"

    def progress(self, job_id):
        return self.db.execute(
            "SELECT total_files,next_file FROM image_vector_erasures WHERE job_id=?", (job_id,)
        ).fetchone()

    def test_ready_multiple_profiles_are_planned_erased_and_metadata_retained(self):
        one = self.add_ready(102, "v1")
        self.add_ready(102, "v2")
        unaffected = self.add_ready(101, "v2")
        self.db.commit()
        metadata = self.db.execute(
            "SELECT record_id,relative_path,file_sha256,status FROM image_vector_artifacts "
            "WHERE asset_id=102 ORDER BY record_id"
        ).fetchall()

        job = self.store().prepare(102)
        self.assertEqual(self.store().prepare(102), job)
        self.assertTrue(self.final_path(one[0]).exists())
        self.assertEqual(self.progress(job), (2, 0))
        self.assertFalse(self.store().step(job))
        self.assertTrue(self.store().step(job))
        self.assertEqual(self.progress(job), (2, 2))
        self.assertEqual(self.db.execute(
            "SELECT record_id,relative_path,file_sha256,status FROM image_vector_artifacts "
            "WHERE asset_id=102 ORDER BY record_id"
        ).fetchall(), metadata)
        self.assertEqual(self.final_path(unaffected[0]).read_bytes(), unaffected[2])

    def test_publication_intent_forms_and_exact_hardlink_pair(self):
        cases = ("missing", "stage", "final", "copies", "links")
        for suffix, form in enumerate(cases):
            record, raw = self.add_intent(102, "intent" + str(suffix), suffix="case")
            if form in ("stage", "copies", "links"):
                stage = self.add_stage(record, raw)
            else:
                stage = None
            final = self.final_path(record)
            if form in ("final", "copies", "links"):
                final.parent.mkdir(parents=True, exist_ok=True)
                final.write_bytes(raw)
            if form == "links":
                final.unlink()
                os.link(stage, final)
        self.db.commit()
        job = self.store().prepare(102)
        while not self.store().step(job):
            pass
        self.assertEqual(self.progress(job), (10, 10))
        self.assertEqual(self.db.execute(
            "SELECT count(*) FROM image_vector_publications WHERE asset_id=102"
        ).fetchone(), (5,))

    def test_extra_hardlink_refuses_and_preserves_every_known_name(self):
        record, raw = self.add_intent(102, "v1", suffix="extra-link")
        stage = self.add_stage(record, raw)
        final = self.final_path(record)
        final.parent.mkdir(parents=True, exist_ok=True)
        os.link(stage, final)
        extra = self.vector_root / "outside-known-vector-name.npy"
        os.link(stage, extra)
        self.db.commit()
        with self.assertRaises(VectorErasureRefused):
            self.store().prepare(102)
        self.assertEqual(stage.read_bytes(), raw)
        self.assertEqual(final.read_bytes(), raw)
        self.assertEqual(extra.read_bytes(), raw)

    def test_corrupt_later_file_refuses_before_any_quarantine_or_source_mutation(self):
        first = self.add_ready(102, "v1")
        second = self.add_ready(102, "v2")
        self.db.commit()
        second[1].write_bytes(b"partial npy")
        before = {path: path.read_bytes() for path in (first[1], second[1])}
        with self.assertRaises(VectorErasureRefused):
            self.store().prepare(102)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse((self.vector_root / "image-vectors" / ".erasing").exists())

    def test_stale_or_uncommitted_withdrawal_receipt_refuses(self):
        self.add_ready(102, "v1")
        self.db.commit()
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute("UPDATE access_original_deletion_state SET applied_seq=0,applied_digest=?", ("0" * 64,))
        with self.assertRaises(VectorErasureRefused):
            self.store().prepare(102)

    def test_deleted_parent_publication_guard_cannot_be_bypassed_by_trusted_callback(self):
        record, _raw = _record(102, "v1")
        publisher = VectorPublicationStore(
            self.db, self.vector_root, IDENTITY,
            guard=lambda *_args: True, finalize=lambda *_args: None,
        )
        with self.assertRaises(VectorPublicationRefused):
            publisher.prepare(record, CLAIM)
        self.db.rollback()
        self.db.execute("BEGIN IMMEDIATE")
        self.db.execute("UPDATE assets SET status='active' WHERE id=102")
        self.db.commit()
        with self.assertRaises(VectorErasureRefused):
            self.store().prepare(102)

    def test_manifest_is_immutable_monotonic_and_schema_is_exact(self):
        self.add_ready(102, "v1")
        self.db.commit()
        self.assertTrue(verify_visual_erasure_schema(self.db))
        job = self.store().prepare(102)
        before = self.db.execute(
            "SELECT manifest_json,total_files,next_file FROM image_vector_erasures WHERE job_id=?", (job,)
        ).fetchone()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE image_vector_erasures SET next_file=next_file+2 WHERE job_id=?", (job,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE image_vector_erasures SET manifest_json='{}' WHERE job_id=?", (job,))
        self.db.rollback()
        self.assertEqual(self.db.execute(
            "SELECT manifest_json,total_files,next_file FROM image_vector_erasures WHERE job_id=?", (job,)
        ).fetchone(), before)

    def test_cap_129_refuses_without_filesystem_mutation(self):
        for index in range(129):
            record, _raw = _record(102, f"v{index:03d}")
            self.db.execute(
                "INSERT INTO image_vector_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (record.record_id, 102, record.source_sha256, record.model_name,
                 record.artifact_sha256, record.preprocessing_sha256, record.vector_space_id,
                 record.model_version, record.dimension, record.normalization, record.identity_sha256,
                 record.relative_path, record.file_sha256, record.component_sha256,
                 record.created_at, record.status),
            )
        self.db.commit()
        with patch("app.access.visual_vector_erasure._inspect",
                   side_effect=AssertionError("cap must be checked before file access")):
            with self.assertRaises(VectorErasureRefused):
                self.store().prepare(102)
        self.assertEqual(self.db.execute("SELECT count(*) FROM image_vector_erasures").fetchone(), (0,))

    def test_no_overwrite_collision_and_wrong_quarantine_bytes_are_preserved(self):
        record, source, raw = self.add_ready(102, "v1")
        self.db.commit()
        store = self.store()
        job = store.prepare(102)
        destination = self.quarantine(job)
        destination.parent.parent.mkdir(mode=0o700)
        destination.parent.parent.chmod(0o700)
        destination.parent.mkdir(mode=0o700)
        destination.parent.chmod(0o700)
        destination.write_bytes(b"unrelated occupant")
        with self.assertRaises(VectorErasureRefused):
            store.step(job)
        self.assertEqual(source.read_bytes(), raw)
        self.assertEqual(destination.read_bytes(), b"unrelated occupant")
        destination.unlink()
        real_link = os.link
        def inject_collision(source_name, target_name, **kwargs):
            Path(target_name).write_bytes(b"racing occupant")
            return real_link(source_name, target_name, **kwargs)
        with patch("app.access.visual_vector_erasure.os.link", side_effect=inject_collision):
            with self.assertRaises(VectorErasureRefused):
                store.step(job)
        self.assertEqual(source.read_bytes(), raw)
        self.assertEqual(destination.read_bytes(), b"racing occupant")

    def test_nonprivate_root_and_symlink_parent_refuse_without_following(self):
        _record_value, source, raw = self.add_ready(102, "v1")
        self.db.commit()
        self.private_root.chmod(0o755)
        with self.assertRaises(VectorErasureRefused):
            self.store().prepare(102)
        self.private_root.chmod(0o700)

        parent = source.parent
        saved = parent.with_name(parent.name + ".saved")
        outside = self.base / "outside-vectors"
        outside.mkdir()
        (outside / source.name).write_bytes(raw)
        parent.rename(saved)
        parent.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(VectorErasureRefused):
            self.store().prepare(102)
        self.assertEqual((outside / source.name).read_bytes(), raw)
        self.assertTrue(parent.is_symlink())
        parent.unlink()
        saved.rename(parent)

    def test_changed_root_or_artifact_metadata_after_plan_refuses(self):
        record, source, raw = self.add_ready(102, "v1")
        self.db.commit()
        store = self.store()
        job = store.prepare(102)
        other_root = self.base / "other-private"
        other_root.mkdir(mode=0o700)
        other_root.chmod(0o700)
        with self.assertRaises(VectorErasureRefused):
            VectorErasureStore(self.db, other_root, self.journal).step(job)
        self.db.execute("DROP TRIGGER trg_image_vector_artifacts_immutable_update")
        self.db.execute("UPDATE image_vector_artifacts SET file_sha256=? WHERE record_id=?",
                        ("0" * 64, record.record_id))
        self.db.commit()
        with self.assertRaises(VectorErasureRefused):
            store.step(job)
        self.assertEqual(source.read_bytes(), raw)

    def test_completed_source_name_reappearance_is_refused_and_preserved(self):
        _record_value, source, raw = self.add_ready(102, "v1")
        self.db.commit()
        store = self.store()
        job = store.prepare(102)
        self.assertTrue(store.step(job))
        source.write_bytes(raw)
        with self.assertRaises(VectorErasureRefused):
            store.step(job)
        self.assertEqual(source.read_bytes(), raw)

    def test_empty_job_still_requires_both_optional_contracts(self):
        self.db.commit()
        self.assertTrue(verify_visual_erasure_schema(self.db))
        job = self.store().prepare(102)
        self.assertEqual(self.progress(job), (0, 0))
        self.assertTrue(self.store().step(job))
        self.db.execute("DROP TABLE image_vector_publications")
        self.db.commit()
        with self.assertRaises(VectorErasureRefused):
            self.store().prepare(102)

    def test_committed_intent_requires_exact_ready_binding(self):
        record, source, raw = self.add_ready(102, "v1")
        mismatched = replace(record, model_name="different-synthetic-model")
        self.db.execute("INSERT INTO image_vector_publications VALUES (?,?,?,?,?,?)",
                        (record.record_id, 102, CLAIM,
                         json.dumps(asdict(mismatched), sort_keys=True, separators=(",", ":")),
                         "committed", NOW))
        self.db.commit()
        with self.assertRaises(VectorErasureRefused):
            self.store().prepare(102)
        self.assertEqual(source.read_bytes(), raw)
        self.assertFalse((self.vector_root / "image-vectors" / ".erasing").exists())

    def test_matching_committed_intent_retains_rows_after_cleanup(self):
        _record_value, source, _raw = self.add_ready(102, "v1")
        self.add_intent(102, "v1", state="committed")
        self.db.commit()
        job = self.store().prepare(102)
        while not self.store().step(job):
            pass
        self.assertFalse(source.exists())
        self.assertEqual(self.db.execute("SELECT state FROM image_vector_publications "
                                         "WHERE asset_id=102").fetchone(), ("committed",))
        self.assertEqual(self.db.execute("SELECT count(*) FROM image_vector_artifacts "
                                         "WHERE asset_id=102").fetchone(), (1,))

    def test_sqlite_commit_failure_after_unlink_recovers_absent_names(self):
        _record_value, source, _raw = self.add_ready(102, "v1")
        self.db.commit()
        job = self.store().prepare(102)

        class FailedCommit(sqlite3.Connection):
            def commit(self):
                raise sqlite3.OperationalError("synthetic commit failure")

        failed = sqlite3.connect(self.fixture.primary_path, factory=FailedCommit)
        try:
            failed.execute("PRAGMA foreign_keys=ON")
            with self.assertRaises(VectorErasureRefused):
                self.store(failed).step(job)
            self.assertFalse(failed.in_transaction)
        finally:
            failed.close()
        self.assertFalse(source.exists())
        self.assertFalse(self.quarantine(job).exists())
        self.assertEqual(self.progress(job), (1, 0))
        self.assertTrue(self.store().step(job))
        self.assertEqual(self.progress(job), (1, 1))

    def test_crashes_after_link_source_unlink_and_quarantine_unlink_resume(self):
        record, source, raw = self.add_ready(102, "v1")
        record2, source2, raw2 = self.add_ready(102, "v2")
        self.db.commit()
        store = self.store()
        job = store.prepare(102)
        manifest = json.loads(self.db.execute(
            "SELECT manifest_json FROM image_vector_erasures WHERE job_id=?", (job,)
        ).fetchone()[0])
        sources = {record.relative_path: (source, raw), record2.relative_path: (source2, raw2)}
        first_relative = manifest["paths"][0][0]
        first_source, first_raw = sources[first_relative]
        second_relative = manifest["paths"][1][0]
        second_source, second_raw = sources[second_relative]
        q = self.quarantine(job, 0)
        q2 = self.quarantine(job, 1)

        real_link = os.link
        with patch("app.access.visual_vector_erasure.os.link", side_effect=lambda *a, **kw: (real_link(*a, **kw), (_ for _ in ()).throw(RuntimeError("crash")))[1]):
            with self.assertRaises(RuntimeError):
                store.step(job)
        self.assertEqual(self.progress(job), (2, 0))
        self.assertEqual(first_source.read_bytes(), first_raw)
        self.assertEqual(q.read_bytes(), first_raw)
        self.assertFalse(store.step(job))
        self.assertEqual(self.progress(job), (2, 1))

        # Now recover after the second source unlink, then after its quarantine
        # unlink, while the same immutable two-file plan remains pending.
        real_unlink = Path.unlink
        def stop_after_source(path, *args, **kwargs):
            result = real_unlink(path, *args, **kwargs)
            if path == second_source:
                raise RuntimeError("crash after source unlink")
            return result
        with patch.object(Path, "unlink", stop_after_source):
            with self.assertRaises(RuntimeError):
                store.step(job)
        self.assertEqual(self.progress(job), (2, 1))
        self.assertFalse(second_source.exists())
        self.assertEqual(q2.read_bytes(), second_raw)
        real_unlink = Path.unlink
        def stop_after_quarantine(path, *args, **kwargs):
            result = real_unlink(path, *args, **kwargs)
            if path == q2:
                raise RuntimeError("crash after quarantine unlink")
            return result
        with patch.object(Path, "unlink", stop_after_quarantine):
            with self.assertRaises(RuntimeError):
                store.step(job)
        self.assertEqual(self.progress(job), (2, 1))
        self.assertFalse(second_source.exists())
        self.assertFalse(q2.exists())
        self.assertTrue(store.step(job))
        self.assertEqual(self.progress(job), (2, 2))

    def test_process_death_after_quarantine_link_recovers_in_fresh_process(self):
        _record_value, source, raw = self.add_ready(102, "v1")
        self.db.commit()
        job = self.store().prepare(102)
        code = r'''import os,sqlite3,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import app.access.visual_vector_erasure as erasure
from app.access.original_deletions import OriginalDeletionJournal
db=sqlite3.connect(sys.argv[2]);db.execute("PRAGMA foreign_keys=ON");db.execute("PRAGMA synchronous=FULL")
journal=OriginalDeletionJournal(sys.argv[3],sys.argv[4])
link=erasure.os.link
def die_after_link(*args,**kwargs):
    link(*args,**kwargs)
    os._exit(47)
erasure.os.link=die_after_link
erasure.VectorErasureStore(db,Path(sys.argv[5]),journal).step(sys.argv[6])
'''
        child = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, str(ROOT / "backend"),
             str(self.fixture.primary_path), str(self.fixture.journal_path),
             self.fixture.namespace, str(self.private_root), job],
            capture_output=True, timeout=30,
        )
        self.assertEqual(child.returncode, 47, child.stderr.decode(errors="replace"))
        quarantine = self.quarantine(job)
        self.assertEqual(source.read_bytes(), raw)
        self.assertEqual(quarantine.read_bytes(), raw)
        self.assertTrue(self.store().step(job))
        self.assertEqual(self.progress(job), (1, 1))
        self.assertFalse(source.exists())
        self.assertFalse(quarantine.exists())

    def test_concurrent_writer_is_serialized_while_step_is_in_progress(self):
        record, _source, _raw = self.add_ready(102, "v1")
        self.db.commit()
        job = self.store().prepare(102)
        other = sqlite3.connect(self.fixture.primary_path, timeout=0.05)
        other.execute("PRAGMA foreign_keys=ON")
        entered, release = threading.Event(), threading.Event()
        real_inspect = __import__("app.access.visual_vector_erasure", fromlist=["_inspect"])._inspect
        failure = []
        def slow_inspect(*args, **kwargs):
            if not entered.is_set():
                entered.set()
                release.wait(2)
            return real_inspect(*args, **kwargs)
        def run_step():
            worker_db = sqlite3.connect(self.fixture.primary_path, timeout=5)
            try:
                worker_db.execute("PRAGMA foreign_keys=ON")
                worker_db.execute("PRAGMA synchronous=FULL")
                self.store(worker_db).step(job)
            except Exception as error:  # pragma: no cover - surfaced below
                failure.append(error)
            finally:
                worker_db.close()
        worker = threading.Thread(target=run_step)
        with patch("app.access.visual_vector_erasure._inspect", side_effect=slow_inspect):
            worker.start()
            self.assertTrue(entered.wait(2))
            with self.assertRaises(sqlite3.OperationalError):
                other.execute("BEGIN IMMEDIATE")
            release.set()
            worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failure, [])
        other.close()


if __name__ == "__main__":
    unittest.main()

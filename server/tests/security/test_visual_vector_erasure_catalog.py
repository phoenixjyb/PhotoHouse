"""Generated backup/restore closure tests; no live media or database access."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import subprocess
import unittest
from unittest.mock import patch
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(Path(__file__).resolve().parent)]
import test_visual_vector_erasure as fixtures
from app.access.visual_vector_erasure import VectorErasureRefused, VectorErasureStore
from app.access.visual_vector_erasure_catalog import VectorCatalogRefused, VectorErasureCatalog


class VectorErasureCatalogTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.VisualVectorErasureTests(
            "test_ready_multiple_profiles_are_planned_erased_and_metadata_retained")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.vector_root
        self.catalog_root = self.fixture.base / "catalog"
        self.catalog_root.mkdir(mode=0o700)
        self.catalog = VectorErasureCatalog(self.catalog_root)
        self.db = self.fixture.db

    def store(self, db=None, root=None):
        return VectorErasureStore(db or self.db, root or self.root,
                                 self.fixture.journal, catalog=self.catalog)

    def test_archive_is_private_exact_and_idempotent_and_required_before_step(self):
        _record, source, raw = self.fixture.add_ready(102, "v2")
        self.db.commit()
        store = self.store()
        job = store.prepare(102)
        path = self.catalog_root / (job + ".json")
        self.assertEqual(store.prepare(102), job)
        self.assertEqual(self.catalog.archive(self.catalog.read(job)), job)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        original = path.read_bytes()
        path.unlink()
        with self.assertRaises(VectorErasureRefused):
            store.step(job)
        self.assertEqual(source.read_bytes(), raw)
        self.assertEqual(store.prepare(102), job)
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(store.step(job))

    def test_partial_archive_refuses_without_overwrite_or_vector_mutation(self):
        _record, source, raw = self.fixture.add_ready(102, "v2")
        self.db.commit()
        store = self.store()
        with patch("app.access.visual_vector_erasure_catalog.os.fsync",
                   side_effect=OSError("synthetic interrupted archive sync")):
            with self.assertRaises(VectorErasureRefused):
                store.prepare(102)
        job = self.db.execute("SELECT job_id FROM image_vector_erasures WHERE asset_id=102").fetchone()[0]
        path = self.catalog_root / (job + ".json")
        path.write_bytes(b'{"partial":')
        with self.assertRaises(VectorErasureRefused):
            store.prepare(102)
        with self.assertRaises(VectorErasureRefused):
            store.step(job)
        self.assertEqual(path.read_bytes(), b'{"partial":')
        self.assertEqual(source.read_bytes(), raw)

    def test_process_death_during_archive_creation_blocks_cleanup(self):
        _record, source, raw = self.fixture.add_ready(102, "v2")
        self.db.commit()
        code = '''import os,sqlite3,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from app.access.original_deletions import OriginalDeletionJournal
from app.access.visual_vector_erasure import VectorErasureStore
from app.access.visual_vector_erasure_catalog import VectorErasureCatalog
real=os.fdopen
class Partial:
    def __init__(self,stream):self.stream=stream
    def __enter__(self):return self
    def __exit__(self,*args):self.stream.close()
    def write(self,raw):
        self.stream.write(raw[:20]);self.stream.flush();os._exit(47)
os.fdopen=lambda *args,**kwargs:Partial(real(*args,**kwargs))
db=sqlite3.connect(sys.argv[2]);db.execute('PRAGMA foreign_keys=ON')
journal=OriginalDeletionJournal(sys.argv[3],sys.argv[4])
catalog=VectorErasureCatalog(Path(sys.argv[6]))
VectorErasureStore(db,Path(sys.argv[5]),journal,catalog=catalog).prepare(102)
'''
        fixture = self.fixture.fixture
        child = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(ROOT / "backend"),
                                str(fixture.primary_path), str(fixture.journal_path), fixture.namespace,
                                str(self.root), str(self.catalog_root)], capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 47, child.stderr.decode(errors="replace"))
        job = self.db.execute("SELECT job_id FROM image_vector_erasures WHERE asset_id=102").fetchone()[0]
        path = self.catalog_root / (job + ".json")
        self.assertEqual(path.stat().st_size, 20)
        with self.assertRaises(VectorErasureRefused):
            self.store().step(job)
        with self.assertRaises(VectorErasureRefused):
            self.store().prepare(102)
        self.assertEqual(path.stat().st_size, 20)
        self.assertEqual(source.read_bytes(), raw)

    def test_catalog_digest_size_links_and_symlinks_are_not_trusted(self):
        self.fixture.add_ready(102, "v2")
        self.db.commit()
        job = self.store().prepare(102)
        path = self.catalog_root / (job + ".json")
        original = path.read_bytes()
        parsed = json.loads(original)
        parsed["asset_id"] = 101
        path.write_text(json.dumps(parsed, sort_keys=True, separators=(",", ":")) + "\n")
        with self.assertRaises(VectorCatalogRefused):
            self.catalog.read(job)
        path.write_bytes(original)
        extra = self.catalog_root / "extra-link.json"
        os.link(path, extra)
        with self.assertRaises(VectorCatalogRefused):
            self.catalog.read(job)
        extra.unlink()
        path.unlink()
        outside = self.fixture.base / "outside-catalog.json"
        outside.write_bytes(original)
        path.symlink_to(outside)
        with self.assertRaises(VectorCatalogRefused):
            self.catalog.read(job)
        self.assertEqual(outside.read_bytes(), original)
        for value in ("../escape", "HEAD", True, None):
            with self.subTest(value=value), self.assertRaises(VectorCatalogRefused):
                self.catalog.read(value)

    def _backup_and_interrupt(self):
        backup = self.fixture.base / "older.sqlite"
        with sqlite3.connect(backup) as target:
            self.db.backup(target)
        record, _source, raw = self.fixture.add_ready(101, "v2")
        self.fixture.add_intent(101, "v2", state="committed")
        stage = self.root / "image-vectors" / ".staging" / (record.record_id + ".npy")
        stage.parent.mkdir(parents=True, exist_ok=True)
        os.link(self.root / record.relative_path, stage)
        self.db.commit()
        self.fixture.fixture._append_and_apply(self.db, 101)
        self.db.commit()
        store = self.store()
        job = store.prepare(101)
        real_link = os.link
        def stop_after_link(*args, **kwargs):
            real_link(*args, **kwargs)
            raise RuntimeError("synthetic process interruption")
        with patch("app.access.visual_vector_erasure.os.link", side_effect=stop_after_link):
            with self.assertRaises(RuntimeError):
                store.step(job)
        self.assertEqual(self.fixture.quarantine(job).read_bytes(), raw)
        path = self.fixture.base / "restored.sqlite"
        shutil.copyfile(backup, path)
        restored = sqlite3.connect(path)
        restored.execute("PRAGMA foreign_keys=ON")
        self.addCleanup(restored.close)
        self.assertEqual(restored.execute("SELECT status FROM assets WHERE id=101").fetchone()[0], "active")
        self.fixture.journal.replay(restored)
        return restored, record, job

    def test_older_backup_restores_publication_closure_then_resumes_quarantine(self):
        restored, record, job = self._backup_and_interrupt()
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_erasures").fetchone(), (0,))
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_artifacts WHERE asset_id=101").fetchone(), (1,))
        store = self.store(restored)
        self.assertEqual(store.restore(job), job)
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_artifacts WHERE asset_id=101").fetchone(), (2,))
        self.assertEqual(store.restore(job), job)
        while not store.step(job):
            pass
        self.assertFalse((self.root / record.relative_path).exists())
        self.assertFalse(self.fixture.quarantine(job).exists())
        self.assertEqual(restored.execute("SELECT total_files,next_file FROM image_vector_erasures").fetchone(), (3, 3))
        self.assertEqual(restored.execute("SELECT state FROM image_vector_publications WHERE asset_id=101").fetchone(), ("committed",))
        self.assertEqual(self.fixture.fixture.source_path.read_bytes(), fixtures.asset_fixtures.SOURCE)

    def test_corrupt_quarantine_rolls_back_restored_metadata_and_preserves_bytes(self):
        restored, _record, job = self._backup_and_interrupt()
        quarantine = self.fixture.quarantine(job)
        quarantine.write_bytes(b"unqualified quarantine")
        with self.assertRaises(VectorErasureRefused):
            self.store(restored).restore(job)
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_artifacts WHERE asset_id=101").fetchone(), (1,))
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_publications WHERE asset_id=101").fetchone(), (0,))
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_erasures").fetchone(), (0,))
        self.assertEqual(quarantine.read_bytes(), b"unqualified quarantine")

    def test_older_prepared_intent_can_restore_its_exact_committed_closure(self):
        restored, _record, job = self._backup_and_interrupt()
        archived = self.catalog.read(job)["metadata"]["intents"][0]
        prior = list(archived)
        prior[4] = "prepared"
        restored.execute("INSERT INTO image_vector_publications VALUES (?,?,?,?,?,?)", prior)
        restored.commit()
        self.store(restored).restore(job)
        self.assertEqual(restored.execute("SELECT state FROM image_vector_publications").fetchone(), ("committed",))
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_artifacts WHERE asset_id=101").fetchone(), (2,))

    def test_unexpected_later_record_refuses_before_importing_any_catalog_rows(self):
        restored, _record, job = self._backup_and_interrupt()
        extra, path, raw = self.fixture.add_ready(101, "unreviewed-v3")
        self.db.commit()
        values = list(asdict(extra).values())
        values[1] = 101
        restored.execute("INSERT INTO image_vector_artifacts VALUES (" +
                         ",".join("?" for _ in values) + ")", values)
        restored.commit()
        with self.assertRaises(VectorErasureRefused):
            self.store(restored).restore(job)
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_artifacts WHERE asset_id=101").fetchone(), (2,))
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_publications").fetchone(), (0,))
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_erasures").fetchone(), (0,))
        self.assertEqual(path.read_bytes(), raw)

    def test_restore_requires_replayed_committed_withdrawal_and_matching_root(self):
        restored, _record, job = self._backup_and_interrupt()
        restored.execute("UPDATE assets SET status='active' WHERE id=101")
        restored.commit()
        with self.assertRaises(VectorErasureRefused):
            self.store(restored).restore(job)
        restored.execute("UPDATE assets SET status='deleted' WHERE id=101")
        restored.commit()
        other = self.fixture.base / "different-vectors"
        other.mkdir(mode=0o700)
        with self.assertRaises(VectorErasureRefused):
            self.store(restored, other).restore(job)
        self.assertEqual(restored.execute("SELECT count(*) FROM image_vector_erasures").fetchone(), (0,))

    def test_catalog_cannot_be_inside_the_vector_root(self):
        nested = self.root / "unsafe-recovery"
        nested.mkdir(mode=0o700)
        with self.assertRaises(VectorErasureRefused):
            VectorErasureStore(self.db, self.root, self.fixture.journal,
                               catalog=VectorErasureCatalog(nested))

    def test_existing_complete_archive_is_resynced_on_retry(self):
        self.fixture.add_ready(102, "v2")
        self.db.commit()
        job = self.store().prepare(102)
        real_fsync = os.fsync
        with patch("app.access.visual_vector_erasure_catalog.os.fsync", wraps=real_fsync) as sync:
            self.catalog.archive(self.catalog.read(job))
        self.assertGreaterEqual(sync.call_count, 1)


if __name__ == "__main__":
    unittest.main()

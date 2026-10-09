"""Approved worker admission against the actual additive D1 SQLite migration."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType
import unittest
import uuid
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import approved_face_queue
import run_approved_cpu_worker as cpu_worker
import run_approved_image_embed_worker as image_worker
import run_approved_video_embed_worker as video_embed_worker
import run_approved_video_worker as video_worker_module
import test_memory_book_edition_migration as edition_migration

D1 = 'd1f6a8c3e920'


class _OptionalNumpyUnavailable(ModuleType):
    """Fail if this schema-only test enters NumPy-backed inference code."""

    def __getattr__(self, name):
        raise AssertionError(f'NumPy-backed face inference was reached: {name}')


def _face_worker_without_numpy():
    """Load the real worker while making its optional inference package absent."""
    import importlib.util

    module_name = '_photohouse_d1_face_worker_without_numpy'
    worker_path = ROOT / 'scripts' / 'run_approved_face_worker.py'
    spec = importlib.util.spec_from_file_location(module_name, worker_path)
    if spec is None or spec.loader is None:
        raise AssertionError('face worker module could not be loaded')
    worker = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'numpy': _OptionalNumpyUnavailable('numpy')}):
        spec.loader.exec_module(worker)
    return worker


class ApprovedWorkersD1CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = edition_migration.MemoryBookEditionMigrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        owner = self.fixture._upgrade_to_b1_with_existing_editorial()
        self.fixture._upgrade()
        self.fixture.migration.upgrade(D1)
        self.database = self.fixture.migration.path.resolve(strict=True)
        self.library = edition_migration.editorial_fixture.LIBRARY
        self.owner = owner

        self.temp = tempfile.TemporaryDirectory(prefix='photohouse-approved-d1-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.originals = self.root / 'originals'
        self.derived = self.root / 'derived'
        self.originals.mkdir()
        self.derived.mkdir()
        self.stop = self.root / 'stop.flag'

        self.paths = {
            101: self.originals / 'approved.png',
            102: self.originals / 'approved.mp4',
            103: self.originals / 'incoming.png',
            104: self.originals / 'incoming.mp4',
        }
        Image.new('RGB', (32, 24), (50, 80, 110)).save(self.paths[101])
        self.paths[102].write_bytes(b'synthetic approved video')
        Image.new('RGB', (32, 24), (90, 20, 10)).save(self.paths[103])
        self.paths[104].write_bytes(b'synthetic incoming video')

        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            self._asset(db, 101, 'image/png', assigned=True)
            self._asset(db, 102, 'video/mp4', assigned=True)
            self._asset(db, 103, 'image/png', assigned=False)
            self._asset(db, 104, 'video/mp4', assigned=False)
            self._task(db, 'thumb', 101)
            self._task(db, 'thumb', 103)
            self._task(db, 'video_probe', 102)
            self._task(db, 'video_probe', 104)
            self._task(db, 'embed', 101, modality='image')
            self._task(db, 'embed', 103, modality='image')
            self._task(db, 'video_embed', 102)
            self._task(db, 'video_embed', 104)
            self._task(db, 'face', 101)
            self._task(db, 'face', 103)
            db.commit()

        self.frame_dir = self.derived / 'video_frames' / '102'
        self.frame_dir.mkdir(parents=True)
        Image.new('RGB', (24, 16), (20, 50, 90)).save(self.frame_dir / 'frame_00001.jpg')
        self.checkpoint = self.root / 'synthetic.ckpt'
        self.checkpoint.write_bytes(b'synthetic local checkpoint')
        self.checkpoint_sha256 = hashlib.sha256(self.checkpoint.read_bytes()).hexdigest()

    def _asset(self, db, asset_id, mime, *, assigned):
        path = self.paths[asset_id]
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        size = len(content)
        exists = db.execute('SELECT 1 FROM assets WHERE id=?', (asset_id,)).fetchone()
        if exists:
            db.execute('''UPDATE assets SET path=?,hash_sha256=?,file_size=?,mime=?,status='active'
                WHERE id=?''', (str(path), digest, size, mime, asset_id))
        else:
            db.execute('''INSERT INTO assets(id,path,hash_sha256,file_size,mime,status)
                VALUES(?,?,?,?,?,'active')''', (asset_id, str(path), digest, size, mime))
        state = 'assigned' if assigned else 'incoming'
        db.execute('''INSERT INTO access_uploads
            (id,asset_id,account_id,incoming_label,batch,original_name,sha256,bytes,state,
             created_at,destination_library_id,approval_mode)
            VALUES(?,?,?,?,?,?,?,?,?,1,?,?)''',
            (asset_id, asset_id, self.owner, 'synthetic-owner',
             f'{asset_id:032x}', path.name, digest, size, state,
             self.library if assigned else None, 'manual' if assigned else None))
        if assigned:
            db.execute('''INSERT INTO access_asset_libraries(asset_id,library_id) VALUES(?,?)
                ON CONFLICT(asset_id) DO UPDATE SET library_id=excluded.library_id''',
                (asset_id, self.library))

    @staticmethod
    def _task(db, kind, asset_id, *, modality=None):
        payload = {'asset_id': asset_id}
        if modality is not None:
            payload['modality'] = modality
        db.execute('''INSERT INTO tasks
            (type,payload_json,state,priority,retry_count,cancel_requested,scheduled_at,created_at)
            VALUES(?,?,'pending',40,0,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)''',
            (kind, json.dumps(payload, sort_keys=True, separators=(',', ':'))))

    def _snapshot(self):
        with closing(sqlite3.connect(self.database)) as db:
            objects = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
            tables = [row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            rows = {table: db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
                    for table in tables if table != 'alembic_version'}
            return objects, rows

    def test_all_approved_worker_gates_accept_actual_d1_and_keep_private_rows_ineligible(self):
        before = self._snapshot()
        with closing(cpu_worker.connect(self.database)) as db:
            self.assertEqual(cpu_worker.validate_schema(db), D1)
            self.assertEqual([row[0] for row in cpu_worker.matching_candidates(db)], [1])

        video_worker = video_worker_module.ApprovedVideoWorker(
            self.database, self.derived, (self.originals,),
            ffprobe=str(self._executable('ffprobe.exe')),
            ffmpeg=str(self._executable('ffmpeg.exe')), once=True)
        self.assertEqual(video_worker.schema_revision, D1)

        with closing(image_worker._sqlite(self.database)) as db:
            self.assertEqual(image_worker.validate_schema(db), D1)
            self.assertEqual([item['asset_id'] for item in image_worker.matching_candidates(db)],
                             [101])

        with closing(video_embed_worker._connect(self.database)) as db:
            self.assertEqual(video_embed_worker._validate_schema(db), D1)
            candidates, _skipped = video_embed_worker.matching_candidates(db, self.derived)
            self.assertEqual([item['asset_id'] for item in candidates], [102])

        face_worker = _face_worker_without_numpy()
        with closing(face_worker.connect(self.database, readonly=True)) as db:
            self.assertEqual(face_worker.schema(db), D1)
            self.assertEqual(face_worker.eligible(db)[1], 'face')

        preflight = face_worker.preflight(
            self.database, self.originals, self.derived, self.stop)
        self.assertEqual(preflight['schema_revision'], D1)
        self.assertEqual(preflight['preflight'], 'pass')
        self.assertFalse(preflight['activated'])

        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA query_only=ON')
            approved_face_queue.validate_schema(db)
            candidate = approved_face_queue.select_candidate(db)
            self.assertEqual(candidate['asset_id'], 101)
            self.assertEqual(candidate['library_id'], self.library)

        self.assertEqual(self._snapshot(), before)

    def _executable(self, name):
        path = self.root / name
        path.touch()
        return path


if __name__ == '__main__':
    unittest.main()

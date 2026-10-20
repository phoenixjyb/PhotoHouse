"""Approved worker admission after the additive E7 memory-groups migration."""
from contextlib import closing
import io
import json
from pathlib import Path
import sqlite3
import sys
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import approved_face_queue
import run_approved_cpu_worker as cpu_worker
import run_approved_image_embed_worker as image_worker
import run_approved_video_embed_worker as video_embed_worker
import run_approved_video_worker as video_worker_module
import test_approved_workers_d1_compatibility as d1_compatibility
import build_approved_worker_package as worker_package
import qualify_approved_workers_windows as windows_qualification


E7 = 'e7c1a9d5b304'
class ApprovedWorkersE7CompatibilityTests(unittest.TestCase):
    """Reuse the D1 worker fixture, then apply the actual E7 migration."""

    schema_revision = E7

    def setUp(self):
        self.worker_fixture = d1_compatibility.ApprovedWorkersD1CompatibilityTests()
        self.worker_fixture.setUp()
        self.addCleanup(self.worker_fixture.doCleanups)
        self.worker_fixture.fixture.migration.upgrade(self.schema_revision)

    def test_all_approved_worker_preflights_and_face_queue_accept_selected_revision(self):
        revision = self.schema_revision
        fixture = self.worker_fixture
        with closing(sqlite3.connect(fixture.database)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchone()[0], revision)
            groups = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertTrue({'access_memory_groups', 'access_memory_group_revisions'} <= groups)

        before = fixture._snapshot()
        cpu = cpu_worker.preflight(fixture.database, fixture.originals, fixture.derived, fixture.stop)
        self.assertEqual((cpu['preflight'], cpu['schema_revision']), ('pass', revision))
        self.assertEqual(cpu['approved_claimable'], 1)

        image = image_worker.preflight(
            fixture.database, fixture.originals, fixture.derived, fixture.checkpoint,
            fixture.checkpoint_sha256, 'clip-synthetic', 'synthetic-v1', 'cpu')
        self.assertEqual((image['preflight'], image['schema_revision']), ('pass', revision))
        self.assertEqual(image['approved_claimable'], 1)

        video_embed = video_embed_worker.preflight(
            fixture.database, fixture.originals, fixture.derived, fixture.checkpoint,
            fixture.checkpoint_sha256, 'clip-synthetic', 'synthetic-v1', 'cpu')
        self.assertEqual((video_embed['preflight'], video_embed['schema_revision']), ('pass', revision))
        self.assertEqual(video_embed['approved_claimable'], 1)

        face_worker = d1_compatibility._face_worker_without_numpy()
        face = face_worker.preflight(fixture.database, fixture.originals, fixture.derived, fixture.stop)
        self.assertEqual((face['preflight'], face['schema_revision']), ('pass', revision))
        self.assertFalse(face['activated'])

        # The video worker constructor validates the schema through its
        # read-only startup gate; it does not launch ffmpeg or process media.
        video = video_worker_module.ApprovedVideoWorker(
            fixture.database, fixture.derived, (fixture.originals,),
            ffprobe=str(fixture._executable('ffprobe-e7.exe')),
            ffmpeg=str(fixture._executable('ffmpeg-e7.exe')), once=True)
        self.assertEqual(video.schema_revision, revision)

        with closing(sqlite3.connect(fixture.database)) as db:
            db.execute('PRAGMA query_only=ON')
            approved_face_queue.validate_schema(db)
            selected = approved_face_queue.select_candidate(db)
            self.assertEqual(selected['asset_id'], 101)
            self.assertEqual(selected['library_id'], fixture.library)

        # Existing claims still resolve only approved media. The additive revision
        # tables do not alter worker query results or schema during preflight.
        with closing(cpu_worker.connect(fixture.database)) as db:
            self.assertEqual([row[0] for row in cpu_worker.matching_candidates(db)], [1])
        with closing(image_worker._sqlite(fixture.database)) as db:
            self.assertEqual([item['asset_id'] for item in image_worker.matching_candidates(db)],
                             [101])
        with closing(video_embed_worker._connect(fixture.database)) as db:
            candidates, _skipped = video_embed_worker.matching_candidates(db, fixture.derived)
            self.assertEqual([item['asset_id'] for item in candidates], [102])
        self.assertEqual(fixture._snapshot(), before)
        self.assertIn(revision, worker_package.TARGET_SCHEMA_REVISIONS)
        self.assertIn(revision, windows_qualification.SUPPORTED_SCHEMA_REVISIONS)
        package_files = {name: b'synthetic worker source' for name in worker_package.FILES}
        with zipfile.ZipFile(io.BytesIO(worker_package.package_bytes(
                'a' * 40, package_files, schema_revision=revision))) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual(manifest['schema_revision'], revision)
            self.assertFalse(manifest['activated'])


if __name__ == '__main__':
    unittest.main()

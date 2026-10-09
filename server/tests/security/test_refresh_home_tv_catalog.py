"""Synthetic TV catalog refresh; no live service, Windows data or originals copy."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts')]

from fastapi.testclient import TestClient
from app.home_catalog import Configuration, CHUNK_BYTES
from app.home_originals import SourceIndex, create_home_originals
from app.photo_delivery import PhotoCache
from refresh_home_tv_catalog import refresh


def sha(data):
    return hashlib.sha256(data).hexdigest()


class RefreshTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='refresh-tv-catalog-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.sources = self.root / 'originals'
        self.sources.mkdir()
        self.photo_bytes = (ROOT / 'tests/security/fixtures/home-8x8.jpg').read_bytes()
        self.old_photo = self.sources / 'old.jpg'
        self.old_photo.write_bytes(self.photo_bytes)
        self.new_photo = self.sources / 'approved-new.jpg'
        self.new_photo.write_bytes(self.photo_bytes)
        self.video_bytes = (ROOT / 'tests/security/fixtures/home-video.mp4').read_bytes()
        self.video = self.sources / 'old.mp4'
        self.video.write_bytes(self.video_bytes)
        self.database = self.root / 'assets.sqlite'
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.execute('CREATE TABLE assets(id INTEGER,mime TEXT,width INTEGER,height INTEGER,status TEXT,path TEXT)')
            conn.executemany('INSERT INTO assets VALUES(?,?,?,?,?,?)', [
                (201, 'image/jpeg', 8, 8, 'active', str(self.old_photo)),
                (202, 'video/mp4', 320, 180, 'active', str(self.video)),
                # Represents a newly approved upload after intake registered it in assets.
                (203, 'image/jpeg', 8, 8, 'active', str(self.new_photo)),
            ])
        self.previous = self.root / 'previous'
        self.media = self.previous / 'prepared'
        for variant in ('grid', 'display', 'video'):
            (self.media / variant).mkdir(parents=True)
        self.old_photo_meta = {'state': 'ready', 'width': 8, 'height': 8,
                               'bytes': len(self.photo_bytes), 'sha256': sha(self.photo_bytes)}
        for variant in ('grid', 'display'):
            (self.media / variant / '201.jpg').write_bytes(self.photo_bytes)
        (self.media / 'video' / '202.mp4').write_bytes(self.video_bytes)
        chunks = json.dumps([sha(self.video_bytes[i:i + CHUNK_BYTES])
                             for i in range(0, len(self.video_bytes), CHUNK_BYTES)]).encode()
        (self.media / 'video' / '202.chunks.json').write_bytes(chunks)
        missing = {'state': 'unavailable', 'reason': 'not_prepared'}
        self.old_catalog = {'version': 2, 'revision': 7, 'library_id': 'home-library',
            'title': 'PhotoHouse', 'assets': [
                {'id': 202, 'kind': 'video', 'label': 'Asset 202', 'width': 320, 'height': 180,
                 'previews': {'grid': dict(missing), 'display': dict(missing)},
                 'video': {'state': 'ready', 'mime': 'video/mp4', 'video_codec': 'h264',
                     'audio_codec': 'aac', 'width': 320, 'height': 180, 'duration_ms': 500,
                     'bytes': len(self.video_bytes), 'sha256': sha(self.video_bytes),
                     'chunks_sha256': sha(chunks)}},
                {'id': 201, 'kind': 'photo', 'label': 'Asset 201', 'width': 8, 'height': 8,
                 'previews': {'grid': dict(self.old_photo_meta), 'display': dict(self.old_photo_meta)},
                 'video': None}]}
        self.write_old_publication()

    def write_old_publication(self):
        raw = json.dumps(self.old_catalog, separators=(',', ':')).encode()
        (self.previous / 'catalog.json').write_bytes(raw)
        (self.previous / 'control.json').write_text(json.dumps({
            'version': 2, 'enabled': True, 'revision': 7, 'catalog_sha256': sha(raw)}))

    def snapshot_previous(self):
        return {p.relative_to(self.previous).as_posix(): sha(p.read_bytes())
                for p in self.previous.rglob('*') if p.is_file()}

    def candidate(self, name='candidate'):
        return refresh(self.database, self.previous, self.root / name, 8, (self.sources,))

    def test_new_approved_photo_is_on_demand_and_old_ready_media_is_reused(self):
        previous_before = self.snapshot_previous()
        result = self.candidate()
        self.assertFalse((self.root / 'candidate' / 'INCOMPLETE').exists())
        self.assertEqual(result['media_root'], str(self.media))
        self.assertEqual(result['assets'], 3)
        publication = Path(result['publication'])
        catalog = json.loads((publication / 'catalog.json').read_text())
        by_id = {asset['id']: asset for asset in catalog['assets']}
        self.assertEqual(by_id[201]['previews']['display'], self.old_photo_meta)
        self.assertEqual(by_id[202]['video']['sha256'], sha(self.video_bytes))
        self.assertEqual(json.loads((publication / 'control.json').read_text())['enabled'], False)
        self.assertEqual(self.snapshot_previous(), previous_before)

        config = Configuration(publication / 'control.json', self.media,
                               'https://home.photohouse.test:18444', ('192.168.40.0/24',))
        index = Path(result['source_index'])
        sources = SourceIndex(__import__('app.home_catalog', fromlist=['Publication']).Publication(config),
            index, result['source_index_sha256'], (self.sources,), originals_allowed=False)
        cache = PhotoCache(self.root / 'cache', guard_factory=lambda _root: lambda *a, **kw: None)
        app = create_home_originals(config, sources, cache)
        client = TestClient(app, base_url=config.origin, client=('192.168.40.20', 1))
        self.addCleanup(client.close)
        # The fixture publication is disabled; enable only the synthetic candidate in memory.
        control = json.loads((publication / 'control.json').read_text())
        control['enabled'] = True
        (publication / 'control.json').write_text(json.dumps(control))
        feed = client.get('/home/v3/catalog').json()
        self.assertEqual(feed['total'], 3)
        new = next(asset for asset in feed['items'] if asset['id'] == 203)
        self.assertEqual(new['previews']['grid']['state'], 'on_demand')
        self.assertIsNone(new['original'])
        preview = client.get(new['previews']['grid']['url'])
        self.assertEqual(preview.status_code, 200, preview.text[:100])
        self.assertEqual(self.new_photo.read_bytes(), self.photo_bytes)
        old = next(asset for asset in feed['items'] if asset['id'] == 201)
        self.assertEqual(old['previews']['grid']['state'], 'ready')
        self.assertEqual(client.get(old['previews']['grid']['url']).content, self.photo_bytes)
        retained_video = client.get('/home/v3/assets/202/video?revision=8',
                                    headers={'Range': 'bytes=0-7'})
        self.assertEqual(retained_video.status_code, 206)
        self.assertEqual(retained_video.content, self.video_bytes[:8])

    def test_tampered_old_ready_media_is_rejected_and_candidate_stays_incomplete(self):
        previous_before = self.snapshot_previous()
        (self.media / 'grid' / '201.jpg').write_bytes(self.photo_bytes + b'tampered')
        previous_before = self.snapshot_previous()
        with self.assertRaises(ValueError):
            self.candidate('bad-candidate')
        self.assertTrue((self.root / 'bad-candidate' / 'INCOMPLETE').is_file())
        self.assertEqual(self.snapshot_previous(), previous_before)
        control = json.loads((self.root / 'bad-candidate/publication/control.json').read_text())
        self.assertFalse(control['enabled'])

    def test_removed_or_changed_old_catalog_scope_is_rejected(self):
        with closing(sqlite3.connect(self.database)) as conn, conn:
            conn.execute('UPDATE assets SET width=9 WHERE id=201')
        with self.assertRaises(ValueError):
            self.candidate('scope-drift')
        self.assertTrue((self.root / 'scope-drift' / 'INCOMPLETE').is_file())


if __name__ == '__main__':
    unittest.main()

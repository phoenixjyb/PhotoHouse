"""Default-off protected moment lookup over one generated interval fixture."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests' / 'security'))

from fastapi.testclient import TestClient
from PIL import Image
from app.access.media import MediaRuntime
from app.access.prepared_video import PreparedVideos, pin
from app.access.video_moments import VideoMoment, VideoMomentCatalog
from app.home_catalog import CHUNK_BYTES
from app.gps_utils import probe_video_metadata
from app.main import create_app
import test_closed_application as closed


BASE = '/libraries/family-a/video-moments/v1/search'


def _generated_video(path, preset='ultrafast'):
    """Produce red, green, and blue one-second scenes with known boundaries."""
    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise unittest.SkipTest('FFmpeg and FFprobe required for generated video')
    command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
        '-f', 'lavfi', '-i', 'color=c=red:s=64x48:r=10:d=1',
        '-f', 'lavfi', '-i', 'color=c=green:s=64x48:r=10:d=1',
        '-f', 'lavfi', '-i', 'color=c=blue:s=64x48:r=10:d=1',
        '-filter_complex', '[0:v][1:v][2:v]concat=n=3:v=1:a=0,format=yuv420p[v]',
        '-map', '[v]', '-an', '-c:v', 'libx264', '-preset', preset,
        '-movflags', '+faststart', str(path)]
    subprocess.run(command, check=True, timeout=20, capture_output=True)
    frame = path.with_name('green-midpoint.png')
    subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                    '-ss', '1.5', '-i', str(path), '-frames:v', '1', str(frame)],
                   check=True, timeout=10, capture_output=True)
    with Image.open(frame) as image:
        midpoint = image.convert('RGB').getpixel((image.width // 2, image.height // 2))
    return probe_video_metadata(path, timeout_sec=10, strict=True), midpoint


def _prepared_entry(asset_id, source, directory, video, probe):
    folder = directory / f'asset-{asset_id}'
    folder.mkdir(exist_ok=True)
    (folder / 'video.mp4').write_bytes(video)
    hashes = [hashlib.sha256(video[index:index + CHUNK_BYTES]).hexdigest()
              for index in range(0, len(video), CHUNK_BYTES)]
    chunks = json.dumps(hashes, separators=(',', ':')).encode()
    (folder / 'video.chunks.json').write_bytes(chunks)
    info = source.stat()
    return {
        'id': asset_id,
        'source_identity': list(pin(info)),
        'directory': f'asset-{asset_id}',
        'video': {
            'state': 'ready', 'mime': 'video/mp4', 'video_codec': 'h264',
            'audio_codec': None, 'width': int(probe['width']),
            'height': int(probe['height']),
            'duration_ms': int(round(probe['duration_sec'] * 1000)),
            'bytes': len(video), 'sha256': hashlib.sha256(video).hexdigest(),
            'chunks_sha256': hashlib.sha256(chunks).hexdigest(),
        },
    }


class VideoMomentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        closed.ClosedApplicationTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        closed.ClosedApplicationTests.tearDownClass()

    def setUp(self):
        self.generated = tempfile.TemporaryDirectory(prefix='photohouse-moment-')
        self.addCleanup(self.generated.cleanup)
        generated_path = Path(self.generated.name) / 'three-scenes.mp4'
        self.probe, self.green_midpoint = _generated_video(generated_path)
        self.alternate_path = Path(self.generated.name) / 'three-scenes-reencoded.mp4'
        self.alternate_probe, _ = _generated_video(self.alternate_path, preset='medium')

        self.e = closed.ClosedApplicationTests()
        self.e.setUp()
        self.addCleanup(self.e.doCleanups)
        self.e.mutate('UPDATE access_memberships SET originals=0 WHERE account_id=?',
                      (self.e.member_id,))
        self.source = self.e.originals / '101.mp4'
        shutil.copyfile(generated_path, self.source)
        self.foreign_source = self.e.originals / '201.mp4'
        shutil.copyfile(generated_path, self.foreign_source)
        self.e.mutate('UPDATE assets SET path=? WHERE id=101', (str(self.source),))
        self.e.mutate('UPDATE assets SET path=? WHERE id=201', (str(self.foreign_source),))

        self.prepared_root = self.e.root / 'prepared-videos'
        self.prepared_root.mkdir()
        self.index = self.e.root / 'prepared-index.json'
        duration_ms = int(round(self.probe['duration_sec'] * 1000))
        video_bytes = generated_path.read_bytes()
        prepared_entries = []
        for asset_id, source in ((101, self.source), (201, self.foreign_source)):
            prepared_entries.append(_prepared_entry(asset_id, source,
                self.prepared_root, video_bytes, self.probe))
        self.video_bytes = video_bytes
        self.prepared_entries = prepared_entries
        index_bytes = json.dumps({'version': 1, 'assets': prepared_entries},
                                 separators=(',', ':')).encode()
        self.index.write_bytes(index_bytes)
        self.prepared = PreparedVideos(self.index,
            hashlib.sha256(index_bytes).hexdigest(), self.prepared_root)

        self.catalog = VideoMomentCatalog((
            VideoMoment(101, 'green scene', 1.0, 2.0,
                        pin(self.source.stat()), duration_ms,
                        hashlib.sha256(video_bytes).hexdigest()),
            # This row is real catalog input but belongs to family-b and must
            # not appear for an authorized family-a caller.
            VideoMoment(201, 'blue scene', 2.0, 3.0,
                        pin(self.foreign_source.stat()), duration_ms,
                        hashlib.sha256(video_bytes).hexdigest()),
        ))
        self.app = create_app(access_runtime=self.e.access,
            media_runtime=MediaRuntime((self.e.originals,), self.e.derived,
                                       prepared_videos=self.prepared),
            video_moment_catalog=self.catalog)
        self.e.client.close()
        self.e.client = TestClient(self.app, base_url='https://photohouse.test',
                                   client=('192.0.2.10', 23456))
        self.e.client.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(self.e.client.close)

    def post(self, query, *, library='family-a', token=None):
        return self.e.client.post(
            f'/libraries/{library}/video-moments/v1/search',
            headers=self.e.headers(token), json={'query': query})

    def test_generated_known_interval_returns_only_protected_playback_reference(self):
        self.assertAlmostEqual(self.probe['duration_sec'], 3.0, delta=0.1)
        red, green, blue = self.green_midpoint
        self.assertGreater(green, red * 1.4)
        self.assertGreater(green, blue * 1.4)
        response = self.post('green')
        self.e.assert_private(response)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'version': 1, 'results': [
            {'asset_id': '101', 'label': 'green scene', 'start_sec': 1.0,
             'end_sec': 2.0,
             'playback_revision': hashlib.sha256(self.video_bytes).hexdigest()}]})
        self.assertNotIn(str(self.e.root), response.text)
        self.assertNotIn('embedding', response.text)

        playback = self.e.client.head('/assets/101/playback?library=family-a',
                                      headers=self.e.headers())
        self.assertEqual(playback.status_code, 200)
        self.assertEqual(playback.headers['content-type'], 'video/mp4')
        revision = response.json()['results'][0]['playback_revision']
        pinned_url = '/assets/101/playback?library=family-a&playback_revision=' + revision
        pinned_head = self.e.client.head(pinned_url, headers=self.e.headers())
        self.assertEqual(pinned_head.status_code, 200)
        pinned_get = self.e.client.get(pinned_url, headers=self.e.headers())
        self.assertEqual(pinned_get.status_code, 200)
        self.assertEqual(pinned_get.content, self.video_bytes)
        self.assertEqual(self.e.client.get('/assets/101/media?library=family-a',
                                           headers=self.e.headers()).status_code, 401)

    def test_capabilities_are_library_authenticated_and_read_only(self):
        capabilities = self.e.client.get(
            '/libraries/family-a/video-moments/v1/capabilities',
            headers=self.e.headers())
        self.assertEqual(capabilities.status_code, 200)
        self.assertEqual(capabilities.json(), {
            'version': 1, 'enabled': True,
            'search': {'max_moments': 32, 'playback_revision': 'sha256'}})
        self.assertEqual(self.e.client.get(
            '/libraries/family-b/video-moments/v1/capabilities',
            headers=self.e.headers()).status_code, 401)

    def test_empty_is_distinct_from_disabled_and_legacy_routes_stay_closed(self):
        empty = self.post('no matching label')
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json(), {'version': 1, 'results': []})
        self.assertEqual(self.post('blue').json(), {'version': 1, 'results': []})

        disabled = create_app(access_runtime=self.e.access,
            media_runtime=MediaRuntime((self.e.originals,), self.e.derived,
                                       prepared_videos=self.prepared))
        client = TestClient(disabled, base_url='https://photohouse.test',
                            client=('192.0.2.10', 23456))
        try:
            denied = client.post(BASE, headers=self.e.headers(), json={'query': 'green'})
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(client.get(
                '/libraries/family-a/video-moments/v1/capabilities',
                headers=self.e.headers()).status_code, 403)
            self.assertEqual(client.post('/search/video-segments', headers=self.e.headers(),
                                         json={'text': 'green'}).status_code, 403)
        finally:
            client.close()

    def test_revoked_and_outside_library_requests_are_denied(self):
        outside = self.post('green', library='family-b', token=self.e.member_token)
        self.assertEqual(outside.status_code, 401)
        self.e.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                      (self.e.member_id,))
        with patch.object(self.prepared, 'open', side_effect=AssertionError(
                'Prepared lookup before current library authorization')):
            revoked = self.post('green')
        self.assertEqual(revoked.status_code, 401)

    def test_invalid_interval_and_stale_source_fail_closed(self):
        duration_ms = int(round(self.probe['duration_sec'] * 1000))
        with self.assertRaises(ValueError):
            VideoMoment(101, 'outside duration', 2.8, 3.2,
                        pin(self.source.stat()), duration_ms,
                        hashlib.sha256(self.video_bytes).hexdigest())

        self.source.write_bytes(self.source.read_bytes() + b'changed')
        changed = self.post('green')
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(changed.json(), {'detail': 'Video moments changed'})

    def test_stale_revision_cannot_open_reprepared_bytes(self):
        old_revision = hashlib.sha256(self.video_bytes).hexdigest()
        next_video = self.alternate_path.read_bytes()
        next_entry = _prepared_entry(101, self.source, self.prepared_root,
                                     next_video, self.alternate_probe)
        other_entry = _prepared_entry(201, self.foreign_source, self.prepared_root,
                                      self.video_bytes, self.probe)
        updated_index = json.dumps({'version': 1, 'assets': [next_entry, other_entry]},
                                   separators=(',', ':')).encode()
        next_index_path = self.e.root / 'prepared-index-next.json'
        next_index_path.write_bytes(updated_index)
        next_provider = PreparedVideos(next_index_path,
            hashlib.sha256(updated_index).hexdigest(), self.prepared_root)
        new_revision = next_provider.entries[101]['video']['sha256']
        self.assertNotEqual(new_revision, old_revision)
        self.app.state.media_runtime = MediaRuntime(
            (self.e.originals,), self.e.derived, prepared_videos=next_provider)

        url = ('/assets/101/playback?library=family-a&playback_revision='
               + old_revision)
        with patch.object(next_provider, 'open', side_effect=AssertionError(
                'Mismatched prepared revision must reject before reader open')):
            stale = self.e.client.head(url, headers=self.e.headers())
        self.assertEqual(stale.status_code, 409)
        current = self.e.client.head('/assets/101/playback?library=family-a',
                                     headers=self.e.headers())
        self.assertEqual(current.status_code, 200, current.text)

    def test_catalog_requires_explicit_prepared_playback_wiring(self):
        with self.assertRaisesRegex(ValueError, 'prepared playback runtime'):
            create_app(access_runtime=self.e.access,
                       media_runtime=MediaRuntime((self.e.originals,), self.e.derived),
                       video_moment_catalog=self.catalog)


if __name__ == '__main__':
    unittest.main()

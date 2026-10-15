"""Explicit QuickTime capture-date handling on synthetic data only."""
from contextlib import closing
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import shutil
import subprocess
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests' / 'security'))

# Legacy worker imports require an operator caption prompt, intentionally absent
# from the public source. Supply fictional prompt text only for this import;
# these tests never instantiate caption/model services.
_read_text = Path.read_text
_prompt = ROOT / 'config' / 'detailed-caption-prompt.txt'
def _fixture_read_text(path, *args, **kwargs):
    if path == _prompt:
        return 'Describe the visible fictional fixture.'
    return _read_text(path, *args, **kwargs)
with tempfile.TemporaryDirectory(prefix='photohouse-video-import-') as _derived:
    with patch.dict(os.environ, {'PHOTOHOUSE_NO_DOTENV': '1', 'DERIVED_PATH': _derived}), \
            patch.object(Path, 'read_text', _fixture_read_text):
        from app import ingest, tasks
from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider
from app.access.service import AccessService
from app.gps_utils import parse_ffprobe_creationdate, probe_video_metadata
from phone_discovery_fixture import TOKEN, create, reviewed


def quicktime_info(*values, stream_values=(), generic=None):
    tags = {'com.apple.quicktime.creationdate': value for value in values}
    stream_tags = {'com.apple.quicktime.creationdate': value for value in stream_values}
    if generic is not None:
        tags['creation_time'] = generic
    return {
        'format': {'format_name': 'mov,mp4,m4a,3gp,3g2,mj2', 'tags': tags},
        'streams': [{'codec_type': 'video', 'width': 640, 'height': 480,
                     'duration': '2', 'r_frame_rate': '30/1', 'tags': stream_tags}],
    }


class QuickTimeCreationDateTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'optional local FFmpeg tools')
    def test_generated_video_roundtrips_explicit_capture_tag_through_real_probe(self):
        with tempfile.TemporaryDirectory() as root:
            video = Path(root) / 'fictional.mp4'
            subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=blue:s=32x32:r=10:d=0.2', '-c:v', 'mpeg4',
                            '-movflags', 'use_metadata_tags', '-metadata',
                            'com.apple.quicktime.creationdate=2025-04-03T00:15:16+08:00',
                            str(video)], check=True, capture_output=True, timeout=20)
            actual = probe_video_metadata(video, strict=True)
            self.assertEqual(actual['taken_at'], datetime(2025, 4, 3, 0, 15, 16))
            self.assertEqual(actual['taken_at_offset_minutes'], 480)

    def test_parser_accepts_valid_explicit_values_without_timezone_conversion(self):
        cases = (
            ('2025-04-03T14:15:16Z', datetime(2025, 4, 3, 14, 15, 16), 0),
            ('2025-04-03T14:15:16.12+08:00', datetime(2025, 4, 3, 14, 15, 16, 120000), 480),
            ('2025-04-03T14:15:16.123456-0230', datetime(2025, 4, 3, 14, 15, 16, 123456), -150),
            ('2025-04-03T14:15:16+1400', datetime(2025, 4, 3, 14, 15, 16), 840),
        )
        for raw, expected, offset in cases:
            with self.subTest(raw=raw):
                self.assertEqual(parse_ffprobe_creationdate(quicktime_info(raw)),
                                 (expected, 'embedded_quicktime_creationdate', offset))

    def test_parser_rejects_untrusted_missing_malformed_and_conflicting_values(self):
        bad_values = (
            '2025-04-03', '2025-04-03T14:15:16', '2025-02-30T14:15:16Z',
            '2025-04-03T14:15:16+1401', '2025-04-03T14:15:16+0860',
            '2025-04-03T14:15:16.1234567Z', ' 2025-04-03T14:15:16Z',
            '2025-04-03T14:15:16Z\n', 'x' * 65,
        )
        for raw in bad_values:
            with self.subTest(raw=raw):
                self.assertEqual(parse_ffprobe_creationdate(quicktime_info(raw)), (None, None, None))
        self.assertEqual(parse_ffprobe_creationdate(quicktime_info(generic='2025-04-03T14:15:16Z')),
                         (None, None, None))
        self.assertEqual(parse_ffprobe_creationdate({'format': {'tags': {}}, 'streams': []}),
                         (None, None, None))
        self.assertEqual(parse_ffprobe_creationdate({'format': {'tags': {}}, 'streams': None}),
                         (None, None, None))
        self.assertEqual(parse_ffprobe_creationdate(
            quicktime_info('2025-04-03T14:15:16Z', stream_values=('2025-04-03T14:15:16+01:00',))),
            (None, None, None))
        self.assertEqual(parse_ffprobe_creationdate(
            quicktime_info('2025-04-03T14:15:16Z', stream_values=('2025-04-03T14:15:16Z',))),
            (datetime(2025, 4, 3, 14, 15, 16), 'embedded_quicktime_creationdate', 0))

    def test_probe_returns_capture_date_diagnostics_and_nulls(self):
        with patch('app.gps_utils._bounded_ffprobe', return_value=quicktime_info(
                '2025-04-03T14:15:16+08:00')):
            captured = probe_video_metadata('synthetic.mp4')
        self.assertEqual(captured['taken_at'], datetime(2025, 4, 3, 14, 15, 16))
        self.assertEqual(captured['taken_at_source'], 'embedded_quicktime_creationdate')
        self.assertEqual(captured['taken_at_offset_minutes'], 480)
        with patch('app.gps_utils._bounded_ffprobe', return_value=quicktime_info(
                generic='2025-04-03T14:15:16Z')):
            unknown = probe_video_metadata('synthetic.mp4')
        self.assertIsNone(unknown['taken_at'])
        self.assertIsNone(unknown['taken_at_source'])
        self.assertIsNone(unknown['taken_at_offset_minutes'])

    def test_ingest_adds_only_valid_capture_timestamp_to_existing_asset_field(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / 'synthetic.mp4'
            source.write_bytes(b'synthetic fixture bytes')
            session = _IngestSession()
            metadata = {'taken_at': datetime(2025, 4, 3, 14, 15, 16),
                        'duration_sec': 2.0, 'fps': 30.0, 'gps_lat': None, 'gps_lon': None}
            settings = SimpleNamespace(video_enabled=True, video_extensions='.mp4',
                                       video_scene_detect=False, image_tag_auto_enqueue=False)
            with patch.object(ingest, 'get_settings', return_value=settings), \
                    patch.object(ingest, 'probe_video_metadata', return_value=metadata):
                ingest.ingest_paths(session, [str(source)])
            self.assertEqual(session.assets[0].taken_at, metadata['taken_at'])
            self.assertFalse(hasattr(session.assets[0], 'taken_at_source'))

            source = Path(root) / 'unknown.mp4'
            source.write_bytes(b'synthetic fixture bytes 2')
            session = _IngestSession()
            metadata['taken_at'] = None
            with patch.object(ingest, 'get_settings', return_value=settings), \
                    patch.object(ingest, 'probe_video_metadata', return_value=metadata):
                ingest.ingest_paths(session, [str(source)])
            self.assertIsNone(session.assets[0].taken_at)

    def test_worker_fills_unknown_only_and_keeps_existing_date(self):
        with tempfile.TemporaryDirectory() as root:
            metadata = {'duration_sec': 2.0, 'fps': 30.0, 'width': 640, 'height': 480,
                        'gps_lat': None, 'gps_lon': None,
                        'taken_at': datetime(2025, 4, 3, 14, 15, 16)}
            for existing, expected in ((None, metadata['taken_at']),
                                       (datetime(2024, 1, 2), datetime(2024, 1, 2))):
                asset = SimpleNamespace(id=7, path='synthetic.mp4', mime='video/mp4',
                                        duration_sec=None, fps=None, width=None, height=None,
                                        gps_lat=None, gps_lon=None, taken_at=existing)
                session = _TaskSession(asset)
                executor = object.__new__(tasks.TaskExecutor)
                executor.settings = SimpleNamespace()
                task = SimpleNamespace(payload_json={'asset_id': 7})
                with patch.object(tasks, 'DERIVED_DIR', Path(root)), \
                        patch.object(tasks, 'probe_video_metadata', return_value=metadata):
                    executor._handle_video_probe(session, task)
                self.assertEqual(asset.taken_at, expected)
                self.assertFalse(hasattr(asset, 'taken_at_source'))
            asset = SimpleNamespace(id=7, path='synthetic.mp4', mime='video/mp4',
                                    duration_sec=None, fps=None, width=None, height=None,
                                    gps_lat=None, gps_lon=None, taken_at=None)
            session = _TaskSession(asset)
            executor = object.__new__(tasks.TaskExecutor)
            executor.settings = SimpleNamespace()
            with patch.object(tasks, 'DERIVED_DIR', Path(root)), \
                    patch.object(tasks, 'probe_video_metadata', return_value=dict(metadata, taken_at=None)):
                executor._handle_video_probe(session, SimpleNamespace(payload_json={'asset_id': 7}))
            self.assertIsNone(asset.taken_at)

    def test_synthetic_captured_video_is_date_searchable_unknown_video_is_not(self):
        with tempfile.TemporaryDirectory() as root:
            database = Path(root) / 'synthetic.sqlite'
            with closing(sqlite3.connect(database)) as db:
                create(db)
                db.execute("INSERT INTO assets VALUES(104,'fixture','active','video/mp4',8,8,NULL,'2025-04-03T14:15:16')")
                db.execute("INSERT INTO assets VALUES(105,'fixture','active','video/mp4',8,8,NULL,NULL)")
                db.executemany('INSERT INTO access_asset_libraries VALUES(?,?)',
                               [(104, 'family-a'), (105, 'family-a')])
                db.commit()
                index = reviewed(AccessService(db, clock=lambda: 2_000_000_000))
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('PRAGMA foreign_keys=ON')
                access = AccessService(connection, clock=lambda: 2_000_000_000)
                service = d.DiscoveryReads(access, MemoryIndexProvider((index,)), d.ReadBudget())
                state = service.facets(TOKEN, 'family-a')
                result = service.search(TOKEN, 'family-a', binding=state['binding'],
                                        filters={'date': {'from': '2025-04-03', 'to': '2025-04-03'}})
                self.assertEqual([item['id'] for item in result['items']], ['104'])


class _Query:
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return None


class _IngestSession:
    def __init__(self):
        self.assets = []

    def query(self, model):
        return _Query()

    def add(self, value):
        from app.db import Asset
        if isinstance(value, Asset):
            self.assets.append(value)

    def flush(self):
        for index, asset in enumerate(self.assets, 1):
            asset.id = index

    def commit(self):
        pass


class _TaskSession:
    def __init__(self, asset):
        self.asset = asset
        self.added = []

    def get(self, model, asset_id):
        return self.asset if asset_id == self.asset.id else None

    def add(self, value):
        self.added.append(value)

    def commit(self):
        pass


if __name__ == '__main__':
    unittest.main()

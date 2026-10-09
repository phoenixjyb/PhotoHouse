"""Driver contract checks, with fake native processes and local generated data.

These checks do not qualify Windows, ffmpeg or any production worker.
"""
from contextlib import closing
import importlib.util
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'approved_native_canary_schema_fixture', ROOT / 'scripts/qualify_approved_workers_windows.py')
canary = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(canary)


class NativeCanarySchemaTests(unittest.TestCase):
    def fake_native_run(self, revision, complete=True, defect=None):
        calls = []

        def generate(command, **kwargs):
            Path(command[-1]).write_bytes(b'synthetic fake video, never published')
            return SimpleNamespace(returncode=0)

        def worker(script, arguments, timeout):
            database = Path(arguments[arguments.index('--database') + 1])
            derived = Path(arguments[arguments.index('--derived-root') + 1])
            with closing(sqlite3.connect(database)) as db:
                actual_revision = db.execute('SELECT version_num FROM alembic_version').fetchone()[0]
                self.assertEqual(actual_revision, revision)
                kind = ('thumb', 'phash', 'video_probe', 'video_keyframes')[len(calls)]
                calls.append((script, kind, actual_revision))
                db.execute("UPDATE tasks SET state='finished' WHERE type=?", (kind,))
                if kind == 'thumb':
                    for edge in (256, 1024):
                        output = derived / 'thumbnails' / str(edge) / '1.jpg'
                        output.parent.mkdir(parents=True)
                        if defect == 'missing_large' and edge == 1024:
                            continue
                        Image.new('RGB', (12, 8)).save(output)
                        if defect == 'corrupt_thumbnail' and edge == 256:
                            output.write_bytes(b'not an image')
                elif kind == 'phash':
                    db.execute('UPDATE assets SET perceptual_hash=? WHERE id=1',
                               ('invalid' if defect == 'bad_phash' else '8000000000000000',))
                elif kind == 'video_probe':
                    db.execute('UPDATE assets SET duration_sec=2.0,width=?,height=72,fps=5.0 WHERE id=2',
                               (640 if defect == 'bad_metadata' else 128,))
                    canary._task(db, 'video_keyframes', 2, 40)
                elif complete:
                    output = derived / 'video_frames/2/frame_1.jpg'
                    output.parent.mkdir(parents=True)
                    Image.new('RGB', (12, 8)).save(output)
                    if defect == 'corrupt_frame':
                        output.write_bytes(b'not a keyframe')
                    canary._task(db, 'caption', 2, 40)
                    canary._task(db, 'video_embed', 2, 40)
                db.commit()

        with tempfile.TemporaryDirectory() as directory:
            ffmpeg = Path(directory) / 'fake-ffmpeg'
            ffprobe = Path(directory) / 'fake-ffprobe'
            ffmpeg.touch(); ffprobe.touch()
            # Replace this module's sys reference, not global sys.platform:
            # pathlib must continue using the actual local platform.
            with (patch.object(canary, 'sys', SimpleNamespace(platform='win32')),
                  patch.object(canary.subprocess, 'run', side_effect=generate),
                  patch.object(canary, '_worker_once', side_effect=worker)):
                result = canary.run(ffmpeg, ffprobe, revision)
        return result, calls

    def test_selected_revision_reaches_all_lanes_and_success_receipt(self):
        for revision in canary.SUPPORTED_SCHEMA_REVISIONS:
            with self.subTest(revision=revision):
                result, calls = self.fake_native_run(revision)
                self.assertEqual(result['schema_revision'], revision)
                self.assertEqual([kind for _, kind, _ in calls],
                                 ['thumb', 'phash', 'video_probe', 'video_keyframes'])
                self.assertFalse(result['production_database_opened'])
                self.assertFalse(result['family_media_opened'])
                self.assertEqual(set(result['decoded_thumbnails']), {'256', '1024'})
                self.assertEqual(result['decoded_keyframes'], 1)
                self.assertTrue(result['synthetic_video_metadata_verified'])

    def test_finished_rows_without_derivative_and_chained_jobs_are_not_a_pass(self):
        with self.assertRaisesRegex(RuntimeError, 'Synthetic derivative or queue verification failed'):
            self.fake_native_run('b1d7e4a9c230', complete=False)

    def test_finished_tasks_cannot_hide_corrupt_or_missing_outputs_and_wrong_metadata(self):
        failures = {'missing_large': 'synthetic_jpeg_decode_failed',
                    'corrupt_thumbnail': 'synthetic_jpeg_decode_failed',
                    'corrupt_frame': 'synthetic_jpeg_decode_failed',
                    'bad_phash': 'Synthetic derivative or queue verification failed',
                    'bad_metadata': 'synthetic_video_metadata_failed'}
        for defect, reason in failures.items():
            with self.subTest(defect=defect), self.assertRaisesRegex(RuntimeError, reason):
                self.fake_native_run('b1d7e4a9c230', defect=defect)

    def test_jpeg_validation_refuses_wrong_format_oversize_dimensions_and_links(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for kind in ('png', 'too_wide', 'linked', 'empty'):
                with self.subTest(kind=kind):
                    path = root / (kind + '.jpg')
                    if kind == 'linked':
                        target = root / 'target.jpg'; Image.new('RGB', (12, 8)).save(target)
                        path.symlink_to(target)
                    elif kind == 'empty':
                        path.touch()
                    else:
                        Image.new('RGB', (257 if kind == 'too_wide' else 12, 8)).save(
                            path, format='PNG' if kind == 'png' else 'JPEG')
                    with self.assertRaisesRegex(RuntimeError, 'synthetic_jpeg_decode_failed'):
                        canary._jpeg_summary(path, 256)

    def test_unsupported_revision_refuses_before_creating_or_launching_anything(self):
        with (patch.object(canary.tempfile, 'TemporaryDirectory') as temporary,
              patch.object(canary.subprocess, 'run') as process):
            with self.assertRaisesRegex(RuntimeError, 'Unsupported synthetic schema revision'):
                canary.run(Path('unused-ffmpeg'), Path('unused-ffprobe'), 'not-a-schema')
            temporary.assert_not_called(); process.assert_not_called()

    def test_cli_preserves_a0_default_and_accepts_explicit_b1(self):
        for option, expected in (([], 'a0c9d2e4f817'),
                                 (['--schema-revision', 'b1d7e4a9c230'], 'b1d7e4a9c230')):
            with (self.subTest(option=option), patch.object(canary, 'run', return_value={}) as run,
                  patch.object(sys, 'stdout', io.StringIO())):
                self.assertEqual(canary.main(['--ffmpeg', 'fake', '--ffprobe', 'fake', *option]), 0)
                self.assertEqual(run.call_args.args[2], expected)

    def test_native_guard_still_refuses_local_execution(self):
        with (patch.object(canary, 'sys', SimpleNamespace(platform='darwin')),
              patch.object(canary.tempfile, 'TemporaryDirectory') as temporary):
            with self.assertRaisesRegex(RuntimeError, 'Windows native qualification required'):
                canary.run(Path('unused-ffmpeg'), Path('unused-ffprobe'), 'b1d7e4a9c230')
            temporary.assert_not_called()


if __name__ == '__main__':
    unittest.main()

"""Bulk collection staging uses only tiny synthetic prepared outputs."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import io
import os
import sqlite3
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tests/security'))
import test_protected_video_export as fixtures
import stage_protected_video_collection as collection
from app.access.prepared_video import PreparedReader, PreparedVideos
from app.home_catalog import CHUNK_BYTES, identity


class CollectionTests(unittest.TestCase):
    def setUp(self):
        fixtures.ExportTests.setUp(self)
        self.config = self.root / 'server.json'
        self.derived = self.root / 'derived'; self.derived.mkdir()
        cert = self.root / 'cert.pem'; cert.write_text('synthetic')
        key = self.root / 'key.pem'; key.write_text('synthetic')
        self.config.write_text(json.dumps(dict(format_version=1, database=str(self.database),
            web_origin='https://gallery.example.test:8443', original_roots=[str(self.sources)],
            derived_root=str(self.derived), bind_host='127.0.0.1', port=8443,
            tls_certificate=str(cert), tls_private_key=str(key))))
        self.pinned_index = self.root / 'audited-index.json'
        report = fixtures.exporter.export(self.database, self.workspace, self.pinned_index)
        self.index_sha = report['index_sha256']
        self.destination = self.root / 'collection'
        self.output = self.root / 'collection-index.json'

    def run_collection(self, **kwargs):
        args = dict(config_path=self.config, index=self.pinned_index,
            index_sha256=self.index_sha, prepared_root=self.workspace,
            destination=self.destination, output=self.output)
        args.update(kwargs)
        with patch.object(collection.shutil, 'disk_usage',
                return_value=type('Space', (), {'free': 2 * collection.GIB})()):
            return collection.stage(**args)

    def add_second_index_entry(self):
        fixtures.ExportTests.add_second_ready_asset(self)
        self.pinned_index.unlink()
        report = fixtures.exporter.export(self.database, self.workspace, self.pinned_index)
        self.index_sha = report['index_sha256']

    def run_with_late_mutation(self, mutate_target):
        self.add_second_index_entry()
        original = PreparedReader.chunk
        mutated = False
        def mutate(reader, number):
            nonlocal mutated
            block = original(reader, number)
            if reader.path.parent.name == 'asset-102-ijklmnop' and not mutated:
                target = mutate_target()
                target.write_bytes(target.read_bytes() + b'drift')
                mutated = True
            return block
        with patch.object(PreparedReader, 'chunk', autospec=True, side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'Prepared or copied file changed'):
                self.run_collection(write=True)
        self.assertTrue(mutated)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.destination / 'INCOMPLETE').exists())

    def test_plan_is_metadata_only_and_stage_keeps_incomplete_and_plays(self):
        original = self.source.read_bytes()
        plan = self.run_collection()
        self.assertFalse(plan['staged']); self.assertFalse(plan['originals_rehashed'])
        self.assertFalse(self.destination.exists())
        result = self.run_collection(write=True)
        self.assertTrue(result['staged']); self.assertTrue(result['incomplete'])
        self.assertFalse(result['activated']); self.assertFalse(result['originals_rehashed'])
        self.assertTrue((self.destination / 'INCOMPLETE').is_file())
        provider = PreparedVideos(self.output, result['index_sha256'], self.destination)
        reader = provider.open(101, identity(self.source))
        try:
            self.assertEqual(reader.chunk(0), self.raw)
        finally:
            reader.close()
        self.assertEqual(self.source.read_bytes(), original)
        self.assertEqual(json.loads(self.output.read_bytes())['assets'][0]['source_identity'],
                         json.loads(self.pinned_index.read_bytes())['assets'][0]['source_identity'])
        staged = self.destination / 'asset-101-abcdefgh' / 'video.mp4'
        prepared = self.workspace / 'asset-101-abcdefgh' / 'video.mp4'
        self.assertNotEqual((prepared.stat().st_dev, prepared.stat().st_ino),
                            (staged.stat().st_dev, staged.stat().st_ino))

    def test_incomplete_marker_bytes_are_lf_even_with_windows_text_translation(self):
        original_fdopen = collection.os.fdopen

        class WindowsTextWriter:
            def __init__(self, stream):
                self.stream = stream

            def write(self, text):
                return self.stream.write(text.replace('\n', '\r\n').encode('utf-8'))

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.stream, name)

        def windows_fdopen(fd, mode='r', *args, **kwargs):
            if 'w' in mode and 'b' not in mode:
                return WindowsTextWriter(original_fdopen(fd, 'wb'))
            return original_fdopen(fd, mode, *args, **kwargs)

        with patch.object(collection.os, 'fdopen', side_effect=windows_fdopen):
            result = self.run_collection(write=True)
        marker = (self.destination / 'INCOMPLETE').read_bytes()
        self.assertTrue(result['staged'])
        self.assertEqual(marker, b'Private collection staging incomplete; do not activate.\n')
        self.assertEqual(len(marker), 56)
        self.assertEqual(hashlib.sha256(marker).hexdigest(),
                         '43d25262f7f544d5be32f008a882892050087202f8a7f5b66671729c8b78c424')

    def test_prepared_input_under_derived_root_is_allowed(self):
        prepared = self.derived / 'home-library-protected-v12'
        shutil.copytree(self.workspace, prepared)
        result = self.run_collection(prepared_root=prepared, write=True)
        self.assertTrue(result['staged'])
        self.assertTrue((self.destination / 'INCOMPLETE').exists())

    def test_wrong_index_pin_and_corrupt_prepared_source_refuse(self):
        with self.assertRaisesRegex(ValueError, 'Pinned index'):
            self.run_collection(index_sha256='0' * 64)
        video = self.workspace / 'asset-101-abcdefgh' / 'video.mp4'
        video.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            self.run_collection(write=True)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.destination.exists())

    def test_corruption_after_plan_leaves_incomplete_and_no_index(self):
        original = collection._copy_verified
        def corrupt(source, target, expected, hashes, file_seconds, deadline):
            source.write_bytes(b'X' + self.raw[1:])
            return original(source, target, expected, hashes, file_seconds, deadline)
        with patch.object(collection, '_copy_verified', side_effect=corrupt):
            with self.assertRaises(ValueError):
                self.run_collection(write=True)
        self.assertTrue((self.destination / 'INCOMPLETE').exists())
        self.assertFalse(self.output.exists())

    def test_source_metadata_change_during_copy_is_rejected_and_marker_remains(self):
        original = collection._copy_verified
        changed = False
        def mutate(*args, **kwargs):
            nonlocal changed
            value = original(*args, **kwargs)
            if not changed:
                with closing(sqlite3.connect(self.database)) as db:
                    db.execute('UPDATE assets SET width=width+1 WHERE id=101'); db.commit()
                changed = True
            return value
        with patch.object(collection, '_copy_verified', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'Original metadata'):
                self.run_collection(write=True)
        self.assertFalse(self.output.exists())
        self.assertTrue((self.destination / 'INCOMPLETE').exists())

    def test_late_chunk_callback_detects_earlier_prepared_input_drift(self):
        self.run_with_late_mutation(lambda: self.workspace / 'asset-101-abcdefgh' / 'video.mp4')

    def test_late_chunk_callback_detects_earlier_copied_output_drift(self):
        self.run_with_late_mutation(lambda: self.destination / 'asset-101-abcdefgh' / 'video.mp4')

    def test_late_chunk_callback_detects_marker_tamper(self):
        original = PreparedReader.chunk
        changed = False
        def tamper(reader, number):
            nonlocal changed
            block = original(reader, number)
            if not changed:
                (self.destination / 'INCOMPLETE').write_text('changed')
                changed = True
            return block
        with patch.object(PreparedReader, 'chunk', autospec=True, side_effect=tamper):
            with self.assertRaisesRegex(ValueError, 'Incomplete marker changed'):
                self.run_collection(write=True)
        self.assertFalse(self.output.exists())

    def test_late_source_metadata_sweep_detects_input_index_hash_drift(self):
        original = collection._check_metadata
        calls = 0
        def drift(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = original(*args, **kwargs)
            if calls == 2:
                self.pinned_index.write_bytes(self.pinned_index.read_bytes() + b'drift')
            return result
        with patch.object(collection, '_check_metadata', side_effect=drift):
            with self.assertRaisesRegex(ValueError, 'Pinned index changed'):
                self.run_collection(write=True)
        self.assertFalse(self.output.exists())

    def test_late_source_sweep_detects_pending_index_tamper_and_preserves_replacement(self):
        original = collection._check_metadata
        calls = 0
        pending = self.output.with_name(self.output.name + '.pending')
        def drift(*args, **kwargs):
            nonlocal calls
            calls += 1
            result = original(*args, **kwargs)
            if calls == 2:
                pending.write_bytes(b'foreign pending replacement')
            return result
        with patch.object(collection, '_check_metadata', side_effect=drift):
            with self.assertRaises(Exception):
                self.run_collection(write=True)
        self.assertFalse(self.output.exists())
        self.assertEqual(pending.read_bytes(), b'foreign pending replacement')

    def test_stage_never_opens_original_media_and_copies_have_distinct_inode(self):
        original_open = collection.os.open
        original_path_open = Path.open
        original_io_open = io.open
        def reject_original(path):
            try:
                candidate = Path(path)
            except TypeError:
                return
            if candidate == self.source:
                raise AssertionError('original media content read')
        def guard_os(path, *args, **kwargs):
            reject_original(path)
            return original_open(path, *args, **kwargs)
        def guard_path(path, *args, **kwargs):
            reject_original(path)
            return original_path_open(path, *args, **kwargs)
        def guard_io(path, *args, **kwargs):
            reject_original(path)
            return original_io_open(path, *args, **kwargs)
        with patch.object(collection.os, 'open', side_effect=guard_os), \
                patch.object(Path, 'open', guard_path), patch.object(io, 'open', guard_io):
            plan = self.run_collection()
            result = self.run_collection(write=True)
        self.assertFalse(plan['staged'])
        self.assertTrue(result['staged'])
        staged = self.destination / 'asset-101-abcdefgh' / 'video.mp4'
        prepared = self.workspace / 'asset-101-abcdefgh' / 'video.mp4'
        self.assertNotEqual((prepared.stat().st_dev, prepared.stat().st_ino),
                            (staged.stat().st_dev, staged.stat().st_ino))

    def test_multi_chunk_reader_hashes_every_runtime_chunk(self):
        raw = b'A' * CHUNK_BYTES + b'B' * CHUNK_BYTES + b'Z' * 17
        directory = self.workspace / 'asset-101-abcdefgh'
        result = json.loads((directory / 'receipt.json').read_bytes())['result']
        video = result['video']
        video['bytes'] = len(raw)
        video['sha256'] = hashlib.sha256(raw).hexdigest()
        hashes = [hashlib.sha256(raw[i:i + CHUNK_BYTES]).hexdigest()
                  for i in range(0, len(raw), CHUNK_BYTES)]
        chunk_raw = json.dumps(hashes, separators=(',', ':')).encode()
        video['chunks_sha256'] = hashlib.sha256(chunk_raw).hexdigest()
        (directory / 'video.mp4').write_bytes(raw)
        (directory / 'video.chunks.json').write_bytes(chunk_raw)
        with closing(sqlite3.connect(self.workspace / 'state.sqlite')) as db:
            db.execute('UPDATE items SET result=? WHERE id=101', (json.dumps(result),))
            db.commit()
        receipt_path = directory / 'receipt.json'
        receipt = json.loads(receipt_path.read_bytes()); receipt['result'] = result
        receipt_path.write_text(json.dumps(receipt))
        self.pinned_index.unlink()
        report = fixtures.exporter.export(self.database, self.workspace, self.pinned_index)
        self.index_sha = report['index_sha256']
        calls = []
        original = PreparedReader.chunk
        def track(reader, number):
            calls.append((reader.path.parent.name, number))
            return original(reader, number)
        with patch.object(PreparedReader, 'chunk', autospec=True, side_effect=track):
            staged = self.run_collection(write=True)
        self.assertTrue(staged['prepared_hashes_verified'])
        self.assertEqual(calls, [('asset-101-abcdefgh', 0),
                                 ('asset-101-abcdefgh', 1),
                                 ('asset-101-abcdefgh', 2)])
        self.assertEqual(staged['copied_bytes'], len(raw) + len(chunk_raw))

    def test_collision_and_deadline_do_not_clobber_or_publish(self):
        self.destination.mkdir(); sentinel = self.destination / 'owner.txt'; sentinel.write_text('keep')
        with self.assertRaises(ValueError): self.run_collection(write=True)
        self.assertEqual(sentinel.read_text(), 'keep')
        sentinel.unlink(); self.destination.rmdir()
        with patch.object(collection.time, 'monotonic', side_effect=[0, 0, 999999]):
            with self.assertRaises(ValueError):
                self.run_collection(write=True, max_seconds=1)
        self.assertFalse(self.output.exists())

    def test_index_size_counts_toward_budget_and_output_reserve(self):
        plan = self.run_collection()
        with self.assertRaisesRegex(ValueError, 'byte budget'):
            self.run_collection(max_bytes=plan['estimated_bytes'] - 1)
        free_values = [2 * collection.GIB,
                       collection.GIB + 16 * 1024 ** 2 + self.pinned_index.stat().st_size - 1]
        with patch.object(collection.shutil, 'disk_usage', side_effect=[
                type('Space', (), {'free': value})() for value in free_values]):
            with self.assertRaisesRegex(ValueError, 'index disk reserve'):
                collection.stage(self.config, self.pinned_index, self.index_sha, self.workspace,
                    self.destination, self.output)
        self.assertFalse(self.destination.exists())

    def test_pending_validation_failure_keeps_error_and_removes_owned_pending(self):
        original = collection.PreparedVideos
        calls = 0
        def refuse_pending(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise ValueError('pending validator sentinel')
            return original(*args, **kwargs)
        with patch.object(collection, 'PreparedVideos', side_effect=refuse_pending):
            with self.assertRaisesRegex(ValueError, 'pending validator sentinel'):
                self.run_collection(write=True)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_name(self.output.name + '.pending').exists())
        self.assertTrue((self.destination / 'INCOMPLETE').exists())

    def test_standalone_cli_help_imports_without_pythonpath_from_outside_repo(self):
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        script = ROOT / 'scripts' / 'stage_protected_video_collection.py'
        result = subprocess.run([sys.executable, '-B', str(script), '--help'],
            cwd=self.root, env=env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--index-sha256', result.stdout)

    def test_duplicate_new_folder_names_and_existing_index_are_refused(self):
        fixtures.ExportTests.add_second_ready_asset(self)
        index = self.root / 'collision-index.json'
        fixtures.exporter.export(self.database, self.workspace, index)
        value = json.loads(index.read_bytes())
        value['assets'][1]['directory'] = value['assets'][0]['directory']
        index.write_text(json.dumps(value, separators=(',', ':')))
        with self.assertRaisesRegex(ValueError, 'Invalid prepared collection directory'):
            self.run_collection(index=index, index_sha256=hashlib.sha256(index.read_bytes()).hexdigest())
        self.output.write_text('owner')
        with self.assertRaises(ValueError): self.run_collection()
        self.assertEqual(self.output.read_text(), 'owner')

    def test_partial_copy_remains_incomplete_with_no_final_index(self):
        with patch.object(collection, '_copy_verified', side_effect=OSError('synthetic copy failure')):
            with self.assertRaises(OSError): self.run_collection(write=True)
        self.assertTrue((self.destination / 'INCOMPLETE').exists())
        self.assertFalse(self.output.exists())


if __name__ == '__main__':
    unittest.main()

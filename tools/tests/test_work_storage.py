"""Generated-file acceptance for development storage admission; no household data."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'server' / 'backend'))
sys.path.insert(0, str(ROOT / 'server' / 'scripts'))
from app import work_storage as storage
import rehearse_fullsize_database as full
import build_editorial_rehearsal_package as editorial
from tools import package_source


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.output = self.root / 'output.bin'

    def test_multiple_copies_and_overlap_are_aggregated_before_any_write(self):
        components = [(self.output, name, 100) for name in ('database', 'restore', 'journal', 'unpack')]
        with patch.object(storage.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(
                10**12, 0, storage.RESERVE + 399)):
            with self.assertRaisesRegex(storage.StorageRefused, 'insufficient_peak_space'):
                with storage.operation([self.output], components):
                    self.fail('allocation was admitted')
        self.assertEqual(list(self.root.iterdir()), [])

    def test_exact_budget_plus_reserve_is_accepted(self):
        with patch.object(storage.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(
                10**12, 0, storage.RESERVE + 400)):
            totals = storage.check_space([(self.output, 'copies', 400)])
        self.assertEqual(sum(size for _, size in totals.values()), 400)

    def test_separate_volumes_each_receive_their_own_reserve(self):
        first, second = self.root / 'a', self.root / 'b'
        with patch.object(storage, 'volume', side_effect=lambda path: (str(path), path)), \
                patch.object(storage.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(
                    10**12, 0, storage.RESERVE + 400)):
            totals = storage.check_space([(first, 'first volume', 400), (second, 'second volume', 400)])
        self.assertEqual(len(totals), 2)

    def test_invalid_budget_and_reserve_are_refused(self):
        for size in (-1, True, 1.5, '100'):
            with self.subTest(size=size), self.assertRaises(storage.StorageRefused):
                storage.check_space([(self.output, 'scratch', size)])
        with self.assertRaises(storage.StorageRefused):
            storage.check_space([(self.output, 'scratch', 1)], reserve=0)

    def test_empty_budget_and_duplicate_outputs_are_refused(self):
        with self.assertRaises(storage.StorageRefused):
            with storage.operation([self.output], []):
                self.fail()
        with self.assertRaisesRegex(storage.StorageRefused, 'distinct_outputs'):
            with storage.operation([self.output, self.output], [(self.output, 'output', 100)]):
                self.fail()

    def test_collision_preserves_existing_bytes(self):
        self.output.write_bytes(b'preserve')
        with self.assertRaisesRegex(storage.StorageRefused, 'output_must_be_absent'):
            storage.target(self.output)
        self.assertEqual(self.output.read_bytes(), b'preserve')

    def test_relative_and_escape_paths_are_refused(self):
        for path in (Path('relative'), self.root / '..' / 'escape.bin'):
            with self.subTest(path=path), self.assertRaises(storage.StorageRefused):
                storage.target(path)

    @unittest.skipUnless(os.name == 'nt', 'native Windows volume identity')
    def test_system_unc_device_and_missing_drive_refuse_without_creation(self):
        system = Path(os.environ['SYSTEMROOT']).anchor
        missing = next(letter for letter in 'ZYXWVUTSRQPONMLK' if not Path(letter + ':/').exists())
        paths = [Path(system) / ('photohouse-refusal-' + str(uuid.uuid4())) / 'out',
                 Path('//localhost/share/out'), Path('\\\\?\\D:\\out'),
                 Path(missing + ':/photohouse-refusal/out')]
        for path in paths:
            with self.subTest(path=path), self.assertRaises((storage.StorageRefused, OSError)):
                storage.target(path)
        self.assertFalse(paths[0].parent.exists())
        self.assertFalse(Path(missing + ':/').exists())

    @unittest.skipUnless(os.name == 'nt', 'native Windows DACL')
    def test_nonprivate_output_parent_is_refused(self):
        with patch.object(storage, 'require_private_directory', side_effect=ValueError('private refused')):
            with self.assertRaisesRegex(ValueError, 'private refused'):
                storage.target(self.output)
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(os.name == 'nt', 'native Windows junction')
    def test_junction_ancestor_is_refused_before_resolution(self):
        real = self.root / 'real'
        real.mkdir()
        junction = self.root / 'junction'
        result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(junction), str(real)],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.addCleanup(os.rmdir, junction)
        with self.assertRaisesRegex(storage.StorageRefused, 'reparse'):
            storage.target(junction / 'out.bin')
        self.assertFalse((real / 'out.bin').exists())

    def test_temporary_environment_is_scoped_and_receipt_records_closure(self):
        previous = {key: os.environ.get(key) for key in ('TEMP', 'TMP', 'TMPDIR', 'SQLITE_TMPDIR')}
        previous_temp = tempfile.tempdir
        with storage.operation([self.output], [(self.output, 'generated output', 1024)]) as temporary:
            for key in previous:
                self.assertEqual(os.environ[key], str(temporary))
            self.assertEqual(Path(tempfile.gettempdir()), temporary)
            self.output.write_bytes(b'generated')
        self.assertEqual({key: os.environ.get(key) for key in previous}, previous)
        self.assertEqual(tempfile.tempdir, previous_temp)
        receipt = json.loads((temporary.parent / 'receipt.json').read_text())
        self.assertEqual(receipt['state'], 'closed')
        self.assertEqual(receipt['actual_bytes'], 9)
        self.assertEqual(receipt['planned_bytes'], 1024)

    def test_failure_retains_partial_output_and_uncertain_receipt(self):
        with self.assertRaisesRegex(RuntimeError, 'synthetic failure'):
            with storage.operation([self.output], [(self.output, 'generated output', 1024)]) as temporary:
                self.output.write_bytes(b'partial')
                raise RuntimeError('synthetic failure')
        self.assertEqual(self.output.read_bytes(), b'partial')
        receipt = json.loads((temporary.parent / 'receipt.json').read_text())
        self.assertEqual(receipt['state'], 'failed_uncertain')
        self.assertEqual(receipt['actual_bytes'], 7)

    def test_final_budget_overrun_is_uncertain_and_preserves_output(self):
        with self.assertRaisesRegex(storage.StorageRefused, 'declared_work_budget_exceeded'):
            with storage.operation([self.output], [(self.output, 'bounded fixture', 1)]) as temporary:
                self.output.write_bytes(b'exceeded')
        receipt = json.loads((temporary.parent / 'receipt.json').read_text())
        self.assertEqual(receipt['state'], 'failed_uncertain')
        self.assertEqual(self.output.read_bytes(), b'exceeded')

    @unittest.skipUnless(os.name == 'nt', 'native cross-process admission lock')
    def test_another_process_cannot_claim_the_same_free_space(self):
        child = self.root / 'child.bin'
        code = ("from pathlib import Path; from app import work_storage as s; "
                "p=Path(__import__('sys').argv[1]); "
                "ctx=s.operation([p], [(p,'child',1024)]); ctx.__enter__()")
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'server' / 'backend'))
        with storage.operation([self.output], [(self.output, 'parent', 1024)]):
            result = subprocess.run([sys.executable, '-B', '-c', code, str(child)],
                                    env=env, capture_output=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'volume_operation_busy', result.stderr)
        self.assertFalse(child.exists())
        # Closure releases the lock without deleting any existing outputs.
        with storage.operation([child], [(child, 'after closure', 1024)]):
            child.write_bytes(b'ok')

    def test_nested_same_process_operation_uses_owned_admission(self):
        other = self.root / 'nested.bin'
        with storage.operation([self.output], [(self.output, 'outer including nested', 2048)]):
            with storage.operation([other], [(other, 'nested', 1024)]):
                other.write_bytes(b'nested')
        self.assertEqual(other.read_bytes(), b'nested')

    def test_database_entrypoint_refuses_full_peak_before_reading_source(self):
        with patch.object(storage.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(
                10**12, 0, storage.RESERVE + 6 * 1024**2 - 1)):
            with patch.object(full, 'read_source', side_effect=AssertionError('source opened')):
                with self.assertRaisesRegex(full.small.Refused, 'insufficient_peak_space'):
                    full.rehearse(self.root / 'absent.sqlite', self.output, self.root / 'restore.sqlite',
                                  'a' * 64, full.Budget(1024**2, 30))
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(os.name == 'nt', 'native Windows real-producer refusal')
    def test_database_entrypoint_refuses_c_before_reading_source(self):
        output = Path(os.environ['SYSTEMROOT']) / 'Temp' / ('photohouse-refused-' + str(uuid.uuid4()))
        with patch.object(full, 'read_source', side_effect=AssertionError('source opened')):
            with self.assertRaisesRegex(full.small.Refused, 'system_volume_refused'):
                full.snapshot(self.root / 'absent.sqlite', output, full.Budget(1024**2, 30))
        self.assertFalse(output.exists())

    def test_editorial_archive_is_admitted_and_written(self):
        output = self.root / 'source.zip'
        with patch.object(editorial, 'source_files', return_value={'fixture.py': b'# generated\n'}):
            result = editorial.build(ROOT, 'a' * 40, self.root / 'unused.zip', output)
        self.assertEqual(result['bytes'], output.stat().st_size)

    def test_editorial_archive_low_space_refuses_before_output(self):
        with patch.object(editorial, 'source_files', return_value={'fixture.py': b'# generated\n'}), \
                patch.object(storage.shutil, 'disk_usage', return_value=shutil._ntuple_diskusage(10**12, 0, 0)):
            with self.assertRaisesRegex(storage.StorageRefused, 'insufficient_peak_space'):
                editorial.build(ROOT, 'a' * 40, self.root / 'unused.zip', self.output)
        self.assertFalse(self.output.exists())

    @unittest.skipUnless(os.name == 'nt', 'native Windows producer defaults')
    def test_real_snapshot_cli_defaults_to_private_d_run(self):
        source = self.root / 'generated.sqlite'
        with closing(sqlite3.connect(source)) as db:
            db.executescript("CREATE TABLE alembic_version(version_num TEXT);"
                             "INSERT INTO alembic_version VALUES('a0c9d2e4f817');"
                             "CREATE TABLE generated(id INTEGER PRIMARY KEY, value TEXT);"
                             "INSERT INTO generated VALUES(1,'synthetic');")
            db.commit()
        run = storage.new_run()
        with patch.object(storage, 'new_run', return_value=run):
            self.assertEqual(full.main(['snapshot', '--database', str(source), '--max-bytes',
                                       str(1024**2), '--timeout-seconds', '30']), 0)
        out = run / 'snapshot.sqlite'
        self.assertEqual(out.drive.upper(), 'D:')
        with closing(sqlite3.connect(out)) as db:
            self.assertEqual(db.execute('SELECT value FROM generated').fetchall(), [('synthetic',)])


if __name__ == '__main__':
    unittest.main()

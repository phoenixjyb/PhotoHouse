"""Synthetic offline proposals never approve identity or modify the source."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'), str(ROOT / 'tests/security')]

from app.access import discovery as d
from app.access.discovery_index import index as parse_index, DiscoveryIndexRefused
from app.access.original_deletions import OriginalDeletionJournal
from app.access.private_storage import require_private_file
from app.access.discovery_provider import RefreshingPeopleIndex
import inspect_people_review_candidates as tool
import test_refreshing_people as fixtures


class PeopleReviewCandidateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RefreshingPeopleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.db_path = self.fixture.path
        if os.name != 'nt':
            self.db_path.chmod(0o600)
        self.index = self.fixture.index
        self.private = self.root / 'private'
        self.private.mkdir(mode=0o700)
        if os.name != 'nt':
            self.private.chmod(0o700)
        self.index_path = self.private / 'reviewed-index.json'
        self.index_path.write_bytes(d.packed(asdict(self.index)))
        if os.name != 'nt':
            self.index_path.chmod(0o600)
        self.output = self.private / 'proposal.json'

    def change(self, sql, params=()):
        self.fixture.change(sql, params)

    def add_candidates(self):
        # Asset 103 is already reviewed; 102 and MAXIMUM are active scoped assets.
        # DNN rows and duplicate manual rows are useful adversarial candidates.
        self.change('''INSERT INTO face_detections VALUES
            (30,102,301,'manual'),(31,102,301,'manual'),(32,102,301,'dnn'),
            (33,9223372036854775807,301,'manual'),
            (34,201,301,'manual'),(35,999,301,'manual'),
            (36,777,301,'manual')''')
        self.change("INSERT INTO assets VALUES(777,'private-path','active','image/jpeg',8,8,NULL,NULL,NULL,NULL)")
        # Deliberately leave 777 unmapped.

    def run_cli(self, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        args = ['--database', str(self.db_path), '--library', 'family-a',
                '--reviewed-index', str(self.index_path), '--out', str(self.output), *extra]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = tool.main(args)
        self.assertNotIn('private-path', stdout.getvalue() + stderr.getvalue())
        self.assertNotIn('Sample Child', stdout.getvalue() + stderr.getvalue())
        return code, stdout.getvalue(), stderr.getvalue()

    def test_distinct_manual_photos_exclude_every_reviewed_asset_and_report_more(self):
        self.add_candidates()
        before = self.db_path.read_bytes()
        code, stdout, _ = self.run_cli('--photos-per-person', '1')
        self.assertEqual(code, 0, stdout)
        result = json.loads(self.output.read_bytes())
        child = next(item for item in result['targets'] if item['person_id'] == '301')
        self.assertEqual([item['asset_id'] for item in child['assets']], ['9223372036854775807'])
        self.assertTrue(child['has_more'])
        face = child['assets'][0]['faces'][0]
        self.assertEqual(face, {'face_id': '33', 'label_source': 'manual',
                                'identity_confirmed': False, 'search_eligible': False})
        self.assertEqual(result['status'], 'requires_explicit_review')
        self.assertNotIn('assignments', result)
        with self.assertRaises(DiscoveryIndexRefused):
            parse_index(d.packed(result), d.ReadBudget().rows)
        self.assertEqual(before, self.db_path.read_bytes())
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)

    def test_manual_only_and_active_mapped_exact_library_scope(self):
        self.add_candidates()
        code, _, _ = self.run_cli()
        self.assertEqual(code, 0)
        result = json.loads(self.output.read_bytes())
        child = next(item for item in result['targets'] if item['person_id'] == '301')
        ids = {asset['asset_id'] for asset in child['assets']}
        self.assertEqual(ids, {'9223372036854775807', '102'})
        face_ids = {face['face_id'] for asset in child['assets'] for face in asset['faces']}
        self.assertEqual(face_ids, {'30', '31', '33'})
        self.assertNotIn('32', face_ids)
        self.assertNotIn('34', face_ids)
        self.assertNotIn('35', face_ids)

    def test_stale_identity_or_frozen_assignment_refuses_before_output(self):
        self.change("UPDATE persons SET display_name='Changed label' WHERE id=301")
        code, _, stderr = self.run_cli()
        self.assertEqual(code, 2)
        self.assertNotIn('Changed label', stderr)
        self.assertFalse(self.output.exists())

        self.change("UPDATE persons SET display_name='Sample Child / 示例儿童' WHERE id=301")
        self.change("UPDATE face_detections SET label_source='dnn' WHERE id=1")
        code, _, _ = self.run_cli()
        self.assertEqual(code, 2)
        self.assertFalse(self.output.exists())

    def test_new_upload_and_catalog_bookkeeping_bind_to_fresh_source(self):
        self.change("INSERT INTO assets VALUES(104,'private-path','active','image/jpeg',8,8,NULL,'2026-10-18',0,0)")
        self.change("INSERT INTO access_asset_libraries VALUES(104,'family-a')")
        self.change("INSERT INTO face_detections VALUES(40,104,301,'manual')")
        self.change("UPDATE persons SET updated_at='2026-10-19' WHERE id=301")
        self.change("UPDATE access_person_libraries SET revision=revision+1 WHERE person_id=301")
        code, _, _ = self.run_cli()
        self.assertEqual(code, 0)
        result = json.loads(self.output.read_bytes())
        self.assertNotEqual(result['current_source_digest'], self.index.source_digest)
        child = next(item for item in result['targets'] if item['person_id'] == '301')
        self.assertEqual(child['assets'][0]['asset_id'], '104')
        self.assertEqual(child['assets'][0]['faces'][0]['face_id'], '40')

    def test_private_new_output_and_paired_deletion_guard(self):
        self.add_candidates()
        # The fixture remains immutable across a successful guarded inspection.
        ledger = self.private / 'journal.sqlite'
        namespace = str(uuid.uuid4())
        journal = OriginalDeletionJournal.initialize(ledger, namespace)
        _, seq, digest = journal.head()
        with sqlite3.connect(self.db_path) as db:
            db.execute('''CREATE TABLE access_original_deletion_state(
                id INTEGER PRIMARY KEY,namespace TEXT NOT NULL,applied_seq INTEGER NOT NULL,
                applied_digest TEXT NOT NULL)''')
            db.execute('INSERT INTO access_original_deletion_state VALUES(1,?,?,?)',
                       (namespace, seq, digest))
            db.commit()
        if os.name != 'nt':
            self.db_path.chmod(0o600)
        before = self.db_path.read_bytes()
        code, _, _ = self.run_cli('--deletion-journal', str(ledger),
                                  '--deletion-namespace', namespace)
        self.assertEqual(code, 0)
        self.assertEqual(before, self.db_path.read_bytes())
        # The file itself is private; the helper also verifies owner and links.
        require_private_file(self.output)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        original = self.output.read_bytes()
        code, _, _ = self.run_cli()
        self.assertEqual(code, 2)
        self.assertEqual(self.output.read_bytes(), original)
        self.output = self.private / 'missing-history.json'
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())
        code, _, _ = self.run_cli('--deletion-journal', str(ledger))
        self.assertEqual(code, 2)
        self.assertFalse(self.output.exists())
        self.assertEqual(self.run_cli('--deletion-journal', str(ledger),
            '--deletion-namespace', str(uuid.uuid4()))[0], 2)
        self.assertFalse(self.output.exists())

    def test_rejects_symlink_and_loose_private_input_or_output_parent(self):
        alias = self.private / 'index-link.json'
        alias.symlink_to(self.index_path)
        args = ['--database', str(self.db_path), '--library', 'family-a',
                '--reviewed-index', str(alias), '--out', str(self.output)]
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(tool.main(args), 2)
        self.assertFalse(self.output.exists())
        if os.name != 'nt':
            self.index_path.chmod(0o644)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(self.run_cli()[0], 2)
            self.index_path.chmod(0o600)
            loose = self.root / 'loose'
            loose.mkdir(mode=0o755)
            loose.chmod(0o755)
            out = loose / 'proposal.json'
            args[args.index('--reviewed-index') + 1] = str(self.index_path)
            args[args.index('--out') + 1] = str(out)
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(tool.main(args), 2)
            self.assertFalse(out.exists())

    def test_refuses_photo_with_more_than_bounded_face_rows(self):
        self.change('''INSERT INTO face_detections VALUES
            (1000,102,301,'manual'),(1001,102,301,'manual'),(1002,102,301,'manual'),
            (1003,102,301,'manual'),(1004,102,301,'manual'),(1005,102,301,'manual'),
            (1006,102,301,'manual'),(1007,102,301,'manual'),(1008,102,301,'manual'),
            (1009,102,301,'manual'),(1010,102,301,'manual'),(1011,102,301,'manual'),
            (1012,102,301,'manual'),(1013,102,301,'manual'),(1014,102,301,'manual'),
            (1015,102,301,'manual'),(1016,102,301,'manual'),(1017,102,301,'manual'),
            (1018,102,301,'manual'),(1019,102,301,'manual'),(1020,102,301,'manual'),
            (1021,102,301,'manual'),(1022,102,301,'manual'),(1023,102,301,'manual'),
            (1024,102,301,'manual'),(1025,102,301,'manual'),(1026,102,301,'manual'),
            (1027,102,301,'manual'),(1028,102,301,'manual'),(1029,102,301,'manual'),
            (1030,102,301,'manual'),(1031,102,301,'manual'),(1032,102,301,'manual')''')
        code, _, _ = self.run_cli('--photos-per-person', '1')
        self.assertEqual(code, 2)
        self.assertFalse(self.output.exists())

    def test_changed_ownership_or_suppressed_approved_sample_refuses(self):
        self.change("UPDATE access_person_libraries SET library_id='family-b' WHERE person_id=301")
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())
        self.change("UPDATE access_person_libraries SET library_id='family-a' WHERE person_id=301")
        self.change("UPDATE assets SET status='suppressed' WHERE id=101")
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_limits_are_refused_before_source_read_or_output(self):
        with patch.object(tool, 'open_reviewed_people_source', side_effect=AssertionError('source opened')) as source:
            for value in ('0', '-1', '13', '1000000'):
                self.assertEqual(self.run_cli('--photos-per-person', value)[0], 2)
                self.assertFalse(self.output.exists())
            source.assert_not_called()


if __name__ == '__main__':
    unittest.main()

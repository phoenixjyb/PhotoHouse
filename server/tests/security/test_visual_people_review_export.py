"""Offline export accepts only fresh owner-confirmed explicit manual faces."""
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

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'), str(ROOT / 'tests/security')]

from app.access import discovery as d
from app.access.original_deletions import OriginalDeletionJournal
import export_visual_people_review as tool
import test_people_visual_review as visual


class VisualPeopleReviewExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        visual.VisualPeopleReviewTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        visual.VisualPeopleReviewTests.tearDownClass()

    def setUp(self):
        self.journey = visual.VisualPeopleReviewTests('runTest')
        self.journey.setUp()
        self.addCleanup(self.journey.doCleanups)
        self.db_path = Path(self.journey.f.path).resolve()
        self.index = self.journey.index
        with self.journey.f.connection() as db:
            self.reviewer = db.execute(
                "SELECT bootstrap_operator FROM access_libraries WHERE id='family-a'").fetchone()[0]
        self.tmp = tempfile.TemporaryDirectory(prefix='visual-review-export-')
        self.addCleanup(self.tmp.cleanup)
        self.private = Path(self.tmp.name).resolve() / 'private'
        self.private.mkdir(mode=0o700)
        if os.name != 'nt':
            self.private.chmod(0o700)
            self.db_path.chmod(0o600)
        self.index_path = self.private / 'reviewed-index.json'
        self.selection_path = self.private / 'selection.json'
        self.output = self.private / 'export.json'
        self.index_path.write_bytes(d.packed(asdict(self.index)))
        self._write_selection()
        if os.name != 'nt':
            self.index_path.chmod(0o600)
            self.selection_path.chmod(0o600)

    def _write_selection(self, assignments=None, people=None):
        self.selection_path.write_bytes(d.packed({'schema': 1, 'library_id': 'family-a',
            'people': people if people is not None else [{'id': '1', 'label': 'Alice'}],
            'assignments': assignments if assignments is not None else [
                {'id': '11', 'asset_id': '101', 'person_id': '1', 'source': 'manual'},
                {'id': '13', 'asset_id': '102', 'person_id': '1', 'source': 'manual'}]}))
        if os.name != 'nt':
            self.selection_path.chmod(0o600)

    def run_cli(self, *extra):
        stdout, stderr = io.StringIO(), io.StringIO()
        args = ['--database', str(self.db_path), '--library', 'family-a',
            '--reviewed-index', str(self.index_path), '--selection', str(self.selection_path),
            '--reviewer-account', self.reviewer, '--out', str(self.output), *extra]
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = tool.main(args)
        self.assertNotIn('Alice', stdout.getvalue() + stderr.getvalue())
        self.assertNotIn('private-vector', stdout.getvalue() + stderr.getvalue())
        return code, stdout.getvalue(), stderr.getvalue()

    def confirm(self):
        item = next(item for item in self.journey.queue()['items'] if item['id'] == '13')
        response = self.journey.confirm(item)
        self.assertEqual(response.status_code, 200, response.text)
        return item

    def test_real_owner_confirmation_exports_bound_tuple_read_only_and_private(self):
        self.confirm()
        before = self.db_path.read_bytes()
        code, stdout, _ = self.run_cli()
        self.assertEqual(code, 0, stdout)
        packet = json.loads(self.output.read_bytes())
        self.assertEqual(packet['status'], 'requires_source_bound_preparation')
        self.assertEqual(packet['base_index_digest'], d.digest(asdict(self.index)))
        self.assertEqual(packet['selection']['people'], [{'id': '1', 'label': 'Alice'}])
        self.assertEqual(packet['selection']['assignments'], [
            {'id': '11', 'asset_id': '101', 'person_id': '1', 'source': 'manual'},
            {'id': '13', 'asset_id': '102', 'person_id': '1', 'source': 'manual'}])
        evidence = packet['confirmation_evidence']
        self.assertEqual(len(evidence), 1)
        self.assertEqual({k: evidence[0][k] for k in ('face_id','asset_id','person_id')},
                         {'face_id':'13','asset_id':'102','person_id':'1'})
        self.assertRegex(evidence[0]['confirmation_proof'], r'^[0-9a-f]{64}$')
        self.assertTrue(evidence[0]['audit_id'].isdigit())
        self.assertEqual(before, self.db_path.read_bytes())
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.private.stat().st_mode), 0o700)
        original = self.output.read_bytes()
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.output.read_bytes(), original)

    def test_manual_association_without_current_marker_is_not_confirmation(self):
        before = self.db_path.read_bytes()
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())
        self.assertEqual(before, self.db_path.read_bytes())

    def test_stale_face_membership_or_suppressed_source_refuses(self):
        self.confirm()
        self.journey.mutate('UPDATE face_detections SET bbox_x=0.2 WHERE id=13')
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_suppressed_face_is_refused_even_with_a_current_confirmation(self):
        self.confirm()
        self.journey.mutate("UPDATE assets SET status='suppressed' WHERE id=102")
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_changed_frozen_index_face_and_membership_revision_refuse(self):
        self.confirm()
        self.journey.mutate("UPDATE face_detections SET label_source='dnn' WHERE id=11")
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_membership_revision_change_invalidates_confirmation(self):
        self.confirm()
        self.journey.mutate("UPDATE access_memberships SET revision=revision+1 WHERE account_id=?",
                            (self.reviewer,))
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_foreign_person_library_and_roster_name_mismatch_refuse(self):
        self.confirm()
        self._write_selection(people=[{'id': '1', 'label': 'Changed'}])
        self.assertEqual(self.run_cli()[0], 2)
        self._write_selection(people=[{'id': '1', 'label': 'Alice'}], assignments=[
            {'id':'11','asset_id':'101','person_id':'1','source':'manual'},
            {'id':'13','asset_id':'102','person_id':'5','source':'manual'}])
        self.assertEqual(self.run_cli()[0], 2)
        self._write_selection(people=[{'id': '1', 'label': 'Alice'}], assignments=[
            {'id':'11','asset_id':'101','person_id':'1','source':'manual'},
            {'id':'21','asset_id':'201','person_id':'1','source':'manual'}])
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_revoked_reviewer_library_or_owner_role_refuses(self):
        self.confirm()
        self.journey.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                            (self.reviewer,))
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_non_owner_role_refuses_even_if_account_stays_active(self):
        self.confirm()
        self.journey.mutate("UPDATE access_memberships SET role='viewer' WHERE account_id=?",
                            (self.reviewer,))
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_active_family_owner_does_not_need_global_operator_privilege(self):
        self.confirm()
        self.journey.mutate('DELETE FROM access_operators WHERE account_id=?', (self.reviewer,))
        code, stdout, _ = self.run_cli()
        self.assertEqual(code, 0, stdout)
        self.assertTrue(self.output.exists())

    def test_selection_cannot_drop_old_approved_tuple_or_add_unconfirmed_face(self):
        self.confirm()
        self._write_selection(assignments=[
            {'id':'13','asset_id':'102','person_id':'1','source':'manual'}])
        self.assertEqual(self.run_cli()[0], 2)
        self._write_selection(assignments=[
            {'id':'11','asset_id':'101','person_id':'1','source':'manual'},
            {'id':'12','asset_id':'102','person_id':'1','source':'manual'}])
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_more_than_twelve_new_faces_is_refused_before_source_lookup(self):
        self.confirm()
        rows = [{'id':'11','asset_id':'101','person_id':'1','source':'manual'}]
        rows.extend({'id':str(face),'asset_id':'102','person_id':'1','source':'manual'}
                    for face in range(1000, 1013))
        self._write_selection(assignments=rows)
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_automatic_or_nonmanual_source_is_rejected_by_selection_schema(self):
        self.confirm()
        self._write_selection(assignments=[
            {'id':'11','asset_id':'101','person_id':'1','source':'manual'},
            {'id':'13','asset_id':'102','person_id':'1','source':'automatic'}])
        self.assertEqual(self.run_cli()[0], 2)
        self.assertFalse(self.output.exists())

    def test_deletion_guard_options_must_be_paired_and_bound(self):
        self.confirm()
        self.assertEqual(self.run_cli('--deletion-journal', str(self.private / 'missing.sqlite'))[0], 2)
        ledger = self.private / 'journal.sqlite'
        namespace = str(uuid.uuid4())
        OriginalDeletionJournal.initialize(ledger, namespace)
        if os.name != 'nt':
            ledger.chmod(0o600)
        # An unbound primary is refused when the operator supplies a journal.
        self.assertEqual(self.run_cli('--deletion-journal', str(ledger),
                                      '--deletion-namespace', namespace)[0], 2)
        _, sequence, digest = OriginalDeletionJournal(ledger, namespace).head()
        with self.journey.f.connection() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS access_original_deletion_state(
                id INTEGER PRIMARY KEY,namespace TEXT NOT NULL,
                applied_seq INTEGER NOT NULL,applied_digest TEXT NOT NULL)''')
            db.execute('DELETE FROM access_original_deletion_state')
            db.execute('INSERT INTO access_original_deletion_state VALUES(1,?,?,?)',
                       (namespace, sequence, digest))
            db.commit()
        before = self.db_path.read_bytes()
        code, stdout, _ = self.run_cli('--deletion-journal', str(ledger),
                                      '--deletion-namespace', namespace)
        self.assertEqual(code, 0, stdout)
        self.assertEqual(before, self.db_path.read_bytes())
        self.assertEqual(json.loads(self.output.read_bytes())['status'],
                         'requires_source_bound_preparation')
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)


if __name__ == '__main__':
    unittest.main()

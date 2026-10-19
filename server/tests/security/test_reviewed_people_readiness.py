"""Synthetic, read-only readiness inspection for explicit people selections."""
from contextlib import closing, redirect_stderr, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'),
               str(ROOT / 'tests' / 'security')]

from phone_discovery_fixture import create
import inspect_reviewed_people_readiness as inspector
from app.access.discovery import ReadBudget


class ReviewedPeopleReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='reviewed-people-readiness-')).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.database = self.tmp / 'access.sqlite3'
        setup = sqlite3.connect(str(self.database))
        setup.execute('''CREATE TABLE persons(id INTEGER PRIMARY KEY,display_name TEXT,
            face_count INTEGER,updated_at TEXT)''')
        create(setup)
        setup.execute('''CREATE TABLE access_person_libraries(
            person_id INTEGER PRIMARY KEY,library_id TEXT,creator_id TEXT,revision INTEGER)''')
        setup.close()
        with closing(sqlite3.connect(str(self.database))) as db:
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(301,'Owned Person',1)")
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(401,'Foreign Secret Label',1)")
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(501,'Legacy Person',3)")
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(502,'Hidden Person',0)")
            db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(503,'Unmapped Only',1)")
            db.execute("INSERT INTO access_person_libraries(person_id,library_id,creator_id,revision) VALUES(301,'family-a','two',1)")
            db.execute("INSERT INTO access_person_libraries(person_id,library_id,creator_id,revision) VALUES(401,'family-b','foreign',1)")
            db.execute("INSERT INTO assets VALUES(500,'synthetic-path','active','image/jpeg',8,8,NULL,'2026-01-01')")
            db.execute("INSERT INTO face_detections VALUES(601,101,301,'manual')")
            db.execute("INSERT INTO face_detections VALUES(602,101,301,'dnn')")
            db.execute("INSERT INTO face_detections VALUES(608,101,301,'manual')")
            db.execute("INSERT INTO face_detections VALUES(603,103,501,'manual')")
            db.execute("INSERT INTO face_detections VALUES(604,201,501,'manual')")
            db.execute("INSERT INTO face_detections VALUES(605,500,501,'manual')")
            db.execute("INSERT INTO face_detections VALUES(606,201,401,'manual')")
            db.execute("INSERT INTO face_detections VALUES(609,101,401,'manual')")
            db.execute("INSERT INTO face_detections VALUES(607,500,503,'manual')")
            db.commit()

    def selection(self, people, assignments):
        return {'schema': 1, 'library_id': 'family-a', 'people': people,
                'assignments': assignments}

    @staticmethod
    def person(person_id, label):
        return {'id': str(person_id), 'label': label}

    @staticmethod
    def assignment(face_id, asset_id, person_id):
        return {'id': str(face_id), 'asset_id': str(asset_id),
                'person_id': str(person_id), 'source': 'manual'}

    def inspect(self, selection, *, budget=None):
        with closing(sqlite3.connect(str(self.database))) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            return inspector.inspect_selection(db, 'family-a', selection, budget=budget)

    def test_legacy_visible_record_is_reported_but_not_ready_while_owned_is_ready(self):
        mixed = self.inspect(self.selection(
            [self.person(301, 'Owned Person'), self.person(501, 'Legacy Person')],
            [self.assignment(601, 101, 301), self.assignment(603, 103, 501)]))
        self.assertFalse(mixed['ready_for_source_bound_preparation'])
        self.assertEqual([item['status'] for item in mixed['people']],
                         ['exact_owned', 'legacy_visible_without_owner'])
        self.assertTrue(mixed['people'][1]['outside_or_unmapped_faces'])
        self.assertEqual([item['status'] for item in mixed['assignments']],
                         ['manual_current', 'manual_current'])

        owned = self.inspect(self.selection([self.person(301, 'Owned Person')],
                                            [self.assignment(601, 101, 301)]))
        self.assertTrue(owned['ready_for_source_bound_preparation'])
        self.assertEqual(owned['status'], 'requires_explicit_review')

    def test_foreign_hidden_and_unmapped_only_people_are_unavailable_without_foreign_labels(self):
        result = self.inspect(self.selection(
            [self.person(401, 'Selected label'), self.person(502, 'Hidden Person'),
             self.person(503, 'Unmapped Only')],
            [self.assignment(606, 201, 401), self.assignment(607, 500, 503),
             self.assignment(609, 101, 401)]))
        self.assertEqual([item['status'] for item in result['people']],
                         ['name_changed_or_unavailable'] * 3)
        self.assertTrue(all(item['outside_or_unmapped_faces'] is None
                            for item in result['people']))
        self.assertEqual([item['status'] for item in result['assignments']],
                         ['unavailable', 'unavailable', 'unavailable'])
        self.assertNotIn('Foreign Secret Label', json.dumps(result))
        self.assertNotIn('family-b', json.dumps(result))

    def test_label_mismatch_and_selected_assignment_states_fail_closed(self):
        # Duplicate explicit face IDs are rejected before querying the catalog.
        with self.assertRaises(inspector.Refused):
            self.inspect(self.selection([self.person(301, 'Old label')],
                [self.assignment(601, 101, 301), self.assignment(601, 103, 301)]))
        result = self.inspect(self.selection(
            [self.person(301, 'Old label')],
            [self.assignment(601, 101, 301), self.assignment(602, 101, 301),
             self.assignment(608, 103, 301)]))
        self.assertEqual(result['people'][0]['status'], 'name_changed_or_unavailable')
        self.assertEqual([item['status'] for item in result['assignments']],
                         ['manual_current', 'not_manual', 'unavailable'])
        self.assertFalse(result['ready_for_source_bound_preparation'])

    def test_only_explicit_assignment_ids_are_checked_and_each_person_needs_one(self):
        result = self.inspect(self.selection(
            [self.person(301, 'Owned Person'), self.person(501, 'Legacy Person')],
            [self.assignment(601, 101, 301)]))
        self.assertEqual([item['id'] for item in result['assignments']], ['601'])
        self.assertEqual(len(result['assignments']), 1)
        self.assertFalse(result['ready_for_source_bound_preparation'])

    def test_digest_binds_owner_revision_and_selected_face_withdrawal(self):
        selection = self.selection([self.person(301, 'Owned Person')],
                                   [self.assignment(601, 101, 301)])
        initial = self.inspect(selection)
        with closing(sqlite3.connect(str(self.database))) as db:
            db.execute("UPDATE access_person_libraries SET revision=2 WHERE person_id=301")
            db.commit()
        revised = self.inspect(selection)
        self.assertNotEqual(initial['source_digest'], revised['source_digest'])
        with closing(sqlite3.connect(str(self.database))) as db:
            db.execute('DELETE FROM face_detections WHERE id=601')
            db.commit()
        withdrawn = self.inspect(selection)
        self.assertNotEqual(revised['source_digest'], withdrawn['source_digest'])
        self.assertEqual(withdrawn['assignments'][0]['status'], 'unavailable')

    def test_unselected_detection_flood_does_not_consume_inspection_rows(self):
        with closing(sqlite3.connect(str(self.database))) as db:
            db.executemany("INSERT INTO face_detections VALUES(?,?,501,'manual')",
                           ((10000 + value, 101) for value in range(3000)))
            db.commit()
        # One selected legacy person, one outside-scope boolean and one exact
        # face fit three rows; its thousands of unseen detections are not read.
        result = self.inspect(self.selection([self.person(501, 'Legacy Person')],
            [self.assignment(603, 103, 501)]), budget=ReadBudget(rows=3))
        self.assertFalse(result['ready_for_source_bound_preparation'])
        self.assertTrue(result['people'][0]['outside_or_unmapped_faces'])
        self.assertEqual([item['id'] for item in result['assignments']], ['603'])

    def test_unavailable_face_digest_does_not_disclose_foreign_person_changes(self):
        selection = self.selection([self.person(301, 'Owned Person')],
                                   [self.assignment(601, 101, 301)])
        with closing(sqlite3.connect(str(self.database))) as db:
            db.execute('UPDATE face_detections SET person_id=401 WHERE id=601')
            db.commit()
        initial = self.inspect(selection)
        with closing(sqlite3.connect(str(self.database))) as db:
            db.execute('UPDATE face_detections SET person_id=999 WHERE id=601')
            db.commit()
        later = self.inspect(selection)
        self.assertEqual(initial['assignments'][0]['status'], 'unavailable')
        self.assertEqual(initial, later)

    def test_selection_schema_is_strict_and_source_is_manual_only(self):
        good = self.selection([self.person(301, 'Owned Person')],
                              [self.assignment(601, 101, 301)])
        for value in (dict(good, extra=True), dict(good, schema=True),
                      dict(good, assignments=[dict(good['assignments'][0], source='dnn')]),
                      dict(good, people=[self.person(301, 'Owned Person'),
                                         self.person(301, 'Duplicate')])):
            with self.subTest(value=value):
                with self.assertRaises(inspector.Refused):
                    inspector.validate_selection(value, 'family-a', 100000)

    def test_cli_is_private_exclusive_read_only_and_does_not_overwrite(self):
        if os.name == 'nt':
            self.skipTest('POSIX private output mode check')
        output_dir = self.tmp / 'private'
        output_dir.mkdir(mode=0o700)
        output_dir.chmod(0o700)
        selection_path = self.tmp / 'selection.json'
        selection_path.write_text(json.dumps(self.selection(
            [self.person(301, 'Owned Person')], [self.assignment(601, 101, 301)])),
            encoding='utf-8')
        selection_path.chmod(0o600)
        out = output_dir / 'inspection.json'
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        args = ['--database', str(self.database), '--library', 'family-a',
                '--selection', str(selection_path), '--out', str(out)]
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
            self.assertEqual(inspector.main(args), 0)
        after = hashlib.sha256(self.database.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(stat_mode(out), 0o600)
        receipt = json.loads(stdout.getvalue())
        self.assertEqual(set(receipt), {'people', 'assignments', 'source_digest',
            'output_sha256', 'output_bytes'})
        original = out.read_bytes()
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(inspector.main(args), 2)
        self.assertEqual(out.read_bytes(), original)


def stat_mode(path):
    return path.stat().st_mode & 0o777


if __name__ == '__main__':
    unittest.main()

"""Deletion-head guarding for the reviewed-people source preparation CLIs."""
from contextlib import closing, redirect_stderr, redirect_stdout
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'),
               str(ROOT / 'tests/security')]

from app.access import discovery as d
from app.access.original_deletions import OriginalDeletionJournal
import inspect_reviewed_people_readiness as inspector
import prepare_reviewed_people_index as preparer
import test_refreshing_people as refreshing_people_fixtures
import test_provisioning_deletion_guard as deletion_guard_fixtures


class ReviewedPeopleDeletionGuardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = refreshing_people_fixtures.RefreshingPeopleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.private = self.root / 'private'
        self.private.mkdir(mode=0o700)
        if os.name != 'nt':
            self.private.chmod(0o700)
        self.selection_path = self.private / 'selection.json'
        self.base_path = self.private / 'base.json'
        self.review_path = self.private / 'review.json'
        self.database = self.fixture.path
        self.selection_path.write_text(json.dumps({
            'schema': 1, 'library_id': 'family-a',
            'people': [{'id': '301', 'label': 'Sample Child / 示例儿童'}],
            'assignments': [{'id': '1', 'asset_id': '101', 'person_id': '301',
                             'source': 'manual'}],
        }), encoding='utf-8')
        self.base_path.write_bytes(d.packed(asdict(self.fixture.base)))
        self.review_path.write_bytes(d.packed(self.fixture.review))
        for path in (self.selection_path, self.base_path, self.review_path):
            if os.name != 'nt':
                path.chmod(0o600)
        self.ledger_path = self.private / 'deletions.sqlite'
        self.namespace = str(uuid.uuid4())
        self.journal = None

    def bind_journal(self, journal=None):
        if journal is None:
            self.journal = OriginalDeletionJournal.initialize(self.ledger_path, self.namespace)
        else:
            self.journal = journal
            self.ledger_path = journal.path
            self.namespace = journal.namespace
        _, sequence, digest = self.journal.head()
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('''CREATE TABLE IF NOT EXISTS access_original_deletion_state(
                id INTEGER PRIMARY KEY,namespace TEXT NOT NULL,applied_seq INTEGER NOT NULL,
                applied_digest TEXT NOT NULL)''')
            db.execute('''INSERT INTO access_original_deletion_state VALUES(1,?,?,?)
                ON CONFLICT(id) DO UPDATE SET namespace=excluded.namespace,
                    applied_seq=excluded.applied_seq,applied_digest=excluded.applied_digest''',
                       (self.namespace, sequence, digest))
            db.commit()
        return self.journal

    def args_for(self, tool, output, guard=()):
        common = ['--database', str(self.database)]
        if tool is inspector:
            common += ['--library', 'family-a', '--selection', str(self.selection_path)]
        else:
            common += ['--base-index', str(self.base_path), '--review', str(self.review_path),
                       '--library', 'family-a', '--revision', '2', '--inspect']
        common += ['--out', str(output), *map(str, guard)]
        return common

    def guard_args(self, *, path=None, namespace=None):
        return ['--deletion-journal', str(path or self.ledger_path),
                '--deletion-namespace', namespace or self.namespace]

    def call(self, tool, output, guard=()):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = tool.main(self.args_for(tool, output, guard))
        message = stdout.getvalue() + stderr.getvalue()
        for private_value in (str(self.ledger_path), self.namespace,
                              'Sample Child', '示例儿童', 'journal_meta'):
            self.assertNotIn(private_value, message)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_unbound_fixtures_stay_compatible_and_bound_current_head_is_read_only(self):
        for tool, name in ((inspector, 'readiness.json'), (preparer, 'candidate.json')):
            output = self.private / name
            code, _, error = self.call(tool, output)
            self.assertEqual((code, error), (0, ''))
            self.assertTrue(output.is_file())
        self.assertFalse(self.ledger_path.exists())

        self.bind_journal()
        before_database = self.database.read_bytes()
        before_ledger = self.ledger_path.read_bytes()
        for tool, name in ((inspector, 'guarded-readiness.json'),
                           (preparer, 'guarded-candidate.json')):
            output = self.private / name
            code, _, error = self.call(tool, output, self.guard_args())
            self.assertEqual((code, error), (0, ''))
            self.assertTrue(output.is_file())
        self.assertEqual(self.database.read_bytes(), before_database)
        self.assertEqual(self.ledger_path.read_bytes(), before_ledger)

    def test_bound_primary_requires_complete_correct_guard_and_current_marker(self):
        self.bind_journal()
        for tool, name in ((inspector, 'readiness'), (preparer, 'candidate')):
            cases = (
                (),
                ['--deletion-journal', str(self.ledger_path)],
                ['--deletion-namespace', self.namespace],
                self.guard_args(namespace=str(uuid.uuid4())),
            )
            for number, guard in enumerate(cases):
                with self.subTest(tool=tool.__name__, guard=guard):
                    output = self.private / f'{name}-{number}.json'
                    code, stdout, _ = self.call(tool, output, guard)
                    self.assertEqual(code, 2)
                    self.assertEqual(stdout, '')
                    self.assertFalse(output.exists())

        with closing(sqlite3.connect(self.database)) as db:
            db.execute("UPDATE access_original_deletion_state SET applied_digest=? WHERE id=1",
                       ('f' * 64,))
            db.commit()
        for tool, name in ((inspector, 'stale-readiness.json'),
                           (preparer, 'stale-candidate.json')):
            output = self.private / name
            code, stdout, _ = self.call(tool, output, self.guard_args())
            self.assertEqual(code, 2)
            self.assertEqual(stdout, '')
            self.assertFalse(output.exists())

    def test_legitimate_external_advance_during_source_read_prevents_output(self):
        advancer_class = deletion_guard_fixtures.ProvisioningDeletionGuardTests
        advancer_class.setUpClass()
        self.addCleanup(advancer_class.tearDownClass)
        cases = (
            (inspector, 'readiness-advanced.json', inspector.inspect_selection),
            (preparer, 'candidate-advanced.json', preparer.derive),
        )
        for tool, name, target in cases:
            with self.subTest(tool=tool.__name__):
                advancer = advancer_class()
                advancer.setUp()
                self.addCleanup(advancer.doCleanups)
                self.bind_journal(advancer.journal)
                output = self.private / name
                def run_then_advance(*args, **kwargs):
                    result = target(*args, **kwargs)
                    advancer.advance_ledger_on_copy()
                    return result
                with patch.object(tool, target.__name__, side_effect=run_then_advance):
                    code, stdout, _ = self.call(tool, output, self.guard_args())
                self.assertEqual(code, 2)
                self.assertEqual(stdout, '')
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()

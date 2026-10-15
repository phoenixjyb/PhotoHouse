"""Private operator CLI: explicit paths, scoped reads and no data mutation."""
from contextlib import closing, redirect_stdout, redirect_stderr
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts'), str(ROOT / 'tests/security')]
import check_private_search as cli
import prepare_access_discovery_index as producer
import test_library_reads as fixtures
from app.access.original_deletions import OriginalDeletionJournal


class PrivateSearchCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.fixture = fixtures.LibraryReadTests('test_gallery_scopes_count_before_pagination_and_returns_safe_contract')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.path = self.fixture.path.resolve()
        self.root = self.fixture.path.parent.resolve()
        self.token = self.root / 'operator-token.txt'
        self.token.write_text(self.fixture.owner_token)
        self.token.chmod(0o600)
        self.index = self.root / 'reviewed-index.json'
        import time
        with closing(producer.open_read_only(self.fixture.path, time.monotonic())) as db:
            index, _ = producer.derive(db, 'family-a', '1')
        producer.write_new(self.index, json.dumps(asdict(index)).encode())

    def invoke(self, out, extra=()):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = cli.main(['--database', str(self.fixture.path), '--library', 'family-a',
                             '--index', str(self.index), '--token-file', str(self.token),
                             '--out', str(out), *extra])
        return code, stdout.getvalue(), stderr.getvalue()

    def test_real_runtime_readiness_and_evaluation_are_readonly_and_redacted(self):
        cases = self.root / 'cases.json'
        cases.write_text(json.dumps({'version': 1, 'cases': [
            {'id': 'q1', 'text': '找视频', 'expect': {'kind': 'results', 'filters': {'media': ['video']}}}]}))
        cases.chmod(0o600)
        before = hashlib.sha256(self.fixture.path.read_bytes()).hexdigest()
        out = self.root / 'report.json'
        code, stdout, stderr = self.invoke(out, ['--cases', str(cases)])
        self.assertEqual(code, 0, stderr)
        self.assertEqual(stderr, '')
        report = json.loads(out.read_bytes())
        self.assertEqual(report['status'], 'current')
        self.assertEqual(report['evaluation']['passed_count'], 1)
        self.assertEqual(report['readiness']['date_basis'], 'capture')
        self.assertEqual(hashlib.sha256(self.fixture.path.read_bytes()).hexdigest(), before)
        self.assertEqual(out.stat().st_mode & 0o077, 0)
        for private in (self.fixture.owner_token, 'family-a', '找视频', str(self.root)):
            self.assertNotIn(private, stdout + stderr + out.read_text())
        code, _, _ = self.invoke(out)
        self.assertEqual(code, 2, 'never overwrite a prior report')

    def test_denied_actor_and_unsafe_private_inputs_create_no_report(self):
        out = self.root / 'refused.json'
        self.token.write_text(self.fixture.other_token)
        code, stdout, stderr = self.invoke(out)
        self.assertEqual(code, 2)
        self.assertFalse(out.exists())
        self.assertEqual(stdout, '')
        self.assertNotIn(self.fixture.other_token, stderr)
        self.token.chmod(0o644)
        code, _, _ = self.invoke(out)
        self.assertEqual(code, 2)
        self.assertFalse(out.exists())

    def test_missing_or_stale_source_reports_no_partial_scores(self):
        self.fixture.mutate("UPDATE assets SET taken_at='2024-01-01' WHERE id=101")
        out = self.root / 'stale.json'
        code, _, stderr = self.invoke(out)
        self.assertEqual(code, 3, stderr)
        self.assertEqual(json.loads(out.read_bytes()),
                         {'version': 1, 'status': 'source_changed', 'readiness': None, 'evaluation': None})

    def test_private_reader_rejects_duplicate_json_symlinks_and_repository_paths(self):
        duplicate = self.root / 'duplicate.json'
        duplicate.write_text('{"version":1,"version":1,"cases":[]}')
        duplicate.chmod(0o600)
        with self.assertRaises(cli.Refused):
            cli.cases_file(duplicate)
        alias = self.root / 'token-link.txt'
        alias.symlink_to(self.token)
        with self.assertRaises(cli.Refused):
            cli.private_bytes(alias, 4096)
        with self.assertRaises(cli.Refused):
            cli.selected(ROOT.parent / 'private-test-output.json', private=True, output=True)


class ReadOnlyJournalTests(unittest.TestCase):
    def test_diagnostics_guard_opens_only_readonly_connections(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root).resolve() / 'deletions.sqlite'
            namespace = '11111111-1111-4111-8111-111111111111'
            journal = OriginalDeletionJournal.initialize(path, namespace)
            expected = journal.head()
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            connect, uris = sqlite3.connect, []
            def recording(database, **kwargs):
                uris.append(database)
                return connect(database, **kwargs)
            with patch.object(cli.sqlite3, 'connect', side_effect=recording):
                guard = cli.deletion_guard(path, namespace)
                self.assertEqual(guard.head(), expected)
                with guard._connect() as db:
                    with self.assertRaises(sqlite3.OperationalError):
                        db.execute('CREATE TABLE forbidden(id)')
            self.assertTrue(uris)
            self.assertTrue(all(uri.endswith('?mode=ro') for uri in uris))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)


if __name__ == '__main__':
    unittest.main()

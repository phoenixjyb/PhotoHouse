"""Offline CLI guards for private assistant workspace preparation."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

import prepare_assistant_workspace as cli  # noqa: E402
from app.access import assistant_workspace_store as store  # noqa: E402


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def invoke(*args):
    output = io.StringIO()
    with redirect_stdout(output):
        code = cli.main(list(args))
    return code, json.loads(output.getvalue())


class PrepareAssistantWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / 'workspace.sqlite'

    def make_v1(self, path=None):
        path = path or self.path
        with sqlite3.connect(path) as db:
            db.executescript(store._V1_SCHEMA_SQL)
            db.execute(
                'INSERT INTO threads VALUES(?,?,?,?,?,?,?)',
                ('thread-secret-id', 'account-secret', 'library-secret', 100, 200,
                 9999999999, 1),
            )
            db.execute(
                'INSERT INTO exchanges VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                ('exchange-secret-id', 'thread-secret-id', 'account-secret',
                 'library-secret', str(uuid.uuid4()), 1, 100, 9999999999,
                 'private input text', 'private reply text', '[]', '[]', 'f' * 64),
            )
        return path

    def test_initialize_is_exclusive_and_missing_files_are_not_born_on_refusal(self):
        missing = self.root / 'missing.sqlite'
        code, result = invoke('--inspect', str(missing))
        self.assertEqual(code, 2)
        self.assertFalse(missing.exists())
        self.assertEqual(result['code'], 'invalid_path')

        code, result = invoke('--upgrade-v1', str(missing))
        self.assertEqual(code, 2)
        self.assertFalse(missing.exists())
        self.assertEqual(result['code'], 'invalid_path')

        code, result = invoke('--initialize', str(self.path))
        self.assertEqual((code, result['outcome'], result['schema_version']),
                         (0, 'created', 2))
        self.assertFalse(result['feature_activated'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)

        empty = self.root / 'already-empty.sqlite'
        empty.touch()
        before = digest(empty)
        code, result = invoke('--initialize', str(empty))
        self.assertEqual(code, 2)
        self.assertEqual(result['code'], 'target_exists')
        self.assertEqual(digest(empty), before)

    def test_upgrade_preserves_existing_v1_history_and_returns_only_safe_metadata(self):
        self.make_v1()
        code, result = invoke('--upgrade-v1', str(self.path))
        self.assertEqual(code, 0)
        self.assertEqual(result['schema_version'], 2)
        self.assertTrue(result['operator_fence_and_backup_required'])
        self.assertFalse(result['feature_activated'])
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT count(*) FROM exchanges').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT input_text,reply FROM exchanges').fetchone(),
                             ('private input text', 'private reply text'))

    def test_wrong_main_database_identity_is_refused_without_exposing_details(self):
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE ordinary_application_data(value TEXT)')
            db.execute("INSERT INTO ordinary_application_data VALUES('secret-row')")
        before = digest(self.path)
        code, result = invoke('--upgrade-v1', str(self.path))
        self.assertEqual(code, 2)
        self.assertEqual(result['code'], 'invalid_store')
        self.assertEqual(digest(self.path), before)
        self.assertNotIn('secret-row', json.dumps(result))
        self.assertNotIn(str(self.path), json.dumps(result))

    def test_inspect_is_read_only_and_exposes_only_aggregate_metadata(self):
        workspace = store.initialize_v2(self.path, clock=lambda: 1234)
        thread_id = workspace.create_thread('secret-account', 'secret-library')['thread_id']
        workspace.append_exchange(
            'secret-account', 'secret-library', thread_id, str(uuid.uuid4()), 0,
            input_text='secret-input-text', reply='secret-reply-text', cards=[], receipts=[],
        )
        workspace.update_preferences('secret-account', 0, {'locale': 'en'})
        before = digest(self.path)

        code, result = invoke('--inspect', str(self.path))

        self.assertEqual(code, 0)
        metadata = result['metadata']
        self.assertEqual(metadata['schema_version'], 2)
        self.assertEqual(metadata['application_id'], store.APPLICATION_ID)
        self.assertEqual(metadata['threads'], 1)
        self.assertEqual(metadata['exchanges'], 1)
        self.assertEqual(metadata['turns'], 0)
        self.assertEqual(metadata['preferences'], 1)
        rendered = json.dumps(result)
        for secret in ('secret-account', 'secret-library', thread_id,
                       'secret-input-text', 'secret-reply-text', str(self.path)):
            self.assertNotIn(secret, rendered)
        self.assertEqual(digest(self.path), before)
        self.assertFalse(Path(str(self.path) + '-wal').exists())
        self.assertFalse(Path(str(self.path) + '-shm').exists())

    def test_path_guards_reject_symlinks_query_syntax_and_uri_forms(self):
        self.path.touch()
        link = self.root / 'link.sqlite'
        link.symlink_to(self.path)
        for candidate in (str(link), str(self.path) + '?mode=ro',
                          'file:' + str(self.path)):
            with self.subTest(candidate=candidate):
                code, result = invoke('--inspect', candidate)
                self.assertEqual(code, 2)
                self.assertIn(result['code'], ('invalid_path', 'invalid_store'))

    def test_modes_are_mutually_exclusive_and_malformed_invocations_are_safe(self):
        code, result = invoke('--inspect', str(self.path), '--initialize', str(self.path))
        self.assertEqual(code, 2)
        self.assertEqual(result['code'], 'invalid_arguments')
        self.assertNotIn(str(self.path), json.dumps(result))


if __name__ == '__main__':
    unittest.main()

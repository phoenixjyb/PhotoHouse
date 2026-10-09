"""CLI contract and no-network preflight checks against synthetic SQLite only."""

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))

import test_memory_books as fixture
import run_memory_worker as worker
from app.access.memory_jobs import MemoryJobs
from app.access.memory_contributions import MemoryContributions
from app.access.service import AccessService
from app.access.original_deletions import OriginalDeletionJournal


class MemoryWorkerLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.MemoryBookTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.MemoryBookTests.tearDownClass()

    def setUp(self):
        self.f = fixture.MemoryBookTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.library = self.f.library_fixture
        self.story_id = self.f.story('Launcher fixture')
        self.tmp = tempfile.TemporaryDirectory(prefix='memory-worker-cli-')
        self.addCleanup(self.tmp.cleanup)
        self.config_path = Path(self.tmp.name).resolve() / 'worker.json'
        self.journal_path = Path(self.tmp.name).resolve() / 'deletions.sqlite'
        self.namespace = str(uuid.uuid4())
        self.journal = OriginalDeletionJournal.initialize(self.journal_path, self.namespace)
        with self.library.connection() as db:
            self.journal.bind(db)
        self.config = {
            'database': str(self.library.path.resolve()), 'mode': 'narrative',
            'ollama_url': 'http://127.0.0.1:11434', 'ollama_model': 'fixture-model',
            'asr_url': None, 'asr_model': None, 'asr_token': None,
            'original_deletion_journal_path': str(self.journal_path),
            'original_deletion_namespace': self.namespace,
        }
        self.write_config()

    def write_config(self, value=None):
        self.config_path.write_text(json.dumps(value or self.config), encoding='utf-8')

    def queue_job(self):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            return MemoryJobs(access).narrative(
                self.f.owner, 'family-a', 'story', self.story_id, '1',
                str(uuid.uuid4()), 'Draft carefully.')

    def cli(self, *args):
        output = io.StringIO()
        with redirect_stdout(output):
            code = worker.main(['--config', str(self.config_path), *args])
        return code, output.getvalue()

    @staticmethod
    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def test_preflight_is_read_only_and_constructs_explicit_provider_without_http(self):
        before = self.digest(self.library.path)
        with patch('httpx.Client', side_effect=AssertionError('network forbidden')) as client:
            code, output = self.cli('--preflight')
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertEqual(report, {'status': 'ready', 'mode': 'narrative',
                                  'schema_valid': True, 'foreign_keys_valid': True})
        client.assert_not_called()

    def test_f7_worker_preflight_remains_compatible_with_a_bound_journal(self):
        with self.library.connection() as db:
            db.execute('DROP TABLE access_memory_contribution_refs')
            db.execute("UPDATE alembic_version SET version_num='f7c3a9d2e614'")
            db.commit()
        before=self.digest(self.library.path)
        with patch('httpx.Client',side_effect=AssertionError('network forbidden')):
            code, output=self.cli('--preflight')
        self.assertEqual(code,0)
        self.assertTrue(json.loads(output)['schema_valid'])
        self.assertEqual(self.digest(self.library.path),before)
        self.assertEqual(self.digest(self.library.path), before)

    def test_preflight_does_not_create_missing_database_and_rejects_old_schema(self):
        missing = Path(self.tmp.name) / 'missing.sqlite'
        self.write_config(self.config | {'database': str(missing)})
        code, output = self.cli('--preflight')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['status'], 'unavailable')
        self.assertFalse(missing.exists())

        self.write_config()
        self.library.mutate("UPDATE alembic_version SET version_num='e6b2f8a1c903'")
        code, output = self.cli('--preflight')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['status'], 'unavailable')

    def test_contribution_config_constructs_local_adapters_without_contacting_them(self):
        self.write_config(self.config | {
            'mode': 'contributions',
            'asr_url': 'http://localhost:9081/transcribe',
            'asr_model': 'fixture-asr',
            'asr_token': None,
        })
        with patch('httpx.Client', side_effect=AssertionError('network forbidden')) as client:
            code, output = self.cli('--preflight')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['status'], 'ready')
        client.assert_not_called()

    def test_editorial_config_is_explicit_boolean_and_requires_native_b1_shape(self):
        self.write_config(self.config | {'memory_editorial_enabled': False})
        self.assertFalse(worker.read_config(self.config_path)['memory_editorial_enabled'])
        self.write_config(self.config | {'memory_editorial_enabled': True})
        with patch('httpx.Client', side_effect=AssertionError('network forbidden')):
            code, output = self.cli('--preflight')
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output)['status'], 'ready')
        self.library.mutate("UPDATE alembic_version SET version_num='a0c9d2e4f817'")
        before = self.digest(self.library.path)
        with patch('httpx.Client', side_effect=AssertionError('network forbidden')) as client:
            code, output = self.cli('--preflight')
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output)['status'], 'unavailable')
        self.assertEqual(self.digest(self.library.path), before)
        client.assert_not_called()
        for invalid in ('true', 1, None, [], {}):
            with self.subTest(value=invalid):
                self.write_config(self.config | {'memory_editorial_enabled': invalid})
                with self.assertRaises(worker.WorkerConfigurationError):
                    worker.read_config(self.config_path)
        self.write_config(self.config | {'mode': 'contributions', 'memory_editorial_enabled': True,
            'asr_url': 'http://localhost:9081/transcribe', 'asr_model': 'fixture-asr'})
        with self.assertRaises(worker.WorkerConfigurationError):
            worker.read_config(self.config_path)

    def test_closed_config_duplicate_keys_and_symlink_are_rejected_without_values(self):
        self.write_config(self.config | {'unexpected_secret': 'do-not-print'})
        code, output = self.cli('--preflight')
        self.assertEqual(code, 2)
        self.assertNotIn('do-not-print', output)

        self.config_path.write_bytes(b' ' * (worker.MAX_CONFIG_BYTES + 1))
        code, output = self.cli('--preflight')
        self.assertEqual(code, 2)
        self.assertNotIn(' ', output)

        self.config_path.write_text(
            json.dumps(self.config)[:-1] + ',"mode":"contributions"}', encoding='utf-8')
        code, output = self.cli('--preflight')
        self.assertEqual(code, 2)
        self.assertNotIn('contributions', output)

        real = Path(self.tmp.name) / 'real.json'
        real.write_text(json.dumps(self.config), encoding='utf-8')
        link = Path(self.tmp.name) / 'linked.json'
        link.symlink_to(real)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(worker.main(['--config', str(link), '--preflight']), 2)

    def test_once_claims_only_one_job_and_report_contains_no_job_or_source_data(self):
        queued = self.queue_job()

        class FakeNarrator:
            def __init__(self, *args, **kwargs):
                pass

            def narrative(self, bundle):
                chapter = bundle['chapters'][0]
                return {'version': 1, 'title': 'Synthetic draft',
                        'chapters': [{'id': chapter['id'], 'narration': 'Synthetic output.',
                                      'source_ids': chapter['evidence_ids'][:1]}],
                        'questions': [], 'needs_review': True}

        with patch.object(worker, 'LocalMemoryNarrator', FakeNarrator), \
                patch('httpx.Client', side_effect=AssertionError('network forbidden')) as client:
            code, output = self.cli('--once')
        self.assertEqual(code, 0)
        report = json.loads(output)
        self.assertEqual(report, {'status': 'complete', 'mode': 'narrative',
                                  'processed': 1, 'states': {'ready': 1}})
        self.assertNotIn(queued['id'], output)
        self.assertNotIn('Synthetic output.', output)
        client.assert_not_called()
        with self.library.connection() as db:
            rows = db.execute('SELECT state FROM access_memory_jobs ORDER BY created_at,id').fetchall()
        self.assertEqual(sum(row[0] == 'ready' for row in rows), 1)

    def test_bounded_options_are_required_and_capped(self):
        for args in (('--max-items', '1'), ('--max-items', '33', '--max-seconds', '10'),
                     ('--max-items', '1', '--max-seconds', '1801'),
                     ('--once', '--max-seconds', '10')):
            with self.subTest(args=args), redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    worker.main(['--config', str(self.config_path), *args])
            self.assertEqual(caught.exception.code, 2)

    def test_preflight_rejects_cross_library_story_conversation_job_and_book_targets(self):
        foreign_story = 'foreign-story-' + str(uuid.uuid4())
        foreign_book = 'foreign-book-' + str(uuid.uuid4())
        with self.library.connection() as db:
            foreign_owner = db.execute("""SELECT account_id FROM access_memberships
                WHERE library_id='family-b' AND role='owner' LIMIT 1""").fetchone()[0]
            db.execute('''INSERT INTO access_memory_stories
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES(?,'family-b',?,1,'{}',?,?)''',
                (foreign_story, foreign_owner, self.library.now, self.library.now))
            db.execute('''INSERT INTO access_memory_books
                (id,library_id,author_id,revision,content,created_at,updated_at)
                VALUES(?,'family-b',?,1,'{}',?,?)''',
                (foreign_book, foreign_owner, self.library.now, self.library.now))
            db.commit()
            access = AccessService(db, clock=lambda: self.library.now)
            contribution = MemoryContributions(access).create(self.f.member, 'family-a',
                self.story_id, {'kind': 'text', 'text': 'Synthetic text', 'language': 'en',
                    'byline': 'Synthetic', 'consent': '0', 'chapter_id': '',
                    'revision': '1', 'mutation_id': str(uuid.uuid4())})
            conversation = MemoryJobs(access).start(self.f.member, 'family-a', 'story',
                self.story_id, str(uuid.uuid4()))
            chat_job = MemoryJobs(access).send(self.f.member, 'family-a', conversation['id'],
                '1', str(uuid.uuid4()), 'Synthetic question.')
            narrative_job = MemoryJobs(access).narrative(self.f.owner, 'family-a', 'story',
                self.story_id, '1', str(uuid.uuid4()), '')

            # IDs remain valid FKs, but their target parents belong to another library.
            db.execute('UPDATE access_memory_contributions SET story_id=? WHERE id=?',
                       (foreign_story, contribution['id']))
            db.execute('UPDATE access_memory_conversations SET story_id=? WHERE id=?',
                       (foreign_story, conversation['id']))
            db.execute('UPDATE access_memory_jobs SET story_id=? WHERE id=?',
                       (foreign_story, chat_job['id']))
            db.execute('UPDATE access_memory_jobs SET story_id=NULL,book_id=? WHERE id=?',
                       (foreign_book, narrative_job['id']))
            db.execute('UPDATE access_memory_conversations SET story_id=NULL,book_id=? WHERE id=?',
                       (foreign_book, conversation['id']))
            db.commit()
            self.assertIsNone(db.execute('PRAGMA foreign_key_check').fetchone())

        code, output = self.cli('--preflight')
        self.assertEqual(code, 2)
        report = json.loads(output)
        self.assertEqual(report['status'], 'unavailable')
        self.assertNotIn(foreign_story, output)
        self.assertNotIn(foreign_book, output)


if __name__ == '__main__':
    unittest.main()

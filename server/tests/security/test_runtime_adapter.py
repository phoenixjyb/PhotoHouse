"""Explicit adapter exercised only with temporary synthetic files and real ASGI."""
from contextlib import closing
import importlib
from pathlib import Path
import sqlite3
import socket
import tempfile
import unittest
import uuid
from unittest.mock import patch

import test_library_reads as library_fixture
from app.access.runtime import EDITORIAL_REVISION, EDITION_REVISION, ExistingDatabase, RuntimeConfiguration, RuntimeUnavailable, REQUIRED_REVISION
from app.access.family_note_identity_schema import IDENTITY_REVISION, IDENTITY_TABLES, sqlite_family_note_identity_contract
from app.main import create_app
from fastapi.testclient import TestClient
from anyio.from_thread import start_blocking_portal
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine
from app.access.bootstrap import bootstrap_owner
from app.access.service import AccessService
from test_orm_migrations import config
from test_access_foundation import OWNER, MEMBER, PASSWORD, NOW


class RuntimeAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library_fixture.LibraryReadTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        library_fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        directory=tempfile.TemporaryDirectory(prefix='photohouse-runtime-adapter-')
        self.addCleanup(directory.cleanup)
        self.root=Path(directory.name).resolve()
        self.path=self.root/'synthetic # database.sqlite'
        with closing(sqlite3.connect(self.path)) as db:
            library_fixture.LibraryReadTests.template.backup(db)
        self.originals,self.derived=self.root/'originals',self.root/'derived'
        self.originals.mkdir();self.derived.mkdir()
        self.settings=RuntimeConfiguration(self.path,'https://photohouse.test',(self.originals,),self.derived)
        self.app=self.settings.build_app(clock=lambda:NOW)
        # Windows constructs an internal socket pair when its event loop starts.
        # Initialize only that test transport before denying all application I/O;
        # every client below reuses the portal while the guards remain active.
        self.portal=self.enterContext(start_blocking_portal())
        self.client=self.new_client(self.app,base_url='https://photohouse.test',client=('192.0.2.40',23456))
        self.client.headers['Sec-Fetch-Site'] = 'same-origin'
        self.addCleanup(self.client.close)
        for target in ('socket.socket.connect','socket.socket.bind','subprocess.Popen','os.system'):
            guard=patch(target,side_effect=AssertionError('External I/O forbidden'))
            guard.start();self.addCleanup(guard.stop)

    def new_client(self, app, **kwargs):
        client=TestClient(app, **kwargs)
        client.portal=self.portal
        return client

    def test_application_socket_operations_remain_forbidden(self):
        with socket.socket() as connection:
            for operation in (connection.bind, connection.connect):
                with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                    operation(('127.0.0.1', 0))
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,200)

    def headers(self):
        return {'Authorization':'Bearer '+library_fixture.LibraryReadTests.member_token}

    def mutate(self,sql,args=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(sql,args);db.commit()

    def test_title_provider_build_is_explicit_and_never_runs_inference_at_startup(self):
        from dataclasses import replace
        from app.access.story_titles import LocalStoryTitleSuggester
        with patch('app.access.story_titles.LocalStoryTitleSuggester', wraps=LocalStoryTitleSuggester) as adapter, \
             patch('httpx.Client', side_effect=AssertionError('provider construction forbidden')):
            disabled = self.settings.build_app(clock=lambda: NOW)
            self.assertIsNone(disabled.state.story_title_suggester)
            adapter.assert_not_called()
            enabled = replace(self.settings, story_title_suggestions_enabled=True,
                story_title_url='http://localhost:19002', story_title_model='synthetic-titles',
                story_title_timeout_seconds=7).build_app(clock=lambda: NOW)
            adapter.assert_called_once_with(url='http://localhost:19002', model='synthetic-titles', timeout=7)
        self.assertEqual(enabled.state.story_title_suggester.timeout, 7)
        self.assertEqual(enabled.state.story_title_suggester.model, 'synthetic-titles')
        self.assertFalse(enabled.state.assistant_enabled)
        self.assertFalse(enabled.state.memory_generation_enabled)

    def test_runtime_title_provider_refuses_invalid_opt_in_and_configuration(self):
        from dataclasses import replace
        valid = dict(story_title_suggestions_enabled=True, story_title_url='http://localhost:19002',
                     story_title_model='synthetic')
        invalid = [dict(story_title_suggestions_enabled=False), dict(story_title_suggestions_enabled=1),
                   dict(story_title_url=None), dict(story_title_model=None),
                   dict(story_title_url='http://192.0.2.1:19002'), dict(story_title_model=' ')]
        invalid += [dict(story_title_timeout_seconds=t) for t in (0, True, 31, float('nan'), float('inf'), '30')]
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.settings, **(valid | change)).build_app(clock=lambda: NOW)

    def test_real_adapter_login_and_scoped_reads_use_existing_migrated_database(self):
        response=self.client.post('/auth/login',json={'phone':MEMBER,'password':PASSWORD,'transport':'native'})
        self.assertEqual(response.status_code,200)
        headers={'Authorization':'Bearer '+response.json()['access_token']}
        response=self.client.get('/assets?library=family-a',headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['total'],2)
        self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertNotIn(str(self.path),response.text)

    def test_related_media_reads_actual_a0_without_generation_or_schema_changes(self):
        # Build the actual older schema, rather than relabelling a head database.
        path = self.root / 'a0-related.sqlite'
        engine = create_engine('sqlite:///' + str(path))
        try:
            with engine.begin() as connection:
                cfg = config(); cfg.attributes['connection'] = connection
                command.upgrade(cfg, REQUIRED_REVISION)
        finally:
            engine.dispose()
        with closing(sqlite3.connect(path)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            bootstrap_owner(db, phone=OWNER, password=PASSWORD, library_id='family-a')
            token = AccessService(db, clock=lambda: NOW).login(OWNER, PASSWORD)
            for asset_id, mime in ((101, 'image/jpeg'), (102, 'video/mp4')):
                db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at)
                    VALUES (?,?,?,'active',?,'2026-01-01')''',
                    (asset_id, f'private-synthetic/{asset_id}', f'private-hash-{asset_id}', mime))
                db.execute('INSERT INTO access_asset_libraries VALUES (?,?)', (asset_id, 'family-a'))
            db.commit()
            before = list(db.iterdump())
        settings = RuntimeConfiguration(path, 'https://photohouse.test', (self.originals,), self.derived)
        self.assertFalse(settings.memory_generation_enabled)
        self.assertFalse(settings.memory_editorial_enabled)
        self.assertFalse(settings.memory_editions_enabled)
        with closing(self.new_client(settings.build_app(clock=lambda: NOW), base_url='https://photohouse.test',
                        client=('192.0.2.40', 23456))) as client:
            response = client.post('/story-workspace/related-media?library=family-a',
                                   json={'asset_ids': '101', 'before_id': ''},
                                   headers={'Authorization': 'Bearer ' + token, 'Sec-Fetch-Site': 'same-origin'})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual([item['id'] for item in response.json()['items']], ['102'])
        self.assertEqual(response.json()['items'][0]['kind'], 'video')
        self.assertTrue(response.json()['needs_review'])
        with closing(sqlite3.connect(path)) as db:
            self.assertEqual(db.execute('SELECT version_num FROM alembic_version').fetchall(),
                             [(REQUIRED_REVISION,)])
            self.assertEqual(list(db.iterdump()), before)

    def test_import_and_construction_open_no_storage_or_runtime_configuration(self):
        with patch('sqlite3.connect',side_effect=AssertionError('Connection during build')), \
             patch('pathlib.Path.lstat',side_effect=AssertionError('Filesystem during build')), \
             patch.dict('os.environ',{'DATABASE_URL':'sqlite:///must-never-be-opened.sqlite'}):
            import app.access.runtime as runtime
            # ``reload`` mutates the existing module object in place.  Restore
            # the identity-bearing classes afterwards so tests that imported
            # RuntimeUnavailable/ExistingDatabase keep matching the globals
            # used by their methods.  Without this, the result depends on
            # unittest's module order: a later stale-database check sees a
            # freshly reloaded exception class and reports an unexpected error.
            original = {name: getattr(runtime, name) for name in
                        ('ExistingDatabase', 'RuntimeConfiguration', 'RuntimeUnavailable',
                         'REQUIRED_REVISION')}
            self.addCleanup(lambda: [setattr(runtime, name, value)
                                     for name, value in original.items()])
            importlib.reload(runtime)
            self.settings.build_app()
            self.assertIsNone(create_app().state.access_runtime)

    def test_missing_database_never_creates_file_or_schema(self):
        self.path.unlink()
        response=self.client.get('/assets?library=family-a',headers=self.headers())
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json(),{'detail':'Access unavailable'})
        self.assertFalse(self.path.exists())
        self.assertEqual(self.client.get('/ui').status_code,200)

    def test_old_or_multiple_revision_and_missing_access_table_fail_closed(self):
        self.mutate("UPDATE alembic_version SET version_num='f4c1a8d2e703'")
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        self.mutate('UPDATE alembic_version SET version_num=?',(REQUIRED_REVISION,))
        self.mutate("INSERT INTO alembic_version VALUES ('synthetic-other-head')")
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        self.mutate("DELETE FROM alembic_version WHERE version_num='synthetic-other-head'")
        self.mutate('DROP TABLE access_audit')
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertNotIn('access_audit',{r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")})

    def test_invalid_admission_key_is_not_regenerated(self):
        self.mutate('DELETE FROM access_admission_key')
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_admission_key').fetchone()[0],0)

    def test_wrong_type_admission_key_is_refused_without_rotation(self):
        self.mutate('UPDATE access_admission_key SET secret=?', ('x'*32,))
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT secret FROM access_admission_key').fetchone()[0],'x'*32)

    def test_symlink_directory_and_corrupt_database_are_refused_without_disclosure(self):
        moved=self.root/'actual.sqlite';self.path.rename(moved);self.path.symlink_to(moved)
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        self.path.unlink();self.path.mkdir()
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        self.path.rmdir();self.path.write_bytes(b'synthetic-not-a-database')
        response=self.client.get('/auth/session',headers=self.headers())
        self.assertEqual(response.status_code,503)
        self.assertNotIn('database.sqlite',response.text)
        self.assertEqual(self.path.read_bytes(),b'synthetic-not-a-database')

    def test_connections_are_fresh_enforce_foreign_keys_and_rollback_uncommitted_work(self):
        factory=ExistingDatabase(self.path)
        with factory() as first:
            self.assertEqual(first.execute('PRAGMA foreign_keys').fetchone()[0],1)
            self.assertEqual(first.execute('PRAGMA trusted_schema').fetchone()[0],0)
            first.execute("UPDATE access_libraries SET state='closed'")
        with self.assertRaises(sqlite3.ProgrammingError):first.execute('SELECT 1')
        with factory() as second:
            self.assertIsNot(first,second)
            self.assertEqual(second.execute('SELECT DISTINCT state FROM access_libraries').fetchall(),[('active',)])
            with self.assertRaises(sqlite3.IntegrityError):
                second.execute("INSERT INTO access_asset_libraries VALUES (123456,'family-a')")

    def test_failed_domain_call_closes_and_rolls_back_connection(self):
        factory=ExistingDatabase(self.path)
        with self.assertRaisesRegex(RuntimeError,'synthetic'):
            with factory() as db:
                db.execute("UPDATE access_libraries SET state='closed'")
                raise RuntimeError('synthetic')
        with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
        self.assertEqual(self.client.get('/assets?library=family-a',headers=self.headers()).status_code,200)

    def test_adapter_revision_pin_matches_actual_migration_head(self):
        self.assertEqual(ScriptDirectory.from_config(config()).get_heads(),[IDENTITY_REVISION])
        for invalid in (Path('relative.sqlite'),':memory:'):
            with self.assertRaises(ValueError):ExistingDatabase(invalid)
        for timeout in (0,-1,11,float('nan'),True):
            with self.assertRaises(ValueError):ExistingDatabase(self.path,timeout=timeout)

    def test_c2_database_without_identity_schema_remains_compatible_without_repair(self):
        for kind, name, _ddl in sqlite_family_note_identity_contract():
            if kind == 'trigger':
                self.mutate('DROP TRIGGER ' + name)
        for table in ('access_memory_book_edition_family_notes', 'access_family_note_scopes',
                      'access_family_note_identities'):
            self.mutate('DROP TABLE ' + table)
        self.mutate('UPDATE alembic_version SET version_num=?', (EDITION_REVISION,))
        self.assertEqual(self.client.get('/auth/session', headers=self.headers()).status_code, 200)
        with ExistingDatabase(self.path)() as db:
            from app.access.stories import Stories
            note = Stories(AccessService(db, clock=lambda: NOW)).save(
                library_fixture.LibraryReadTests.owner_token, 'family-a',
                {'title': 'Legacy-compatible note', 'text': 'Synthetic source', 'language': 'en',
                 'byline': '', 'mutation_id': str(uuid.uuid4())}, asset_id=101)
            self.assertEqual(note['revision'], 1)
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            self.assertFalse(IDENTITY_TABLES & tables)

    def test_identity_revision_requires_complete_schema_without_repair(self):
        self.mutate('DROP TABLE access_memory_book_edition_family_notes')
        response = self.client.get('/auth/session', headers=self.headers())
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('family_note', response.text)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertFalse(db.execute("SELECT 1 FROM sqlite_master WHERE name='access_memory_book_edition_family_notes'").fetchall())

    def test_identity_revision_refuses_missing_immutability_trigger(self):
        self.mutate('DROP TRIGGER trg_family_note_no_reuse')
        self.assertEqual(self.client.get('/auth/session', headers=self.headers()).status_code, 503)

    def test_f7_adapter_remains_compatible_without_the_new_reference_table(self):
        self.mutate('DROP TABLE access_memory_contribution_refs')
        self.mutate("UPDATE alembic_version SET version_num='f7c3a9d2e614'")
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,200)
        self.assertEqual(self.client.get('/memory-stories?library=family-a',headers=self.headers()).status_code,200)

    def test_new_revision_requires_reference_table_without_recreating_it(self):
        self.mutate('DROP TABLE access_memory_contribution_refs')
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertNotIn('access_memory_contribution_refs',
                {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")})

    def test_bound_f7_primary_still_requires_its_external_deletion_journal(self):
        self.mutate('DROP TABLE access_memory_contribution_refs')
        self.mutate("UPDATE alembic_version SET version_num='f7c3a9d2e614'")
        self.mutate('''INSERT INTO access_original_deletion_state
            (id,namespace,applied_seq,applied_digest) VALUES (1,?,0,?)''',
            ('11111111-1111-4111-8111-111111111111','0'*64))
        self.assertEqual(self.client.get('/auth/session',headers=self.headers()).status_code,503)

    def test_http_and_host_headers_cannot_supply_configuration_or_proxy_trust(self):
        with closing(self.new_client(self.app,base_url='http://photohouse.test')) as client:
            response=client.get('/assets?library=family-a',headers={**self.headers(),'X-Forwarded-Proto':'https'})
            self.assertEqual(response.status_code,400)
        self.assertEqual(self.client.get('/assets?library=family-a',headers={**self.headers(),'Host':'evil.test'}).status_code,400)


if __name__=='__main__':unittest.main()

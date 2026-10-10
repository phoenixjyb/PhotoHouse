"""Synthetic security checks for optional persistent memory groups."""
import json
from pathlib import Path
import sys
import unittest
import uuid

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

import test_memory_book_edition_migration as edition_fixture
import test_memory_books as book_fixture
import test_memory_book_editorial_migration as editorial_fixture
import test_orm_migrations as migration_fixture
from app import db as models
from app.access.memory_group_schema import (REVISION_TABLE, TABLE,
    verify_memory_group_schema)
from app.access.memory_groups import MemoryGroups
from app.access.metadata import migration_metadata
from app.access.service import AccessDenied, AccessService
from app.access.stories import Stories
from app.access.transport import TransportError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

REVISION = 'e7c1a9d5b304'
DOWN_REVISION = 'd1f6a8c3e920'
GROUP_TABLES = {TABLE, REVISION_TABLE}
NOTE_ID = str(uuid.UUID(int=8891))


class MemoryGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        book_fixture.MemoryBookTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        book_fixture.MemoryBookTests.tearDownClass()

    def setUp(self):
        self.base = book_fixture.MemoryBookTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.f = self.base.library_fixture
        self.owner = self.f.owner_token
        self.member = self.f.member_token
        self._install_schema()

    def _install_schema(self):
        metadata = migration_metadata(models.Base.metadata)
        groups, revisions = metadata.tables[TABLE], metadata.tables[REVISION_TABLE]
        with self.f.connection() as db:
            present = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            existing = GROUP_TABLES & present
            if existing and existing != GROUP_TABLES:
                raise AssertionError('optional memory group schema is partial')
            if not existing:
                engine = create_engine(f'sqlite:///{self.f.path}')
                try:
                    groups.create(engine)
                    revisions.create(engine)
                finally:
                    engine.dispose()
        with self.f.connection() as db:
            self.assertTrue(verify_memory_group_schema(db))

    def domain(self, method, token, *args, library='family-a'):
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            return getattr(MemoryGroups(access), method)(token, library, *args)

    def note(self, *, asset=101, title='Before edit', text='Current family words'):
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            return Stories(access).save(self.owner, 'family-a', {
                'title': title, 'text': text, 'language': 'en', 'byline': 'A parent',
                'mutation_id': str(uuid.uuid4()),
            }, asset_id=asset)

    def edit_note(self, note, *, revision, title, text, delete=False):
        body = {'revision': str(revision), 'mutation_id': str(uuid.uuid4())}
        if not delete:
            body.update(title=title, text=text, language='en', byline='A parent')
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            return Stories(access).save(self.owner, 'family-a', body,
                                        story_id=note['id'], delete=delete)

    @staticmethod
    def body(*, assets='101,102', excluded='', sources='', theme='everyday',
             revision='0', mutation=None):
        return {
            'asset_ids': assets,
            'excluded_asset_ids': excluded,
            'source_story_ids': sources,
            'theme': theme,
            'revision': revision,
            'mutation_id': mutation or str(uuid.uuid4()),
        }

    def save(self, token, body, ident=None, *, library='family-a'):
        return self.domain('save', token, body, ident, library=library)

    def test_optional_schema_is_exact_and_absence_fails_closed(self):
        with self.f.connection() as db:
            db.execute(f'DROP TABLE {REVISION_TABLE}')
            db.execute(f'DROP TABLE {TABLE}')
        with self.assertRaises(TransportError) as unavailable:
            self.domain('list_for_asset', self.owner, 101)
        self.assertEqual(unavailable.exception.status, 503)
        self._install_schema()
        with self.f.connection() as db:
            db.execute(f'ALTER TABLE {TABLE} ADD COLUMN unexpected TEXT')
            self.assertFalse(verify_memory_group_schema(db))
        with self.assertRaises(TransportError) as malformed:
            self.domain('list_for_asset', self.owner, 101)
        self.assertEqual(malformed.exception.status, 503)

    def test_revisioned_idempotent_group_sticky_exclusions_and_id_only_storage(self):
        body = self.body(excluded='201,202')
        saved = self.save(self.owner, body)
        self.assertEqual(saved['revision'], '1')
        self.assertEqual(saved['asset_ids'], ['101', '102'])
        self.assertEqual(saved['excluded_asset_ids'], ['201', '202'])
        self.assertEqual(saved['items'][0]['thumbnail_url'].split('?')[0],
                         '/assets/101/thumbnail')
        self.assertEqual(self.save(self.owner, body), saved)
        with self.f.connection() as db:
            current = db.execute(f'SELECT * FROM {TABLE} WHERE id=?',
                                 (saved['id'],)).fetchone()
            history = db.execute(f'SELECT * FROM {REVISION_TABLE} WHERE group_id=?',
                                 (saved['id'],)).fetchone()
            columns = [row[1] for row in db.execute(f'PRAGMA table_info({REVISION_TABLE})')]
            joined = repr(tuple(current)) + repr(tuple(history))
            self.assertNotIn('title', columns)
            self.assertNotIn('text', columns)
            self.assertNotIn('Current family words', joined)
        edit = self.body(assets='101', excluded='201,202', revision='1', theme='trip')
        revised = self.save(self.owner, edit, saved['id'])
        self.assertEqual(revised['revision'], '2')
        self.assertEqual(revised['asset_ids'], ['101'])
        self.assertEqual(revised['excluded_asset_ids'], ['201', '202'])
        with self.assertRaises(TransportError) as stale:
            self.save(self.owner, self.body(revision='1'), saved['id'])
        self.assertEqual(stale.exception.status, 409)
        with self.assertRaises(TransportError) as reused:
            self.save(self.owner, {**body, 'theme': 'trip'})
        self.assertEqual(reused.exception.status, 409)

    def test_story_text_is_read_through_and_deleted_source_is_omitted(self):
        note = self.note()
        body = self.body(sources=note['id'])
        saved = self.save(self.owner, body)
        self.assertEqual(saved['source_story_ids'], [note['id']])
        self.assertEqual(saved['sources'][0]['text'], 'Current family words')
        self.edit_note(note, revision=1, title='After edit', text='Revised family words')
        reopened = self.domain('get', self.owner, saved['id'])
        self.assertEqual(reopened['sources'][0]['title'], 'After edit')
        self.assertEqual(reopened['sources'][0]['text'], 'Revised family words')
        with self.f.connection() as db:
            rows = db.execute(f'SELECT asset_ids_json,excluded_asset_ids_json,source_story_ids_json '
                f'FROM {TABLE} WHERE id=? UNION ALL SELECT asset_ids_json,excluded_asset_ids_json,'
                f'source_story_ids_json FROM {REVISION_TABLE} WHERE group_id=?',
                (saved['id'], saved['id'])).fetchall()
            self.assertNotIn('Revised family words', repr(rows))
            self.assertNotIn('After edit', repr(rows))
        self.edit_note(note, revision=2, title='', text='', delete=True)
        deleted = self.domain('get', self.owner, saved['id'])
        self.assertEqual(deleted['sources'], [])
        self.assertEqual(deleted['source_story_ids'], [])

    def test_source_note_must_be_active_scoped_and_attached_to_group_member(self):
        note = self.note()
        with self.assertRaises(TransportError) as unrelated:
            self.save(self.owner, self.body(assets='102', sources=note['id']))
        self.assertEqual(unrelated.exception.status, 422)
        foreign_headers = {'Authorization': 'Bearer ' + self.f.other_token}
        preview = self.f.client.post('/story-workspace/preview?library=family-b',
            headers=foreign_headers, json={'asset_ids': '201', 'title': 'Foreign',
                                           'theme': 'everyday', 'language': 'en'})
        self.assertEqual(preview.status_code, 200, preview.text)
        draft = preview.json()
        foreign = self.f.client.post('/memory-stories?library=family-b', headers=foreign_headers,
            json={'title': draft['title'], 'theme': 'everyday', 'language': 'en',
                  'asset_ids': '201', 'chapters': json.dumps(draft['chapters']),
                  'selection_revision': draft['selection_revision'], 'revision': '0',
                  'mutation_id': str(uuid.uuid4())}).json()['id']
        with self.assertRaises(AccessDenied):
            self.save(self.owner, self.body(assets='101', sources=foreign))

    def test_missing_or_moved_group_member_denies_get_and_hides_list(self):
        saved = self.save(self.owner, self.body())
        self.assertEqual(len(self.domain('list_for_asset', self.owner, 101)['items']), 1)
        self.f.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=102")
        with self.assertRaises(AccessDenied):
            self.domain('get', self.owner, saved['id'])
        self.assertEqual(self.domain('list_for_asset', self.owner, 101)['items'], [])

    def test_listing_bounds_candidate_scan_and_reports_uninspected_matches(self):
        # The valid group is deliberately older than 64 incomplete groups. A
        # listing may inspect only its fixed candidate window and must disclose
        # that further matching candidates were not examined.
        valid = self.save(self.owner, self.body(assets='101'))
        self.f.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=102")
        with self.f.connection() as db:
            owner_id = db.execute("SELECT account_id FROM access_memberships "
                                  "WHERE library_id='family-a' AND role='owner'").fetchone()[0]
            for ordinal in range(64):
                db.execute(f'''INSERT INTO {TABLE}
                    (id,library_id,author_id,revision,theme,asset_ids_json,
                     excluded_asset_ids_json,source_story_ids_json,created_at,updated_at)
                    VALUES(?,?,?,1,'everyday','[101,102]','[]','[]',?,?)''',
                    (str(uuid.uuid4()), 'family-a', owner_id, self.f.now,
                     self.f.now + ordinal + 100))
            db.commit()
        listed = self.domain('list_for_asset', self.owner, 101)
        self.assertEqual(listed['items'], [])
        self.assertTrue(listed['has_more'])
        self.assertEqual(valid['asset_ids'], ['101'])

    def test_viewer_can_read_but_only_author_or_owner_can_edit(self):
        saved = self.save(self.owner, self.body())
        read = self.domain('get', self.member, saved['id'])
        self.assertFalse(read['can_edit'])
        with self.assertRaises(AccessDenied):
            self.save(self.member, self.body(revision='1'), saved['id'])
        self.f.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?",
                      (self.f.member_id,))
        contributor = self.save(self.member, self.body(assets='101'))
        self.assertTrue(contributor['can_edit'])
        with self.assertRaises(AccessDenied):
            self.domain('get', self.owner, contributor['id'], library='family-b')
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                      (self.f.member_id,))
        with self.assertRaises(AccessDenied):
            self.domain('get', self.member, saved['id'])
        with self.assertRaises(AccessDenied):
            self.domain('list_for_asset', self.member, 101)


class MemoryGroupMigrationTests(unittest.TestCase):
    def setUp(self):
        self.edition = edition_fixture.MemoryBookEditionMigrationTests()
        self.edition.setUp()
        self.addCleanup(self.edition.doCleanups)
        self.migration = self.edition.migration

    def _upgrade_to_old_head_with_note(self):
        owner = self.edition._upgrade_to_b1_with_existing_editorial()
        self.migration.upgrade(DOWN_REVISION)
        with self.migration.engine.begin() as connection:
            connection.exec_driver_sql('''INSERT INTO access_stories
                (id,asset_id,library_id,author_id,revision,title,text,language,byline,
                 created_at,updated_at,deleted)
                VALUES(?,101,?,?,1,'Existing family note','Existing note text',
                       'en','Synthetic author',30,30,0)''',
                (NOTE_ID, editorial_fixture.LIBRARY, owner))
            connection.exec_driver_sql('''INSERT INTO access_story_revisions
                (story_id,revision,editor_id,mutation_id,request_digest,title,text,
                 language,byline,occurred_at,deleted)
                VALUES(?,1,?,?,?,'Existing family note','Existing note text',
                       'en','Synthetic author',30,0)''',
                (NOTE_ID, owner, str(uuid.UUID(int=8892)), 'synthetic-note-digest'))
        return owner

    def _upgrade(self):
        self.migration.upgrade(REVISION)

    def _downgrade(self):
        with self.migration.engine.begin() as connection:
            cfg = migration_fixture.config()
            cfg.attributes['connection'] = connection
            command.downgrade(cfg, DOWN_REVISION)

    @staticmethod
    def _snapshot(connection):
        return {
            table: connection.exec_driver_sql(f'SELECT * FROM {table} ORDER BY 1').all()
            for table in ('assets', 'access_asset_libraries', 'access_stories',
                          'access_story_revisions')
        }

    def _assert_downgrade_refused_with_row(self, table):
        owner = self._upgrade_to_old_head_with_note()
        self._upgrade()
        group_id = str(uuid.UUID(int=8893))
        with self.migration.engine.begin() as connection:
            if table == TABLE:
                connection.exec_driver_sql(f'''INSERT INTO {TABLE}
                    (id,library_id,author_id,revision,theme,asset_ids_json,
                     excluded_asset_ids_json,source_story_ids_json,created_at,updated_at)
                    VALUES(?,? ,?,1,'everyday','[101]','[]','[]',40,40)''',
                    (group_id, editorial_fixture.LIBRARY, owner))
            else:
                connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
                connection.exec_driver_sql(f'''INSERT INTO {REVISION_TABLE}
                    (group_id,revision,editor_id,mutation_id,request_digest,theme,
                     asset_ids_json,excluded_asset_ids_json,source_story_ids_json,occurred_at)
                    VALUES(?,1,?,?,'synthetic-digest','everyday','[101]','[]','[]',40)''',
                    (group_id, owner, str(uuid.UUID(int=8894))))
        with self.assertRaisesRegex(RuntimeError, 'Memory group records'):
            self._downgrade()
        with self.migration.engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), REVISION)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {table}').scalar_one(), 1)
            self.assertTrue(verify_memory_group_schema(
                connection.connection.driver_connection))

    def test_migration_metadata_and_upgrade_preserve_existing_note_and_media(self):
        original = set(models.Base.metadata.tables)
        combined = migration_metadata(models.Base.metadata)
        self.assertTrue(GROUP_TABLES <= set(combined.tables))
        self.assertEqual(set(models.Base.metadata.tables), original)

        self._upgrade_to_old_head_with_note()
        with self.migration.engine.connect() as connection:
            before = self._snapshot(connection)
            before_tables = set(inspect(connection).get_table_names())
        self._upgrade()
        with self.migration.engine.connect() as connection:
            after_tables = set(inspect(connection).get_table_names())
            self.assertEqual(after_tables - before_tables, GROUP_TABLES)
            self.assertEqual(before_tables - after_tables, set())
            self.assertEqual(self._snapshot(connection), before)
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), REVISION)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {TABLE}').scalar_one(), 0)
            self.assertEqual(connection.exec_driver_sql(
                f'SELECT count(*) FROM {REVISION_TABLE}').scalar_one(), 0)
            self.assertTrue(verify_memory_group_schema(
                connection.connection.driver_connection))
            context = MigrationContext.configure(connection, opts={
                'include_object': lambda obj, name, kind, _reflected, _compare_to:
                    (name in GROUP_TABLES if kind == 'table' else
                     getattr(getattr(obj, 'table', None), 'name', None) in GROUP_TABLES),
                'compare_server_default': True,
            })
            self.assertEqual(compare_metadata(context,
                migration_metadata(models.Base.metadata)), [])
            self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])

    def test_downgrade_refuses_current_group_rows(self):
        self._assert_downgrade_refused_with_row(TABLE)

    def test_downgrade_refuses_revision_rows(self):
        self._assert_downgrade_refused_with_row(REVISION_TABLE)

    def test_empty_downgrade_drops_only_group_tables(self):
        self._upgrade_to_old_head_with_note()
        with self.migration.engine.connect() as connection:
            before = self._snapshot(connection)
            before_tables = set(inspect(connection).get_table_names())
        self._upgrade()
        with self.migration.engine.connect() as connection:
            upgraded_tables = set(inspect(connection).get_table_names())
        self._downgrade()
        with self.migration.engine.connect() as connection:
            after_tables = set(inspect(connection).get_table_names())
            self.assertEqual(upgraded_tables - after_tables, GROUP_TABLES)
            self.assertEqual(after_tables - before_tables, set())
            self.assertEqual(self._snapshot(connection), before)
            self.assertEqual(connection.exec_driver_sql(
                'SELECT version_num FROM alembic_version').scalar_one(), DOWN_REVISION)


if __name__ == '__main__':
    unittest.main()

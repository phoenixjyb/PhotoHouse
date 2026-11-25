"""Fresh, revision-bound restoration for the assistant's current result set."""
from contextlib import closing
import sqlite3
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]

from app.access import assistant_workspace_transport as transport
import test_assistant_result_pages as ordinary
import test_assistant_scene_pages as scene_fixture

BASE = '/assistant/workspace/v1'


class AssistantCurrentResultTests(unittest.TestCase):
    def setUp(self):
        self.fixture = ordinary.AssistantResultPagesTests(
            'test_mixed_media_pages_preserve_order_and_do_not_create_turns_or_call_planner')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def _read(self, thread_id, request_id, revision, *, version=2, headers=None,
              query=None):
        selected = dict(self.fixture.auth)
        if headers is None and version in (2, 3, 4):
            selected['X-PhotoHouse-Search-Version'] = str(version)
        selected.update(headers or {})
        suffix = query if query is not None else (
            f'library_id=family-a&expected_revision={revision}')
        return self.fixture.client.get(
            f'{BASE}/threads/{thread_id}/requests/{request_id}/current-result?{suffix}',
            headers=selected)

    def _insert_newer(self, thread_id, revision, status):
        now = int(self.fixture.now[0])
        request_id = str(uuid.uuid4())
        if status == 'pending':
            lease_id, lease_expires, error = str(uuid.uuid4()), now + 30, None
        else:
            lease_id, lease_expires, error = None, None, 'assistant_unavailable'
        with closing(sqlite3.connect(self.fixture.workspace.path)) as db, db:
            db.execute('''INSERT INTO turn_requests(request_id,thread_id,account_id,library_id,
                status,created_at,expires_at,expected_revision,input_text,lease_id,
                lease_expires_at,revision,result_summary,error_code)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (request_id, thread_id, 'one', 'family-a', status, now, now + 3600,
                 revision, 'newer request', lease_id, lease_expires, revision, None, error))
        return request_id

    def test_current_result_envelope_revalidates_and_preserves_original_context(self):
        thread_id, request_id, turn, headers = self.fixture._turn_with_many_results(2)
        before = self.fixture.workspace.get_thread('one', 'family-a', thread_id)
        with closing(sqlite3.connect(self.fixture.workspace.path)) as db:
            request_count = db.execute(
                'SELECT COUNT(*) FROM turn_requests WHERE thread_id=?', (thread_id,)).fetchone()[0]
        response = self._read(thread_id, request_id, turn['revision'], headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertEqual(set(value), {'version', 'thread_id', 'request_id', 'status',
                                      'revision', 'recovered', 'error', 'result'})
        self.assertEqual((value['status'], value['revision'], value['recovered'], value['error']),
                         ('completed', turn['revision'], True, None))
        self.assertEqual(value['result']['context'], turn['result']['context'])
        self.assertEqual([item['id'] for item in value['result']['items']],
                         [item['id'] for item in turn['result']['items']])
        self.assertEqual(self.fixture.workspace.get_thread('one', 'family-a', thread_id), before)
        with closing(sqlite3.connect(self.fixture.workspace.path)) as db:
            self.assertEqual(db.execute(
                'SELECT COUNT(*) FROM turn_requests WHERE thread_id=?', (thread_id,)).fetchone()[0],
                request_count)

    def test_v1_and_v3_current_results_reuse_original_engine_version_without_planning(self):
        for version in (1, 3):
            with self.subTest(version=version):
                thread_id, request_id, turn, headers = self.fixture._turn_with_many_results(version)
                planner_calls = list(self.fixture.planner.calls)
                response = self._read(thread_id, request_id, turn['revision'],
                                      version=version, headers=headers)
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()['result']['version'], version)
                self.assertEqual(self.fixture.planner.calls, planner_calls)

    def test_mismatched_original_version_is_refused(self):
        thread_id, request_id, turn, _headers = self.fixture._turn_with_many_results(2)
        response = self._read(thread_id, request_id, turn['revision'], version=3)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('result', response.json())

    def test_newer_pending_or_failed_blocks_current_but_legacy_receipt_recovery_remains(self):
        for status in ('pending', 'failed'):
            with self.subTest(status=status):
                thread_id, request_id, turn, headers = self.fixture._turn_with_many_results(2)
                self._insert_newer(thread_id, turn['revision'], status)
                current = self._read(thread_id, request_id, turn['revision'], headers=headers)
                self.assertEqual(current.status_code, 409, current.text)
                self.assertNotIn('result', current.json())
                legacy = self.fixture.client.get(
                    f'{BASE}/threads/{thread_id}/requests/{request_id}?library_id=family-a',
                    headers=headers)
                self.assertEqual(legacy.status_code, 200, legacy.text)
                self.assertEqual(legacy.json()['request_id'], request_id)
                self.assertTrue(legacy.json()['recovered'])

    def test_query_requires_canonical_revision_and_exact_fields(self):
        thread_id, request_id, turn, headers = self.fixture._turn_with_many_results(2)
        invalid = (
            f'library_id=family-a&expected_revision=0{turn["revision"]}',
            f'library_id=family-a&expected_revision=+{turn["revision"]}',
            f'library_id=family-a&expected_revision={turn["revision"]}&extra=1',
            f'library_id=family-a&library_id=family-a&expected_revision={turn["revision"]}',
        )
        for query in invalid:
            with self.subTest(query=query):
                response = self._read(thread_id, request_id, turn['revision'],
                                      headers=headers, query=query)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertNotIn('result', response.json())
        unsupported = self._read(thread_id, request_id, turn['revision'],
                                 headers={'X-PhotoHouse-Search-Version': '5'})
        self.assertEqual(unsupported.status_code, 400, unsupported.text)

    def test_catalog_change_after_restore_suppresses_cards(self):
        thread_id, request_id, turn, headers = self.fixture._turn_with_many_results(2)
        original = transport._turn_result

        def restore_then_change(*args, **kwargs):
            result = original(*args, **kwargs)
            with closing(sqlite3.connect(self.fixture.database)) as db, db:
                db.execute("UPDATE assets SET status='inactive' WHERE id=1000")
            return result

        with patch.object(transport, '_turn_result', side_effect=restore_then_change):
            response = self._read(thread_id, request_id, turn['revision'], headers=headers)
        self.assertIn(response.status_code, (409, 503), response.text)
        self.assertNotIn('items', response.json())

    def test_off_page_media_metadata_change_refuses_ordinary_handoff(self):
        thread_id, request_id, turn, headers = self.fixture._turn_with_many_results(2)
        page = self.fixture._page(thread_id, request_id, turn['revision'], 2, headers=headers)
        self.assertEqual(page.status_code, 200, page.text)
        selected = page.json()['items'][0]
        old_date = selected['taken_at'][:10]
        new_date = '2026-12-15' if old_date != '2026-12-15' else '2026-11-15'
        self.fixture.update('UPDATE assets SET taken_at=? WHERE id=?', (new_date, int(selected['id'])))
        response = self._read(thread_id, request_id, turn['revision'], headers=headers)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('result', response.json())

    def test_off_page_metadata_change_refuses_v4_scene_handoff(self):
        fixture = scene_fixture.AssistantScenePagesTests(
            'test_pages_are_exact_rank_slices_and_leave_durable_first_page_unchanged')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        scene = fixture.scene
        _scope, request_id, _original = fixture._scene_result()
        page = fixture._page(request_id, 2)
        self.assertEqual(page.status_code, 200, page.text)
        selected = page.json()['items'][0]
        with closing(sqlite3.connect(scene.source.database)) as db, db:
            db.execute('UPDATE assets SET taken_at=? WHERE id=?',
                       ('2030-01-02', int(selected['id'])))
        response = scene.client.get(
            f'{BASE}/threads/{scene.thread}/requests/{request_id}/current-result'
            f'?library_id=family-a&expected_revision={fixture.scene_revision}',
            headers=scene.headers)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('result', response.json())

    def test_newer_request_inserted_during_restore_blocks_post_read(self):
        thread_id, request_id, turn, headers = self.fixture._turn_with_many_results(2)
        original = transport._turn_result

        def restore_then_insert(*args, **kwargs):
            result = original(*args, **kwargs)
            self._insert_newer(thread_id, turn['revision'], 'pending')
            return result

        with patch.object(transport, '_turn_result', side_effect=restore_then_insert):
            response = self._read(thread_id, request_id, turn['revision'], headers=headers)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('result', response.json())

    def test_membership_loss_and_wrong_library_never_release_cards(self):
        thread_id, request_id, turn, headers = self.fixture._turn_with_many_results(2)
        wrong_library = self._read(thread_id, request_id, turn['revision'], headers=headers,
                                   query=f'library_id=family-b&expected_revision={turn["revision"]}')
        self.assertIn(wrong_library.status_code, (401, 404))
        self.assertNotIn('result', wrong_library.json())

        self.fixture.update("DELETE FROM access_libraries WHERE id='family-a'")
        revoked = self._read(thread_id, request_id, turn['revision'], headers=headers)
        self.assertEqual(revoked.status_code, 401, revoked.text)
        self.assertNotIn('result', revoked.json())

    def test_v4_scene_current_result_restores_without_reencoding(self):
        fixture = scene_fixture.AssistantScenePagesTests(
            'test_pages_are_exact_rank_slices_and_leave_durable_first_page_unchanged')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        scene = fixture.scene
        _scope, request_id, original = fixture._scene_result()
        revision = fixture.scene_revision
        before_calls = list(scene.pilot.calls)
        response = scene.client.get(
            f'{BASE}/threads/{scene.thread}/requests/{request_id}/current-result'
            f'?library_id=family-a&expected_revision={revision}',
            headers=scene.headers)
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertEqual((value['status'], value['revision'], value['recovered']),
                         ('completed', revision, True))
        self.assertEqual([item['id'] for item in value['result']['items']],
                         [item['id'] for item in original['items']])
        self.assertEqual(scene.pilot.calls, before_calls)


if __name__ == '__main__':
    unittest.main()

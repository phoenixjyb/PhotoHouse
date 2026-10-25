"""Generated HTTP/store contract for opted-in scene reword-draft recovery."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]

from fastapi.testclient import TestClient
import test_assistant_scene_search as scenes
from phone_discovery_fixture import SECOND

BASE = '/assistant/workspace/v1'
SCENE_REWORD_HEADER = 'X-PhotoHouse-Scene-Reword-Version'


class AssistantSceneRewordRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = scenes.AssistantSceneSearchTests(
            'test_post_retry_and_get_recovery_keep_order_and_never_reencode')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def thread_get(self, *, headers=None, library='family-a'):
        selected = dict(self.fixture.auth)
        selected[SCENE_REWORD_HEADER] = '1'
        if headers is not None:
            selected.update(headers)
        return self.fixture.client.get(
            f'{BASE}/threads/{self.fixture.thread}?library_id={library}', headers=selected)

    def make_failed_scene(self, query='a dog not on grass'):
        self.fixture.scope()
        response = self.fixture.send(query, revision=1, scene=True)
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertEqual((value['status'], value['error'], value['revision']),
                         ('failed', 'scene_query_unsupported', 1))
        self.assertIsNone(value['result'])
        self.assertNotIn(query, response.text)
        self.assertEqual(self.fixture.pilot.calls, [])
        return value

    def _insert_newest_request(self, status, *, error_code=None, expired=False):
        request_id = str(uuid.uuid4())
        now = int(self.fixture.store.clock())
        expires_at = now - 1 if expired else now + 3600
        if status == 'pending':
            lease_id, lease_expires_at = str(uuid.uuid4()), now + 30
            result_summary = error_code = None
        elif status == 'completed':
            lease_id = lease_expires_at = error_code = None
            result_summary = '{}'
        else:
            lease_id = lease_expires_at = result_summary = None
            error_code = error_code or 'assistant_unavailable'
        with closing(sqlite3.connect(self.fixture.store.path)) as db, db:
            db.execute('''INSERT INTO turn_requests(request_id,thread_id,account_id,library_id,
                status,created_at,expires_at,expected_revision,input_text,lease_id,
                lease_expires_at,revision,result_summary,error_code)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (request_id, self.fixture.thread, 'one', 'family-a', status, now,
                 expires_at, 1, 'newer request', lease_id, lease_expires_at,
                 1, result_summary, error_code))
        return request_id

    def test_legacy_get_shape_is_unchanged_and_opt_in_projection_is_nullable(self):
        legacy = self.fixture.client.get(
            f'{BASE}/threads/{self.fixture.thread}?library_id=family-a',
            headers=self.fixture.auth)
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(set(legacy.json()), {
            'version', 'thread', 'exchanges', 'has_older_exchanges', 'latest_request_id'})

        projected = self.thread_get()
        self.assertEqual(projected.status_code, 200, projected.text)
        self.assertEqual(projected.json()['scene_reword'], None)

    def test_latest_same_second_scene_refusal_is_returned_as_draft_only(self):
        first = self.make_failed_scene('a dog not on grass')
        second = self.fixture.send('a phone not in a house', revision=1, scene=True)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()['error'], 'scene_query_unsupported')
        self.assertEqual(second.json()['revision'], 1)

        legacy = self.fixture.client.get(
            f'{BASE}/threads/{self.fixture.thread}?library_id=family-a',
            headers=self.fixture.auth)
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertNotIn('scene_reword', legacy.json())

        response = self.thread_get()
        self.assertEqual(response.status_code, 200, response.text)
        cue = response.json()['scene_reword']
        self.assertEqual(cue, {
            'version': 1,
            'request_id': second.json()['request_id'],
            'revision': response.json()['thread']['revision'],
            'query': 'a phone not in a house',
        })
        self.assertNotEqual(cue['request_id'], first['request_id'])
        self.assertEqual(set(cue), {'version', 'request_id', 'revision', 'query'})
        self.assertNotIn('filters', cue)
        self.assertNotIn('context', cue)
        self.assertNotIn('visible_ids', cue)

    def test_newest_request_status_or_expiry_suppresses_older_scene_refusal(self):
        self.make_failed_scene()
        cases = (
            ('pending', None, False),
            ('failed', 'assistant_unavailable', False),
            ('interrupted', 'turn_interrupted', False),
            ('completed', None, False),
            ('failed', 'scene_query_unsupported', True),
        )
        for status, error_code, expired in cases:
            with self.subTest(status=status, error_code=error_code, expired=expired):
                self._insert_newest_request(status, error_code=error_code, expired=expired)
                response = self.thread_get()
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIsNone(response.json()['scene_reword'])

    def test_bom_and_unicode_whitespace_only_drafts_are_hidden_but_literal_is_preserved(self):
        failed = self.make_failed_scene()
        path = self.fixture.store.path
        for blank_query in ('\ufeff', '\ufeff \u00a0\ufeff'):
            with self.subTest(query=repr(blank_query)):
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute('UPDATE turn_requests SET input_text=? WHERE request_id=?',
                               (blank_query, failed['request_id']))
                response = self.thread_get()
                self.assertEqual(response.status_code, 200, response.text)
                self.assertIsNone(response.json()['scene_reword'])

        literal = '  please keep the \ufeff symbol in this draft  '
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('UPDATE turn_requests SET input_text=? WHERE request_id=?',
                       (literal, failed['request_id']))
        response = self.thread_get()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['scene_reword']['query'], literal)

    def test_projection_header_is_strict_and_refusals_do_not_echo_query(self):
        failed = self.make_failed_scene('a dog not on grass')
        path = f'{BASE}/threads/{self.fixture.thread}?library_id=family-a'
        for headers in (
            self.fixture.auth | {'X-PhotoHouse-Search-Version': '3', SCENE_REWORD_HEADER: '1'},
            self.fixture.auth | {'X-PhotoHouse-Search-Version': '4', SCENE_REWORD_HEADER: 'true'},
            self.fixture.auth | {'X-PhotoHouse-Search-Version': '4', SCENE_REWORD_HEADER: '2'},
            self.fixture.auth | {'X-PhotoHouse-Search-Version': '4'},
        ):
            with self.subTest(headers=headers):
                response = self.fixture.client.get(path, headers=headers)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertNotIn('scene_reword', response.json())
                self.assertNotIn('a dog not on grass', response.text)

        duplicate = list(self.fixture.auth.items()) + [
            (SCENE_REWORD_HEADER, '1'), (SCENE_REWORD_HEADER, '1')]
        response = self.fixture.client.get(path, headers=duplicate)
        self.assertEqual(response.status_code, 400, response.text)
        self.assertNotIn('a dog not on grass', response.text)

        request_path = (f'{BASE}/threads/{self.fixture.thread}/requests/'
                        f'{failed["request_id"]}?library_id=family-a')
        misplaced = self.fixture.client.get(request_path, headers={
            **self.fixture.auth, SCENE_REWORD_HEADER: '1'})
        self.assertEqual(misplaced.status_code, 400, misplaced.text)
        self.assertNotIn('a dog not on grass', misplaced.text)

    def test_malformed_or_ambiguous_query_parameters_are_refused(self):
        self.make_failed_scene('a dog not on grass')
        headers = self.fixture.auth | {SCENE_REWORD_HEADER: '1'}
        paths = (
            f'{BASE}/threads/{self.fixture.thread}?library_id=family-a&library_id=family-a',
            f'{BASE}/threads/{self.fixture.thread}?library_id=family-a&extra=value',
            f'{BASE}/threads/{self.fixture.thread}?library_id=%ZZ',
        )
        for path in paths:
            with self.subTest(path=path):
                response = self.fixture.client.get(path, headers=headers)
                self.assertEqual(response.status_code, 400, response.text)
                self.assertNotIn('scene_reword', response.json())
                self.assertNotIn('a dog not on grass', response.text)

    def test_authorization_and_membership_revocation_precede_projection(self):
        self.make_failed_scene('a dog not on grass')
        path = f'{BASE}/threads/{self.fixture.thread}?library_id=family-a'
        denied = (
            self.fixture.client.get(path, headers={
                SCENE_REWORD_HEADER: '1'}),
            self.fixture.client.get(path, headers={
                'Authorization': 'Bearer ' + SECOND,
                SCENE_REWORD_HEADER: '1'}),
            self.fixture.client.get(
                f'{BASE}/threads/{self.fixture.thread}?library_id=family-b',
                headers=self.fixture.auth | {SCENE_REWORD_HEADER: '1'}),
        )
        for response in denied:
            self.assertIn(response.status_code, (401, 403, 404), response.text)
            self.assertNotIn('a dog not on grass', response.text)

        self.fixture.source.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        revoked = self.thread_get()
        self.assertIn(revoked.status_code, (401, 403, 404), revoked.text)
        self.assertNotIn('a dog not on grass', revoked.text)

    def test_source_change_keeps_projection_limited_to_the_user_draft(self):
        self.make_failed_scene('a dog not on grass')
        self.fixture.source.mutate(
            "UPDATE access_stories SET revision=2,text='changed' WHERE id='note-101'")
        response = self.thread_get()
        self.assertEqual(response.status_code, 200, response.text)
        cue = response.json()['scene_reword']
        self.assertEqual(cue['query'], 'a dog not on grass')
        self.assertEqual(set(cue), {'version', 'request_id', 'revision', 'query'})
        self.assertNotIn('scope', cue)
        self.assertNotIn('filters', cue)
        self.assertNotIn('context', cue)
        self.assertNotIn('visible_ids', cue)

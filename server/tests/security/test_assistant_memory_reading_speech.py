"""Explicit protected speech for current saved story/memoir openings."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

SECURITY = Path(__file__).resolve().parent
ROOT = SECURITY.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(SECURITY))

from app.access import assistant_workspace_transport as workspace_transport
import test_assistant_saved_memory_tool as tool_fixtures
import test_assistant_saved_memory_http as http_fixtures
from app.access.memory_books import MemoryBooks
from app.access.service import AccessService

FakeTts = http_fixtures.FakeTts
new_id = http_fixtures.new_id

BASE = '/assistant/workspace/v1'
ACCEPTS = ['saved_memory_cards_v1']


class AssistantMemoryReadingSpeechTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tool_fixtures.AssistantSavedMemoryToolTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        tool_fixtures.AssistantSavedMemoryToolTests.tearDownClass()

    def setUp(self):
        self.fx = http_fixtures.AssistantSavedMemoryHttpTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def fresh_turn(self, *, memoir=False, opening=None):
        if opening is None:
            opening = 'A quiet picnic opening.' if memoir else 'First story narration.'
        marker = 'openingtoken'
        story = self.fx.helper._save_story('Lake ' + marker + ' story', opening)
        if memoir:
            self.fx.helper._save_memoir('Lake ' + marker + ' memoir', opening, story['id'])
            text = 'find memoir ' + marker
        else:
            text = 'find saved story ' + marker
        self.fx.enable()
        thread = self.fx.thread()
        turn_id = new_id()
        response = self.fx.turn(thread['thread_id'], request_id=turn_id,
            text=text, accepts=ACCEPTS)
        self.assertEqual(response.status_code, 200, response.text)
        return thread, turn_id, response.json()

    def speech(self, thread, turn_id, *, ordinal='0', revision=1, body=None,
               request_id=None, parent_id=None, token=None):
        headers = {
            'X-PhotoHouse-Request-Id': request_id or new_id(),
            'X-PhotoHouse-Parent-Request-Id': parent_id or turn_id,
        }
        return self.fx.request('POST',
            f"/threads/{thread['thread_id']}/requests/{turn_id}/memory-cards/{ordinal}/speech",
            body=body or {'library_id': 'family-a', 'expected_revision': revision},
            headers=headers, token=token)

    def test_reading_capability_is_exact_and_requires_saved_memory_and_speech(self):
        self.fx.enable()
        response = self.fx.request('GET',
            '/saved-memory-reading-capabilities?library_id=family-a')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'version': 1, 'available': True})
        self.assertEqual(set(response.json()), {'version', 'available'})
        self.assertIn('no-store', response.headers.get('cache-control', '').lower())

        self.fx.app.state.assistant_reply_speech_enabled = False
        self.assertEqual(self.fx.request('GET',
            '/saved-memory-reading-capabilities?library_id=family-a').json(),
            {'version': 1, 'available': False})
        self.fx.app.state.assistant_reply_speech_enabled = True
        self.fx.app.state.assistant_saved_memory_cards_enabled = False
        self.assertEqual(self.fx.request('GET',
            '/saved-memory-reading-capabilities?library_id=family-a').json(),
            {'version': 1, 'available': False})

    def test_speaks_story_first_chapter_and_memoir_introduction_with_exact_clip(self):
        story_opening = ('🙂故事开头' * 55) + '尾部不应播报'
        thread, turn_id, _ = self.fresh_turn(opening=story_opening)
        response = self.speech(thread, turn_id)
        expected = story_opening[:240]
        while len(expected.encode('utf-8')) > 600:
            expected = expected[:-1]
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.fx.tts.calls[-1], (expected, 'zh'))
        self.assertLessEqual(len(self.fx.tts.calls[-1][0]), 240)
        self.assertLessEqual(len(self.fx.tts.calls[-1][0].encode('utf-8')), 600)

        memoir_opening = 'A memoir begins beside the lake.'
        thread, turn_id, _ = self.fresh_turn(memoir=True, opening=memoir_opening)
        response = self.speech(thread, turn_id)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.fx.tts.calls[-1], (memoir_opening, 'en'))

    def test_empty_opening_is_unavailable_without_title_fallback_or_tts(self):
        thread, turn_id, result = self.fresh_turn(opening='')
        self.fx.tts.calls.clear()
        response = self.speech(thread, turn_id)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()['error'], 'speech_unavailable')
        self.assertEqual(self.fx.tts.calls, [])
        self.assertNotIn(result['result']['memory_cards'][0]['title'], response.text)

    def test_original_unicode_spacing_is_preserved_for_speech(self):
        opening = '湖边\u00a0野餐，家人\u202f一起散步。\u2028傍晚回家。'
        thread, turn_id, _ = self.fresh_turn(opening=opening)
        response = self.speech(thread, turn_id)
        self.assertEqual(response.status_code, 200, response.headers.get('content-type'))
        self.assertEqual(self.fx.tts.calls[-1], (opening, 'zh'))

    def test_exact_request_scope_ordinal_parent_and_memory_cohort_are_required(self):
        thread, turn_id, _ = self.fresh_turn()
        path = f"/threads/{thread['thread_id']}/requests/{turn_id}/memory-cards/0/speech"
        good_headers = {'X-PhotoHouse-Request-Id': new_id(),
                        'X-PhotoHouse-Parent-Request-Id': turn_id}

        for ordinal in ('00', '+0', '-1', '12', '1e0', '9' * 500):
            with self.subTest(ordinal=ordinal):
                response = self.fx.request('POST', path.replace('/0/speech', f'/{ordinal}/speech'),
                    body={'library_id': 'family-a', 'expected_revision': 1}, headers=good_headers)
                self.assertIn(response.status_code, (400, 403), response.text)
        malformed_bodies = (
            {'library_id': 'family-a', 'expected_revision': 1, 'text': 'private source'},
            {'library_id': 'family-a'},
            {'library_id': 'family-b', 'expected_revision': 1},
        )
        for body in malformed_bodies:
            with self.subTest(body=body):
                response = self.speech(thread, turn_id, body=body)
                self.assertIn(response.status_code, (400, 401), response.text)
        bad_parent = self.speech(thread, turn_id, parent_id=new_id())
        self.assertEqual(bad_parent.status_code, 400, bad_parent.text)
        missing_headers = self.fx.request('POST', path,
            body={'library_id': 'family-a', 'expected_revision': 1})
        self.assertEqual(missing_headers.status_code, 400, missing_headers.text)
        stale = self.speech(thread, turn_id, revision=2)
        self.assertEqual(stale.status_code, 409, stale.text)
        foreign = self.speech(thread, turn_id, token=self.fx.library_fixture.other_token)
        self.assertIn(foreign.status_code, (401, 404), foreign.text)

        with self.fx.workspace.connection() as db:
            refs = json.loads(db.execute('SELECT card_refs FROM exchanges WHERE request_id=?',
                                         (turn_id,)).fetchone()[0])
            refs.append({'type': 'media', 'id': '101', 'revision': 'a' * 64,
                         'fingerprint': 'b' * 64})
            db.execute('UPDATE exchanges SET card_refs=? WHERE request_id=?',
                       (json.dumps(refs), turn_id))
        self.fx.tts.calls.clear()
        with patch.object(workspace_transport, '_saved_memory_reader') as reader:
            mixed = self.speech(thread, turn_id)
            reader.assert_not_called()
        self.assertIn(mixed.status_code, (400, 404, 409), mixed.text)
        self.assertEqual(self.fx.tts.calls, [])

        thread, turn_id, _ = self.fresh_turn()
        with self.fx.workspace.connection() as db:
            db.execute('UPDATE exchanges SET card_refs=? WHERE request_id=?',
                (json.dumps([{'type': 'media', 'id': '101', 'revision': 'a' * 64,
                              'fingerprint': 'a' * 64}]), turn_id))
        with patch.object(workspace_transport, '_saved_memory_reader') as reader:
            media_only = self.speech(thread, turn_id)
            reader.assert_not_called()
        self.assertIn(media_only.status_code, (400, 404, 409), media_only.text)
        self.assertEqual(self.fx.tts.calls, [])

    def test_pending_parent_is_not_read_or_synthesized(self):
        thread, turn_id, _ = self.fresh_turn()
        pending_id = new_id()
        pending = self.fx.workspace.begin_turn(self.fx.account, 'family-a',
            thread['thread_id'], pending_id, 1, 'find photos')
        self.assertEqual(pending['status'], 'pending')
        self.fx.tts.calls.clear()
        with patch.object(workspace_transport, '_saved_memory_reader') as reader:
            response = self.speech(thread, pending_id, revision=1)
            reader.assert_not_called()
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.fx.tts.calls, [])

    def test_source_edit_during_tts_withholds_audio(self):
        thread, turn_id, _ = self.fresh_turn()
        original = self.fx.tts.synthesize

        def edit_story(words, language):
            audio = original(words, language)
            body = self.fx.helper.fixture.body()
            body.update(revision='1', title='Changed opening source')
            stored = self.fx.workspace.get_thread(self.fx.account, 'family-a',
                                                  thread['thread_id'])
            story_id = stored['exchanges'][0]['cards'][0]['id']
            saved = self.fx.helper.fixture.save(
                body, ident=story_id)
            self.assertEqual(saved.status_code, 200, saved.text)
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=edit_story):
            changed = self.speech(thread, turn_id)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotEqual(changed.headers.get('content-type'), 'audio/wav')

    def test_membership_revocation_during_tts_withholds_audio(self):
        thread, turn_id, _ = self.fresh_turn()
        original = self.fx.tts.synthesize

        def revoke_membership(words, language):
            audio = original(words, language)
            with self.fx.library_fixture.connection() as db:
                updated = db.execute("UPDATE access_memberships SET status='revoked', revision=revision+1 "
                                     'WHERE account_id=? AND library_id=?',
                                     (self.fx.account, 'family-a'))
                self.assertEqual(updated.rowcount, 1)
                db.commit()
            return audio

        self.fx.tts.calls.clear()
        with patch.object(self.fx.tts, 'synthesize', side_effect=revoke_membership):
            response = self.speech(thread, turn_id)
        self.assertEqual(response.status_code, 401, response.headers.get('content-type'))
        self.assertEqual(response.json()['error'], 'access_denied')
        with self.fx.library_fixture.connection() as db:
            self.assertEqual(db.execute('SELECT status FROM access_memberships '
                                        'WHERE account_id=? AND library_id=?',
                                        (self.fx.account, 'family-a')).fetchone()[0], 'revoked')
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
        self.assertEqual(len(self.fx.tts.calls), 1)

    def test_feature_disable_during_tts_withholds_audio(self):
        thread, turn_id, _ = self.fresh_turn()
        original = self.fx.tts.synthesize

        def disable_feature(words, language):
            audio = original(words, language)
            self.fx.app.state.assistant_saved_memory_cards_enabled = False
            return audio

        self.fx.tts.calls.clear()
        with patch.object(self.fx.tts, 'synthesize', side_effect=disable_feature):
            response = self.speech(thread, turn_id)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
        self.assertEqual(len(self.fx.tts.calls), 1)

    def test_malformed_and_storage_failed_source_are_unavailable_without_tts(self):
        thread, turn_id, _ = self.fresh_turn()
        self.fx.tts.calls.clear()
        with patch.object(workspace_transport, '_saved_memory_reader',
                          return_value={'version': 1, 'kind': 'story', 'reader': {}}):
            malformed = self.speech(thread, turn_id)
        self.assertEqual(malformed.status_code, 503, malformed.text)
        self.assertEqual(malformed.json()['error'], 'speech_unavailable')
        self.assertNotEqual(malformed.headers.get('content-type'), 'audio/wav')
        self.assertEqual(self.fx.tts.calls, [])

        with patch.object(workspace_transport, '_saved_memory_reader',
                          side_effect=sqlite3.OperationalError('private storage detail')):
            failed = self.speech(thread, turn_id)
        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(failed.json()['error'], 'speech_unavailable')
        self.assertNotIn('private storage detail', failed.text)
        self.assertNotEqual(failed.headers.get('content-type'), 'audio/wav')
        self.assertEqual(self.fx.tts.calls, [])

    def test_changed_selected_opening_during_tts_withholds_audio(self):
        opening = 'Original selected opening.'
        thread, turn_id, _ = self.fresh_turn(opening=opening)
        original_reader = workspace_transport._saved_memory_reader
        calls = 0

        def changed_opening(*args):
            nonlocal calls
            calls += 1
            envelope = original_reader(*args)
            if calls > 1:
                envelope['reader']['chapters'][0]['narration'] = 'Different selected opening.'
            return envelope

        self.fx.tts.calls.clear()
        with patch.object(workspace_transport, '_saved_memory_reader',
                          side_effect=changed_opening):
            response = self.speech(thread, turn_id)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
        self.assertEqual(self.fx.tts.calls, [(opening, 'en')])

    def test_nonselected_cohort_source_drift_during_tts_withholds_audio(self):
        first = self.fx.helper._save_story('Picnic memory first', 'First source opening.')
        second = self.fx.helper._save_story('Picnic memory second', 'Second source opening.')
        self.fx.enable()
        thread = self.fx.thread()
        turn_id = new_id()
        turn = self.fx.turn(thread['thread_id'], request_id=turn_id,
                            text='find saved story picnic', accepts=ACCEPTS)
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertGreaterEqual(len(turn.json()['result']['memory_cards']), 2)
        self.assertEqual(turn.json()['result']['memory_cards'][0]['id'], first['id'])
        self.assertEqual(turn.json()['result']['memory_cards'][1]['id'], second['id'])
        original = self.fx.tts.synthesize

        def edit_other_story(words, language):
            audio = original(words, language)
            body = self.fx.helper.fixture.body()
            body.update(revision='1', title='Changed nonselected source')
            saved = self.fx.helper.fixture.save(body, ident=second['id'])
            self.assertEqual(saved.status_code, 200, saved.text)
            return audio

        self.fx.tts.calls.clear()
        with patch.object(self.fx.tts, 'synthesize', side_effect=edit_other_story):
            response = self.speech(thread, turn_id, ordinal='0')
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
        self.assertEqual(len(self.fx.tts.calls), 1)

    def test_latest_stored_cohort_change_during_tts_withholds_audio(self):
        thread, turn_id, _ = self.fresh_turn()
        original = self.fx.tts.synthesize

        def change_cohort(words, language):
            audio = original(words, language)
            with self.fx.workspace.connection() as db:
                db.execute('UPDATE exchanges SET card_refs=? WHERE request_id=?',
                           (json.dumps([]), turn_id))
            return audio

        self.fx.tts.calls.clear()
        with patch.object(self.fx.tts, 'synthesize', side_effect=change_cohort):
            response = self.speech(thread, turn_id)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
        self.assertEqual(len(self.fx.tts.calls), 1)

    def test_changed_memoir_child_or_latest_thread_turn_during_tts_withholds_audio(self):
        thread, turn_id, result = self.fresh_turn(memoir=True)
        book_id = result['result']['memory_cards'][0]['id']
        with self.fx.library_fixture.connection() as db:
            book = MemoryBooks(AccessService(db,
                clock=lambda: self.fx.library_fixture.now)).get(
                    self.fx.token, 'family-a', book_id)
        child_id = book['stories'][0]['id']
        original = self.fx.tts.synthesize

        def edit_child(words, language):
            audio = original(words, language)
            body = self.fx.helper.fixture.body()
            body.update(revision='1', title='Changed memoir child')
            saved = self.fx.helper.fixture.save(body, ident=child_id)
            self.assertEqual(saved.status_code, 200, saved.text)
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=edit_child):
            changed = self.speech(thread, turn_id)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotEqual(changed.headers.get('content-type'), 'audio/wav')

        thread, turn_id, _ = self.fresh_turn()
        original = self.fx.tts.synthesize

        def advance_thread(words, language):
            audio = original(words, language)
            next_turn = self.fx.turn(thread['thread_id'], request_id=new_id(),
                                     revision=1, text='find photos')
            self.assertEqual(next_turn.status_code, 200, next_turn.text)
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=advance_thread):
            changed = self.speech(thread, turn_id)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotEqual(changed.headers.get('content-type'), 'audio/wav')

        thread, turn_id, _ = self.fresh_turn()
        original = self.fx.tts.synthesize

        def replace_provider(words, language):
            audio = original(words, language)
            self.fx.app.state.assistant_tts = FakeTts()
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=replace_provider):
            changed = self.speech(thread, turn_id)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotEqual(changed.headers.get('content-type'), 'audio/wav')

    def test_receipt_and_private_store_never_copy_opening_and_duplicate_id_does_not_resynthesize(self):
        secret = 'OPENING TEXT MUST NOT LEAK TO PRIVATE RECEIPTS'
        thread, turn_id, _ = self.fresh_turn(opening=secret)
        speech_id = new_id()
        first = self.speech(thread, turn_id, request_id=speech_id)
        self.assertEqual(first.status_code, 200, first.text)
        call_count = len(self.fx.tts.calls)
        duplicate = self.speech(thread, turn_id, request_id=speech_id)
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertEqual(len(self.fx.tts.calls), call_count)

        receipt = self.fx.journal.get(speech_id, self.fx.account, 'family-a')
        self.assertEqual(receipt['input_text'], None)
        self.assertEqual(receipt['recognized_text'], None)
        with self.fx.workspace.connection() as db:
            stored = '\n'.join(str(row) for row in db.execute(
                'SELECT input_text,reply,card_refs FROM exchanges WHERE request_id=?',
                (turn_id,)).fetchall())
            summary = db.execute('SELECT result_summary FROM turn_requests WHERE request_id=?',
                                 (turn_id,)).fetchone()[0]
        self.assertNotIn(secret, stored)
        self.assertNotIn(secret, summary)

    def test_existing_generic_reply_speech_contract_is_unchanged(self):
        self.fx.enable()
        thread = self.fx.thread()
        turn_id = new_id()
        turn = self.fx.turn(thread['thread_id'], request_id=turn_id,
                            text='find photos')
        self.assertEqual(turn.status_code, 200, turn.text)
        speech = self.fx.request('POST',
            f"/threads/{thread['thread_id']}/requests/{turn_id}/speech",
            body={'library_id': 'family-a', 'expected_revision': 1},
            headers={'X-PhotoHouse-Request-Id': new_id(),
                     'X-PhotoHouse-Parent-Request-Id': turn_id})
        self.assertEqual(speech.status_code, 200, speech.text)
        self.assertEqual(self.fx.tts.calls, [(turn.json()['result']['reply'], 'en')])


if __name__ == '__main__':
    unittest.main()

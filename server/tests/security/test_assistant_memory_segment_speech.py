"""Protected, transient speech for one current saved-memory segment."""
import io
import json
from pathlib import Path
import sys
import unittest
import wave
from unittest.mock import patch

SECURITY = Path(__file__).resolve().parent
ROOT = SECURITY.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(SECURITY))

from app.access import assistant_reading_segments
from app.access import assistant_workspace_transport as workspace_transport
import test_assistant_memory_reading_speech as opening_fixtures
import test_assistant_saved_memory_http as http_fixtures

new_id = http_fixtures.new_id
SEGMENT_PATH = ('/threads/{thread}/requests/{turn}/memory-cards/{card}'
                '/segments/{segment}/speech')
BASE = '/assistant/workspace/v1'


class AssistantMemorySegmentSpeechTests(unittest.TestCase):
    """Reuse the existing isolated opening-speech fixture without inheriting it."""

    @classmethod
    def setUpClass(cls):
        opening_fixtures.AssistantMemoryReadingSpeechTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        opening_fixtures.AssistantMemoryReadingSpeechTests.tearDownClass()

    def setUp(self):
        self.opening = opening_fixtures.AssistantMemoryReadingSpeechTests()
        self.opening.setUp()
        self.addCleanup(self.opening.doCleanups)
        self.fx = self.opening.fx

    def fresh_turn(self, **kwargs):
        return self.opening.fresh_turn(**kwargs)

    def segment_speech(self, thread, turn_id, *, card='0', segment='0', revision=1,
                       body=None, request_id=None, parent_id=None, token=None):
        headers = {
            'X-PhotoHouse-Request-Id': request_id or new_id(),
            'X-PhotoHouse-Parent-Request-Id': parent_id or turn_id,
        }
        return self.fx.request(
            'POST', SEGMENT_PATH.format(thread=thread['thread_id'], turn=turn_id,
                                        card=card, segment=segment),
            body=body or {'library_id': 'family-a', 'expected_revision': revision},
            headers=headers, token=token)

    def test_segmenter_preserves_exact_unicode_source_and_bounds(self):
        self.assertEqual(assistant_reading_segments.MAX_SEGMENT_CODEPOINTS, 120)
        self.assertEqual(assistant_reading_segments.MAX_SEGMENT_BYTES, 360)
        self.assertEqual(assistant_reading_segments.MAX_SOURCE_BYTES, 6000)
        self.assertEqual(assistant_reading_segments.MAX_SEGMENTS, 128)

        cases = ('a' * 6000, '家' * 2000, '🙂' * 1500,
                 'Start. ' + ('湖边野餐🙂，家人同行。' * 100))
        for source in cases:
            with self.subTest(codepoints=len(source)):
                segments = assistant_reading_segments.saved_reading_segments(source)
                self.assertEqual(''.join(segments), source)
                self.assertLessEqual(len(segments), 128)
                for segment in segments:
                    self.assertTrue(segment.strip())
                    self.assertLessEqual(len(segment), 120)
                    self.assertLessEqual(len(segment.encode('utf-8')), 360)

        self.assertEqual(len(assistant_reading_segments.saved_reading_segments('a' * 6000)), 50)
        for bad in ('a' * 6001, ('家' * 2000) + 'x', '', '   ', '\x00hidden', '\ud800'):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ValueError):
                    assistant_reading_segments.saved_reading_segments(bad)
        with patch.object(assistant_reading_segments, 'MAX_SEGMENTS', 1):
            with self.assertRaises(ValueError):
                assistant_reading_segments.saved_reading_segments('a' * 121)

    def test_segmenter_uses_sentence_boundaries_without_rewriting_spacing(self):
        source = ('🙂' * 60) + '。  ' + ('家' * 70)
        segments = assistant_reading_segments.saved_reading_segments(source)
        self.assertEqual(segments[0], ('🙂' * 60) + '。  ')
        self.assertEqual(''.join(segments), source)
        self.assertFalse(segments[1].startswith(' '))

    def test_segment_capability_is_separate_exact_and_flag_gated(self):
        self.fx.enable()
        path = '/saved-memory-segment-reading-capabilities?library_id=family-a'
        response = self.fx.request('GET', path)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'version': 1, 'available': True})
        self.assertEqual(set(response.json()), {'version', 'available'})
        self.assertIn('no-store', response.headers.get('cache-control', '').lower())

        self.fx.app.state.assistant_reply_speech_enabled = False
        self.assertEqual(self.fx.request('GET', path).json(),
                         {'version': 1, 'available': False})
        self.fx.app.state.assistant_reply_speech_enabled = True
        self.fx.app.state.assistant_saved_memory_cards_enabled = False
        self.assertEqual(self.fx.request('GET', path).json(),
                         {'version': 1, 'available': False})

    def test_one_request_synthesizes_only_requested_server_derived_segment(self):
        source = 'A' * 250
        thread, turn_id, _ = self.fresh_turn(opening=source)
        self.fx.tts.calls.clear()

        first = self.segment_speech(thread, turn_id, segment='0')
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.headers.get('content-type'), 'audio/wav')
        self.assertEqual(first.headers.get('X-PhotoHouse-Reading-Segment'), '0')
        self.assertEqual(first.headers.get('X-PhotoHouse-Reading-Segment-Count'), '3')
        self.assertEqual(first.headers.get('X-PhotoHouse-Request-Id'),
                         first.request.headers.get('X-PhotoHouse-Request-Id'))
        self.assertEqual(first.headers.get('X-PhotoHouse-Receipt-Status'), 'succeeded')
        self.assertEqual(first.headers.get('X-PhotoHouse-Playback-Tracking'), 'enabled')
        self.assertIn('no-store', first.headers.get('cache-control', '').lower())
        self.assertEqual(self.fx.tts.calls, [('A' * 120, 'en')])

        second = self.segment_speech(thread, turn_id, segment='1')
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.headers.get('X-PhotoHouse-Reading-Segment'), '1')
        self.assertEqual(second.headers.get('X-PhotoHouse-Reading-Segment-Count'), '3')
        self.assertEqual(self.fx.tts.calls[-1], ('A' * 120, 'en'))
        self.assertEqual(len(self.fx.tts.calls), 2, 'each explicit request synthesizes exactly one segment')

        memoir_source = 'B' * 130
        thread, turn_id, _ = self.fresh_turn(memoir=True, opening=memoir_source)
        self.fx.tts.calls.clear()
        memoir = self.segment_speech(thread, turn_id, segment='1')
        self.assertEqual(memoir.status_code, 200, memoir.text)
        self.assertEqual(self.fx.tts.calls, [('B' * 10, 'en')])
        self.assertEqual(memoir.headers.get('X-PhotoHouse-Reading-Segment-Count'), '2')

    def test_path_body_parent_and_headers_are_strict_and_out_of_range_does_not_synthesize(self):
        thread, turn_id, _ = self.fresh_turn(opening='A' * 250)
        path = SEGMENT_PATH.format(thread=thread['thread_id'], turn=turn_id,
                                   card='0', segment='0')
        good_headers = {'X-PhotoHouse-Request-Id': new_id(),
                        'X-PhotoHouse-Parent-Request-Id': turn_id}
        for segment in ('00', '+0', '-1', '128', '999', '1e0'):
            with self.subTest(segment=segment):
                invalid = self.fx.request('POST', path.replace('/0/speech', f'/{segment}/speech'),
                    body={'library_id': 'family-a', 'expected_revision': 1}, headers=good_headers)
                self.assertIn(invalid.status_code, (400, 403, 404), invalid.text)
        for card in ('00', '+0', '-1', '12'):
            with self.subTest(card=card):
                invalid = self.fx.request('POST', path.replace('/memory-cards/0/', f'/memory-cards/{card}/'),
                    body={'library_id': 'family-a', 'expected_revision': 1}, headers=good_headers)
                self.assertIn(invalid.status_code, (400, 403, 404), invalid.text)
        self.assertEqual(self.fx.tts.calls, [])

        for body in (
            {'library_id': 'family-a', 'expected_revision': 1, 'text': 'client prose'},
            {'library_id': 'family-a', 'expected_revision': 1, 'source_id': 'client-source'},
            {'library_id': 'family-a'},
            {'library_id': 'family-b', 'expected_revision': 1},
        ):
            with self.subTest(body=body):
                invalid = self.segment_speech(thread, turn_id, body=body)
                self.assertIn(invalid.status_code, (400, 401), invalid.text)

        self.assertEqual(self.segment_speech(thread, turn_id, segment='2').status_code, 200)
        self.fx.tts.calls.clear()
        out_of_range = self.segment_speech(thread, turn_id, segment='3')
        self.assertIn(out_of_range.status_code, (404, 503), out_of_range.text)
        self.assertEqual(self.fx.tts.calls, [])
        canonical_last = self.segment_speech(thread, turn_id, segment='127')
        self.assertIn(canonical_last.status_code, (404, 503), canonical_last.text)
        rejected_next = self.segment_speech(thread, turn_id, segment='128')
        self.assertIn(rejected_next.status_code, (400, 403), rejected_next.text)
        self.assertEqual(self.fx.tts.calls, [])
        wrong_parent = self.segment_speech(thread, turn_id, parent_id=new_id())
        self.assertEqual(wrong_parent.status_code, 400, wrong_parent.text)
        missing_headers = self.fx.request('POST', path,
            body={'library_id': 'family-a', 'expected_revision': 1})
        self.assertEqual(missing_headers.status_code, 400, missing_headers.text)

    def test_selected_segment_and_other_cohort_source_drift_withhold_audio(self):
        thread, turn_id, _ = self.fresh_turn(opening='C' * 250)
        original = self.fx.tts.synthesize

        def edit_later_text(words, language):
            audio = original(words, language)
            body = self.fx.helper.fixture.body()
            body.update(revision='1', title='Changed source')
            body['chapters'] = json.loads(body['chapters'])
            body['chapters'][0]['narration'] = ('C' * 120) + ('D' * 130)
            body['chapters'] = json.dumps(body['chapters'], ensure_ascii=False)
            refs = self.fx.workspace.get_thread(self.fx.account, 'family-a', thread['thread_id'])
            story_id = refs['exchanges'][0]['cards'][0]['id']
            saved = self.fx.helper.fixture.save(body, ident=story_id)
            self.assertEqual(saved.status_code, 200, saved.text)
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=edit_later_text):
            response = self.segment_speech(thread, turn_id, segment='0')
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')

    def test_nonselected_cohort_source_drift_withholds_audio(self):
        self.fx.helper._save_story('Segment cohort first', 'E' * 150)
        second = self.fx.helper._save_story('Segment cohort second', 'F' * 150)
        self.fx.enable()
        thread = self.fx.thread()
        turn_id = new_id()
        turn = self.fx.turn(thread['thread_id'], request_id=turn_id,
            text='find saved story segment cohort', accepts=opening_fixtures.ACCEPTS)
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertGreaterEqual(len(turn.json()['result']['memory_cards']), 2)
        self.assertIn(second['id'], [card['id'] for card in turn.json()['result']['memory_cards']])
        original = self.fx.tts.synthesize

        def edit_nonselected(words, language):
            audio = original(words, language)
            body = self.fx.helper.fixture.body()
            body.update(revision='1', title='Changed nonselected story')
            saved = self.fx.helper.fixture.save(body, ident=second['id'])
            self.assertEqual(saved.status_code, 200, saved.text)
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=edit_nonselected):
            response = self.segment_speech(thread, turn_id, segment='0')
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
        self.assertEqual(len(self.fx.tts.calls), 1)

    def test_stored_cohort_change_during_synthesis_withholds_audio(self):
        thread, turn_id, _ = self.fresh_turn(opening='M' * 150)
        original = self.fx.tts.synthesize

        def clear_stored_cohort(words, language):
            audio = original(words, language)
            with self.fx.workspace.connection() as db:
                db.execute('UPDATE exchanges SET card_refs=? WHERE request_id=?',
                           (json.dumps([]), turn_id))
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=clear_stored_cohort):
            response = self.segment_speech(thread, turn_id)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
        self.assertEqual(len(self.fx.tts.calls), 1)

    def test_foreign_pending_and_malformed_parent_cohorts_never_reach_tts(self):
        thread, turn_id, _ = self.fresh_turn(opening='N' * 150)
        self.fx.tts.calls.clear()

        foreign = self.segment_speech(thread, turn_id,
                                      token=self.fx.library_fixture.other_token)
        self.assertIn(foreign.status_code, (401, 404), foreign.text)
        self.assertEqual(self.fx.tts.calls, [])

        with self.fx.workspace.connection() as db:
            row = db.execute('SELECT card_refs FROM exchanges WHERE request_id=?',
                             (turn_id,)).fetchone()
            valid = json.loads(row[0])
        mixed_cohorts = (
            [],
            [{'type': 'media', 'id': '101', 'revision': 'a' * 64,
              'fingerprint': 'a' * 64}],
            [valid[0], valid[0]],
        )
        for refs in mixed_cohorts:
            with self.subTest(refs=refs):
                with self.fx.workspace.connection() as db:
                    db.execute('UPDATE exchanges SET card_refs=? WHERE request_id=?',
                               (json.dumps(refs), turn_id))
                response = self.segment_speech(thread, turn_id)
                self.assertIn(response.status_code, (404, 409), response.text)
                self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
                self.assertEqual(self.fx.tts.calls, [])

        pending_id = new_id()
        pending = self.fx.workspace.begin_turn(self.fx.account, 'family-a',
            thread['thread_id'], pending_id, 1, 'find photos')
        self.assertEqual(pending['status'], 'pending')
        response = self.segment_speech(thread, pending_id, revision=1)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.fx.tts.calls, [])

    def test_full_source_bytes_guard_detects_same_revision_suffix_change(self):
        source = 'C' * 250
        thread, turn_id, _ = self.fresh_turn(opening=source)
        original_reader = workspace_transport._saved_memory_reader
        calls = 0

        def change_only_unspoken_suffix(access, token, library, reference):
            nonlocal calls
            envelope = original_reader(access, token, library, reference)
            calls += 1
            if calls > 1:
                # Keep segment 0 and the segment count identical. Only the
                # unspoken tail changes; don't update the persisted revision.
                envelope['reader']['chapters'][0]['narration'] = ('C' * 120) + ('D' * 130)
            return envelope

        self.fx.tts.calls.clear()
        with patch.object(workspace_transport, '_saved_memory_reader',
                          side_effect=change_only_unspoken_suffix):
            response = self.segment_speech(thread, turn_id, segment='0')
        self.assertEqual(calls, 2)
        self.assertEqual(self.fx.tts.calls, [('C' * 120, 'en')])
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')

    def test_membership_revocation_during_synthesis_withholds_audio(self):
        thread, turn_id, _ = self.fresh_turn(opening='G' * 150)
        original = self.fx.tts.synthesize

        def revoke_membership(words, language):
            audio = original(words, language)
            with self.fx.library_fixture.connection() as db:
                changed = db.execute("UPDATE access_memberships SET status='revoked', revision=revision+1 "
                    'WHERE account_id=? AND library_id=?', (self.fx.account, 'family-a'))
                self.assertEqual(changed.rowcount, 1)
                db.commit()
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=revoke_membership):
            response = self.segment_speech(thread, turn_id)
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')

    def test_feature_disable_during_synthesis_withholds_audio(self):
        thread, turn_id, _ = self.fresh_turn(opening='H' * 150)
        original = self.fx.tts.synthesize

        def disable_feature(words, language):
            audio = original(words, language)
            self.fx.app.state.assistant_saved_memory_cards_enabled = False
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=disable_feature):
            response = self.segment_speech(thread, turn_id)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')

    def test_provider_replacement_during_synthesis_withholds_audio(self):
        thread, turn_id, _ = self.fresh_turn(opening='I' * 150)
        original = self.fx.tts.synthesize

        def replace_provider(words, language):
            audio = original(words, language)
            self.fx.app.state.assistant_tts = http_fixtures.FakeTts()
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=replace_provider):
            response = self.segment_speech(thread, turn_id)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')

    def test_thread_advancement_during_synthesis_withholds_audio(self):
        thread, turn_id, _ = self.fresh_turn(opening='J' * 150)
        original = self.fx.tts.synthesize

        def advance_thread(words, language):
            audio = original(words, language)
            next_turn = self.fx.turn(thread['thread_id'], request_id=new_id(),
                                     revision=1, text='find photos')
            self.assertEqual(next_turn.status_code, 200, next_turn.text)
            return audio

        with patch.object(self.fx.tts, 'synthesize', side_effect=advance_thread):
            response = self.segment_speech(thread, turn_id)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')

    def test_invalid_wav_is_rejected_without_retry_or_source_text_in_journal(self):
        thread, turn_id, _ = self.fresh_turn(opening='PRIVATE SEGMENT TEXT ' * 7)
        speech_id = new_id()

        def too_long_wav(_words, _language):
            buffer = io.BytesIO()
            with wave.open(buffer, 'wb') as audio:
                audio.setnchannels(1)
                audio.setsampwidth(1)
                audio.setframerate(8000)
                audio.writeframes(b'\x00' * (31 * 8000))
            return buffer.getvalue()

        with patch.object(self.fx.tts, 'synthesize', side_effect=too_long_wav) as synthesize:
            response = self.segment_speech(thread, turn_id, request_id=speech_id)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
        synthesize.assert_called_once()
        receipt = self.fx.journal.get(speech_id, self.fx.account, 'family-a')
        self.assertIsNone(receipt['input_text'])
        self.assertIsNone(receipt['recognized_text'])
        with self.fx.workspace.connection() as db:
            stored = '\n'.join(str(row) for row in db.execute(
                'SELECT input_text,reply,card_refs FROM exchanges WHERE request_id=?',
                (turn_id,)).fetchall())
            summary = db.execute('SELECT result_summary FROM turn_requests WHERE request_id=?',
                                 (turn_id,)).fetchone()[0]
        self.assertNotIn('PRIVATE SEGMENT TEXT', stored)
        self.assertNotIn('PRIVATE SEGMENT TEXT', summary)

        thread, turn_id, _ = self.fresh_turn(opening='L' * 130)
        with patch.object(self.fx.tts, 'synthesize', return_value=b'x' * (2 * 1024 * 1024 + 1)) as synthesize:
            oversized = self.segment_speech(thread, turn_id)
        self.assertEqual(oversized.status_code, 503, oversized.text)
        self.assertNotEqual(oversized.headers.get('content-type'), 'audio/wav')
        synthesize.assert_called_once()

    def test_duplicate_segment_request_id_does_not_synthesize_twice(self):
        thread, turn_id, _ = self.fresh_turn(opening='K' * 130)
        request_id = new_id()
        first = self.segment_speech(thread, turn_id, segment='0', request_id=request_id)
        self.assertEqual(first.status_code, 200, first.text)
        count = len(self.fx.tts.calls)
        replay = self.segment_speech(thread, turn_id, segment='0', request_id=request_id)
        self.assertEqual(replay.status_code, 409, replay.text)
        self.assertEqual(len(self.fx.tts.calls), count)


if __name__ == '__main__':
    unittest.main()

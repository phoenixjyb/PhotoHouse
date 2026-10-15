"""Actual-playback reports are scoped terminal events, not audio-download claims."""
import unittest
import uuid

import httpx
import test_assistant_journal as fixture
import test_assistant_workspace_reply_speech as speech_fixture
from app.access.transport import COOKIE, csrf_token


class PlaybackReceiptTests(unittest.TestCase):
    setUp = fixture.JournalHttpTests.setUp
    connection = fixture.JournalHttpTests.connection
    update = fixture.JournalHttpTests.update
    turn = fixture.JournalHttpTests.turn
    journal = fixture.JournalHttpTests.journal
    receipt = fixture.JournalHttpTests.receipt
    asr = fixture.JournalHttpTests.asr
    transcribe = fixture.JournalHttpTests.transcribe
    wav = fixture.JournalHttpTests.wav

    def report(self, ident, outcome='completed', *, headers=None, library='family-a', **extra):
        return self.client.post('/assistant/v1/receipts/' + ident + '/playback',
            json=dict(library_id=library, outcome=outcome, **extra),
            headers=self.auth if headers is None else headers)

    def speech_record(self, *, status='succeeded', operation='speech'):
        ident = str(uuid.uuid4())
        self.app.state.assistant_journal.begin('one', 'family-a', operation, ident)
        self.app.state.assistant_journal.finish(ident, status, http_status=200 if status == 'succeeded' else 503)
        return ident

    def test_first_terminal_report_idempotent_and_legacy_receipt_unchanged(self):
        journal = self.journal()
        for terminal in ('completed', 'failed', 'cancelled'):
            with self.subTest(terminal=terminal):
                ident = self.speech_record()
                original = self.receipt(ident).json()
                self.assertEqual(self.report(ident, terminal).status_code, 200)
                self.assertEqual(self.report(ident, terminal).json(),
                                 dict(version=1, request_id=ident, playback_outcome=terminal))
                self.assertEqual(self.receipt(ident).json(), original)
                different = 'failed' if terminal != 'failed' else 'completed'
                self.assertEqual(self.report(ident, different).status_code, 409)
                stages = journal.inspect(ident=ident)['items'][0]['stages']
                self.assertEqual([s['stage'] for s in stages if s['stage'].startswith('client_playback_')],
                                 ['client_playback_' + terminal])

    def test_auth_csrf_operation_and_expiry_boundaries(self):
        self.journal()
        ident = self.speech_record()
        self.assertEqual(self.report(ident, headers={}).status_code, 401)
        self.assertEqual(self.report(ident, headers={'Authorization': 'Bearer ' + fixture.SECOND}).status_code, 404)
        self.assertEqual(self.report(ident, library='family-b').status_code, 401)
        cookie = {'Cookie': COOKIE + '=' + fixture.TOKEN, 'Origin': fixture.ORIGIN}
        self.assertEqual(self.report(ident, headers=cookie).status_code, 403)
        cookie['X-CSRF-Token'] = csrf_token(fixture.TOKEN)
        self.assertEqual(self.report(ident, headers=cookie).status_code, 200)
        for operation, status in (('turn', 'succeeded'), ('transcribe', 'succeeded'), ('speech', 'failed')):
            self.assertEqual(self.report(self.speech_record(operation=operation, status=status)).status_code, 409)
        for outcome in ('displayed', 'open_requested', 'unknown', {}, None):
            self.assertEqual(self.report(ident, outcome).status_code, 400)
        self.assertEqual(self.report(ident, extra='forbidden').status_code, 400)
        self.assertEqual(self.report('invalid').status_code, 403)
        self.assertEqual(self.report(str(uuid.uuid4())).status_code, 404)
        self.app.state.assistant_journal.clock = lambda: fixture.NOW + 31 * 86400
        self.assertEqual(self.report(ident).status_code, 404)

    def test_asr_safe_categories_are_durable_and_never_store_provider_body(self):
        journal = self.journal()
        cases = ((httpx.Response(200, json={'success': True, 'text': ''}), 422, 'speech_no_input'),
                 (httpx.Response(429, text='private-provider-secret'), 503, 'speech_busy'),
                 (httpx.Response(200, json={'bad': 'private-provider-secret'}), 502, 'speech_invalid_response'))
        for upstream, status, code in cases:
            self.asr(lambda request, upstream=upstream: upstream)
            ident = str(uuid.uuid4())
            response = self.transcribe(ident)
            self.assertEqual((response.status_code, response.json()['error']), (status, code))
            saved = self.receipt(ident).json()
            self.assertEqual((saved['status'], saved['error_code']), ('failed', code))
            self.assertIsNone(saved['recognized_text'])
        self.asr(lambda request: (_ for _ in ()).throw(httpx.ReadTimeout('private-provider-secret')))
        ident = str(uuid.uuid4())
        self.assertEqual(self.transcribe(ident).status_code, 504)
        self.assertEqual(self.receipt(ident).json()['error_code'], 'speech_timeout')
        self.assertNotIn(b'private-provider-secret', journal.path.read_bytes())
        self.assertNotIn(self.wav(), journal.path.read_bytes())


class PrivateSpeechPlaybackTests(unittest.TestCase):
    setUp = speech_fixture.AssistantWorkspaceReplySpeechTests.setUp
    connection = speech_fixture.AssistantWorkspaceReplySpeechTests.connection
    headers = speech_fixture.AssistantWorkspaceReplySpeechTests.headers
    create_thread = speech_fixture.AssistantWorkspaceReplySpeechTests.create_thread
    create_turn = speech_fixture.AssistantWorkspaceReplySpeechTests.create_turn
    speak = speech_fixture.AssistantWorkspaceReplySpeechTests.speak

    def test_header_requires_successful_speech_and_receipt_is_linked_to_turn(self):
        thread_id = self.create_thread()
        turn_id, _ = self.create_turn(thread_id, text='查找编号101')
        ident, spoken = self.speak(thread_id, turn_id)
        self.assertEqual(spoken.status_code, 200, spoken.text)
        self.assertEqual(spoken.headers['X-PhotoHouse-Playback-Tracking'], 'enabled')
        # Receiving the waveform creates no playback terminal event.
        row = self.journal.inspect(ident=ident)['items'][0]
        self.assertEqual(row['parent_request_id'], turn_id)
        self.assertFalse(any(s['stage'].startswith('client_playback_') for s in row['stages']))
        result = self.client.post('/assistant/v1/receipts/' + ident + '/playback',
            json={'library_id': 'family-a', 'outcome': 'completed'}, headers=self.headers())
        self.assertEqual(result.status_code, 200, result.text)
        _, duplicate = self.speak(thread_id, turn_id, request_id=ident)
        self.assertNotIn('X-PhotoHouse-Playback-Tracking', duplicate.headers)

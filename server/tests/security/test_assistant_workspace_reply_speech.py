"""Private saved-reply synthesis stays owned, bounded and journaled."""
from contextlib import closing, contextmanager
import io
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid
import wave
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests' / 'security'))
sys.path.insert(0, str(ROOT / 'scripts'))

from fastapi.testclient import TestClient
from app.access import discovery as discovery_module
from app.access import assistant as assistant_module
from app.access.assistant_journal import initialize as initialize_journal
from app.access.assistant_speech import LocalAssistantTts
from app.access.assistant_speech import AssistantSpeechUnavailable
from app.access.assistant_workspace_store import initialize_v2
from app.access.discovery_provider import MemoryIndexProvider
from app.access.discovery_transport import DiscoveryRuntime
from app.access.service import AccessService
from app.access.transport import AccessRuntime
from app.main import create_app
from app.access.runtime import RuntimeConfiguration
import staging_app
from phone_discovery_fixture import create, reviewed, TOKEN, SECOND, NOW

ORIGIN = 'https://photohouse.example.test'
BASE = '/assistant/workspace/v1'


def new_id():
    return str(uuid.uuid4())


def valid_audio(seconds=0.1):
    output = io.BytesIO()
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(b'\0\0' * int(16000 * seconds))
    return output.getvalue()


class FakeTts(LocalAssistantTts):
    """Typed adapter fixture; synthesis is local deterministic byte generation."""
    def __init__(self):
        self.calls = []
        self.on_synthesize = None
        self.audio = valid_audio()
        self.failure = None

    def synthesize(self, words, language):
        self.calls.append((words, language))
        if self.on_synthesize is not None:
            self.on_synthesize()
        if self.failure is not None:
            raise self.failure
        return self.audio


class AssistantWorkspaceReplySpeechTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.database = self.root / 'synthetic.sqlite'
        with closing(sqlite3.connect(self.database)) as connection, connection:
            create(connection)
            index = reviewed(AccessService(connection, clock=lambda: NOW))
        self.now = [NOW]
        self.access = AccessRuntime(self.connection, ORIGIN, clock=lambda: self.now[0])
        self.discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)),
                                          discovery_module.ReadBudget())
        self.workspace = initialize_v2(self.root / 'workspace.sqlite', clock=lambda: self.now[0])
        self.journal = initialize_journal(self.root / 'journal.sqlite')
        self.tts = FakeTts()
        self.app = create_app(access_runtime=self.access, discovery_runtime=self.discovery,
            assistant_enabled=True, assistant_tts=self.tts, assistant_journal=self.journal,
            assistant_workspace_store=self.workspace, assistant_reply_speech_enabled=True)
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.addCleanup(self.client.close)

    def test_staging_flag_defaults_off_validates_dependencies_and_reaches_runtime(self):
        base = {
            'format_version': 1,
            'database': '/synthetic/database.sqlite',
            'web_origin': 'https://photohouse.example.test',
            'original_roots': ['/synthetic/photos'],
            'derived_root': '/synthetic/cache',
            'bind_host': '127.0.0.1',
            'port': 443,
            'tls_certificate': '/synthetic/tls.crt',
            'tls_private_key': '/synthetic/tls.key',
        }
        self.assertFalse(staging_app.parse_configuration(base).assistant_reply_speech_enabled)
        with self.assertRaises(staging_app.InvalidConfiguration):
            staging_app.parse_configuration(base | {'assistant_reply_speech_enabled': True})
        with self.assertRaises(staging_app.InvalidConfiguration):
            staging_app.parse_configuration(base | {'assistant_reply_speech_enabled': 1})

        configured = base | {
            'assistant_enabled': True,
            'assistant_tts_url': 'http://127.0.0.1:11390/api/tts',
            'assistant_journal_path': '/synthetic/private/journal.sqlite',
            'assistant_workspace_path': '/synthetic/private/workspace.sqlite',
            'assistant_reply_speech_enabled': True,
        }
        parsed = staging_app.parse_configuration(configured)
        self.assertTrue(parsed.assistant_reply_speech_enabled)
        with patch.object(RuntimeConfiguration, 'build_app', autospec=True,
                          side_effect=lambda runtime: runtime) as build_app:
            runtime = parsed.build_app()
        self.assertTrue(runtime.assistant_reply_speech_enabled)
        build_app.assert_called_once()
        default_runtime = RuntimeConfiguration(Path('/synthetic/database.sqlite'),
            'https://photohouse.example.test', (Path('/synthetic/photos'),),
            Path('/synthetic/cache'))
        self.assertFalse(default_runtime.assistant_reply_speech_enabled)
        invalid_runtime = RuntimeConfiguration(Path('/synthetic/database.sqlite'),
            'https://photohouse.example.test', (Path('/synthetic/photos'),),
            Path('/synthetic/cache'), assistant_reply_speech_enabled=1)
        with self.assertRaisesRegex(ValueError, 'private reply speech opt-in'):
            invalid_runtime.build_app()

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.database, timeout=.25)
        connection.execute('PRAGMA foreign_keys=ON')
        connection.execute('PRAGMA query_only=ON')
        try:
            yield connection
        finally:
            connection.close()

    def update(self, sql, params=()):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute(sql, params)

    def headers(self, token=TOKEN, *, request_id=None, parent_id=None):
        result = {'Authorization': 'Bearer ' + token}
        if request_id is not None:
            result['X-PhotoHouse-Request-Id'] = request_id
        if parent_id is not None:
            result['X-PhotoHouse-Parent-Request-Id'] = parent_id
        return result

    def create_thread(self, token=TOKEN, library='family-a'):
        response = self.client.post(BASE + '/threads', headers=self.headers(token),
                                    json={'library_id': library})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['thread']['thread_id']

    def create_turn(self, thread_id, *, text='find photos', revision=0, result=None, search_v2=False):
        turn_id = new_id()
        headers = self.headers(request_id=turn_id)
        if search_v2:
            headers['X-PhotoHouse-Search-Version'] = '2'
        body = {'library_id': 'family-a', 'request_id': turn_id,
                'expected_revision': revision, 'text': text}
        if result is None:
            response = self.client.post(f'{BASE}/threads/{thread_id}/turns',
                                        headers=headers, json=body)
        else:
            with patch.object(assistant_module, '_turn', return_value=result):
                response = self.client.post(f'{BASE}/threads/{thread_id}/turns',
                                            headers=headers, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return turn_id, response.json()

    def speak(self, thread_id, turn_id, *, request_id=None, parent_id=None,
              revision=1, token=TOKEN, body=None, search_v2=False):
        request_id = request_id or new_id()
        parent_id = turn_id if parent_id is None else parent_id
        headers = self.headers(token, request_id=request_id, parent_id=parent_id)
        if search_v2:
            headers['X-PhotoHouse-Search-Version'] = '2'
        payload = {'library_id': 'family-a', 'expected_revision': revision} if body is None else body
        return request_id, self.client.post(
            f'{BASE}/threads/{thread_id}/requests/{turn_id}/speech',
            headers=headers, json=payload)

    def test_filter_explanation_reply_is_spoken_only_while_source_remains_current(self):
        self.update('''CREATE TABLE access_stories (
            id TEXT PRIMARY KEY, asset_id INTEGER, library_id TEXT, author_id TEXT,
            revision INTEGER, title TEXT, text TEXT, updated_at INTEGER, deleted INTEGER)''')
        tid = self.create_thread()
        _, initial = self.create_turn(tid, text='find Sample Child photos in 2026', search_v2=True)
        turn_id, explained = self.create_turn(tid, text='what filters are active',
                                              revision=1, search_v2=True)
        result = explained['result']
        self.assertEqual(result['filters'], initial['result']['filters'])
        self.assertIn('Sample Child', result['reply'])
        self.assertLessEqual(len(result['reply'].encode('utf-8')), 600)
        _, speech = self.speak(tid, turn_id, revision=2, search_v2=True)
        self.assertEqual(speech.status_code, 200, speech.text)
        self.assertEqual(speech.content, self.tts.audio)
        # Mixed reviewed labels can select the existing Chinese narration voice;
        # the exact current summary, not a rewritten prompt, reaches the adapter.
        self.assertEqual(self.tts.calls[-1][0], result['reply'])
        self.tts.on_synthesize = lambda: self.update(
            "UPDATE captions SET text='changed source' WHERE id=1")
        _, stale = self.speak(tid, turn_id, revision=2, search_v2=True)
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertNotEqual(stale.headers.get('content-type'), 'audio/wav')

    def test_saved_reply_speech_is_default_opt_in_and_duplicate_receipt_never_synthesizes_twice(self):
        capabilities = self.client.get(BASE + '/capabilities?library_id=family-a',
                                       headers=self.headers()).json()
        self.assertTrue(capabilities['reply_speech'])
        self.app.state.assistant_reply_speech_enabled = False
        legacy = self.client.get(BASE + '/capabilities?library_id=family-a',
                                 headers=self.headers()).json()
        self.assertNotIn('reply_speech', legacy)
        self.app.state.assistant_reply_speech_enabled = True

        thread_id = self.create_thread()
        turn_id, completed = self.create_turn(thread_id)
        self.assertEqual(completed['result']['kind'], 'results')
        self.assertEqual(completed['result']['total'], 2)
        speech_id = new_id()
        first_id, spoken = self.speak(thread_id, turn_id, request_id=speech_id)
        self.assertEqual(spoken.status_code, 200, spoken.text)
        self.assertEqual(spoken.headers['content-type'], 'audio/wav')
        self.assertEqual(spoken.content, self.tts.audio)
        self.assertEqual(spoken.headers['cache-control'], 'no-store')
        self.assertEqual(spoken.headers['X-PhotoHouse-Request-Id'], speech_id)
        self.assertEqual(spoken.headers['X-PhotoHouse-Receipt-Status'], 'succeeded')
        self.assertEqual(self.tts.calls, [(
            'Found 2 results. In the current list: '
            'Result 1 is a photo, recorded date December 1, 2025. '
            'Result 2 is a photo, recorded date January 2, 2026. '
            'Say "open the first result" to view it.', 'en')])

        duplicate_id, duplicate = self.speak(thread_id, turn_id, request_id=speech_id)
        self.assertEqual(duplicate_id, first_id)
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json()['error'], 'request_conflict')
        self.assertEqual(len(self.tts.calls), 1)
        receipt = self.journal.inspect(ident=speech_id, include_input=True)['items'][0]
        self.assertEqual((receipt['operation'], receipt['parent_request_id'], receipt['status']),
                         ('speech', turn_id, 'succeeded'))
        self.assertIsNone(receipt['input_text'])
        self.assertIsNone(receipt['recognized_text'])
        self.assertTrue({'received', 'validated', 'provider_started', 'provider_completed',
                         'succeeded'} <= {stage['stage'] for stage in receipt['stages']})

    def test_contract_rejects_bad_headers_extra_body_open_reply_and_over_limit_without_speech(self):
        thread_id = self.create_thread()
        turn_id, _ = self.create_turn(thread_id)
        same_id, same = self.speak(thread_id, turn_id, request_id=turn_id)
        self.assertEqual(same_id, turn_id)
        self.assertEqual(same.status_code, 400)
        self.assertEqual(self.tts.calls, [])
        extra_id, extra = self.speak(thread_id, turn_id, body={
            'library_id': 'family-a', 'expected_revision': 1, 'reply': 'caller text'})
        self.assertEqual(extra.status_code, 400)
        self.assertEqual(extra.headers.get('X-PhotoHouse-Request-Id'), None)

        open_id, opened = self.create_turn(thread_id, text='open the first result', revision=1)
        self.assertEqual(opened['result']['kind'], 'open')
        _, open_speech = self.speak(thread_id, open_id, revision=2)
        self.assertEqual(open_speech.status_code, 400)
        self.assertEqual(self.tts.calls, [])

        long_thread = self.create_thread()
        long_result = {'version': 1, 'kind': 'clarification', 'reply': 'x' * 601,
                       'context': None, 'filters': None, 'items': [], 'total': 0,
                       'has_more': False, 'effect': None}
        long_id, _ = self.create_turn(long_thread, result=long_result)
        _, too_long = self.speak(long_thread, long_id)
        self.assertEqual(too_long.status_code, 400)
        self.assertEqual(self.tts.calls, [])

        missing_id_headers = self.headers()
        missing_id = self.client.post(
            f'{BASE}/threads/{thread_id}/requests/{long_id}/speech',
            headers=missing_id_headers,
            json={'library_id': 'family-a', 'expected_revision': 1})
        self.assertEqual(missing_id.status_code, 400)
        oversized = self.client.post(
            f'{BASE}/threads/{thread_id}/requests/{long_id}/speech',
            content=b' ' * 2049,
            headers={**self.headers(request_id=new_id(), parent_id=long_id),
                     'Content-Type': 'application/json'})
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(oversized.json()['error'], 'request_too_large')
        self.assertEqual(self.tts.calls, [])

    def test_failed_provider_and_invalid_or_unbounded_wav_never_return_audio(self):
        thread_id = self.create_thread()
        turn_id, _ = self.create_turn(thread_id)
        self.tts.failure = AssistantSpeechUnavailable()
        failed_id, failed = self.speak(thread_id, turn_id)
        self.assertEqual(failed.status_code, 503)
        self.assertNotEqual(failed.headers.get('content-type'), 'audio/wav')
        self.assertEqual(self.journal.inspect(ident=failed_id)['items'][0]['status'], 'failed')

        self.tts.failure = None
        for audio in (b'not a wav', b'\0' * (2 * 1024 * 1024 + 1), valid_audio(31)):
            self.tts.audio = audio
            request_id, response = self.speak(thread_id, turn_id)
            self.assertEqual(response.status_code, 503)
            self.assertNotEqual(response.headers.get('content-type'), 'audio/wav')
            self.assertEqual(self.journal.inspect(ident=request_id)['items'][0]['status'], 'failed')
        self.assertEqual(len(self.tts.calls), 4)

    def test_expired_parent_deleted_thread_and_failed_finalization_never_return_audio(self):
        expired_thread = self.create_thread()
        expired_turn, _ = self.create_turn(expired_thread)
        with sqlite3.connect(self.workspace.path) as connection:
            connection.execute('UPDATE turn_requests SET expires_at=? WHERE request_id=?',
                               (NOW - 1, expired_turn))
        _, expired = self.speak(expired_thread, expired_turn)
        self.assertEqual(expired.status_code, 404)
        self.assertNotEqual(expired.headers.get('content-type'), 'audio/wav')

        deleted_thread = self.create_thread()
        deleted_turn, _ = self.create_turn(deleted_thread)
        self.tts.on_synthesize = lambda: self.workspace.delete_thread(
            'one', 'family-a', deleted_thread, 1)
        _, deleted = self.speak(deleted_thread, deleted_turn)
        self.assertEqual(deleted.status_code, 404)
        self.assertNotEqual(deleted.headers.get('content-type'), 'audio/wav')
        self.tts.on_synthesize = None

        finalized_thread = self.create_thread()
        finalized_turn, _ = self.create_turn(finalized_thread)
        speech_id = new_id()
        with patch.object(self.journal, 'finish', side_effect=RuntimeError('synthetic failure')):
            _, finalization = self.speak(finalized_thread, finalized_turn,
                                         request_id=speech_id)
        self.assertEqual(finalization.status_code, 503)
        self.assertNotEqual(finalization.headers.get('content-type'), 'audio/wav')
        self.assertEqual(finalization.headers.get('X-PhotoHouse-Receipt-Status'), 'received')

    def test_wrong_owner_stale_revision_and_source_drift_cannot_return_audio(self):
        thread_id = self.create_thread()
        turn_id, _ = self.create_turn(thread_id)
        _, foreign = self.speak(thread_id, turn_id, token=SECOND)
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(self.tts.calls, [])

        self.create_turn(thread_id, revision=1)
        _, stale = self.speak(thread_id, turn_id, revision=1)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.tts.calls, [])

        context_thread = self.create_thread()
        context_turn, _ = self.create_turn(context_thread)
        self.update("UPDATE captions SET text='Changed synthetic caption' WHERE asset_id=101")
        _, drift = self.speak(context_thread, context_turn)
        self.assertEqual(drift.status_code, 409)
        self.assertEqual(drift.json()['error'], 'context_changed')
        self.assertEqual(self.tts.calls, [])

    def test_membership_and_revision_are_rechecked_after_synthesis_before_audio_return(self):
        thread_id = self.create_thread()
        turn_id, _ = self.create_turn(thread_id)
        self.tts.on_synthesize = lambda: self.update(
            "UPDATE access_memberships SET status='requested' WHERE account_id='one' AND library_id='family-a'")
        _, revoked = self.speak(thread_id, turn_id)
        self.assertEqual(revoked.status_code, 401)
        self.assertNotEqual(revoked.headers.get('content-type'), 'audio/wav')

        self.update("UPDATE access_memberships SET status='approved' WHERE account_id='one' AND library_id='family-a'")
        self.tts.on_synthesize = None
        fresh_thread = self.create_thread()
        fresh_turn, _ = self.create_turn(fresh_thread)
        self.tts.on_synthesize = lambda: self.workspace.append_exchange(
            'one', 'family-a', fresh_thread, new_id(), 1, 'Synthetic concurrent exchange',
            'Synthetic concurrent reply', [], [])
        _, revision_changed = self.speak(fresh_thread, fresh_turn)
        self.assertEqual(revision_changed.status_code, 409)
        self.assertNotEqual(revision_changed.headers.get('content-type'), 'audio/wav')


    def test_search_v2_reply_requires_negotiation_and_revalidates_after_synthesis(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('''CREATE TABLE access_stories (
                id TEXT PRIMARY KEY, asset_id INTEGER, library_id TEXT, author_id TEXT,
                revision INTEGER, title TEXT, text TEXT, updated_at INTEGER, deleted INTEGER)''')
        tid = self.create_thread()
        rid = new_id()
        headers = self.headers(request_id=rid) | {'X-PhotoHouse-Search-Version': '2'}
        turn = self.client.post(f'{BASE}/threads/{tid}/turns', headers=headers,
            json={'library_id': 'family-a', 'request_id': rid,
                  'expected_revision': 0, 'text': 'find photos'})
        self.assertEqual(turn.status_code, 200, turn.text)
        self.assertEqual(turn.json()['result']['version'], 2)
        _, downgraded = self.speak(tid, rid)
        self.assertEqual(downgraded.status_code, 409)
        self.assertEqual(self.tts.calls, [])

        def speak_v2():
            speech_headers = self.headers(request_id=new_id(), parent_id=rid) | {
                'X-PhotoHouse-Search-Version': '2'}
            return self.client.post(f'{BASE}/threads/{tid}/requests/{rid}/speech',
                headers=speech_headers, json={'library_id': 'family-a', 'expected_revision': 1})

        audio = speak_v2()
        self.assertEqual(audio.status_code, 200, audio.text if audio.status_code != 200 else '')
        self.assertEqual(audio.content, self.tts.audio)
        self.tts.on_synthesize = lambda: self.update('''INSERT INTO access_stories
            VALUES('synthetic-note',101,'family-a','one',1,'Changed','New source',1,0)''')
        changed = speak_v2()
        self.assertEqual(changed.status_code, 409)
        self.assertNotEqual(changed.headers.get('content-type'), 'audio/wav')


if __name__ == '__main__':
    unittest.main()

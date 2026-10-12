"""Opt-in saved-memory assistant transport keeps recovery and scope safe."""
from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

SECURITY = Path(__file__).resolve().parent
ROOT = SECURITY.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(SECURITY))

from fastapi.testclient import TestClient
from app.access import assistant_workspace_transport as workspace_transport
from app.access import discovery as discovery_module
from app.access.assistant_journal import initialize as initialize_journal
from app.access.assistant_workspace_store import RETENTION_SECONDS, initialize_v2
from app.access.assistant_speech import LocalAssistantTts
from app.access.discovery_provider import MemoryIndexProvider
from app.access.discovery_transport import DiscoveryRuntime
from app.access.service import AccessService
from app.access.transport import AccessRuntime
from app.main import create_app
import prepare_access_discovery_index as index_producer
import test_assistant_saved_memory_tool as tool_fixture
from test_assistant_workspace_reply_speech import valid_audio

ORIGIN = 'https://photohouse.example.test'
BASE = '/assistant/workspace/v1'
ACCEPTS = ['saved_memory_cards_v1']


def new_id():
    return str(uuid.uuid4())


class FakeTts(LocalAssistantTts):
    def __init__(self):
        self.calls = []
        self.audio = valid_audio()

    def synthesize(self, words, language):
        self.calls.append((words, language))
        return self.audio


class AssistantSavedMemoryHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tool_fixture.AssistantSavedMemoryToolTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        tool_fixture.AssistantSavedMemoryToolTests.tearDownClass()

    def setUp(self):
        self.helper = tool_fixture.AssistantSavedMemoryToolTests()
        self.helper.setUp()
        self.addCleanup(self.helper.doCleanups)
        self.library_fixture = self.helper.library_fixture
        self.token = self.helper.owner
        self.temp = tempfile.TemporaryDirectory(prefix='saved-memory-http-')
        self.addCleanup(self.temp.cleanup)
        private_root = Path(self.temp.name).resolve()
        self.workspace = initialize_v2(private_root / 'workspace.sqlite',
                                       clock=lambda: self.library_fixture.now)
        self.journal = initialize_journal(private_root / 'journal.sqlite')
        self.tts = FakeTts()
        self.access = AccessRuntime(self.connection, ORIGIN,
                                    clock=lambda: self.library_fixture.now)
        with self.library_fixture.connection() as db:
            domain = AccessService(db, clock=lambda: self.library_fixture.now)
            self.account = domain.profile(self.token)['account_id']
            index, _catalog = index_producer.derive(db, 'family-a', '1')
        self.discovery = DiscoveryRuntime(
            self.access, MemoryIndexProvider((index,)), discovery_module.ReadBudget())
        self._make_client(enabled=False)

    @contextmanager
    def connection(self):
        with self.library_fixture.connection() as db:
            db.execute('PRAGMA query_only=ON')
            yield db

    def _make_client(self, *, enabled):
        self.app = create_app(
            access_runtime=self.access, discovery_runtime=self.discovery,
            assistant_enabled=True, memory_collaboration_enabled=True,
            assistant_saved_memory_cards_enabled=enabled,
            assistant_workspace_store=self.workspace, assistant_journal=self.journal,
            assistant_tts=self.tts, assistant_reply_speech_enabled=True)
        self.client = TestClient(self.app, base_url=ORIGIN)
        self.addCleanup(self.client.close)

    def enable(self):
        self.client.close()
        self._make_client(enabled=True)

    def request(self, method, path, *, body=None, token=None, headers=None):
        selected = {'Authorization': 'Bearer ' + (token or self.token)}
        if headers:
            selected.update(headers)
        return self.client.request(method, BASE + path, json=body, headers=selected)

    def thread(self):
        response = self.request('POST', '/threads', body={'library_id': 'family-a'})
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()['thread']

    def turn(self, thread_id, *, request_id=None, revision=0, text='find photos',
             accepts=None, token=None):
        body = {'library_id': 'family-a', 'request_id': request_id or new_id(),
                'expected_revision': revision, 'text': text}
        if accepts is not None:
            body['accepts'] = accepts
        return self.request('POST', f'/threads/{thread_id}/turns', body=body, token=token)

    def capabilities(self, *, token=None, path='/saved-memory-capabilities?library_id=family-a'):
        return self.request('GET', path, token=token)

    def _seed_story_and_memoir(self):
        story = self.helper._save_story('Lake picnic story', 'We packed picnic food.')
        memoir = self.helper._save_memoir('Lake picnic memoir', 'A quiet picnic opening.', story['id'])
        return story, memoir

    def test_flag_dependencies_and_exact_separate_capability_shape(self):
        self.assertEqual(self.capabilities().json(), {'version': 1, 'available': False})
        with self.assertRaisesRegex(ValueError, 'Saved-memory cards require'):
            create_app(access_runtime=self.access, assistant_enabled=True,
                       assistant_saved_memory_cards_enabled=True,
                       assistant_workspace_store=self.workspace)
        with self.assertRaisesRegex(ValueError, 'Saved-memory cards require'):
            create_app(access_runtime=self.access, assistant_enabled=True,
                       memory_collaboration_enabled=True,
                       assistant_saved_memory_cards_enabled=True)

        self.enable()
        response = self.capabilities()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.json()), {'version', 'available'})
        self.assertEqual(response.json(), {'version': 1, 'available': True})
        self.app.state.memory_retention_healthy = False
        self.assertEqual(self.capabilities().json(), {'version': 1, 'available': False})

    def test_capability_probe_requires_authorized_current_library(self):
        self.enable()
        unauthenticated = self.client.get(BASE + '/saved-memory-capabilities?library_id=family-a')
        self.assertEqual(unauthenticated.status_code, 401)
        foreign = self.capabilities(token=self.library_fixture.other_token)
        self.assertIn(foreign.status_code, (401, 404))
        self.assertEqual(self.client.get(BASE + '/saved-memory-capabilities?library_id=family-a&extra=1',
                         headers={'Authorization': 'Bearer ' + self.token}).status_code, 400)

    def test_old_turn_body_stays_media_only_and_malformed_or_disabled_opt_in_fails_before_ledger(self):
        thread = self.thread()
        old = self.turn(thread['thread_id'], text='find photos')
        self.assertEqual(old.status_code, 200, old.text)
        self.assertEqual(old.json()['result']['kind'], 'results')
        self.assertNotIn('memory_cards', old.json()['result'])

        malformed = self.turn(thread['thread_id'], request_id=new_id(), revision=1,
                              accepts=['saved_memory_cards_v1', 'unknown'])
        self.assertEqual(malformed.status_code, 400, malformed.text)
        malformed_type = self.turn(thread['thread_id'], request_id=new_id(), revision=1,
                                   accepts='saved_memory_cards_v1')
        self.assertEqual(malformed_type.status_code, 400, malformed_type.text)
        before = self.workspace.get_thread(self.account, 'family-a', thread['thread_id'])
        self.assertEqual(before['thread']['revision'], 1)
        self.assertEqual(len(before['exchanges']), 1)

        refused = self.turn(thread['thread_id'], request_id=new_id(), revision=1,
                            text='find saved story picnic', accepts=ACCEPTS)
        self.assertEqual(refused.status_code, 503, refused.text)
        after = self.workspace.get_thread(self.account, 'family-a', thread['thread_id'])
        self.assertEqual(after['thread']['revision'], 1)
        self.assertEqual(len(after['exchanges']), 1)

    def test_enabled_story_and_memoir_return_cards_once_then_only_legacy_recovery(self):
        story, memoir = self._seed_story_and_memoir()
        self.enable()
        thread = self.thread()
        validator = workspace_transport._validate_memory_outcome
        with patch.object(workspace_transport, '_validate_memory_outcome', wraps=validator) as validate:
            story_id = new_id()
            story_turn = self.turn(thread['thread_id'], request_id=story_id,
                                   text='find saved story picnic', accepts=ACCEPTS)
            self.assertEqual(story_turn.status_code, 200, story_turn.text)
            story_result = story_turn.json()['result']
            self.assertEqual(story_result['kind'], 'memory_cards')
            self.assertEqual([card['id'] for card in story_result['memory_cards']], [story['id']])
            self.assertEqual(story_result['effect'], None)
            self.assertEqual(story_result['items'], [])
            self.assertGreaterEqual(validate.call_count, 2)

        recovered = self.request('GET',
            f"/threads/{thread['thread_id']}/requests/{story_id}?library_id=family-a")
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertTrue(recovered.json()['recovered'])
        self.assertEqual(recovered.json()['result']['kind'], 'results')
        self.assertNotIn('memory_cards', recovered.json()['result'])
        self.assertEqual(recovered.json()['result']['reply'], story_result['reply'])

        with patch('app.access.assistant_saved_memory_tool.AssistantSavedMemoryTool.run',
                   side_effect=AssertionError('same request ID must not search again')) as no_recompute:
            # Existing-only replay never re-runs search even when the fresh
            # response was lost or the same request is submitted again.
            replay = self.turn(thread['thread_id'], request_id=story_id,
                               text='find saved story picnic', accepts=ACCEPTS)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertTrue(replay.json()['recovered'])
            self.assertNotIn('memory_cards', replay.json()['result'])
            no_recompute.assert_not_called()

        memoir_id = new_id()
        memoir_turn = self.turn(thread['thread_id'], request_id=memoir_id, revision=1,
                                text='find memoir picnic', accepts=ACCEPTS)
        self.assertEqual(memoir_turn.status_code, 200, memoir_turn.text)
        self.assertEqual(memoir_turn.json()['result']['kind'], 'memory_cards')
        self.assertEqual([card['id'] for card in memoir_turn.json()['result']['memory_cards']],
                         [memoir['id']])
        self.assertIsNone(memoir_turn.json()['result']['effect'])

        history = self.request('GET', f"/threads/{thread['thread_id']}?library_id=family-a")
        self.assertEqual(history.status_code, 200, history.text)
        self.assertNotIn(story['id'], history.text)
        self.assertNotIn(memoir['id'], history.text)
        kinds = {item['type'] for exchange in history.json()['exchanges'] for item in exchange['cards']}
        self.assertTrue({'story', 'memoir'} <= kinds)

    def test_same_id_negotiation_replay_is_readback_even_when_feature_is_disabled(self):
        self._seed_story_and_memoir()
        self.enable()
        thread = self.thread()
        request_id = new_id()
        fresh = self.turn(thread['thread_id'], request_id=request_id,
                          text='find saved story picnic', accepts=ACCEPTS)
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.app.state.assistant_saved_memory_cards_enabled = False
        for accepts in (None, ACCEPTS, ['unknown'], 'changed'):
            replay = self.turn(thread['thread_id'], request_id=request_id,
                               text='find saved story picnic', accepts=accepts)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertTrue(replay.json()['recovered'])
            self.assertNotIn('memory_cards', replay.json()['result'])
        changed_text = self.turn(thread['thread_id'], request_id=request_id,
                                 text='find saved story changed', revision=0, accepts=ACCEPTS)
        self.assertEqual(changed_text.status_code, 409, changed_text.text)
        changed_revision = self.turn(thread['thread_id'], request_id=request_id,
                                     text='find saved story picnic', revision=1, accepts=ACCEPTS)
        self.assertEqual(changed_revision.status_code, 409, changed_revision.text)

    def test_expired_thread_and_foreign_scope_cannot_submit_or_read_memory(self):
        self.enable()
        thread = self.thread()
        refused = self.turn(thread['thread_id'], text='find saved story picnic',
                            accepts=ACCEPTS, token=self.library_fixture.other_token)
        self.assertEqual(refused.status_code, 401, refused.text)
        self.workspace.clock = lambda: self.library_fixture.now + RETENTION_SECONDS + 1
        expired = self.turn(thread['thread_id'], text='find saved story picnic', accepts=ACCEPTS)
        self.assertEqual(expired.status_code, 404, expired.text)
        self.assertEqual(self.capabilities().status_code, 200)

    def test_memory_completion_clears_previous_media_context_and_speech_is_refused(self):
        story, _memoir = self._seed_story_and_memoir()
        self.enable()
        thread = self.thread()
        media = self.turn(thread['thread_id'], text='find photos')
        self.assertEqual(media.status_code, 200, media.text)
        self.assertIsNotNone(media.json()['result']['context'])
        with self.workspace.connection() as db:
            before = db.execute('SELECT context_json FROM thread_context WHERE thread_id=?',
                                (thread['thread_id'],)).fetchone()
        self.assertIsNotNone(before)

        memory_id = new_id()
        memory = self.turn(thread['thread_id'], request_id=memory_id, revision=1,
                           text='find saved story picnic', accepts=ACCEPTS)
        self.assertEqual(memory.status_code, 200, memory.text)
        with self.workspace.connection() as db:
            after = db.execute('SELECT context_json FROM thread_context WHERE thread_id=?',
                               (thread['thread_id'],)).fetchone()
        self.assertIsNone(after)

        speech = self.request('POST',
            f"/threads/{thread['thread_id']}/requests/{memory_id}/speech",
            body={'library_id': 'family-a', 'expected_revision': 2},
            headers={'X-PhotoHouse-Request-Id': new_id(),
                     'X-PhotoHouse-Parent-Request-Id': memory_id})
        self.assertEqual(speech.status_code, 400, speech.text)
        self.assertEqual(self.tts.calls, [])

    def test_source_change_after_completion_withholds_cards_and_recovers_only_safe_summary(self):
        story, _memoir = self._seed_story_and_memoir()
        self.enable()
        thread = self.thread()
        ident = new_id()
        validator = workspace_transport._validate_memory_outcome
        calls = []
        def change_before_response(*args):
            calls.append(True)
            if len(calls) == 2:
                self.library_fixture.mutate("UPDATE captions SET text='changed synthetic evidence' WHERE id=101")
            return validator(*args)
        with patch.object(workspace_transport, '_validate_memory_outcome', side_effect=change_before_response):
            fresh = self.turn(thread['thread_id'], request_id=ident,
                              text='find saved story picnic', accepts=ACCEPTS)
        self.assertEqual(fresh.status_code, 409, fresh.text)
        self.assertNotIn(story['id'], fresh.text)
        recovered = self.request('GET', f"/threads/{thread['thread_id']}/requests/{ident}?library_id=family-a")
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertTrue(recovered.json()['recovered'])
        self.assertNotIn('memory_cards', recovered.json()['result'])
        self.assertNotIn(story['id'], recovered.text)

    def test_source_withdrawal_before_completion_fails_without_storing_family_card_text(self):
        story, _memoir = self._seed_story_and_memoir()
        self.enable()
        thread = self.thread()
        ident = new_id()
        validator = workspace_transport._validate_memory_outcome
        def withdraw_before_completion(*args):
            self.library_fixture.mutate("UPDATE assets SET status='deleted' WHERE id=101")
            return validator(*args)
        with patch.object(workspace_transport, '_validate_memory_outcome', side_effect=withdraw_before_completion):
            fresh = self.turn(thread['thread_id'], request_id=ident,
                              text='find saved story picnic', accepts=ACCEPTS)
        self.assertEqual(fresh.status_code, 401, fresh.text)
        recovered = self.request('GET', f"/threads/{thread['thread_id']}/requests/{ident}?library_id=family-a")
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['status'], 'failed')
        self.assertEqual(recovered.json()['error'], 'access_denied')
        self.assertIsNone(recovered.json()['result'])
        self.assertNotIn(story['id'], recovered.text)


if __name__ == '__main__':
    unittest.main()

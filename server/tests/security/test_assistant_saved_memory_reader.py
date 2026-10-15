"""Protected full-reader handoff for saved-memory assistant cards."""
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager

SECURITY = Path(__file__).resolve().parent
ROOT = SECURITY.parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(SECURITY))

from app.access import assistant_workspace_transport as workspace_transport
from app.access import discovery as discovery_module
from app.access.assistant_workspace_store import initialize_v2
from app.access.discovery_provider import MemoryIndexProvider
from app.access.discovery_transport import DiscoveryRuntime
from app.access.memory_books import MemoryBooks
from app.access.memory_stories import MemoryStories
from app.access.service import AccessService
from app.access.transport import AccessRuntime
from app.main import create_app
import prepare_access_discovery_index as index_producer
import test_assistant_saved_memory_tool as tool_fixture

BASE = '/assistant/workspace/v1'
ACCEPTS = ['saved_memory_cards_v1']


def new_id():
    return str(uuid.uuid4())


class AssistantSavedMemoryReaderTests(unittest.TestCase):
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
        self.temp = tempfile.TemporaryDirectory(prefix='saved-memory-reader-http-')
        self.addCleanup(self.temp.cleanup)
        private_root = Path(self.temp.name).resolve()
        self.workspace = initialize_v2(private_root / 'workspace.sqlite',
                                       clock=lambda: self.library_fixture.now)
        self.access = AccessRuntime(self.connection, 'https://photohouse.example.test',
                                    clock=lambda: self.library_fixture.now)
        with self.library_fixture.connection() as db:
            index, _catalog = index_producer.derive(db, 'family-a', '1')
            self.account = AccessService(db, clock=lambda: self.library_fixture.now).profile(
                self.token)['account_id']
        discovery = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)),
                                     discovery_module.ReadBudget())
        self.app = create_app(access_runtime=self.access, discovery_runtime=discovery,
            assistant_enabled=True, memory_collaboration_enabled=True,
            assistant_saved_memory_cards_enabled=True,
            assistant_workspace_store=self.workspace)
        from fastapi.testclient import TestClient
        self.client = TestClient(self.app, base_url='https://photohouse.example.test')
        self.addCleanup(self.client.close)

    @contextmanager
    def connection(self):
        with self.library_fixture.connection() as db:
            db.execute('PRAGMA query_only=ON')
            yield db

    def request(self, method, path, *, token=None, body=None):
        headers = {'Authorization': 'Bearer ' + (token or self.token)}
        return self.client.request(method, BASE + path, headers=headers, json=body)

    def thread(self):
        response = self.request('POST', '/threads', body={'library_id': 'family-a'})
        self.assertIn(response.status_code, (200, 201), response.text)
        return response.json()['thread']

    def turn(self, thread_id, *, request_id, text, accepts):
        return self.request('POST', f'/threads/{thread_id}/turns', body={
            'library_id': 'family-a', 'request_id': request_id,
            'expected_revision': 0, 'text': text, 'accepts': accepts})

    def story_and_memoir_turn(self, *, memoir=False):
        marker = uuid.uuid4().hex[:8]
        phrase = 'picnic' + marker
        story = self.helper._save_story('Lake picnic ' + marker + ' story',
                                        'We packed ' + phrase + ' food.')
        saved_memoir = self.helper._save_memoir('Lake picnic ' + marker + ' memoir',
                                               'A quiet ' + phrase + ' opening.', story['id'])
        thread = self.thread()
        request_id = new_id()
        text = ('find memoir ' if memoir else 'find saved story ') + phrase
        turn = self.turn(thread['thread_id'], request_id=request_id,
                         text=text, accepts=ACCEPTS)
        self.assertEqual(turn.status_code, 200, turn.text)
        expected_id = saved_memoir['id'] if memoir else story['id']
        cards = turn.json()['result']['memory_cards']
        self.assertEqual([card['id'] for card in cards], [expected_id])
        return thread, request_id, story, saved_memoir, turn.json()['revision']

    def reader(self, thread, request_id, revision, ordinal='0', *, library='family-a',
               token=None, suffix=''):
        return self.request('GET',
            f'/threads/{thread}/requests/{request_id}/memory-cards/{ordinal}'
            f'?library_id={library}&expected_revision={revision}{suffix}', token=token)

    def test_reader_capability_is_separate_exact_and_flag_gated(self):
        response = self.request('GET', '/saved-memory-reader-capabilities?library_id=family-a')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'version': 1, 'available': True})
        self.assertEqual(set(response.json()), {'version', 'available'})
        self.assertIn('no-store', response.headers.get('cache-control', '').lower())
        self.app.state.assistant_saved_memory_cards_enabled = False
        disabled = self.request('GET', '/saved-memory-reader-capabilities?library_id=family-a')
        self.assertEqual(disabled.json(), {'version': 1, 'available': False})

    def test_story_and_memoir_handoff_returns_existing_authorized_reader_payload(self):
        for memoir in (False, True):
            with self.subTest(kind='memoir' if memoir else 'story'):
                thread, request_id, story, book, revision = self.story_and_memoir_turn(memoir=memoir)
                response = self.reader(thread['thread_id'], request_id, revision)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertEqual(set(body), {'version', 'kind', 'reader'})
                self.assertEqual(body['version'], 1)
                self.assertEqual(body['kind'], 'memoir' if memoir else 'story')
                with self.library_fixture.connection() as db:
                    access = AccessService(db, clock=lambda: self.library_fixture.now)
                    expected = (MemoryBooks(access).get(self.token, 'family-a', book['id'])
                                if memoir else
                                MemoryStories(access).get(self.token, 'family-a', story['id']))
                self.assertEqual(body['reader'], expected)
                self.assertEqual(response.headers.get('x-content-type-options'), 'nosniff')
                self.assertIn('no-store', response.headers.get('cache-control', '').lower())

    def test_turn_scope_revision_ordinal_and_query_are_strict(self):
        thread, request_id, _story, _book, revision = self.story_and_memoir_turn()
        thread_id = thread['thread_id']
        self.assertEqual(self.reader(thread_id, request_id, revision, ordinal='1').status_code, 404)
        for ordinal in ('00', '+0', '-1', '12', '1e0'):
            with self.subTest(ordinal=ordinal):
                self.assertIn(self.reader(thread_id, request_id, revision,
                                          ordinal=ordinal).status_code, (400, 403))
        for value in ('0', '01', '+1', '-1', '9223372036854775807', '99999999999999999999'):
            with self.subTest(revision=value):
                self.assertEqual(self.reader(thread_id, request_id, value).status_code, 400)
        self.assertEqual(self.reader(thread_id, request_id, '2').status_code, 409)
        self.assertEqual(self.reader(thread_id, request_id, revision,
                                     suffix='&expected_revision=1').status_code, 400)
        foreign = self.reader(thread_id, request_id, revision,
                              token=self.library_fixture.other_token)
        self.assertIn(foreign.status_code, (401, 404))
        other_member = self.reader(thread_id, request_id, revision,
                                   token=self.library_fixture.member_token)
        self.assertEqual(other_member.status_code, 404, other_member.text)
        self.assertEqual(self.reader(new_id(), request_id, revision).status_code, 404)
        self.assertEqual(self.reader(thread_id, new_id(), revision).status_code, 404)
        self.assertEqual(self.reader(thread_id, request_id, revision,
                                     library='family-b').status_code, 401)

    def test_current_source_and_memoir_child_changes_conflict(self):
        thread, request_id, story, book, revision = self.story_and_memoir_turn()
        self.library_fixture.mutate(
            "UPDATE captions SET text='changed synthetic caption' WHERE id=101")
        changed_story = self.reader(thread['thread_id'], request_id, revision)
        self.assertEqual(changed_story.status_code, 409, changed_story.text)

        thread, request_id, story, book, revision = self.story_and_memoir_turn(memoir=True)
        body = self.helper.fixture.body()
        body.update(revision='1', title='Changed child story')
        edited = self.helper.fixture.save(body, story['id'])
        self.assertEqual(edited.status_code, 200, edited.text)
        changed_book = self.reader(thread['thread_id'], request_id, revision)
        self.assertEqual(changed_book.status_code, 409, changed_book.text)

    def test_withdrawn_source_is_hidden(self):
        thread, request_id, _story, _book, revision = self.story_and_memoir_turn()
        self.library_fixture.mutate(
            "UPDATE assets SET status='deleted' WHERE id IN (101,102)")
        withdrawn = self.reader(thread['thread_id'], request_id, revision)
        self.assertEqual(withdrawn.status_code, 404, withdrawn.text)

    def test_feature_or_stored_reference_corruption_denies_handoff(self):
        thread, request_id, _story, _book, revision = self.story_and_memoir_turn()
        with self.workspace.connection() as db:
            row = db.execute('SELECT card_refs FROM exchanges WHERE request_id=?',
                             (request_id,)).fetchone()
            refs = json.loads(row[0])
            refs.append({'type': 'media', 'id': '101', 'revision': 'a' * 64,
                         'fingerprint': 'a' * 64})
            db.execute('UPDATE exchanges SET card_refs=? WHERE request_id=?',
                       (json.dumps(refs), request_id))
            db.commit()
        mixed = self.reader(thread['thread_id'], request_id, revision)
        self.assertEqual(mixed.status_code, 404, mixed.text)

        thread, request_id, _story, _book, revision = self.story_and_memoir_turn()
        self.app.state.assistant_saved_memory_cards_enabled = False
        disabled = self.reader(thread['thread_id'], request_id, revision)
        self.assertEqual(disabled.status_code, 503, disabled.text)

    def test_feature_flag_revoked_during_source_read_withholds_payload(self):
        thread, request_id, _story, _book, revision = self.story_and_memoir_turn()
        reader = workspace_transport._saved_memory_reader
        def revoke(*args, **kwargs):
            result = reader(*args, **kwargs)
            self.app.state.assistant_saved_memory_cards_enabled = False
            return result
        with patch.object(workspace_transport, '_saved_memory_reader', side_effect=revoke):
            response = self.reader(thread['thread_id'], request_id, revision)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('reader', response.json())

    def test_principal_and_completed_exchange_are_rechecked_after_source_read(self):
        thread, request_id, _story, _book, revision = self.story_and_memoir_turn()
        reader = workspace_transport._saved_memory_reader

        def advance_exchange(*args, **kwargs):
            result = reader(*args, **kwargs)
            with self.workspace.connection() as db:
                db.execute('UPDATE exchanges SET revision=revision+1 WHERE request_id=?',
                           (request_id,))
                db.commit()
            return result

        with patch.object(workspace_transport, '_saved_memory_reader',
                          side_effect=advance_exchange):
            response = self.reader(thread['thread_id'], request_id, revision)
        self.assertEqual(response.status_code, 409, response.text)
        self.assertNotIn('reader', response.json())

        thread, request_id, _story, _book, revision = self.story_and_memoir_turn()
        principal_calls = []
        async def switched_principal(*_args, **_kwargs):
            principal_calls.append(True)
            return self.account if len(principal_calls) == 1 else 'different-account'

        with patch.object(workspace_transport, '_principal', side_effect=switched_principal):
            response = self.reader(thread['thread_id'], request_id, revision)
        self.assertEqual(response.status_code, 401, response.text)
        self.assertNotIn('reader', response.json())

    def test_reader_response_is_capped_at_one_mib(self):
        thread, request_id, _story, _book, revision = self.story_and_memoir_turn()
        with patch('app.access.assistant_memory_discovery.AssistantMemoryDiscovery.read_reference',
                   return_value={'payload': 'x' * (1024 * 1024)}):
            response = self.reader(thread['thread_id'], request_id, revision)
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('reader', response.json())


if __name__ == '__main__':
    unittest.main()

"""Negotiated voice/view actions bind the current complete saved-memory cohort."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SECURITY = Path(__file__).resolve().parent
sys.path.insert(0, str(SECURITY))
import test_assistant_saved_memory_http as fixtures
from app.access.assistant_memory_followup import SavedMemoryFollowup, parse_saved_memory_action
from app.access import assistant_workspace_transport as transport

ACCEPTS = ['saved_memory_cards_v1', 'saved_memory_actions_v1']


class MemoryActionParserTests(unittest.TestCase):
    def test_complete_chinese_and_english_commands(self):
        for text, mode, ordinal in (
            ('读第一篇回忆', 'read_opening', 1), ('请朗读第二个故事的开篇。', 'read_opening', 2),
            ('帮我打开第三本回忆录', 'open', 3), ('查看第12段回忆', 'open', 12),
            ('Read the second story!', 'read_opening', 2), ('please open 1st memoir', 'open', 1),
            ('open the 99th saved memory', 'open', 99), ('朗读开篇', 'read_opening', None),
            ('open this story', 'open', None)):
            with self.subTest(text=text):
                self.assertEqual(parse_saved_memory_action(text), SavedMemoryFollowup(mode, ordinal))

    def test_negations_suffix_mutations_and_arbitrary_text_do_not_dispatch(self):
        for text in ('不要读第一篇回忆', '读第一篇回忆然后删除', '打开第二个故事并分享',
                     'read the second story and delete it', 'do not open this story',
                     'I said open this story yesterday', '介绍这个故事', '', None):
            with self.subTest(text=text):
                self.assertIsNone(parse_saved_memory_action(text))


class MemoryActionHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.AssistantSavedMemoryHttpTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixtures.AssistantSavedMemoryHttpTests.tearDownClass()

    def setUp(self):
        self.fx = fixtures.AssistantSavedMemoryHttpTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)

    def search(self, count=2):
        for index in range(count):
            self.fx.helper._save_story(f'{index} picnic story', f'SOURCE WORDS {index}')
        self.fx.enable()
        self.thread = self.fx.thread()
        self.parent = fixtures.new_id()
        response = self.fx.turn(self.thread['thread_id'], request_id=self.parent,
            text='find saved story picnic', accepts=ACCEPTS)
        self.assertEqual(response.status_code, 200, response.text)
        self.cards = response.json()['result']['memory_cards']
        return response

    def action(self, text, *, parent=None, revision=1, accepts=ACCEPTS, request_id=None):
        return self.fx.turn(self.thread['thread_id'], request_id=request_id,
            revision=revision, text=text, accepts=accepts,
            memory_parent={'request_id': parent or self.parent, 'revision': revision})

    def test_capability_is_authenticated_exact_and_fails_closed(self):
        self.fx.enable()
        path = '/saved-memory-action-capabilities?library_id=family-a'
        response = self.fx.request('GET', path)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {'version': 1, 'available': True})
        self.assertIn('no-store', response.headers['cache-control'])
        self.assertIn(self.fx.request('GET', path, token='invalid').status_code, (401, 403))
        self.fx.app.state.assistant_saved_memory_cards_enabled = False
        self.assertEqual(self.fx.request('GET', path).json(), {'version': 1, 'available': False})

    def test_action_preserves_order_and_new_parent_can_read_exact_source(self):
        self.search()
        request_id = fixtures.new_id()
        response = self.action('读第二个故事', request_id=request_id)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['memory_action'], {'type': 'read_opening', 'ordinal': 1})
        self.assertEqual(result['context']['references'], [{key: card[key] for key in ('kind', 'id', 'revision', 'source_revision')} for card in self.cards])
        self.assertIsNone(result['effect'])
        speech = self.fx.request('POST',
            f"/threads/{self.thread['thread_id']}/requests/{request_id}/memory-cards/1/speech",
            body={'library_id': 'family-a', 'expected_revision': 2}, headers={
                'X-PhotoHouse-Request-Id': fixtures.new_id(), 'X-PhotoHouse-Parent-Request-Id': request_id})
        self.assertEqual(speech.status_code, 200, speech.text)
        self.assertEqual(self.fx.tts.calls[-1][0], result['memory_cards'][1]['excerpt'])
        stale = self.fx.request('GET',
            f"/threads/{self.thread['thread_id']}/requests/{self.parent}/memory-cards/1?library_id=family-a&expected_revision=1")
        self.assertEqual(stale.status_code, 409, stale.text)

    def test_actions_are_not_persisted_or_recovered_and_source_text_is_transient(self):
        self.search()
        ident = fixtures.new_id()
        response = self.action('打开第二个故事', request_id=ident)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['result']['memory_action'], {'type': 'open', 'ordinal': 1})
        recovered = self.action('打开第二个故事', request_id=ident, accepts=None)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertTrue(recovered.json()['recovered'])
        self.assertNotIn('memory_action', recovered.json()['result'])
        with self.fx.workspace.connection() as db:
            stored = json.dumps([dict(row) for row in db.execute('SELECT result_summary FROM turn_requests')])
        self.assertNotIn('memory_action', stored)
        self.assertNotIn('SOURCE WORDS', stored)
        self.assertNotIn('picnic story', stored)

    def test_ambiguity_retains_cohort_for_next_ordinal_and_never_selects_first(self):
        self.search()
        ident = fixtures.new_id()
        ambiguous = self.action('读这个故事', request_id=ident)
        self.assertEqual(ambiguous.status_code, 200, ambiguous.text)
        result = ambiguous.json()['result']
        self.assertEqual(result['context']['references'], [{key: card[key] for key in ('kind', 'id', 'revision', 'source_revision')} for card in self.cards])
        self.assertNotIn('memory_action', result)
        chosen = self.action('读第二个故事', parent=ident, revision=2)
        self.assertEqual(chosen.status_code, 200, chosen.text)
        self.assertEqual(chosen.json()['result']['memory_action']['ordinal'], 1)

    def test_out_of_range_and_missing_parent_clarify_without_action(self):
        self.search()
        response = self.action('打开第99个故事')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual([card['id'] for card in response.json()['result']['memory_cards']], [card['id'] for card in self.cards])
        self.assertNotIn('memory_action', response.json()['result'])
        missing = self.fx.turn(self.thread['thread_id'], revision=2,
            text='读第一个故事', accepts=ACCEPTS)
        self.assertEqual(missing.status_code, 200, missing.text)
        self.assertEqual(missing.json()['result']['kind'], 'clarification')
        self.assertNotIn('memory_action', missing.json()['result'])

    def test_old_client_never_receives_action_and_unknown_negotiation_is_invalid(self):
        self.search(1)
        old = self.action('读第一个故事', accepts=['saved_memory_cards_v1'])
        self.assertEqual(old.status_code, 200, old.text)
        self.assertNotIn('memory_action', old.json()['result'])
        invalid = self.fx.turn(self.thread['thread_id'], revision=2, text='find photos',
            accepts=['saved_memory_actions_v1', 'saved_memory_cards_v1'])
        self.assertEqual(invalid.status_code, 400, invalid.text)
        legacy = self.fx.turn(self.thread['thread_id'], revision=2, text='find photos')
        self.assertEqual(legacy.status_code, 200, legacy.text)

    def test_whole_parent_cohort_rechecked_before_commit(self):
        self.search()
        original = transport._validate_memory_outcome
        def mutate_parent(*args):
            value = original(*args)
            with self.fx.workspace.connection() as db:
                db.execute('UPDATE exchanges SET card_refs=? WHERE request_id=?', ('[]', self.parent))
                db.commit()
            return value
        with patch.object(transport, '_validate_memory_outcome', side_effect=mutate_parent):
            response = self.action('打开第一个故事')
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.fx.workspace.get_thread(self.fx.account, 'family-a',
            self.thread['thread_id'])['thread']['revision'], 1)

    def test_changed_unselected_source_blocks_the_selected_action(self):
        self.search()
        body = self.fx.helper.fixture.body()
        body.update(revision=self.cards[1]['revision'], title='Changed unselected story')
        edited = self.fx.helper.fixture.save(body, ident=self.cards[1]['id'])
        self.assertEqual(edited.status_code, 200, edited.text)
        response = self.action('读第一个故事')
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(self.fx.tts.calls, [])
        self.assertEqual(self.fx.workspace.get_thread(self.fx.account, 'family-a',
            self.thread['thread_id'])['thread']['revision'], 1)

    def test_reader_rechecks_unselected_source_after_action_completion(self):
        self.search()
        ident = fixtures.new_id()
        response = self.action('打开第一个故事', request_id=ident)
        self.assertEqual(response.status_code, 200, response.text)
        body = self.fx.helper.fixture.body()
        body.update(revision=self.cards[1]['revision'], title='Changed after the action')
        edited = self.fx.helper.fixture.save(body, ident=self.cards[1]['id'])
        self.assertEqual(edited.status_code, 200, edited.text)
        reader = self.fx.request('GET',
            f"/threads/{self.thread['thread_id']}/requests/{ident}/memory-cards/0?library_id=family-a&expected_revision=2")
        self.assertEqual(reader.status_code, 409, reader.text)


if __name__ == '__main__':
    unittest.main()

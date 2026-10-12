"""Read-only domain projections for opted-in saved-memory searches."""
import json
import sys
import unittest
import uuid
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import patch

SECURITY = Path(__file__).resolve().parent
sys.path.insert(0, str(SECURITY))

import test_memory_stories as story_fixture
from app.access import assistant_workspace_store as workspace_store
from app.access.assistant_memory_discovery import MemoryReference, MemorySearchPage
from app.access.assistant_saved_memory_tool import (AssistantSavedMemoryTool,
                                                    MAX_RESULT_BYTES)
from app.access.memory_books import MemoryBooks
from app.access.memory_stories import MemoryStories
from app.access.service import AccessDenied, AccessService
from app.access.transport import TransportError


class AssistantSavedMemoryToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        story_fixture.MemoryStoryTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        story_fixture.MemoryStoryTests.tearDownClass()

    def setUp(self):
        self.fixture = story_fixture.MemoryStoryTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.library_fixture = self.fixture.f
        self.owner = self.library_fixture.owner_token

    def _save_story(self, title, narration):
        headers = {'Authorization': 'Bearer ' + self.owner}
        preview = self.fixture.client.post(
            '/story-workspace/preview?library=family-a', headers=headers,
            json={'asset_ids': '102,101', 'title': title,
                  'theme': 'everyday', 'language': 'en'})
        self.assertEqual(preview.status_code, 200, preview.text)
        draft = preview.json()
        draft['chapters'][0]['narration'] = narration
        body = {'title': title, 'theme': draft['theme'], 'language': 'en',
                'asset_ids': ','.join(item['id'] for item in draft['items']),
                'chapters': json.dumps(draft['chapters']),
                'selection_revision': draft['selection_revision'], 'revision': '0',
                'mutation_id': str(uuid.uuid4())}
        saved = self.fixture.save(body, headers=headers)
        self.assertEqual(saved.status_code, 200, saved.text)
        return saved.json()

    def _save_memoir(self, title, introduction, story_id):
        body = {'title': title, 'language': 'en', 'introduction': introduction,
                'story_ids': story_id, 'revision': '0',
                'mutation_id': str(uuid.uuid4())}
        with self.library_fixture.connection() as db:
            access = AccessService(db, clock=lambda: self.library_fixture.now)
            return MemoryBooks(access).save(self.owner, 'family-a', body)

    def _run(self, text, *, locale=None, token=None, library='family-a'):
        with self.library_fixture.connection() as db:
            access = AccessService(db, clock=lambda: self.library_fixture.now)
            return AssistantSavedMemoryTool(access).run(
                self.owner if token is None else token, library, text, locale=locale)

    def test_authorized_story_and_memoir_fresh_summary_and_typed_reference_shapes(self):
        story = self._save_story('Lake picnic story', 'We packed picnic food.')
        memoir = self._save_memoir('Lake picnic memoir', 'A quiet picnic opening.', story['id'])

        story_outcome = self._run('搜索故事 picnic', locale='zh')
        self.assertEqual(story_outcome.total, 1)
        self.assertEqual([ref.kind for ref in story_outcome.references], ['story'])
        story_fresh = story_outcome.fresh_result()
        story_summary = story_outcome.legacy_summary()
        story_refs = story_outcome.store_card_refs()
        self.assertEqual(story_fresh['kind'], 'memory_cards')
        self.assertEqual(story_fresh['memory_cards'][0]['id'], story['id'])
        self.assertEqual(story_fresh['effect'], None)
        self.assertEqual(story_fresh['items'], [])
        self.assertEqual(workspace_store._result_summary(story_summary, 'family-a'), story_summary)
        self.assertEqual(workspace_store._card_refs(story_refs), story_refs)
        self.assertEqual(story_refs[0]['type'], 'story')
        self.assertEqual(story_refs[0]['revision'], story_refs[0]['fingerprint'])
        self.assertEqual(story_refs[0]['revision'], story_outcome.references[0].source_revision)
        self.assertNotIn('Lake picnic', json.dumps(story_summary))

        memoir_outcome = self._run('find memoir picnic', locale='en')
        self.assertEqual(memoir_outcome.total, 1)
        self.assertEqual([ref.kind for ref in memoir_outcome.references], ['memoir'])
        memoir_fresh = memoir_outcome.fresh_result()
        memoir_summary = memoir_outcome.legacy_summary()
        memoir_refs = memoir_outcome.store_card_refs()
        self.assertEqual(memoir_fresh['memory_cards'][0]['id'], memoir['id'])
        self.assertEqual(workspace_store._result_summary(memoir_summary, 'family-a'), memoir_summary)
        self.assertEqual(workspace_store._card_refs(memoir_refs), memoir_refs)

    def test_empty_and_zero_match_outcomes_are_localized_and_authenticated(self):
        clarification = self._run('找回忆', locale='zh')
        self.assertTrue(clarification.clarification)
        self.assertIsNone(clarification.fresh_result()['context'])
        self.assertEqual(clarification.fresh_result()['memory_cards'], [])
        self.assertEqual(clarification.legacy_summary()['kind'], 'clarification')
        self.assertEqual(workspace_store._result_summary(
            clarification.legacy_summary(), 'family-a'), clarification.legacy_summary())
        self.assertEqual(clarification.reply, '请说出要查找的回忆短语。')
        with self.assertRaises(AccessDenied):
            self._run('find memoir', locale='en', token='invalid-session')

        no_match = self._run('找回忆 nonexistentphrase', locale='zh')
        self.assertFalse(no_match.clarification)
        self.assertEqual(no_match.total, 0)
        self.assertFalse(no_match.has_more)
        fresh = no_match.fresh_result()
        self.assertEqual(fresh['context']['references'], [])
        self.assertEqual(fresh['memory_cards'], [])
        self.assertEqual(fresh['total'], 0)
        self.assertFalse(fresh['has_more'])
        self.assertEqual(no_match.legacy_summary()['kind'], 'results')
        self.assertEqual(no_match.legacy_summary()['reply'], fresh['reply'])
        self.assertEqual(workspace_store._result_summary(
            no_match.legacy_summary(), 'family-a'), no_match.legacy_summary())

    def test_full_match_count_and_twelve_card_bound(self):
        for index in range(13):
            self._save_story(f'Picnic memory {index:02d}', 'shared picnic phrase')
        outcome = self._run('find saved story picnic')
        fresh = outcome.fresh_result()
        self.assertEqual(outcome.total, 13)
        self.assertEqual(len(outcome.references), 12)
        self.assertEqual(len(fresh['memory_cards']), 12)
        self.assertTrue(fresh['has_more'])
        self.assertEqual(fresh['total'], 13)
        self.assertIn('first 12', fresh['reply'])
        self.assertEqual([card['id'] for card in fresh['memory_cards']],
                         [ref.id for ref in outcome.references])
        self.assertLessEqual(len(json.dumps(fresh, ensure_ascii=False).encode('utf-8')),
                             MAX_RESULT_BYTES)

    def test_locale_preference_overrides_command_language_and_auto_detects(self):
        self._save_story('Locale picnic', 'picnic story')
        zh = self._run('find saved story missing', locale='zh')
        self.assertEqual(zh.locale, 'zh')
        self.assertTrue(zh.reply.startswith('没有找到'))
        en = self._run('找回忆 missing', locale='en')
        self.assertEqual(en.locale, 'en')
        self.assertTrue(en.reply.startswith('No saved memories'))
        auto_zh = self._run('找回忆')
        auto_en = self._run('find memoir')
        self.assertEqual((auto_zh.locale, auto_en.locale), ('zh', 'en'))
        with self.assertRaises(TransportError):
            self._run('找回忆 missing', locale='fr')

    def test_oversized_or_invalid_source_fields_fail_closed_without_truncation(self):
        valid_ref = MemoryReference('story', str(uuid.uuid4()), '1', 'a' * 64,
                                    'x' * 641, 'bounded excerpt')
        with self.library_fixture.connection() as db:
            access = AccessService(db, clock=lambda: self.library_fixture.now)
            tool = AssistantSavedMemoryTool(access)
            with patch.object(tool.discovery, 'search_page', return_value=MemorySearchPage((valid_ref,), 1, False)):
                with self.assertRaises(TransportError) as raised:
                    tool.run(self.owner, 'family-a', 'find saved story x')
        self.assertEqual(raised.exception.status, 503)

        bad_ref = MemoryReference('story', str(uuid.uuid4()), '1', 'A' * 64,
                                  'valid title', 'valid excerpt')
        with self.library_fixture.connection() as db:
            access = AccessService(db, clock=lambda: self.library_fixture.now)
            tool = AssistantSavedMemoryTool(access)
            with patch.object(tool.discovery, 'search_page', return_value=MemorySearchPage((bad_ref,), 1, False)):
                with self.assertRaises(TransportError) as raised:
                    tool.run(self.owner, 'family-a', 'find saved story x')
        self.assertEqual(raised.exception.status, 503)

    def test_read_only_source_preservation_and_unrecognized_requests(self):
        saved = self._save_story('No mutation target', 'original saved narration')
        with self.library_fixture.connection() as db:
            access = AccessService(db, clock=lambda: self.library_fixture.now)
            before = db.total_changes
            tool = AssistantSavedMemoryTool(access)
            self.assertIsNone(tool.run(self.owner, 'family-a', '删除所有内容'))
            self.assertIsNone(tool.run(self.owner, 'family-a', '找照片'))
            result = tool.run(self.owner, 'family-a', '搜索故事 No mutation')
            self.assertEqual(db.total_changes, before)
            current = MemoryStories(access).get(self.owner, 'family-a', saved['id'])
            self.assertEqual(current['chapters'][0]['narration'], 'original saved narration')
            self.assertEqual(result.references[0].id, saved['id'])

    def test_invalid_phrase_and_incomplete_page_refuse_without_partial_success(self):
        with self.assertRaises(TransportError) as raised:
            self._run('find saved story ' + 'x' * 161)
        self.assertEqual(raised.exception.status, 400)
        with self.library_fixture.connection() as db:
            access = AccessService(db, clock=lambda: self.library_fixture.now)
            tool = AssistantSavedMemoryTool(access)
            with patch.object(tool.discovery, 'search_page', return_value=MemorySearchPage((), 1, True)):
                with self.assertRaises(TransportError) as raised:
                    tool.run(self.owner, 'family-a', 'find saved story x')
        self.assertEqual(raised.exception.status, 503)

    def test_frozen_outcome_projections_do_not_share_mutable_response_objects(self):
        self._save_story('Projection copy', 'original excerpt phrase')
        outcome = self._run('find saved story phrase')
        with self.assertRaises(FrozenInstanceError):
            outcome.total = 0
        first = outcome.fresh_result()
        first['memory_cards'][0]['title'] = 'changed'
        first['context']['references'].clear()
        second = outcome.fresh_result()
        self.assertNotEqual(second['memory_cards'][0]['title'], 'changed')
        self.assertEqual(len(second['context']['references']), 1)

    def test_joined_emoji_are_preserved_without_claiming_reader_navigation(self):
        title = 'Family 👨‍👩‍👧 picnic'
        self._save_story(title, 'picnic together')
        result = self._run('find saved story picnic').fresh_result()
        self.assertEqual(result['memory_cards'][0]['title'], title)
        self.assertEqual(result['memory_cards'][0]['excerpt'], title)
        self.assertNotIn('open', result['reply'])


if __name__ == '__main__':
    unittest.main()

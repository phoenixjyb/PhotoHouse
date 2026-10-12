"""Authorized, read-only discovery over saved story and memoir text."""
import json
import sys
import unittest
import uuid
from pathlib import Path
from dataclasses import FrozenInstanceError
from unittest.mock import patch

SECURITY = Path(__file__).resolve().parent
sys.path.insert(0, str(SECURITY))

import test_memory_stories as story_fixture
from app.access import assistant_memory_discovery as discovery_module
from app.access.assistant_memory_discovery import (AssistantMemoryDiscovery,
                                                    MAX_CANDIDATES,
                                                    MAX_EXCERPT_CHARS,
                                                    MemoryReference)
from app.access.memory_books import MemoryBooks
from app.access.memory_stories import MemoryStories
from app.access.service import AccessDenied, AccessService
from app.access.transport import TransportError


class AssistantMemoryDiscoveryTests(unittest.TestCase):
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
        self.library = self.fixture.f
        self.owner = self.library.owner_token
        self.member = self.library.member_token

    def _domain(self, cls, method, token, library, *args):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            return getattr(cls(access), method)(token, library, *args)

    def _save_story(self, title, narration, token=None, library='family-a'):
        token = token or self.owner
        headers = {'Authorization': 'Bearer ' + token}
        preview = self.fixture.client.post(
            '/story-workspace/preview?library=' + library,
            headers=headers,
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
        return self._domain(MemoryBooks, 'save', self.owner, 'family-a', body)

    def _edit_story(self, ident, revision, title, narration):
        preview = self.fixture.client.post(
            '/story-workspace/preview?library=family-a',
            headers={'Authorization': 'Bearer ' + self.owner},
            json={'asset_ids': '102,101', 'title': title,
                  'theme': 'everyday', 'language': 'en'})
        self.assertEqual(preview.status_code, 200, preview.text)
        draft = preview.json()
        draft['chapters'][0]['narration'] = narration
        body = {'title': title, 'theme': draft['theme'], 'language': 'en',
                'asset_ids': ','.join(item['id'] for item in draft['items']),
                'chapters': json.dumps(draft['chapters']),
                'selection_revision': draft['selection_revision'],
                'revision': revision, 'mutation_id': str(uuid.uuid4())}
        saved = self.fixture.save(body, ident=ident)
        self.assertEqual(saved.status_code, 200, saved.text)
        return saved.json()

    def _search(self, token, library, query, **kwargs):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            return AssistantMemoryDiscovery(access).search(token, library, query, **kwargs)

    def test_literal_match_ignores_sql_metacharacter_semantics_and_source_captions(self):
        saved = self._save_story('Budget _100%\\ plan', 'The saved narration is ordinary.')
        result = self._search(self.owner, 'family-a', '%\\')
        self.assertEqual(len(result), 1)
        self.assertEqual((result[0].kind, result[0].id, result[0].revision),
                         ('story', saved['id'], saved['revision']))
        self.assertIn('%\\', result[0].excerpt)

        # Captions are not saved story narration and are intentionally outside
        # this discovery foundation.
        self.assertEqual(self._search(self.owner, 'family-a', 'caption-101'), ())

    def test_searches_saved_narration_and_memoir_opening_with_bounded_excerpts(self):
        long_text = 'begin ' + ('x' * 600) + ' family phrase ' + ('y' * 600) + ' end'
        story = self._save_story('Story title', long_text)
        memoir = self._save_memoir('Memoir title', 'Opening phrase for family.', story['id'])

        story_hits = self._search(self.owner, 'family-a', 'family phrase')
        self.assertEqual([item.id for item in story_hits], [story['id']])
        self.assertIsInstance(story_hits[0], MemoryReference)
        self.assertLessEqual(len(story_hits[0].excerpt), MAX_EXCERPT_CHARS)
        self.assertIn('family phrase', story_hits[0].excerpt)
        self.assertEqual(self._search(self.owner, 'family-a', 'Opening phrase')[0].id,
                         memoir['id'])

    def test_trimmed_unicode_casefold_query_and_immutable_reference(self):
        saved = self._save_story('A Straße memory', 'nothing else')
        result = self._search(self.owner, 'family-a', '  STRASSE  ')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, saved['id'])
        self.assertEqual(result[0].excerpt, 'A Straße memory')
        with self.assertRaises(FrozenInstanceError):
            result[0].title = 'changed'

    def test_deterministic_title_order_and_current_revision(self):
        beta = self._save_story('Beta memory', 'same needle')
        alpha = self._save_story('Alpha memory', 'same needle')
        changed = self._edit_story(alpha['id'], '1', 'Alpha memory current', 'same needle')
        hits = self._search(self.owner, 'family-a', 'needle')
        self.assertEqual([item.title for item in hits],
                         ['Alpha memory current', 'Beta memory'])
        by_id = {item.id: item for item in hits}
        self.assertEqual(by_id[changed['id']].revision, changed['revision'])
        self.assertEqual(by_id[alpha['id']].revision, '2')
        self.assertEqual(by_id[beta['id']].revision, beta['revision'])

    def test_foreign_library_and_actor_are_denied_before_results(self):
        saved = self._save_story('Private family memory', 'private phrase')
        with self.assertRaises(AccessDenied):
            self._search(self.owner, 'family-b', 'private')
        # The other owner can read its own library, but cannot see the first
        # library's saved story or its narration.
        self.assertEqual(self._search(self.library.other_token, 'family-b', 'private'), ())
        self.assertNotIn(saved['id'], [item.id for item in
                                      self._search(self.library.other_token, 'family-b', 'private')])

    def test_source_caption_change_updates_story_source_revision_only(self):
        saved = self._save_story('Evidence target', 'saved narration')
        before = self._search(self.owner, 'family-a', 'Evidence target')[0]
        self.library.mutate("UPDATE captions SET text='changed source evidence' WHERE id=101")
        after = self._search(self.owner, 'family-a', 'Evidence target')[0]
        self.assertEqual(before.revision, after.revision)
        self.assertEqual(after.revision, saved['revision'])
        self.assertNotEqual(before.source_revision, after.source_revision)

    def test_changed_child_changes_memoir_source_revision_without_parent_edit(self):
        child = self._save_story('Child title', 'first version')
        memoir = self._save_memoir('Opening card', 'Memoir opening', child['id'])
        before = next(item for item in self._search(self.owner, 'family-a', 'Opening card')
                      if item.kind == 'memoir')
        self._edit_story(child['id'], '1', 'Child title revised', 'second version')
        after = next(item for item in self._search(self.owner, 'family-a', 'Opening card')
                     if item.kind == 'memoir')
        self.assertEqual(after.revision, memoir['revision'])
        self.assertNotEqual(before.source_revision, after.source_revision)

    def test_child_revision_drift_during_memoir_hydration_conflicts(self):
        child = self._save_story('Child title', 'child body')
        self._save_memoir('Memoir card', 'Memoir opening', child['id'])
        original = MemoryBooks.get

        def get_then_edit(service, token, library, ident):
            result = original(service, token, library, ident)
            self._edit_story(child['id'], '1', 'Child title revised', 'new child body')
            return result

        with patch.object(MemoryBooks, 'get', get_then_edit):
            with self.assertRaises(TransportError) as raised:
                self._search(self.owner, 'family-a', 'Memoir card')
        self.assertEqual(raised.exception.status, 409)

    def test_concurrent_insert_between_pages_refuses_unstable_scan(self):
        for index in range(9):
            self._save_story(f'Memory {index:02d}', 'common phrase')
        original = MemoryStories.list
        inserted = False

        def list_then_insert(service, token, library, page, theme=None):
            nonlocal inserted
            result = original(service, token, library, page, theme)
            if page == 1 and not inserted:
                inserted = True
                late = self._save_story('Late memory', 'common phrase')
                self.library.mutate(
                    'UPDATE access_memory_stories SET updated_at=? WHERE id=?',
                    ('0000', late['id']))
            return result

        with patch.object(MemoryStories, 'list', list_then_insert):
            with self.assertRaises(TransportError) as raised:
                self._search(self.owner, 'family-a', 'common phrase')
        self.assertEqual(raised.exception.status, 409)

    def test_duplicate_page_identity_refuses_ambiguous_scan(self):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            discovery = AssistantMemoryDiscovery(access)
            def duplicate_page(_token, _library, page):
                return {'items': [{'id': 'same-id'}], 'has_more': page == 1}

            with patch.object(discovery.stories, 'list', side_effect=duplicate_page):
                with self.assertRaises(TransportError) as raised:
                    discovery.search(self.owner, 'family-a', 'missing')
        self.assertEqual(raised.exception.status, 409)

    def test_source_change_after_hydration_is_caught_before_return(self):
        self._save_story('Final guard target', 'guarded result')
        original = discovery_module._source_revision
        changed = False

        def fingerprint_then_change(value):
            nonlocal changed
            digest = original(value)
            if not changed:
                changed = True
                self.library.mutate("UPDATE captions SET text='late evidence change' WHERE id=101")
            return digest

        with patch.object(discovery_module, '_source_revision', fingerprint_then_change):
            with self.assertRaises(TransportError) as raised:
                self._search(self.owner, 'family-a', 'Final guard target')
        self.assertEqual(raised.exception.status, 409)

    def test_withdrawn_memoir_child_during_fresh_validation_is_denied(self):
        child = self._save_story('Child title', 'child body')
        self._save_memoir('Memoir card', 'Memoir opening', child['id'])
        original = MemoryStories.get
        calls = 0

        def get_then_withdraw(service, token, library, ident):
            nonlocal calls
            calls += 1
            if calls == 2:
                self.library.mutate("UPDATE assets SET status='deleted' WHERE id=101")
            return original(service, token, library, ident)

        with patch.object(MemoryStories, 'get', get_then_withdraw):
            with self.assertRaises(AccessDenied):
                self._search(self.owner, 'family-a', 'Memoir card')
        self.assertEqual(calls, 2)

    def test_withdrawal_between_list_and_detail_fails_closed(self):
        self._save_story('Current memory', 'phrase remains only while authorized')
        original = MemoryStories.list

        def list_then_withdraw(service, token, library, page, theme=None):
            result = original(service, token, library, page, theme)
            self.library.mutate("UPDATE assets SET status='deleted' WHERE id=101")
            return result

        with patch.object(MemoryStories, 'list', list_then_withdraw):
            with self.assertRaises(AccessDenied):
                self._search(self.owner, 'family-a', 'phrase remains')

    def test_candidate_cap_refuses_partial_discovery(self):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            discovery = AssistantMemoryDiscovery(access)
            def page(_token, _library, number):
                return {'items': [{'id': str((number - 1) * 8 + i)} for i in range(8)],
                        'has_more': number * 8 < MAX_CANDIDATES + 1}
            with patch.object(discovery.stories, 'list', side_effect=page):
                with self.assertRaises(TransportError) as raised:
                    discovery.search(self.owner, 'family-a', 'missing')
        self.assertEqual(raised.exception.status, 503)

    def test_query_bounds_and_result_limit_are_strict(self):
        for invalid in ('', '   ', 'x' * 161, '\ud800'):
            with self.subTest(query=repr(invalid)), self.assertRaises(TransportError):
                self._search(self.owner, 'family-a', invalid)
        with self.assertRaises(TransportError):
            self._search(self.owner, 'family-a', 'valid', limit=0)


if __name__ == '__main__':
    unittest.main()

"""Memoir drafting plans: full authorization, bounded context and no writes."""
import json
import unittest
import uuid

import test_memory_books as fixture
from app.access.memory_book_planning import MemoryBookPlanning
from app.access.memory_contributions import MemoryContributions
from app.access.service import AccessDenied, AccessService
from app.access.transport import TransportError


class MemoryBookPlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.MemoryBookTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.MemoryBookTests.tearDownClass()

    def setUp(self):
        self.f = fixture.MemoryBookTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.library = self.f.library_fixture
        self.owner, self.member = self.f.owner, self.f.member

    def plan(self, book, token=None):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            before = db.total_changes
            result = MemoryBookPlanning(access).get(token or self.owner, 'family-a', book)
            self.assertEqual(db.total_changes, before, 'planning must not enqueue or persist sources')
            self.assertFalse(db.in_transaction)
            return result

    def book(self, stories):
        return self.f.save(self.owner, self.f.body(stories))['id']

    def two_chapter_story(self, title):
        ident = self.f.story(title)
        # Use two existing authorized fixture media in their saved order.
        with self.library.connection() as db:
            raw = json.loads(db.execute('SELECT content FROM access_memory_stories WHERE id=?',
                                        (ident,)).fetchone()[0])
            raw['chapters'] = [{'id': f'chapter-{n+1}', 'title': f'Section {n+1}',
                'narration': 'Family editorial wording', 'asset_ids': [asset], 'evidence_ids': []}
                for n, asset in enumerate(raw['asset_ids'])]
            db.execute('UPDATE access_memory_stories SET content=? WHERE id=?',
                       (json.dumps(raw), ident))
            db.commit()
        return ident

    def contribution(self, story, *, consent='1', accepted=True, text='private-family-original'):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            domain = MemoryContributions(access)
            contribution = domain.create(self.member, 'family-a', story,
                {'kind': 'text', 'text': text, 'language': 'en', 'byline': 'Family member',
                 'consent': consent, 'chapter_id': '', 'revision': '1',
                 'mutation_id': str(uuid.uuid4())})
            if accepted:
                domain.review(self.owner, 'family-a', story, contribution['id'], 'accepted', 1)
            return contribution

    def test_saved_order_structure_and_source_counts_are_read_only_not_generated_prose(self):
        first, second = self.f.story('First'), self.f.story('Second', assets='102')
        plan = self.plan(self.book([second, first]))
        self.assertEqual([s['id'] for s in plan['sections']], [second, first])
        self.assertEqual([s['position'] for s in plan['sections']], [1, 2])
        self.assertEqual((plan['story_count'], plan['chapter_count'], plan['item_count']), (2, 2, 3))
        self.assertEqual(plan['distinct_item_count'], 2)
        self.assertEqual(plan['kind'], 'saved_structure_plan')
        self.assertFalse(plan['generated'])
        self.assertFalse(plan['queued'])
        self.assertTrue(plan['needs_review'])
        self.assertEqual(plan['whole']['state'], 'within_limits')
        self.assertEqual(plan['limits'], {'chapters': 24, 'sources': 96, 'context_bytes': 65536})
        serialized = json.dumps(plan)
        self.assertNotIn('private-child-source-', serialized)
        self.assertNotIn('narration', serialized)
        self.assertNotIn('source_ids', serialized)

    def test_saved_unicode_titles_remain_complete_outside_model_title_budget(self):
        title = '🌷' * 160
        story = self.two_chapter_story(title)
        with self.library.connection() as db:
            raw = json.loads(db.execute('SELECT content FROM access_memory_stories WHERE id=?',
                                        (story,)).fetchone()[0])
            raw['chapters'][0]['title'] = title
            db.execute('UPDATE access_memory_stories SET content=? WHERE id=?', (json.dumps(raw), story))
            db.commit()
        plan = self.plan(self.book([story]))
        self.assertEqual(plan['sections'][0]['title'], title)
        self.assertEqual(plan['sections'][0]['chapters'][0]['title'], title)
        self.assertEqual(len(title.encode()), 640)

    def test_large_memoir_has_complete_ordered_essay_plan_even_when_whole_exceeds_limit(self):
        stories = [self.two_chapter_story(f'Essay {n}') for n in range(13)]
        plan = self.plan(self.book(stories))
        self.assertEqual(plan['chapter_count'], 26)
        self.assertEqual(plan['whole']['state'], 'smaller_scope_required')
        self.assertIsNone(plan['whole']['source_count'])
        self.assertFalse(plan['whole']['can_draft'])
        self.assertEqual([s['id'] for s in plan['sections']], stories)
        self.assertTrue(all(s['state'] == 'within_limits' for s in plan['sections']))
        self.assertTrue(all(s['can_draft'] for s in plan['sections']))
        self.assertTrue(all(len(s['chapters']) == 2 for s in plan['sections']))

    def test_pending_and_unconsented_originals_are_not_sources_or_returned(self):
        story = self.f.story('Consent test')
        book = self.book([story])
        baseline = self.plan(book)['sections'][0]['source_count']
        self.contribution(story, accepted=False, text='pending private text')
        self.contribution(story, consent='0', text='unconsented private text')
        hidden = self.plan(book)
        self.assertEqual(hidden['sections'][0]['source_count'], baseline)
        self.contribution(story, text='accepted consented private text')
        visible = self.plan(book)
        self.assertEqual(visible['sections'][0]['source_count'], baseline + 1)
        self.assertEqual(visible['sections'][0]['source_kinds']['family'], 1)
        self.assertNotIn('private text', json.dumps(visible))

    def test_oversized_essay_marks_smaller_scope_without_suppressing_other_essays(self):
        large, small = self.f.story('Large'), self.f.story('Small', assets='102')
        for n in range(17):
            self.contribution(large, text=f'Consented family original {n}')
        plan = self.plan(self.book([large, small]))
        self.assertEqual(plan['sections'][0]['state'], 'smaller_scope_required')
        self.assertEqual(plan['sections'][1]['state'], 'within_limits')
        self.assertEqual(plan['whole']['state'], 'smaller_scope_required')

    def test_viewer_can_plan_but_cannot_draft_and_scope_loss_denies_whole_response(self):
        child = self.f.story('Authorized')
        book = self.book([child])
        viewer = self.plan(book, self.member)
        self.assertFalse(viewer['can_edit'])
        self.assertFalse(viewer['whole']['can_draft'])
        self.assertFalse(viewer['sections'][0]['can_draft'])
        with self.assertRaises(AccessDenied):
            self.plan(book, self.library.other_token)
        self.library.mutate("UPDATE assets SET status='deleted' WHERE id=101")
        with self.assertRaises(AccessDenied):
            self.plan(book)

    def test_missing_schema_or_revoked_membership_does_not_return_a_partial_plan(self):
        book = self.book([self.f.story('Before revoke')])
        self.library.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                            (self.library.member_id,))
        with self.assertRaises(AccessDenied):
            self.plan(book, self.member)
        self.library.mutate('DROP TABLE access_memory_contribution_derivations')
        with self.assertRaises(TransportError) as missing:
            self.plan(book)
        self.assertEqual(missing.exception.status, 503)


if __name__ == '__main__':
    unittest.main()

"""Synthetic closure checks: include uncited inputs, return no copied wording."""
import copy
from dataclasses import FrozenInstanceError, asdict
import json
import unittest

import test_memory_book_edition_contract as fixture
from app.access.memory_book_edition_contract import EditionChildRevision
from app.access.memory_book_edition_provenance import build_edition_provenance
from app.access.transport import TransportError


class MemoirEditionProvenanceTests(unittest.TestCase):
    def setUp(self):
        base = fixture.MemoryBookEditionContractTests()
        base.setUp()
        self.bundle = copy.deepcopy(base.bundle)
        self.children = tuple(EditionChildRevision(c['id'], c['revision']) for c in base.children)
        self.cid = fixture.ident(20)
        self.owners = {self.cid: self.children[0].id}

    def build(self):
        return build_edition_provenance(self.bundle, self.children, contribution_owners=self.owners)

    def unavailable(self):
        with self.assertRaises(TransportError) as raised:
            self.build()
        self.assertEqual(503, raised.exception.status)
        self.assertEqual('Memoir edition provenance unavailable', raised.exception.message)

    def test_closure_contains_all_sources_without_source_words_or_bylines(self):
        result = self.build()
        self.assertEqual([s['id'] for s in self.bundle['sources']], [s.source_id for s in result.sources])
        self.assertEqual(self.cid, result.sources[0].contribution_id)
        self.assertEqual(self.children[0].id, result.sources[0].contribution_story_id)
        serialized = json.dumps(asdict(result), ensure_ascii=False)
        for private in ('家人记得那天。', 'Family member', 'A garden in spring.'):
            self.assertNotIn(private, serialized)
        with self.assertRaises(FrozenInstanceError):
            result.sources[0].source_id = 'changed'

    def test_uncited_prompt_contribution_still_has_a_deletion_pointer(self):
        uncited = fixture.ident(21)
        self.bundle['sources'].append({'id': 'contribution-' + uncited, 'kind': 'transcript',
            'text': 'An uncited family recollection.', 'asset_id': None, 'author': None})
        self.owners[uncited] = self.children[1].id
        result = self.build()
        dependency = result.sources[-1]
        self.assertEqual(uncited, dependency.contribution_id)
        self.assertEqual((), dependency.chapter_ids)
        self.assertEqual(self.children[1].id, dependency.contribution_story_id)

    def test_any_source_change_changes_digest_even_if_uncited(self):
        before = self.build()
        self.bundle['sources'][1]['text'] += ' Another detail.'
        after = self.build()
        self.assertNotEqual(before.closure_digest, after.closure_digest)
        self.assertEqual(before.sources[0], after.sources[0])
        self.assertNotEqual(before.sources[1].source_digest, after.sources[1].source_digest)

    def test_missing_wrong_or_cross_story_contribution_ownership_is_refused(self):
        self.owners = {}; self.unavailable()
        self.owners = {self.cid: fixture.ident(200)}; self.unavailable()
        self.owners = {self.cid: self.children[1].id}; self.unavailable()

    def test_family_evidence_ids_are_not_invented_contribution_pointers(self):
        source = self.bundle['sources'][1]
        source.update(id='family-' + fixture.ident(91), kind='family')
        self.bundle['chapters'][1]['evidence_ids'] = [source['id']]
        dependency = self.build().sources[1]
        self.assertIsNone(dependency.contribution_id)
        self.assertIsNone(dependency.contribution_story_id)

    def test_child_order_revision_and_complete_chapter_binding_are_checked(self):
        original = self.children
        self.children = tuple(reversed(original)); self.unavailable()
        self.children = original + (original[0],); self.unavailable()
        self.children = (EditionChildRevision(original[0].id, '01'), original[1]); self.unavailable()
        self.children = original
        self.bundle['chapters'].pop(); self.unavailable()

    def test_chat_or_story_context_cannot_be_persisted_as_memoir_provenance(self):
        self.bundle['recent_turns'] = [{'user': 'Question', 'assistant': 'Reply'}]; self.unavailable()
        self.bundle['recent_turns'] = []
        self.bundle['target']['type'] = 'story'; self.unavailable()

    def test_result_detaches_caller_metadata(self):
        before = self.build()
        original = before.closure_digest
        self.bundle['sources'][0]['text'] = 'Changed later'
        self.bundle['chapters'][0]['evidence_ids'].clear()
        self.owners.clear()
        self.assertEqual(original, before.closure_digest)
        self.assertTrue(before.sources[0].chapter_ids)


if __name__ == '__main__':
    unittest.main()

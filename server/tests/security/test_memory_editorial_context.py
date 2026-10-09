"""Synthetic source and strict-shape checks for opt-in memoir context v2."""
from copy import deepcopy
import json
import unittest
import uuid
from unittest.mock import patch

import httpx

from app.access.memory_editorial_context import enrich
from app.access.memory_book_editorial_contract import ChildRevision
from app.access.memory_narrative import (
    MAX_BUNDLE_BYTES, LocalMemoryNarrator, _EDITORIAL_SAFETY_SUFFIX,
    _SAFETY_PROMPT, _validate_bundle,
)
from app.access.service import AccessService
from app.access.transport import TransportError
import test_memory_book_editorial_service as editorial_fixture


class MemoryEditorialContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        editorial_fixture.MemoryBookEditorialServiceTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        editorial_fixture.MemoryBookEditorialServiceTests.tearDownClass()

    def setUp(self):
        self.fixture = editorial_fixture.MemoryBookEditorialServiceTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture._service('save', self.fixture.book_id, self.fixture._request())
        self.bundle = self._bundle()

    def _bundle(self):
        f = self.fixture
        source_one = 'contribution-' + f.source_one
        source_two = 'contribution-' + f.source_two
        return {
            'version': 1,
            'library_id': 'family-a',
            'target': {'type': 'book', 'id': f.book_id, 'revision': 2},
            'language': 'en', 'title': 'Synthetic memoir', 'theme': 'family story',
            'chapters': [
                {'id': f.child_one + '-chapter-1', 'title': 'One', 'narration': '',
                 'asset_ids': [], 'evidence_ids': [source_one]},
                {'id': f.child_two + '-chapter-1', 'title': 'Two', 'narration': '',
                 'asset_ids': [], 'evidence_ids': [source_two]},
            ],
            'sources': [
                {'id': source_one, 'kind': 'family', 'text': 'Synthetic family source one',
                 'asset_id': None, 'author': 'Synthetic'},
                {'id': source_two, 'kind': 'family', 'text': 'Synthetic family source two',
                 'asset_id': None, 'author': 'Synthetic'},
            ],
            'recent_turns': [], 'instructions': '',
        }

    def _enrich(self, bundle=None):
        f = self.fixture
        with f.f.connection() as db:
            access = AccessService(db, clock=lambda: f.f.now)
            member = access._require(f.owner, 'family-a', 'library.read')
            return enrich(access, 'family-a', member, f.book_id,
                          self.bundle if bundle is None else bundle)

    def test_current_b1_sidecar_adds_detached_citations_and_preserves_input(self):
        original = deepcopy(self.bundle)
        enriched, sidecar = self._enrich()
        self.assertEqual(original, self.bundle)
        self.assertEqual(2, enriched['version'])
        self.assertEqual({
            'children': [
                {'story_id': self.fixture.child_one, 'revision': '1'},
                {'story_id': self.fixture.child_two, 'revision': '1'},
            ],
            'introduction_source_ids': ['contribution-' + self.fixture.source_one],
            'transitions': [{
                'left_story_id': self.fixture.child_one,
                'right_story_id': self.fixture.child_two,
                'text': 'Our shared moment',
                'source_ids': ['contribution-' + self.fixture.source_two],
            }],
        }, enriched['book_editorial'])
        self.assertEqual('current', sidecar['state'])
        self.assertEqual('2', sidecar['revision'])
        validated = _validate_bundle(enriched)
        self.assertEqual(2, validated['version'])
        enriched['book_editorial']['transitions'][0]['source_ids'].clear()
        self.assertEqual(1, len(sidecar['transitions'][0]['source_refs']))

    def test_missing_hydrated_source_and_revoked_consent_refuse_with_conflict(self):
        missing = deepcopy(self.bundle)
        missing['sources'] = missing['sources'][:1]
        missing['chapters'][1]['evidence_ids'] = []
        with self.assertRaises(TransportError) as absent:
            self._enrich(missing)
        self.assertEqual(409, absent.exception.status)

        self.fixture.f.mutate(
            'UPDATE access_memory_contributions SET local_processing_consent=0 WHERE id=?',
            (self.fixture.source_one,))
        with self.assertRaises(TransportError) as revoked:
            self._enrich()
        self.assertEqual(409, revoked.exception.status)

    def test_stale_or_reordered_current_child_snapshot_is_not_used(self):
        self.fixture.base.save(self.fixture.owner, self.fixture.base.body(
            [self.fixture.child_two, self.fixture.child_one], title='Reordered memoir'))
        stale_bundle = deepcopy(self.bundle)
        stale_bundle['target']['revision'] = 3
        with self.assertRaises(TransportError) as stale:
            self._enrich(stale_bundle)
        self.assertEqual(409, stale.exception.status)

    def test_legacy_bundle_library_must_match_authorized_library(self):
        wrong_library = deepcopy(self.bundle)
        wrong_library['library_id'] = 'another-library'
        with self.assertRaises(TransportError) as mismatch:
            self._enrich(wrong_library)
        self.assertEqual(400, mismatch.exception.status)

    def test_repeated_contribution_across_chapters_deduplicates_v2_id_but_keeps_snapshot(self):
        first, second = str(uuid.uuid4()), str(uuid.uuid4())
        contribution = str(uuid.uuid4())
        child_revisions = (ChildRevision(first, '1'), ChildRevision(second, '1'))
        source_id = 'contribution-' + contribution
        bundle = {
            'version': 1, 'library_id': 'family-a',
            'target': {'type': 'book', 'id': self.fixture.book_id, 'revision': 7},
            'language': 'en', 'title': 'Two chapter memoir', 'theme': 'family story',
            'chapters': [
                {'id': first + '-chapter-a', 'title': 'A', 'narration': '',
                 'asset_ids': [], 'evidence_ids': [source_id]},
                {'id': first + '-chapter-b', 'title': 'B', 'narration': '',
                 'asset_ids': [], 'evidence_ids': [source_id]},
                {'id': second + '-chapter-c', 'title': 'C', 'narration': '',
                 'asset_ids': [], 'evidence_ids': []},
            ],
            'sources': [{'id': source_id, 'kind': 'family', 'text': 'Shared source',
                         'asset_id': None, 'author': None}],
            'recent_turns': [], 'instructions': '',
        }
        ref_a = {'story_id': first, 'story_revision': '1', 'chapter_id': 'chapter-a',
                 'contribution_id': contribution}
        ref_b = {**ref_a, 'chapter_id': 'chapter-b'}
        sidecar = {
            'version': 1, 'id': self.fixture.book_id, 'revision': '7',
            'children': [{'story_id': first, 'revision': '1'},
                         {'story_id': second, 'revision': '1'}],
            'state': 'current', 'introduction_source_refs': [ref_a, ref_b],
            'transitions': [{'left_story_id': first, 'right_story_id': second,
                             'text': '', 'source_refs': []}],
        }

        class FakeEditorial:
            def __init__(self, _access, *, enabled):
                self.enabled = enabled

            def _ready(self):
                self.assert_enabled = True

            def _book_context(self, *_args):
                return {'id': self_book_id, 'revision': 7}, None, child_revisions, frozenset()

            def _read_sidecar(self, *_args):
                return sidecar

        self_book_id = self.fixture.book_id
        with patch('app.access.memory_editorial_context.MemoryBookEditorial', FakeEditorial):
            enriched, snapshot = enrich(object(), 'family-a', {}, self.fixture.book_id, bundle)
        self.assertEqual([source_id], enriched['book_editorial']['introduction_source_ids'])
        self.assertEqual(2, len(snapshot['introduction_source_refs']))

    def test_opt_in_bundle_v2_rejects_bad_order_bounds_and_nonfamily_references(self):
        valid, _ = self._enrich()
        cases = []

        reordered = deepcopy(valid)
        reordered['book_editorial']['children'].reverse()
        cases.append(reordered)

        wrong_revision = deepcopy(valid)
        wrong_revision['book_editorial']['children'][0]['revision'] = '01'
        cases.append(wrong_revision)

        missing_reference = deepcopy(valid)
        missing_reference['book_editorial']['introduction_source_ids'] = ['contribution-' + '0' * 36]
        cases.append(missing_reference)

        nonfamily_reference = deepcopy(valid)
        nonfamily_reference['sources'][0]['kind'] = 'editorial'
        cases.append(nonfamily_reference)

        too_many_references = deepcopy(valid)
        too_many_references['book_editorial']['introduction_source_ids'] = [
            'contribution-' + self.fixture.source_one
        ] * 13
        cases.append(too_many_references)

        oversized_transition = deepcopy(valid)
        oversized_transition['book_editorial']['transitions'][0]['text'] = 'é' * 3001
        cases.append(oversized_transition)

        wrong_target = deepcopy(valid)
        wrong_target['target']['type'] = 'story'
        cases.append(wrong_target)

        for candidate in cases:
            with self.subTest(candidate=candidate['book_editorial']), self.assertRaises(ValueError):
                _validate_bundle(candidate)

    def test_legacy_v1_bundle_shape_and_copy_remain_unchanged(self):
        clean = _validate_bundle(self.bundle)
        self.assertEqual(self.bundle, clean)
        self.assertNotIn('book_editorial', clean)

    def test_only_v2_prompt_adds_editorial_authority_boundary(self):
        v2, _ = self._enrich()
        captured = []
        response = json.dumps({
            'model': 'synthetic-local', 'done': True,
            'response': json.dumps({'version': 1, 'kind': 'answer',
                                    'reply': 'Synthetic response', 'source_ids': [],
                                    'questions': [], 'proposal': None}),
        }).encode()

        def handler(request):
            captured.append(json.loads(request.content)['prompt'])
            return httpx.Response(200, content=response)

        model = LocalMemoryNarrator('http://127.0.0.1:11434', 'synthetic-local',
                                    transport=httpx.MockTransport(handler))
        model.companion(self.bundle)
        model.companion(v2)
        self.assertTrue(captured[0].startswith(_SAFETY_PROMPT + '\nTask:'))
        self.assertNotIn(_EDITORIAL_SAFETY_SUFFIX, captured[0])
        self.assertTrue(captured[1].startswith(
            _SAFETY_PROMPT + _EDITORIAL_SAFETY_SUFFIX + '\nTask:'))

    def test_valid_v2_context_over_budget_returns_sizing_conflict(self):
        padded = deepcopy(self.bundle)
        target_size = MAX_BUNDLE_BYTES - 350
        index = 0
        while True:
            size = len(json.dumps(padded, ensure_ascii=False,
                                  separators=(',', ':')).encode('utf-8'))
            remaining = target_size - size
            if remaining <= 100:
                break
            chunk = min(8192, remaining - 100)
            padded['sources'].append({
                'id': f'meta-padding-{index}', 'kind': 'metadata',
                'text': 'x' * chunk, 'asset_id': None, 'author': None,
            })
            index += 1
        self.assertLessEqual(
            len(json.dumps(padded, ensure_ascii=False, separators=(',', ':')).encode('utf-8')),
            MAX_BUNDLE_BYTES)
        with self.assertRaises(TransportError) as too_large:
            self._enrich(padded)
        self.assertEqual(422, too_large.exception.status)


if __name__ == '__main__':
    unittest.main()

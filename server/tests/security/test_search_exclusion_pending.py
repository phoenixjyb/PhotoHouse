"""Strict private state for unsupported exclusion clarifications."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from app.access.search_pending import (PENDING_TTL_SECONDS, current_pending,
    exclusion_context_digest, make_exclusion_pending, validate_pending)


CONTEXT = {
    'library_id': 'family-a', 'binding': 'a' * 64, 'fingerprint': 'b' * 64,
    'filters': {'people': {'ids': ['301'], 'match': 'any'}, 'media': ['image']},
    'visible_ids': ['103'], 'total': 1, 'search_version': 3,
}


class SearchExclusionPendingTests(unittest.TestCase):
    def test_original_query_and_exact_context_digest_are_retained(self):
        query = 'Find photos of Sample Child, but exclude red coats'
        state = make_exclusion_pending(query, CONTEXT['binding'], CONTEXT, 500)
        self.assertEqual(state, {
            'version': 1, 'question': 'exclusion', 'query': query,
            'binding': CONTEXT['binding'],
            'context_digest': exclusion_context_digest(CONTEXT), 'created_at': 500,
        })
        self.assertEqual(state, validate_pending(state))
        self.assertEqual(state, current_pending(state, 500 + PENDING_TTL_SECONDS))
        self.assertIsNone(current_pending(state, 499))
        self.assertIsNone(current_pending(state, 501 + PENDING_TTL_SECONDS))

    def test_null_context_has_a_stable_distinct_digest(self):
        query = 'Find photos excluding red coats'
        state = make_exclusion_pending(query, 'c' * 64, None, 500)
        self.assertEqual(state['context_digest'], exclusion_context_digest(None))
        self.assertNotEqual(state['context_digest'], exclusion_context_digest(CONTEXT))

    def test_query_is_not_normalized_and_has_no_offset_length_restriction(self):
        query = 'Ｆｉｎｄ photos, excluding “red coat”'
        state = make_exclusion_pending(query, 'c' * 64, None, 500)
        self.assertEqual(state['query'], query)
        self.assertEqual(len(state['query']), len(query))

    def test_closed_schema_rejects_extra_fields_bad_types_and_unsafe_queries(self):
        valid = make_exclusion_pending('Find photos excluding red coats', 'c' * 64,
                                       None, 500)
        malformed = (
            {**valid, 'version': True},
            {**valid, 'version': 2},
            {**valid, 'question': 'date'},
            {**valid, 'created_at': True},
            {**valid, 'binding': 'C' * 64},
            {**valid, 'context_digest': 'x' * 64},
            {**valid, 'extra': 'ignored? no'},
            {**valid, 'query': 'Find photos\x00'},
            {**valid, 'query': 'Find photos\ud800'},
            {**valid, 'query': 'x' * 1025},
            {**valid, 'query': '   '},
        )
        for candidate in malformed:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    validate_pending(candidate)

    def test_make_requires_context_binding_to_match(self):
        with self.assertRaises(ValueError):
            make_exclusion_pending('Find photos excluding red coats', 'c' * 64,
                                   CONTEXT, 500)


if __name__ == '__main__':
    unittest.main()

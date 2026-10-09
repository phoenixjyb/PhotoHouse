"""Synthetic tests for the pure, versioned memoir editorial request contract."""
import json
import traceback
import unittest
import uuid
from dataclasses import FrozenInstanceError

from app.access.memory_book_editorial_contract import (
    MAX_BODY_BYTES,
    MAX_REFS_PER_SECTION,
    ContractCode,
    ChildRevision,
    EditorialContractError,
    EditorialMutation,
    SourceIdentity,
    parse_mutation,
)


class MemoryBookEditorialContractTests(unittest.TestCase):
    def setUp(self):
        self.stories = [str(uuid.UUID(int=1)), str(uuid.UUID(int=2))]
        self.contributions = [str(uuid.UUID(int=101)), str(uuid.UUID(int=102))]
        self.children = tuple(ChildRevision(story_id, '3') for story_id in self.stories)
        self.sources = frozenset({
            SourceIdentity(self.stories[0], '3', 'chapter-1', self.contributions[0]),
            SourceIdentity(self.stories[1], '3', 'chapter-1', self.contributions[1]),
        })
        self.mutation = str(uuid.UUID(int=501))

    def ref(self, index=0):
        source = sorted(self.sources, key=lambda item: item.story_id)[index]
        return {'story_id': source.story_id, 'story_revision': source.story_revision,
                'chapter_id': source.chapter_id, 'contribution_id': source.contribution_id}

    def body(self):
        return {
            'version': 1,
            'revision': '7',
            'mutation_id': self.mutation,
            'children': [{'story_id': item.story_id, 'revision': item.revision}
                         for item in self.children],
            'introduction_source_refs': [],
            'transitions': [{
                'left_story_id': self.stories[0],
                'right_story_id': self.stories[1],
                'text': 'Reviewed bridge.',
                'source_refs': [self.ref(0)],
            }],
        }

    def parse(self, body=None, *, raw=None, book_revision='7', children=None,
              eligible_sources=None):
        if raw is None:
            raw = json.dumps(self.body() if body is None else body,
                             ensure_ascii=False, separators=(',', ':'))
        return parse_mutation(
            raw, current_book_revision=book_revision,
            current_children=self.children if children is None else children,
            eligible_sources=self.sources if eligible_sources is None else eligible_sources)

    def assert_code(self, code, **kwargs):
        with self.assertRaises(EditorialContractError) as caught:
            self.parse(**kwargs)
        self.assertIs(caught.exception.code, code)

    def test_valid_contract_returns_immutable_typed_values(self):
        result = self.parse()
        self.assertIsInstance(result, EditorialMutation)
        self.assertEqual(result.expected_revision, '7')
        self.assertEqual(result.mutation_id, self.mutation)
        self.assertEqual(result.children, self.children)
        self.assertEqual(len(result.transitions), 1)
        self.assertEqual(result.transitions[0].source_refs[0],
                         SourceIdentity(**self.ref(0)))
        with self.assertRaises(FrozenInstanceError):
            result.expected_revision = '8'
        with self.assertRaises(AttributeError):
            result.transitions.append(None)

    def test_book_and_ordered_child_compare_and_swap(self):
        self.assert_code(ContractCode.REVISION_CONFLICT, book_revision='8')
        stale = (ChildRevision(self.stories[0], '2'), self.children[1])
        self.assert_code(ContractCode.SOURCE_CHANGED, children=stale)
        reordered = tuple(reversed(self.children))
        self.assert_code(ContractCode.SOURCE_CHANGED, children=reordered)
        wrong_body = self.body()
        wrong_body['children'][0]['revision'] = '2'
        self.assert_code(ContractCode.SOURCE_CHANGED, body=wrong_body)

    def test_duplicate_json_keys_invalid_utf8_and_nonstandard_numbers_rejected(self):
        self.assert_code(ContractCode.INVALID_JSON, raw=b'{"version":1,"version":1}')
        self.assert_code(ContractCode.INVALID_JSON, raw=b'\xff')
        self.assert_code(ContractCode.INVALID_JSON, raw='{"version":NaN}')

    def test_exact_keys_version_and_json_types_are_enforced(self):
        body = self.body() | {'surprise': 'secret marker'}
        self.assert_code(ContractCode.INVALID_SHAPE, body=body)
        body = self.body(); body['version'] = True
        self.assert_code(ContractCode.UNSUPPORTED_VERSION, body=body)
        body = self.body(); body['children'][0]['extra'] = 1
        self.assert_code(ContractCode.INVALID_SHAPE, body=body)
        body = self.body(); body['transitions'][0]['source_refs'][0]['extra'] = 1
        self.assert_code(ContractCode.INVALID_SHAPE, body=body)

    def test_canonical_uuid_and_positive_decimal_revision_forms(self):
        body = self.body(); body['mutation_id'] = self.mutation.upper()
        self.assert_code(ContractCode.INVALID_IDENTIFIER, body=body)
        body = self.body(); body['revision'] = '07'
        self.assert_code(ContractCode.INVALID_IDENTIFIER, body=body)
        body = self.body(); body['children'][0]['revision'] = True
        self.assert_code(ContractCode.INVALID_IDENTIFIER, body=body)
        body = self.body(); body['children'][0]['story_id'] = 'not-a-uuid'
        self.assert_code(ContractCode.INVALID_IDENTIFIER, body=body)

    def test_raw_byte_cap_and_transition_utf8_byte_cap(self):
        self.assert_code(ContractCode.TOO_LARGE, raw=b' ' * (MAX_BODY_BYTES + 1))
        body = self.body(); body['transitions'][0]['text'] = '界' * 2001
        self.assertGreater(len(body['transitions'][0]['text'].encode()), 6000)
        self.assert_code(ContractCode.INVALID_TRANSITION, body=body)
        body = self.body(); body['transitions'][0]['text'] = 'bad\x00text'
        self.assert_code(ContractCode.INVALID_TRANSITION, body=body)

    def test_children_are_unique_and_bounded(self):
        body = self.body(); body['children'][1]['story_id'] = self.stories[0]
        self.assert_code(ContractCode.INVALID_IDENTIFIER, body=body)
        body = self.body(); body['children'] = []
        self.assert_code(ContractCode.CHILD_LIMIT, body=body)
        body = self.body(); body['children'] *= 13
        self.assert_code(ContractCode.CHILD_LIMIT, body=body)

    def test_transitions_are_exactly_ordered_adjacent_pairs(self):
        body = self.body(); body['transitions'] = []
        self.assert_code(ContractCode.INVALID_TRANSITION, body=body)
        body = self.body(); body['transitions'][0]['left_story_id'] = self.stories[1]
        self.assert_code(ContractCode.INVALID_TRANSITION, body=body)
        body = self.body(); body['transitions'][0]['right_story_id'] = self.stories[0]
        self.assert_code(ContractCode.INVALID_TRANSITION, body=body)

    def test_references_must_match_current_trusted_identity_and_transition_pair(self):
        body = self.body(); body['introduction_source_refs'] = [self.ref(0)]
        self.assertEqual(len(self.parse(body).introduction_source_refs), 1)
        third_story = str(uuid.UUID(int=3))
        third_contribution = str(uuid.UUID(int=103))
        third_child = ChildRevision(third_story, '4')
        third_source = SourceIdentity(third_story, '4', 'chapter-1', third_contribution)
        body = self.body()
        body['children'].append({'story_id': third_story, 'revision': '4'})
        body['transitions'].append({
            'left_story_id': self.stories[1], 'right_story_id': third_story,
            'text': 'Second bridge.', 'source_refs': [
                {'story_id': self.stories[1], 'story_revision': '3',
                 'chapter_id': 'chapter-1', 'contribution_id': self.contributions[1]}],
        })
        body['transitions'][0]['source_refs'] = [{
            'story_id': third_story, 'story_revision': '4',
            'chapter_id': 'chapter-1', 'contribution_id': third_contribution}]
        self.assert_code(ContractCode.INVALID_REFERENCE, body=body,
                         children=self.children + (third_child,),
                         eligible_sources=self.sources | {third_source})
        body = self.body(); body['transitions'][0]['source_refs'] = [self.ref(0)]
        self.assert_code(ContractCode.INVALID_REFERENCE, body=body,
                         eligible_sources=frozenset())
        body = self.body(); body['transitions'][0]['source_refs'][0]['story_revision'] = '2'
        self.assert_code(ContractCode.INVALID_REFERENCE, body=body)

    def test_transition_text_and_source_presence_are_consistent(self):
        body = self.body(); body['transitions'][0]['source_refs'] = []
        self.assert_code(ContractCode.INVALID_TRANSITION, body=body)
        body = self.body(); body['transitions'][0]['text'] = '  \n '
        body['transitions'][0]['source_refs'] = []
        self.assertEqual(self.parse(body).transitions[0].text, '  \n ')
        body = self.body(); body['transitions'][0]['text'] = '\t'
        self.assert_code(ContractCode.INVALID_TRANSITION, body=body)

    def test_reference_duplicates_and_section_and_total_caps(self):
        body = self.body()
        body['transitions'][0]['source_refs'] = [self.ref(0), self.ref(0)]
        self.assert_code(ContractCode.INVALID_REFERENCE, body=body)
        body = self.body()
        body['introduction_source_refs'] = [self.ref(0)] * (MAX_REFS_PER_SECTION + 1)
        self.assert_code(ContractCode.INVALID_REFERENCE, body=body)

        children = tuple(ChildRevision(str(uuid.UUID(int=1000 + i)), '3')
                         for i in range(24))
        eligible = set()
        refs_by_story = {}
        for child in children:
            refs = []
            for offset in range(5 if child == children[0] else 4):
                source = SourceIdentity(child.story_id, child.revision, 'chapter-1',
                                        str(uuid.UUID(int=2000 + len(eligible))))
                eligible.add(source)
                refs.append({'story_id': source.story_id,
                             'story_revision': source.story_revision,
                             'chapter_id': source.chapter_id,
                             'contribution_id': source.contribution_id})
            refs_by_story[child.story_id] = refs
        full = {
            'version': 1, 'revision': '7', 'mutation_id': str(uuid.UUID(int=3000)),
            'children': [{'story_id': child.story_id, 'revision': child.revision}
                         for child in children],
            'introduction_source_refs': refs_by_story[children[0].story_id][:3],
            'transitions': [{
                'left_story_id': children[i].story_id,
                'right_story_id': children[i + 1].story_id,
                'text': 'Reviewed bridge.',
                'source_refs': refs_by_story[children[i].story_id][:4],
            } for i in range(len(children) - 1)],
        }
        parsed = self.parse(body=full, children=children,
                            eligible_sources=frozenset(eligible))
        self.assertEqual(sum(len(t.source_refs) for t in parsed.transitions)
                         + len(parsed.introduction_source_refs), 95)
        full['introduction_source_refs'] = refs_by_story[children[0].story_id][:4]
        self.assertEqual(sum(len(t.source_refs) for t in self.parse(
            body=full, children=children, eligible_sources=frozenset(eligible)).transitions)
            + len(full['introduction_source_refs']), 96)
        full['introduction_source_refs'].append(
            refs_by_story[children[0].story_id][4])
        self.assert_code(ContractCode.INVALID_REFERENCE, body=full, children=children,
                         eligible_sources=frozenset(eligible))

    def test_validation_errors_never_echo_untrusted_input(self):
        body = self.body() | {'unknown': 'private-user-sentinel'}
        with self.assertRaises(EditorialContractError) as caught:
            self.parse(body)
        self.assertNotIn('private-user-sentinel', str(caught.exception))
        self.assertNotIn('private-user-sentinel', repr(caught.exception))

    def test_formatted_tracebacks_suppress_parser_unicode_and_field_values(self):
        invalid_raw = '{"private-user-sentinel":"\ud800"}'
        with self.assertRaises(EditorialContractError) as caught:
            self.parse(raw=invalid_raw)
        rendered = ''.join(traceback.format_exception(caught.exception))
        self.assertNotIn('private-user-sentinel', rendered)
        self.assertNotIn('UnicodeEncodeError', rendered)

        body = self.body()
        body['introduction_source_refs'] = [{
            'story_id': self.stories[0], 'story_revision': '3',
            'chapter_id': 'private-user-sentinel' * 20,
            'contribution_id': self.contributions[0],
        }]
        with self.assertRaises(EditorialContractError) as caught:
            self.parse(body)
        rendered = ''.join(traceback.format_exception(caught.exception))
        self.assertNotIn('private-user-sentinel', rendered)

        body = self.body()
        body['transitions'][0]['text'] = 'private-user-sentinel\ud800'
        with self.assertRaises(EditorialContractError) as caught:
            self.parse(raw=json.dumps(body, ensure_ascii=True))
        rendered = ''.join(traceback.format_exception(caught.exception))
        self.assertNotIn('private-user-sentinel', rendered)
        self.assertNotIn('UnicodeEncodeError', rendered)

    def test_one_child_empty_transitions_and_invalid_trusted_context(self):
        only_child = (self.children[0],)
        body = self.body() | {
            'children': [{'story_id': only_child[0].story_id,
                          'revision': only_child[0].revision}],
            'transitions': [],
        }
        result = self.parse(body=body, children=only_child, eligible_sources=self.sources)
        self.assertEqual(result.transitions, ())
        self.assertEqual(result.children, only_child)

        self.assert_code(ContractCode.INVALID_CONTEXT,
                         children=({'story_id': self.stories[0]},))
        self.assert_code(ContractCode.INVALID_CONTEXT,
                         eligible_sources=[*self.sources])


if __name__ == '__main__':
    unittest.main()

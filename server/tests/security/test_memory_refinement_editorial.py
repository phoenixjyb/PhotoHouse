"""Automatic editorial profile contracts; no model or household fixture data."""
from copy import deepcopy
import unittest

from app.access.memory_narrative import (
    STORY_REFINEMENT_PROFILE, _validate_bundle, _generation_payload,
    validate_generated_narrative, validate_narrative)
from test_memory_narrative import bundle, narrative


def editorial_bundle():
    value = bundle()
    value.update(version=4, language='zh', story_refinement={
        'profile': STORY_REFINEMENT_PROFILE,
        'people': [{'name': '林澄', 'aliases': ['Lina', '澄澄']}]})
    value['chapters'][0]['narration'] = '我们在花园，在一个花园里，Lina或者澄澄都很开心。'
    return value


class EditorialProfileTests(unittest.TestCase):
    def test_v4_compact_editor_prompt_carries_only_text_and_reviewed_name_context(self):
        value = editorial_bundle()
        before = deepcopy(value)
        payload = _generation_payload(_validate_bundle(value), 'narrative', 'synthetic-local')
        self.assertEqual(value, before)
        for requirement in ('常见ASR错字、同音词', '已审核称呼', '重复句',
                            '连贯自然的中文散文', '人审核'):
            self.assertIn(requirement, payload['prompt'])
        self.assertIn('林澄', payload['prompt'])
        self.assertIn('\nTask: ', payload['prompt'])
        self.assertIn('saved_story_editorial_v4', payload['prompt'])
        self.assertNotIn('evidence_ids', payload['prompt'])
        self.assertNotIn('source_ids', payload['prompt'])
        self.assertNotIn('Bundle JSON', payload['prompt'])
        self.assertEqual({'title', 'paragraphs', 'questions'},
                         set(payload['format']['properties']))
        old = _generation_payload(bundle(), 'narrative', 'synthetic-local')
        self.assertIn('preserve names and verbatim', old['prompt'])
        self.assertNotIn('Saved-story editing task', old['prompt'])
        self.assertEqual(payload['options'], old['options'])

    def test_v4_host_rebuilds_citations_and_rejects_model_controlled_ids_or_noop(self):
        value = editorial_bundle()
        original_text = '我们在花园里散步，聊起了以前的日子，也一起照看花草。' * 4
        value['chapters'][0]['narration'] = original_text
        story_id = value['target']['id']
        chapter_id = value['chapters'][0]['id']
        editorial_id = f'editorial-{story_id}-{chapter_id}'
        value['sources'].append({'id': editorial_id, 'kind': 'editorial',
                                 'text': value['chapters'][0]['narration'],
                                 'asset_id': None, 'author': None})
        value['chapters'][0]['evidence_ids'].append(editorial_id)
        clean = _validate_bundle(value)
        compact = {'title': 'A revised memory',
                   'paragraphs': ['我们在花园里相聚，聊着当时的心情。'],
                   'questions': []}
        result = validate_generated_narrative(compact, clean)
        self.assertEqual([editorial_id], result['chapters'][0]['source_ids'])
        self.assertTrue(result['needs_review'])

        bad_responses = (
            {'title': 'A story', 'paragraphs': [], 'questions': []},
            {**compact, 'chapter_ids': [chapter_id]},
            {**compact, 'source_ids': ['injected-source']},
            {'version': 1, 'title': 'A story',
             'chapters': [{'id': chapter_id, 'narration': 'new text',
                           'source_ids': [editorial_id]}],
             'questions': [], 'needs_review': True},
            {'title': 'A story', 'paragraphs': [original_text],
             'questions': []},
        )
        for response in bad_responses:
            with self.subTest(keys=sorted(response)), self.assertRaises(ValueError):
                validate_generated_narrative(response, clean)

        empty_input = deepcopy(clean)
        empty_input['chapters'][0]['narration'] = ''
        empty_response = {'title': 'A story', 'paragraphs': [''], 'questions': []}
        self.assertEqual('', validate_generated_narrative(
            empty_response, empty_input)['chapters'][0]['narration'])
        invented_response = {**empty_response, 'paragraphs': ['New unsupported text.']}
        with self.assertRaisesRegex(ValueError, 'empty chapter'):
            validate_generated_narrative(invented_response, empty_input)

    def test_refinement_context_is_closed_bounded_and_story_only(self):
        edits = [lambda v: v['story_refinement'].update(profile='unreviewed'),
                 lambda v: v['story_refinement'].update(token='secret'),
                 lambda v: v['story_refinement']['people'][0].update(account_id='private'),
                 lambda v: v['story_refinement']['people'][0].update(aliases=['a'] * 17),
                 lambda v: v['story_refinement']['people'][0].update(name=''),
                 lambda v: v['story_refinement'].update(people=[{'name':'a','aliases':[]}] * 33),
                 lambda v: v['target'].update(type='book')]
        for edit in edits:
            value = editorial_bundle()
            edit(value)
            with self.subTest(edit=edit), self.assertRaises(ValueError):
                _validate_bundle(value)
        with self.assertRaises(ValueError):
            _generation_payload(editorial_bundle(), 'companion', 'synthetic-local')

    def test_name_context_cannot_be_cited_as_event_evidence_and_review_stays_required(self):
        value = editorial_bundle()
        self.assertEqual(narrative(), validate_narrative(narrative(), value))
        for proposal in (narrative(refs=('林澄',)), narrative(refs=('reviewed-name-1',)),
                         dict(narrative(), needs_review=False), narrative(chapter_id='other')):
            with self.subTest(proposal=proposal), self.assertRaises(ValueError):
                validate_narrative(proposal, value)

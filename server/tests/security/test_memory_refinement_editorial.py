"""Automatic editorial profile contracts; no model or household fixture data."""
from copy import deepcopy
import unittest

from app.access.memory_narrative import (
    STORY_REFINEMENT_PROFILE, _validate_bundle, _generation_payload, validate_narrative)
from test_memory_narrative import bundle, narrative


def editorial_bundle():
    value = bundle()
    value.update(version=4, language='zh', story_refinement={
        'profile': STORY_REFINEMENT_PROFILE,
        'people': [{'name': '林澄', 'aliases': ['Lina', '澄澄']}]})
    value['chapters'][0]['narration'] = '我们在花园，在一个花园里，Lina或者澄澄都很开心。'
    return value


class EditorialProfileTests(unittest.TestCase):
    def test_versioned_prompt_edits_transcription_and_prose_without_weakening_original_profile(self):
        value = editorial_bundle()
        before = deepcopy(value)
        payload = _generation_payload(_validate_bundle(value), 'narrative', 'synthetic-local')
        self.assertEqual(value, before)
        for requirement in ('ASR homophones', 'reviewed name/alias', 'Merge repeated mentions',
                            '散文', '不能只照抄转录', 'separate paraphrased proposal',
                            'needs_review=true', 'do not guess a person'):
            self.assertIn(requirement, payload['prompt'])
        self.assertIn('林澄', payload['prompt'])
        self.assertNotIn('preserve names and verbatim', payload['prompt'])
        old = _generation_payload(bundle(), 'narrative', 'synthetic-local')
        self.assertIn('preserve names and verbatim', old['prompt'])
        self.assertNotIn('Saved-story editing task', old['prompt'])
        self.assertEqual(payload['options'], old['options'])

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

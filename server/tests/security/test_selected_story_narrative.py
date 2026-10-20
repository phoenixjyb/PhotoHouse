"""Closed v3 selected-source narrative contract and loopback transport tests.

All evidence below is synthetic. Provider behavior is exercised through
httpx.MockTransport; no model, household data, or network service is used.
"""

from copy import deepcopy
import json
import unittest

import httpx

from backend.app.access.memory_narrative import (
    LocalMemoryNarrativeError,
    LocalMemoryNarrator,
    _response_schema,
    _validate_bundle,
    validate_companion,
    validate_narrative,
)


OPERATION_ID = 'abcdefab-cdef-4abc-8def-abcdefabcdef'
SELECTION_REVISION = 'a' * 64


def v3_bundle(language='en', *, evidence=True, mixed=False):
    sources = []
    if evidence:
        family_id = 'family-en' if language == 'en' or mixed else 'family-zh'
        family_text = ('We planted beans together.' if language == 'en' or mixed
                       else '我们一起种了豆子。')
        caption_id = 'caption-zh' if language == 'zh' or mixed else 'caption-en'
        caption_text = ('菜畦旁边有一个蓝色的浇水壶。' if language == 'zh' or mixed
                        else 'A blue watering can beside the raised bed.')
        sources = [
            {'id': family_id, 'kind': 'family', 'text': family_text,
             'asset_id': 'asset-plant', 'author': 'Synthetic Aunt' if language == 'en' or mixed
             else '虚构阿姨', 'source_kind': 'family_note'},
            {'id': caption_id, 'kind': 'ai', 'text': caption_text,
             'asset_id': 'asset-can', 'author': None, 'source_kind': 'ai_caption'},
        ]
    chapters = ([
            {'id': 'chapter-plant', 'title': 'Planting beans' if language == 'en'
             else '一起种豆子', 'narration': '', 'asset_ids': ['asset-plant'],
             'evidence_ids': [family_id]},
            {'id': 'chapter-can', 'title': 'The blue can' if language == 'en'
             else '蓝色浇水壶', 'narration': '', 'asset_ids': ['asset-can'],
             'evidence_ids': [caption_id]},
        ] if evidence else [
            {'id': 'chapter-empty', 'title': 'A moment', 'narration': '',
             'asset_ids': ['asset-plant'], 'evidence_ids': []},
        ])
    return {
        'version': 3,
        'library_id': 'family-1',
        'target': {'type': 'draft', 'id': OPERATION_ID, 'revision': 0},
        'selection_revision': SELECTION_REVISION,
        'language': language,
        'title': 'A small garden story',
        'theme': 'planting together',
        'chapters': chapters,
        'sources': sources,
        'recent_turns': [],
        'instructions': 'Keep the story brief.',
    }


def result_for(bundle, *, narration=None, refs=None):
    chapters = []
    for chapter in bundle['chapters']:
        allowed = chapter['evidence_ids']
        chapters.append({
            'id': chapter['id'],
            'narration': (narration if narration is not None else
                          ('A short supported draft.' if allowed else '')),
            'source_ids': list(refs) if refs is not None else list(allowed),
        })
    return {'version': 1, 'title': 'A small garden story', 'chapters': chapters,
            'questions': [], 'needs_review': True}


def provider_envelope(response, model='qwen-local'):
    return json.dumps({'model': model, 'done': True,
                       'response': json.dumps(response, ensure_ascii=False)},
                      ensure_ascii=False).encode('utf-8')


class SelectedStoryNarrativeValidationTests(unittest.TestCase):
    def test_english_chinese_and_mixed_evidence_v3_bundles_validate(self):
        for language in ('en', 'zh'):
            with self.subTest(language=language):
                source = v3_bundle(language)
                self.assertEqual(source, _validate_bundle(source, allow_draft=True))
                self.assertEqual(result_for(source),
                                 validate_narrative(result_for(source), source))

        mixed = v3_bundle('zh', mixed=True)
        clean = _validate_bundle(mixed, allow_draft=True)
        self.assertEqual(['family_note', 'ai_caption'],
                         [source['source_kind'] for source in clean['sources']])
        self.assertEqual(['family', 'ai'], [source['kind'] for source in clean['sources']])

    def test_empty_selection_has_no_evidence_and_allows_blank_narration(self):
        source = v3_bundle('en', evidence=False)
        self.assertEqual([], _validate_bundle(source, allow_draft=True)['sources'])
        result = result_for(source)
        self.assertEqual('', validate_narrative(result, source)['chapters'][0]['narration'])
        result['chapters'][0]['narration'] = 'Unsupported guess.'
        with self.assertRaises(ValueError):
            validate_narrative(result, source)

    def test_shared_source_can_be_cited_across_chapters_when_origin_asset_is_unselected(self):
        source = v3_bundle(mixed=True)
        source['sources'][0]['asset_id'] = 'asset-outside-selection'
        source['chapters'][1]['evidence_ids'] = ['family-en', 'caption-zh']
        clean = _validate_bundle(source, allow_draft=True)
        self.assertEqual(2, len(clean['sources']))
        output = result_for(source)
        output['chapters'][1]['source_ids'] = ['family-en', 'caption-zh']
        self.assertEqual(['family-en', 'caption-zh'],
                         validate_narrative(output, source)['chapters'][1]['source_ids'])

    def test_caption_origins_must_match_every_referencing_selected_chapter(self):
        for source_kind, normalized_kind in (('ai_caption', 'ai'),
                                             ('family_edited_caption', 'family')):
            for origin, asset_id in (('missing', None), ('unselected', 'asset-unselected'),
                                     ('another chapter asset', 'asset-plant')):
                with self.subTest(source_kind=source_kind, origin=origin):
                    candidate = v3_bundle(mixed=True)
                    caption = candidate['sources'][1]
                    caption['source_kind'] = source_kind
                    caption['kind'] = normalized_kind
                    caption['asset_id'] = asset_id
                    with self.assertRaises(ValueError):
                        _validate_bundle(candidate, allow_draft=True)

            with self.subTest(source_kind=source_kind, origin='cited across chapters'):
                candidate = v3_bundle(mixed=True)
                caption = candidate['sources'][1]
                caption['source_kind'] = source_kind
                caption['kind'] = normalized_kind
                candidate['chapters'][0]['evidence_ids'].append(caption['id'])
                with self.assertRaises(ValueError):
                    _validate_bundle(candidate, allow_draft=True)

    def test_v3_requires_exact_top_level_and_source_shapes_and_no_transcript_kind(self):
        invalids = []
        source = v3_bundle()
        invalids.append(('extra top field', source | {'book_editorial': {}}))
        source = v3_bundle()
        del source['selection_revision']
        invalids.append(('missing digest', source))
        source = v3_bundle()
        source['sources'][0]['unexpected'] = True
        invalids.append(('extra source field', source))
        source = v3_bundle()
        source['sources'][0]['source_kind'] = 'transcript'
        invalids.append(('unsupported source kind', source))
        source = v3_bundle()
        source['sources'][0]['kind'] = 'ai'
        invalids.append(('wrong normalized kind', source))
        source = v3_bundle()
        source['sources'][0]['source_kind'] = 'family_edited_caption'
        source['sources'][0]['kind'] = 'ai'
        invalids.append(('edited caption has wrong normalized kind', source))
        source = v3_bundle()
        source['sources'][0]['transcript_text'] = 'not allowed'
        invalids.append(('transcript payload field', source))
        for reason, candidate in invalids:
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                _validate_bundle(candidate, allow_draft=True)

    def test_v3_rejects_noncanonical_target_digest_and_boolean_revision(self):
        mutations = [
            lambda b: b['target'].__setitem__('id', OPERATION_ID.upper()),
            lambda b: b['target'].__setitem__('id', '44444444444444448444444444444444'),
            lambda b: b['target'].__setitem__('type', 'story'),
            lambda b: b['target'].__setitem__('revision', True),
            lambda b: b['target'].__setitem__('revision', 1),
            lambda b: b.__setitem__('selection_revision', 'A' * 64),
            lambda b: b.__setitem__('selection_revision', 'a' * 63),
        ]
        for index, mutate in enumerate(mutations):
            candidate = v3_bundle()
            mutate(candidate)
            with self.subTest(case=index), self.assertRaises(ValueError):
                _validate_bundle(candidate, allow_draft=True)

    def test_v3_limits_chapters_assets_sources_citations_and_recent_turns(self):
        mutations = []
        candidate = v3_bundle()
        candidate['chapters'] = []
        mutations.append(('zero chapters', candidate))
        candidate = v3_bundle()
        for index in range(7):
            candidate['chapters'].append({'id': f'extra-{index}', 'title': 'x',
                'narration': '', 'asset_ids': [f'extra-asset-{index}'], 'evidence_ids': []})
        candidate['chapters'] = candidate['chapters'][2:]
        candidate['sources'] = []
        mutations.append(('seven chapters', candidate))
        candidate = v3_bundle()
        candidate['chapters'][0]['asset_ids'] = [f'a{i}' for i in range(25)]
        mutations.append(('more than 24 selected assets', candidate))
        candidate = v3_bundle()
        candidate['chapters'][0]['asset_ids'] = ['same', 'same']
        mutations.append(('duplicate asset in chapter', candidate))
        candidate = v3_bundle()
        candidate['chapters'][0]['asset_ids'] = []
        mutations.append(('no selected asset in chapter', candidate))
        candidate = v3_bundle()
        candidate['chapters'][0]['asset_ids'] = [f'a{i}' for i in range(5)]
        mutations.append(('five assets in one chapter', candidate))
        max_assets = v3_bundle()
        max_assets['chapters'] = [
            {'id': f'ch-{index}', 'title': 'Moment', 'narration': '',
             'asset_ids': [f'a-{index}-{asset}' for asset in range(4)], 'evidence_ids': []}
            for index in range(6)
        ]
        max_assets['sources'] = []
        candidate = v3_bundle()
        candidate['chapters'][0]['evidence_ids'] = [f'e{i}' for i in range(13)]
        mutations.append(('more than 12 citations per chapter', candidate))
        candidate = v3_bundle()
        candidate['recent_turns'] = [{'user': 'x', 'assistant': 'y'}]
        mutations.append(('history access', candidate))
        for reason, candidate in mutations:
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                _validate_bundle(candidate, allow_draft=True)
        self.assertEqual(24, len({asset for chapter in max_assets['chapters']
                                  for asset in chapter['asset_ids']}))
        self.assertEqual(max_assets, _validate_bundle(max_assets, allow_draft=True))

    def test_v3_source_union_and_global_unique_source_ids_are_enforced(self):
        candidates = []
        candidate = v3_bundle()
        candidate['sources'].append(deepcopy(candidate['sources'][0]))
        candidates.append(('duplicate source ID', candidate))
        candidate = v3_bundle()
        candidate['sources'].append({'id': 'orphan', 'kind': 'family', 'text': 'note',
            'asset_id': None, 'author': None, 'source_kind': 'family_note'})
        candidates.append(('foreign source outside evidence union', candidate))
        candidate = v3_bundle()
        candidate['chapters'][0]['evidence_ids'] = ['caption-zh']
        candidates.append(('evidence has no matching source union entry', candidate))
        for reason, candidate in candidates:
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                _validate_bundle(candidate, allow_draft=True)

    def test_v3_enforces_scalar_title_and_utf8_text_author_and_aggregate_budgets(self):
        for field, value in (
            ('title', 't' * 161),
            ('title', '😀' * 129),
        ):
            candidate = v3_bundle()
            candidate[field] = value
            with self.subTest(field=field, value_length=len(value)), self.assertRaises(ValueError):
                _validate_bundle(candidate, allow_draft=True)

        candidate = v3_bundle()
        candidate['chapters'][0]['title'] = '記' * 171
        with self.assertRaises(ValueError):
            _validate_bundle(candidate, allow_draft=True)
        candidate = v3_bundle()
        candidate['sources'][0]['text'] = 'x' * 8193
        with self.assertRaises(ValueError):
            _validate_bundle(candidate, allow_draft=True)
        candidate = v3_bundle()
        candidate['sources'][0]['text'] = ' \t\n'
        with self.assertRaises(ValueError):
            _validate_bundle(candidate, allow_draft=True)
        candidate = v3_bundle()
        candidate['sources'][0]['author'] = 'a' * 257
        with self.assertRaises(ValueError):
            _validate_bundle(candidate, allow_draft=True)
        candidate = v3_bundle()
        candidate['title'] = '😀' * 160
        with self.assertRaises(ValueError):
            _validate_bundle(candidate, allow_draft=True)

        candidate = v3_bundle()
        candidate['chapters'] = [{'id': 'chapter-big', 'title': 'Big', 'narration': '',
            'asset_ids': ['asset-plant'], 'evidence_ids': [f'ev-{i}' for i in range(7)]}]
        candidate['sources'] = [{'id': f'ev-{i}', 'kind': 'family', 'text': 'x' * 7100,
            'asset_id': None, 'author': None, 'source_kind': 'family_note'} for i in range(7)]
        with self.assertRaises(ValueError):
            _validate_bundle(candidate, allow_draft=True)

    def test_narrative_output_cannot_change_target_chapters_assets_or_metadata(self):
        source = v3_bundle()
        valid = result_for(source)
        self.assertEqual(valid, validate_narrative(valid, source))
        invalids = []
        for key, value in (('target', source['target']), ('selection_revision', 'f' * 64),
                           ('asset_ids', ['foreign-asset']), ('metadata', {'trusted': True})):
            invalids.append((key, valid | {key: value}))
        changed = deepcopy(valid)
        changed['chapters'][0]['id'] = 'foreign-chapter'
        invalids.append(('forged chapter ID', changed))
        changed = deepcopy(valid)
        changed['chapters'].reverse()
        invalids.append(('reordered chapters', changed))
        changed = deepcopy(valid)
        changed['needs_review'] = False
        invalids.append(('review bypass', changed))
        changed = deepcopy(valid)
        changed['title'] = 't' * 161
        invalids.append(('title exceeds scalar limit', changed))
        changed = deepcopy(valid)
        changed['title'] = '😀' * 129
        invalids.append(('title exceeds UTF-8 byte limit', changed))
        changed = deepcopy(valid)
        changed['chapters'][0]['source_ids'] = [source['chapters'][1]['evidence_ids'][0]]
        invalids.append(('foreign citation', changed))
        changed = deepcopy(valid)
        changed['chapters'][0]['narration'] = 'A claim with no citation.'
        changed['chapters'][0]['source_ids'] = []
        invalids.append(('invalid citation relationship', changed))
        for reason, candidate in invalids:
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                validate_narrative(candidate, source)

    def test_companion_validation_rejects_draft_bundle(self):
        reply = {'version': 1, 'kind': 'clarification', 'reply': 'Could you add context?',
                 'source_ids': [], 'questions': [], 'proposal': None}
        with self.assertRaises(ValueError):
            validate_companion(reply, v3_bundle())


class SelectedStoryNarrativeTransportTests(unittest.TestCase):
    def narrator(self, response):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx.Response(200, content=response)

        return LocalMemoryNarrator('http://127.0.0.1:11434', 'qwen-local',
                                   transport=httpx.MockTransport(handler)), seen

    def test_narrative_transport_preserves_original_source_kind_and_schema_has_only_ids(self):
        source = v3_bundle('zh', mixed=True)
        response = provider_envelope(result_for(source))
        model, seen = self.narrator(response)
        self.assertEqual(result_for(source), model.narrative(source))
        self.assertEqual(1, len(seen))
        request = json.loads(seen[0].content)
        prompt = request['prompt']
        self.assertIn('"source_kind":"family_note"', prompt)
        self.assertIn('"source_kind":"ai_caption"', prompt)
        self.assertIn('"kind":"family"', prompt)
        self.assertIn('"kind":"ai"', prompt)
        self.assertNotIn('We planted beans together.', json.dumps(request['format']))
        self.assertNotIn('蓝色的浇水壶', json.dumps(request['format']))
        allowed = json.dumps(request['format'], ensure_ascii=False)
        self.assertIn('family-en', allowed)
        self.assertIn('caption-zh', allowed)
        self.assertNotIn('source_kind', allowed)
        self.assertEqual(160, request['format']['properties']['title']['maxLength'])

    def test_edited_caption_kind_and_legacy_draft_targets_are_closed_before_http(self):
        source = v3_bundle()
        source['sources'][0]['source_kind'] = 'family_edited_caption'
        source['sources'][0]['kind'] = 'family'
        model, seen = self.narrator(provider_envelope(result_for(source)))
        self.assertEqual(result_for(source), model.narrative(source))
        request = json.loads(seen[0].content)
        self.assertIn('"source_kind":"family_edited_caption"', request['prompt'])
        self.assertIn('"kind":"family"', request['prompt'])
        self.assertEqual(160, request['format']['properties']['title']['maxLength'])

        with self.assertRaises(ValueError):
            _validate_bundle(source)
        with self.assertRaises(ValueError):
            _validate_bundle(source, allow_draft=1)

        for version in (1, 2):
            legacy = deepcopy(source)
            legacy['version'] = version
            legacy.pop('selection_revision')
            legacy['target'] = {'type': 'draft', 'id': OPERATION_ID, 'revision': 0}
            for item in legacy['sources']:
                item.pop('source_kind')
            if version == 2:
                legacy['book_editorial'] = {}
            request_model, requests = self.narrator(provider_envelope(result_for(source)))
            with self.subTest(legacy_version=version), self.assertRaises(ValueError):
                request_model.narrative(legacy)
            self.assertEqual([], requests)

    def test_companion_and_invalid_narrative_bundles_fail_before_provider_http(self):
        source = v3_bundle()
        model, seen = self.narrator(provider_envelope(result_for(source)))
        with self.assertRaises(ValueError):
            model.companion(source)
        self.assertEqual([], seen)

        invalid = deepcopy(source)
        invalid['target']['revision'] = True
        with self.assertRaises(ValueError):
            model.narrative(invalid)
        self.assertEqual([], seen)

    def test_response_schema_refuses_v3_for_companion_task(self):
        source = _validate_bundle(v3_bundle(), allow_draft=True)
        with self.assertRaises(ValueError):
            _response_schema(source, 'companion')

    def test_provider_output_with_bad_citation_or_review_flag_is_sanitized(self):
        source = v3_bundle()
        for reason, mutate in (
            ('foreign citation', lambda output: output['chapters'][0].__setitem__(
                'source_ids', ['caption-en'])),
            ('review false', lambda output: output.__setitem__('needs_review', False)),
            ('forged source metadata', lambda output: output.__setitem__(
                'sources', deepcopy(source['sources']))),
        ):
            output = result_for(source)
            mutate(output)
            model, seen = self.narrator(provider_envelope(output))
            with self.subTest(reason=reason), self.assertRaises(LocalMemoryNarrativeError) as caught:
                model.narrative(source)
            self.assertEqual('invalid_response', caught.exception.category)
            self.assertEqual(1, len(seen))


if __name__ == '__main__':
    unittest.main()

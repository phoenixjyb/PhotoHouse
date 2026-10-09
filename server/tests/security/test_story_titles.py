import json
import unittest

import httpx

from app.access.memory_narrative import LocalMemoryNarrativeError
from app.access.story_titles import (
    MAX_BUNDLE_BYTES,
    LocalStoryTitleSuggester,
    validate_bundle,
    validate_suggestions,
)


REVISION = 'a' * 64


def bundle(sources=None):
    return {
        'version': 1,
        'language': 'zh',
        'theme': 'trip',
        'selection_revision': REVISION,
        'sources': ([{'id': 'family-1', 'source': 'family', 'text': '海边散步'}]
                    if sources is None else sources),
    }


def response_for(payload, *, status=200):
    return httpx.Response(status, content=json.dumps(payload, ensure_ascii=False).encode('utf-8'))


class StoryTitleValidationTests(unittest.TestCase):
    def test_valid_bundle_and_suggestions_are_returned_in_exact_shapes(self):
        source_bundle = validate_bundle(bundle())
        self.assertEqual(set(source_bundle), {
            'version', 'language', 'theme', 'selection_revision', 'sources'})
        result = validate_suggestions({
            'version': 1,
            'selection_revision': REVISION,
            'titles': [{'text': '海边的一天', 'source_ids': ['family-1']}],
            'needs_review': True,
        }, source_bundle)
        self.assertEqual(result, {
            'version': 1, 'selection_revision': REVISION,
            'titles': [{'text': '海边的一天', 'source_ids': ['family-1']}],
            'needs_review': True,
        })

    def test_bundle_rejects_shape_revision_source_and_size_violations(self):
        invalid = []
        value = bundle(); value['extra'] = 1; invalid.append(value)
        value = bundle(); value['version'] = True; invalid.append(value)
        value = bundle(); value['language'] = 'zh-CN'; invalid.append(value)
        value = bundle(); value['theme'] = 'unsupported'; invalid.append(value)
        value = bundle(); value['selection_revision'] = 'A' * 64; invalid.append(value)
        value = bundle([{'id': '../unsafe', 'source': 'family', 'text': 'x'}]); invalid.append(value)
        value = bundle([{'id': 'x', 'source': 'other', 'text': 'x'}]); invalid.append(value)
        value = bundle([{'id': 'x', 'source': 'family', 'text': 'x' * 1801}]); invalid.append(value)
        value = bundle([{'id': 'same', 'source': 'family', 'text': 'a'},
                        {'id': 'same', 'source': 'draft', 'text': 'b'}]); invalid.append(value)
        value = bundle([{'id': str(i), 'source': 'family', 'text': 'x'} for i in range(80)]); invalid.append(value)
        value = bundle([{'id': 'x', 'source': 'family', 'text': '🙂' * MAX_BUNDLE_BYTES}]); invalid.append(value)
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_bundle(candidate)
        self.assertEqual(validate_bundle(
            bundle([{'id': 'x', 'source': 'family', 'text': 'line one\nline two'}])
        )['sources'][0]['text'], 'line one\nline two')

    def test_bundle_rejects_total_size_overflow_with_individually_valid_sources(self):
        sources = [
            {'id': f'source-{index}', 'source': 'family', 'text': 'x' * 1700}
            for index in range(40)
        ]
        self.assertTrue(all(len(source['text'].encode('utf-8')) <= 1800 for source in sources))
        with self.assertRaises(ValueError):
            validate_bundle(bundle(sources))

    def test_suggestions_reject_bad_citations_titles_and_review_flag(self):
        good = {'version': 1, 'selection_revision': REVISION,
                'titles': [{'text': '海边的一天', 'source_ids': ['family-1']}],
                'needs_review': True}
        cases = []
        value = dict(good); value['extra'] = True; cases.append(value)
        value = dict(good); value['selection_revision'] = 'b' * 64; cases.append(value)
        value = dict(good); value['needs_review'] = False; cases.append(value)
        value = dict(good); value['titles'] = [
            {'text': '海边的一天', 'source_ids': ['family-1']}] * 2; cases.append(value)
        value = dict(good); value['titles'] = [{'text': '  ', 'source_ids': ['family-1']}]; cases.append(value)
        value = dict(good); value['titles'] = [{'text': 'line\nbreak', 'source_ids': ['family-1']}]; cases.append(value)
        value = dict(good); value['titles'] = [{'text': 'x' * 161, 'source_ids': ['family-1']}]; cases.append(value)
        value = dict(good); value['titles'] = [{'text': 'ok', 'source_ids': []}]; cases.append(value)
        value = dict(good); value['titles'] = [{'text': 'ok', 'source_ids': ['missing']}]; cases.append(value)
        value = dict(good); value['titles'] = [{'text': 'ok', 'source_ids': ['family-1', 'family-1']}]; cases.append(value)
        value = dict(good); value['titles'] = [{'text': 'x' * 161, 'source_ids': ['family-1']}]
        value['titles'][0]['text'] = '🙂' * 161; cases.append(value)
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_suggestions(candidate, bundle())

    def test_empty_sources_only_allow_empty_titles(self):
        empty = bundle([])
        self.assertEqual(validate_suggestions({
            'version': 1, 'selection_revision': REVISION,
            'titles': [], 'needs_review': True,
        }, empty)['titles'], [])
        with self.assertRaises(ValueError):
            validate_suggestions({
                'version': 1, 'selection_revision': REVISION,
                'titles': [{'text': 'title', 'source_ids': ['x']}], 'needs_review': True,
            }, empty)


class LocalStoryTitleSuggesterTests(unittest.TestCase):
    def adapter(self, result=None, *, status=200, body=None, transport=None, **kwargs):
        if transport is None:
            if body is None:
                body = {'model': 'local-model', 'done': True,
                        'response': json.dumps(result, ensure_ascii=False)}
            transport = httpx.MockTransport(lambda request: response_for(body, status=status))
        return LocalStoryTitleSuggester('http://127.0.0.1:11434', 'local-model',
                                        transport=transport, **kwargs)

    def test_suggest_posts_explicit_bounded_json_request_and_validates_citations(self):
        seen = {}
        answer = {'version': 1, 'selection_revision': REVISION,
                  'titles': [{'text': '海边的一天', 'source_ids': ['family-1']}],
                  'needs_review': True}

        def handler(request):
            seen['url'] = str(request.url)
            seen['body'] = json.loads(request.content)
            return response_for({'model': 'local-model', 'done': True,
                                 'response': json.dumps(answer, ensure_ascii=False)})

        result = LocalStoryTitleSuggester(
            'http://localhost:11434/api/generate', 'local-model',
            transport=httpx.MockTransport(handler)).suggest(bundle())
        self.assertEqual(result['titles'][0]['text'], '海边的一天')
        self.assertEqual(seen['url'], 'http://localhost:11434/api/generate')
        self.assertEqual(seen['body']['model'], 'local-model')
        self.assertIs(seen['body']['stream'], False)
        self.assertIs(seen['body']['think'], False)
        self.assertEqual(seen['body']['format'], 'json')
        self.assertIn('Do not invent dates, people, identities, relationships, or activities',
                      seen['body']['prompt'])
        self.assertIn('Keep every user-provided source text untouched', seen['body']['prompt'])

    def test_empty_sources_skip_provider(self):
        def fail(_request):
            raise AssertionError('provider should not be called for empty sources')
        result = LocalStoryTitleSuggester(
            'http://127.0.0.1:11434', 'local-model',
            transport=httpx.MockTransport(fail)).suggest(bundle([]))
        self.assertEqual(result['titles'], [])
        self.assertIs(result['needs_review'], True)

    def test_provider_status_is_sanitized_and_http_status_is_retained(self):
        with self.assertRaises(LocalMemoryNarrativeError) as caught:
            self.adapter(status=503, body={}).suggest(bundle())
        self.assertEqual(caught.exception.category, 'provider')
        self.assertEqual(caught.exception.provider_http_status, 503)
        self.assertNotIn('海边', str(caught.exception))

    def test_invalid_envelope_and_duplicate_response_keys_are_rejected(self):
        bad_bodies = [
            {'model': 'another-model', 'done': True,
             'response': json.dumps({'version': 1})},
            {'model': 'local-model', 'done': False, 'response': '{}'},
            {'model': 'local-model', 'done': True,
             'response': '{"version":1,"version":1}'},
        ]
        for body in bad_bodies:
            with self.subTest(body=body), self.assertRaises(LocalMemoryNarrativeError) as caught:
                self.adapter(body=body).suggest(bundle())
            self.assertEqual(caught.exception.category, 'invalid_response')

    def test_invalid_provider_suggestion_is_sanitized(self):
        invalid = {'version': 1, 'selection_revision': REVISION,
                   'titles': [{'text': 'unbound', 'source_ids': ['unknown']}],
                   'needs_review': True}
        with self.assertRaises(LocalMemoryNarrativeError) as caught:
            self.adapter(invalid).suggest(bundle())
        self.assertEqual(caught.exception.category, 'invalid_response')

    def test_oversized_provider_response_is_rejected(self):
        large_body = b'x' * (128 * 1024 + 1)
        transport = httpx.MockTransport(
            lambda _request: httpx.Response(200, content=large_body))
        with self.assertRaises(LocalMemoryNarrativeError) as caught:
            LocalStoryTitleSuggester('http://127.0.0.1:11434', 'local-model',
                                     transport=transport).suggest(bundle())
        self.assertEqual(caught.exception.category, 'invalid_response')
        self.assertNotIn('xxxxx', str(caught.exception))

    def test_http_transport_failure_is_sanitized(self):
        def fail(_request):
            raise httpx.ConnectError('private-host.example secret path')
        transport = httpx.MockTransport(fail)
        with self.assertRaises(LocalMemoryNarrativeError) as caught:
            LocalStoryTitleSuggester('http://127.0.0.1:11434', 'local-model',
                                     transport=transport).suggest(bundle())
        self.assertEqual(caught.exception.category, 'transport')
        self.assertNotIn('private-host', str(caught.exception))
        self.assertNotIn('secret path', str(caught.exception))

    def test_simulated_monotonic_deadline_expires_without_waiting(self):
        times = iter((0.0, 1.0))
        transport = httpx.MockTransport(lambda _request: response_for({
            'model': 'local-model', 'done': True,
            'response': json.dumps({'version': 1, 'selection_revision': REVISION,
                                    'titles': [], 'needs_review': True}),
        }))
        with self.assertRaises(LocalMemoryNarrativeError) as caught:
            LocalStoryTitleSuggester('http://127.0.0.1:11434', 'local-model', timeout=1,
                                     transport=transport, monotonic=lambda: next(times)).suggest(bundle())
        self.assertEqual(caught.exception.category, 'transport')

    def test_non_loopback_urls_and_bad_model_or_timeout_are_rejected(self):
        for url in ('https://127.0.0.1:11434', 'http://example.test:11434',
                    'http://127.0.0.1:11434/path'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                LocalStoryTitleSuggester(url, 'local-model')
        for model, timeout in (('', 5), (' spaced ', 5), ('local-model', 0),
                               ('local-model', float('nan')), ('local-model', 121)):
            with self.subTest(model=model, timeout=timeout), self.assertRaises(ValueError):
                LocalStoryTitleSuggester('http://127.0.0.1:11434', model, timeout)


if __name__ == '__main__':
    unittest.main()

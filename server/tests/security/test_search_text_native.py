"""Exact optional-native behavior against the authoritative Python matcher."""
import importlib
import os
import random
import sys
import types
import unittest
from unittest.mock import patch

from app.access import search_text as text


class NativeLiteral(unittest.TestCase):
    def scan(self, contents, phrase, engine, *, cancel_at=None):
        count = 0

        def check():
            nonlocal count
            count += 1
            if count == cancel_at:
                raise InterruptedError('test_cancel')

        cache = text.TextQueryCache(engine=engine)
        sources = text.normalize_sources([
            {'source': 'photo_memory' if i % 2 else 'caption',
             'source_id': str(i), 'revision': i, 'content': content,
             'private_extra': 'must_not_cross'}
            for i, content in enumerate(contents)], check)
        found = text.match_text({'text_sources': sources}, text.normalize_filters({'text': phrase}),
                                check, query_cache=cache)
        return found, count

    def test_real_binding_matches_mixed_script_and_fallback(self):
        rng = random.Random(147)
        cases = [(['海边合影 family picnic', '（海边合影）'], '海边合影'),
                 (['abc中def', 'abc 中 def', '中abc中def中'], 'abc中def'),
                 (['Straße café İ ı K', '🙂旅行\uf900\u0301', '\ud800 picnic'], 'picnic'),
                 (['café picnic', 'Straße café'], 'café'),
                 (['全角ＡＢＣ和旅行'], 'ABC'),
                 (['abc' * 22000], 'abc'),
                 (['aaaa', '---', '海边海边海边'], 'aa')]
        alphabet = 'abc09_海边合影，。！？- 🙂éİ\u0301\uf900\ud800'
        for _ in range(1000):
            content = ''.join(rng.choice(alphabet) for _ in range(rng.randrange(0, 150)))
            start = rng.randrange(len(content) + 1)
            cases.append(([content], content[start:start + rng.randrange(1, 14)] or 'a'))
        for contents, phrase in cases:
            expected = self.scan(contents, phrase, 'python')
            self.assertEqual(self.scan(contents, phrase, 'rust'), expected)
            self.assertEqual(self.scan(contents, phrase, 'shadow'), expected)

    def test_fast_character_domain_matches_python_word_and_cjk_policy(self):
        native = importlib.import_module('photohouse_literal_kernel')
        for code in [*range(128), *range(0x3400, 0x4DC0), *range(0x4E00, 0xA000)]:
            char = chr(code)
            self.assertEqual(native.quality(char, char),
                             (text._coverage(char, char),
                              int(text._has_whole_phrase_boundary(char, char)), -1))

    def test_callbacks_reason_cap_and_original_exception_are_preserved(self):
        contents = ['海边合影'] * 47 + ['海边合影 family picnic']
        baseline, calls = self.scan(contents, '海边合影', 'python')
        self.assertEqual(len(baseline[1]), text.MAX_MATCH_REASONS)
        self.assertTrue(all(set(r) == {'source', 'source_id', 'revision'} for r in baseline[1]))
        self.assertEqual(self.scan(contents, '海边合影', 'rust'), (baseline, calls))
        for at in range(1, calls + 1):
            for engine in ('python', 'rust', 'shadow'):
                with self.assertRaisesRegex(InterruptedError, '^test_cancel$'):
                    self.scan(contents, '海边合影', engine, cancel_at=at)

    def test_default_does_not_load_native_and_invalid_selector_refuses(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(importlib, 'import_module') as load:
            self.assertIsNone(text.TextQueryCache()._native)
            load.assert_not_called()
        with self.assertRaisesRegex(ValueError, '^invalid_literal_text_engine$'):
            text.TextQueryCache(engine='unknown')
        with patch.object(importlib, 'import_module', side_effect=ImportError('private detail')):
            with self.assertRaisesRegex(RuntimeError, '^literal_text_kernel_unavailable$'):
                text.TextQueryCache(engine='rust')

    def test_shadow_refuses_mismatch_without_private_text_in_error(self):
        fake = types.SimpleNamespace(POLICY_VERSION=1, quality=lambda content, phrase: (0, 0, -len(content)))
        with patch.dict(sys.modules, {'photohouse_literal_kernel': fake}):
            with self.assertRaisesRegex(RuntimeError, '^literal_text_shadow_mismatch$'):
                self.scan(['private picnic'], 'picnic', 'shadow')
        fake.quality = lambda content, phrase: (1001, 0, -len(content))
        with patch.dict(sys.modules, {'photohouse_literal_kernel': fake}):
            with self.assertRaisesRegex(RuntimeError, '^invalid_literal_text_kernel_result$'):
                self.scan(['private picnic'], 'picnic', 'rust')

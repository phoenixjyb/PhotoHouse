"""Differential checks against the frozen pre-optimization literal policy."""
from dataclasses import replace
from pathlib import Path
import random
import re
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from app.access import search_text as text

# Frozen from 018668c: keep these independent of optimized token preparation.
WORD = re.compile(r'[\w]+', re.UNICODE)
CJK = re.compile(r'[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]')


def old_tokens(value):
    tokens = []
    for match in WORD.finditer(value):
        token = match.group(0)
        if CJK.search(token):
            tokens.extend(char for char in token if CJK.fullmatch(char))
            remainder = ''.join(char for char in token if not CJK.fullmatch(char))
            if remainder:
                tokens.append(remainder)
        else:
            tokens.append(token)
    return tuple(tokens)


def old_match(row, filters, check=lambda: None):
    check()
    if 'text' not in filters:
        return True, [], (0, 0, 0, 0)
    phrase = filters.get('text')
    if type(phrase) is not str or not phrase:
        return False, [], (0, 0, 0, 0)
    reasons, best, authored = [], None, 0
    sources = row.get('text_sources', ())
    if type(sources) not in (tuple, list):
        sources = ()
    for source in sources:
        check()
        if type(source) is not text.NormalizedSource or phrase not in source.normalized_text:
            continue
        if len(reasons) < 43:
            reasons.append(source.reason())
        authored = max(authored, int(source.source in ('photo_memory', 'edited_caption')))
        tokens = old_tokens(phrase)
        available = set(old_tokens(source.normalized_text)) if tokens else set()
        coverage = sum(token in available for token in tokens) * 1000 // len(tokens) if tokens else 0
        offset, boundary = 0, False
        while True:
            start = source.normalized_text.find(phrase, offset)
            if start < 0:
                break
            end = start + len(phrase)
            left = start == 0 or not (source.normalized_text[start - 1].isalnum() or source.normalized_text[start - 1] == '_')
            right = end == len(source.normalized_text) or not (source.normalized_text[end].isalnum() or source.normalized_text[end] == '_')
            if left and right:
                boundary = True
                break
            offset = start + 1
        quality = coverage, int(boundary), -len(source.normalized_text)
        if best is None or quality > best:
            best = quality
    check()
    return (True, reasons, (authored, *best)) if best is not None else (False, [], (0, 0, 0, 0))


def row(contents):
    return {'text_sources': text.normalize_sources([
        {'source': source, 'source_id': str(index), 'revision': 1, 'content': content}
        for index, (source, content) in enumerate(contents)], lambda: None)}


class TextReuseTests(unittest.TestCase):
    def test_all_unicode_codepoints_keep_exact_old_token_sequence(self):
        # Covers both sides of every CJK range and Python's complete Unicode
        # word table, including supplementary planes and unpaired surrogates.
        value = ''.join(map(chr, range(0x110000)))
        self.assertEqual(text._tokens(value), old_tokens(value))

    def test_mixed_scripts_and_normalization_keep_exact_quality_and_reasons(self):
        rng = random.Random(20261121)
        pieces = ['海边', '合影', 'ＡＢＣ', 'Straße', 'İ', 'K', 'a_b', 'e\u0301',
                  '١٢٣', '²', '\u3400', '\u4dbf', '\uf900', '\ufaff', '𠀀',
                  '한글', 'ไทย', '😀', '\u200d', '\x00', ' ', '。', '!!!']
        cache = text.TextQueryCache()
        for _ in range(1000):
            words = ''.join(rng.choices(pieces, k=rng.randint(1, 16)))
            query = rng.choice(pieces)
            sources = row([('edited_caption', words), ('photo_memory', query + words),
                           ('generated_caption', words + query)])
            filters = text.normalize_filters({'text': query})
            expected = old_match(sources, filters)
            self.assertEqual(text.match_text(sources, filters), expected)
            self.assertEqual(text.match_text(sources, filters, query_cache=cache), expected)

    def test_query_tokens_are_reused_across_sources_and_rows_only(self):
        cache = text.TextQueryCache()
        sources = row([('edited_caption', '海边合影 family'), ('photo_memory', '合影 海边合影')])
        filters = {'text': '海边合影'}
        original = text._tokens
        with patch.object(text, '_tokens', wraps=original) as calls:
            for _ in range(5):
                self.assertTrue(text.match_text(sources, filters, query_cache=cache)[0])
        self.assertEqual(sum(c.args == ('海边合影',) for c in calls.call_args_list), 1)
        self.assertEqual(calls.call_count, 11)  # one query, every current source
        with patch.object(text, '_tokens', wraps=original) as calls:
            text.match_text(sources, filters)
        self.assertEqual(sum(c.args == ('海边合影',) for c in calls.call_args_list), 1)

    def test_no_match_or_immediate_cancel_does_not_prepare_tokens(self):
        sources = row([('photo_memory', 'city garden')])
        with patch.object(text, '_tokens', side_effect=AssertionError('unneeded token work')):
            self.assertFalse(text.match_text(sources, {'text': 'beach'},
                                            query_cache=text.TextQueryCache())[0])
            marker = LookupError('stop')
            def stop():
                raise marker
            with self.assertRaises(LookupError) as caught:
                text.match_text(sources, {'text': 'city'}, stop, query_cache=text.TextQueryCache())
            self.assertIs(caught.exception, marker)

    def test_filter_refinement_and_current_source_revision_never_reuse_old_evidence(self):
        cache = text.TextQueryCache()
        filters = {'text': 'park'}
        before = row([('photo_memory', 'park')])
        self.assertEqual(text.match_text(before, filters, query_cache=cache), old_match(before, filters))
        changed = replace(before['text_sources'][0], revision=2, content='beach', normalized_text='beach')
        after = {'text_sources': (changed,)}
        self.assertFalse(text.match_text(after, filters, query_cache=cache)[0])
        filters['text'] = 'beach'
        self.assertEqual(text.match_text(after, filters, query_cache=cache), old_match(after, filters))
        self.assertEqual(text.match_text(after, filters, query_cache=cache)[1][0]['revision'], 2)
        self.assertEqual(text.match_text(before, {'text': 'park'}, query_cache=cache)[1][0]['revision'], 1)

    def test_callback_mutation_and_every_cancellation_boundary_are_unchanged(self):
        sources = row([('photo_memory', 'park beach') for _ in range(5)])
        for limit in range(1, 8):
            records = []
            for implementation in ['old', 'new']:
                filters, checks = {'text': 'park'}, []
                marker = LookupError('owned cancellation')
                def check():
                    checks.append(len(checks) + 1)
                    if len(checks) == 2:
                        filters['text'] = 'beach'
                    if len(checks) == limit:
                        raise marker
                try:
                    result = (old_match(sources, filters, check) if implementation == 'old' else
                              text.match_text(sources, filters, check, query_cache=text.TextQueryCache()))
                except LookupError as error:
                    self.assertIs(error, marker)
                    records.append(('cancelled', checks))
                else:
                    records.append((result, checks))
            self.assertEqual(*records)

    def test_reason_cap_remains_43_and_private_content_never_enters_reasons(self):
        sources = row([('photo_memory', 'private park words') for _ in range(60)])
        expected = old_match(sources, {'text': 'park'})
        actual = text.match_text(sources, {'text': 'park'}, query_cache=text.TextQueryCache())
        self.assertEqual(actual, expected)
        self.assertEqual(len(actual[1]), 43)
        self.assertTrue(all(set(reason) == {'source', 'source_id', 'revision'} for reason in actual[1]))


if __name__ == '__main__':
    unittest.main()

"""Deterministic parsing for opt-in saved-memory search commands."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.assistant_memory_discovery import MAX_QUERY_BYTES, MAX_QUERY_CHARS
from app.access.assistant_memory_intent import (SavedMemoryIntent,
                                                parse_saved_memory_command)


class AssistantMemoryIntentTests(unittest.TestCase):
    def test_current_chinese_reader_names_search_the_exact_saved_kind(self):
        for command in ('找回忆录 春节。', '搜索回忆录「春节」'):
            with self.subTest(command=command):
                self.assertEqual(parse_saved_memory_command(command), SavedMemoryIntent('memoir', '春节'))
        self.assertEqual(parse_saved_memory_command('找故事 野餐！'), SavedMemoryIntent('story', '野餐'))
        self.assertEqual(parse_saved_memory_command('找回忆录'), SavedMemoryIntent('memoir', ''))
        self.assertEqual(parse_saved_memory_command('找故事 删除'), SavedMemoryIntent('story', '删除'))

    def test_chinese_prefixes_accept_asr_spacing_and_trim_outer_whitespace(self):
        self.assertEqual(parse_saved_memory_command('  找回忆野餐  '),
                         SavedMemoryIntent(None, '野餐'))
        self.assertEqual(parse_saved_memory_command('搜索故事 野餐'),
                         SavedMemoryIntent('story', '野餐'))
        self.assertEqual(parse_saved_memory_command('找回忆册野餐'),
                         SavedMemoryIntent('memoir', '野餐'))

    def test_longest_chinese_prefix_wins(self):
        intent = parse_saved_memory_command('找回忆册的野餐')
        self.assertEqual(intent.kind, 'memoir')
        self.assertEqual(intent.phrase, '的野餐')

    def test_english_prefixes_are_case_insensitive_and_word_bounded(self):
        self.assertEqual(parse_saved_memory_command('FIND SAVED STORY picnic'),
                         SavedMemoryIntent('story', 'picnic'))
        self.assertEqual(parse_saved_memory_command('Find Memoir spring'),
                         SavedMemoryIntent('memoir', 'spring'))
        self.assertEqual(parse_saved_memory_command('Search saved memories for 春节'),
                         SavedMemoryIntent(None, '春节'))
        self.assertIsNone(parse_saved_memory_command('find memoirist spring'))
        self.assertIsNone(parse_saved_memory_command('find saved storybook picnic'))
        self.assertEqual(parse_saved_memory_command('Find \t memoir 春节?'),
                         SavedMemoryIntent('memoir', '春节'))

    def test_unquoted_terminal_spoken_punctuation_is_normalized(self):
        self.assertEqual(parse_saved_memory_command('找回忆 野餐？！。'),
                         SavedMemoryIntent(None, '野餐'))
        self.assertEqual(parse_saved_memory_command('find saved story picnic?!'),
                         SavedMemoryIntent('story', 'picnic'))

    def test_matching_quoted_phrases_preserve_inner_punctuation_and_metacharacters(self):
        samples = (
            ('找回忆 "%_\\？"', '%_\\？'),
            ('搜索故事 “野餐？！”', '野餐？！'),
            ('找回忆册「旅程。_」', '旅程。_'),
            ("find memoir 'Picnic?!_%'", 'Picnic?!_%'),
            ('find saved story "picnic?".', 'picnic?'),
        )
        for command, expected in samples:
            with self.subTest(command=command):
                self.assertEqual(parse_saved_memory_command(command).phrase, expected)

    def test_mixed_language_phrase_stays_literal(self):
        self.assertEqual(parse_saved_memory_command('find saved story 春节_野餐'),
                         SavedMemoryIntent('story', '春节_野餐'))

    def test_recognized_empty_and_punctuation_only_phrases_request_clarification(self):
        self.assertEqual(parse_saved_memory_command('找回忆'), SavedMemoryIntent(None, ''))
        self.assertEqual(parse_saved_memory_command('搜索故事 ？！。'),
                         SavedMemoryIntent('story', ''))
        self.assertEqual(parse_saved_memory_command('find memoir'),
                         SavedMemoryIntent('memoir', ''))

    def test_literal_wildcard_and_sql_metacharacters_are_not_interpreted(self):
        self.assertEqual(parse_saved_memory_command(r"找回忆 100%_\' OR 1=1 --"),
                         SavedMemoryIntent(None, r"100%_\' OR 1=1 --"))

    def test_ordinary_media_and_mutation_requests_are_unrecognized(self):
        for text in ('找照片', 'find photos', 'open first', '删除故事 野餐',
                     '编辑回忆册 标题', 'delete saved story picnic',
                     'modify memoir introduction'):
            with self.subTest(text=text):
                self.assertIsNone(parse_saved_memory_command(text))

    def test_invalid_raw_text_and_over_limit_recognized_phrases_fail_closed(self):
        invalid = (
            'x' * 1025,
            'find saved story ' + 'x' * (MAX_QUERY_CHARS + 1),
            'find saved story ' + '野' * ((MAX_QUERY_BYTES // 3) + 1),
            '找回忆 phrase\nwith newline',
            '找回忆 phrase\x01',
            '找回忆 ' + '\ud800',
        )
        for command in invalid:
            with self.subTest(command=repr(command[:48])):
                with self.assertRaises(ValueError):
                    parse_saved_memory_command(command)

    def test_query_boundaries_apply_after_quote_unwrap(self):
        allowed = 'x' * MAX_QUERY_CHARS
        self.assertEqual(parse_saved_memory_command(f'找回忆 "{allowed}"').phrase,
                         allowed)
        phrase = '野' * 106 + 'ab'
        self.assertEqual(len(phrase.encode('utf-8')), MAX_QUERY_BYTES)
        self.assertEqual(parse_saved_memory_command('找回忆' + phrase).phrase, phrase)

    def test_normalization_preserves_internal_punctuation_and_literal_effect_words(self):
        self.assertEqual(parse_saved_memory_command('找回忆 2026.09.23 的野餐。'),
                         SavedMemoryIntent(None, '2026.09.23 的野餐'))
        self.assertEqual(parse_saved_memory_command('搜索故事 删除所有内容'),
                         SavedMemoryIntent('story', '删除所有内容'))
        # Recognizing search words creates only an immutable phrase, never an
        # action, source ID or trusted context.
        self.assertEqual(set(SavedMemoryIntent.__dataclass_fields__), {'kind', 'phrase'})

    def test_intent_is_frozen(self):
        intent = parse_saved_memory_command('找回忆 春节')
        with self.assertRaises(FrozenInstanceError):
            intent.phrase = 'different'


if __name__ == '__main__':
    unittest.main()

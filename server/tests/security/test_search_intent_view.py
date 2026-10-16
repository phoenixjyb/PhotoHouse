"""Offset-preserving tests for the private descriptive-provider query view."""
from datetime import date
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.search_intent_view import REDACTION_MARKER, scene_view


TODAY = date(2032, 9, 14)


class SearchIntentViewTests(unittest.TestCase):
    def assert_same_offsets(self, source, view):
        self.assertEqual(len(source), len(view))
        for original, visible in zip(source, view):
            self.assertTrue(original == visible or visible == REDACTION_MARKER)

    def test_masks_quotes_resolved_label_dates_and_media_without_shifting_scene_spans(self):
        query = ('find photos of Mira in September 2032 wearing a red coat '
                 'holding a striped scarf "secret phrase"')
        view = scene_view(query, TODAY, ['Mira'])
        self.assert_same_offsets(query, view)
        self.assertEqual('wearing a red coat', view[query.index('wearing'):query.index('holding')].strip())
        self.assertEqual('holding a striped scarf',
                         view[query.index('holding'):query.index('"secret')].strip())
        self.assertNotIn('Mira', view)
        self.assertNotIn('September', view)
        self.assertNotIn('photos', view)
        self.assertNotIn('secret phrase', view)

    def test_masks_only_a_recognized_leading_command_and_keeps_scene_offsets(self):
        for command in ('Find', 'find', 'Please show me', '找', '请帮我查找一下', 'only', '只看', 'Ｆｉｎｄ', 'ﬁnd'):
            query = '  ' + command + ' photos carrying a yellow suitcase'
            with self.subTest(command=command):
                view = scene_view(query, TODAY, [])
                self.assert_same_offsets(query, view)
                self.assertEqual(''.join(' ' if char == ' ' else REDACTION_MARKER for char in command),
                                 view[2:2 + len(command)])
                start = query.index('carrying')
                self.assertEqual(query[start:], view[start:])
        for query in ('2032 photos find shells', 'photos show animals',
                      'searchlight beside a bench', 'finder carrying a bag'):
            with self.subTest(query=query):
                view = scene_view(query, TODAY, [])
                self.assert_same_offsets(query, view)
                for phrase in ('find shells', 'show animals', 'searchlight', 'finder'):
                    if phrase in query:
                        start = query.index(phrase)
                        self.assertEqual(phrase, view[start:start + len(phrase)])

    def test_masks_fullwidth_dates_and_labels_while_preserving_mixed_han_offsets(self):
        query = '找全角１２号人２０３２年９月玩雪的照片'
        view = scene_view(query, TODAY, ['全角１２号人'])
        self.assert_same_offsets(query, view)
        self.assertEqual('玩雪', view[query.index('玩雪'):query.index('的照片')])
        self.assertEqual(REDACTION_MARKER * len('全角１２号人'), view[query.index('全角'):query.index('２０３２')])
        self.assertEqual(REDACTION_MARKER * len('２０３２年９月'), view[query.index('２０３２'):query.index('玩雪')])
        self.assertEqual(REDACTION_MARKER * len('照片'), view[-2:])

    def test_normalization_expansions_mask_only_complete_original_codepoints(self):
        for source, label in (
                ('find photos of Straße wearing a red coat', 'STRASSE'),
                ('find photos of oﬃce wearing a red coat', 'office'),
                ('find photos of e\u0301 wearing a red coat', 'é'),
                ('find photos of 가 wearing a red coat', '가')):
            with self.subTest(source=source):
                view = scene_view(source, TODAY, [label])
                self.assert_same_offsets(source, view)
                start = source.index('of ') + 3
                end = source.index(' wearing')
                self.assertEqual(REDACTION_MARKER * (end - start), view[start:end])
                self.assertEqual('wearing a red coat', view[end + 1:])

    def test_refuses_a_label_match_that_splits_one_normalized_source_character(self):
        query = 'find photos of İ wearing a red coat'
        with self.assertRaisesRegex(ValueError, '^Invalid scene view$'):
            scene_view(query, TODAY, ['i'])

    def test_masks_only_supplied_resolved_labels_and_keeps_repeated_visible_surfaces(self):
        query = 'find photos of Mira and Jordan wearing red coat near red coat'
        view = scene_view(query, TODAY, ['Mira'])
        self.assert_same_offsets(query, view)
        self.assertNotIn('Mira', view)
        self.assertIn('Jordan', view)
        self.assertEqual(2, view.count('red coat'))

    def test_hard_conditions_are_boundaries_even_without_surrounding_spaces(self):
        for query, label, left, right in (
                ('find carrying Mira red suitcase photos', 'Mira', 'carrying', 'red suitcase'),
                ('找提着米拉红箱子的照片', '米拉', '提着', '红箱子'),
                ('找carrying米拉red suitcase的照片', '米拉', 'carrying', 'red suitcase')):
            with self.subTest(query=query):
                view = scene_view(query, TODAY, [label])
                self.assert_same_offsets(query, view)
                start = query.index(label)
                self.assertEqual(REDACTION_MARKER * len(label), view[start:start + len(label)])
                self.assertIn(left, view)
                self.assertIn(right, view)
                self.assertNotIn(label, view)

    def test_original_spaces_and_literal_quote_boundary_remain_distinct(self):
        query = 'find photos carrying  a red bag "private words" beside a bench'
        view = scene_view(query, TODAY, [])
        self.assert_same_offsets(query, view)
        self.assertIn('carrying  a red bag', view)
        start = query.index('"')
        end = query.index('"', start + 1) + 1
        self.assertEqual(REDACTION_MARKER * (end - start), view[start:end])
        self.assertEqual(query[end:], view[end:])

    def test_masks_only_content_introducers_directly_before_paired_literals(self):
        cases = (
            ('Find photos containing: "paper moon" with Mira holding a red kite',
             'holding a red kite'),
            ('找Mira在公园里包含：“红色的球”玩耍的照片', '在公园里'),
            ('show Mira carrying a red bag about "private phrase" beside a bench',
             'carrying a red bag'),
            ('photos with the words "snow day" of Mira making a snowman',
             'making a snowman'),
        )
        for query, visible_scene in cases:
            with self.subTest(query=query):
                view = scene_view(query, TODAY, ['Mira'])
                self.assert_same_offsets(query, view)
                cue = next((cue for cue in ('containing', '包含', 'about', 'with the words')
                            if cue in query), None)
                self.assertIsNotNone(cue)
                start = query.index(cue)
                expected_cue = ''.join(' ' if char.isspace() else REDACTION_MARKER for char in cue)
                self.assertEqual(expected_cue, view[start:start + len(cue)])
                self.assertIn(visible_scene, view)
                self.assertNotIn('paper moon', view)
                self.assertNotIn('红色的球', view)
                self.assertNotIn('private phrase', view)
                self.assertNotIn('snow day', view)

    def test_leaves_nonadjacent_unquoted_and_quoted_cue_words_alone(self):
        queries = (
            'find photos about children building a fort "red coat"',
            'find photos containing a red coat wearing a blue hat',
            'find photos "about" Mira wearing a red coat',
            'find photos about children, "red coat"',
        )
        for query in queries:
            with self.subTest(query=query):
                view = scene_view(query, TODAY, [])
                self.assert_same_offsets(query, view)
                if '"about"' in query:
                    start = query.index('about')
                    self.assertEqual(REDACTION_MARKER * len('"about"'),
                                     view[start - 1:start + len('about') + 1])
                elif 'containing a red coat' in query:
                    self.assertIn('containing a red coat', view)
                else:
                    start = query.index('about')
                    self.assertEqual('about', view[start:start + len('about')])

    def test_intro_mask_uses_source_offsets_after_unicode_folding(self):
        for query, cue in (
                ('ﬁnd photos ＣＯＮＴＡＩＮＩＮＧ： “snow day” beside a bench', 'ＣＯＮＴＡＩＮＩＮＧ'),
                ('找e\u0301朋友关于：“春游”在公园里', '关于')):
            with self.subTest(query=query):
                view = scene_view(query, TODAY, [])
                self.assert_same_offsets(query, view)
                start = query.index(cue)
                self.assertEqual(REDACTION_MARKER * len(cue), view[start:start + len(cue)])
                literal = 'snow day' if 'snow day' in query else '春游'
                self.assertNotIn(literal, view)

    def test_content_intro_without_a_paired_quote_is_not_masked(self):
        for query in ('find photos containing a red coat',
                      'find photos containing "an unfinished literal'):
            with self.subTest(query=query):
                view = scene_view(query, TODAY, [])
                self.assert_same_offsets(query, view)
                self.assertIn('containing', view)
                self.assertIn('red coat' if 'red coat' in query else 'unfinished literal', view)

    def test_invalid_or_conflicting_dates_fail_closed(self):
        for query in ('find photos in 2032年13月 wearing red coat',
                      'find photos in September 2032 and February 2032 wearing red coat'):
            with self.subTest(query=query):
                with self.assertRaisesRegex(ValueError, '^Invalid scene view$'):
                    scene_view(query, TODAY, [])

    def test_rejects_invalid_inputs_with_one_fixed_error(self):
        for args in ((None, TODAY, []), (' ', TODAY, []), ('find photos', TODAY, 'Mira'),
                     ('find photos\x00 red coat', TODAY, []),
                     ('x' * 1025, TODAY, [])):
            with self.subTest(args=args[:1]):
                with self.assertRaisesRegex(ValueError, '^Invalid scene view$'):
                    scene_view(*args)


if __name__ == '__main__':
    unittest.main()

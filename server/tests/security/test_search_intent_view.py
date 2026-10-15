"""Offset-preserving tests for the private descriptive-provider query view."""
from datetime import date
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.search_intent_view import scene_view


TODAY = date(2032, 9, 14)


class SearchIntentViewTests(unittest.TestCase):
    def assert_same_offsets(self, source, view):
        self.assertEqual(len(source), len(view))
        for original, visible in zip(source, view):
            self.assertTrue(original == visible or visible == ' ')

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

    def test_masks_fullwidth_dates_and_labels_while_preserving_mixed_han_offsets(self):
        query = '找全角１２号人２０３２年９月玩雪的照片'
        view = scene_view(query, TODAY, ['全角１２号人'])
        self.assert_same_offsets(query, view)
        self.assertEqual('玩雪', view[query.index('玩雪'):query.index('的照片')])
        self.assertEqual(' ' * len('全角１２号人'), view[query.index('全角'):query.index('２０３２')])
        self.assertEqual(' ' * len('２０３２年９月'), view[query.index('２０３２'):query.index('玩雪')])
        self.assertEqual(' ' * len('照片'), view[-2:])

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
                self.assertEqual(' ' * (end - start), view[start:end])
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

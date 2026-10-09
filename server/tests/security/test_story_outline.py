import unittest

from app.access.story_outline import build_outline


def item(asset_id, *, kind='image', evidence=(), taken_at=None, date_hint=None):
    return {
        'id': asset_id,
        'kind': kind,
        'taken_at': taken_at,
        'date_hint': date_hint,
        'evidence': list(evidence),
    }


class StoryOutlineTests(unittest.TestCase):
    def test_preserves_order_and_video_ids_without_copying_evidence_text(self):
        items = [
            item('asset-2', kind='video', evidence=[{'id': 'ev-2', 'source': 'ai', 'text': 'AI says birthday cake'}]),
            item('asset-1', evidence=[{'id': 'ev-1', 'source': 'family', 'text': 'We visited Paris on June 3'}]),
        ]
        result = build_outline(items, theme='birthday', language='zh')
        self.assertEqual(result['chapters'][0]['asset_ids'], ['asset-2', 'asset-1'])
        self.assertEqual(result['chapters'][0]['evidence_ids'], ['ev-2', 'ev-1'])
        self.assertNotIn('birthday cake', str(result['chapters']))
        self.assertNotIn('Paris', str(result['chapters']))
        self.assertNotIn('June 3', str(result['chapters']))
        self.assertIn('生日主题', result['chapters'][0]['title'])
        self.assertTrue(result['needs_review'])

    def test_groups_at_most_four_items_into_at_most_six_chapters(self):
        result = build_outline([item(f'a{i}') for i in range(24)], theme='everyday', language='en')
        self.assertEqual(len(result['chapters']), 6)
        self.assertTrue(all(1 <= len(chapter['asset_ids']) <= 4 for chapter in result['chapters']))
        self.assertEqual([asset for chapter in result['chapters'] for asset in chapter['asset_ids']], [f'a{i}' for i in range(24)])
        self.assertEqual([c['id'] for c in result['chapters']], [f'chapter-{i}' for i in range(1, 7)])

    def test_theme_labels_and_role_headings_are_localized(self):
        items = [item(f'a{i}') for i in range(9)]
        zh = build_outline(items, theme='trip', language='zh')
        en = build_outline(items, theme='trip', language='en')
        self.assertIn('旅途主题', zh['chapters'][0]['title'])
        self.assertIn('回看开始', zh['chapters'][0]['title'])
        self.assertIn('继续回看', zh['chapters'][1]['title'])
        self.assertIn('留下结尾', zh['chapters'][-1]['title'])
        self.assertIn('Travel theme', en['chapters'][0]['title'])
        self.assertIn('A place to begin', en['chapters'][0]['title'])
        self.assertIn('Continue the story', en['chapters'][1]['title'])
        self.assertIn('A place to close', en['chapters'][-1]['title'])

    def test_uncertain_dates_are_not_rendered_as_facts_and_questions_invite_context(self):
        result = build_outline([item('a1', taken_at=None, date_hint={'date': '2020-01-01', 'confidence': 0.2})],
                               theme='year_in_review', language='en')
        self.assertNotIn('2020-01-01', str(result))
        self.assertNotIn('2020', str(result))
        self.assertTrue(any('date' in question.lower() for question in result['questions']))
        self.assertLessEqual(len(result['questions']), 3)

    def test_rejects_malformed_or_unexpected_reference_shapes(self):
        valid = item('asset-1')
        bad_items = [
            [dict(valid, filename='secret.jpg')],
            [item('../outside')],
            [item('asset-1'), item('asset-1')],
            [dict(valid, kind='audio')],
            [dict(valid, evidence=[{'id': 'x', 'source': 'family', 'text': 'ok', 'url': 'https://example.test'}])],
            [item('asset-1', evidence=[{'id': '../secret', 'source': 'family', 'text': 'ok'}])],
            [item('asset-1', evidence=[{'id': 'x', 'source': 'model', 'text': 'ok'}])],
            [item('asset-1', evidence=[{'id': 'x', 'source': 'ai', 'text': '\ud800'}])],
            [item('asset-1', date_hint={'when': {'nested': {'too': {'deep': {'again': 'x'}}}}})],
        ]
        for candidate in bad_items:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    build_outline(candidate, theme='everyday', language='zh')

    def test_rejects_unsupported_theme_language_and_item_limit(self):
        with self.assertRaises(ValueError):
            build_outline([], theme='unknown', language='en')
        with self.assertRaises(ValueError):
            build_outline([], theme='everyday', language='fr')
        with self.assertRaises(ValueError):
            build_outline([item(str(i)) for i in range(25)], theme='everyday', language='en')


if __name__ == '__main__':
    unittest.main()

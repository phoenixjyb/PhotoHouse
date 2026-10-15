"""Closed, read-only queries and bounded evidence for a current result."""
import copy
import unittest
from unittest.mock import patch

from app.access import result_explanation as explanation


class WhyResultQueryTests(unittest.TestCase):
    def test_english_exact_ordinals_and_current_item_phrases(self):
        expected = {
            'why the first result': {'ordinal': 1, 'kind': None},
            'Why second result?': {'ordinal': 2, 'kind': None},
            'please why 10 result!': {'ordinal': 10, 'kind': None},
            'why this result': {'ordinal': None, 'kind': None},
            'why this photo': {'ordinal': None, 'kind': 'image'},
            'why this video？': {'ordinal': None, 'kind': 'video'},
        }
        for words, selection in expected.items():
            with self.subTest(words=words):
                self.assertEqual(explanation.parse_why_result_query(words), selection)

    def test_chinese_exact_ordinals_and_typed_single_item_phrases(self):
        expected = {
            '为什么第一项': {'ordinal': 1, 'kind': None},
            '为什么是第2项结果？': {'ordinal': 2, 'kind': None},
            '请为什么第十个结果。': {'ordinal': 10, 'kind': None},
            '为什么这张照片': {'ordinal': None, 'kind': 'image'},
            '为什么是这个视频？': {'ordinal': None, 'kind': 'video'},
            '为什么这个结果': {'ordinal': None, 'kind': None},
        }
        for words, selection in expected.items():
            with self.subTest(words=words):
                self.assertEqual(explanation.parse_why_result_query(words), selection)

    def test_nfkc_and_casefold_are_safe_but_quotes_actions_and_extra_words_are_closed(self):
        self.assertEqual(explanation.parse_why_result_query('ＰＬＥＡＳＥ WHY THE ３ RESULT？'),
                         {'ordinal': 3, 'kind': None})
        for words in (
                'why the first result and open it',
                'why the first result then delete it',
                'open the first result',
                'why red coat',
                '"why this photo"',
                'why the first result, please open',
                '为什么第一项然后打开',
                '为什么第一项 红外套',
                '“为什么这张照片”',
                'why the 11 result',
                'why this image',
                'why this photo please'):
            with self.subTest(words=words):
                self.assertIsNone(explanation.parse_why_result_query(words))

    def test_nontext_controls_lone_surrogates_and_oversized_queries_fail_closed(self):
        for words in (None, 7, 'why\nthis photo', 'why this photo\ud800',
                      'why this result' + (' ' * 600)):
            with self.subTest(words=repr(words)):
                self.assertIsNone(explanation.parse_why_result_query(words))


class ResultExplanationTests(unittest.TestCase):
    def _render_with_summary(self, item, filters, interpretation, language, summary):
        with patch.object(explanation, 'explain_filters',
                          return_value=summary) as shared_formatter:
            reply = explanation.explain_result(item, 2, filters, interpretation, language)
        normalized_filters = filters if type(filters) is dict else {}
        normalized_interpretation = interpretation if type(interpretation) is dict else {}
        shared_formatter.assert_called_once_with(normalized_filters, normalized_interpretation,
                                                 language, max_bytes=300)
        return reply

    def test_only_supported_current_reason_classes_are_rendered_and_private_values_are_redacted(self):
        item = {
            'id': 'PRIVATE_ASSET_ID',
            'kind': 'image',
            'taken_at': '2032-09-14T10:00:00Z',
            'caption': 'PRIVATE_RAW_CAPTION',
            'path': '/private/original.jpg',
            'match_reasons': [
                {'source': 'reviewed_person', 'source_id': 'p1'},
                {'source': 'capture_date', 'value': '2032-09-14'},
                {'source': 'photo_memory', 'source_id': 'note-secret', 'revision': 42,
                 'content': 'PRIVATE_MEMORY_TEXT'},
                {'source': 'edited_caption', 'source_id': 'caption-secret',
                 'revision': 'PRIVATE_REVISION', 'content': 'PRIVATE_EDITED_TEXT'},
                {'source': 'generated_caption', 'source_id': 'caption-secret-2',
                 'content': 'PRIVATE_GENERATED_TEXT'},
                {'source': 'unknown_private_provider', 'content': 'PRIVATE_EXTRA'},
            ],
        }
        filters = {
            'media': ['image'],
            'people': {'ids': ['p1'], 'match': 'any'},
            'date': {'from': '2032-09-01', 'to': '2032-09-30'},
            'descriptive': {'version': 1, 'concepts': [
                {'surface': 'red coat', 'alternatives': ['red coat', '红外套']},
            ]},
        }
        interpretation = {'people': [{'id': 'p1', 'label': 'Reviewed Person'}]}
        original = copy.deepcopy((item, filters, interpretation))
        reply = self._render_with_summary(
            item, filters, interpretation, 'en', 'Active filters: Reviewed Person; red coat')
        self.assertIn('Match explanation for result 2', reply)
        self.assertIn('photo', reply)
        self.assertIn('reviewed-person filter match', reply)
        self.assertIn('capture-date filter match', reply)
        self.assertIn('saved photo memory', reply)
        self.assertIn('edited caption', reply)
        self.assertIn('generated caption', reply)
        for private in ('PRIVATE_ASSET_ID', 'PRIVATE_RAW_CAPTION', '/private/',
                        'note-secret', 'caption-secret', 'PRIVATE_REVISION',
                        'PRIVATE_MEMORY_TEXT', 'PRIVATE_EDITED_TEXT',
                        'PRIVATE_GENERATED_TEXT', 'PRIVATE_EXTRA', '红外套'):
            self.assertNotIn(private, reply)
        self.assertEqual((item, filters, interpretation), original)

    def test_reason_classes_require_matching_active_person_and_date_filters(self):
        item = {'kind': 'video', 'match_reasons': [
            {'source': 'reviewed_person', 'source_id': 'other'},
            {'source': 'capture_date', 'value': '2032-10-01'},
            {'source': 'photo_memory'},
        ]}
        filters = {'people': {'ids': ['p1'], 'match': 'all'},
                   'descriptive': {'version': 1, 'concepts': [
                       {'surface': 'winter', 'alternatives': ['winter']}]},
                   'date': {'from': '2032-09-01', 'to': '2032-09-30'}}
        reply = self._render_with_summary(item, filters, {}, 'zh', '筛选条件：人物，日期')
        self.assertIn('视频', reply)
        self.assertNotIn('已审核匹配记录', reply)
        self.assertNotIn('拍摄日期筛选有匹配记录', reply)
        self.assertIn('照片回忆', reply)

    def test_missing_or_unknown_reasons_use_a_restrained_fallback(self):
        for item in ({'kind': 'other'},
                     {'kind': 'image', 'match_reasons': [
                         {'source': 'unknown', 'source_id': 'secret', 'content': 'secret'}]}):
            reply = self._render_with_summary(
                item, {'text': 'family'}, {}, 'en', 'Active filters: text phrase')
            self.assertIn('No text-source detail is available', reply)
            self.assertNotIn('secret', reply)
            self.assertNotIn('depicts', reply)
        generic = self._render_with_summary(
            {'kind': 'image'}, {}, {}, 'en', 'No search filters are active.')
        self.assertIn('matched the current search filters', generic)
        self.assertNotIn('visual', generic.casefold())

    def test_malformed_and_large_utf8_inputs_stay_valid_and_within_reply_bound(self):
        item = {'kind': object(), 'match_reasons': [
            {'source': 'capture_date', 'value': '2032-02-31'},
            {'source': 'reviewed_person', 'source_id': 'p1'},
        ]}
        filters = {'date': {'from': 'bad', 'to': '\ud800'},
                   'people': {'ids': ['p1'], 'match': 'any'}}
        huge_summary = '\ud800' + '家庭' * 500
        reply = self._render_with_summary(item, filters, {}, 'zh', huge_summary)
        self.assertLessEqual(len(reply.encode('utf-8')), 600)
        self.assertNotIn('\ud800', reply)
        self.assertIn('…', reply)
        fallback = self._render_with_summary(None, None, None, 'en', 'x' * 900)
        self.assertLessEqual(len(fallback.encode('utf-8')), 600)


if __name__ == '__main__':
    unittest.main()

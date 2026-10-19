"""Bilingual private people-search journeys on fictional reviewed identities."""
import unittest

import test_reviewed_family_search_journeys as family_journey


PEOPLE_ALL = {'ids': ['301', '302', '303'], 'match': 'all'}


class AssistantBilingualReviewJourneys(unittest.TestCase):
    def setUp(self):
        self.journey = family_journey.ReviewedFamilySearchJourneys('runTest')
        self.addCleanup(self.journey.doCleanups)
        self.journey.setUp()
        self.fixture = self.journey.fixture

    def search(self, words, context=None):
        response = self.fixture.turn(words, context=context)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def assert_same_joint_selection(self, result):
        self.assertEqual(result['filters']['people'], PEOPLE_ALL)

    def test_english_chinese_and_mixed_turns_keep_joint_people_date_and_media_filters(self):
        journeys = (
            ('find Sample Child, mom, and dad together photos from 2025',
             'only videos of them'),
            ('找示例儿童、妈妈和爸爸一起的照片，2025年', '只看视频'),
            ('find示例儿童和妈妈和爸爸一起的photos from 2025', 'only videos'),
        )
        for opening, followup in journeys:
            with self.subTest(opening=opening, followup=followup):
                initial = self.search(opening)
                self.assertEqual(initial['kind'], 'results', initial)
                self.assertEqual(initial['filters']['date'],
                                 {'from': '2025-01-01', 'to': '2025-12-31'})
                self.assert_same_joint_selection(initial)
                refined = self.search(followup, initial['context'])
                self.assertEqual(refined['kind'], 'results', refined)
                self.assertEqual(refined['filters'], {
                    'media': ['video'],
                    'date': {'from': '2025-01-01', 'to': '2025-12-31'},
                    'people': PEOPLE_ALL,
                })
                self.assertEqual(refined['items'], [])
                same_item_notice = ('同一项' if followup == '只看视频'
                                    else 'same item')
                evidence_notice = ('已确认的标注' if followup == '只看视频'
                                   else 'confirmed assignments only')
                self.assertIn(same_item_notice, refined['reply'])
                self.assertIn(evidence_notice, refined['reply'])
                self.assertIsNone(refined['effect'])

    def test_pronoun_continuation_preserves_all_selected_people_across_languages(self):
        openings = (
            ('find Sample Child, Mom, and Dad together photos', 'find videos of them'),
            ('找示例儿童、妈妈和爸爸一起的照片', '他们的视频'),
            ('find示例儿童and妈妈and爸爸的photos', '只看他们的视频'),
        )
        for opening, followup in openings:
            with self.subTest(opening=opening, followup=followup):
                initial = self.search(opening)
                self.assert_same_joint_selection(initial)
                refined = self.search(followup, initial['context'])
                self.assertEqual(refined['kind'], 'results', refined)
                self.assert_same_joint_selection(refined)
                self.assertEqual(refined['filters']['media'], ['video'])

    def test_people_scope_explanation_does_not_claim_unreviewed_media_was_checked(self):
        cases = (
            ('find Sample Child, mom, and dad together photos',
             'People search uses confirmed assignments only',
             'All selected people must be confirmed in the same item'),
            ('找示例儿童、妈妈和爸爸一起的照片', '人物检索只使用已确认的标注',
             '所选人物须在同一项中均有确认标注'),
            ('find示例儿童和妈妈和爸爸一起的photos',
             '人物检索只使用已确认的标注',
             '所选人物须在同一项中均有确认标注'),
        )
        for words, evidence_notice, same_item_notice in cases:
            with self.subTest(words=words):
                result = self.search(words)
                self.assertEqual(result['kind'], 'results', result)
                self.assert_same_joint_selection(result)
                self.assertIn(evidence_notice, result['reply'])
                self.assertIn(same_item_notice, result['reply'])
                self.assertIsNone(result['effect'])

    def test_ambiguous_relative_date_followup_requests_clarification(self):
        phrases = ('再早一点', 'a bit earlier', 'earlier please',
                   'a bit earlier please', 'earlier一点')
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                initial = self.search(
                    'find Sample Child, mom, and dad together photos from 2025 '
                    'containing "Example Park"')
                self.assertEqual(initial['filters']['text'], 'Example Park')
                self.assert_same_joint_selection(initial)
                ambiguous = self.search(phrase, initial['context'])
                self.assertEqual(ambiguous['kind'], 'clarification', ambiguous)
                self.assertEqual(ambiguous['items'], initial['items'])
                self.assertEqual(ambiguous['filters'], initial['filters'])
                self.assertEqual(ambiguous['context'], initial['context'])
                self.assertIsNone(ambiguous['effect'])
                if phrase == '再早一点' or phrase == 'earlier一点':
                    self.assertIn('请提供明确的年份、月份或日期', ambiguous['reply'])
                else:
                    self.assertIn('Give a year, month, or date', ambiguous['reply'])

                resolved = self.search('2024年', ambiguous['context'])
                self.assertEqual(resolved['kind'], 'results', resolved)
                self.assertEqual(resolved['filters'], {
                    'media': ['image'],
                    'date': {'from': '2024-01-01', 'to': '2024-12-31'},
                    'people': PEOPLE_ALL,
                    'text': 'Example Park',
                })

    def test_revoked_membership_blocks_a_followup_to_a_private_joint_search(self):
        initial = self.search('find Sample Child, Mom, and Dad together photos')
        self.fixture.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        response = self.fixture.turn('find videos of them', context=initial['context'])
        self.assertIn(response.status_code, (401, 403), response.text)
        self.assertNotIn('Sample Child', response.text)
        self.assertNotIn('示例儿童', response.text)

    def test_withdrawn_reviewed_source_invalidates_old_and_new_joint_searches(self):
        initial = self.search('找示例儿童、妈妈和爸爸一起的照片，2025年')
        self.fixture.mutate("UPDATE face_detections SET label_source='dnn' WHERE id=6")
        for words, context in (
            ('介绍这些结果', initial['context']),
            ('find Sample Child, Mom, and Dad together photos from 2025', None),
        ):
            with self.subTest(words=words, has_context=context is not None):
                response = self.fixture.turn(words, context=context)
                self.assertEqual(response.status_code, 409, response.text)
                self.assertNotIn('Sample Father', response.text)
                self.assertNotIn('示例父亲', response.text)


if __name__ == '__main__':
    unittest.main()

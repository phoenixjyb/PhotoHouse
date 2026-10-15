"""Security tests for deterministic continuation of one vague-date slot."""
from datetime import date, datetime
import unittest

from app.access.search_pending import (PENDING_TTL_SECONDS, current_pending,
                                       find_date_slot, make_pending,
                                       resolve_date_answer, validate_pending)


TODAY = date(2032, 9, 14)
TODAY_DATETIME = datetime(2032, 9, 14, 12, 0)
BINDING = "a" * 64


def pending_for(query, *, labels=None, created_at=500):
    entities = {'labels': [] if labels is None else labels, 'enabled': ['date']}
    slot = find_date_slot(query, entities, TODAY_DATETIME)
    if slot is None:
        raise AssertionError('expected one eligible vague-time slot')
    return make_pending(query, slot, BINDING, created_at)


class SearchPendingDateTests(unittest.TestCase):
    def test_closed_english_chinese_and_mixed_phrases_return_original_offsets(self):
        examples = (
            ("Find photos from childhood", "from childhood"),
            ("Find photos about childhood", "childhood"),
            ("Find photos from when younger", "when younger"),
            ("Find photos from a long time ago", "a long time ago"),
            ("Find photos from long ago", "long ago"),
            ("Find photos long ago", "long ago"),
            ("找小时候的照片", "小时候"),
            ("找儿时的照片", "儿时"),
            ("找小的时候的照片", "小的时候"),
            ("找很久以前的照片", "很久以前"),
            ("找好久以前的照片", "好久以前"),
            ("Find photos of 示例儿童小时候", "小时候"),
        )
        for query, phrase in examples:
            with self.subTest(query=query):
                start = query.index(phrase)
                self.assertEqual((start, start + len(phrase)),
                                 find_date_slot(query, {'labels': [], 'enabled': ['date']},
                                                TODAY_DATETIME))
                value = pending_for(query)
                self.assertEqual(query[start:start + len(phrase)],
                                 value["query"][value["start"]:value["end"]])

    def test_explicit_approximate_age_phrases_are_closed_and_preserve_offsets(self):
        examples = (
            ("Find photos maybe two summers ago", "maybe two summers ago"),
            ("Find photos about two years ago", "about two years ago"),
            ("Find photos around a few winters ago", "around a few winters ago"),
            ("Find photos maybe 2 years ago", "maybe 2 years ago"),
            ("Find photos about three years ago", "about three years ago"),
            ("找大概两年前的照片", "大概两年前"),
            ("找可能是2年前的照片", "可能是2年前"),
            ("找大概是两年前的照片", "大概是两年前"),
            ("找可能两年前的照片", "可能两年前"),
            ("找可能在3年前的照片", "可能在3年前"),
            ("找前几年的照片", "前几年"),
            ("找前些年的照片", "前些年"),
            ("找前两年的照片", "前两年"),
            ("find示例儿童可能是两年前playing in snow的photos", "可能是两年前"),
        )
        for query, phrase in examples:
            with self.subTest(query=query):
                start = query.index(phrase)
                self.assertEqual((start, start + len(phrase)),
                    find_date_slot(query, {'labels': [], 'enabled': ['date']}, TODAY_DATETIME))
                pending = pending_for(query)
                self.assertEqual(phrase, pending['query'][pending['start']:pending['end']])

    def test_approximate_age_requires_supported_prefix_and_exact_closed_wording(self):
        queries = (
            "Find photos two years ago", "Find photos two summers ago",
            "Find photos maybe four years ago", "Find photos around two decades ago",
            "Find photos maybe two years", "Find photos maybe two years agoish",
            "找两年前的照片", "找大概四年前的照片", "找可能几年以前的照片",
            "找前四年的照片", "找大概两年后的照片",
        )
        for query in queries:
            with self.subTest(query=query):
                self.assertIsNone(find_date_slot(
                    query, {'labels': [], 'enabled': ['date']}, TODAY_DATETIME))

        for query, labels in (
                ('Find photos of "maybe two summers ago"', []),
                ('Find photos about two years ago in 2020', []),
                ('Find photos maybe two years ago', ['maybe two years ago']),
                ('找“大概两年前”的照片', []),
                ('找大概两年前和前几年的照片', [])):
            with self.subTest(query=query):
                self.assertIsNone(find_date_slot(
                    query, {'labels': labels, 'enabled': ['date']}, TODAY_DATETIME))

    def test_quotes_dates_reviewed_labels_and_competing_phrases_refuse_slot(self):
        queries = (
            'Find photos of "childhood"',
            "Find photos from childhood in 2020",
            "Find photos from childhood yesterday",
            "Find childhood photos from a long time ago",
            "找小时候和很久以前的照片",
            'Find photos of “from childhood”',
            'Find photos of “school childhood”',
        )
        for query in queries:
            with self.subTest(query=query):
                self.assertIsNone(find_date_slot(query, {'labels': [], 'enabled': ['date']},
                                                 TODAY_DATETIME))
        query = "Find photos about childhood"
        self.assertIsNone(find_date_slot(query, {'labels': ['childhood'], 'enabled': ['date']},
                                         TODAY_DATETIME))

    def test_closed_set_does_not_guess_nearby_language_or_invalid_unicode(self):
        for query in ("Find photos when she was little", "找从小的照片",
                      "Find photos from childhooß", "Find photos about growing up",
                      "Find photos about ｃｈｉｌｄｈｏｏｄ"):
            with self.subTest(query=query):
                self.assertIsNone(find_date_slot(query, {'labels': [], 'enabled': ['date']},
                                                 TODAY_DATETIME))
        self.assertIsNone(find_date_slot("Find photos from childhood\ud800",
                                         {'labels': [], 'enabled': ['date']}, TODAY_DATETIME))

    def test_private_object_is_strict_and_storage_validation_can_ignore_expiry(self):
        query = "Find photos from childhood"
        value = pending_for(query)
        self.assertEqual(value['version'], 3)
        self.assertEqual(value, validate_pending(value))
        self.assertEqual(value, current_pending(value, 500 + PENDING_TTL_SECONDS))

        malformed = (
            {**value, "version": True},
            {**value, "version": 4},
            {**value, "question": "person"},
            {**value, "start": True},
            {**value, "end": len(query) + 1},
            {**value, "created_at": True},
            {**value, "binding": "A" * 64},
            {**value, "extra": "not allowed"},
            {**value, "query": "Find photos from childhood\x00"},
            {**value, "query": "Find photos from childhood\ud800"},
            {**value, "query": "Find photos from childhood " + "x" * 1024},
            {**value, "start": value["start"] + 1},
        )
        for candidate in malformed:
            with self.subTest(candidate=candidate):
                with self.assertRaisesRegex(ValueError, "Invalid pending date"):
                    validate_pending(candidate)

        # An expired object remains structurally readable in stored history.
        self.assertEqual(value, validate_pending(value))
        for now in (499, 500 + PENDING_TTL_SECONDS + 1, True, 500.0):
            with self.subTest(now=now):
                self.assertIsNone(current_pending(value, now))

    def test_version_one_keeps_its_frozen_phrase_policy_while_current_matching_stays_ambiguous(self):
        query = "Find photos from childhood about two years ago"
        start = query.index('from childhood')
        legacy = {
            'version': 1, 'question': 'date', 'query': query,
            'start': start, 'end': start + len('from childhood'),
            'binding': BINDING, 'created_at': 500,
        }
        self.assertEqual(legacy, validate_pending(legacy))
        self.assertEqual(legacy, current_pending(legacy, 500))
        self.assertIsNone(find_date_slot(
            query, {'labels': [], 'enabled': ['date']}, TODAY_DATETIME))

    def test_version_two_keeps_its_frozen_policy_when_new_long_ago_phrase_is_ambiguous(self):
        query = 'Find photos from childhood and long ago'
        start = query.index('from childhood')
        legacy = {
            'version': 2, 'question': 'date', 'query': query,
            'start': start, 'end': start + len('from childhood'),
            'binding': BINDING, 'created_at': 500,
        }
        self.assertEqual(legacy, validate_pending(legacy))
        self.assertEqual(legacy, current_pending(legacy, 500))
        self.assertIsNone(find_date_slot(
            query, {'labels': [], 'enabled': ['date']}, TODAY_DATETIME))

    def test_long_ago_is_not_a_slot_when_label_quote_explicit_date_or_other_age_competes(self):
        for query, labels in (
                ('Find photos from long ago', ['long ago']),
                ('Find photos from "long ago"', []),
                ('Find photos from long ago in 2020', []),
                ('Find photos from childhood and long ago', []),
                ('Find photos from a long time ago and long ago', [])):
            with self.subTest(query=query):
                self.assertIsNone(find_date_slot(
                    query, {'labels': labels, 'enabled': ['date']}, TODAY_DATETIME))

    def test_date_answer_becomes_separate_hard_filter_and_masks_only_slot(self):
        original = "Find Sample Child from childhood"
        pending = pending_for(original)
        date_entities = {
            'enabled': ['date'], 'ambiguous': False,
            'groups': {'people': [], 'tags': [], 'locations': []}, 'labels': [],
        }
        masked, date_filter = resolve_date_answer(pending, "in 2020", TODAY_DATETIME,
                                                 date_entities)
        self.assertEqual({"from": "2020-01-01", "to": "2020-12-31"}, date_filter)
        self.assertEqual(len(original), len(masked))
        self.assertEqual(original[:pending["start"]], masked[:pending["start"]])
        self.assertEqual(" " * (pending["end"] - pending["start"]),
                         masked[pending["start"]:pending["end"]])
        self.assertEqual(original[pending["end"]:], masked[pending["end"]:])
        self.assertNotIn("2020", masked)
        self.assertEqual(original, pending["query"])
        self.assertIsNone(resolve_date_answer(pending, "2020", TODAY_DATETIME,
                                             {**date_entities, 'enabled': []}))

        chinese = pending_for("找小时候的照片")
        self.assertEqual({"from": "2024-03-01", "to": "2024-03-31"},
                         resolve_date_answer(chinese, "2024年3月", TODAY_DATETIME,
                                             date_entities)[1])

    def test_answer_must_resolve_to_only_one_literal_date_filter(self):
        pending = pending_for("Find photos from childhood")
        for answer in (
                "", "photos", "2020 photos", "2020 beach", "Sample Child 2020",
                "2019 and 2020", "not 2020", '"2020"', "delete 2020",
                "2020-99-99", "小时候"):
            with self.subTest(answer=answer):
                self.assertIsNone(resolve_date_answer(pending, answer, TODAY_DATETIME,
                                                     {'enabled': ['date'], 'ambiguous': False,
                                                      'groups': {'people': [], 'tags': [], 'locations': []},
                                                      'labels': []}))

    def test_resume_uses_fresh_resolver_entities_and_fails_closed(self):
        pending = pending_for("Find photos from childhood")
        answer = "2018"
        for entities in (None, [], "invalid", {'enabled': ['date'], 'ambiguous': True}):
            with self.subTest(entities=entities):
                self.assertIsNone(resolve_date_answer(
                    pending, answer, TODAY_DATETIME, entities))

        # A reviewed label that is also a valid year must retain the literal
        # planner's ambiguity policy, whether the resolver chose a person or tag.
        collisions = (
            {'enabled': ['date', 'people'], 'ambiguous': False,
             'groups': {'people': ['301'], 'tags': [], 'locations': []},
             'labels': ['2018']},
            {'enabled': ['date', 'tags'], 'ambiguous': False,
             'groups': {'people': [], 'tags': ['44'], 'locations': []},
             'labels': ['2018']},
        )
        for entities in collisions:
            with self.subTest(groups=entities['groups']):
                self.assertIsNone(resolve_date_answer(
                    pending, answer, TODAY_DATETIME, entities))

        # Even when both tokens are authorized, a date-plus-person answer is
        # not a date-only clarification and must not alter the pending query.
        person_and_date = {
            'enabled': ['date', 'people'], 'ambiguous': False,
            'groups': {'people': ['301'], 'tags': [], 'locations': []},
            'labels': ['Sample Adult'],
        }
        self.assertIsNone(resolve_date_answer(
            pending, '2020 Sample Adult', TODAY_DATETIME, person_and_date))

    def test_resume_rejects_expired_or_future_pending_without_mutating_it(self):
        pending = pending_for("找很久以前的照片", created_at=100)
        original = dict(pending)
        for now in (99, 100 + PENDING_TTL_SECONDS + 1):
            with self.subTest(now=now):
                self.assertIsNone(current_pending(pending, now))
        self.assertEqual(original, pending)


if __name__ == "__main__":
    unittest.main()

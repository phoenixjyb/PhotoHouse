"""Focused contract tests for pure descriptive concept matching."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.access.search_description import (  # noqa: E402
    MAX_ALTERNATIVES,
    MAX_CONCEPTS,
    MAX_DESCRIPTION_BYTES,
    MAX_MATCH_REASONS,
    MAX_PHRASE_BYTES,
    match_description,
    normalize_description,
)
from app.access.search_text import NormalizedSource, normalize_sources  # noqa: E402


class SearchDescriptionTests(unittest.TestCase):
    def description(self, *concepts):
        return {"version": 1, "concepts": [
            {"surface": surface, "alternatives": list(alternatives)}
            for surface, alternatives in concepts
        ]}

    def source(self, source, source_id, content, revision=1):
        return normalize_sources([{"source": source, "source_id": source_id,
                                   "revision": revision, "content": content}], lambda: None)[0]

    def test_bilingual_alternatives_match_with_unicode_compatibility_and_casefold(self):
        plan = self.description(("在海边", ("by the sea", "sea shore")))
        sources = (self.source("generated_caption", "1", "BY THE SEA at sunset"),)

        matched, reasons, quality = match_description(sources, plan)

        self.assertTrue(matched)
        self.assertEqual(reasons, [{"source": "generated_caption", "source_id": "1", "revision": 1}])
        self.assertEqual(quality, (0, 1, -20))
        self.assertEqual(normalize_description(plan), plan)

    def test_all_concepts_are_required_and_can_be_grounded_in_different_sources(self):
        plan = self.description(
            ("玩得开心", ("having fun", "happy play")),
            ("在水边", ("by the water", "riverside")),
        )
        sources = (
            self.source("generated_caption", "cap-1", "The children were having fun."),
            self.source("photo_memory", "note-1", "A walk by the water after lunch.", revision=2),
        )

        matched, reasons, quality = match_description(sources, plan)

        self.assertTrue(matched)
        self.assertEqual(reasons, [
            {"source": "generated_caption", "source_id": "cap-1", "revision": 1},
            {"source": "photo_memory", "source_id": "note-1", "revision": 2},
        ])
        self.assertEqual(quality[:2], (1, 2))
        self.assertEqual(set(reasons[0]), {"source", "source_id", "revision"})
        self.assertNotIn("having fun", repr(reasons))
        self.assertNotIn("children", repr(reasons))

    def test_one_missing_concept_fails_closed_without_partial_evidence(self):
        plan = self.description(
            ("开心", ("having fun",)),
            ("穿红衣服", ("wearing red",)),
        )

        self.assertEqual(match_description(
            (self.source("edited_caption", "cap-1", "having fun at the park"),), plan),
            (False, [], (0, 0, 0)))

    def test_surface_is_not_implicitly_added_as_an_alternative(self):
        plan = self.description(("海边", ("by the sea",)))

        self.assertFalse(match_description((self.source("generated_caption", "1", "海边"),), plan)[0])
        self.assertTrue(match_description((self.source("generated_caption", "1", "海边"),),
                                          self.description(("海边", ("by the sea", "海边"))))[0])

    def test_quality_prefers_authored_and_phrase_bounded_evidence(self):
        plan = self.description(("玩", ("having fun",)))
        weak = self.source("generated_caption", "1", "infrared having fun outdoors")
        authored = self.source("edited_caption", "2", "Having fun!")

        self.assertGreater(match_description((authored,), plan)[2],
                           match_description((weak,), plan)[2])

    def test_negative_clauses_do_not_supply_positive_scene_evidence(self):
        cases = (
            ('dog', 'No dog was nearby.'),
            ('dog', 'A dog was not nearby.'),
            ('dog', "There isn't a dog here."),
            ('dog', "A dog can't be seen."),
            ('dog', 'The dog wasn’t there.'),
            ('dog', 'Not yet a dog in view.'),
            ('dog', 'Neither a dog nor a cat is described.'),
            ('red coat', 'Without a red coat, a scarf was worn.'),
            ('雪', '路面没有积雪。'),
            ('红外套', '她没穿红外套。'),
            ('玩雪', '今天不玩雪。'),
            ('玩雪', '今天没玩雪。'),
            ('雪', '没去雪山。'),
            ('雪', '未到雪山。'),
            ('雪', '照片里沒在下雪。'),
            ('雪', '路上沒有積雪。'),
            ('红外套', '不是穿红外套。'),
            ('敲手鼓', 'The note says not 敲手鼓.'),
        )
        for phrase, content in cases:
            with self.subTest(content=content):
                source = self.source('generated_caption', '1', content)
                self.assertEqual((False, [], (0, 0, 0)), match_description(
                    (source,), self.description((phrase, (phrase,)))))

    def test_positive_sentences_and_explicit_contrasts_remain_usable(self):
        for content in ('No dog in the first frame. A dog is running in the next.',
                        'No cat is visible; a dog is running.',
                        'No cat, but a dog is running.',
                        'There is no cat. However a dog is running.',
                        '没有猫，但是有一只dog在跑。'):
            with self.subTest(content=content):
                self.assertTrue(match_description(
                    (self.source('photo_memory', '1', content),),
                    self.description(('dog', ('dog',))))[0])
        self.assertTrue(match_description(
            (self.source('photo_memory', '1', '路上没有车；新雪铺满了小路。'),),
            self.description(('雪', ('雪',))))[0])

    def test_latin_word_edges_reject_substrings_without_requiring_chinese_spaces(self):
        for phrase, content in (('cat', 'A vacation at the lake.'),
                                ('dog', 'A hotdog on a plate.'),
                                ('rain', 'A train on the tracks.'),
                                ('dog', 'doghouse'), ('dog', 'dog_2'),
                                ('dog', '2dog'), ('cafe', 'cafe\u0301')):
            with self.subTest(phrase=phrase, content=content):
                self.assertFalse(match_description(
                    (self.source('edited_caption', '1', content),),
                    self.description((phrase, (phrase,))))[0])
        for phrase, content in (('dog', '一只dog在跑。'), ('雪', '雪地里有积雪。'),
                                ('dog', 'A DOG!'), ('red coat', 'A red coat is visible.')):
            with self.subTest(content=content):
                self.assertTrue(match_description(
                    (self.source('edited_caption', '1', content),),
                    self.description((phrase, (phrase,))))[0])

    def test_negative_sources_cannot_contribute_reasons_or_authored_quality(self):
        sources = (self.source('photo_memory', 'private-negative', 'No dog was nearby.'),
                   self.source('generated_caption', 'positive', 'A dog running.'))
        matched, reasons, quality = match_description(sources, self.description(('dog', ('dog',))))
        self.assertTrue(matched)
        self.assertEqual([{'source':'generated_caption', 'source_id':'positive', 'revision':1}], reasons)
        self.assertEqual(quality[0], 0)

    def test_reasons_are_deduplicated_and_bounded_without_text_leaks(self):
        plan = self.description(("岸边", ("beach",)), ("海滩", ("beach",)))
        sources = tuple(self.source("generated_caption", str(index), "A beach day, private phrase")
                        for index in range(MAX_MATCH_REASONS + 10))

        matched, reasons, _quality = match_description(sources, plan)

        self.assertTrue(matched)
        self.assertEqual(len(reasons), MAX_MATCH_REASONS)
        self.assertEqual(len({reason["source_id"] for reason in reasons}), MAX_MATCH_REASONS)
        self.assertTrue(all(set(reason) == {"source", "source_id", "revision"} for reason in reasons))
        self.assertNotIn("private phrase", repr(reasons))
        self.assertNotIn("beach", repr(reasons))

    def test_closed_shape_types_caps_and_duplicates_are_rejected_safely(self):
        good = self.description(("beach", ("by the sea",)))
        invalid = [
            {**good, "extra": True},
            {"version": True, "concepts": good["concepts"]},
            {"version": 1.0, "concepts": good["concepts"]},
            {"version": 1, "concepts": []},
            self.description(*[(f"concept-{i}", (f"alt-{i}",)) for i in range(MAX_CONCEPTS + 1)]),
            self.description(("beach", tuple(f"alternative-{i}" for i in range(MAX_ALTERNATIVES + 1)))),
            self.description(("beach", ("shore", "ＳＨＯＲＥ"))),
            self.description(("beach", ("shore", " shore"))),
            self.description(("Ｆａｍｉｌｙ", ("family",)), ("family", ("kin",))),
            self.description(("beach\n", ("shore",))),
            self.description(("\ud800", ("shore",))),
            self.description(("x" * (MAX_PHRASE_BYTES + 1), ("shore",))),
            {"version": 1, "concepts": tuple(good["concepts"])},
        ]
        for value in invalid:
            with self.subTest(value=type(value).__name__):
                with self.assertRaisesRegex(ValueError, "^Invalid descriptive query$") as error:
                    normalize_description(value)
                self.assertNotIn("shore", str(error.exception))

    def test_total_description_byte_cap(self):
        plan = self.description(*[
            ((chr(0x4e00 + index) * 42) + str(index),
             tuple((chr(0x4e00 + index) * 42) + str(index) + str(alt)
                                        for alt in range(MAX_ALTERNATIVES)))
            for index in range(MAX_CONCEPTS)
        ])
        self.assertGreater(len(json.dumps(
            plan, ensure_ascii=False, separators=(",", ":")).encode("utf-8")), MAX_DESCRIPTION_BYTES)
        with self.assertRaisesRegex(ValueError, "^Invalid descriptive query$"):
            normalize_description(plan)

    def test_only_normalized_source_records_are_accepted(self):
        plan = self.description(("park", ("in the park",)))
        with self.assertRaisesRegex(ValueError, "^Invalid descriptive query$"):
            match_description([{"source": "edited_caption", "source_id": "1",
                                "revision": 1, "content": "in the park"}], plan)
        with self.assertRaisesRegex(ValueError, "^Invalid descriptive query$"):
            class UntrustedSource(NormalizedSource):
                pass

            match_description((UntrustedSource("edited_caption", "1", 1,
                                               "in the park", "in the park"),), plan)
        with self.assertRaisesRegex(ValueError, "^Invalid descriptive query$"):
            match_description((NormalizedSource("private_conversation", "1", 1,
                                                "in the park", "in the park"),), plan)

    def test_cancellation_propagates_from_concept_source_loops(self):
        plan = self.description(("park", ("in the park", "park")))
        sources = (self.source("generated_caption", str(i), "in the park") for i in range(3))
        sources = tuple(sources)
        checks = [0]

        def check():
            checks[0] += 1
            if checks[0] == 5:
                raise RuntimeError("cancelled")

        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            match_description(sources, plan, check)
        self.assertEqual(checks[0], 5)


if __name__ == "__main__":
    unittest.main()

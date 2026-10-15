"""Focused tests for request-local literal text match quality."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.access.search_text import (  # noqa: E402
    SEARCH_TEXT_POLICY_VERSION,
    NormalizedSource,
    match_text,
    normalize_filters,
    normalize_sources,
    rank_results,
)


class SearchTextTests(unittest.TestCase):
    def source(self, source, source_id, revision, content, **extra):
        return {"source": source, "source_id": source_id, "revision": revision,
                "content": content, **extra}

    def test_literal_unicode_normalization_and_no_synonym_expansion(self):
        row = {"text_sources": normalize_sources([
            self.source("edited_caption", "1", 1, "Ｆａｍｉｌｙ 海边 Beach")
        ], lambda: None)}
        filters = normalize_filters({"text": '"Family 海边"'})
        # Quotes remain literal characters supplied by the caller. There is no
        # synonym/semantic expansion and no quote-stripping in this helper.
        matched, reasons, quality = match_text(row, filters)
        self.assertFalse(matched)
        self.assertEqual(reasons, [])
        self.assertEqual(quality, (0, 0, 0, 0))

        matched, reasons, quality = match_text(
            row, normalize_filters({"text": "Family 海边"}))
        self.assertTrue(matched)
        self.assertEqual(reasons, [{"source": "edited_caption", "source_id": "1", "revision": 1}])
        self.assertEqual(quality[0], 1)
        self.assertFalse(match_text(row, normalize_filters({"text": "shore"}))[0])
        self.assertEqual(SEARCH_TEXT_POLICY_VERSION, 1)

    def test_existing_substring_eligibility_is_kept_while_boundaries_rank_higher(self):
        sources = normalize_sources([
            self.source("generated_caption", "substring", 1, "infrared blue"),
            self.source("generated_caption", "phrase", 1, "red blue"),
        ], lambda: None)
        phrase = normalize_filters({"text": "red blue"})
        substring = match_text({"text_sources": (sources[0],)}, phrase)
        whole = match_text({"text_sources": (sources[1],)}, phrase)
        self.assertTrue(substring[0])  # eligibility remains literal substring
        self.assertTrue(whole[0])
        self.assertGreater(whole[2], substring[2])

    def test_authored_evidence_then_tighter_text_then_stable_id(self):
        phrase = normalize_filters({"text": "park"})
        rows = {
            "1": {"id": "1", "match_reasons": [{"source": "generated_caption"}]},
            "2": {"id": "2", "match_reasons": [{"source": "edited_caption"}]},
            "3": {"id": "3", "match_reasons": [{"source": "edited_caption"}]},
            "4": {"id": "4", "match_reasons": [{"source": "photo_memory"}]},
        }
        quality = {}
        for asset_id, content, source in (
                ("1", "park", "generated_caption"),
                ("2", "a long note about the park and the surrounding neighborhood", "edited_caption"),
                ("3", "park", "edited_caption"),
                ("4", "park", "photo_memory")):
            normalized = normalize_sources([self.source(source, asset_id, 1, content)], lambda: None)
            matched, reasons, score = match_text({"text_sources": normalized}, phrase)
            self.assertTrue(matched)
            rows[asset_id]["match_reasons"] = reasons
            quality[asset_id] = score

        ranked = rank_results(list(rows.values()), quality)
        self.assertEqual([row["id"] for row in ranked], ["4", "3", "2", "1"])
        self.assertTrue(all("quality" not in row and "score" not in row for row in ranked))

        ties = [{"id": "2"}, {"id": "10"}, {"id": "7"}]
        tied = rank_results(ties, {"2": (1, 1000, 1, -4), "10": (1, 1000, 1, -4),
                                   "7": (1, 1000, 1, -4)})
        self.assertEqual([row["id"] for row in tied], ["10", "7", "2"])

        internal = rank_results([{"id": "2", "_asset_id": "10"}],
                                 {"10": (1, 1000, 1, -4)})
        self.assertEqual(internal, [{"id": "2"}])

    def test_sources_are_request_local_and_keep_only_provenance_fields(self):
        original = self.source("photo_memory", "note-1", 1, "Family park", secret="discard")
        first = normalize_sources([original], lambda: None)[0]
        original.update(revision=2, content="Family beach")
        second = normalize_sources([original], lambda: None)[0]
        self.assertIsInstance(first, NormalizedSource)
        self.assertIsNot(first, second)
        self.assertEqual((first.revision, first.normalized_text), (1, "family park"))
        self.assertEqual((second.revision, second.normalized_text), (2, "family beach"))
        matched, reasons, _ = match_text({"text_sources": (second,)},
                                         normalize_filters({"text": "beach"}))
        self.assertTrue(matched)
        self.assertEqual(reasons, [{"source": "photo_memory", "source_id": "note-1", "revision": 2}])
        self.assertNotIn("secret", reasons[0])

    def test_reason_limit_and_cancellation_are_bounded(self):
        sources = normalize_sources([
            self.source("generated_caption", str(index), 1, "beach")
            for index in range(60)
        ], lambda: None)
        checks = [0]

        def check():
            checks[0] += 1
            if checks[0] == 5:
                raise RuntimeError("cancelled")

        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            match_text({"text_sources": sources}, normalize_filters({"text": "beach"}), check)

        matched, reasons, _ = match_text({"text_sources": sources},
                                         normalize_filters({"text": "beach"}))
        self.assertTrue(matched)
        self.assertEqual(len(reasons), 43)

    def test_rank_cancellation_during_emission_returns_no_partial_list(self):
        found = [{"id": str(value)} for value in (1, 2, 3)]
        quality = {str(value): (1, 1000, 1, -4) for value in (1, 2, 3)}
        checks = [0]

        def check():
            checks[0] += 1
            # Initial + three key preparations + pre/post-sort + first emitted
            # card; cancel before the second card can complete.
            if checks[0] == 8:
                raise RuntimeError("cancelled")

        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            rank_results(found, quality, check)
        self.assertEqual(checks[0], 8)


if __name__ == "__main__":
    unittest.main()

"""Exact bounded parsing for saved-memory card followups."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.assistant_memory_followup import (SavedMemoryFollowup, _clip_source,
    parse_saved_memory_followup)


class AssistantMemoryFollowupParserTests(unittest.TestCase):
    def test_documented_overview_phrases(self):
        for command in ('介绍这些回忆', '介绍这些故事。', '介绍这些回忆录',
                        'introduce these memories', 'Tell me about these saved memories!'):
            with self.subTest(command=command):
                self.assertEqual(parse_saved_memory_followup(command),
                                 SavedMemoryFollowup('overview'))

    def test_documented_ordinal_preview_and_outline_phrases(self):
        self.assertEqual(parse_saved_memory_followup('第2段回忆讲了什么？'),
                         SavedMemoryFollowup('preview', 2))
        self.assertEqual(parse_saved_memory_followup('第二段回忆讲了什么'),
                         SavedMemoryFollowup('preview', 2))
        self.assertEqual(parse_saved_memory_followup('第二个故事讲了什么'),
                         SavedMemoryFollowup('preview', 2))
        self.assertEqual(parse_saved_memory_followup('第2段回忆有哪些章节'),
                         SavedMemoryFollowup('outline', 2))
        self.assertEqual(parse_saved_memory_followup('第二段回忆有哪些章节'),
                         SavedMemoryFollowup('outline', 2))
        self.assertEqual(parse_saved_memory_followup('第2本回忆录有哪些章节'),
                         SavedMemoryFollowup('outline', 2))
        self.assertEqual(parse_saved_memory_followup('what is the second saved memory about'),
                         SavedMemoryFollowup('preview', 2))
        self.assertEqual(parse_saved_memory_followup('what chapters does the 2nd saved memory have'),
                         SavedMemoryFollowup('outline', 2))

    def test_default_outline_is_recognized_without_an_ordinal(self):
        self.assertEqual(parse_saved_memory_followup('有哪些章节。'),
                         SavedMemoryFollowup('outline'))
        self.assertEqual(parse_saved_memory_followup('what chapters does it have?'),
                         SavedMemoryFollowup('outline'))

    def test_range_is_parsed_for_safe_clarification(self):
        self.assertEqual(parse_saved_memory_followup('第99段回忆讲了什么'),
                         SavedMemoryFollowup('preview', 99))

    def test_excerpt_clipping_preserves_original_codepoints_and_source_whitespace(self):
        source = 'A\tB\nFamily 👨‍👩‍👧' + 'x' * 250
        clipped = _clip_source(source)
        self.assertEqual(clipped, source[:240])
        self.assertEqual(_clip_source('Exact title fallback'), 'Exact title fallback')
        self.assertEqual(_clip_source(''), '')

    def test_non_followups_and_suffix_mutations_do_not_match(self):
        for command in ('介绍这些结果', '介绍这些回忆然后删除',
                        '第二段回忆讲了什么并删除原文',
                        'what is the second saved memory about and delete it',
                        'what chapters does this have', 'find photos'):
            with self.subTest(command=command):
                self.assertIsNone(parse_saved_memory_followup(command))


if __name__ == '__main__':
    unittest.main()

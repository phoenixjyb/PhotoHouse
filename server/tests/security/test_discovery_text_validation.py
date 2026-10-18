"""Caption validation keeps its byte, Unicode and control-character contract."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from app.access.discovery import DiscoveryInvalid, text


class DiscoveryTextValidationTests(unittest.TestCase):
    def test_c0_controls_at_every_position_and_allowed_line_breaks(self):
        for codepoint in range(128):
            char = chr(codepoint)
            for value in (char + '海边', '海' + char + '边', '海边' + char):
                with self.subTest(codepoint=codepoint, value=value):
                    if codepoint < 32 and char not in '\n\t':
                        with self.assertRaises(DiscoveryInvalid):
                            text(value, 64)
                    else:
                        self.assertIs(text(value, 64), value)

    def test_bilingual_and_unicode_text_keeps_original_spelling(self):
        for value in ('海边和姥姥 beach', '俺家娃', 'ＡＢＣ café e\u0301',
                      '小溪🙂\t家人\n', '\x7f\x85\u2028\u2029', '\u0009照片\u000a'):
            with self.subTest(value=value):
                size = len(value.encode('utf-8'))
                self.assertIs(text(value, size), value)
                with self.assertRaises(DiscoveryInvalid):
                    text(value, size - 1)

    def test_utf8_byte_limit_is_not_a_character_limit(self):
        for value in ('x' * 4096, '海' * 1365 + 'x', '🙂' * 1024):
            self.assertEqual(len(value.encode('utf-8')), 4096)
            self.assertIs(text(value, 4096), value)
            with self.assertRaises(DiscoveryInvalid):
                text(value + 'x', 4096)

    def test_empty_and_whitespace_policy_is_unchanged(self):
        for value in ('', ' ', '\t\n', '\u00a0\u3000', '\u2028'):
            with self.subTest(value=value):
                with self.assertRaises(DiscoveryInvalid):
                    text(value, 64)
                self.assertIs(text(value, 64, nonempty=False), value)
        # Optional empty content still cannot contain a forbidden control.
        with self.assertRaises(DiscoveryInvalid):
            text('\r', 64, nonempty=False)

    def test_invalid_unicode_and_non_strings_fail_closed(self):
        class TextSubclass(str):
            pass

        for value in ('\ud800', '\udfff', 'caption\ud800', None, 1, b'photo',
                      TextSubclass('caption')):
            with self.subTest(value=repr(value)):
                with self.assertRaises(DiscoveryInvalid):
                    text(value, 4096)


if __name__ == '__main__':
    unittest.main()

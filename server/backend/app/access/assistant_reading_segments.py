"""Deterministic transient segments of one authorized saved narrative section."""
from __future__ import annotations

import unicodedata

MAX_SOURCE_BYTES = 6000
MAX_SEGMENT_CODEPOINTS = 120
MAX_SEGMENT_BYTES = 360
MAX_SEGMENTS = 128
_BREAKS = frozenset('。！？.!?\n；;')


def saved_reading_segments(text: str) -> tuple[str, ...]:
    """Preserve exact source order/spacing; never infer or polish saved words.

    This input bound is smaller than the TTS adapter's 600-byte ceiling. It is
    not an audio duration guarantee; every returned WAV still needs validation.
    """
    if type(text) is not str or not text.strip():
        raise ValueError('saved_section_unavailable')
    try:
        raw = text.encode('utf-8')
    except UnicodeError:
        raise ValueError('saved_section_unavailable') from None
    if len(raw) > MAX_SOURCE_BYTES:
        raise ValueError('saved_section_unavailable')
    for char in text:
        if char in '\n\t\u200c\u200d' or unicodedata.category(char) in {'Zs', 'Zl', 'Zp'}:
            continue
        if not char.isprintable():
            raise ValueError('saved_section_unavailable')

    result = []
    start = 0
    while start < len(text):
        end = start
        byte_count = 0
        last_break = None
        while end < len(text) and end - start < MAX_SEGMENT_CODEPOINTS:
            size = len(text[end].encode('utf-8'))
            if byte_count + size > MAX_SEGMENT_BYTES:
                break
            byte_count += size
            end += 1
            # Keep useful sentence boundaries without creating many tiny turns.
            if (text[end - 1] in _BREAKS or text[end - 1].isspace()) and end - start >= 60:
                last_break = end
        if end < len(text) and last_break is not None:
            end = last_break
        section = text[start:end]
        # Do not drop whitespace or synthesize an empty segment. A pathological
        # whitespace-only bounded section requires source correction/review.
        if end <= start or not section.strip() or len(result) >= MAX_SEGMENTS:
            raise ValueError('saved_section_unavailable')
        result.append(section)
        start = end
    return tuple(result)

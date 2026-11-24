"""Characterization adapter for the bounded, normalized literal-quality kernel.

Production authorization, normalization, provenance, callbacks and sorting stay
in Python. Unsupported text returns None so the original Unicode path is used.
"""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from app.access.search_text import _coverage, _has_whole_phrase_boundary


def run_batch(payload: str) -> str:
    """Record one exact quality calculation through rust-anything."""
    try:
        if len(payload.encode('utf-8')) > 1024 * 1024:
            raise ValueError()
        value = json.loads(payload)
        if (type(value) is not dict or set(value) != {'content', 'phrase'}
                or any(type(v) is not str for v in value.values())
                or any(0xD800 <= ord(c) <= 0xDFFF for v in value.values() for c in v)):
            raise ValueError()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError('invalid_literal_batch') from None
    content, phrase = value['content'], value['phrase']
    punctuation = '，。！？、：；（）【】《》…—‘’“”'
    supported = all(
        ord(c) < 128 or '\u3400' <= c <= '\u4dbf'
        or '\u4e00' <= c <= '\u9fff' or c in punctuation
        for v in (content, phrase) for c in v)
    if (not supported or not phrase or len(content.encode('utf-8')) > 65536
            or len(phrase.encode('utf-8')) > 65536):
        result = None
    else:
        result = (_coverage(content, phrase),
                  int(_has_whole_phrase_boundary(content, phrase)), -len(content))
    return json.dumps(result, separators=(',', ':'))

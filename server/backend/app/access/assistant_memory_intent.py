"""Deterministic opt-in command parsing for saved-memory discovery.

This module recognizes read-only search intents only. It does not authorize a
library or source, resolve an object ID, call discovery, or perform an effect.
"""
from dataclasses import dataclass
import re

from .assistant_memory_discovery import MAX_QUERY_BYTES, MAX_QUERY_CHARS
from .assistant_workspace_store import MAX_INPUT_BYTES, _text


_CHINESE_PREFIXES = (
    ('找回忆册', 'memoir'),
    ('搜索故事', 'story'),
    ('找回忆', None),
)

_ENGLISH_PREFIXES = (
    ('search saved memories for', None),
    ('find saved story', 'story'),
    ('find memoir', 'memoir'),
)

_QUOTES = {
    '"': '"',
    "'": "'",
    '“': '”',
    '‘': '’',
    '「': '」',
    '『': '』',
}
_TERMINAL_SPOKEN_PUNCTUATION = frozenset('。！？!?.,，；;：:、…')


@dataclass(frozen=True, slots=True)
class SavedMemoryIntent:
    """A recognized literal search; `kind=None` searches stories and memoirs."""

    kind: str | None
    phrase: str


def _unwrap_quotes(phrase):
    if len(phrase) >= 2 and phrase[0] in _QUOTES and phrase[-1] == _QUOTES[phrase[0]]:
        return phrase[1:-1].strip(), True
    return phrase, False


def _normalize_phrase(value):
    phrase = value.strip()
    phrase, quoted = _unwrap_quotes(phrase)
    if not quoted:
        # ASR often appends sentence-final punctuation. Preserve punctuation
        # inside an explicitly quoted literal phrase.
        phrase = phrase.rstrip(''.join(_TERMINAL_SPOKEN_PUNCTUATION)).rstrip()
        phrase, quoted = _unwrap_quotes(phrase)
    if not phrase:
        return ''
    if any(0xD800 <= ord(char) <= 0xDFFF or ord(char) < 32 for char in phrase):
        raise ValueError('Invalid saved-memory search phrase')
    try:
        encoded = phrase.encode('utf-8')
    except UnicodeError:
        raise ValueError('Invalid saved-memory search phrase') from None
    if len(phrase) > MAX_QUERY_CHARS or len(encoded) > MAX_QUERY_BYTES:
        raise ValueError('Invalid saved-memory search phrase')
    return phrase


def _english_remainder(text, prefix):
    # The word boundary prevents forms such as "find memoirist" from being
    # interpreted as a command; matching is case-insensitive and phrase text
    # is sliced from the original input so its spelling is preserved.
    pattern = r'[ \t]+'.join(re.escape(word) for word in prefix.split()) + r'\b'
    matched = re.match(pattern, text, flags=re.IGNORECASE)
    if matched is None:
        return None
    return text[matched.end():].lstrip()


def parse_saved_memory_command(text):
    """Return a bounded read-only search intent, or None for other requests.

    Invalid raw request text or an over-limit recognized phrase raises
    ``ValueError``. A recognized prefix with no phrase returns an intent whose
    empty phrase signals that the caller should ask for clarification.
    """
    try:
        _text(text, MAX_INPUT_BYTES)
    except ValueError:
        raise ValueError('Invalid saved-memory command') from None

    command = text.strip()
    for prefix, kind in _CHINESE_PREFIXES:
        if command.startswith(prefix):
            phrase = command[len(prefix):].lstrip()
            return SavedMemoryIntent(kind, _normalize_phrase(phrase))

    for prefix, kind in _ENGLISH_PREFIXES:
        remainder = _english_remainder(command, prefix)
        if remainder is not None:
            return SavedMemoryIntent(kind, _normalize_phrase(remainder))

    return None

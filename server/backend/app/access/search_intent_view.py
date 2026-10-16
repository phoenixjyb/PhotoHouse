"""Build an offset-preserving, redacted view for descriptive intent extraction.

Deterministic hard conditions and recognized command prefixes are hidden from an optional provider.
The returned string has exactly the same Python code-point offsets as the
source query; callers continue compiling filters from the untouched query.
"""
from datetime import date

from . import discovery as d
from .assistant_query_plan import (_MEDIA, _QUOTE, _REFINE_OPEN, _SEARCH_OPEN,
                                   _extract_dates, _remove_occurrences)


_ERROR = 'Invalid scene view'
REDACTION_MARKER = '\u2588'


def _fold_boundary_map(raw: str, folded: str) -> dict[int, int]:
    """Map only normalization-safe source boundaries to folded offsets.

    A boundary is safe when folding its two sides independently produces the
    same result as folding the complete source. This keeps combining and
    Hangul composition sequences indivisible, and prevents partial mappings
    into case-fold or compatibility expansions such as ``ß`` or ligatures.
    """
    positions: dict[int, list[int]] = {}
    for index in range(len(raw) + 1):
        left = d.fold(raw[:index])
        right = d.fold(raw[index:])
        if left + right == folded:
            positions.setdefault(len(left), []).append(index)
    return {offset: sources[0] for offset, sources in positions.items() if len(sources) == 1}


def _changed_runs(before: str, after: str) -> list[tuple[int, int]]:
    if len(before) != len(after):
        raise ValueError(_ERROR)
    runs = []
    start = None
    for index, (old, new) in enumerate(zip(before, after)):
        changed = old != new
        if changed and start is None:
            start = index
        elif not changed and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, len(before)))
    return runs


def scene_view(words: str, today: date, labels) -> str:
    """Mask hard conditions and a recognized command with visible boundaries.

    ``labels`` must be the request's already-resolved public label strings; it
    is used locally and is never included in the returned view. Any date parse
    error or normalization span that cannot map to complete source boundaries
    fails closed with the same fixed error.
    """
    try:
        if (type(words) is not str or not words.strip() or not isinstance(today, date)
                or type(labels) not in (list, tuple)
                or any(type(label) is not str for label in labels)):
            raise ValueError
        raw_bytes = words.encode('utf-8', errors='strict')
        if len(raw_bytes) > 1024 or any(
                (ord(char) < 32 and char not in '\n\t') or ord(char) == 127
                for char in words):
            raise ValueError

        # Quotes are cut from the original before normalization so neither
        # literal contents nor quoted date/media-like words reach detection.
        outside_chars = list(words)
        for match in _QUOTE.finditer(words):
            outside_chars[match.start():match.end()] = ' ' * (match.end() - match.start())
        outside = ''.join(outside_chars)
        folded = d.fold(outside)

        _ranges, date_residue, date_error = _extract_dates(folded, today)
        if date_error is not None or len(date_residue) != len(folded):
            raise ValueError
        masked = _remove_occurrences(date_residue, labels)
        for _kind, pattern in _MEDIA:
            masked = pattern.sub(lambda match: ' ' * len(match.group(0)), masked)

        # Reuse the literal parser's command grammar, anchored to the original
        # unquoted query. Do not reinterpret a later scene word as a command
        # just because earlier hard conditions have already been hidden.
        command_start = len(folded) - len(folded.lstrip())
        command_words = folded[command_start:]
        command = _SEARCH_OPEN.match(command_words) or _REFINE_OPEN.match(command_words)
        if command is not None:
            start, end = command_start + command.start(), command_start + command.end()
            masked = masked[:start] + ' ' * (end - start) + masked[end:]
        if len(masked) != len(folded):
            raise ValueError

        boundaries = _fold_boundary_map(outside, folded)
        source_runs = []
        for start, end in _changed_runs(folded, masked):
            source_start = boundaries.get(start)
            source_end = boundaries.get(end)
            if (source_start is None or source_end is None or source_start >= source_end
                    or d.fold(outside[source_start:source_end]) != folded[start:end]):
                raise ValueError
            source_runs.append((source_start, source_end))

        # A run can bridge adjacent independently-detected masks. Merge runs
        # before applying them so overlapping labels/date/media hits are safe.
        merged = []
        for start, end in sorted(source_runs):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))

        result = list(outside)
        for match in _QUOTE.finditer(words):
            result[match.start():match.end()] = REDACTION_MARKER * (match.end() - match.start())
        for start, end in merged:
            result[start:end] = REDACTION_MARKER * (end - start)
        view = ''.join(result)
        if len(view) != len(words):
            raise ValueError
        return view
    except (UnicodeError, TypeError, ValueError, OverflowError):
        raise ValueError(_ERROR) from None

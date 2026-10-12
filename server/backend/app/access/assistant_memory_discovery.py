"""Read-only, library-scoped discovery over saved family stories and memoirs.

This is an internal foundation for later assistant presentation. It deliberately
uses the existing authorized memory readers and never reads source captions,
media, providers, or saved-memory revision tables directly.
"""
from dataclasses import dataclass
import hashlib
import json
import sqlite3

from .memory_books import MemoryBooks
from .memory_stories import MemoryStories
from .transport import TransportError


MAX_CANDIDATES = 256
MAX_RESULTS = 12
MAX_QUERY_BYTES = 320
MAX_QUERY_CHARS = 160
MAX_EXCERPT_CHARS = 240


@dataclass(frozen=True, slots=True)
class MemoryReference:
    """Immutable reference to a currently readable saved memory."""

    kind: str
    id: str
    revision: str
    source_revision: str
    title: str
    excerpt: str


def _query(value):
    if type(value) is not str:
        raise TransportError(400, 'Invalid memory search')
    value = value.strip()
    if not value or len(value) > MAX_QUERY_CHARS:
        raise TransportError(400, 'Invalid memory search')
    try:
        if len(value.encode('utf-8')) > MAX_QUERY_BYTES or any(
                0xD800 <= ord(char) <= 0xDFFF or ord(char) < 32 for char in value):
            raise ValueError()
    except (UnicodeError, ValueError):
        raise TransportError(400, 'Invalid memory search') from None
    return value.casefold()


def _source_revision(value):
    try:
        packed = json.dumps(value, ensure_ascii=True, sort_keys=True,
                            separators=(',', ':'), allow_nan=False).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise TransportError(503, 'Saved memory search unavailable') from None
    return hashlib.sha256(packed).hexdigest()


def _excerpt(text, query):
    """Return a bounded plain-text window containing the literal match."""
    if not text:
        return ''
    folded = text.casefold()
    at = folded.find(query)
    if at < 0:
        return ''
    # casefold can expand some code points. Map the folded offset back to a
    # source offset so the returned excerpt always slices the original text.
    folded_length = 0
    source_at = 0
    for source_at, char in enumerate(text):
        next_length = folded_length + len(char.casefold())
        if next_length > at:
            break
        folded_length = next_length
    start = max(0, source_at - max(0, (MAX_EXCERPT_CHARS - len(query)) // 2))
    end = min(len(text), start + MAX_EXCERPT_CHARS)
    start = max(0, end - MAX_EXCERPT_CHARS)
    excerpt = text[start:end]
    # Memory title, narration and introduction are already plain text. Keep
    # whitespace but remove control characters that can affect card rendering.
    return ''.join(char if char in '\n\t' or char.isprintable() else ' ' for char in excerpt)


class AssistantMemoryDiscovery:
    """Search currently authorized saved memories for a literal text phrase.

    `access` is the request-scoped AccessService. Every list and detail operation
    reauthorizes the supplied token and exact library using existing domain
    services; stale or withdrawn items therefore fail closed during hydration.
    """

    def __init__(self, access):
        self.access = access
        self.stories = MemoryStories(access)
        self.books = MemoryBooks(access)

    def _list_all(self, reader, token, library, budget):
        items = []
        seen = set()
        page = 1
        while True:
            result = reader.list(token, library, page)
            for item in result['items']:
                ident = item.get('id') if type(item) is dict else None
                if type(ident) is not str or not ident or ident in seen:
                    raise TransportError(409, 'Saved memory changed; refresh before reading')
                seen.add(ident)
                items.append(item)
            if len(items) > budget or result['has_more'] and len(items) >= budget:
                # Returning a partial match set would silently hide a possible
                # later hit. Fail closed rather than claim complete discovery.
                raise TransportError(503, 'Saved memory search unavailable')
            if not result['has_more']:
                return items
            page += 1

    def search(self, token, library, query, *, limit=MAX_RESULTS):
        phrase = _query(query)
        if type(limit) is not int or not 1 <= limit <= MAX_RESULTS:
            raise TransportError(400, 'Invalid memory search')

        try:
            source_version = self.access.db.execute('PRAGMA data_version').fetchone()[0]
        except sqlite3.Error:
            raise TransportError(503, 'Saved memory search unavailable') from None

        story_rows = self._list_all(self.stories, token, library, MAX_CANDIDATES)
        book_rows = self._list_all(self.books, token, library,
                                   MAX_CANDIDATES - len(story_rows))

        matches = []
        for summary in story_rows:
            detail = self.stories.get(token, library, summary['id'])
            title = detail['title']
            title_match = phrase in title.casefold()
            body = '\n'.join(chapter['narration'] for chapter in detail['chapters'])
            if title_match or phrase in body.casefold():
                excerpt = _excerpt(title, phrase) if title_match else _excerpt(body, phrase)
                source_revision = _source_revision({
                    'kind': 'story', 'id': detail['id'],
                    'revision': detail['revision'],
                    'selection_revision': detail['selection_revision']})
                matches.append(MemoryReference('story', detail['id'], detail['revision'],
                                               source_revision, title, excerpt))

        for summary in book_rows:
            detail = self.books.get(token, library, summary['id'])
            title = detail['title']
            opening = detail['introduction']
            current_children = []
            for child in detail['stories']:
                current = self.stories.get(token, library, child['id'])
                if current['revision'] != child['revision']:
                    raise TransportError(409, 'Saved memory changed; refresh before reading')
                current_children.append({
                    'id': current['id'], 'revision': current['revision'],
                    'selection_revision': current['selection_revision']})
            title_match = phrase in title.casefold()
            if title_match or phrase in opening.casefold():
                excerpt = _excerpt(title, phrase) if title_match else _excerpt(opening, phrase)
                source_revision = _source_revision({
                    'kind': 'memoir', 'id': detail['id'],
                    'revision': detail['revision'], 'stories': current_children})
                matches.append(MemoryReference('memoir', detail['id'], detail['revision'],
                                               source_revision, title, excerpt))

        # Stable relevance ordering: title hits first, then a normalized title,
        # kind, and ID. The input reader's ordering is deterministic too, but
        # explicit sorting keeps results stable across the two object types.
        def rank(reference):
            title_match = phrase in reference.title.casefold()
            return (0 if title_match else 1, reference.title.casefold(),
                    reference.kind, reference.id)

        result = tuple(sorted(matches, key=rank)[:limit])
        try:
            final_version = self.access.db.execute('PRAGMA data_version').fetchone()[0]
        except sqlite3.Error:
            raise TransportError(503, 'Saved memory search unavailable') from None
        if final_version != source_version:
            raise TransportError(409, 'Saved memory changed; refresh before reading')
        return result

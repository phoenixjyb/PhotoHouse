"""Read-only saved-memory command outcome for explicit assistant opt-in.

The domain object projects transient cards for a fresh response, a strict
legacy-v1 persisted summary, and the assistant store's existing typed refs.
It has no route, persistence, model, provider, media, or navigation behavior.
"""
from dataclasses import dataclass
import hashlib
import json
import re
import uuid

from .assistant_memory_discovery import (MAX_CANDIDATES, MAX_RESULTS,
                                        AssistantMemoryDiscovery,
                                        MemoryReference, MemorySearchPage)
from .assistant_memory_intent import parse_saved_memory_command
from .transport import TransportError


MAX_RESULT_BYTES = 240 * 1024
MAX_TITLE_BYTES = 640
MAX_TITLE_CHARS = 640
MAX_EXCERPT_BYTES = 960
MAX_EXCERPT_CHARS = 240


def _language(text, preference):
    if preference is not None:
        if type(preference) is not str or preference not in {'zh', 'en'}:
            raise TransportError(400, 'Invalid saved-memory locale')
        return preference
    return 'zh' if re.search(r'[\u3400-\u9fff]', text) else 'en'


def _safe_source_text(value, *, max_chars, max_bytes, allow_newlines=False):
    if type(value) is not str:
        raise TransportError(503, 'Saved memory cards unavailable')
    try:
        encoded = value.encode('utf-8')
    except UnicodeError:
        raise TransportError(503, 'Saved memory cards unavailable') from None
    if len(value) > max_chars or len(encoded) > max_bytes or not value.strip():
        raise TransportError(503, 'Saved memory cards unavailable')
    for char in value:
        if allow_newlines and char in '\n\t':
            continue
        # Joined emoji are valid saved family text. Permit the joiners while
        # still rejecting control and bidi formatting characters in cards.
        if not char.isprintable() and char not in '\u200c\u200d':
            raise TransportError(503, 'Saved memory cards unavailable')
    return value


def _reference_payload(reference):
    if (not isinstance(reference, MemoryReference) or type(reference.kind) is not str
            or reference.kind not in {'story', 'memoir'}):
        raise TransportError(503, 'Saved memory cards unavailable')
    ident = reference.id
    try:
        parsed = uuid.UUID(ident) if type(ident) is str else None
        if parsed is None or parsed.version != 4 or str(parsed) != ident:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise TransportError(503, 'Saved memory cards unavailable') from None
    revision = reference.revision
    if (type(revision) is not str or re.fullmatch(r'[1-9][0-9]{0,18}', revision) is None
            or int(revision) > 2**63 - 2):
        raise TransportError(503, 'Saved memory cards unavailable')
    source_revision = reference.source_revision
    if (type(source_revision) is not str or
            re.fullmatch(r'[0-9a-f]{64}', source_revision) is None):
        raise TransportError(503, 'Saved memory cards unavailable')
    title = _safe_source_text(reference.title, max_chars=MAX_TITLE_CHARS,
                              max_bytes=MAX_TITLE_BYTES)
    excerpt = _safe_source_text(reference.excerpt, max_chars=MAX_EXCERPT_CHARS,
                                max_bytes=MAX_EXCERPT_BYTES, allow_newlines=True)
    return {
        'kind': reference.kind, 'id': ident, 'revision': revision,
        'source_revision': source_revision, 'title': title, 'excerpt': excerpt,
    }


def _context_revision(library_id, total, references):
    bound = {
        'kind': 'saved_memory',
        'library_id': library_id,
        'total': total,
        'references': [
            {key: item[key] for key in ('kind', 'id', 'revision', 'source_revision')}
            for item in references
        ],
    }
    packed = json.dumps(bound, ensure_ascii=True, sort_keys=True,
                        separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(packed).hexdigest()


@dataclass(frozen=True, slots=True)
class AssistantSavedMemoryOutcome:
    """Frozen projections for fresh cards, safe history, and typed store refs."""

    library_id: str
    locale: str
    clarification: bool
    reply: str
    references: tuple
    total: int
    has_more: bool
    context_revision: str | None

    def fresh_result(self):
        """Return the transient proposed wire result as fresh mutable objects."""
        cards = [
            {'kind': ref.kind, 'id': ref.id, 'revision': ref.revision,
             'source_revision': ref.source_revision,
             'title': ref.title, 'excerpt': ref.excerpt}
            for ref in self.references
        ]
        if self.clarification:
            result = {
                'version': 1, 'kind': 'clarification', 'reply': self.reply,
                'context': None, 'filters': None, 'items': [], 'total': 0,
                'has_more': False, 'effect': None, 'memory_cards': [],
            }
        else:
            bindings = [
                {key: card[key] for key in ('kind', 'id', 'revision', 'source_revision')}
                for card in cards
            ]
            result = {
                'version': 1, 'kind': 'memory_cards', 'reply': self.reply,
                'context': {
                    'kind': 'saved_memory', 'library_id': self.library_id,
                    'source_revision': self.context_revision,
                    'references': bindings,
                },
                'filters': None, 'items': [], 'total': self.total,
                'has_more': self.has_more, 'effect': None,
                'memory_cards': cards,
            }
        try:
            size = len(json.dumps(result, ensure_ascii=False, separators=(',', ':'),
                                  allow_nan=False).encode('utf-8'))
        except (TypeError, ValueError, UnicodeError, RecursionError):
            raise TransportError(503, 'Saved memory cards unavailable') from None
        if size > MAX_RESULT_BYTES:
            raise TransportError(503, 'Saved memory cards unavailable')
        return result

    def legacy_summary(self):
        """Return the exact safe result-summary grammar accepted by store v1."""
        return {
            'version': 1,
            'kind': 'clarification' if self.clarification else 'results',
            'reply': self.reply,
            'context': None,
            'filters': None,
            'total': 0,
            'has_more': False,
            'effect': None,
        }

    def store_card_refs(self):
        """Project existing opaque typed refs; source text stays out of storage."""
        return [
            {'type': ref.kind, 'id': ref.id,
             'revision': ref.source_revision, 'fingerprint': ref.source_revision}
            for ref in self.references
        ]


class AssistantSavedMemoryTool:
    """Dispatch an explicit search phrase through current scoped readers."""

    def __init__(self, access, discovery=None):
        self.access = access
        self.discovery = discovery if discovery is not None else AssistantMemoryDiscovery(access)

    def run(self, token, library, text, *, locale=None):
        try:
            intent = parse_saved_memory_command(text)
        except ValueError:
            raise TransportError(400, 'Invalid saved-memory search phrase') from None
        if intent is None:
            return None
        # The empty-phrase clarification is still a private-library operation.
        self.access.library_principal(token, library)
        lang = _language(text, locale)
        if intent.phrase == '':
            reply = ('请说出要查找的回忆短语。' if lang == 'zh' else
                     'Say a phrase to search saved memories.')
            return AssistantSavedMemoryOutcome(
                library_id=library, locale=lang, clarification=True, reply=reply,
                references=(), total=0, has_more=False, context_revision=None)

        page = self.discovery.search_page(token, library, intent.phrase, kind=intent.kind)
        if (not isinstance(page, MemorySearchPage) or type(page.total) is not int
                or not 0 <= page.total <= MAX_CANDIDATES
                or type(page.has_more) is not bool or type(page.references) is not tuple
                or len(page.references) > MAX_RESULTS
                or len(page.references) != min(page.total, MAX_RESULTS)
                or page.has_more != (page.total > len(page.references))):
            raise TransportError(503, 'Saved memory cards unavailable')
        projected = tuple(_reference_payload(ref) for ref in page.references)
        identities = [(ref['kind'], ref['id']) for ref in projected]
        if len(set(identities)) != len(identities):
            raise TransportError(503, 'Saved memory cards unavailable')
        if any(intent.kind is not None and ref['kind'] != intent.kind for ref in projected):
            raise TransportError(503, 'Saved memory cards unavailable')
        # Reconstruct frozen refs from validated exact source values. Never
        # truncate source title/excerpt text to fit a wire or storage budget.
        refs = tuple(MemoryReference(**item) for item in projected)
        if page.total == 0:
            reply = ('没有找到匹配的已保存回忆。试试换个短语。' if lang == 'zh' else
                     'No saved memories matched. Try a different phrase.')
        elif page.has_more:
            reply = (f'找到 {page.total} 段已保存回忆，先显示前 {MAX_RESULTS} 段。可以用更具体的短语继续查找。'
                     if lang == 'zh' else
                     f'Found {page.total} saved memories; showing the first {MAX_RESULTS}. '
                     'Try a more specific phrase to narrow the search.')
        else:
            reply = (f'找到 {page.total} 段已保存回忆。'
                     if lang == 'zh' else
                     f'Found {page.total} saved memories.')
        context_revision = _context_revision(library, page.total, projected)
        outcome = AssistantSavedMemoryOutcome(
            library_id=library, locale=lang, clarification=False, reply=reply,
            references=refs, total=page.total, has_more=page.has_more,
            context_revision=context_revision)
        outcome.fresh_result()  # Enforce the complete 240 KiB response budget now.
        return outcome

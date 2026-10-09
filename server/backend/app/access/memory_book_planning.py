"""Read-only editorial planning for memoirs larger than one model pass.

This lists current saved structure and bounded drafting eligibility. It neither
invents an outline nor starts generation. All children are authorized before
returning any part, and no source wording or private contribution is copied.
"""
from collections import Counter
import json

from .memory_books import MemoryBooks
from .memory_jobs import context, parent, editorial_choice, EDITORIAL_CONTEXT_PROFILE
from .memory_narrative import MAX_BUNDLE_BYTES, MAX_CHAPTERS, MAX_SOURCES
from .stories import _uuid
from .transport import TransportError


class MemoryBookPlanning:
    def __init__(self, access, *, editorial_enabled=False):
        if type(editorial_enabled) is not bool:
            raise ValueError('editorial_feature_flag_must_be_boolean')
        self.access = access
        self.editorial_enabled = editorial_enabled

    @staticmethod
    def _capacity(access, library, member, target_type, ident, *, editorial_context=False):
        try:
            bundle, _, can_edit = context(access, library, member, target_type, ident,
                                         editorial_context=editorial_context)
        except TransportError as error:
            if error.status != 422:
                raise
            # Existing context validation covers source, chapter and byte bounds.
            # Do not expose evidence, provider errors or partial context as a plan.
            result = {'state': 'smaller_scope_required', 'can_draft': False,
                      'source_count': None, 'source_kinds': None}
            if editorial_context:
                result['context_bytes'] = None
            return result
        result = {'state': 'within_limits', 'can_draft': can_edit,
                'source_count': len(bundle['sources']),
                'source_kinds': dict(sorted(Counter(s['kind'] for s in bundle['sources']).items()))}
        if editorial_context:
            result['context_bytes'] = len(json.dumps(bundle, ensure_ascii=False, allow_nan=False,
                separators=(',', ':')).encode('utf-8'))
        return result

    def get(self, token, library, ident, editorial_context=False):
        ident = _uuid(ident)
        with self.access._transaction():
            member = self.access._require(token, library, 'library.read')
            if type(editorial_context) is not bool:
                raise TransportError(400, 'Invalid memoir context choice')
            if editorial_context:
                editorial_choice({'context_profile': EDITORIAL_CONTEXT_PROFILE}, enabled=self.editorial_enabled)
            books = MemoryBooks(self.access)
            books._ready()
            tables = {r[0] for r in self.access.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if not {'access_memory_contributions', 'access_memory_contribution_derivations'} <= tables:
                raise TransportError(503, 'Memory planning unavailable')
            row, stories, can_edit, _ = parent(self.access, library, member, 'book', ident)
            sections = []
            for position, story in enumerate(stories, 1):
                section = {'position': position, 'id': story['id'],
                    'revision': story['revision'], 'title': story['title'],
                    'item_count': len(story['items']), 'can_edit': story['can_edit'],
                    'chapters': [{'id': chapter['id'], 'title': chapter['title'],
                                  'item_count': len(chapter['asset_ids'])}
                                 for chapter in story['chapters']],
                    **self._capacity(self.access, library, member, 'story', story['id'])}
                sections.append(section)
            whole = self._capacity(self.access, library, member, 'book', ident,
                                   editorial_context=editorial_context)
            result = {'version': 1, 'target_type': 'book', 'target_id': ident,
                'revision': str(row['revision']), 'can_edit': can_edit,
                'kind': 'saved_structure_plan', 'generated': False, 'queued': False,
                'needs_review': True, 'story_count': len(sections),
                'chapter_count': sum(len(s['chapters']) for s in sections),
                'item_count': sum(s['item_count'] for s in sections),
                'distinct_item_count': len({item['id'] for story in stories for item in story['items']}),
                'limits': {'chapters': MAX_CHAPTERS, 'sources': MAX_SOURCES,
                           'context_bytes': MAX_BUNDLE_BYTES},
                'whole': whole, 'sections': sections}
            if editorial_context:
                result['context_profile'] = EDITORIAL_CONTEXT_PROFILE
            return result

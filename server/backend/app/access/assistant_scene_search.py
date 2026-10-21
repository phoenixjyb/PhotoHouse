"""Explicit workspace-only scene ranking inside an already reviewed search.

V4 is not a replacement language planner. The separate scene opt-in supplies
visual wording; only server-owned v2/v3 context supplies hard conditions.
Recovery trusts the validated private store's first-page ranking, then checks
the entire source/vector cohort again without re-encoding the user's query.
"""
from dataclasses import dataclass, replace
import math

from . import discovery as d
from .assistant_search import SearchRuntime, SearchPlan
from .semantic_search import SemanticSearchRuntime
from .semantic_streaming import MAX_LIBRARY_CANDIDATES


def scene_query(value):
    d.text(value, 512)
    d.require(not any(ord(c) < 32 or 0x7f <= ord(c) < 0xa0 for c in value))
    return value


def _coverage_reply(reply, semantic, total, language):
    coverage = semantic.get('coverage_details')
    if coverage is None or coverage['state'] != 'partial':
        return reply
    searchable, omitted = coverage['searchable_images'], coverage['omitted_images']
    matched = coverage['matched_omitted_images']
    if language == 'zh':
        lead = '在可语义检索的照片中未找到符合当前筛选条件的结果。' if total == 0 else reply
        return (f'{lead} 语义检索覆盖 {searchable:,} 张照片；{omitted:,} 张尚未建立索引。'
                f'当前筛选条件中有 {matched:,} 张未参与相似度排序。这些照片仍可通过普通搜索查找。')
    lead = 'No matches in the searchable photos within your current filters.' if total == 0 else reply
    return (f'{lead} Semantic search covers {searchable:,} photos; {omitted:,} are not indexed yet. '
            f'{matched:,} photos within your current filters were not ranked. '
            'You can still look for those photos using ordinary search.')


def _scope(value, library):
    from .assistant_workspace_store import _context_value
    if type(value) is not dict or value.get('search_version') not in (2, 3):
        raise ValueError('Reviewed search scope required')
    scope = _context_value(value, library)
    SearchPlan(2, scope['filters'])  # Descriptive caption clues must not be dropped.
    if 'media' in scope['filters'] and scope['filters']['media'] != ['image']:
        raise ValueError('Photo scope required')
    if (scope['filters'] == {} and scope['total'] == 1 and
            scope['fingerprint'] == d.assistant_asset_fingerprint(
                scope['binding'], scope['visible_ids'][0])):
        # An explicit asset lookup is not an unrestricted library search.
        raise ValueError('Search scope required')
    return scope


def context_value(value, library):
    """Closed, bounded server-owned context; never accepted by legacy turn APIs."""
    from .assistant_workspace_store import _context_value
    fields = {'library_id', 'binding', 'fingerprint', 'filters', 'visible_ids',
              'total', 'search_version', 'scene'}
    if (type(value) is not dict or set(value) != fields or
            type(value['search_version']) is not int or value['search_version'] != 4):
        raise ValueError('Invalid scene context')
    # Reuse the legacy storage checks without letting nested semantic scopes
    # recurse or smuggle a different library, identifier or result count.
    base = _context_value({**{k: v for k, v in value.items() if k != 'scene'},
                           'search_version': 2}, library)
    scene = value['scene']
    if (type(scene) is not dict or set(scene) != {'version', 'query', 'scope', 'scores'}
            or type(scene['version']) is not int or scene['version'] != 1):
        raise ValueError('Invalid scene context')
    query = scene_query(scene['query'])
    scope = _scope(scene['scope'], library)
    scores = scene['scores']
    if (base['filters'] != {**scope['filters'], 'media': ['image']} or
            base['total'] > min(MAX_LIBRARY_CANDIDATES, scope['total']) or type(scores) is not list or
            len(scores) != len(base['visible_ids']) or
            any(type(x) not in (int, float) or not math.isfinite(x) or not -1 <= x <= 1
                for x in scores)):
        raise ValueError('Invalid scene context')
    return {**base, 'search_version': 4,
            'scene': {'version': 1, 'query': query, 'scope': scope,
                      'scores': [float(x) for x in scores]}}


@dataclass(frozen=True)
class SceneSearchRuntime:
    semantic: SemanticSearchRuntime
    kinship_provider: object = None

    def base_engine(self, scope):
        discovery = (replace(self.semantic.discovery, budget=self.semantic.budget)
                     if self.semantic.serving_limits else self.semantic.discovery)
        return SearchRuntime(discovery, self.kinship_provider,
                             search_version=scope['search_version'])

    def scope_result(self, token, library, scope):
        from .assistant import _context_result
        return _context_result(self.base_engine(scope), token, library, scope)

    def deadline(self):
        # One allowance across scope reads, ranking, and final scope validation.
        # Individual synchronous reads/provider phases retain their own bounds;
        # checks are cooperative rather than a provider cancellation receipt.
        clock = self.semantic.budget.clock
        started = previous = clock()
        def check():
            nonlocal previous
            now = clock()
            if (not math.isfinite(started) or not math.isfinite(now) or now < previous or
                    now - started > self.semantic.budget.search_seconds):
                raise d.DiscoveryUnavailable()
            previous = now
            return False
        check()
        return check

    def search(self, token, library, words, previous, *, language=None):
        from .assistant import AssistantChanged, AssistantInvalid, _language, _normalize_cards
        try:
            query = scene_query(words)
            scope = (context_value(previous, library)['scene']['scope']
                     if type(previous) is dict and previous.get('search_version') == 4
                     else _scope(previous, library))
        except ValueError:
            raise AssistantInvalid() from None
        check = self.deadline()
        self.scope_result(token, library, scope)
        check()
        found = _normalize_cards(self.semantic.call('search', token, library, check,
            {'query': query, 'filters': scope['filters'], 'page_size': 20}))
        check()
        presentation = self.scope_result(token, library, scope)
        check()
        if found['total'] > scope['total']:
            raise AssistantChanged()
        ctx = context_value({'library_id': library, 'binding': found['binding'],
            'fingerprint': found['fingerprint'], 'filters': found['filters'],
            'visible_ids': [x['id'] for x in found['items']], 'total': found['total'],
            'search_version': 4, 'scene': {'version': 1, 'query': query, 'scope': scope,
                'scores': [x['semantic_score'] for x in found['items']]}}, library)
        lang = language if language in ('zh', 'en') else _language(words)
        reply = ('已在当前筛选条件内按场景相似度排列照片。相似度仅供参考，请查看照片确认。'
                 if lang == 'zh' else
                 'Photos ranked by scene similarity within your current filters. '
                 'Similarity is approximate; check the photos to confirm.')
        reply = _coverage_reply(reply, found['semantic'], found['total'], lang)
        return {'version': 4, 'kind': 'results', 'reply': reply, 'context': ctx,
                'filters': ctx['filters'], 'items': found['items'], 'total': found['total'],
                'has_more': found['has_more'], 'effect': None,
                'interpretation': presentation['interpretation'], 'semantic': found['semantic']}

    def restore(self, token, library, summary):
        from .assistant import AssistantChanged, _normalize_cards
        ctx = context_value(summary['context'], library)
        scope = ctx['scene']['scope']
        check = self.deadline()
        self.scope_result(token, library, scope)
        check()
        snapshot = tuple(zip(ctx['visible_ids'], ctx['scene']['scores']))
        found = _normalize_cards(self.semantic._restore_server_snapshot(
            token, library, check, {'query': ctx['scene']['query'],
                'filters': ctx['filters'], 'binding': ctx['binding'],
                'fingerprint': ctx['fingerprint'], 'page_size': 20}, snapshot))
        check()
        presentation = self.scope_result(token, library, scope)
        check()
        if found['total'] != ctx['total'] or [x['id'] for x in found['items']] != ctx['visible_ids']:
            raise AssistantChanged()
        return {**summary, 'context': ctx, 'effect': None, 'items': found['items'],
                'interpretation': presentation['interpretation'], 'semantic': found['semantic']}

"""Narrow, run-scoped tools for the optional read-only assistant agent."""
from dataclasses import dataclass
import json
import secrets


MAX_TOOL_BYTES = 16 * 1024
MAX_SELECTOR_BYTES = 1024


class AgentToolError(ValueError):
    """The runtime supplied a tool name, arguments, or selector we do not accept."""


def _pack(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'),
                      sort_keys=True, allow_nan=False).encode('utf-8')


def _unpack(value):
    return json.loads(value.decode('utf-8'))


def _copy(value):
    return _unpack(_pack(value))


@dataclass(frozen=True)
class HostOutcome:
    """Detached authoritative result. The agent receives only a projection."""

    _summary_json: bytes
    _items_json: bytes

    _SUMMARY_FIELDS = frozenset({'version', 'kind', 'reply', 'context', 'filters',
                                 'total', 'has_more', 'effect'})

    @classmethod
    def from_result(cls, result, pending_intent):
        if type(result) is not dict or type(result.get('items')) is not list:
            raise AgentToolError('Invalid host result')
        if not cls._SUMMARY_FIELDS <= result.keys():
            raise AgentToolError('Invalid host result summary')
        summary = {key: result[key] for key in cls._SUMMARY_FIELDS}
        if pending_intent is not None:
            summary['pending_intent'] = pending_intent
        return cls(_pack(summary), _pack(result['items']))

    def summary(self):
        return _unpack(self._summary_json)

    def cards(self):
        summary = self.summary()
        context = summary.get('context')
        if context is None:
            return []
        items = self.items()
        ids = [item.get('id') for item in items]
        if ids != context.get('visible_ids'):
            raise AgentToolError('Host cards do not match their context')
        return [{'type': 'media', 'id': ident,
                 'revision': context['binding'],
                 'fingerprint': context['fingerprint']} for ident in ids]

    def items(self):
        """Return detached raw cards for host-side projection only."""
        return _unpack(self._items_json)


class _CheckedSearchRuntime:
    """Preserve SearchRuntime behavior while fencing each protected read."""

    def __new__(cls, engine, check, invalidated):
        from .assistant_search import SearchRuntime

        class Checked(SearchRuntime):
            def __init__(self):
                super().__init__(engine.runtime, engine.kinship_provider,
                                 search_version=engine.search_version,
                                 intent_planner=engine.intent_planner)
                self.descriptive_enabled = engine.descriptive_enabled

            def call(self, operation, token, library, cancelled, values):
                check()

                def guarded_cancelled():
                    return invalidated() or cancelled()

                value = super().call(operation, token, library, guarded_cancelled, values)
                check()
                return value

        return Checked()


class AgentTools:
    """Synchronous domain facade. The supervisor owns async scheduling/budget."""

    _TOOLS = frozenset({'get_search_capabilities', 'search_media',
                        'inspect_current_results'})

    def __init__(self, *, engine, token, library, words, context, pending_intent,
                 clock, language, check, invalidated=None):
        from .assistant_search import SearchRuntime
        if not isinstance(engine, SearchRuntime) or engine.search_version != 2:
            raise AgentToolError('Search v2 is required')
        if not callable(check):
            raise AgentToolError('A synchronous liveness check is required')
        if invalidated is not None and not callable(invalidated):
            raise AgentToolError('Invalid cooperative cancellation callback')
        self._engine = _CheckedSearchRuntime(engine, check, invalidated or (lambda: False))
        self._token = token
        self._library = library
        self._words = words
        self._context_json = _pack(context)
        self._pending_json = _pack(pending_intent)
        self._clock = clock
        self._language = language if language in ('zh', 'en') else 'en'
        self._check = check
        self._handle = None
        self._outcome = None
        self._result_json = None
        self._item_handles = {}
        self._incoming_pending_initially_expired = False

    def _revalidate(self, summary):
        """Read the exact saved sources again; never re-run the query planner."""
        self._check()
        from .assistant_workspace_transport import _turn_result
        from .search_pending import current_pending, validate_pending

        pending = summary.get('pending_intent')
        if pending is not None:
            state = validate_pending(pending)
            current = current_pending(state, int(self._clock()))
            # Incoming exclusion questions remain safety guards after their
            # presentation TTL. A new/live date clarification must remain live
            # for the duration of this run; never commit a newly expired prompt.
            allowed_expired_input = (
                state['question'] != 'exclusion' and current is None and
                self._incoming_pending_initially_expired and
                pending == _unpack(self._pending_json))
            if state['question'] != 'exclusion' and current is None and not allowed_expired_input:
                from .assistant import AssistantChanged
                raise AssistantChanged()
            context = summary.get('context')
            if context is not None and context.get('binding') != state['binding']:
                from .assistant import AssistantChanged
                raise AssistantChanged()
        result = _turn_result(self._engine, self._token, self._library, summary,
                              recovered=False)
        self._check()
        return result

    def _canonical(self):
        self._check()
        if self._outcome is None:
            from .assistant_workspace_transport import _workspace_search_turn
            from .search_pending import current_pending
            incoming_pending = _unpack(self._pending_json)
            initial_stamp = int(self._clock())
            if incoming_pending is not None:
                self._incoming_pending_initially_expired = (
                    current_pending(incoming_pending, initial_stamp) is None and
                    incoming_pending.get('question') != 'exclusion')
            result, pending = _workspace_search_turn(
                self._engine, self._token, self._library, self._words,
                _unpack(self._context_json), self._clock,
                language=self._language, pending_intent=_unpack(self._pending_json))
            result = _copy(result)
            pending = _copy(pending)
            effect = result.get('effect')
            if effect is not None:
                if (result.get('kind') != 'open' or type(effect) is not dict or
                        set(effect) != {'type', 'asset_id'} or
                        effect.get('type') != 'open_asset' or
                        type(effect.get('asset_id')) is not str or
                        type(result.get('context')) is not dict or
                        effect['asset_id'] not in result['context'].get('visible_ids', []) or
                        effect['asset_id'] not in [item.get('id') for item in result.get('items', [])]):
                    raise AgentToolError('Unsupported host effect')
                result['kind'] = 'results'
                result['effect'] = None
                result['reply'] = ('请选择一项结果打开。' if self._language == 'zh' else
                                   'Select a result to open it.')
            elif result.get('kind') == 'open':
                raise AgentToolError('Open result is missing its effect')
            if result.get('kind') not in ('results', 'clarification', 'unsupported'):
                raise AgentToolError('Unsupported host result')
            summary = {key: value for key, value in result.items() if key != 'items'}
            if pending is not None:
                summary['pending_intent'] = pending
            self._check()
            self._revalidate(summary)
            self._result_json = _pack(result)
            self._outcome = HostOutcome.from_result(result, pending)
            self._handle = secrets.token_urlsafe(24)
            self._item_handles = {index: secrets.token_urlsafe(24)
                                  for index, _ in enumerate(result['items'][:5])}
        else:
            self._revalidate(self._outcome.summary())
        self._check()
        return self._outcome

    def resolve(self, selector):
        if (type(selector) is not dict or set(selector) != {'outcome_handle'} or
                type(selector.get('outcome_handle')) is not str):
            raise AgentToolError('Invalid outcome selector')
        try:
            if len(_pack(selector)) > MAX_SELECTOR_BYTES:
                raise AgentToolError('Outcome selector is too large')
        except (UnicodeError, ValueError):
            raise AgentToolError('Invalid outcome selector') from None
        if self._outcome is None or not secrets.compare_digest(
                selector['outcome_handle'], self._handle):
            raise AgentToolError('Unknown outcome selector')
        self._revalidate(self._outcome.summary())
        self._check()
        return HostOutcome(_pack(self._outcome.summary()), _pack(self._outcome.items()))

    def dispatch(self, name, arguments):
        if type(name) is not str or name not in self._TOOLS:
            self._check()
            raise AgentToolError('Unknown tool')
        if type(arguments) is not dict:
            self._check()
            raise AgentToolError('Tool arguments must be an object')
        self._check()
        if name == 'get_search_capabilities':
            if arguments:
                raise AgentToolError('Capabilities takes no arguments')
            ready = self._engine.call('readiness', self._token, self._library,
                                      lambda: False, {})
            self._check()
            response = {
                'search_version': ready['search_version'],
                'date_basis': ready['date_basis'],
                'enabled': list(ready['enabled']),
                'truncated': False,
            }
        elif name == 'search_media':
            if arguments:
                raise AgentToolError('Search takes no arguments')
            self._canonical()
            response = self._projection()
        else:
            if (set(arguments) != {'outcome_handle'} or
                    type(arguments.get('outcome_handle')) is not str):
                raise AgentToolError('Inspection requires an outcome handle')
            outcome = self.resolve(arguments)
            response = self._projection(outcome)
        packed = _pack(response)
        if len(packed) > MAX_TOOL_BYTES:
            raise AgentToolError('Tool response exceeds the byte limit')
        self._check()
        return _unpack(packed)

    def _projection(self, outcome=None):
        outcome = outcome or self._outcome
        summary = outcome.summary()
        result = _unpack(self._result_json) if outcome is self._outcome else None
        # The resolved copy has the same content but is intentionally detached.
        cards = outcome.items()
        if result is None:
            result = {**summary, 'items': cards}
        from .assistant import _result_overview
        overview = _result_overview(result, self._language,
                                    filters=result.get('filters'))
        overview, summary_truncated = _clip(overview, 1024)
        previews = []
        for position, item in enumerate(cards[:5], 1):
            entry = {'position': position,
                     'item_handle': (self._item_handles[position - 1]
                                     if position - 1 in self._item_handles
                                     else secrets.token_urlsafe(24))}
            if item.get('kind') in ('image', 'video'):
                entry['kind'] = item['kind']
            if type(item.get('taken_at')) is str:
                from . import discovery
                day = discovery.taken_day(item['taken_at'])
                if day is not None:
                    entry['date'] = day
            caption = item.get('caption')
            if type(caption) is str:
                entry['caption_excerpt'], clipped = _clip(caption, 256)
                summary_truncated = summary_truncated or clipped
            previews.append(entry)
        return {'outcome_handle': self._handle,
                'kind': summary['kind'], 'summary': overview,
                'total': result.get('total', 0),
                'has_more': bool(result.get('has_more')),
                'truncated': summary_truncated or len(cards) > 5,
                'items': previews}


def _clip(value, maximum):
    """Clip UTF-8 text on a character boundary and report whether it changed."""
    if type(value) is not str:
        return '', False
    raw = value.encode('utf-8')
    if len(raw) <= maximum:
        return value, False
    return raw[:maximum].decode('utf-8', errors='ignore'), True

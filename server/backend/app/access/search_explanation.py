"""Pure, bounded explanations of the current search filters."""
from __future__ import annotations

import json
import unicodedata


_FILTER_QUERY_PHRASES = frozenset((
    'what are we looking for',
    'what are we searching for',
    'what filters are active',
    'describe the current search',
    'explain the current search',
    '当前筛选条件是什么',
    '现在筛选了哪些条件',
    '现在在找什么',
    '解释当前查找条件',
    '当前search条件是什么',
    'what are the 当前筛选条件',
))
_EMPTY_QUERY_PHRASES = frozenset((
    'why no results',
    'why did you find nothing',
    'why are there no results',
    '为什么没找到',
    '怎么没有结果',
    '为什么没有结果',
    '为什么没有results',
))
_TERMINAL_PUNCTUATION = frozenset('?!。？！.,;:，；：、')
_MAX_BYTES = 600


def _normalize_query(value: str) -> str:
    value = unicodedata.normalize('NFKC', value).casefold()
    value = ' '.join(value.split())
    return value.rstrip(''.join(_TERMINAL_PUNCTUATION)).strip()


def describe_filter_query(words) -> bool:
    """Recognize only a complete, closed request to explain active filters."""
    if type(words) is not str:
        return False
    normalized = _normalize_query(words)
    # Politeness is a complete optional token at either edge, never an
    # allowance for a request embedded in a larger action.
    for token in ('please', '请'):
        if normalized.startswith(token + ' '):
            normalized = normalized[len(token):].strip()
        elif token == '请' and normalized.startswith(token):
            normalized = normalized[len(token):].strip()
        if normalized.endswith(' ' + token):
            normalized = normalized[:-len(token)].strip()
    return normalized in _FILTER_QUERY_PHRASES


def describe_empty_query(words) -> bool:
    """Recognize only a complete, closed question about an empty result set."""
    if type(words) is not str:
        return False
    normalized = _normalize_query(words)
    for token in ('please', '请'):
        if normalized.startswith(token + ' '):
            normalized = normalized[len(token):].strip()
        elif token == '请' and normalized.startswith(token):
            normalized = normalized[len(token):].strip()
        if normalized.endswith(' ' + token):
            normalized = normalized[:-len(token)].strip()
        elif token == '请' and normalized.endswith(token):
            normalized = normalized[:-len(token)].strip()
    return normalized in _EMPTY_QUERY_PHRASES


def _safe_text(value) -> str:
    if type(value) is not str:
        return ''
    # Replace lone surrogates so the final value always encodes as valid UTF-8.
    return value.encode('utf-8', 'replace').decode('utf-8')


def _quoted(value: str, budget: int) -> str:
    """JSON-quote a value within a UTF-8 byte budget, marking any excerpt."""
    value = _safe_text(value)
    full = json.dumps(value, ensure_ascii=False)
    if len(full.encode('utf-8')) <= budget:
        return full
    suffix = '…'
    room = max(2, budget - len(suffix.encode('utf-8')))
    # Work in code points, testing the encoded JSON because controls expand to
    # six bytes and non-ASCII characters have different UTF-8 widths.
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        candidate = json.dumps(value[:middle], ensure_ascii=False)
        if len(candidate.encode('utf-8')) <= room:
            low = middle
        else:
            high = middle - 1
    quoted = json.dumps(value[:low], ensure_ascii=False)
    # budget is chosen large enough for the two quote marks and excerpt mark.
    return quoted + suffix


def _ids(value, *, nested=False):
    if nested:
        value = value.get('ids', []) if type(value) is dict else []
    return value if type(value) is list else []


def _labels(filters, interpretation, facet):
    selected = _ids(filters.get(facet, []), nested=facet in ('people', 'tags'))
    rows = interpretation.get(facet, []) if type(interpretation) is dict else []
    if type(rows) is not list:
        rows = []
    found = []
    seen = []
    for row in rows:
        if type(row) is not dict or row.get('id') not in selected:
            continue
        ident = row.get('id')
        if ident in seen:
            continue
        label = row.get('label')
        if type(label) is not str:
            continue
        seen.append(ident)
        found.append(label)
    return selected, found


def _preview(selected, labels, *, zh, label_budget):
    pieces = [_quoted(label, label_budget) for label in labels[:2]]
    if not pieces:
        pieces.append('名称不可用' if zh else 'names unavailable')
    remaining = max(0, len(selected) - len(labels[:2]))
    if remaining:
        pieces.append(('另' if zh else '+') + str(remaining) + ('项' if zh else ' more'))
    return ', '.join(pieces)


def _text_clause(value, *, zh, text_budget):
    label = '匹配文字' if zh else 'Text phrase'
    if type(value) is not str:
        return (f'{label}: active (value unavailable)' if not zh else
                f'{label}：已启用（内容不可用）')
    quoted = _quoted(value, text_budget)
    excerpt = len(json.dumps(_safe_text(value), ensure_ascii=False).encode('utf-8')) > text_budget
    if zh:
        return f'{label}：{"摘录" if excerpt else ""}{quoted}'
    return f'{label}: {"excerpt " if excerpt else ""}{quoted}'


def _render(filters, interpretation, *, zh, label_budget=96, text_budget=128):
    clauses = []
    if 'media' in filters:
        media = filters.get('media')
        kinds = [x for x in media if x in ('image', 'video', 'other')] if type(media) is list else []
        names = ({'image': '照片', 'video': '视频', 'other': '其他媒体'} if zh else
                 {'image': 'images', 'video': 'videos', 'other': 'other media'})
        value = ', '.join(names[item] for item in kinds) if kinds else ('未指定' if zh else 'unspecified')
        clauses.append(f'媒体类型：{value}' if zh else f'Media kind: {value}')
    if 'date' in filters:
        date = filters.get('date')
        start = _safe_text(date.get('from')) if type(date) is dict and date.get('from') is not None else None
        end = _safe_text(date.get('to')) if type(date) is dict and date.get('to') is not None else None
        lower = start or ('无下界' if zh else 'no lower bound')
        upper = end or ('无上界' if zh else 'no upper bound')
        clauses.append((f'拍摄日期（含边界）：{lower} 至 {upper}' if zh else
                        f'Capture dates (inclusive): {lower} through {upper}'))
    for facet, label_en, label_zh in (
            ('people', 'People', '人物'),
            ('tags', 'Tags', '标签')):
        if facet not in filters:
            continue
        raw = filters.get(facet)
        selected = _ids(raw, nested=True)
        mode = raw.get('match') if type(raw) is dict else None
        mode_en = 'all' if mode == 'all' else 'any'
        mode_zh = '全部匹配' if mode == 'all' else '任一匹配'
        names = _preview(*_labels(filters, interpretation, facet), zh=zh,
                         label_budget=label_budget)
        count = len(selected)
        clauses.append((f'{label_zh}：{mode_zh}，{count}项（{names}）' if zh else
                        f'{label_en}: {mode_en} of {count} ({names})'))
    if 'locations' in filters:
        selected, labels = _labels(filters, interpretation, 'locations')
        names = _preview(selected, labels, zh=zh, label_budget=label_budget)
        clauses.append((f'地点：{len(selected)}项（{names}）' if zh else
                        f'Locations: {len(selected)} ({names})'))
    if 'text' in filters:
        clauses.append(_text_clause(filters.get('text'), zh=zh, text_budget=text_budget))
    if 'descriptive' in filters:
        raw = filters.get('descriptive')
        concepts = raw.get('concepts', []) if type(raw) is dict else []
        concepts = concepts[:6] if type(concepts) is list else []
        surfaces = [item['surface'] for item in concepts
                    if type(item) is dict and type(item.get('surface')) is str]
        preview = _preview([None] * len(concepts), surfaces, zh=zh, label_budget=label_budget)
        clauses.append((f'描述线索：全部{len(concepts)}项，查找说明或回忆（{preview}）' if zh else
                        f'Descriptive clues: all {len(concepts)}, requiring captions or notes ({preview})'))
    if not clauses:
        return '当前没有查找筛选条件。' if zh else 'No search filters are active.'
    return ('当前筛选条件：' if zh else 'Active search filters: ') + '; '.join(clauses)


def explain_filters(filters, interpretation, language) -> str:
    """Explain active filter slots using only the supplied current snapshot.

    The formatter does not change either input, infer identities, or inspect
    results. Its fixed clauses survive even when previews need truncation.
    """
    filters = filters if type(filters) is dict else {}
    interpretation = interpretation if type(interpretation) is dict else {}
    zh = language == 'zh'
    # Keep ordinary reviewed names intact when the whole summary permits it.
    # Reduce only variable previews, each of which marks truncation, while
    # preserving every fixed filter clause.
    for label_budget, text_budget in (
            (96, 128), (72, 96), (48, 64), (32, 48), (22, 32), (12, 16), (8, 8)):
        result = _render(filters, interpretation, zh=zh,
                         label_budget=label_budget, text_budget=text_budget)
        if len(result.encode('utf-8')) <= _MAX_BYTES:
            return result

    # For malformed oversized fixed fields, discard values rather than shorten
    # them and accidentally describe a different exact filter.
    fields = ('media', 'date', 'people', 'tags', 'locations', 'text', 'descriptive')
    if zh:
        labels = {'media': '媒体类型', 'date': '拍摄日期（含边界）', 'people': '人物',
                  'tags': '标签', 'locations': '地点', 'text': '匹配文字', 'descriptive': '描述线索'}
        clauses = [f'{labels[key]}：已启用' for key in fields if key in filters]
        result = '当前筛选条件：' + '；'.join(clauses)
    else:
        labels = {'media': 'Media kind', 'date': 'Capture dates (inclusive)', 'people': 'People',
                  'tags': 'Tags', 'locations': 'Locations', 'text': 'Text phrase', 'descriptive': 'Descriptive clues'}
        clauses = [f'{labels[key]}: active' for key in fields if key in filters]
        result = 'Active search filters: ' + '; '.join(clauses)
    return result


def no_results_guidance(filters, language) -> str:
    """Give bounded, non-speculative guidance for the current empty search."""
    filters = filters if type(filters) is dict else {}
    zh = language == 'zh'
    if 'date' in filters:
        if zh:
            result = ('没有找到符合条件且已记录拍摄日期的照片或视频。日期搜索会排除未记录拍摄日期的项目。'
                      '说“不限日期”可仅移除日期筛选并保留其他条件。')
        else:
            result = ('No matching photos or videos with a recorded capture date were found. '
                      'Items without a capture date are excluded from date searches. '
                      'Say "any date" to remove only the date filter and keep the other conditions.')
    elif 'text' in filters:
        if zh:
            result = ('没有找到符合条件的照片或视频。'
                      '说“不限内容”可仅移除内容筛选并保留其他条件。')
        else:
            result = ('No matching photos or videos were found. '
                      'Say "any text" to remove only the text filter and keep the other conditions.')
    elif 'descriptive' in filters:
        result = ('没有找到符合全部描述线索的说明或回忆。可以补充线索，或说“不限描述”仅移除描述条件。'
                  if zh else 'No captions or notes matched all descriptive clues. Add another clue, '
                  'or say "any description" to remove only the descriptive conditions.')
    elif zh:
        result = '没有找到符合条件的照片或视频。可以问“现在筛选了哪些条件”查看当前筛选条件。'
    else:
        result = 'No matching photos or videos were found. Ask "what filters are active" to review the current filters.'
    if 'descriptive' in filters:
        result += (' 可按检索条件中的原文说：去掉“某条线索”线索。其余条件会保留。'
                   if zh else ' To drop one descriptive clue, use its exact wording from the search conditions: '
                   'remove the "clue wording" clue. Other conditions stay active.')
    # Fixed strings are already small, but preserve the same hard reply bound
    # if future wording changes exceed the transport limit.
    if len(result.encode('utf-8')) <= _MAX_BYTES:
        return result
    return ('没有找到符合条件的照片或视频。' if zh else
            'No matching photos or videos were found.')

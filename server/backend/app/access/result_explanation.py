"""Closed, read-only explanations for a currently visible search result."""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from .discovery import taken_day
from .search_explanation import explain_filters


_TERMINAL = frozenset('?!。？！.,;:，；：、')
_EN_ORDINALS = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5}
_ZH_ORDINALS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
                '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
_MAX_REPLY_BYTES = 600
_MAX_QUERY_BYTES = 512


def _query_text(value):
    if type(value) is not str:
        return None
    try:
        if len(value.encode('utf-8', errors='strict')) > _MAX_QUERY_BYTES:
            return None
    except UnicodeError:
        return None
    if any(unicodedata.category(char) == 'Cc' for char in value):
        return None
    normalized = unicodedata.normalize('NFKC', value).casefold()
    normalized = ' '.join(normalized.split())
    return normalized.rstrip(''.join(_TERMINAL)).strip()


def _ordinal(value):
    if value.isascii() and value.isdecimal():
        number = int(value)
        return number if 1 <= number <= 10 else None
    return _ZH_ORDINALS.get(value, _EN_ORDINALS.get(value))


def parse_why_result_query(words):
    """Return a closed current-result selection, or None for other text."""
    normalized = _query_text(words)
    if normalized is None:
        return None
    if normalized.startswith('please '):
        normalized = normalized[len('please '):]
    elif normalized.startswith('请'):
        normalized = normalized[len('请'):].strip()

    match = re.fullmatch(
        r'why (?:the )?(first|second|third|fourth|fifth|[1-9]|10) result',
        normalized)
    if match:
        return {'ordinal': _ordinal(match.group(1)), 'kind': None}
    match = re.fullmatch(r'why this (result|photo|video)', normalized)
    if match:
        kind = {'result': None, 'photo': 'image', 'video': 'video'}[match.group(1)]
        return {'ordinal': None, 'kind': kind}

    match = re.fullmatch(
        r'为什么(?:是)?第(10|[1-9]|十|[一二三四五六七八九])'
        r'((?:项|个|张)?(?:结果)|项|个|张)', normalized)
    if match:
        unit = match.group(2)
        kind = 'image' if unit == '张' else None
        return {'ordinal': _ordinal(match.group(1)), 'kind': kind}
    match = re.fullmatch(r'为什么(?:是)?这(张照片|个视频|个结果)', normalized)
    if match:
        kind = {'张照片': 'image', '个视频': 'video', '个结果': None}[match.group(1)]
        return {'ordinal': None, 'kind': kind}
    return None


def _date_reason_matches(reason, item, filters):
    if type(reason) is not dict or reason.get('source') != 'capture_date':
        return False
    if type(filters) is not dict or 'date' not in filters:
        return False
    date_filter = filters.get('date')
    value = reason.get('value')
    if (type(date_filter) is not dict or set(date_filter) != {'from', 'to'}
            or type(value) is not str):
        return False
    try:
        day = date.fromisoformat(value)
        if day.isoformat() != value or taken_day(item.get('taken_at')) != value:
            return False
        lower, upper = date_filter.get('from'), date_filter.get('to')
        parsed_lower = date.fromisoformat(lower) if type(lower) is str else None
        parsed_upper = date.fromisoformat(upper) if type(upper) is str else None
        if ((lower is not None and (type(lower) is not str or parsed_lower.isoformat() != lower)) or
                (upper is not None and (type(upper) is not str or parsed_upper.isoformat() != upper)) or
                (parsed_lower is None and parsed_upper is None)):
            return False
        return ((parsed_lower is None or day >= parsed_lower) and
                (parsed_upper is None or day <= parsed_upper))
    except (TypeError, ValueError):
        return False


def _selected_person_reason(reason, filters):
    if type(reason) is not dict or reason.get('source') != 'reviewed_person':
        return False
    if type(filters) is not dict or 'people' not in filters:
        return False
    people = filters.get('people')
    if type(people) is not dict or set(people) != {'ids', 'match'} or people.get('match') not in ('any', 'all'):
        return False
    ids = people.get('ids')
    ident = reason.get('source_id')
    return (type(ids) is list and bool(ids) and all(type(value) is str for value in ids)
            and type(ident) is str and ident in ids)


def _text_reason_source(reason, zh):
    if type(reason) is not dict or type(reason.get('source')) is not str:
        return None
    labels = {
        'photo_memory': ('照片回忆', 'saved photo memory'),
        'edited_caption': ('编辑说明', 'edited caption'),
        'generated_caption': ('自动生成的说明', 'generated caption'),
    }.get(reason.get('source'))
    return labels[0 if zh else 1] if labels else None


def _safe_utf8_prefix(value, budget):
    encoded = value.encode('utf-8', errors='replace')
    if len(encoded) <= budget:
        return encoded.decode('utf-8')
    suffix = '…'
    room = max(0, budget - len(suffix.encode('utf-8')))
    return encoded[:room].decode('utf-8', errors='ignore') + suffix


def explain_result(item, ordinal, filters, interpretation, language):
    """Explain one item from its current bounded match-reason snapshot only."""
    zh = language == 'zh'
    if type(item) is not dict:
        item = {}
    if type(ordinal) is not int or not 1 <= ordinal <= 10:
        ordinal = 1
    filters = filters if type(filters) is dict else {}
    interpretation = interpretation if type(interpretation) is dict else {}

    kind = item.get('kind')
    if kind not in ('image', 'video', 'other'):
        kind = None
    reasons = item.get('match_reasons')
    if type(reasons) is not list:
        reasons = []
    text_sources = []
    person_match = False
    date_match = False
    for reason in reasons[:43]:
        source = (_text_reason_source(reason, zh)
                  if 'text' in filters or 'descriptive' in filters else None)
        if source and source not in text_sources:
            text_sources.append(source)
        person_match = person_match or _selected_person_reason(reason, filters)
        date_match = date_match or _date_reason_matches(reason, item, filters)

    # The shared formatter owns selected labels and bounds filter previews.
    summary = _safe_utf8_prefix(
        explain_filters(filters, interpretation, language, max_bytes=300), 300)
    pieces = [
        ('第%d项的匹配说明：' % ordinal if zh else
         'Match explanation for result %d: ' % ordinal),
        ('这是当前筛选条件下的匹配项。' if zh else
         'This item matched the current search filters.'),
    ]
    kind_label = ({
        'image': '照片', 'video': '视频', 'other': '其他媒体'
    }.get(kind) if zh else {
        'image': 'photo', 'video': 'video', 'other': 'other media'
    }.get(kind))
    if kind_label:
        pieces.append((' 项目类型为%s。' % kind_label) if zh else
                      (' Item type: %s.' % kind_label))
    if person_match:
        pieces.append(' 人物筛选有已审核匹配记录。' if zh else
                      ' A reviewed-person filter match is recorded.')
    if date_match:
        pieces.append(' 拍摄日期筛选有匹配记录。' if zh else
                      ' A capture-date filter match is recorded.')
    if text_sources:
        names = '、'.join(text_sources) if zh else ', '.join(text_sources)
        pieces.append(('文字匹配证据来源包括：%s。' % names) if zh else
                      (' Text-match evidence includes: %s.' % names))
    elif 'text' in filters or 'descriptive' in filters:
        pieces.append(' 当前项目没有可展示的文字来源详情。' if zh else
                      ' No text-source detail is available for this item.')
    summary = (' ' if not zh else '') + summary
    prefix = ''.join(pieces)
    if len((prefix + summary).encode('utf-8')) > _MAX_REPLY_BYTES:
        # The filter summary already states this generic clause. Preserve all
        # active slots before spending the reply budget on repeated wording.
        del pieces[1]
        prefix = ''.join(pieces)
    room = _MAX_REPLY_BYTES - len(summary.encode('utf-8'))
    return _safe_utf8_prefix(prefix, room) + summary

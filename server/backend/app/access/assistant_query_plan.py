"""Pure, bounded deterministic planning for negotiated assistant search v2.

This module turns one already-authorized entity-resolution result plus user
text into the existing v2 filter shape. It performs no provider, database,
filesystem, or network work and never selects identities outside ``entities``.
"""
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re

from . import discovery as d


@dataclass(frozen=True)
class QueryPlan:
    version: int
    status: str
    filters: dict
    reason: str | None = None


_QUOTE = re.compile(r'[“"]([^“”"]+)[”"]')
_MONTHS = {
    name.casefold(): number for number, names in enumerate((
        ('january', 'jan'), ('february', 'feb'), ('march', 'mar'),
        ('april', 'apr'), ('may',), ('june', 'jun'), ('july', 'jul'),
        ('august', 'aug'), ('september', 'sep', 'sept'),
        ('october', 'oct'), ('november', 'nov'), ('december', 'dec'),
    ), 1) for name in names
}
_MONTH_PATTERN = '|'.join(sorted(_MONTHS, key=len, reverse=True))
_ZH_MONTHS = {'一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6,
              '七': 7, '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12}
_MEDIA = (
    ('video', re.compile(r'影片|视频|\b(?:videos?|movies?)\b', re.I)),
    ('image', re.compile(r'照片|图片|相片|\b(?:photos?|photographs?|pictures?|images?)\b', re.I)),
)
_NEGATION = re.compile(r'不要|没有|排除|除外|删除|不包括|\b(?:not|without|except|excluding|exclude|remove|delete)\b', re.I)
_SEARCH_OPEN = re.compile(
    r'^(?:(?:(?:请|麻烦)(?:你)?\s*)?'
    r'(?:(?:帮我|替我|我想|帮忙|帮我忙|能不能|可以)(?:你)?\s*)?'
    r'(?:(?:找一找|搜一搜|查找|搜索|找|查|搜|看看|看)|给我(?:看看|看)|显示)(?:一下)?|'
    r'(?:(?:please|can you|could you|would you)\s+)?(?:find|search|show)\b'
    r'(?:\s+(?:me|for)\b)?)', re.I)
_REFINE_OPEN = re.compile(
    r'^(?:只看|只要|筛选|再找|再看看|再看|缩小|换成|改成|那么|那|'
    r'refine\b|only\b|filter\b|just\b|what about\b|how about\b|same but\b)', re.I)
_CONNECTORS = re.compile(r'\b(and|or|both|together)\b|和|与|及|或者|或|一起|同时', re.I)
_DATE_ONLY_WORD = re.compile(
    r'^(?:today|yesterday|this\s+week|last\s+week|this\s+month|last\s+month|'
    r'this\s+year|last\s+year|今天|昨天|本周|这周|上周|本月|这个月|這個月|上个月|上個月|今年|去年)$', re.I)
_DATE_ONLY_SHAPE = re.compile(
    rf'^(?:20\d{{2}}(?:年|[-/.](?:\d{{1,2}}(?:[-/.]\d{{1,2}})?))'
    rf'|20\d{{2}}年\d{{1,2}}月?(?:\d{{1,2}}日?)?'
    rf'|20\d{{2}}年(?:十一|十二|十|[一二三四五六七八九])月'
    rf'|(?:去年|今年)(?:(?:1[0-2]|0?[1-9]|十一|十二|十|[一二三四五六七八九])月|{_MONTH_PATTERN})'
    rf'|(?:\d{{1,2}}|十一|十二|十|[一二三四五六七八九])月'
    rf'|{_MONTH_PATTERN}(?:\s+\d{{1,2}}(?:st|nd|rd|th)?(?:[,]?\s+20\d{{2}})?|\s+20\d{{2}})?'
    rf'|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH_PATTERN}(?:[,]?\s+20\d{{2}})?)$', re.I)
_BARE_MEDIA = re.compile(r'^(?:照片|图片|相片|视频|影片|photos?|photographs?|pictures?|images?|videos?|movies?)(?:呢)?$', re.I)
_DATE_MEDIA = re.compile(
    rf'^(?P<date>.+?)\s*(?:的\s*)?(?:照片|图片|相片|视频|影片|photos?|photographs?|pictures?|images?|videos?|movies?)(?:呢)?$', re.I)

# Deliberately closed vocabulary: these are the same bounded scene concepts
# supported by the existing turn planner, with a short bilingual extension.
_SCENES = {
    '海边': ('在海边玩', '在海边'), '海滩': ('在海滩玩', '在海滩'),
    '沙滩': ('在沙滩玩', '在沙滩'), '河边': ('在河边玩', '在河边'),
    '湖边': ('在湖边玩', '在湖边'), '公园': ('在公园玩', '在公园'),
    '草地': ('在草地玩', '在草地'), '山上': ('在山上玩', '在山上'),
    'beach': ('at the beach', 'on the beach', 'beach'),
    'seaside': ('at the seaside', 'by the sea', 'seaside'),
    'river': ('by the river', 'riverside'), 'lake': ('by the lake', 'lakeside'),
    'park': ('in the park', 'at the park'), 'grass': ('on the grass', 'in the grass'),
    'mountain': ('on the mountain', 'in the mountains'),
}


def _clarify(reason, filters=None):
    return QueryPlan(1, 'clarification', dict(filters or {}), reason)


def query_mode(words):
    """Classify only explicit search/refine openings and closed bare followups."""
    if type(words) is not str or not words.strip():
        return None
    value = d.fold(words.strip())
    if _SEARCH_OPEN.match(value):
        return 'search'
    if _REFINE_OPEN.match(value):
        return 'refine'
    value = re.sub(r'[。！？.!?]+$', '', value).strip()
    value = re.sub(r'^(?:请|please)\s*', '', value)
    value = re.sub(r'(?:呢|嗎|吗)$', '', value).strip()
    if _DATE_ONLY_WORD.fullmatch(value) or _BARE_MEDIA.fullmatch(value):
        return 'refine'
    if _DATE_ONLY_SHAPE.fullmatch(value):
        return 'refine'
    media = _DATE_MEDIA.fullmatch(value)
    if media and (_DATE_ONLY_WORD.fullmatch(media.group('date')) or
                  _DATE_ONLY_SHAPE.fullmatch(media.group('date'))):
        return 'refine'
    return None


def _month_bounds(year, month):
    return date(year, month, 1), date(year, month, monthrange(year, month)[1])


def _date_range(start, end):
    return {'from': start.isoformat(), 'to': end.isoformat()}


def _extract_dates(text, today):
    """Return (ranges, residue, error); every date-like span is consumed whole."""
    spans = []
    candidates = []

    def add(match, start, end):
        spans.append(match.span())
        candidates.append((start, end))

    # ISO and Chinese numeric year/month/day forms. A date-shaped but invalid
    # calendar value is an error, never a partially consumed year/month.
    numeric = re.compile(
        r'(?<!\d)(20\d{2})(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?|年(\d{1,2})月?(?:(\d{1,2})日?)?)(?!\d)')
    for match in numeric.finditer(text):
        year = int(match.group(1))
        month = int(match.group(2) or match.group(4) or 1)
        day_value = match.group(3) or match.group(5)
        try:
            if month < 1 or month > 12:
                return [], text, 'invalid_date'
            start, end = _month_bounds(year, month)
            if day_value is not None:
                day = date(year, month, int(day_value))
                start = end = day
        except (ValueError, OverflowError):
            return [], text, 'invalid_date'
        add(match, start, end)

    # Preserve the prior parser's Chinese year-only and Chinese numeral
    # year/month forms as complete spans (including forms such as 2032年九月).
    chinese_year_month = re.compile(r'(?<!\d)(20\d{2})年(十一|十二|十|[一二三四五六七八九])月')
    for match in chinese_year_month.finditer(text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        year, month = int(match.group(1)), _ZH_MONTHS[match.group(2)]
        add(match, *_month_bounds(year, month))
    year_only = re.compile(r'(?<!\d)(20\d{2})年(?!\d)')
    for match in year_only.finditer(text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        year = int(match.group(1))
        add(match, date(year, 1, 1), date(year, 12, 31))

    # English month names: March 5, 2032; March 2032; 5 March 2032.
    english_date = re.compile(
        rf'\b(?:(?P<month1>{_MONTH_PATTERN})\s+(?:(?P<day1>\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+)?(?P<year1>20\d{{2}})|'
        rf'(?P<day2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month2>{_MONTH_PATTERN})[,]?\s+(?P<year2>20\d{{2}}))\b', re.I)
    for match in english_date.finditer(text):
        month = _MONTHS[(match.group('month1') or match.group('month2')).casefold()]
        year = int(match.group('year1') or match.group('year2'))
        raw_day = match.group('day1') or match.group('day2')
        try:
            start, end = _month_bounds(year, month)
            if raw_day:
                start = end = date(year, month, int(raw_day))
        except (ValueError, OverflowError):
            return [], text, 'invalid_date'
        add(match, start, end)

    english_day_month = re.compile(
        rf'\b(?:(?P<month1>{_MONTH_PATTERN})\s+(?P<day1>\d{{1,2}})(?:st|nd|rd|th)?|'
        rf'(?P<day2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month2>{_MONTH_PATTERN}))\b', re.I)
    for match in english_day_month.finditer(text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        month = _MONTHS[(match.group('month1') or match.group('month2')).casefold()]
        raw_day = match.group('day1') or match.group('day2')
        try:
            day = date(today.year, month, int(raw_day))
        except (ValueError, OverflowError):
            return [], text, 'invalid_date'
        add(match, day, day)

    relative_month = re.compile(
        rf'(?P<year>去年|今年|last\s+year|this\s+year)\s*'
        rf'(?:(?P<month_num>1[0-2]|0?[1-9]|十一|十二|十|[一二三四五六七八九])月|'
        rf'(?P<month_name>{_MONTH_PATTERN}))', re.I)
    for match in relative_month.finditer(text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        year = today.year - (1 if match.group('year').casefold() in {'去年', 'last year'} else 0)
        raw_month = match.group('month_num')
        month = (_ZH_MONTHS.get(raw_month, int(raw_month) if raw_month and raw_month.isdecimal() else None)
                 if raw_month else _MONTHS[match.group('month_name').casefold()])
        if month is None or not 1 <= month <= 12:
            return [], text, 'invalid_date'
        add(match, *_month_bounds(year, month))

    # Yearless month names use this year and remain explicit calendar ranges.
    month_only = re.compile(rf'\b(?P<month>{_MONTH_PATTERN})\b', re.I)
    for match in month_only.finditer(text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        month = _MONTHS[match.group('month').casefold()]
        start, end = _month_bounds(today.year, month)
        add(match, start, end)

    chinese_month = re.compile(r'(?<!\d)(十一|十二|十|[一二三四五六七八九])月')
    for match in chinese_month.finditer(text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        add(match, *_month_bounds(today.year, _ZH_MONTHS[match.group(1)]))

    # Preserve numeric month-only forms (for example, "9月") and reject an
    # invalid month as a date condition instead of consuming only its suffix.
    numeric_month = re.compile(r'(?<!\d)(\d{1,2})月')
    for match in numeric_month.finditer(text):
        if any(a <= match.start() < b for a, b in spans):
            continue
        month = int(match.group(1))
        if not 1 <= month <= 12:
            return [], text, 'invalid_date'
        add(match, *_month_bounds(today.year, month))

    relatives = (
        (r'(?<!\w)today(?!\w)|今天', lambda: (today, today)),
        (r'(?<!\w)yesterday(?!\w)|昨天', lambda: (today - timedelta(days=1), today - timedelta(days=1))),
        (r'\bthis\s+week\b|本周|这周', lambda: _week(today)),
        (r'\blast\s+week\b|上周', lambda: _week(today - timedelta(days=7))),
        (r'\bthis\s+month\b|本月|这个月|這個月', lambda: _month_bounds(today.year, today.month)),
        (r'\blast\s+month\b|上个月|上個月', lambda: _previous_month(today)),
        (r'\bthis\s+year\b|今年', lambda: (date(today.year, 1, 1), date(today.year, 12, 31))),
        (r'\blast\s+year\b|去年', lambda: (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))),
    )
    for pattern, bounds in relatives:
        for match in re.finditer(pattern, text, re.I):
            if any(a <= match.start() < b for a, b in spans):
                continue
            add(match, *bounds())

    # Flag orphan day/month syntax and invalid numeric month fragments. This
    # prevents invalid dates from falling through as otherwise successful text.
    if re.search(r'(?<!\d)20\d{2}年\d{1,2}月\d{1,2}日?', text):
        if not any(re.search(r'20\d{2}', text[a:b]) for a, b in spans):
            return [], text, 'invalid_date'
    for orphan in re.finditer(r'\b\d{1,2}(?:st|nd|rd|th)?\s+(?:' + _MONTH_PATTERN + r')\b', text, re.I):
        if not any(start <= orphan.start() and end >= orphan.end() for start, end in spans):
            return [], text, 'invalid_date'

    # A second distinct date constraint is ambiguous. Identical paraphrases can
    # safely collapse to one range.
    unique = list(dict.fromkeys(candidates))
    if len(unique) > 1:
        return [], text, 'conflicting_dates'
    residue = list(text)
    for start, end in spans:
        residue[start:end] = ' ' * (end - start)
    return unique, ''.join(residue), None


def _week(day):
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def _previous_month(day):
    year, month = (day.year - 1, 12) if day.month == 1 else (day.year, day.month - 1)
    return _month_bounds(year, month)


def _strip_prefix(text):
    value = text.strip()
    value = _SEARCH_OPEN.sub(' ', value, count=1)
    value = _REFINE_OPEN.sub(' ', value, count=1)
    return value


def _remove_occurrences(text, labels):
    result = text
    for label in sorted({label for label in labels if type(label) is str and label.strip()}, key=len, reverse=True):
        folded_label = d.fold(label.strip())
        if not folded_label:
            continue
        pattern = re.escape(folded_label)
        if re.fullmatch(r'[a-z0-9_ .-]+', folded_label):
            pattern = r'(?<![a-z0-9_])' + pattern + r'(?![a-z0-9_])'
        result = re.sub(pattern, lambda match: ' ' * len(match.group(0)), result, flags=re.I)
    return result


def _consumed_label(text, residue, labels):
    """A date/media keyword cannot silently double as a reviewed identity."""
    masked = _remove_occurrences(text, labels)
    return any(original != label_mask and original != condition_mask
               for original, label_mask, condition_mask in zip(text, masked, residue))


def _entity_filters(entities):
    if type(entities) is not dict or type(entities.get('groups')) is not dict:
        return None, 'invalid_entities'
    if type(entities.get('ambiguous')) is not bool:
        return None, 'invalid_entities'
    if entities['ambiguous']:
        return None, 'ambiguous_entities'
    enabled = entities.get('enabled')
    if type(enabled) is not list or any(type(value) is not str for value in enabled):
        return None, 'invalid_entities'
    groups = entities['groups']
    normalized = {}
    for facet in ('people', 'tags', 'locations'):
        values = groups.get(facet, [])
        if type(values) is not list or len(values) > 20:
            return None, 'invalid_entities'
        selected = []
        for ident in values:
            if type(ident) is not str or re.fullmatch(r'[1-9][0-9]{0,18}', ident) is None or int(ident) > d.MAX_ID:
                return None, 'invalid_entities'
            if ident not in selected:
                selected.append(ident)
        normalized[facet] = selected
    labels = entities.get('labels', [])
    if type(labels) is not list or any(type(label) is not str for label in labels):
        return None, 'invalid_entities'
    return (normalized, labels, set(enabled)), None


def _valid_previous(filters):
    if type(filters) is not dict or set(filters) - {'people', 'date', 'media', 'tags', 'locations', 'text'}:
        return False
    if 'media' in filters:
        values = filters['media']
        if (type(values) is not list or not 1 <= len(values) <= 3 or
                any(type(value) is not str or value not in ('image', 'video', 'other') for value in values) or
                len(set(values)) != len(values)):
            return False
    if 'date' in filters:
        value = filters['date']
        if type(value) is not dict or set(value) != {'from', 'to'}:
            return False
        parsed = []
        for endpoint in (value['from'], value['to']):
            if endpoint is None:
                parsed.append(None)
                continue
            if type(endpoint) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}', endpoint) is None:
                return False
            try:
                parsed.append(date.fromisoformat(endpoint))
            except ValueError:
                return False
        start, end = parsed
        if start is None and end is None:
            return False
        if start is not None and end is not None and start > end:
            return False
    if 'people' in filters:
        value = filters['people']
        if (type(value) is not dict or set(value) != {'ids', 'match'} or type(value['ids']) is not list
                or value['match'] not in ('any', 'all') or not 1 <= len(value['ids']) <= 20):
            return False
        if any(type(ident) is not str or re.fullmatch(r'[1-9][0-9]{0,18}', ident) is None or
               int(ident) > d.MAX_ID for ident in value['ids']):
            return False
        if len(set(value['ids'])) != len(value['ids']):
            return False
    if 'tags' in filters:
        value = filters['tags']
        if (type(value) is not dict or set(value) != {'ids', 'match'} or type(value['ids']) is not list
                or value['match'] not in ('any', 'all') or not 1 <= len(value['ids']) <= 20):
            return False
        if any(type(ident) is not str or re.fullmatch(r'[1-9][0-9]{0,18}', ident) is None or
               int(ident) > d.MAX_ID for ident in value['ids']):
            return False
        if len(set(value['ids'])) != len(value['ids']):
            return False
    if 'locations' in filters:
        values = filters['locations']
        if (type(values) is not list or not 1 <= len(values) <= 20 or
                any(type(value) is not str or re.fullmatch(r'[1-9][0-9]{0,18}', value) is None
                    or int(value) > d.MAX_ID for value in values) or len(set(values)) != len(values)):
            return False
    if 'text' in filters:
        value = filters['text']
        if type(value) is not str or not value.strip():
            return False
        try:
            if len(value.encode('utf-8', errors='strict')) > 512:
                return False
        except UnicodeError:
            return False
    return True


def plan_query(words, *, now: datetime, entities: dict,
               previous_filters: dict | None, refine: bool) -> QueryPlan:
    """Build a ready plan or a closed clarification from one v2 user query."""
    if type(words) is not str or not words.strip() or not isinstance(now, datetime) or type(refine) is not bool:
        return _clarify('invalid_query')
    try:
        if len(words.encode('utf-8', errors='strict')) > 1024:
            return _clarify('invalid_query')
    except UnicodeError:
        return _clarify('invalid_query')
    entity_data, reason = _entity_filters(entities)
    if reason:
        return _clarify(reason)
    groups, labels, enabled = entity_data
    if refine and previous_filters is None:
        return _clarify('refine_without_context')
    if previous_filters is not None and not _valid_previous(previous_filters):
        return _clarify('invalid_previous_filters')

    query = words.strip()
    quoted = list(_QUOTE.finditer(query))
    quote_removed = _QUOTE.sub(' ', query)
    # Any remaining quote glyph means an unmatched quote; multiple literals
    # are deliberately clarified until a multi-literal contract exists.
    if any(mark in quote_removed for mark in '“”"') or len(quoted) > 1:
        return _clarify('ambiguous_quote', previous_filters if refine else None)
    literal = quoted[0].group(1) if quoted else None
    if literal is not None and not literal.strip():
        return _clarify('empty_literal', previous_filters if refine else None)
    if literal is not None and len(literal.encode('utf-8')) > 512:
        return _clarify('text_too_long', previous_filters if refine else None)

    # Normalize once before any span-based parsing so all later offsets refer
    # to this same string. The quoted literal remains byte-for-byte as entered.
    outside = d.fold(quote_removed)
    # Content introducers are syntax, not content. Quoted words stay opaque.
    outside = re.sub(r'包含|含有|關於|关于|内容|內容|\b(?:containing|contains|about|with the words)\b', ' ', outside, flags=re.I)
    outside = _strip_prefix(outside)

    today = now.date()
    date_surface = outside
    dates, outside, date_error = _extract_dates(date_surface, today)
    if date_error:
        return _clarify(date_error, previous_filters if refine else None)
    if dates and _consumed_label(date_surface, outside, labels):
        return _clarify('ambiguous_date_entity', previous_filters if refine else None)
    if dates and 'date' not in enabled:
        return _clarify('date_unavailable', previous_filters if refine else None)

    media_hits = []
    for kind, pattern in _MEDIA:
        if pattern.search(outside):
            media_hits.append(kind)
            residue = pattern.sub(lambda match: ' ' * len(match.group(0)), outside)
            if _consumed_label(outside, residue, labels):
                return _clarify('ambiguous_media_entity', previous_filters if refine else None)
            outside = residue
    if len(set(media_hits)) > 1:
        return _clarify('conflicting_media', previous_filters if refine else None)

    # Preserve exact ID groups returned by the authorized resolver. Do not
    # derive, guess, or accept an ID from user text or a future model.
    outside = _remove_occurrences(outside, labels)
    if _NEGATION.search(outside):
        return _clarify('unsupported_negation', previous_filters if refine else None)

    people, tags, locations = (groups[name] for name in ('people', 'tags', 'locations'))
    # Relation words are meaningful only when they connect two resolved people.
    relation_tokens = [match.group(0).casefold() for match in _CONNECTORS.finditer(outside)]
    together = any(token in {'both', 'together', '一起', '同时'} for token in relation_tokens)
    has_and = any(token in {'and', '和', '与', '及'} for token in relation_tokens)
    has_or = any(token in {'or', '或者', '或'} for token in relation_tokens)
    if has_and and has_or:
        return _clarify('conflicting_people_mode', previous_filters if refine else None)
    if (together or has_and or has_or) and len(people) < 2:
        return _clarify('incomplete_people_relation', previous_filters if refine else None)
    people_mode = 'all' if together or has_and else 'any'
    outside = _CONNECTORS.sub(' ', outside)

    text_filter = literal
    if text_filter is None:
        folded = d.fold(outside)
        for scene, phrases in sorted(_SCENES.items(), key=lambda pair: max(map(len, pair[1])), reverse=True):
            for phrase in phrases:
                phrase_folded = d.fold(phrase)
                if re.fullmatch(r'[a-z ]+', phrase_folded):
                    pattern = r'(?<![a-z])' + re.escape(phrase_folded) + r'(?![a-z])'
                else:
                    pattern = re.escape(phrase_folded)
                    if re.fullmatch(r'[\u3400-\u9fff]+', phrase_folded):
                        # Chinese scene forms are complete phrases. In
                        # particular, "at the beach photographed" must not
                        # collapse to the recognized prefix "at the beach".
                        pattern = re.escape(phrase_folded) + r'(?:的)?(?![\u3400-\u9fff])'
                match = re.search(pattern, folded)
                if match:
                    text_filter = scene
                    outside = outside[:match.start()] + ' ' * (match.end() - match.start()) + outside[match.end():]
                    break
            if text_filter is not None:
                break
    if text_filter is None:
        # Retain the old explicit Chinese play-scene syntax, but require the
        # entire remaining condition to be exactly "在<scene>玩/游玩(的)".
        # This keeps arbitrary unknown suffixes from being consumed as a
        # recognized scene while preserving literal, bounded scene wording.
        play_surface = re.sub(r'[\s。！？.!?、，,：:]+', '', outside)
        play = re.fullmatch(r'在([^不要没有排除删除]{1,40}?)(?:游玩|玩)(?:的)?', play_surface)
        if play:
            text_filter = play.group(1)
            outside = ' '
    if text_filter is not None and 'text' not in enabled:
        return _clarify('text_unavailable', previous_filters if refine else None)

    if people and 'people' not in enabled:
        return _clarify('people_unavailable', previous_filters if refine else None)
    if tags and 'tags' not in enabled:
        return _clarify('tags_unavailable', previous_filters if refine else None)
    if locations and 'locations' not in enabled:
        return _clarify('locations_unavailable', previous_filters if refine else None)

    # Only a small closed vocabulary of grammatical residue is accepted.
    outside = re.sub(r'\b(?:the|a|an|of|in|on|at|by|from|during|taken|take|photographed|photo|photos|picture|pictures|image|images|please|me|for|and|or)\b', ' ', outside, flags=re.I)
    outside = re.sub(r'请|麻烦|帮忙|帮我|替我|我想|能不能|可以|一下|的|那些|一些|里面|中|所拍|找|搜索|查找|查|搜|看看|看|显示|照片|图片|相片|视频|影片|有关|包含|关于|在|于|年|月|日|里|上|下|呢|吗|么|？|\?|！|!|。|\.|、|，|,|：|:|\s+', ' ', outside, flags=re.I)
    if outside.strip():
        return _clarify('unsupported_condition', previous_filters if refine else None)

    filters = dict(previous_filters) if refine and previous_filters is not None else {}
    if media_hits:
        filters['media'] = ['image' if media_hits[-1] == 'image' else 'video']
    elif not refine and not people and not tags and not locations and literal is None and text_filter is None and not dates:
        # A bare “find” has no meaningful constraint and should not expose a
        # catalogue-sized result set.
        return _clarify('missing_conditions')
    if dates:
        filters['date'] = _date_range(*dates[0])
    if people:
        filters['people'] = {'ids': people, 'match': people_mode}
    if tags:
        filters['tags'] = {'ids': tags, 'match': 'any'}
    if locations:
        filters['locations'] = locations
    if text_filter is not None:
        filters['text'] = text_filter
    return QueryPlan(1, 'ready', filters)

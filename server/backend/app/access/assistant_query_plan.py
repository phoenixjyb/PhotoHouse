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
# Scope English word boundaries to ASCII: Python's Unicode word boundary
# treats Han and Latin letters as one word ("videos的", "找September").
# Only boundary assertions use ASCII mode; the surrounding query, labels and
# quoted literals retain Unicode handling and their original text.
_MEDIA = (
    ('video', re.compile(r'影片|视频|(?a:\b)(?:videos?|movies?)(?a:\b)', re.I)),
    ('image', re.compile(r'照片|图片|相片|(?a:\b)(?:photos?|photographs?|pictures?|images?)(?a:\b)', re.I)),
)
_NEGATION = re.compile(r'不要|没有|排除|除外|删除|不包括|(?a:\b)(?:not|without|except|excluding|exclude|remove|delete)(?a:\b)', re.I)
_SEARCH_OPEN = re.compile(
    r'^(?:'
    r'(?:(?:please\s+)?(?:i(?:\s+am|[\x27’]m)\s+looking\s+for|'
    r'i\s+would\s+like\s+to\s+see|do\s+we\s+have|can\s+you\s+pull\s+up|'
    r'look\s+for)(?a:\b))|'
    r'(?:(?:(?:请|麻烦)(?:你)?\s*)?'
    r'(?:(?:帮我|替我|我想|帮忙|帮我忙|能不能|可以)(?:你)?\s*)?'
    r'(?:(?:找一找|搜一搜|查找|搜索|找|查|搜|看看|看)|给我(?:看看|看)|显示)(?:一下)?|'
    r'(?:(?:please|can you|could you|would you)\s+)?(?:find|search|show)(?a:\b)'
    r'(?:\s+(?:me|for)(?a:\b))?)|'
    r'(?:(?:请)?(?:我想看看|我想看|我想找|想找|想看|还有没有|有没有))'
    r')', re.I)
_REFINE_OPEN = re.compile(
    r'^(?:只看|只要|筛选|再找|再看看|再看|缩小|换成|改成|那么|那|'
    r'refine(?a:\b)|only(?a:\b)|filter(?a:\b)|just(?a:\b)|what about(?a:\b)|how about(?a:\b)|same but(?a:\b))', re.I)
_CONNECTORS = re.compile(r'(?a:\b)(and|or|both|together)(?a:\b)|和|与|及|或者|或|一起|同时', re.I)
_CONTENT_INTRO = re.compile(
    r'包含|含有|關於|关于|内容|內容|(?a:\b)(?:containing|contains|about|with the words)(?a:\b)', re.I)
_CONTENT_ACTION = re.compile(
    r'(?:^|[\s,，;；。.!！?？]|(?a:\b)(?:and|then|also)\s+)'
    r'(?:(?:please|kindly|(?:can|could|would)\s+you)\s+){0,2}'
    r'(?:open|show|share|delete|remove|play|edit|save|send|find|search)(?a:\b)|'
    r'(?:^|[\s,，;；。.!！?？]|(?:然后|接着|并且|并|再)\s*)'
    r'(?:(?:请|麻烦你?|帮我|替我|给我|能不能|能否|可以|帮忙)\s*){0,2}'
    r'(?:打开|展示|分享|删除|移除|播放|编辑|保存|发送|查找|搜索)', re.I)

_CONTENT_MEDIA_TAIL = re.compile(
    r'(?:(?:\s+of)?\s+|\s*的\s*)(?P<media>videos?|movies?|photos?|photographs?|pictures?|images?|影片|视频|照片|图片|相片)\s*$', re.I)
_DATE_ONLY_WORD = re.compile(
    r'^(?:today|yesterday|this\s+week|last\s+week|this\s+month|last\s+month|'
    r'this\s+year|last\s+year|今天|昨天|本周|这周|上周|本月|这个月|這個月|上个月|上個月|今年|去年)$', re.I)
_DATE_ONLY_SHAPE = re.compile(
    rf'^(?:(?:19|20)\d{{2}}(?:年?|[-/.](?:\d{{1,2}}(?:[-/.]\d{{1,2}})?))'
    rf'|(?:19|20)\d{{2}}年\d{{1,2}}月?(?:\d{{1,2}}日?)?'
    rf'|(?:19|20)\d{{2}}年(?:十一|十二|十|[一二三四五六七八九])月'
    rf'|(?:去年|今年)(?:(?:1[0-2]|0?[1-9]|十一|十二|十|[一二三四五六七八九])月|(?:{_MONTH_PATTERN}))'
    rf'|(?:\d{{1,2}}|十一|十二|十|[一二三四五六七八九])月'
    rf'|(?:{_MONTH_PATTERN})(?:\s+\d{{1,2}}(?:st|nd|rd|th)?(?:[,]?\s+(?:19|20)\d{{2}})?|\s+(?:19|20)\d{{2}})?'
    rf'|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{_MONTH_PATTERN})(?:[,]?\s+(?:19|20)\d{{2}})?)$', re.I)
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
    # A complete explicit range is also a closed follow-up. A fixed civil
    # date suffices here because supported range endpoints are explicit.
    if len(value) <= 1024 and re.search(r'(?a:\b)(?:to|through|between)(?a:\b)|到|至|[–—]', value):
        ranges, residue, error = _extract_dates(value, date(2000, 1, 1))
        if ranges and not error and not residue.strip():
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

    def overlaps(match):
        return any(a < match.end() and match.start() < b for a, b in spans)

    def month_bounds(year, month):
        if not 1 <= month <= 12:
            raise ValueError('invalid month')
        return _month_bounds(year, month)

    # Consume supported ranges before individual dates, so both endpoints
    # become one inclusive interval. Omitted years inherit only from an
    # explicit adjacent endpoint in the documented shortened forms.
    range_specs = (
        (re.compile(r'(?a:\b)from\s+(?P<a>(?:19|20)\d{2}-\d{2}-\d{2})\s+to\s+(?P<b>(?:19|20)\d{2}-\d{2}-\d{2})(?a:\b)', re.I), 'iso'),
        (re.compile(r'(?<![0-9a-z_])(?P<a>(?:19|20)\d{2}-\d{2}-\d{2})\s*(?:to|through|至|到|[-–—])\s*(?P<b>(?:19|20)\d{2}-\d{2}-\d{2})(?!\d)', re.I), 'iso'),
        (re.compile(r'(?a:\b)from\s+(?P<m1>' + _MONTH_PATTERN + r')\s+to\s+(?P<m2>' + _MONTH_PATTERN + r')\s+(?P<y2>(?:19|20)\d{2})(?a:\b)', re.I), 'english_shared'),
        (re.compile(r'(?a:\b)from\s+(?P<m1>' + _MONTH_PATTERN + r')\s+(?P<y1>(?:19|20)\d{2})\s+to\s+(?P<m2>' + _MONTH_PATTERN + r')\s+(?P<y2>(?:19|20)\d{2})(?a:\b)', re.I), 'english'),
        (re.compile(r'(?a:\b)between\s+(?P<m1>' + _MONTH_PATTERN + r')\s+(?P<y1>(?:19|20)\d{2})\s+and\s+(?P<m2>' + _MONTH_PATTERN + r')\s+(?P<y2>(?:19|20)\d{2})(?a:\b)', re.I), 'english'),
        (re.compile(r'(?:从\s*)?(?<!\d)(?P<y1>(?:19|20)\d{2})年(?P<m1>\d{1,2})月(?P<d1>\d{1,2})日?\s*(?:到|至)\s*(?P<y2>(?:19|20)\d{2})年(?P<m2>\d{1,2})月(?P<d2>\d{1,2})日?(?!\d)'), 'numeric_days'),
        (re.compile(r'(?:从\s*)?(?<!\d)(?P<y1>(?:19|20)\d{2})年(?P<m1>\d{1,2})月\s*(?:到|至)\s*(?P<y2>(?:19|20)\d{2})年(?P<m2>\d{1,2})月(?!\d)'), 'numeric_months'),
        (re.compile(r'(?:从\s*)?(?<!\d)(?P<y1>(?:19|20)\d{2})年(?P<m1>\d{1,2})月\s*(?:到|至)\s*(?P<m2>\d{1,2})月(?!\d)'), 'numeric_shared'),
    )
    for pattern, kind in range_specs:
        for match in pattern.finditer(text):
            if overlaps(match):
                continue
            try:
                if kind == 'iso':
                    start, end = date.fromisoformat(match.group('a')), date.fromisoformat(match.group('b'))
                elif kind in ('english', 'english_shared'):
                    y1 = int(match.groupdict().get('y1') or match.group('y2'))
                    y2 = int(match.group('y2'))
                    start = month_bounds(y1, _MONTHS[match.group('m1').casefold()])[0]
                    end = month_bounds(y2, _MONTHS[match.group('m2').casefold()])[1]
                elif kind == 'numeric_days':
                    start = date(int(match.group('y1')), int(match.group('m1')), int(match.group('d1')))
                    end = date(int(match.group('y2')), int(match.group('m2')), int(match.group('d2')))
                else:
                    y1 = int(match.group('y1'))
                    y2 = int(match.groupdict().get('y2') or y1)
                    start = month_bounds(y1, int(match.group('m1')))[0]
                    end = month_bounds(y2, int(match.group('m2')))[1]
            except (ValueError, OverflowError, KeyError):
                return [], text, 'invalid_date'
            if start > end:
                return [], text, 'invalid_date'
            add(match, start, end)

    # Do not let a truncated range fall through as one endpoint.
    for match in re.finditer(r'(?a:\b)(?:from|between)(?a:\b)|从', text, re.I):
        if overlaps(match):
            continue
        tail = text[match.start():]
        connector = r'(?a:\b)to(?a:\b)' if re.match(r'(?a:\b)from(?a:\b)', match.group(), re.I) else r'(?a:\b)and(?a:\b)' if re.match(r'(?a:\b)between(?a:\b)', match.group(), re.I) else r'到|至'
        if re.search(connector, tail, re.I) and re.search(r'(?:19|20)\d{2}|(?a:\b)(?:' + _MONTH_PATTERN + r')(?a:\b)|\d{1,2}月', tail, re.I):
            return [], text, 'invalid_date'

    # ISO and Chinese numeric year/month/day forms. A date-shaped but invalid
    # calendar value is an error, never a partially consumed year/month.
    numeric = re.compile(
        r'(?<!\d)((?:19|20)\d{2})(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?|年(\d{1,2})月?(?:(\d{1,2})日?)?)(?!\d)')
    for match in numeric.finditer(text):
        if overlaps(match):
            continue
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
    chinese_year_month = re.compile(r'(?<!\d)((?:19|20)\d{2})年(十一|十二|十|[一二三四五六七八九])月')
    for match in chinese_year_month.finditer(text):
        if overlaps(match):
            continue
        year, month = int(match.group(1)), _ZH_MONTHS[match.group(2)]
        add(match, *_month_bounds(year, month))
    year_only = re.compile(r'(?<!\d)((?:19|20)\d{2})年(?!\d)')
    for match in year_only.finditer(text):
        if overlaps(match):
            continue
        year = int(match.group(1))
        add(match, date(year, 1, 1), date(year, 12, 31))

    bare_year = re.compile(r'(?<!\d)((?:19|20)\d{2})(?!\d)')
    for match in bare_year.finditer(text):
        if overlaps(match):
            continue
        before = text[max(0, match.start() - 32):match.start()]
        if re.search(r'(?:(?a:\b)(?:' + _MONTH_PATTERN + r')\s+(?:\d{1,2}(?:st|nd|rd|th)?[,]?\s+)?|(?a:\b)\d{1,2}(?:st|nd|rd|th)?\s+(?:' + _MONTH_PATTERN + r')[,]?\s+)$', before, re.I):
            continue
        year = int(match.group(1))
        add(match, date(year, 1, 1), date(year, 12, 31))

    # English month names: March 5, 2032; March 2032; 5 March 2032.
    english_date = re.compile(
        rf'(?a:\b)(?:(?P<month1>(?:{_MONTH_PATTERN}))\s+(?:(?P<day1>\d{{1,2}})(?:st|nd|rd|th)?[,]?\s+)?(?P<year1>(?:19|20)\d{{2}})|'
        rf'(?P<day2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month2>(?:{_MONTH_PATTERN}))[,]?\s+(?P<year2>(?:19|20)\d{{2}}))(?a:\b)', re.I)
    for match in english_date.finditer(text):
        if overlaps(match):
            continue
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
        rf'(?a:\b)(?:(?P<month1>(?:{_MONTH_PATTERN}))\s+(?P<day1>\d{{1,2}})(?:st|nd|rd|th)?|'
        rf'(?P<day2>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month2>(?:{_MONTH_PATTERN})))(?a:\b)', re.I)
    for match in english_day_month.finditer(text):
        if overlaps(match):
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
        rf'(?P<month_name>(?:{_MONTH_PATTERN})))', re.I)
    for match in relative_month.finditer(text):
        if overlaps(match):
            continue
        year = today.year - (1 if match.group('year').casefold() in {'去年', 'last year'} else 0)
        raw_month = match.group('month_num')
        month = (_ZH_MONTHS.get(raw_month, int(raw_month) if raw_month and raw_month.isdecimal() else None)
                 if raw_month else _MONTHS[match.group('month_name').casefold()])
        if month is None or not 1 <= month <= 12:
            return [], text, 'invalid_date'
        add(match, *_month_bounds(year, month))

    # Yearless month names use this year and remain explicit calendar ranges.
    month_only = re.compile(rf'(?a:\b)(?P<month>(?:{_MONTH_PATTERN}))(?a:\b)', re.I)
    for match in month_only.finditer(text):
        if overlaps(match):
            continue
        month = _MONTHS[match.group('month').casefold()]
        start, end = _month_bounds(today.year, month)
        add(match, start, end)

    chinese_month = re.compile(r'(?<!\d)(十一|十二|十|[一二三四五六七八九])月')
    for match in chinese_month.finditer(text):
        if overlaps(match):
            continue
        add(match, *_month_bounds(today.year, _ZH_MONTHS[match.group(1)]))

    # Preserve numeric month-only forms (for example, "9月") and reject an
    # invalid month as a date condition instead of consuming only its suffix.
    numeric_month = re.compile(r'(?<!\d)(\d{1,2})月')
    for match in numeric_month.finditer(text):
        if overlaps(match):
            continue
        month = int(match.group(1))
        if not 1 <= month <= 12:
            return [], text, 'invalid_date'
        add(match, *_month_bounds(today.year, month))

    relatives = (
        (r'(?<![a-z0-9_])today(?![a-z0-9_])|今天', lambda: (today, today)),
        (r'(?<![a-z0-9_])yesterday(?![a-z0-9_])|昨天', lambda: (today - timedelta(days=1), today - timedelta(days=1))),
        (r'(?a:\b)this\s+week(?a:\b)|本周|这周', lambda: _week(today)),
        (r'(?a:\b)last\s+week(?a:\b)|上周', lambda: _week(today - timedelta(days=7))),
        (r'(?a:\b)this\s+month(?a:\b)|本月|这个月|這個月', lambda: _month_bounds(today.year, today.month)),
        (r'(?a:\b)last\s+month(?a:\b)|上个月|上個月', lambda: _previous_month(today)),
        (r'(?a:\b)this\s+year(?a:\b)|今年', lambda: (date(today.year, 1, 1), date(today.year, 12, 31))),
        (r'(?a:\b)last\s+year(?a:\b)|去年', lambda: (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31))),
    )
    for pattern, bounds in relatives:
        for match in re.finditer(pattern, text, re.I):
            if overlaps(match):
                continue
            add(match, *bounds())

    # Flag orphan day/month syntax and invalid numeric month fragments. This
    # prevents invalid dates from falling through as otherwise successful text.
    if re.search(r'(?<!\d)20\d{2}年\d{1,2}月\d{1,2}日?', text):
        if not any(re.search(r'20\d{2}', text[a:b]) for a, b in spans):
            return [], text, 'invalid_date'
    for orphan in re.finditer(r'(?a:\b)\d{1,2}(?:st|nd|rd|th)?\s+(?:' + _MONTH_PATTERN + r')(?a:\b)', text, re.I):
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
    # Keep offsets aligned for the reviewed-label collision check.
    value = re.sub(r'^\s+', lambda match: ' ' * len(match.group(0)), text)
    leading = len(value) - len(value.lstrip())
    prefix = value[:leading]
    value = value[leading:]
    value = _SEARCH_OPEN.sub(lambda match: ' ' * len(match.group(0)), value, count=1)
    value = _REFINE_OPEN.sub(lambda match: ' ' * len(match.group(0)), value, count=1)
    value = prefix + value
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


def _grammar_residue(text):
    """Remove only the same closed syntax words used by the query parser."""
    text = re.sub(r'(?a:\b)(?:the|a|an|of|in|on|at|by|from|during|taken|take|photographed|photo|photos|picture|pictures|image|images|please|me|for|and|or)(?a:\b)', ' ', text, flags=re.I)
    text = re.sub(r'请|麻烦|帮忙|帮我|替我|我想|能不能|可以|一下|的|那些|一些|里面|中|所拍|找|搜索|查找|查|搜|看看|看|显示|照片|图片|相片|视频|影片|有关|包含|关于|在|于|年|月|日|里|上|下|呢|吗|么|？|\?|！|!|。|\.|、|，|,|：|:|\s+', ' ', text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip()


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

    # Bare "content" nouns remain legacy syntax (for example 不限内容).
    # They do not independently introduce a new unquoted literal.
    content_cues = [match for match in _CONTENT_INTRO.finditer(quote_removed)
                    if match.group(0) not in {'内容', '內容'}]
    content_tail = None
    if len(content_cues) == 1 and literal is None:
        content_tail = quote_removed[content_cues[0].end():].strip()
        content_tail = re.sub(r'^[\s,，;；:：]+', '', content_tail)
        content_tail = re.sub(r'[\s,，;；。.!！?？:：]+$', '', content_tail).strip()

    # Normalize once before any span-based parsing so all later offsets refer
    # to this same string. The quoted literal remains byte-for-byte as entered.
    outside = d.fold(quote_removed)
    # Content introducers are syntax, not content. Quoted words stay opaque.
    cue_residue = _CONTENT_INTRO.sub(lambda match: ' ' * len(match.group(0)), quote_removed)
    cue_labels = [d.fold(match.group(0)) for match in content_cues]
    if (content_cues and (_consumed_label(quote_removed, cue_residue, labels) or
            any(cue and cue in d.fold(label.strip()) for cue in cue_labels
                for label in labels if label.strip()))):
        return _clarify('ambiguous_entities', previous_filters if refine else None)
    outside = _CONTENT_INTRO.sub(lambda match: ' ' * len(match.group(0)), outside)
    prefixed = outside
    outside = _strip_prefix(outside)
    if _consumed_label(prefixed, outside, labels):
        return _clarify('ambiguous_entities', previous_filters if refine else None)

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

    # Multiple content introducers make the literal span unclear. This check
    # follows date, media, entity and negation validation, so those guards stay
    # authoritative before any unquoted phrase is accepted.
    if len(content_cues) > 1 and literal is None:
        return _clarify('unsupported_condition', previous_filters if refine else None)

    text_filter = literal
    if text_filter is None and not content_cues:
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
    if text_filter is None and not content_cues:
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

    if len(content_cues) == 1 and literal is None:
        if not content_tail:
            return _clarify('empty_literal', previous_filters if refine else None)
        if _CONTENT_ACTION.search(content_tail):
            return _clarify('unsupported_condition', previous_filters if refine else None)
        candidate = content_tail
        folded_candidate = d.fold(candidate)
        if len(folded_candidate) != len(candidate):
            return _clarify('unsupported_condition', previous_filters if refine else None)
        dates_in_candidate, _, date_error = _extract_dates(folded_candidate, today)
        if date_error:
            return _clarify(date_error, previous_filters if refine else None)
        if dates_in_candidate or _remove_occurrences(folded_candidate, labels) != folded_candidate:
            return _clarify('unsupported_condition', previous_filters if refine else None)
        media_spans = [match.span() for _, pattern in _MEDIA for match in pattern.finditer(folded_candidate)]
        if media_spans:
            suffix = _CONTENT_MEDIA_TAIL.search(folded_candidate)
            if (suffix is None or not media_spans or
                    any(start < suffix.start('media') or end > len(folded_candidate)
                        for start, end in media_spans)):
                return _clarify('unsupported_condition', previous_filters if refine else None)
            candidate = candidate[:suffix.start()].rstrip(' \t,，;；:：')
            folded_candidate = d.fold(candidate)
            if not candidate:
                return _clarify('empty_literal', previous_filters if refine else None)
        try:
            if len(candidate.encode('utf-8', errors='strict')) > 512:
                return _clarify('text_too_long', previous_filters if refine else None)
        except UnicodeError:
            return _clarify('invalid_query', previous_filters if refine else None)
        # A content cue authorizes only the tail as literal text. Parsed
        # filters before the cue remain separate; if other unconsumed words or
        # hard-filter spans remain, do not absorb them into the literal.
        if (_grammar_residue(folded_candidate) and
                _grammar_residue(outside) == _grammar_residue(folded_candidate)):
            text_filter = candidate
            outside = ' '

    if text_filter is not None and 'text' not in enabled:
        return _clarify('text_unavailable', previous_filters if refine else None)

    # Only a small closed vocabulary of grammatical residue is accepted.
    outside = _grammar_residue(outside)
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

"""Pure, editable story-outline scaffolding for caller-authorized media."""

from __future__ import annotations

import re


THEMES = {
    'trip': {'zh': '旅途主题', 'en': 'Travel theme'},
    'growing_up': {'zh': '成长主题', 'en': 'Growing up theme'},
    'birthday': {'zh': '生日主题', 'en': 'Birthday theme'},
    'grandparents': {'zh': '祖辈主题', 'en': 'Grandparents theme'},
    'year_in_review': {'zh': '年度回顾主题', 'en': 'Year in review theme'},
    'everyday': {'zh': '日常主题', 'en': 'Everyday theme'},
}
_ID = re.compile(r'\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z', re.ASCII)
_ITEM_KEYS = {'id', 'kind', 'taken_at', 'date_hint', 'evidence'}
_EVIDENCE_KEYS = {'id', 'source', 'text'}
_CHAPTER_LIMIT = 4


def _text(value, *, limit, field, allow_empty=True):
    if not isinstance(value, str) or (not allow_empty and not value):
        raise ValueError(f'{field} must be a string')
    try:
        encoded = value.encode('utf-8')
    except UnicodeEncodeError:
        raise ValueError(f'{field} contains invalid Unicode') from None
    if len(encoded) > limit or '\x00' in value:
        raise ValueError(f'{field} exceeds its limit or contains invalid characters')
    return value


def _identifier(value, field):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f'{field} is invalid')
    return value


def _date_hint(value, depth=0):
    """Accept only bounded JSON-like hints; never interpret them as confirmed dates."""
    if value is None:
        return
    if depth > 3:
        raise ValueError('date_hint is too deeply nested')
    if isinstance(value, dict):
        if len(value) > 16:
            raise ValueError('date_hint has too many fields')
        for key, child in value.items():
            _text(key, limit=128, field='date_hint key', allow_empty=False)
            _date_hint(child, depth + 1)
    elif isinstance(value, list):
        if len(value) > 16:
            raise ValueError('date_hint has too many values')
        for child in value:
            _date_hint(child, depth + 1)
    elif isinstance(value, str):
        _text(value, limit=512, field='date_hint value')
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError('date_hint must contain JSON-like values')


def _validate_items(items):
    if not isinstance(items, list) or len(items) > 24:
        raise ValueError('items must be a list of at most 24 entries')
    seen_asset_ids = set()
    seen_evidence_ids = set()
    cleaned = []
    for item in items:
        if not isinstance(item, dict) or set(item) != _ITEM_KEYS:
            raise ValueError('each item must have the supported media fields')
        asset_id = _identifier(item['id'], 'item id')
        if asset_id in seen_asset_ids:
            raise ValueError('item ids must be unique')
        seen_asset_ids.add(asset_id)
        if not isinstance(item['kind'], str) or item['kind'] not in {'image', 'video'}:
            raise ValueError('item kind must be image or video')
        taken_at = item['taken_at']
        if taken_at is not None:
            _text(taken_at, limit=128, field='taken_at', allow_empty=False)
        _date_hint(item['date_hint'])
        evidence = item['evidence']
        if not isinstance(evidence, list) or len(evidence) > 12:
            raise ValueError('evidence must be a list of at most 12 entries')
        clean_evidence = []
        for entry in evidence:
            if not isinstance(entry, dict) or set(entry) != _EVIDENCE_KEYS:
                raise ValueError('each evidence entry must have the supported fields')
            evidence_id = _identifier(entry['id'], 'evidence id')
            if evidence_id in seen_evidence_ids:
                raise ValueError('evidence ids must be unique')
            seen_evidence_ids.add(evidence_id)
            if not isinstance(entry['source'], str) or entry['source'] not in {'family', 'ai'}:
                raise ValueError('evidence source must be family or ai')
            _text(entry['text'], limit=8192, field='evidence text')
            clean_evidence.append(evidence_id)
        cleaned.append((asset_id, clean_evidence))
    return cleaned


def _role(index, total):
    if index == 0:
        return 'opening'
    if index == total - 1:
        return 'ending'
    return 'middle'


def build_outline(items, *, theme, language, title=''):
    """Build an editable outline without IO, inference, or claims from evidence.

    ``items`` must already be authorized and ordered by the caller. Evidence IDs
    are returned only as references for the reader; their text is never copied
    into generated narration.
    """
    if not isinstance(theme, str) or theme not in THEMES:
        raise ValueError('unsupported theme')
    if not isinstance(language, str) or language not in {'zh', 'en'}:
        raise ValueError('language must be zh or en')
    title = _text(title, limit=640, field='title')
    cleaned = _validate_items(items)
    theme_label = THEMES[theme][language]
    if not title:
        title = '家庭故事草稿' if language == 'zh' else 'Family story draft'

    if language == 'zh':
        role_labels = {'opening': '回看开始', 'middle': '继续回看', 'ending': '留下结尾'}
        narrations = {
            'opening': '从这里开始，回看选中的这些片段。',
            'middle': '继续沿着这些画面，补充你记得的细节。',
            'ending': '留下一段家人自己的话，为这次回顾收尾。',
        }
        questions = [
            '你想用什么事件或主题来理解这些片段？',
            '这些片段与什么地点、日期或时间范围有关？不确定的部分可以留空。',
            '家人希望记住哪些意义、感受或细节？',
        ]
    else:
        role_labels = {'opening': 'A place to begin', 'middle': 'Continue the story', 'ending': 'A place to close'}
        narrations = {
            'opening': 'Begin by looking back at the selected moments.',
            'middle': 'Continue with these images and add details you remember.',
            'ending': 'Leave space for the family’s own words to close this review.',
        }
        questions = [
            'What event or theme, if any, helps make sense of these moments?',
            'What place, date, or time range is relevant? Leave uncertain details open.',
            'What meaning, feeling, or detail would the family like to remember?',
        ]

    groups = [cleaned[i:i + _CHAPTER_LIMIT] for i in range(0, len(cleaned), _CHAPTER_LIMIT)]
    chapters = []
    for index, group in enumerate(groups):
        role = _role(index, len(groups))
        evidence_ids = []
        seen_evidence = set()
        for _, refs in group:
            for evidence_id in refs:
                if evidence_id not in seen_evidence:
                    evidence_ids.append(evidence_id)
                    seen_evidence.add(evidence_id)
        if language == 'zh':
            chapter_title = f'{theme_label} · {role_labels[role]}'
        else:
            chapter_title = f'{theme_label} · {role_labels[role]}'
        chapters.append({
            'id': f'chapter-{index + 1}',
            'title': chapter_title,
            'narration': narrations[role],
            'asset_ids': [asset_id for asset_id, _ in group],
            'evidence_ids': evidence_ids,
        })

    return {
        'title': title,
        'theme': theme,
        'language': language,
        'generator': 'evidence_outline',
        'needs_review': True,
        'chapters': chapters,
        'questions': questions,
    }

"""Bounded, server-owned followups over the latest displayed memory cards."""
from dataclasses import dataclass
import re
import sqlite3
import uuid

from .assistant_memory_discovery import MAX_RESULTS
from .assistant_saved_memory_tool import (AssistantSavedMemoryOutcome,
                                         _context_revision,
                                         _reference_payload)
from .service import AccessDenied
from .transport import TransportError


_ZH_NUMBER = {
    '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6,
    '七': 7, '八': 8, '九': 9, '十': 10, '十一': 11, '十二': 12,
}
_EN_NUMBER = {
    'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5,
    'sixth': 6, 'seventh': 7, 'eighth': 8, 'ninth': 9, 'tenth': 10,
    'eleventh': 11, 'twelfth': 12,
}
_TERMINAL = '。！？!?.,，；;：:、…'


@dataclass(frozen=True, slots=True)
class SavedMemoryFollowup:
    mode: str
    ordinal: int | None = None


def _trim(text):
    return text.strip().rstrip(_TERMINAL).rstrip()


def _ordinal(raw):
    ordinal_match = re.fullmatch(r'([0-9]+)(?:st|nd|rd|th)', raw)
    if ordinal_match is not None:
        raw = ordinal_match.group(1)
    if raw.isascii() and raw.isdecimal():
        try:
            return int(raw)
        except ValueError:
            return 13
    return _ZH_NUMBER.get(raw, _EN_NUMBER.get(raw, 13))


def parse_saved_memory_followup(text):
    """Recognize only the documented read-only followup utterances."""
    if type(text) is not str:
        return None
    value = _trim(text.casefold())
    if value in {'介绍这些回忆', '介绍这些故事', '介绍这些回忆录',
                 'introduce these memories', 'tell me about these saved memories'}:
        return SavedMemoryFollowup('overview')

    patterns = (
        (r'^第([0-9]+|一|二|两|三|四|五|六|七|八|九|十|十一|十二)(?:段回忆|个故事|本回忆录)讲了什么$', 'preview'),
        (r'^第([0-9]+|一|二|两|三|四|五|六|七|八|九|十|十一|十二)(?:段回忆|本回忆录)有哪些章节$', 'outline'),
        (r'^what is the ([0-9]+(?:st|nd|rd|th)|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth) saved memory about$', 'preview'),
        (r'^what chapters does the ([0-9]+(?:st|nd|rd|th)|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth) saved memory have$', 'outline'),
    )
    for pattern, mode in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            return SavedMemoryFollowup(mode, _ordinal(match.group(1)))

    if value in {'有哪些章节', 'what chapters does it have'}:
        return SavedMemoryFollowup('outline')
    return None


def parse_saved_memory_action(text):
    """Recognize a complete read-only request; never extract a command substring."""
    if type(text) is not str:
        return None
    value = _trim(text.casefold())
    zh_number = r'([0-9]+|一|二|两|三|四|五|六|七|八|九|十|十一|十二)'
    en_number = r'([0-9]+(?:st|nd|rd|th)?|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth)'
    patterns = (
        (rf'(?:请|帮我)?(?:打开|查看)第{zh_number}(?:个|篇|段|本)(?:回忆录|回忆|故事)', 'open'),
        (rf'(?:请|帮我)?(?:读|朗读|读一下|读一读)第{zh_number}(?:个|篇|段|本)(?:回忆录|回忆|故事)(?:的开篇|开篇)?', 'read_opening'),
        (rf'(?:please )?open (?:the )?{en_number} (?:saved memory|story|memoir)', 'open'),
        (rf'(?:please )?read (?:the )?{en_number} (?:saved memory|story|memoir)(?: opening)?', 'read_opening'),
    )
    for pattern, mode in patterns:
        match = re.fullmatch(pattern, value)
        if match:
            return SavedMemoryFollowup(mode, _ordinal(match.group(1)))
    for mode, phrases in (
            ('open', {'打开这个故事', '打开这篇回忆', '打开这本回忆录', 'open this story', 'open this saved memory', 'open this memoir'}),
            ('read_opening', {'读这个故事', '读这篇回忆', '读这本回忆录', '朗读开篇', 'read this story', 'read this saved memory', 'read this memoir'})):
        if value in phrases:
            return SavedMemoryFollowup(mode)
    return None


def _reply(mode, count, ordinal, locale):
    if locale == 'zh':
        if mode in {'open', 'read_opening'}:
            return (f'已选中第 {ordinal} 条回忆，可以打开阅读。' if mode == 'open' else
                    f'可以朗读第 {ordinal} 条回忆的开篇。')
        if mode == 'overview':
            return f'已按当前显示的 {count} 条已保存回忆整理概览；内容仅对应当前显示列表。'
        if mode == 'preview':
            return f'已根据当前显示列表第 {ordinal} 条已保存回忆提供原文摘录。'
        return f'已根据当前显示列表第 {ordinal} 条已保存回忆整理章节目录。'
    if mode == 'overview':
        return f'Overview of the {count} currently displayed saved memories; this uses only the displayed list.'
    if mode in {'open', 'read_opening'}:
        return (f'Item {ordinal} is ready to open.' if mode == 'open' else
                f'The opening of item {ordinal} is ready to read aloud.')
    if mode == 'preview':
        return f'Original excerpt for item {ordinal} in the currently displayed saved memory list.'
    return f'Chapter outline for item {ordinal} in the currently displayed saved memory list.'


def _clarification(library, locale, reply):
    return AssistantSavedMemoryOutcome(library_id=library, locale=locale,
        clarification=True, reply=reply, references=(), total=0,
        has_more=False, context_revision=None)


def _clip_source(value, limit=240):
    if type(value) is not str:
        raise TransportError(503, 'Saved memory unavailable')
    # Python slices code points, so clipping cannot split a UTF-8 sequence.
    return value[:limit]


class AssistantMemoryFollowupTool:
    """Hydrate and project one exact, currently authorized card cohort."""

    def run(self, access, token, library, locale, mode, references, ordinal=None):
        from .assistant_memory_discovery import AssistantMemoryDiscovery, MemoryReference
        from .service import AccessService

        if type(mode) is not str or mode not in {'overview', 'preview', 'outline', 'open', 'read_opening'}:
            raise TransportError(400, 'Invalid saved-memory followup')
        if type(references) is not list or len(references) > MAX_RESULTS:
            return _clarification(library, locale, '请先搜索并显示要查看的已保存回忆。'
                if locale == 'zh' else 'Search for saved memories first and show the results.')
        if not references:
            return _clarification(library, locale, '请先搜索并显示要查看的已保存回忆。'
                if locale == 'zh' else 'Search for saved memories first and show the results.')

        payloads = []
        identities = set()
        for reference in references:
            if (type(reference) is not dict or set(reference) !=
                    {'type', 'id', 'revision', 'fingerprint'} or
                    type(reference.get('type')) is not str or
                    reference.get('type') not in {'story', 'memoir'} or
                    type(reference.get('id')) is not str or
                    type(reference.get('revision')) is not str or
                    reference.get('revision') != reference.get('fingerprint') or
                    re.fullmatch(r'[0-9a-f]{64}', reference['revision']) is None):
                raise TransportError(404, 'Saved memory unavailable')
            try:
                ident = uuid.UUID(reference['id'])
                if ident.version != 4 or str(ident) != reference['id']:
                    raise ValueError()
            except (ValueError, TypeError, AttributeError):
                raise TransportError(404, 'Saved memory unavailable') from None
            identity = (reference['type'], reference['id'])
            if identity in identities:
                raise TransportError(404, 'Saved memory unavailable')
            identities.add(identity)
            payloads.append(reference)

        action = mode in {'open', 'read_opening'}
        choice_reply = None
        if ordinal is None:
            if mode == 'outline' and len(payloads) != 1:
                return _clarification(library, locale,
                    '请先搜索并只显示一条已保存回忆，再询问章节。' if locale == 'zh' else
                    'Search again and display one saved memory before asking for its chapters.')
            selected = 0 if len(payloads) == 1 else None
            if action and selected is None:
                choice_reply = (f'你想选择哪一条？当前有 {len(payloads)} 条回忆，可以说“读第二个故事”或“打开第一个故事”。'
                    if locale == 'zh' else
                    f'Which one? There are {len(payloads)} memories. Say “read the second story” or “open the first story”.')
        else:
            if type(ordinal) is not int or not 1 <= ordinal <= 12 or ordinal > len(payloads):
                if not action:
                    return _clarification(library, locale,
                        '这个序号不在当前显示列表中；请先重新搜索。' if locale == 'zh' else
                        'That number is outside the displayed list. Search again first.')
                selected = None
                choice_reply = (f'当前只有 {len(payloads)} 条回忆，请选择列表中的序号。' if locale == 'zh' else
                    f'There are {len(payloads)} memories. Choose a number from this list.')
            else:
                selected = ordinal - 1

        try:
            with access.connection_factory() as connection:
                domain = AccessService(connection, clock=access.clock,
                    memory_groups_enabled=access.memory_groups_enabled)
                domain.library_principal(token, library)
                version = connection.execute('PRAGMA data_version').fetchone()[0]
                reader = AssistantMemoryDiscovery(domain)
                projected = []
                selected_detail = None
                selected_child_titles = None
                for index, reference in enumerate(payloads):
                    kind = reference['type']
                    detail_reader = reader.stories if kind == 'story' else reader.books
                    detail = detail_reader.get(token, library, reference['id'])
                    numeric_revision = detail.get('revision')
                    payload = reader.read_reference(token, library, kind,
                        reference['id'], numeric_revision, reference['revision'])
                    title = payload.get('title')
                    if kind == 'story':
                        chapters = payload.get('chapters')
                        if type(chapters) is not list:
                            raise ValueError('invalid current story')
                        first_text = (chapters[0].get('narration', '')
                            if chapters and type(chapters[0]) is dict else '')
                        children = None
                    else:
                        introduction = payload.get('introduction')
                        child_refs = payload.get('stories')
                        if type(child_refs) is not list:
                            raise ValueError('invalid current memoir')
                        first_text = introduction if type(introduction) is str else ''
                        children = []
                        for child in child_refs:
                            current = reader.stories.get(token, library, child['id'])
                            if current.get('revision') != child.get('revision'):
                                raise TransportError(409, 'Saved memory changed; refresh before reading')
                            children.append(current['title'])
                    if type(title) is not str or not title.strip():
                        raise ValueError('invalid current memory title')
                    excerpt = _clip_source(first_text or title)
                    ref = MemoryReference(kind, reference['id'], numeric_revision,
                        reference['revision'], title, excerpt)
                    projected.append(ref)
                    if index == selected:
                        selected_detail = payload
                        selected_child_titles = children
                if connection.execute('PRAGMA data_version').fetchone()[0] != version:
                    raise TransportError(409, 'Saved memory changed; refresh before reading')
        except TransportError as exc:
            if exc.status in (401, 403, 404):
                raise TransportError(404, 'Saved memory unavailable') from None
            raise
        except AccessDenied:
            raise TransportError(404, 'Saved memory unavailable') from None
        except (sqlite3.Error, AttributeError, IndexError, KeyError,
                TypeError, ValueError):
            raise TransportError(503, 'Saved memory unavailable') from None

        count = len(projected)
        if mode == 'preview':
            if selected_detail is None:
                return _clarification(library, locale, '请先搜索并显示要查看的已保存回忆。'
                    if locale == 'zh' else 'Search for saved memories first and show the results.')
            source = (selected_detail['introduction'] if projected[selected].kind == 'memoir'
                      else selected_detail['chapters'][0]['narration'])
            excerpt = _clip_source(source or projected[selected].title)
            projected[selected] = MemoryReference(projected[selected].kind,
                projected[selected].id, projected[selected].revision,
                projected[selected].source_revision, projected[selected].title, excerpt)
        elif mode == 'outline':
            if selected_detail is None:
                return _clarification(library, locale, '请先搜索并显示要查看的已保存回忆。'
                    if locale == 'zh' else 'Search for saved memories first and show the results.')
            titles = (selected_child_titles if projected[selected].kind == 'memoir' else
                      [item['title'] for item in selected_detail['chapters']])
            lines = ['章节目录：'] if locale == 'zh' else ['Chapters:']
            lines.extend(f'{index}. {title}' for index, title in enumerate(titles, 1))
            excerpt = _clip_source('\n'.join(lines))
            projected[selected] = MemoryReference(projected[selected].kind,
                projected[selected].id, projected[selected].revision,
                projected[selected].source_revision, projected[selected].title, excerpt)

        immutable = tuple(projected)
        return AssistantSavedMemoryOutcome(library_id=library, locale=locale,
            clarification=False, reply=choice_reply or _reply(mode, count,
                None if selected is None else selected + 1, locale),
            references=immutable, total=count, has_more=False,
            context_revision=_context_revision(library, count,
                [_reference_payload(item) for item in immutable]),
            action_type=mode if action and selected is not None else None,
            action_ordinal=selected if action and selected is not None else None)

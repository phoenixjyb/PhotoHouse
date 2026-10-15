"""Negotiated search-v2, request-time text projection; no persistent index/model.

The discovery artifact keeps its original policy and validation. This separate
projection reads current captions and saved photo notes after authorization,
inside the same transaction and budget. Private conversations are never sources.
"""
from collections import defaultdict
from dataclasses import dataclass
import re

from . import discovery as d

KINSHIP = frozenset(('妈妈', '妈咪', '爸爸', '母亲', '父亲', '爷爷', '奶奶', '外公', '外婆',
                     '姥姥', '姥爷', '哥哥', '姐姐', '弟弟', '妹妹', '儿子', '女儿', '老公', '老婆',
                     '丈夫', '妻子', '叔叔', '阿姨', '舅舅', '姑姑', 'mom', 'mum', 'mummy',
                     'mother', 'dad', 'daddy', 'father', 'grandma', 'grandpa', 'grandmother',
                     'grandfather', 'sister', 'brother', 'son', 'daughter', 'husband', 'wife'))


def kinship_name(name):
    from .kinship import SELECTORS
    parts = [re.sub(r'^(?:my |our |我的|我们的)', '', d.fold(part.strip()))
             for part in name.split('/')]
    return bool(parts) and all(part in KINSHIP or part in SELECTORS for part in parts)


@dataclass(frozen=True)
class SearchPlan:
    version: int
    filters: dict
    date_basis: str = 'capture'

    def __post_init__(self):
        d.require(self.version == 2 and self.date_basis == 'capture')
        d.require(type(self.filters) is dict and set(self.filters) <= set(d.FIELDS) | {'text'})


def name_hits(words, label, aliases=(), *, person=False):
    haystack = d.fold(words)
    names = [label, *aliases]
    names += [part.strip() for name in names for part in name.split('/')]
    return [name for name in names if name.strip() and not (person and kinship_name(name)) and (
        re.search(r'(?<![a-z0-9_])' + re.escape(d.fold(name)) + r'(?![a-z0-9_])', haystack)
        if re.fullmatch(r'[\w .-]+', name, flags=re.ASCII) else d.fold(name) in haystack)]


class AssistantSearchReads(d.DiscoveryReads):
    def __init__(self, access, provider, budget, *, kinship=None):
        super().__init__(access, provider, budget)
        self.kinship = kinship

    def _extra_source(self, index, source, read, check):
        captions = source['captions'] if 'caption' in index.enabled else read(
            'SELECT x.id,x.asset_id,CASE WHEN length(CAST(x.text AS BLOB))<=4096 THEN x.text END,'
            'length(CAST(x.text AS BLOB)),length(CAST(x.text AS BLOB)),x.user_edited,x.superseded '
            'FROM captions x' + d.SCOPE + ' ORDER BY x.id', (index.library_id,))
        # Same child AND parent scope as Stories.search; no revisions/history,
        # annotation drafts, saved multi-image stories, or assistant receipts.
        notes = read('''SELECT s.id,s.asset_id,s.revision,
            CASE WHEN length(CAST(s.title AS BLOB))<=512 THEN s.title END,
            CASE WHEN length(CAST(s.text AS BLOB))<=65536 THEN s.text END,
            s.author_id,s.updated_at
            FROM access_stories s JOIN assets a ON a.id=s.asset_id
            JOIN access_asset_libraries m ON m.asset_id=a.id
            WHERE m.library_id=? AND s.library_id=m.library_id AND s.deleted=0
            AND (a.status='active' OR a.status IS NULL) ORDER BY s.id''', (index.library_id,))
        return {'text_projection_version': 2, 'text_captions': captions, 'photo_notes': notes,
                **({'kinship_digest': self.kinship.digest} if self.kinship is not None else {})}

    def _search_fields(self, index):
        return super()._search_fields(index) | {'text'}

    def _facts(self, index, source, people, places, check):
        assets, rows, facets, coverage = super()._facts(index, source, people, places, check)
        captions = defaultdict(list)
        for row in source['text_captions']:
            check(); captions[str(row[1])].append(row)
        notes = defaultdict(list)
        for sid, aid, revision, title, content, author, updated in source['photo_notes']:
            check()
            if type(title) is str and type(content) is str:
                notes[str(aid)].append({'source': 'photo_memory', 'source_id': sid,
                    'revision': revision, 'content': title + '\n' + content})
        for aid, row in rows.items():
            check()
            row['text_sources'] = list(notes[aid])
            caption = d.current_caption(captions[aid])
            if caption is not None:
                eligible = [r for r in captions[aid] if r[2] == caption and r[6] == 0 and r[5] in (0, 1)]
                chosen = max(eligible, key=lambda r: r[5])
                row['text_sources'].append({'source': 'edited_caption' if chosen[5] == 1 else 'generated_caption',
                    'source_id': str(chosen[0]), 'revision': d.digest(chosen), 'content': caption})
        return assets, rows, facets, coverage

    def _content_match(self, row, filters):
        reasons = []
        for source in row.get('text_sources', ()) if row and 'text' in filters else ():
            if filters['text'] in d.fold(source['content']):
                # A reason identifies provenance without copying private prose
                # into context or implying that a generated caption is fact.
                reasons.append({k: source[k] for k in ('source', 'source_id', 'revision')})
        if 'text' in filters and not reasons:
            return False, []
        if row:
            for person in sorted(row['people'] & set(filters.get('people', {}).get('ids', ())), key=int):
                reasons.append({'source': 'reviewed_person', 'source_id': person})
            if 'date' in filters:
                reasons.append({'source': 'capture_date', 'value': row['date']})
        return True, reasons

    def _rank(self, found):
        # Stable deterministic baseline: authored evidence first, then ID.
        # This is a policy baseline, not a qualified relevance model.
        return sorted(found, key=lambda item: (
            any(r['source'] in ('photo_memory', 'edited_caption')
                for r in item.get('match_reasons', ())), int(item['id'])), reverse=True)

    def entities(self, token, library, *, words, binding=None, cancelled=lambda: False):
        d.text(words, 1024)
        def action(index, facts, context, member, check):
            from .kinship import KinshipUnavailable
            groups = {}; labels = []; ambiguous = False; related = set(); working_words = words
            if self.kinship is not None:
                targets, phrases, ambiguous = self.kinship.mentions(words)
                labels.extend(phrases)
                for phrase in phrases: working_words = working_words.replace(phrase, ' ')
                if targets:
                    try:
                        related = self.kinship.catalog_ids(targets, index.people)
                    except KinshipUnavailable:
                        ambiguous = True
                    if 'people' not in index.enabled: ambiguous = True
            for facet, items in facts[2].items():
                hits = []
                for item in items:
                    check()
                    names = name_hits(working_words, item['label'], item.get('aliases', ()), person=facet == 'people')
                    if names:
                        hits.append(item['id']); labels.append(max(names, key=len))
                if facet == 'people': hits = sorted(set(hits) | related, key=int)
                if len(hits) > 20:
                    ambiguous = True
                groups[facet] = hits[:20]
            # A shared/overlapping alias is never resolved to multiple identities.
            matched_people = [p for p in index.people if p.id in groups['people']]
            for pos, first in enumerate(matched_people):
                first_hits = name_hits(working_words, first.label, first.aliases, person=True)
                for second in matched_people[pos + 1:]:
                    if any(d.fold(a) in d.fold(b) or d.fold(b) in d.fold(a)
                           for a in first_hits for b in name_hits(working_words, second.label, second.aliases, person=True)):
                        ambiguous = True
            return {'binding': context, 'enabled': list(index.enabled) + ['text'],
                    'groups': groups, 'labels': labels, 'ambiguous': ambiguous}
        return self._run(token, library, binding, action, cancelled)


class SearchRuntime:
    """Internal adapter selected only by explicit transport negotiation."""
    def __init__(self, runtime, kinship_provider=None):
        self.runtime = runtime
        self.kinship_provider = kinship_provider

    def authorize(self, token, library):
        return self.runtime.authorize(token, library)

    def call(self, operation, token, library, cancelled, values):
        from .service import AccessService
        from .kinship import KinshipGraph, KinshipUnavailable
        with self.runtime.access.connection_factory() as connection:
            access = AccessService(connection, clock=self.runtime.access.clock)
            kinship = None; account = None
            if self.kinship_provider is not None:
                # Authenticate BEFORE opening even the private graph file. A
                # provider cannot choose an account/library on a caller's behalf.
                account = access.library_principal(token, library)
                kinship = self.kinship_provider.get(account, library)
                if kinship is not None:
                    if not isinstance(kinship, KinshipGraph): raise KinshipUnavailable()
                    if not kinship.allows(account, library):
                        kinship = None
            reader = AssistantSearchReads(access, self.runtime.provider, self.runtime.budget, kinship=kinship)
            methods = {'entities': reader.entities, 'search': reader.search,
                       'facets': reader.facets, 'assistant_asset': reader.assistant_asset}
            d.require(operation in methods)
            if operation == 'search':
                SearchPlan(2, values['filters'])
            result = methods[operation](token, library, cancelled=cancelled, **values)
            if kinship is not None:
                latest = self.kinship_provider.get(account, library)
                if not isinstance(latest, KinshipGraph) or latest.digest != kinship.digest:
                    raise d.DiscoveryChanged()
            return result

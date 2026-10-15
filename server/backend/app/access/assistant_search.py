"""Negotiated search-v2, request-time text projection; no persistent index/model.

The discovery artifact keeps its original policy and validation. This separate
projection reads current captions and saved photo notes after authorization,
inside the same transaction and budget. Private conversations are never sources.
"""
from collections import defaultdict
from dataclasses import dataclass
import re

from . import discovery as d


@dataclass(frozen=True)
class SearchPlan:
    version: int
    filters: dict
    date_basis: str = 'capture'

    def __post_init__(self):
        d.require(self.version == 2 and self.date_basis == 'capture')
        d.require(type(self.filters) is dict and set(self.filters) <= set(d.FIELDS) | {'text'})


def name_hits(words, label, aliases=()):
    haystack = d.fold(words)
    names = [label, *aliases]
    names += [part.strip() for name in names for part in name.split('/')]
    return [name for name in names if name.strip() and (
        re.search(r'(?<![a-z0-9_])' + re.escape(d.fold(name)) + r'(?![a-z0-9_])', haystack)
        if re.fullmatch(r'[\w .-]+', name, flags=re.ASCII) else d.fold(name) in haystack)]


class AssistantSearchReads(d.DiscoveryReads):
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
        return {'text_projection_version': 2, 'text_captions': captions, 'photo_notes': notes}

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
                eligible = [r for r in captions[aid] if r[2] == caption and r[6] == 0]
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
            groups = {}; labels = []; ambiguous = False
            for facet, items in facts[2].items():
                hits = []
                for item in items:
                    check()
                    names = name_hits(words, item['label'], item.get('aliases', ()))
                    if names:
                        hits.append(item['id']); labels.append(max(names, key=len))
                if len(hits) > 20:
                    ambiguous = True
                groups[facet] = hits[:20]
            # A shared/overlapping alias is never resolved to multiple identities.
            matched_people = [p for p in index.people if p.id in groups['people']]
            for pos, first in enumerate(matched_people):
                first_hits = name_hits(words, first.label, first.aliases)
                for second in matched_people[pos + 1:]:
                    if any(d.fold(a) in d.fold(b) or d.fold(b) in d.fold(a)
                           for a in first_hits for b in name_hits(words, second.label, second.aliases)):
                        ambiguous = True
            return {'binding': context, 'enabled': list(index.enabled) + ['text'],
                    'groups': groups, 'labels': labels, 'ambiguous': ambiguous}
        return self._run(token, library, binding, action, cancelled)


class SearchRuntime:
    """Internal adapter selected only by explicit transport negotiation."""
    def __init__(self, runtime):
        self.runtime = runtime

    def authorize(self, token, library):
        return self.runtime.authorize(token, library)

    def call(self, operation, token, library, cancelled, values):
        from .service import AccessService
        with self.runtime.access.connection_factory() as connection:
            reader = AssistantSearchReads(AccessService(connection, clock=self.runtime.access.clock),
                                          self.runtime.provider, self.runtime.budget)
            methods = {'entities': reader.entities, 'search': reader.search,
                       'facets': reader.facets, 'assistant_asset': reader.assistant_asset}
            d.require(operation in methods)
            if operation == 'search':
                SearchPlan(2, values['filters'])
            return methods[operation](token, library, cancelled=cancelled, **values)

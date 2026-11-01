"""Resolve bounded reviewed names for automatic saved-story refinement.

This is an internal prompt-context adapter. Callers must first reauthorize the
job actor and library with ``member``. It never resolves faces, performs fuzzy
matching, or returns account, catalog, graph, or configuration identifiers.
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import re

from . import discovery as d
from .discovery_provider import RefreshingPeopleIndex, RefreshingPlaceIndex
from .kinship import KinshipGraph, KinshipUnavailable
from .transport import TransportError

MAX_RELATED_PEOPLE = 32
MAX_NARRATION_BYTES = 1024 * 1024


class StoryRefinementContextError(ValueError):
    """Configured reviewed context was stale, mismatched, or invalid."""

    def __init__(self):
        super().__init__('Reviewed story context unavailable')


class StoryRefinementContextBusy(TransportError):
    def __init__(self):
        super().__init__(503, 'Reviewed story context busy; retry later')


def _digest(value):
    try:
        payload = json.dumps(value, ensure_ascii=True, sort_keys=True,
                             separators=(',', ':'), allow_nan=False).encode('ascii')
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise StoryRefinementContextError() from None
    return hashlib.sha256(payload).hexdigest()


def _text(value, maximum, *, multiline=False):
    if type(value) is not str or not value.strip():
        raise StoryRefinementContextError()
    try:
        if len(value.encode('utf-8')) > maximum or any(ord(c) < 32 and not (multiline and c in '\n\t') for c in value):
            raise StoryRefinementContextError()
    except UnicodeError:
        raise StoryRefinementContextError() from None
    return value.strip()


def _name_parts(value):
    if type(value) is not str:
        raise StoryRefinementContextError()
    return tuple(part.strip() for part in value.split('/') if part.strip())


def _mentioned(haystack, value):
    folded = d.fold(value)
    if not folded:
        return False
    if re.fullmatch(r'[\w .-]+', value, flags=re.ASCII):
        return re.search(r'(?<![a-z0-9_])' + re.escape(folded) +
                         r'(?![a-z0-9_])', haystack) is not None
    return folded in haystack


def _authorized_member(library, member):
    # ``member`` is the current row returned by memory_processing.member(),
    # after session, account, library, status, expiry, and state checks.
    if (type(library) is not str or not library or type(member) is not dict or
            member.get('library_id') != library or
            member.get('status') != 'approved' or
            type(member.get('account_id')) is not str or not member['account_id']):
        raise StoryRefinementContextError()


def _reviewed_index(access, library, discovery_runtime):
    if discovery_runtime is None:
        return None, {'kind': 'unconfigured'}
    try:
        provider = discovery_runtime.provider
        budget = discovery_runtime.budget
        if not callable(getattr(provider, 'get', None)) or not isinstance(budget, d.ReadBudget):
            raise StoryRefinementContextError()
        # The caller already owns its authorization transaction. Reuse the same
        # validation and bounded reads as DiscoveryReads without nesting one.
        with budget.attempt(access.db, lambda: False) as (check, read):
            check()
            index = provider.get(library)
            if index is None:
                return None, {'kind': 'no-index', 'library_id': library}
            people, _places = d.validate(index, library, budget.rows)
            if len(d.packed(asdict(index))) > budget.index_bytes:
                raise StoryRefinementContextError()
            source = d.index_source(index, read)
            check()
            if type(index) is RefreshingPeopleIndex:
                d.validate_people_source(index, source)
            current = index
            if type(index) in (RefreshingPlaceIndex, RefreshingPeopleIndex):
                current = d.refreshed_index(index, source, check, budget.rows)
                if len(d.packed(asdict(current))) > budget.index_bytes:
                    raise StoryRefinementContextError()
                check()
            if (tuple(str(row[0]) for row in source['assets']) != current.scope_ids or
                    d.digest(source) != current.source_digest):
                raise StoryRefinementContextError()
            return current, {
                'kind': 'reviewed-index',
                'library_id': library,
                'revision': current.revision,
                'source_digest': current.source_digest,
                'index_digest': d.digest(asdict(current)),
                'people_ids': sorted(people, key=int),
            }
    except d.DiscoveryBusy:
        raise StoryRefinementContextBusy() from None
    except StoryRefinementContextError:
        raise
    except Exception:
        # A configured source that cannot be authenticated/validated must not
        # silently fall back to a less current roster.
        raise StoryRefinementContextError() from None


def _graph_for_member(kinship_provider, member, library):
    if kinship_provider is None:
        return None, {'kind': 'unconfigured'}
    try:
        if not callable(getattr(kinship_provider, 'get', None)):
            raise StoryRefinementContextError()
        graph = kinship_provider.get(member['account_id'], library)
        if graph is None:
            return None, {'kind': 'no-authorized-graph'}
        if (not isinstance(graph, KinshipGraph) or
                not graph.allows(member['account_id'], library) or
                type(getattr(graph, 'digest', None)) is not str or
                re.fullmatch(r'[0-9a-f]{64}', graph.digest) is None):
            raise StoryRefinementContextError()
        return graph, {'kind': 'authorized-graph', 'digest': graph.digest}
    except StoryRefinementContextError:
        raise
    except Exception:
        raise StoryRefinementContextError() from None


def resolve(access, library, member, narration, *, discovery_runtime=None,
            kinship_provider=None):
    """Return ``(closed_people_dto, identity_digest)`` for one current story.

    ``narration`` may combine the selected story narration and selected source
    excerpts. Matching is exact after Unicode normalization; English names use
    token boundaries. Unmentioned roster entries are never returned.
    """
    _authorized_member(library, member)
    if (access is None or not hasattr(access, 'db') or
            not getattr(access.db, 'in_transaction', False)):
        raise StoryRefinementContextError()
    narration = _text(narration, MAX_NARRATION_BYTES, multiline=True)
    haystack = d.fold(narration)

    index, index_identity = _reviewed_index(access, library, discovery_runtime)
    graph, graph_identity = _graph_for_member(kinship_provider, member, library)
    if index is None:
        return [], _digest({'version': 1, 'index': index_identity,
                            'graph': graph_identity, 'people': []})

    # A graph name is admitted only through its unique catalog binding. If two
    # graph identities point at one reviewed person, both links are ambiguous.
    graph_by_catalog = {}
    if graph is not None:
        try:
            document = graph.document
            if type(document) is not dict or type(document.get('people')) is not list:
                raise StoryRefinementContextError()
            if len(document['people']) > 256:
                raise StoryRefinementContextError()
            for graph_person in document['people']:
                if type(graph_person) is not dict or type(graph_person.get('id')) is not str:
                    raise StoryRefinementContextError()
                try:
                    catalog_ids = graph.catalog_ids((graph_person['id'],), index.people)
                except KinshipUnavailable:
                    continue  # Ambiguous/unbound identities add no name context.
                if len(catalog_ids) != 1:
                    continue
                catalog_id = next(iter(catalog_ids))
                graph_by_catalog.setdefault(catalog_id, []).append(graph_person)
        except StoryRefinementContextError:
            raise
        except Exception:
            raise StoryRefinementContextError() from None

    # Resolve bilingual graph names through reviewed catalog joins BEFORE mention
    # selection. A narration can use an English graph name while the catalog
    # label is Chinese. No fuzzy matching or unbound graph identity is admitted.
    candidates = {}
    owners = {}
    for reviewed in index.people:
        if reviewed.library_id != library:
            raise StoryRefinementContextError()
        links = graph_by_catalog.get(reviewed.id, [])
        graph_person = links[0] if len(links) == 1 else None
        names = []
        values = [reviewed.label, *reviewed.aliases]
        if graph_person is not None:
            values += [graph_person.get('name_en'), graph_person.get('name_zh'),
                       *graph_person.get('aliases', ())]
        for value in values:
            if value is not None:
                names.extend(_name_parts(_text(value, 256)))
        chinese = graph_person.get('name_zh') if graph_person is not None else None
        canonical = _text(chinese, 256) if chinese else reviewed.label.strip()
        aliases, seen = [], {d.fold(canonical)}
        for name in names:
            folded = d.fold(name)
            owners.setdefault(folded, set()).add(reviewed.id)
            if folded not in seen:
                seen.add(folded)
                aliases.append(name)
        owners.setdefault(d.fold(canonical), set()).add(reviewed.id)
        candidates[reviewed.id] = {'name': canonical, 'aliases': aliases}

    selected, ambiguous = set(), set()
    for name, identities in owners.items():
        if _mentioned(haystack, name):
            if len(identities) == 1:
                selected.update(identities)
            else:
                ambiguous.update(identities)
    selected -= ambiguous
    if len(selected) > MAX_RELATED_PEOPLE:
        raise StoryRefinementContextError()
    result = [candidates[ident] for ident in sorted(selected, key=int)]
    if any(len(person['aliases']) > 16 for person in result):
        raise StoryRefinementContextError()
    result.sort(key=lambda item: (d.fold(item['name']), tuple(d.fold(a) for a in item['aliases'])))
    identity = {'version': 1, 'index': index_identity,
                'graph': graph_identity, 'people': result}
    return result, _digest(identity)

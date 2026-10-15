"""Content-free readiness diagnostics for the current authorized search view.

This module reports coverage and reviewed-identity binding status. It does not
approve people, change access, or make filename/receipt dates searchable.
"""
import re

from . import discovery as d


def _person_name_candidates(graph, logical_person, reviewed_people, check):
    """Mirror KinshipGraph.catalog_ids name matching for diagnostic categories."""
    from .kinship import SELECTORS, folded, names

    requested = {
        folded(name)
        for name in names(logical_person)
        if re.sub(r'^(?:my |our |我的|我们的)', '', folded(name)) not in SELECTORS
    }
    found = []
    for reviewed in reviewed_people:
        check()
        candidates = {
            folded(part.strip())
            for label in (reviewed.label, *reviewed.aliases)
            for part in (label, *label.split('/'))
        }
        if requested & candidates:
            found.append(reviewed.id)
    return found


def _kinship_bindings(graph, reviewed_people, assignments, check):
    """Summarize current graph-to-roster joins without returning identity data."""
    from .kinship import KinshipUnavailable

    if graph is None:
        return {'status': 'not_configured', 'people': 0, 'unique': 0, 'missing': 0,
                'ambiguous': 0, 'stale': 0, 'unique_with_assignments': 0,
                'unique_allow_zero': 0}

    current_people = tuple(
        person for person in reviewed_people if person.library_id == graph._library_id
    )
    assignments = {item.person_id for item in assignments}
    allow_zero = {item.id: item.allow_zero for item in current_people}
    statuses = {}
    matched_ids = {}
    for logical_id, person in graph.people.items():
        check()
        binding = person['catalog_binding']
        if binding is not None:
            candidates = [item.id for item in current_people
                          if item.id == binding['person_id'] and item.label == binding['label']]
            status = 'unique' if len(candidates) == 1 else 'stale'
        else:
            candidates = _person_name_candidates(graph, person, current_people, check)
            try:
                resolved = graph.catalog_ids({logical_id}, current_people)
            except KinshipUnavailable:
                resolved = set()
            status = 'unique' if len(candidates) == 1 and resolved == {candidates[0]} else (
                'ambiguous' if len(candidates) > 1 else 'missing')
        statuses[logical_id] = status
        if status == 'unique':
            matched_ids[logical_id] = candidates[0]

    # Two private graph people may not collapse onto one reviewed identity.
    owners = {}
    for logical_id, catalog_id in matched_ids.items():
        owners.setdefault(catalog_id, []).append(logical_id)
    for logical_ids in owners.values():
        if len(logical_ids) > 1:
            for logical_id in logical_ids:
                statuses[logical_id] = 'ambiguous'

    counts = {key: sum(value == key for value in statuses.values())
              for key in ('unique', 'missing', 'ambiguous', 'stale')}
    counts['people'] = len(statuses)
    counts['unique_with_assignments'] = sum(
        status == 'unique' and matched_ids.get(logical_id) in assignments
        for logical_id, status in statuses.items()
    )
    counts['unique_allow_zero'] = sum(
        status == 'unique' and matched_ids.get(logical_id) not in assignments
        and allow_zero.get(matched_ids.get(logical_id), False)
        for logical_id, status in statuses.items()
    )
    counts['status'] = 'current' if counts['unique'] == counts['people'] else 'unresolved'
    return counts


def build_readiness(index, facts, context, kinship, check):
    """Build aggregate readiness from `DiscoveryReads._facts` in its transaction."""
    assets, rows, facets, _coverage = facts
    by_media = {}
    for kind in ('image', 'video', 'other'):
        selected = {}
        for aid, asset in assets.items():
            check()
            if asset['kind'] == kind:
                selected[aid] = asset
        values = {}
        for aid in selected:
            check()
            if aid in rows:
                values[aid] = rows[aid]
        counts = {'catalog_assets': len(selected), 'indexed_assets': len(values),
                  'unindexed_assets': len(selected) - len(values)}
        counts['capture_dates_recorded'] = 0
        for asset in selected.values():
            check()
            counts['capture_dates_recorded'] += d.taken_day(asset['taken_at']) is not None
        counts['capture_dates_missing'] = len(selected) - counts['capture_dates_recorded']
        counts['capture_dates_searchable'] = 0
        counts['text_searchable'] = 0
        counts['people_searchable'] = 0
        for row in values.values():
            check()
            counts['capture_dates_searchable'] += ('date' in index.enabled and row['date'] is not None)
            counts['text_searchable'] += bool(row['text_sources'])
            counts['people_searchable'] += ('people' in index.enabled and bool(row['people']))
        for source in ('photo_memory', 'edited_caption', 'generated_caption'):
            check()
            counts[source] = sum(any(item['source'] == source for item in row['text_sources'])
                                 for row in values.values())
        by_media[kind] = counts

    people = tuple(index.people)
    assigned_people = {assignment.person_id for assignment in index.assignments}
    assigned_assets = sum(bool(row['people']) for row in rows.values())
    indexed_assets = len(rows)
    catalog_assets = len(assets)
    if 'people' not in index.enabled:
        people_status = 'disabled'
    elif not index.people:
        people_status = 'empty_roster'
    elif assigned_assets == 0:
        people_status = 'zero_assigned'
    elif indexed_assets < catalog_assets:
        people_status = 'partial_coverage'
    else:
        people_status = 'available'
    people_readiness = {
        'status': people_status,
        'reviewed_person_count': len(facets['people']),
        'reviewed_people_with_assignments': sum(person.id in assigned_people for person in people),
        'reviewed_people_without_assignments': sum(person.id not in assigned_people for person in people),
        'reviewed_people_allow_zero': sum(person.allow_zero for person in people),
        'assigned_assets_searchable': assigned_assets,
        'indexed_assets': indexed_assets,
        'catalog_assets': catalog_assets,
    }

    recorded_dates = sum(item['capture_dates_recorded'] for item in by_media.values())
    searchable_dates = sum(item['capture_dates_searchable'] for item in by_media.values())
    unsearchable_recorded_dates = recorded_dates - searchable_dates
    issues = []
    if indexed_assets < catalog_assets:
        issues.append({'code': 'assets_outside_reviewed_index',
                       'count': catalog_assets - indexed_assets})
    if by_media['video']['capture_dates_missing']:
        issues.append({'code': 'videos_without_recorded_capture_date',
                       'count': by_media['video']['capture_dates_missing']})
    if 'date' not in index.enabled and recorded_dates:
        issues.append({'code': 'capture_dates_recorded_but_index_disabled',
                       'count': recorded_dates})
    elif 'date' in index.enabled and unsearchable_recorded_dates:
        issues.append({'code': 'capture_date_index_missing_coverage',
                       'count': unsearchable_recorded_dates})
    if not any(value['text_searchable'] for value in by_media.values()):
        issues.append({'code': 'no_eligible_text', 'count': indexed_assets})
    if people_status in ('disabled', 'empty_roster'):
        issues.append({'code': 'reviewed_people_unavailable', 'count': 0})
    elif people_status == 'zero_assigned':
        issues.append({'code': 'reviewed_people_have_no_assigned_assets', 'count': 0})

    graph_bindings = _kinship_bindings(kinship, people, index.assignments, check)
    return {
        'version': 1, 'search_version': 2, 'status': 'current', 'binding': context,
        'index_revision': index.revision, 'date_basis': 'capture',
        'enabled': [field for field in d.FIELDS if field in index.enabled] + ['text'],
        'catalog_assets': catalog_assets, 'indexed_assets': indexed_assets,
        'index_complete': catalog_assets == indexed_assets, 'by_media': by_media,
        'reviewed_person_count': len(facets['people']),
        'kinship_available': kinship is not None,
        'relevance_measured': False, 'issues': issues,
        'people_readiness': people_readiness,
        'kinship_bindings': graph_bindings,
    }

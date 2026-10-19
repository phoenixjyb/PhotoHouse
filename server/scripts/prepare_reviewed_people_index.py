#!/usr/bin/env python3
"""Prepare, never install, a reviewed people layer over approved refreshing places.

The two-pass inspector emits a private review envelope. Only a subsequent exact
source-bound review can produce an index. No names or assignments are inferred.
"""
import argparse
from dataclasses import asdict, replace
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import prepare_access_discovery_index as producer
from app.access import discovery as d
from app.access.discovery_index import accepted, index as parse_index, person, face, read
from app.access.discovery_provider import RefreshingPlaceIndex, RefreshingPeopleIndex
from reviewed_people_source import open_reviewed_people_source

ENABLED = ('people', 'date', 'locations', 'media')


def derive(db, base, library, revision, review, *, inspect=False):
    """Retain approved location rules, explicitly review only supplied people/faces."""
    budget = d.ReadBudget()
    accepted(base, budget)
    if type(base) is not RefreshingPlaceIndex or base.library_id != library:
        raise producer.Refused('Explicit refreshing place base required')
    if type(review) is not dict or set(review) != producer.REVIEW_KEYS | {'base_index_digest'}:
        raise producer.Refused('Complete explicit review required')
    if (review['base_index_digest'] != d.digest(asdict(base)) or
            review['library_id'] != library or review['enabled'] != list(ENABLED) or
            review['places'] != [] or review['regions'] != [] or review['source_fields'] != {} or
            type(review['people']) is not list or not 1 <= len(review['people']) <= 5000):
        raise producer.Refused('Review policy refused')
    people = tuple(person(dict(record, library_id=library)) for record in review['people'])
    if type(review['assignments']) is not list or len(review['assignments']) > budget.rows:
        raise producer.Refused('Bounded explicit assignments required')
    assignments = tuple(face(record) for record in review['assignments'])
    seed = RefreshingPeopleIndex(library, revision, base.scope_ids, base.scope_ids,
        base.source_digest, people=people, assignments=assignments, enabled=ENABLED, places=base.places,
        region_rules=base.region_rules, catalog_digest='0' * 64)
    with budget.attempt(db, lambda: False) as (check, fetch):
        source = d.index_source(seed, fetch)
        scope = tuple(str(row[0]) for row in source['assets'])
        source_digest = d.digest(source)
        envelope = dict(review)
        if inspect:
            # Inspection is not approval. Emit an exact candidate for later review.
            envelope.update(source_digest=source_digest, indexed_ids=list(scope))
        reviewed = producer.reviewed_index({key: envelope[key] for key in producer.REVIEW_KEYS},
            library, revision, scope, source_digest, source)
        if reviewed.indexed_ids != scope:
            raise producer.Refused('Current full library scope review required')
        candidate = replace(seed, scope_ids=scope, indexed_ids=scope,
            assignments=reviewed.assignments, pinned_ids=reviewed.pinned_ids,
            catalog_digest=d.reviewed_catalog_digest(source['reviewed_people']))
        accepted(candidate, budget)
        d.validate_people_source(candidate, source)
        candidate = d.refreshed_index(candidate, source, check, budget.rows)
        accepted(candidate, budget)
        # Same exact manual-row/current-roster admission as the serving path.
        d.DiscoveryReads._facts(None, candidate, source,
            {p.id: p for p in candidate.people}, {p.id: p for p in candidate.places}, check)
    return candidate, envelope


def main(argv=None):
    parser = producer.Parser(allow_abbrev=False, description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--base-index', type=Path, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--revision', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--inspect', action='store_true')
    parser.add_argument('--deletion-journal', type=Path)
    parser.add_argument('--deletion-namespace')
    try:
        args = parser.parse_args(argv)
        library, revision = producer.library(args.library), producer.revision(args.revision)
        base_bytes = read(args.base_index, d.ReadBudget().index_bytes)
        base = parse_index(base_bytes, d.ReadBudget().rows)
        review = producer.review_json(args.review)
        with open_reviewed_people_source(producer, args.database, time.monotonic(),
                deletion_journal=args.deletion_journal,
                deletion_namespace=args.deletion_namespace) as db:
            candidate, envelope = derive(db, base, library, revision, review, inspect=args.inspect)
        # An inspector output is intentionally not a loadable index/review file.
        result = ({'schema': 1, 'status': 'requires_explicit_review', 'review': envelope,
                   'base_index_digest': d.digest(asdict(base)),
                   'catalog_digest': candidate.catalog_digest}
                  if args.inspect else asdict(candidate))
        payload = d.packed(result)
        producer.direct(args.out)
        if os.name != 'nt' and args.out.parent.stat().st_mode & 0o077:
            raise producer.Refused('Private output directory required')
        digest = producer.write_new(args.out, payload)
        print(json.dumps({'completed': True, 'inspection_only': args.inspect,
            'database_modified': False, 'runtime_changed': False, 'output_sha256': digest,
            'people': len(candidate.people), 'reviewed_assignments': len(candidate.assignments)}, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print('Interrupted; inspect any new output before reuse.', file=sys.stderr)
        return 130
    except Exception:
        print('Reviewed people preparation refused; inspect any new output before reuse.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

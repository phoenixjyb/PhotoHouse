#!/usr/bin/env python3
"""Inspect an explicit people/face selection without approving or installing it.

The report distinguishes library-visible legacy records from people whose
ownership and selected manual assignments satisfy source-bound preparation.
It never scans for candidate people or faces: every identity and face ID comes
from the private selection file.
"""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

from app.access import discovery as d
import prepare_access_discovery_index as producer

SELECTION_KEYS = frozenset({'schema', 'library_id', 'people', 'assignments'})
PERSON_KEYS = frozenset({'id', 'label'})
ASSIGNMENT_KEYS = frozenset({'id', 'asset_id', 'person_id', 'source'})
MAX_PEOPLE = 5000
MAX_ASSIGNMENTS = 100000


class Refused(RuntimeError):
    """Opaque fail-closed result for malformed or unavailable inspection."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('Invalid arguments')


def validate_selection(value, library_id, row_limit):
    if (type(value) is not dict or set(value) != SELECTION_KEYS
            or type(value['schema']) is not int or value['schema'] != 1):
        raise Refused('Invalid selection')
    if value['library_id'] != library_id:
        raise Refused('Selection library mismatch')
    people = value['people']
    assignments = value['assignments']
    if type(people) is not list or not 1 <= len(people) <= MAX_PEOPLE:
        raise Refused('Invalid selected people')
    if type(assignments) is not list or not 1 <= len(assignments) <= min(MAX_ASSIGNMENTS, row_limit):
        raise Refused('Invalid selected assignments')
    normalized_people = []
    person_ids = set()
    for item in people:
        if type(item) is not dict or set(item) != PERSON_KEYS:
            raise Refused('Invalid selected person')
        try:
            person_id = d.identifier(item['id'])
            label = d.text(item['label'], 256)
        except d.DiscoveryInvalid:
            raise Refused('Invalid selected person') from None
        if person_id in person_ids:
            raise Refused('Duplicate selected person')
        person_ids.add(person_id)
        normalized_people.append({'id': person_id, 'label': label})
    normalized_assignments = []
    assignment_ids = set()
    for item in assignments:
        if type(item) is not dict or set(item) != ASSIGNMENT_KEYS or item['source'] != 'manual':
            raise Refused('Invalid selected assignment')
        try:
            face_id = d.identifier(item['id'])
            asset_id = d.identifier(item['asset_id'])
            person_id = d.identifier(item['person_id'])
        except d.DiscoveryInvalid:
            raise Refused('Invalid selected assignment') from None
        if face_id in assignment_ids or person_id not in person_ids:
            raise Refused('Duplicate or unknown selected assignment')
        assignment_ids.add(face_id)
        normalized_assignments.append({
            'id': face_id, 'asset_id': asset_id, 'person_id': person_id, 'source': 'manual'})
    return {'schema': 1, 'library_id': library_id,
            'people': normalized_people, 'assignments': normalized_assignments}


def inspect_selection(db, library_id, selection, *, budget=None):
    """Return a private, non-installable report for one explicit selection.

    ``db`` must be a read-only SQLite connection. This callable is also used by
    the native operator harness, which opens the original database read-only
    and loads this source without installing it.
    """
    try:
        if type(library_id) is not str:
            raise Refused('Invalid library')
        try:
            library_id = producer.library(library_id)
        except producer.Refused:
            raise Refused('Invalid library') from None
        budget = budget or d.ReadBudget()
        selected = validate_selection(selection, library_id, budget.rows)
        people = selected['people']
        assignments = selected['assignments']
        report_people = []
        report_assignments = []
        evidence = {'people': [], 'assignments': []}
        person_visible = {}

        with budget.attempt(db, lambda: False) as (check, read):
            # Only explicit IDs that are owned here or have an active face in
            # this library are returned. Foreign and hidden names never enter
            # Python report state, and long labels are bounded in SQL.
            for start in range(0, len(people), 256):
                check()
                batch = people[start:start + 256]
                rows = read('''SELECT p.id,
                    CASE WHEN length(CAST(p.display_name AS BLOB))<=256
                         THEN p.display_name END,
                    CASE WHEN o.person_id IS NULL THEN 0
                         ELSE 1 END,
                    CASE WHEN length(CAST(p.display_name AS BLOB))<=256 THEN 1 ELSE 0 END,
                    length(CAST(p.display_name AS BLOB)),
                    CASE WHEN length(CAST(p.updated_at AS BLOB))<=64 THEN p.updated_at END,
                    length(CAST(p.updated_at AS BLOB)),o.library_id,o.revision
                    FROM persons p LEFT JOIN access_person_libraries o ON o.person_id=p.id
                    WHERE p.id IN (''' + ','.join('?' for _ in batch) + ''')
                      AND (o.library_id=? OR (o.person_id IS NULL AND EXISTS (
                        SELECT 1 FROM face_detections f JOIN assets a ON a.id=f.asset_id
                        JOIN access_asset_libraries m ON m.asset_id=a.id
                        WHERE f.person_id=p.id AND m.library_id=?
                          AND (a.status='active' OR a.status IS NULL))))
                      ORDER BY p.id''',
                    (*(int(item['id']) for item in batch), library_id, library_id))
                by_id = {str(row[0]): row for row in rows}
                for item in batch:
                    check()
                    row = by_id.get(item['id'])
                    person_visible[item['id']] = row is not None
                    owner_state = row[2] if row else None
                    current_label = row[1] if row else None
                    exact_label = bool(row and row[3] == 1 and current_label == item['label'])
                    if owner_state == 1 and exact_label:
                        status = 'exact_owned'
                    elif owner_state == 0 and exact_label:
                        status = 'legacy_visible_without_owner'
                    else:
                        status = 'name_changed_or_unavailable'
                    outside_or_unmapped = None
                    if owner_state == 0:
                        # One aggregate probe over this selected legacy person;
                        # same-library inactive rows are not outside/unmapped.
                        outside_or_unmapped = bool(read('''SELECT 1 FROM face_detections f
                            LEFT JOIN assets a ON a.id=f.asset_id
                            LEFT JOIN access_asset_libraries m
                              ON m.asset_id=a.id AND m.library_id=?
                            WHERE f.person_id=? AND (a.id IS NULL OR m.asset_id IS NULL)
                            LIMIT 1''', (library_id, int(item['id']))))
                    report_people.append({'id': item['id'], 'selected_label': item['label'],
                        'status': status, 'outside_or_unmapped_faces': outside_or_unmapped})
                    evidence['people'].append((item['id'], item['label'], status,
                        current_label, row[4] if row else None, row[5] if row else None,
                        row[6] if row else None, row[7] if row else None,
                        row[8] if row else None,
                        outside_or_unmapped))

            for start in range(0, len(assignments), 256):
                check()
                batch = assignments[start:start + 256]
                rows = read('''SELECT f.id,f.asset_id,f.person_id,f.label_source
                    FROM face_detections f JOIN assets a ON a.id=f.asset_id
                    JOIN access_asset_libraries m ON m.asset_id=a.id
                    WHERE f.id IN (''' + ','.join('?' for _ in batch) + ''')
                      AND m.library_id=? AND (a.status='active' OR a.status IS NULL)
                    ORDER BY f.id''',
                    (*(int(item['id']) for item in batch), library_id))
                by_id = {str(row[0]): row for row in rows}
                for item in batch:
                    check()
                    row = by_id.get(item['id'])
                    if (not person_visible.get(item['person_id'], False) or row is None
                            or (str(row[1]), str(row[2])) !=
                            (item['asset_id'], item['person_id'])):
                        status = 'unavailable'
                    elif row[3] != 'manual':
                        status = 'not_manual'
                    else:
                        status = 'manual_current'
                    report_assignments.append({'id': item['id'], 'asset_id': item['asset_id'],
                        'person_id': item['person_id'], 'status': status})
                    evidence['assignments'].append((item['id'], item['asset_id'],
                        item['person_id'], status,
                        tuple(row) if status != 'unavailable' else None))

        valid_assignment_people = {item['person_id'] for item in report_assignments
                                   if item['status'] == 'manual_current'}
        exact_owned = {item['id'] for item in report_people if item['status'] == 'exact_owned'}
        ready = (all(person['id'] in exact_owned and person['id'] in valid_assignment_people
                     for person in people)
                 and all(item['status'] == 'manual_current' for item in report_assignments))
        return {'schema': 1, 'status': 'requires_explicit_review',
                'library_id': library_id, 'ready_for_source_bound_preparation': ready,
                'people': report_people, 'assignments': report_assignments,
                'source_digest': d.digest({'library_id': library_id, **evidence})}
    except (d.DiscoveryInvalid, d.DiscoveryUnavailable, d.DiscoveryCancelled,
            d.DiscoveryBusy, d.DiscoveryChanged, ValueError, TypeError, KeyError,
            sqlite3.Error):
        raise Refused('Readiness inspection refused') from None


def read_selection(path):
    try:
        producer.direct(path)
        if os.name != 'nt' and path.stat().st_mode & 0o077:
            raise Refused('Private selection required')
        value = producer.review_json(path)
    except Exception:
        raise Refused('Invalid selection file') from None
    return value


def main(argv=None):
    parser = Parser(allow_abbrev=False, description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    try:
        args = parser.parse_args(argv)
        library_id = producer.library(args.library)
        selection = read_selection(args.selection)
        start = time.monotonic()
        with closing(producer.open_read_only(args.database, start)) as db:
            result = inspect_selection(db, library_id, selection)
        payload = json.dumps(result, sort_keys=True, ensure_ascii=True,
                             separators=(',', ':'), allow_nan=False).encode()
        producer.direct(args.out)
        if os.name != 'nt' and args.out.parent.stat().st_mode & 0o077:
            raise Refused('Private output directory required')
        output_sha256 = producer.write_new(args.out, payload)
        print(json.dumps({'people': len(result['people']),
            'assignments': len(result['assignments']),
            'source_digest': result['source_digest'], 'output_sha256': output_sha256,
            'output_bytes': len(payload)}, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print('Interrupted; inspect any new output before reuse.', file=sys.stderr)
        return 130
    except Exception:
        print('Reviewed people readiness inspection refused or incomplete.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

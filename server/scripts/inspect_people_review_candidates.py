#!/usr/bin/env python3
"""Write a private, offline proposal of manually labeled people-review candidates.

This tool does not confirm identities, install a discovery index, or read media.
Each proposal is bound to an existing RefreshingPeopleIndex and the current
source that still validates every frozen identity and assignment.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

from app.access import discovery as d
from app.access.discovery_index import read as read_index, index as parse_index
from app.access.discovery_provider import RefreshingPeopleIndex
from app.access.private_storage import require_private_directory, require_private_file
import prepare_access_discovery_index as producer
from reviewed_people_source import open_reviewed_people_source

MAX_PEOPLE = 20
MAX_PHOTOS = 12
MAX_FACES_PER_PHOTO = 32


class Refused(RuntimeError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('Invalid arguments')


def _input(path, *, maximum=None):
    producer.direct(path)
    require_private_file(path)
    if maximum is not None and path.stat().st_size > maximum:
        raise Refused('Input too large')
    return path


def _validate_frozen_source(index, source):
    """Match the request-time frozen identity/assignment checks before proposing."""
    current_scope = {str(row[0]) for row in source['assets']}
    d.validate_people_source(index, source)
    frozen = {(item.id, item.asset_id, item.person_id, item.source)
              for item in index.assignments}
    present = {(str(row[0]), str(row[1]), str(row[2]), row[3])
               for row in source['faces']}
    if present != frozen or any(item[1] not in current_scope for item in frozen):
        raise Refused('Reviewed assignment changed')


def _candidate_assets(read, library_id, person_id, excluded, photos_per_person):
    # At most one result per reviewed photo is skipped. Fetching |excluded|+N+1
    # distinct IDs therefore gives N candidates and a correct has_more bit.
    fetch_limit = len(excluded) + photos_per_person + 1
    rows = read('''SELECT DISTINCT f.asset_id
        FROM face_detections f JOIN assets a ON a.id=f.asset_id
        JOIN access_asset_libraries m ON m.asset_id=a.id
        WHERE m.library_id=? AND (a.status='active' OR a.status IS NULL)
          AND f.person_id=? AND f.label_source='manual'
        ORDER BY f.asset_id DESC LIMIT ?''', (library_id, int(person_id), fetch_limit))
    return [str(row[0]) for row in rows if str(row[0]) not in excluded]


def inspect(db, index, photos_per_person):
    budget = d.ReadBudget()
    d.validate(index, index.library_id, budget.rows)
    if type(index) is not RefreshingPeopleIndex or not 1 <= len(index.people) <= MAX_PEOPLE:
        raise Refused('Explicit refreshing people index required')
    if type(photos_per_person) is not int or not 1 <= photos_per_person <= MAX_PHOTOS:
        raise Refused('Invalid photo limit')
    with budget.attempt(db, lambda: False) as (check, read):
        source = d.index_source(index, read)
        _validate_frozen_source(index, source)
        approved_asset_ids = {assignment.asset_id for assignment in index.assignments}
        targets = []
        for person in index.people:
            check()
            candidates = _candidate_assets(read, index.library_id, person.id,
                                           approved_asset_ids, photos_per_person)
            selected = candidates[:photos_per_person]
            assets = []
            for asset_id in selected:
                check()
                faces = read('''SELECT f.id FROM face_detections f
                    JOIN assets a ON a.id=f.asset_id
                    JOIN access_asset_libraries m ON m.asset_id=a.id
                    WHERE m.library_id=? AND (a.status='active' OR a.status IS NULL)
                      AND f.asset_id=? AND f.person_id=? AND f.label_source='manual'
                    ORDER BY f.id LIMIT ?''',
                    (index.library_id, int(asset_id), int(person.id), MAX_FACES_PER_PHOTO + 1))
                if len(faces) > MAX_FACES_PER_PHOTO:
                    raise Refused('Too many candidate faces')
                assets.append({'asset_id': asset_id, 'faces': [
                    {'face_id': str(row[0]), 'label_source': 'manual',
                     'identity_confirmed': False, 'search_eligible': False}
                    for row in faces]})
            targets.append({'person_id': person.id, 'label': person.label,
                            'assets': assets, 'has_more': len(candidates) > photos_per_person})
        check()
    binding = d.digest({'reviewed_index': asdict(index), 'current_source': d.digest(source),
                        'photos_per_person': photos_per_person, 'targets': targets})
    return {'schema': 1, 'status': 'requires_explicit_review',
            'library_id': index.library_id, 'reviewed_index_digest': d.digest(asdict(index)),
            'current_source_digest': d.digest(source), 'proposal_binding_digest': binding,
            'photos_per_person': photos_per_person, 'targets': targets}


def main(argv=None):
    parser = Parser(allow_abbrev=False, description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--reviewed-index', type=Path, required=True)
    parser.add_argument('--photos-per-person', type=int, default=6)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--deletion-journal', type=Path)
    parser.add_argument('--deletion-namespace')
    try:
        args = parser.parse_args(argv)
        library_id = producer.library(args.library)
        if not 1 <= args.photos_per_person <= MAX_PHOTOS:
            raise Refused('Invalid photo limit')
        # The primary database follows the repository's existing direct,
        # regular-file read-only boundary; owner-private ACL is required for
        # the proposal/index/journal, not imposed on the service-owned DB.
        producer.direct(args.database)
        _input(args.reviewed_index, maximum=d.ReadBudget().index_bytes)
        if args.out in (args.database, args.reviewed_index):
            raise Refused('Output aliases an input')
        if (args.deletion_journal is None) != (args.deletion_namespace is None):
            raise Refused('Deletion history options must be paired')
        if args.deletion_journal is not None:
            _input(args.deletion_journal)
        require_private_directory(args.out.parent)
        producer.direct(args.out)
        try:
            if args.out.exists() or args.out.is_symlink():
                raise Refused('Output must be new')
        except OSError:
            raise Refused('Output unavailable') from None
        payload = read_index(args.reviewed_index, d.ReadBudget().index_bytes)
        index = parse_index(payload, d.ReadBudget().rows)
        if type(index) is not RefreshingPeopleIndex or index.library_id != library_id:
            raise Refused('Refreshing people index required')
        with open_reviewed_people_source(producer, args.database, time.monotonic(),
                deletion_journal=args.deletion_journal,
                deletion_namespace=args.deletion_namespace) as db:
            result = inspect(db, index, args.photos_per_person)
        encoded = d.packed(result)
        output_sha256 = producer.write_new(args.out, encoded)
        require_private_file(args.out)
        print(json.dumps({'completed': True, 'database_modified': False,
            'identity_approval': False, 'people': len(result['targets']),
            'candidate_photos': sum(len(item['assets']) for item in result['targets']),
            'output_sha256': output_sha256, 'output_bytes': len(encoded)}, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print('Interrupted; inspect any new output before reuse.', file=sys.stderr)
        return 130
    except Exception:
        print('People review candidate inspection refused or incomplete.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

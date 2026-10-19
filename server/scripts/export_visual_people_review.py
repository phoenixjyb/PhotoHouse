#!/usr/bin/env python3
"""Export a bounded, source-bound manual visual review selection.

This offline operator tool only exports explicit, current owner confirmations.
It never writes to the library database or activates a search index.
"""
from dataclasses import asdict
import argparse
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts')]

from app.access import discovery as d
from app.access.discovery_index import read as read_index, index as parse_index
from app.access.discovery_provider import MemoryIndexProvider, RefreshingPeopleIndex
from app.access.people_review import PeopleReview
from app.access.private_storage import require_private_directory, require_private_file
import inspect_reviewed_people_readiness as selection_tool
import prepare_access_discovery_index as producer
from reviewed_people_source import open_reviewed_people_source

MAX_NEW_FACES = 12


class Refused(RuntimeError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise Refused('Invalid arguments')


class _ReviewProducer:
    """Per-connection producer wrapper for PeopleReview's tiny SQL function set."""
    def authorize(self, action, first, second, *rest):
        if action == sqlite3.SQLITE_FUNCTION and second in {'max', 'coalesce', 'substr'}:
            return sqlite3.SQLITE_OK
        return producer.authorize(action, first, second, *rest)

    def open_read_only(self, path, start):
        db = producer.open_read_only(path, start)
        db.set_authorizer(self.authorize)
        return db

    def __getattr__(self, name):
        return getattr(producer, name)


class _ReadOnlyAccess:
    """Minimal People helper context; the reviewed source already owns BEGIN."""
    def __init__(self, db, clock):
        self.db, self.clock = db, clock

    def _now(self):
        return int(self.clock())


def _private_input(path, maximum):
    producer.direct(path)
    require_private_file(path)
    if path.stat().st_size > maximum:
        raise Refused('Input too large')
    return path


def _reviewer(value):
    if type(value) is not str:
        raise Refused('Invalid reviewer')
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        raise Refused('Invalid reviewer') from None
    if str(parsed) != value:
        raise Refused('Invalid reviewer')
    return value


def _active_owner(db, library, account_id, now):
    row = db.execute('''SELECT m.revision FROM access_memberships m
        JOIN access_accounts a ON a.id=m.account_id
        JOIN access_libraries l ON l.id=m.library_id
        WHERE m.account_id=? AND m.library_id=? AND m.role='owner'
          AND m.status='approved' AND a.state='active' AND l.state='active'
          AND (m.expires_at IS NULL OR m.expires_at>?)''',
        (account_id, library, now)).fetchone()
    if not row:
        raise Refused('Current active owner required')
    return row[0]


def export(db, index, selection, reviewer_account, *, now=None):
    """Validate an exact roster and export only newly confirmed manual faces."""
    budget = d.ReadBudget()
    d.validate(index, index.library_id, budget.rows)
    if type(index) is not RefreshingPeopleIndex:
        raise Refused('Refreshing people index required')
    selected = selection_tool.validate_selection(selection, index.library_id, budget.rows)
    if reviewer_account != _reviewer(reviewer_account):
        raise Refused('Invalid reviewer')
    roster = {person.id: person for person in index.people}
    selected_roster = {person['id']: person['label'] for person in selected['people']}
    if (set(selected_roster) != set(roster) or any(
            selected_roster[person_id] != person.label for person_id, person in roster.items())):
        raise Refused('Selected roster does not match reviewed index')

    old = {(item.id, item.asset_id, item.person_id, item.source) for item in index.assignments}
    supplied = {(item['id'], item['asset_id'], item['person_id'], item['source'])
                for item in selected['assignments']}
    if not old <= supplied:
        raise Refused('Existing approved assignments must be preserved')
    additions = supplied - old
    if not additions or len(additions) > MAX_NEW_FACES:
        raise Refused('One to twelve new explicit faces required')

    # The private selection intentionally retains reviewed labels; no private
    # media values are exported. The source boundary rechecks deletion history.
    checked_at = int(time.time()) if now is None else now
    service = PeopleReview(_ReadOnlyAccess(db, lambda: checked_at),
                           MemoryIndexProvider((index,)), budget)
    with budget.attempt(db, lambda: False) as (check, read):
        membership_revision = _active_owner(db, index.library_id, reviewer_account, checked_at)
        current = service._index(index.library_id, read, check)
        if current != index:
            raise Refused('Reviewed index changed')
        evidence = []
        for face_id, asset_id, person_id, source in sorted(additions, key=lambda row: int(row[0])):
            check()
            if source != 'manual' or person_id not in roster:
                raise Refused('Only explicit manual faces under reviewed people are allowed')
            row = service._face(int(face_id), index.library_id)
            target = service._target(int(person_id), index.library_id, index)
            if (str(row[0]), str(row[1]), str(row[2]), row[3]) != (
                    face_id, asset_id, person_id, 'manual'):
                raise Refused('Selected face or target changed')
            member = {'account_id': reviewer_account, 'revision': membership_revision}
            proof, _action, saved = service._record(member, index.library_id, row, target)
            if saved is None:
                raise Refused('Current owner confirmation required')
            audit_id = saved[0]
            audit = db.execute('''SELECT actor_account,library_id,action FROM access_audit
                WHERE id=?''', (audit_id,)).fetchone()
            if audit != (reviewer_account, index.library_id, 'face.review.' + proof):
                raise Refused('Confirmation evidence changed')
            evidence.append({'face_id': face_id, 'asset_id': asset_id,
                'person_id': person_id, 'confirmation_proof': proof, 'audit_id': str(audit_id)})
        check()

    assignments = sorted(supplied, key=lambda row: int(row[0]))
    packet = {'schema': 1, 'status': 'requires_source_bound_preparation',
        'library_id': index.library_id, 'base_index_digest': d.digest(asdict(index)),
        'selection': {'schema': 1, 'library_id': index.library_id,
            'people': [{'id': person.id, 'label': person.label} for person in index.people],
            'assignments': [{'id': face, 'asset_id': asset, 'person_id': person,
                             'source': source}
                            for face, asset, person, source in assignments]},
        'confirmation_evidence': evidence}
    if len(d.packed(packet)) > min(64 * 1024, budget.response_bytes):
        raise Refused('Export exceeds output budget')
    return packet


def main(argv=None):
    parser = Parser(allow_abbrev=False, description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--reviewed-index', type=Path, required=True)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--reviewer-account', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--deletion-journal', type=Path)
    parser.add_argument('--deletion-namespace')
    try:
        args = parser.parse_args(argv)
        library = producer.library(args.library)
        if (args.deletion_journal is None) != (args.deletion_namespace is None):
            raise Refused('Deletion history options must be paired')
        _private_input(args.reviewed_index, d.ReadBudget().index_bytes)
        _private_input(args.selection, 1024 * 1024)
        if args.deletion_journal is not None:
            _private_input(args.deletion_journal, 16 * 1024 * 1024)
        require_private_directory(args.out.parent)
        producer.direct(args.out)
        if args.out in (args.database, args.reviewed_index, args.selection, args.deletion_journal):
            raise Refused('Output aliases an input')
        if args.out.exists() or args.out.is_symlink():
            raise Refused('Output must be new')
        index_payload = read_index(args.reviewed_index, d.ReadBudget().index_bytes)
        index = parse_index(index_payload, d.ReadBudget().rows)
        if type(index) is not RefreshingPeopleIndex or index.library_id != library:
            raise Refused('Refreshing people index required')
        selection = producer.review_json(args.selection)
        reviewer = _reviewer(args.reviewer_account)
        with open_reviewed_people_source(_ReviewProducer(), args.database, time.monotonic(),
                deletion_journal=args.deletion_journal,
                deletion_namespace=args.deletion_namespace) as db:
            result = export(db, index, selection, reviewer)
        payload = d.packed(result)
        output_sha256 = producer.write_new(args.out, payload)
        require_private_file(args.out)
        print(json.dumps({'new_confirmations': len(result['confirmation_evidence']),
            'total_assignments': len(result['selection']['assignments']),
            'base_index_digest': result['base_index_digest'],
            'output_sha256': output_sha256, 'output_bytes': len(payload)}, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        print('Interrupted; inspect any new output before reuse.', file=sys.stderr)
        return 130
    except Exception:
        print('Visual people review export refused or incomplete.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

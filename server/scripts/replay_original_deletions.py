#!/usr/bin/env python3
"""Review or explicitly replay an external PhotoHouse original-deletion journal."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
import rehearse_fullsize_database as full
import initialize_original_deletions as deletion_schema
from app.access.runtime import COLLABORATION_REVISIONS

from app.access.original_deletions import OriginalDeletionError, OriginalDeletionJournal


def _existing_regular(path, label):
    value = Path(path)
    if not value.is_absolute():
        raise OriginalDeletionError(label + ' path must be absolute')
    try:
        info = value.lstat()
    except OSError:
        raise OriginalDeletionError(label + ' path is unavailable') from None
    if not value.is_file() or value.is_symlink():
        raise OriginalDeletionError(label + ' must be a regular file')
    for suffix in ('-journal','-wal','-shm'):
        if os.path.lexists(str(value)+suffix):
            raise OriginalDeletionError(label + ' has an unexpected SQLite sidecar')
    return value


def _read_only_db(path):
    uri = Path(path).as_uri() + '?mode=ro'
    db = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA query_only=ON')
    return db


def _logical_digest(path, budget):
    db = _read_only_db(path)
    try:
        db.row_factory = None
        state = deletion_schema._database_state(db, budget)
        return state['tables'], state['fingerprint']
    except (sqlite3.Error, full.small.Refused):
        raise OriginalDeletionError('Separate backup is not a valid collaboration database') from None
    finally:
        db.close()


def _writable_db(path):
    uri = Path(path).as_uri() + '?mode=rw'
    db = sqlite3.connect(uri, uri=True, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, help='restored primary SQLite file')
    parser.add_argument('--journal', required=True, help='external deletion journal SQLite file')
    parser.add_argument('--backup-path', required=True, help='separate verified backup copy retained for rollback')
    parser.add_argument('--namespace', required=True, help='expected canonical dataset namespace UUID')
    parser.add_argument('--expected-sequence', required=True, type=int,
                        help='operator-reviewed external journal sequence')
    parser.add_argument('--expected-digest', required=True,
                        help='operator-reviewed external journal head SHA-256')
    parser.add_argument('--max-bytes', type=int, default=1024 * 1024 * 1024,
                        help='bounded logical database verification budget')
    parser.add_argument('--timeout-seconds', type=int, default=300,
                        help='bounded verification time budget')
    parser.add_argument('--execute', action='store_true', help='apply replay; default is read-only review')
    parser.add_argument('--all-writers-stopped', action='store_true',
                        help='operator attestation required for --execute')
    args = parser.parse_args(argv)

    try:
        database = _existing_regular(args.database, 'Primary database')
        backup = _existing_regular(args.backup_path, 'Separate backup')
        journal_path = Path(args.journal)
        if not journal_path.is_absolute():
            raise OriginalDeletionError('Journal path must be absolute')
        journal_info=journal_path.lstat()
        identities_expected = tuple((item.st_dev,item.st_ino) for item in
                                    (database.lstat(),backup.lstat(),journal_info))
        identities=set(identities_expected)
        if len(identities) != 3:
            raise OriginalDeletionError('Primary, journal, and backup must be separate files')
        budget = full.Budget(args.max_bytes, args.timeout_seconds)
        backup_tables, backup_digest = _logical_digest(backup, budget)
        candidate_tables, candidate_digest = _logical_digest(database, budget)
        if backup_tables != candidate_tables or backup_digest != candidate_digest:
            raise OriginalDeletionError('Backup does not match restored candidate')
        journal = OriginalDeletionJournal(journal_path, args.namespace)
        namespace, head_seq, head_digest = journal.head()
        if (namespace != args.namespace or head_seq != args.expected_sequence
                or head_digest != args.expected_digest):
            raise OriginalDeletionError('Journal head differs from explicit expected values')
        if args.execute and not args.all_writers_stopped:
            raise OriginalDeletionError('--execute requires --all-writers-stopped')

        db = _writable_db(database) if args.execute else _read_only_db(database)
        try:
            reviewed = journal.review(db)
            marker_seq, marker_digest = journal._primary_marker(db)
            plan = {'namespace': namespace, 'journal_sequence': reviewed['sequence'],
                    'journal_digest': reviewed['digest'], 'primary_sequence': marker_seq,
                    'primary_digest': marker_digest, 'pending_records': reviewed['pending_count'],
                    'candidate_digest': candidate_digest,
                    'mode': 'execute' if args.execute else 'read-only-review'}
            if args.execute:
                expected_head = (namespace, head_seq, head_digest)
                def recheck_files(primary):
                    _existing_regular(args.database, 'Primary database')
                    _existing_regular(args.backup_path, 'Separate backup')
                    _existing_regular(journal_path, 'Journal')
                    pair_now = tuple((path.stat().st_dev, path.stat().st_ino)
                                     for path in (database, backup, journal_path))
                    if pair_now != identities_expected:
                        raise OriginalDeletionError('Reviewed files changed')
                    if _logical_digest(backup, budget) != (backup_tables, backup_digest):
                        raise OriginalDeletionError('Reviewed backup changed')
                    if (full.small.revision(primary) not in COLLABORATION_REVISIONS
                            or full.schema(primary) != candidate_tables
                            or full.fingerprint(primary, candidate_tables, budget)[0] != candidate_digest):
                        raise OriginalDeletionError('Restored candidate changed')
                result = journal.replay(db, expected_head=expected_head,
                                        precommit_guard=recheck_files)
                plan['replay'] = {'namespace': result[0], 'sequence': result[1],
                                  'digest': result[2], 'applied_records': result[3]}
            else:
                if marker_seq > head_seq:
                    raise OriginalDeletionError('Primary marker is ahead of journal')
                plan['primary_matches_history'] = (
                    journal.history_digest(marker_seq) == marker_digest)
                if not plan['primary_matches_history']:
                    raise OriginalDeletionError('Primary marker is outside journal history')
            print(json.dumps(plan, sort_keys=True))
        finally:
            db.close()
        return 0
    except (OriginalDeletionError, full.small.Refused):
        print('original-deletion replay refused: validation failed', file=sys.stderr)
        return 2
    except (sqlite3.Error, OSError):
        print('original-deletion replay refused: validation failed', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

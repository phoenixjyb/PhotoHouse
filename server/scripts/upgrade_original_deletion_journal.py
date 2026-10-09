#!/usr/bin/env python3
"""Qualify an offline V1 deletion journal and explicitly upgrade it to V2.

Review is read-only. Execution requires an operator attestation that every
writer is stopped. The primary is locked and rechecked before the journal DDL;
neither primary data nor backup files are changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

import initialize_original_deletions as deletion_schema
import rehearse_fullsize_database as full
from app.access.family_note_identity_schema import IDENTITY_REVISION
from app.access.original_deletions import OriginalDeletionJournal
from app.access.private_storage import require_private_file


def _regular_private(path, label, budget):
    path = Path(path)
    full.small.direct(path)
    full.small.no_sidecars(path)
    try:
        record = path.lstat()
        if not stat.S_ISREG(record.st_mode) or path.resolve(strict=True) != path:
            raise full.small.Refused('Direct regular input required')
        if record.st_size > budget.max_bytes:
            raise full.small.Refused('Input exceeds explicit size budget')
        require_private_file(path)
    except (OSError, ValueError, PermissionError):
        raise full.small.Refused(label + ' is unavailable or not private') from None
    return path


def _digest_file(path, budget):
    digest = hashlib.sha256()
    total = 0
    with open(path, 'rb', buffering=0) as stream:
        while True:
            budget.check()
            block = stream.read(1024 * 1024)
            if not block:
                break
            total += len(block)
            if total > budget.max_bytes:
                raise full.small.Refused('Input exceeds explicit size budget')
            digest.update(block)
    return digest.hexdigest()


def _identity(path):
    return full.small.identity(path)


def _state(path, budget):
    return deletion_schema._read_state(path, budget)


class _BoundedJournal(OriginalDeletionJournal):
    def __init__(self, path, namespace, budget):
        self._budget = budget
        super().__init__(path, namespace)

    def _connect(self, *, validate=True):
        db = super()._connect(validate=validate)
        try:
            self._budget.configure(db)
        except BaseException:
            db.close()
            raise
        return db


def _format(journal):
    db = journal._connect()
    try:
        db.execute('BEGIN')
        row = db.execute('SELECT format FROM journal_meta WHERE id=1').fetchone()
        if row is None:
            raise full.small.Refused('Deletion journal format is invalid')
        return row[0]
    finally:
        db.close()


def _probe_committed_v2(path, namespace, expected_head, expected_identity):
    """Use a short independent read to detect a ledger commit after an error."""
    db = None
    try:
        path = Path(path)
        size = path.lstat().st_size
        budget = full.Budget(max(1024 * 1024, size), 2)
        _regular_private(path, 'Journal', budget)
        if _identity(path) != expected_identity:
            return False
        deadline = budget.deadline
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                             timeout=1, isolation_level=None)
        budget.configure(db)
        db.execute('PRAGMA query_only=ON')
        db.set_progress_handler(lambda: time.monotonic() >= deadline, 1000)
        row = db.execute('''SELECT format,namespace,head_seq,head_digest
            FROM journal_meta WHERE id=1''').fetchone()
        return row == ('photohouse-original-deletion-journal-v2', *expected_head)
    except Exception:
        return False
    finally:
        if db is not None:
            db.close()


def _check_journal_pair(primary_journal, backup_journal, namespace, expected_head, budget):
    journal = _BoundedJournal(primary_journal, namespace, budget)
    backup = _BoundedJournal(backup_journal, namespace, budget)
    primary_head = journal.head()
    backup_head = backup.head()
    primary_format = _format(journal)
    backup_format = _format(backup)
    if primary_head != expected_head:
        raise full.small.Refused('Journal head differs from explicit expected values')
    if backup_head != primary_head or backup_format != primary_format:
        raise full.small.Refused('Journal backup differs from reviewed journal')
    if primary_format.endswith('v2'):
        raise full.small.Refused('V2 journals cannot be downgraded or retried')
    if not primary_format.endswith('v1'):
        raise full.small.Refused('V1 journal required')
    journal_hash = _digest_file(primary_journal, budget)
    backup_hash = _digest_file(backup_journal, budget)
    if journal_hash != backup_hash:
        raise full.small.Refused('Journal backup bytes differ from reviewed journal')
    return journal, primary_head, journal_hash


def _open_primary(path, budget, *, writable=False):
    mode = 'rw' if writable else 'ro'
    db = sqlite3.connect(path.as_uri() + '?mode=' + mode, uri=True,
                         timeout=3, isolation_level=None)
    budget.configure(db)
    db.execute('PRAGMA foreign_keys=ON')
    if not writable:
        db.execute('PRAGMA query_only=ON')
    return db


def _review_primary(path, journal, budget, expected_head):
    full.small.no_sidecars(path)
    state = _state(path, budget)
    if state['revision'] != IDENTITY_REVISION:
        raise full.small.Refused('D1 family note identity schema required')
    if state['marker_rows'] != 1:
        raise full.small.Refused('Exact primary deletion marker required')
    db = _open_primary(path, budget)
    try:
        reviewed = journal.review(db)
        marker = journal._primary_marker(db)
        if (reviewed['sequence'], reviewed['digest']) != expected_head[1:] or marker != expected_head[1:]:
            raise full.small.Refused('Primary marker must exactly match journal head')
        if reviewed['pending_count'] != 0:
            raise full.small.Refused('Journal has pending primary records')
        return state, reviewed
    finally:
        db.close()


def qualify(database, backup, journal_path, journal_backup, namespace, expected_sequence,
            expected_digest, budget, *, execute=False, all_writers_stopped=False,
            state=None):
    state = state if state is not None else {}
    if execute and not all_writers_stopped:
        raise full.small.Refused('Execution requires --all-writers-stopped')
    if not execute and all_writers_stopped:
        raise full.small.Refused('--all-writers-stopped requires --execute')
    namespace = deletion_schema._namespace(namespace)
    if (type(expected_sequence) is not int or expected_sequence < 0 or
            type(expected_digest) is not str or
            re.fullmatch(r'[0-9a-f]{64}', expected_digest) is None):
        raise full.small.Refused('Explicit canonical journal head required')
    paths = tuple(_regular_private(path, label, budget) for path, label in (
        (database, 'Primary'), (backup, 'Primary backup'),
        (journal_path, 'Journal'), (journal_backup, 'Journal backup')))
    database, backup, journal_path, journal_backup = paths
    identities = tuple(_identity(path) for path in paths)
    if len(set(identities)) != 4:
        raise full.small.Refused('All four inputs must be separate files')

    primary_state = _state(database, budget)
    backup_state = _state(backup, budget)
    if primary_state['revision'] != IDENTITY_REVISION:
        raise full.small.Refused('D1 family note identity schema required')
    if (primary_state['tables'] != backup_state['tables'] or
            primary_state['fingerprint'] != backup_state['fingerprint']):
        raise full.small.Refused('Primary backup does not match primary')
    backup_hash = _digest_file(backup, budget)

    expected_head = (namespace, expected_sequence, expected_digest)
    journal, head, journal_hash = _check_journal_pair(
        journal_path, journal_backup, namespace, expected_head, budget)
    primary_review, journal_review = _review_primary(database, journal, budget, head)
    if (primary_review['tables'] != primary_state['tables'] or
            primary_review['fingerprint'] != primary_state['fingerprint']):
        raise full.small.Refused('Primary changed during qualification review')
    if (tuple(_identity(path) for path in paths) != identities or
            _digest_file(backup, budget) != backup_hash or
            _digest_file(journal_path, budget) != journal_hash or
            _digest_file(journal_backup, budget) != journal_hash):
        raise full.small.Refused('Reviewed file or backup changed during qualification')
    state['durable_upgrade'] = False
    report = {'status': 'reviewed', 'mode': 'read-only-review',
              'schema_revision': primary_state['revision'],
              'table_count': len(primary_state['tables']),
              'primary_rows': sum(primary_state['counts'].values()),
              'original_rows': sum(primary_state['originals'].values()),
              'journal_format_version': 1, 'journal_sequence': head[1],
              'journal_digest': head[2], 'pending_records': journal_review['pending_count'],
              'logical_fingerprint': primary_state['fingerprint'],
              'journal_backup_sha256': journal_hash}
    state['report'] = report
    if not execute:
        return report

    full.small.no_sidecars(database)
    db = _open_primary(database, budget, writable=True)
    try:
        db.execute('PRAGMA synchronous=FULL')
        if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
            raise full.small.Refused('Offline primary must use DELETE journaling')
        db.execute('BEGIN EXCLUSIVE')

        def locked_guard(primary_db):
            if not primary_db.in_transaction:
                raise full.small.Refused('Primary exclusive lock required')
            for path, expected in zip(paths, identities):
                _regular_private(path, 'Reviewed input', budget)
                if _identity(path) != expected:
                    raise full.small.Refused('Reviewed file identity changed')
            if _digest_file(journal_backup, budget) != journal_hash:
                raise full.small.Refused('Journal backup changed after review')
            if _digest_file(backup, budget) != backup_hash:
                raise full.small.Refused('Primary backup changed after review')
            if _digest_file(journal_path, budget) != journal_hash:
                raise full.small.Refused('Journal bytes changed after review')
            current = deletion_schema._database_state(primary_db, budget)
            if (current['revision'] != IDENTITY_REVISION or
                    current['tables'] != primary_state['tables'] or
                    current['fingerprint'] != primary_state['fingerprint'] or
                    current['marker_rows'] != 1):
                raise full.small.Refused('Locked primary changed after review')
            saved = _state(backup, budget)
            if (saved['tables'] != primary_state['tables'] or
                    saved['fingerprint'] != primary_state['fingerprint']):
                raise full.small.Refused('Primary backup changed after review')
            if journal._primary_marker(primary_db) != head[1:]:
                raise full.small.Refused('Primary marker changed')

        try:
            journal.upgrade_family_format(db, expected_head=head,
                                          precommit_guard=locked_guard)
            state['durable_upgrade'] = True
            db.commit()
        except BaseException:
            # The ledger commit is independent of the primary transaction. Detect
            # a completed ledger upgrade without relying on the expired review budget.
            state['durable_upgrade'] = state.get('durable_upgrade', False) or _probe_committed_v2(
                journal_path, namespace, head, identities[2])
            db.rollback()
            raise
    finally:
        db.close()

    state['durable_upgrade'] = True
    for path in paths:
        _regular_private(path, 'Reviewed input', budget)
    if tuple(_identity(path) for path in paths) != identities:
        raise full.small.Refused('Reviewed file identity changed during upgrade verification')
    after_journal = _BoundedJournal(journal_path, namespace, budget)
    if after_journal.head() != head or _format(after_journal) != 'photohouse-original-deletion-journal-v2':
        raise full.small.Refused('Upgraded journal head or format failed verification')
    after_state, after_review = _review_primary(database, after_journal, budget, head)
    if (after_state['tables'] != primary_state['tables'] or
            after_state['fingerprint'] != primary_state['fingerprint'] or
            after_review['pending_count'] != 0):
        raise full.small.Refused('Primary changed during journal upgrade')
    if (_digest_file(backup, budget) != backup_hash or
            _digest_file(journal_backup, budget) != journal_hash):
        raise full.small.Refused('A verified backup changed during upgrade verification')
    for path in paths:
        _regular_private(path, 'Reviewed input', budget)
    if tuple(_identity(path) for path in paths) != identities:
        raise full.small.Refused('Reviewed file identity changed during upgrade verification')
    report.update({'status': 'upgraded', 'mode': 'execute', 'journal_format_version': 2,
                   'primary_unchanged': True, 'journal_backup_unchanged': True})
    state['report'] = report
    return report


def _parser():
    parser = full.small.Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--backup', type=Path, required=True,
                        help='separate logically identical primary backup')
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--journal-backup', type=Path, required=True,
                        help='separate byte-identical private journal backup')
    parser.add_argument('--namespace', required=True)
    parser.add_argument('--expected-sequence', type=int, required=True)
    parser.add_argument('--expected-digest', required=True)
    parser.add_argument('--max-bytes', type=int, default=1024 * 1024 * 1024)
    parser.add_argument('--timeout-seconds', type=int, default=300)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--all-writers-stopped', action='store_true')
    return parser


def main(argv=None):
    state = {}
    try:
        args = _parser().parse_args(argv)
        result = qualify(args.database, args.backup, args.journal, args.journal_backup,
                         args.namespace, args.expected_sequence, args.expected_digest,
                         full.Budget(args.max_bytes, args.timeout_seconds),
                         execute=args.execute, all_writers_stopped=args.all_writers_stopped,
                         state=state)
        print(json.dumps(result, sort_keys=True))
        return 0
    except KeyboardInterrupt:
        if state.get('durable_upgrade'):
            _incomplete(state)
        else:
            print(json.dumps({'status': 'refused'}, sort_keys=True))
        return 130
    except Exception:
        if state.get('durable_upgrade'):
            _incomplete(state)
        else:
            print(json.dumps({'status': 'refused'}, sort_keys=True))
        return 2


def _incomplete(state):
    reviewed = state.get('report')
    report = {'status': 'upgraded_verification_incomplete'}
    if reviewed:
        for key in ('schema_revision', 'table_count', 'primary_rows', 'original_rows',
                    'journal_sequence', 'journal_digest', 'logical_fingerprint'):
            if key in reviewed:
                report[key] = reviewed[key]
    print(json.dumps(report, sort_keys=True))


if __name__ == '__main__':
    raise SystemExit(main())

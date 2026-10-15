#!/usr/bin/env python3
"""Read-only search readiness and private relevance checks for one library.

Run on the data-owning host with explicit existing paths. No listeners, login,
index approval, data migration, media opening, speech, or model invocation.
Token, case and report files must be outside repositories in private storage.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import time

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / 'backend'))

from app.access import discovery as d
from app.access.assistant_search import SearchRuntime
from app.access.discovery_transport import DiscoveryRuntime
from app.access.private_storage import require_private_directory, require_private_file, stable_stat_identity
from app.access.runtime import ExistingDatabase
from app.access.transport import AccessRuntime


class Refused(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused()


def selected(path, *, private=False, output=False):
    path = Path(path)
    if (not path.is_absolute() or '..' in path.parts
            or path.anchor.startswith(('//', '\\\\'))):
        raise Refused()
    for parent in (path.parent, *path.parent.parents):
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or getattr(info, 'st_file_attributes', 0) & 0x400
                or (parent / '.git').exists()):
            raise Refused()
    if output:
        if os.path.lexists(path):
            raise Refused()
    else:
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or getattr(info, 'st_file_attributes', 0) & 0x400):
            raise Refused()
    if private:
        require_private_directory(path.parent)
        if not output:
            require_private_file(path)
    return path


def private_bytes(path, limit):
    selected(path, private=True)
    before = path.stat()
    if not 0 < before.st_size <= limit:
        raise Refused()
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        payload = stream.read(limit + 1)
        after = os.fstat(stream.fileno())
    selected(path, private=True)
    if (not stat.S_ISREG(opened.st_mode) or len(payload) > limit
            or not stable_stat_identity(before) == stable_stat_identity(opened)
            == stable_stat_identity(after) == stable_stat_identity(path.stat())):
        raise Refused()
    return payload


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise Refused()
        value[key] = item
    return value


def cases_file(path):
    return json.loads(private_bytes(path, 1024 * 1024).decode('utf-8'),
                      object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(Refused()))


class SelectedIndex:
    """Load the selected artifact only after the service's membership check."""
    def __init__(self, path, budget):
        self.path, self.budget = path, budget

    def get(self, library):
        if self.path is None:
            return None
        from app.access.discovery_index import load
        try:
            return load((self.path,), budget=self.budget).get(library)
        except Exception:
            raise d.DiscoveryUnavailable() from None


def deletion_guard(path, namespace):
    from app.access.original_deletions import OriginalDeletionJournal, OriginalDeletionError

    class ReadOnlyJournal(OriginalDeletionJournal):
        def _connect(self, *, validate=True):
            if validate:
                self._validate_file()
            db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True,
                                 timeout=3, isolation_level=None)
            try:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA query_only=ON')
                db.execute('PRAGMA trusted_schema=OFF')
                db.execute('PRAGMA foreign_keys=ON')
                if db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                    raise OriginalDeletionError('Deletion journal unavailable')
                return db
            except BaseException:
                db.close()
                raise

    return ReadOnlyJournal(path, namespace)


def inspect_search(engine, token, library, *, cases=None, clock=time.time):
    engine.authorize(token, library)
    try:
        readiness = engine.call('readiness', token, library, lambda: False, {})
        evaluation = None
        if cases is not None:
            from app.access.search_evaluation import evaluate_cases
            evaluation = evaluate_cases(engine, token, library, cases, clock=clock)
        engine.call('presentation', token, library, lambda: False,
                    {'binding': readiness['binding']})
        return {'version': 1, 'status': 'current', 'readiness': readiness,
                'evaluation': evaluation}
    except (d.DiscoveryChanged, d.DiscoveryUnavailable, d.DiscoveryBusy) as error:
        # Discard earlier counts/scores if any source boundary fails.
        reason = {d.DiscoveryChanged: 'source_changed', d.DiscoveryUnavailable: 'source_unavailable',
                  d.DiscoveryBusy: 'source_busy'}[type(error)]
        return {'version': 1, 'status': reason, 'readiness': None, 'evaluation': None}


def write_report(path, report):
    selected(path, private=True, output=True)
    payload = json.dumps(report, ensure_ascii=True, sort_keys=True,
                         separators=(',', ':'), allow_nan=False).encode('ascii') + b'\n'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_NOFOLLOW', 0)
                 | getattr(os, 'O_BINARY', 0), 0o600)
    with os.fdopen(fd, 'wb') as stream:
        require_private_file(path)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def main(argv=None):
    parser = Parser(allow_abbrev=False, description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--library', required=True)
    parser.add_argument('--index', type=Path)
    parser.add_argument('--token-file', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cases', type=Path)
    parser.add_argument('--kinship', type=Path)
    parser.add_argument('--deletion-journal', type=Path)
    parser.add_argument('--deletion-namespace')
    try:
        args = parser.parse_args(argv)
        selected(args.out, private=True, output=True)
        selected(args.database)
        if args.index is not None:
            selected(args.index)
        token = private_bytes(args.token_file, 4096).decode('ascii').strip()
        if re.fullmatch(r'[A-Za-z0-9_-]{43}', token) is None:
            raise Refused()
        d.text(args.library, 128)
        document = cases_file(args.cases) if args.cases is not None else None
        if (args.deletion_journal is None) != (args.deletion_namespace is None):
            raise Refused()
        guard = None
        if args.deletion_journal is not None:
            selected(args.deletion_journal, private=True)
            guard = deletion_guard(args.deletion_journal, args.deletion_namespace)
        access = AccessRuntime(ExistingDatabase(args.database, read_only=True, original_deletions=guard),
                               'https://offline-search.invalid')
        budget = d.ReadBudget()
        discovery = DiscoveryRuntime(access, SelectedIndex(args.index, budget), budget)
        kinship = None
        if args.kinship is not None:
            from app.access.kinship import PrivateKinshipProvider
            kinship = PrivateKinshipProvider(args.kinship, source_root=SERVER.parent)
        report = inspect_search(SearchRuntime(discovery, kinship), token, args.library, cases=document)
        sha = write_report(args.out, report)
        evaluation = report['evaluation']
        summary = {'completed': True, 'status': report['status'], 'output_sha256': sha,
                   'case_count': evaluation['case_count'] if evaluation else 0,
                   'failed_count': evaluation['failed_count'] if evaluation else 0}
        print(json.dumps(summary, sort_keys=True))
        return 0 if report['status'] == 'current' and not summary['failed_count'] else 3
    except KeyboardInterrupt:
        print('Private search check interrupted; inspect any new output before reuse.', file=sys.stderr)
        return 130
    except Exception:
        # No token, query, account/library identifier, path, SQL or exception text.
        print('Private search check refused or incomplete; inspect any new output before reuse.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

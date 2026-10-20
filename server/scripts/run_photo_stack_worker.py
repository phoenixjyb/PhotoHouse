"""Explicit, one-sweep CPU photo-stack refresh; read-only preflight by default.

No scheduler, schema repair, model, original media or general task executor.
Windows execution always supervises a bounded child. A later operator-owned task
may invoke this once per sweep; importing it or serving a gallery never does so.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import sqlite3
import stat
import subprocess
import sys
import threading
import time

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / 'backend'))
sys.path.insert(0, str(SERVER / 'scripts'))

from app.access.original_deletions import OriginalDeletionJournal
from app.access.photo_stack_schema import REVISION, available
from app.access.photo_stack_worker import PhotoStackRefreshWorker
from app.access.photo_stack_index import PhotoStackCancelled, check_stopped
from app.access.private_storage import require_private_directory, require_private_file
from app.access.runtime import ExistingDatabase
from app.access.library_photo_stacks import MAX_ASSETS
from prepare_access_database import direct, identity

CHILD_SECONDS = 240
WORK_SECONDS = 225
MEMORY_LIMIT = 2 * 1024**3
PROCESS_LIMIT = 8
MINIMUM_FREE_RAM = 8 * 1024**3
MAX_DATABASE_BYTES = 8 * 1024**3
MAX_JOURNAL_BYTES = 64 * 1024**2


class Refused(ValueError):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('worker_arguments_invalid')


def _file(value):
    path = direct(Path(value))
    require_private_file(path)
    identity(path)
    return path


def _configuration(database, journal, namespace, libraries, stop_file):
    database, journal = _file(database), _file(journal)
    if database.stat().st_size > MAX_DATABASE_BYTES or journal.stat().st_size > MAX_JOURNAL_BYTES:
        raise Refused('worker_input_size_limit')
    require_private_directory(database.parent)
    if identity(database) == identity(journal):
        raise Refused('separate_journal_required')
    # Reuse the domain's exact explicit-library validation without a connection.
    PhotoStackRefreshWorker(lambda: None, libraries)
    stop_file = direct(Path(stop_file))
    require_private_directory(stop_file.parent)
    if stop_file.suffix != '.stop':
        raise Refused('explicit_stop_control_required')
    protected = {database, journal, Path(str(database) + '.photo-stack-refresh.lock')}
    protected.update(Path(str(p) + suffix) for p in (database, journal) for suffix in ('-wal', '-shm', '-journal'))
    if stop_file in protected:
        raise Refused('separate_stop_control_required')
    if os.path.lexists(stop_file):
        _file(stop_file)
        if identity(stop_file) in {identity(database), identity(journal)}:
            raise Refused('separate_stop_control_required')
    history = _PinnedJournal(journal, namespace, database=database)
    # Index publication reads the current history only. Preserve any supported
    # V1-V4 format; family-note erasure capability remains separately configured.
    return database, journal, history, stop_file


class _PinnedJournal(OriginalDeletionJournal):
    def __init__(self, path, namespace, *, database=None):
        self.selected_identity = identity(path)
        self.primary = database
        self.primary_identity = identity(database) if database is not None else None
        super().__init__(path, namespace)

    def _connect(self, *, validate=True):
        if self.primary is not None and identity(self.primary) != self.primary_identity:
            raise Refused('database_replaced')
        if identity(self.path) != self.selected_identity or self.path.stat().st_size > MAX_JOURNAL_BYTES:
            raise Refused('journal_replaced')
        if validate:
            self._validate_file()
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=3, isolation_level=None)
        try:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA cache_size=-8192')
            db.execute('PRAGMA temp_store=FILE')
            db.execute('PRAGMA mmap_size=0')
            if identity(self.path) != self.selected_identity or db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
                raise Refused('journal_replaced_or_not_quiescent')
            return db
        except BaseException:
            db.close()
            raise


class StopSignal:
    def __init__(self, stop_file, *, seconds=WORK_SECONDS, event=None, monotonic=time.monotonic):
        self.stop_file = stop_file
        self.monotonic = monotonic
        self.deadline = monotonic() + seconds
        self.event = event or threading.Event()
        self.next_file_check = 0
        self.reason = None

    def __call__(self):
        now = self.monotonic()
        if self.reason:
            return True
        if self.event.is_set():
            self.reason = 'signal'
        elif now >= self.deadline:
            self.reason = 'time_budget'
        elif now >= self.next_file_check:
            self.next_file_check = now + 0.05
            if os.path.lexists(self.stop_file):
                self.reason = 'stop_control'
        return self.reason is not None


def _factory(database, history, stopped, *, readonly, selected=None):
    selected = identity(database) if selected is None else selected
    adapter = ExistingDatabase(database, read_only=readonly, original_deletions=history)
    @contextmanager
    def connection():
        if identity(database) != selected:
            raise Refused('database_replaced')
        with adapter() as db:
            db.execute('PRAGMA cache_size=-8192')
            db.execute('PRAGMA temp_store=FILE')
            db.execute('PRAGMA mmap_size=0')
            db.set_progress_handler(lambda: int(stopped()), 1000)
            try:
                if db.execute('SELECT version_num FROM alembic_version').fetchall() != [(REVISION,)] or not available(db):
                    raise Refused('photo_stack_migration_required')
                yield db
            finally:
                db.set_progress_handler(None, 0)
    return connection


def _preflight(database, history, libraries, stopped, *, selected=None):
    counts = []
    with _factory(database, history, stopped, readonly=True, selected=selected)() as db:
        for library in libraries:
            check_stopped(stopped)
            if db.execute("SELECT 1 FROM access_libraries WHERE id=? AND state='active'", (library,)).fetchone() is None:
                raise Refused('active_library_required')
            count = db.execute('''SELECT count(*) FROM (
                SELECT a.id FROM assets a JOIN access_asset_libraries m ON m.asset_id=a.id
                WHERE m.library_id=? AND (a.status='active' OR a.status IS NULL) LIMIT ?)''',
                (library, MAX_ASSETS + 1)).fetchone()[0]
            if count > MAX_ASSETS:
                raise Refused('photo_stack_asset_limit')
            counts.append({'library_id':library, 'active_assets':count})
        history.assert_current(db)
        check_stopped(stopped)
    return {'status':'ready', 'schema_revision':REVISION, 'libraries':counts,
            'worker_executed':False, 'schema_changed':False, 'tasks_changed':False}


def preflight(database, journal, namespace, libraries, stop_file):
    started = time.monotonic()
    database, _, history, stop_file = _configuration(database, journal, namespace, libraries, stop_file)
    selected = identity(database)
    stopped = StopSignal(stop_file, seconds=max(0, WORK_SECONDS - (time.monotonic() - started)))
    if stopped():
        return {'status':'stopped', 'reason':stopped.reason, 'worker_executed':False}
    try:
        return _preflight(database, history, libraries, stopped, selected=selected)
    except PhotoStackCancelled:
        return {'status':'stopped', 'reason':stopped.reason, 'worker_executed':False}
    except sqlite3.OperationalError as error:
        if str(error) != 'interrupted' or not stopped():
            raise
        return {'status':'stopped', 'reason':stopped.reason, 'worker_executed':False}


@contextmanager
def _lock(database):
    path = Path(str(database) + '.photo-stack-refresh.lock')
    direct(path)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
    with os.fdopen(os.open(path, flags, 0o600), 'r+b', buffering=0) as stream:
        require_private_file(path)
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != identity(path):
            raise Refused('worker_lock_changed')
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise Refused('photo_stack_worker_already_running') from None
            try:
                yield
            finally:
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Refused('photo_stack_worker_already_running') from None
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)


def execute_once(database, journal, namespace, libraries, stop_file, *, event=None):
    started = time.monotonic()
    database, _, history, stop_file = _configuration(database, journal, namespace, libraries, stop_file)
    selected = identity(database)
    stopped = StopSignal(stop_file, event=event, seconds=max(0, WORK_SECONDS - (time.monotonic() - started)))
    if stopped():
        return {'status':'stopped', 'reason':stopped.reason, 'worker_executed':False}
    results = []
    executed = False
    try:
        _preflight(database, history, libraries, stopped, selected=selected)
        with _lock(database):
            check_stopped(stopped)
            worker = PhotoStackRefreshWorker(_factory(database, history, stopped, readonly=False, selected=selected), libraries, stopped=stopped)
            executed = True
            results = worker.run_once()
    except PhotoStackCancelled:
        pass
    except sqlite3.OperationalError as error:
        if str(error) != 'interrupted' or not stopped():
            raise
        # An interruption while validating a fresh connection may precede a
        # domain result. The adapter always closes/rolls back that connection.
    return {'status':'stopped' if stopped() else 'completed', 'reason':stopped.reason,
            'worker_executed':executed, 'schema_revision':REVISION, 'results':results,
            'schema_changed':False, 'tasks_changed':False, 'models_loaded':False}


def _child(arguments):
    event = threading.Event()
    previous = {number:signal.signal(number, lambda *_:event.set()) for number in (signal.SIGINT, signal.SIGTERM)}
    try:
        report = execute_once(**arguments, event=event)
        print(json.dumps(report, sort_keys=True, separators=(',', ':')))
        return 0
    except Exception:
        print('{"status":"failed","details_withheld":true}', file=sys.stderr)
        return 2
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def _bounded_execute(arguments):
    from bounded_windows_job import CheckRefused, WindowsAPI, run_bounded
    system_root = os.environ.get('SystemRoot') or os.environ.get('SYSTEMROOT')
    if not system_root:
        raise CheckRefused('system_root_unavailable')
    executable = str(Path(sys.executable).resolve())
    stop_file = direct(Path(arguments['stop_file']))
    require_private_directory(stop_file.parent)
    PhotoStackRefreshWorker(lambda: None, arguments['libraries'])
    control = str(stop_file.parent)
    environment = {'PATH':str(Path(executable).parent), 'SYSTEMROOT':system_root, 'WINDIR':system_root,
                   'TEMP':control, 'TMP':control, 'PHOTOHOUSE_NO_DOTENV':'1',
                   'PYTHONNOUSERSITE':'1', 'PYTHONDONTWRITEBYTECODE':'1'}
    # Only fixed internal function dispatch; no caller-marked child CLI bypass.
    program = ('import runpy\n' + f"raise SystemExit(runpy.run_path({str(Path(__file__).resolve())!r},run_name='photo_stack_bounded_worker')['_child']({arguments!r}))\n")
    argv = [executable, '-I', '-B', '-c', program]
    if len(subprocess.list2cmdline(argv).encode('utf-16le')) // 2 > 32766:
        raise CheckRefused('worker_command_budget')
    return run_bounded(WindowsAPI(), executable, argv,
        environment, control, timeout_seconds=CHILD_SECONDS, memory_limit=MEMORY_LIMIT,
        process_limit=PROCESS_LIMIT, minimum_free_ram=MINIMUM_FREE_RAM)


def main(argv=None):
    parser = Parser(description=__doc__)
    for name in ('database', 'journal', 'namespace', 'stop-file'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--library', action='append', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args(argv)
    arguments = {'database':args.database, 'journal':args.journal, 'namespace':args.namespace,
                 'libraries':tuple(args.library), 'stop_file':args.stop_file}
    if args.execute and os.name == 'nt':
        return _bounded_execute(arguments)
    report = execute_once(**arguments) if args.execute else preflight(**arguments)
    print(json.dumps(report, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","details_withheld":true}', file=sys.stderr)
        raise SystemExit(2) from None

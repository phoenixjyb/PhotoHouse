"""Experimental, request-local replay of exact semantic source SQL rows.

This module contains no cross-request cache. Native connections are created
read-only; a private controller may replay only whitelisted immutable rows from
the same request's first complete, stable source pass.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import math
import sqlite3
import stat
import weakref
from os import name as _os_name


_READ_PRAGMAS = frozenset({
    'data_version', 'foreign_keys', 'trusted_schema', 'query_only',
    'read_uncommitted', 'journal_mode', 'database_list', 'table_list',
    'table_info', 'table_xinfo', 'schema_version', 'user_version',
})
_WRITE_ACTIONS = frozenset(getattr(sqlite3, name) for name in (
    'SQLITE_INSERT', 'SQLITE_UPDATE', 'SQLITE_DELETE', 'SQLITE_CREATE_INDEX',
    'SQLITE_CREATE_TABLE', 'SQLITE_CREATE_TEMP_INDEX', 'SQLITE_CREATE_TEMP_TABLE',
    'SQLITE_CREATE_TEMP_TRIGGER', 'SQLITE_CREATE_TEMP_VIEW', 'SQLITE_CREATE_TRIGGER',
    'SQLITE_CREATE_VIEW', 'SQLITE_DROP_INDEX', 'SQLITE_DROP_TABLE',
    'SQLITE_DROP_TEMP_INDEX', 'SQLITE_DROP_TEMP_TABLE', 'SQLITE_DROP_TEMP_TRIGGER',
    'SQLITE_DROP_TEMP_VIEW', 'SQLITE_DROP_TRIGGER', 'SQLITE_DROP_VIEW',
    'SQLITE_CREATE_VTABLE', 'SQLITE_DROP_VTABLE', 'SQLITE_CREATE_TEMP_VTABLE',
    'SQLITE_DROP_TEMP_VTABLE',
    'SQLITE_ALTER_TABLE', 'SQLITE_REINDEX', 'SQLITE_ANALYZE', 'SQLITE_ATTACH',
    'SQLITE_DETACH', 'SQLITE_SAVEPOINT',
) if hasattr(sqlite3, name))


class RequestSnapshotConnection(sqlite3.Connection):
    """Native sqlite connection with sticky mutation tracking and read guard."""

    original_deletions = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._snapshot_open_path = None
        self._snapshot_open_identity = None
        self._snapshot_environment_valid = True
        self._snapshot_internal = False
        self._snapshot_sealed = False
        self._snapshot_authorizer = None

    def __setattr__(self, name, value):
        sealed = getattr(self, '_snapshot_sealed', False)
        internal = getattr(self, '_snapshot_internal', False)
        if sealed and not internal and name.startswith('_snapshot_'):
            object.__setattr__(self, '_snapshot_environment_valid', False)
            raise sqlite3.ProgrammingError('snapshot connection state is private')
        if (name in {'row_factory', 'text_factory', 'isolation_level', 'autocommit'}
                and sealed and not internal):
            object.__setattr__(self, '_snapshot_environment_valid', False)
        super().__setattr__(name, value)

    def _changed(self):
        if self._snapshot_sealed and not self._snapshot_internal:
            object.__setattr__(self, '_snapshot_environment_valid', False)
            raise sqlite3.ProgrammingError('snapshot connection environment is sealed')

    def create_function(self, *args, **kwargs):
        self._changed()
        return super().create_function(*args, **kwargs)

    def create_aggregate(self, *args, **kwargs):
        self._changed()
        return super().create_aggregate(*args, **kwargs)

    def create_window_function(self, *args, **kwargs):
        self._changed()
        return super().create_window_function(*args, **kwargs)

    def create_collation(self, *args, **kwargs):
        self._changed()
        return super().create_collation(*args, **kwargs)

    def set_authorizer(self, callback):
        self._changed()
        return super().set_authorizer(callback)

    def enable_load_extension(self, enabled):
        self._changed()
        return super().enable_load_extension(enabled)

    def load_extension(self, *args, **kwargs):
        self._changed()
        return super().load_extension(*args, **kwargs)

    def deserialize(self, *args, **kwargs):
        self._changed()
        return super().deserialize(*args, **kwargs)

    def set_trace_callback(self, callback):
        self._changed()
        return super().set_trace_callback(callback)

    def setconfig(self, *args, **kwargs):
        self._changed()
        return super().setconfig(*args, **kwargs)

    def setlimit(self, *args, **kwargs):
        self._changed()
        return super().setlimit(*args, **kwargs)

    def bind_open_identity(self, path, identity):
        if self._snapshot_open_identity is not None:
            raise sqlite3.ProgrammingError('snapshot identity already bound')
        object.__setattr__(self, '_snapshot_open_path', Path(path))
        object.__setattr__(self, '_snapshot_open_identity', identity)

    def seal_read_only_environment(self):
        if (self.row_factory is not None or self.text_factory is not str
                or self.in_transaction or self.total_changes != 0):
            raise sqlite3.OperationalError('unsupported snapshot environment')
        self._snapshot_internal = True
        try:
            self.execute('PRAGMA foreign_keys=ON')
            self.execute('PRAGMA trusted_schema=OFF')
            self.execute('PRAGMA query_only=ON')
            self.execute('PRAGMA read_uncommitted=OFF')
            if (self.execute('PRAGMA foreign_keys').fetchone() != (1,)
                    or self.execute('PRAGMA trusted_schema').fetchone() != (0,)
                    or self.execute('PRAGMA query_only').fetchone() != (1,)
                    or self.execute('PRAGMA read_uncommitted').fetchone() != (0,)):
                raise sqlite3.OperationalError('unsupported snapshot environment')
            def authorize(action, arg1, arg2, _database, _trigger):
                if action in _WRITE_ACTIONS:
                    object.__setattr__(self, '_snapshot_environment_valid', False)
                    return sqlite3.SQLITE_DENY
                if action == getattr(sqlite3, 'SQLITE_PRAGMA', -1):
                    pragma = arg1.casefold() if type(arg1) is str else None
                    setters = {'foreign_keys', 'trusted_schema', 'query_only',
                        'read_uncommitted', 'journal_mode', 'schema_version', 'user_version'}
                    if (pragma not in _READ_PRAGMAS
                            or pragma in setters and arg2 is not None
                            or pragma in {'table_info', 'table_xinfo'}
                                and type(arg2) is not str):
                        object.__setattr__(self, '_snapshot_environment_valid', False)
                        return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            self._snapshot_authorizer = authorize
            super().set_authorizer(authorize)
            databases = self.execute('PRAGMA database_list').fetchall()
            mode = self.execute('PRAGMA journal_mode').fetchone()
            version = self.execute('PRAGMA data_version').fetchone()
            if (len(databases) != 1 or databases[0][1] != 'main'
                    or mode is None or mode[0] not in ('delete', 'wal')
                    or version is None or type(version[0]) is not int):
                raise sqlite3.OperationalError('unsupported snapshot database')
            self.execute('PRAGMA main.table_list').fetchall()
            self._snapshot_sealed = True
        finally:
            self._snapshot_internal = False


def _file_identity(path):
    try:
        item = Path(path).lstat()
    except FileNotFoundError:
        return None
    reparse_flag = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
    if (stat.S_ISLNK(item.st_mode)
            or _os_name == 'nt' and item.st_file_attributes & reparse_flag
            or not stat.S_ISREG(item.st_mode)
            or item.st_nlink != 1):
        return False
    return (item.st_dev, item.st_ino, item.st_mode, item.st_nlink,
            item.st_size, item.st_mtime_ns, item.st_ctime_ns)


def path_identity(path):
    path = Path(path)
    main = _file_identity(path)
    if main is None or main is False:
        return None
    sidecars = tuple((suffix, _file_identity(str(path) + suffix))
                     for suffix in ('-wal', '-shm', '-journal'))
    if any(value is False for _suffix, value in sidecars):
        return None
    return (main, sidecars)


def _same_open_files(opened, current):
    """Reject inode substitution while allowing in-place database/WAL writes."""
    if (opened is None or current is None or opened[0] is None or current[0] is None
            or opened[0][:4] != current[0][:4]):
        return False
    for (_opened_suffix, prior), (_current_suffix, now) in zip(opened[1], current[1]):
        if prior is not None and now is not None and prior[:4] != now[:4]:
            return False
    return True


def _stable_during_sqlite_setup(before, after):
    if before is None or after is None or before[0][:4] != after[0][:4]:
        return False
    prior_wal, current_wal = before[1][0][1], after[1][0][1]
    if prior_wal != current_wal and not (
            prior_wal is None and current_wal is not None and current_wal[4] == 0):
        return False
    if before[1][2] != after[1][2]:
        return False
    prior_shm, current_shm = before[1][1][1], after[1][1][1]
    return (prior_shm is None or current_shm is not None
            and prior_shm[:4] == current_shm[:4])


_OBSERVATION_UNSAFE = object()
_OBSERVATION_UNSUPPORTED = object()


def _observe(connection):
    if type(connection) is not RequestSnapshotConnection:
        return _OBSERVATION_UNSUPPORTED
    if (connection._snapshot_open_path is None
            or connection._snapshot_open_identity is None):
        return _OBSERVATION_UNSUPPORTED
    # Physical identity is independent of cache-environment eligibility. Check
    # it first so a denied PRAGMA or other sticky environment failure cannot
    # mask pathname replacement and permit a fallback on the old open handle.
    current_path = path_identity(connection._snapshot_open_path)
    if not _same_open_files(connection._snapshot_open_identity, current_path):
        return _OBSERVATION_UNSAFE
    if (not connection._snapshot_environment_valid
            or connection.in_transaction
            or connection.row_factory is not None
            or connection.text_factory is not str
            or connection.total_changes != 0):
        return _OBSERVATION_UNSUPPORTED
    try:
        databases = connection.execute('PRAGMA database_list').fetchall()
        mode = connection.execute('PRAGMA journal_mode').fetchone()
        read_version = connection.execute('PRAGMA data_version').fetchone()
        if len(databases) != 1 or databases[0][1] != 'main':
            return _OBSERVATION_UNSUPPORTED
        if Path(databases[0][2]).resolve(strict=True) != connection._snapshot_open_path:
            return _OBSERVATION_UNSAFE
        if mode is None or mode[0] not in ('delete', 'wal'):
            return _OBSERVATION_UNSUPPORTED
        if (read_version is None or type(read_version[0]) is not int
                or connection.execute('PRAGMA foreign_keys').fetchone() != (1,)
                or connection.execute('PRAGMA trusted_schema').fetchone() != (0,)
                or connection.execute('PRAGMA query_only').fetchone() != (1,)
                or connection.execute('PRAGMA read_uncommitted').fetchone() != (0,)):
            return _OBSERVATION_UNSUPPORTED
        table_rows = connection.execute('PRAGMA main.table_list').fetchall()
        if (not any(row[0] == 'main' and row[1] == 'sqlite_schema'
                    for row in table_rows)
                or any(row[2] in ('virtual', 'shadow') for row in table_rows)):
            return _OBSERVATION_UNSUPPORTED
        for _schema, name, kind, _ncol, _wr, _strict in table_rows:
            if kind == 'table':
                if any(row[6] != 0 for row in connection.execute(
                        'PRAGMA main.table_xinfo(' + '"' + name.replace('"', '""') + '"' + ')')):
                    return _OBSERVATION_UNSUPPORTED
        final_path = path_identity(connection._snapshot_open_path)
        final_version = connection.execute('PRAGMA data_version').fetchone()
        if not _same_open_files(connection._snapshot_open_identity, final_path):
            return _OBSERVATION_UNSAFE
        if final_path != current_path:
            return _OBSERVATION_UNSUPPORTED
        if (final_version is None or type(final_version[0]) is not int
                or final_version[0] != read_version[0]):
            return _OBSERVATION_UNSUPPORTED
        return (final_version[0], connection.total_changes, final_path, mode[0])
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return _OBSERVATION_UNSUPPORTED


@dataclass(frozen=True)
class NativeSnapshotDatabase:
    """Exact generated-fixture native read-only factory for qualification."""
    path: Path
    timeout: float = 3.0

    def __post_init__(self):
        if (type(self.path) is not type(Path()) or not self.path.is_absolute()
                or type(self.timeout) not in (int, float) or not 0 < self.timeout <= 10):
            raise ValueError('explicit snapshot database path required')

    @contextmanager
    def __call__(self):
        connection = None
        try:
            before = path_identity(self.path)
            if before is None or self.path.resolve(strict=True) != self.path:
                raise sqlite3.OperationalError('snapshot source unavailable')
            connection = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True,
                timeout=self.timeout, factory=RequestSnapshotConnection)
            after = path_identity(self.path)
            if not _stable_during_sqlite_setup(before, after):
                raise sqlite3.OperationalError('snapshot source changed during open')
            connection.seal_read_only_environment()
            opened = path_identity(self.path)
            if not _stable_during_sqlite_setup(after, opened):
                raise sqlite3.OperationalError('snapshot source changed during setup')
            connection.bind_open_identity(self.path, opened)
        except (OSError, sqlite3.Error, ValueError):
            if connection is not None:
                connection.close()
            raise RuntimeError('snapshot source unavailable') from None
        try:
            yield connection
        finally:
            if connection.in_transaction:
                connection.rollback()
            connection.close()


_SNAPSHOT_CREATE_TOKEN = object()
_ATTEMPT_CREATE_TOKEN = object()
_SNAPSHOT_STATES = weakref.WeakKeyDictionary()
_ATTEMPT_STATES = weakref.WeakKeyDictionary()


class _SnapshotAttempt:
    __slots__ = ('__weakref__',)

    def __new__(cls, token=None):
        if token is not _ATTEMPT_CREATE_TOKEN:
            raise TypeError('private snapshot attempt')
        return super().__new__(cls)


class RequestSourceSnapshot:
    """Opaque handle for one request's private source-row replay state."""
    __slots__ = ('__weakref__',)
    _MAX_QUERIES = 16
    _MAX_ROWS = 1_000_000
    _MAX_BYTES = 256 * 1024**2

    def __new__(cls, library_id=None, *, _token=None):
        if cls is not RequestSourceSnapshot or _token is not _SNAPSHOT_CREATE_TOKEN:
            raise TypeError('private request source snapshot')
        if type(library_id) is not str or not library_id:
            raise ValueError('snapshot library identity required')
        return super().__new__(cls)

    def __init__(self, library_id=None, *, _token=None):
        _SNAPSHOT_STATES[self] = {
            'auth': _SNAPSHOT_CREATE_TOKEN, 'library_id': library_id,
            'connection': None, 'entries': {}, 'baseline': None,
            'disabled': False, 'final_requested': False,
            'replay_used': False, 'fallback_required': False,
            'identity_unsafe': False, 'stored_rows': 0, 'stored_bytes': 0,
        }

    @property
    def disabled(self):
        state = _snapshot_state(self)
        return state is None or state['disabled']

    @property
    def has_entries(self):
        state = _snapshot_state(self)
        return bool(state and state['entries'])

    @property
    def has_baseline(self):
        state = _snapshot_state(self)
        return bool(state and state['baseline'] is not None)

    @property
    def replay_used(self):
        state = _snapshot_state(self)
        return bool(state and state['replay_used'])

    def bind(self, connection):
        state = _snapshot_state(self)
        if state is None:
            return
        if type(connection) is not RequestSnapshotConnection:
            self.disable()
            return
        state['connection'] = connection

    def request_final_replay(self):
        state = _snapshot_state(self)
        if state is not None:
            state['final_requested'] = (not state['disabled'] and not state['identity_unsafe']
                                         and bool(state['entries']))
            state['replay_used'] = False
            state['fallback_required'] = False

    def stop_final_replay(self):
        state = _snapshot_state(self)
        if state is not None:
            state['final_requested'] = False

    def consume_fallback_required(self):
        state = _snapshot_state(self)
        if state is None:
            return False
        value, state['fallback_required'] = state['fallback_required'], False
        return value

    def consume_identity_unsafe(self):
        state = _snapshot_state(self)
        return bool(state and state['identity_unsafe'])

    def disable(self):
        state = _snapshot_state(self)
        if state is not None:
            state['disabled'] = True
            state['final_requested'] = False
            state['entries'].clear()
            state['stored_rows'] = state['stored_bytes'] = 0

    @staticmethod
    def _key(sql, args, library_id):
        if (type(sql) is not str or type(args) is not tuple or not args
                or type(args[0]) is not str or args[0] != library_id
                or len(args) > 8):
            return None
        if not _known_query(sql):
            return None
        frozen_args = []
        for value in args:
            if type(value) is not str or len(value.encode('utf-8')) > 1024:
                return None
            frozen_args.append((type(value), value))
        return (sql, tuple(frozen_args), library_id)

    def begin_attempt(self, connection, *, rows_limit, bytes_limit):
        state = _snapshot_state(self)
        if state is None:
            return _new_attempt(self, {'start': None, 'replay': False,
                'capture': False, 'staged': {}, 'excluded': set(), 'rows': 0,
                'bytes': 0, 'replay_used': False, 'owned': False,
                'rows_limit': min(rows_limit, self._MAX_ROWS),
                'bytes_limit': min(bytes_limit, self._MAX_BYTES)})
        if state['connection'] is None or connection is not state['connection']:
            return _new_attempt(self, {'start': None, 'replay': False,
                'capture': False, 'staged': {}, 'excluded': set(), 'rows': 0,
                'bytes': 0, 'replay_used': False, 'owned': False,
                'rows_limit': min(rows_limit, self._MAX_ROWS),
                'bytes_limit': min(bytes_limit, self._MAX_BYTES)})
        if state['identity_unsafe']:
            raise sqlite3.OperationalError('snapshot source identity is unsafe')
        observed = _observe(connection)
        if observed is _OBSERVATION_UNSAFE:
            state['identity_unsafe'] = True
            self.disable()
            raise sqlite3.OperationalError('snapshot source identity/environment changed')
        if observed is _OBSERVATION_UNSUPPORTED:
            self.disable()
            return _new_attempt(self, {'start': None, 'replay': False,
                'capture': False, 'staged': {}, 'excluded': set(), 'rows': 0,
                'bytes': 0, 'replay_used': False, 'owned': True,
                'rows_limit': min(rows_limit, self._MAX_ROWS),
                'bytes_limit': min(bytes_limit, self._MAX_BYTES)})
        opened_identity = connection._snapshot_open_identity
        if state['disabled']:
            start_matches = False
            capture = False
        elif state['baseline'] is None:
            if observed[2] != opened_identity:
                # A legitimate in-place source update since connection setup
                # disables reuse; the normal query still sees the live source.
                self.disable()
                start_matches = False
                capture = False
            else:
                start_matches = True
                capture = True
        else:
            start_matches = observed == state['baseline']
            capture = False
            if not start_matches:
                self.disable()
        replay = bool(state['final_requested'] and start_matches and state['entries']
                      and not state['disabled'])
        attempt = {'start': observed, 'replay': replay,
                   'capture': capture and not state['disabled'], 'staged': {},
                   'excluded': set(), 'rows': 0, 'bytes': 0,
                   'rows_limit': min(rows_limit, self._MAX_ROWS),
                   'bytes_limit': min(bytes_limit, self._MAX_BYTES),
                   'replay_used': False, 'owned': True, 'query_calls': {}}
        return _new_attempt(self, attempt)

    def owns_attempt(self, attempt, connection):
        state = _snapshot_state(self)
        payload = _attempt_payload(self, attempt)
        return bool(state and payload and payload['owned']
                    and state['connection'] is connection)

    def attempt_accounting(self, attempt):
        state = _snapshot_state(self)
        payload = _attempt_payload(self, attempt)
        if state is None or payload is None:
            raise ValueError('valid snapshot attempt required')
        return (payload['rows'], payload['bytes'])

    def read(self, attempt, sql, args, *, check):
        """Fetch, account, and optionally replay rows on the bound native handle."""
        state = _snapshot_state(self)
        payload = _attempt_payload(self, attempt)
        if (state is None or payload is None or not payload['owned']
                or state['connection'] is None):
            raise sqlite3.ProgrammingError('owned snapshot read required')
        from . import discovery as d
        connection = state['connection']
        check()
        key = self._key(sql, args, state['library_id'])
        if (payload['replay'] and key is not None and key in state['entries']
                and key not in payload['excluded']):
            payload['replay_used'] = True
            state['replay_used'] = True
            result = []
            for frozen_rows, packed_bytes in state['entries'][key]:
                check()
                self._charge(payload, len(frozen_rows), packed_bytes)
                result.extend(frozen_rows)
            return result

        if key is not None:
            count = payload['query_calls'].get(key, 0) + 1
            payload['query_calls'][key] = count
            if count > 1:
                self._exclude_query(payload, key)
            elif payload['capture']:
                payload['staged'][key] = []

        cursor = connection.execute(sql, args)
        result = []
        while True:
            chunk = cursor.fetchmany(128)
            if not chunk:
                break
            check()
            if payload['rows'] + len(chunk) > payload['rows_limit']:
                raise d.DiscoveryUnavailable()
            chunk_size = d._packed_chunk_size(chunk,
                payload['bytes_limit'] - payload['bytes'])
            if chunk_size is None:
                if payload['capture'] and key is not None:
                    self._exclude_query(payload, key)
                for row in chunk:
                    size = len(d.packed(row))
                    if payload['bytes'] + size > payload['bytes_limit']:
                        raise d.DiscoveryUnavailable()
                    payload['rows'] += 1
                    payload['bytes'] += size
                    result.append(row)
            else:
                if payload['bytes'] + chunk_size > payload['bytes_limit']:
                    raise d.DiscoveryUnavailable()
                payload['rows'] += len(chunk)
                payload['bytes'] += chunk_size
                result.extend(chunk)
                if (payload['capture'] and key is not None
                        and key not in payload['excluded']):
                    payload['staged'][key].append((tuple(tuple(row) for row in chunk),
                                                   chunk_size))
        return result

    def _charge(self, payload, rows, packed_bytes):
        from . import discovery as d
        if (type(rows) is not int or type(packed_bytes) is not int
                or rows < 0 or packed_bytes < 0
                or payload['rows'] + rows > payload['rows_limit']
                or payload['bytes'] + packed_bytes > payload['bytes_limit']):
            raise d.DiscoveryUnavailable()
        payload['rows'] += rows
        payload['bytes'] += packed_bytes

    @staticmethod
    def _exclude_query(attempt, key):
        attempt['staged'].pop(key, None)
        attempt['excluded'].add(key)

    def end_attempt(self, connection, attempt, *, success):
        state = _snapshot_state(self)
        payload = _attempt_payload(self, attempt)
        if (state is None or payload is None or connection is not state['connection']):
            return
        observed = _observe(connection)
        if observed is _OBSERVATION_UNSAFE:
            state['identity_unsafe'] = True
            self.disable()
            return
        if observed is _OBSERVATION_UNSUPPORTED:
            if success and payload['replay_used']:
                state['fallback_required'] = True
            self.disable()
            return
        if payload['replay_used']:
            state['replay_used'] = True
            if observed != payload['start']:
                if success:
                    state['fallback_required'] = True
                self.disable()
            return
        if not success:
            self.disable()
            return
        if state['baseline'] is None and payload['capture']:
            if observed != payload['start']:
                self.disable()
                return
            if len(payload['staged']) > self._MAX_QUERIES:
                self.disable()
                return
            state['entries'] = {key: tuple(chunks)
                for key, chunks in payload['staged'].items()}
            state['stored_rows'] = sum(len(rows) for chunks in state['entries'].values()
                                       for rows, _size in chunks)
            state['stored_bytes'] = sum(size for chunks in state['entries'].values()
                                        for _rows, size in chunks)
            if state['entries']:
                state['baseline'] = observed
        elif state['baseline'] is not None and observed != state['baseline']:
            self.disable()

    def close(self):
        state = _snapshot_state(self)
        if state is not None:
            self.disable()
            state['connection'] = None
            state['baseline'] = None
            _SNAPSHOT_STATES.pop(self, None)


def _snapshot_state(snapshot):
    if type(snapshot) is not RequestSourceSnapshot:
        return None
    state = _SNAPSHOT_STATES.get(snapshot)
    return state if state is not None and state.get('auth') is _SNAPSHOT_CREATE_TOKEN else None


def _new_attempt(snapshot, payload):
    payload.setdefault('query_calls', {})
    payload.setdefault('owned', False)
    payload.setdefault('rows_limit', RequestSourceSnapshot._MAX_ROWS)
    payload.setdefault('bytes_limit', RequestSourceSnapshot._MAX_BYTES)
    attempt = _SnapshotAttempt(_ATTEMPT_CREATE_TOKEN)
    _ATTEMPT_STATES[attempt] = {'owner': snapshot, 'payload': payload,
                                'auth': _ATTEMPT_CREATE_TOKEN}
    return attempt


def _attempt_payload(snapshot, attempt):
    if type(attempt) is not _SnapshotAttempt:
        return None
    record = _ATTEMPT_STATES.get(attempt)
    if (record is None or record.get('auth') is not _ATTEMPT_CREATE_TOKEN
            or record.get('owner') is not snapshot):
        return None
    return record['payload']


def create_request_source_snapshot(library_id):
    """Create the opaque request capability for the runtime's private use."""
    return RequestSourceSnapshot(library_id, _token=_SNAPSHOT_CREATE_TOKEN)


def is_request_source_snapshot(snapshot):
    return _snapshot_state(snapshot) is not None


def _known_query(sql):
    return sql in _query_templates()


@lru_cache(maxsize=1)
def _query_templates():
    from . import discovery as d
    from .visual_vector_loader import _COLUMNS
    scoped = d.SCOPE
    templates = {
        "SELECT a.id,CASE WHEN length(CAST(a.mime AS BLOB))<=256 THEN a.mime END,a.width,a.height,a.duration_sec,CASE WHEN length(CAST(a.taken_at AS BLOB))<=64 THEN a.taken_at END,length(CAST(a.taken_at AS BLOB)) FROM assets a JOIN access_asset_libraries m ON m.asset_id=a.id WHERE m.library_id=? AND (a.status='active' OR a.status IS NULL) ORDER BY a.id",
        'SELECT x.id,x.asset_id,CASE WHEN length(CAST(x.text AS BLOB))<=4096 THEN x.text END,length(CAST(x.text AS BLOB)),length(CAST(x.text AS BLOB)),x.user_edited,x.superseded FROM captions x' + scoped + ' ORDER BY x.id',
        'SELECT x.id,x.asset_id,x.person_id,x.label_source FROM face_detections x' + scoped + ' ORDER BY x.id',
        'SELECT x.id,x.asset_id,x.tag_id,x.source FROM asset_tags x' + scoped + ' ORDER BY x.id',
        'SELECT x.id,x.asset_id,x.tag_id FROM asset_tag_blocks x' + scoped + ' ORDER BY x.id',
        "SELECT DISTINCT t.id,CASE WHEN length(CAST(t.name AS BLOB))<=256 THEN t.name END,CASE WHEN length(CAST(t.type AS BLOB))<=32 THEN t.type END,length(CAST(t.name AS BLOB)) FROM tags t JOIN asset_tags x ON x.tag_id=t.id" + scoped + ' ORDER BY t.id',
        "SELECT a.id,CASE WHEN length(CAST(a.mime AS BLOB))<=256 THEN a.mime END,a.width,a.height,a.duration_sec,CASE WHEN length(CAST(a.taken_at AS BLOB))<=64 THEN a.taken_at END,length(CAST(a.taken_at AS BLOB)) FROM access_asset_libraries m JOIN assets a ON a.id=m.asset_id WHERE m.library_id=? AND (a.status='active' OR a.status IS NULL) ORDER BY m.asset_id",
        'SELECT x.id,x.asset_id,CASE WHEN length(CAST(x.text AS BLOB))<=4096 THEN x.text END,length(CAST(x.text AS BLOB)),length(CAST(x.text AS BLOB)),x.user_edited,x.superseded FROM captions x' + scoped + ' AND x.superseded=0 ORDER BY x.id',
        '''SELECT s.id,s.asset_id,s.revision,
            CASE WHEN length(CAST(s.title AS BLOB))<=512 THEN s.title END,
            CASE WHEN length(CAST(s.text AS BLOB))<=65536 THEN s.text END,
            s.author_id,s.updated_at
            FROM access_stories s JOIN assets a ON a.id=s.asset_id
            JOIN access_asset_libraries m ON m.asset_id=a.id
            WHERE m.library_id=? AND s.library_id=m.library_id AND s.deleted=0
            AND (a.status='active' OR a.status IS NULL) ORDER BY s.id''',
        f'''SELECT {','.join('v.' + column for column in _COLUMNS.split(','))} FROM image_vector_artifacts v
            JOIN assets a ON a.id=v.asset_id
            JOIN access_asset_libraries m ON m.asset_id=a.id
            WHERE m.library_id=? AND (a.status IS NULL OR a.status='active')
            AND a.mime GLOB 'image/*' AND v.status='ready' AND v.identity_sha256=?
            ORDER BY v.asset_id,v.record_id''',
        '''SELECT a.id,a.hash_sha256 FROM assets a
            JOIN access_asset_libraries m ON m.asset_id=a.id WHERE m.library_id=?
            AND (a.status IS NULL OR a.status='active') AND a.mime GLOB 'image/*'
            ORDER BY a.id''',
    }
    return frozenset(templates)

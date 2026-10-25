"""Generated SQLite checks for opt-in, one-request source SQL replay."""
from contextlib import closing
import sqlite3

import pytest

ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]
import sys
sys.path.insert(0, str(ROOT / 'backend'))

from app.access import discovery as d
from app.access.service import AccessService
from app.access.semantic_request_snapshot import (
    NativeSnapshotDatabase, RequestSnapshotConnection, RequestSourceSnapshot,
    create_request_source_snapshot,
)


ASSET_SQL = ("SELECT a.id,CASE WHEN length(CAST(a.mime AS BLOB))<=256 THEN a.mime END,"
    "a.width,a.height,a.duration_sec,CASE WHEN length(CAST(a.taken_at AS BLOB))<=64 "
    "THEN a.taken_at END,length(CAST(a.taken_at AS BLOB)) FROM assets a JOIN "
    "access_asset_libraries m ON m.asset_id=a.id WHERE m.library_id=? AND "
    "(a.status='active' OR a.status IS NULL) ORDER BY a.id")


def _database(path, *, wal=True):
    with closing(sqlite3.connect(path)) as db, db:
        if wal:
            assert db.execute('PRAGMA journal_mode=WAL').fetchone() == ('wal',)
        db.executescript('''
            CREATE TABLE assets(id INTEGER PRIMARY KEY, mime TEXT, width INTEGER,
                height INTEGER, duration_sec REAL, taken_at TEXT, status TEXT);
            CREATE TABLE access_asset_libraries(asset_id INTEGER, library_id TEXT);
            INSERT INTO assets VALUES(1,'image/jpeg',16,16,NULL,NULL,'active');
            INSERT INTO access_asset_libraries VALUES(1,'lib');
        ''')


def _read(connection, snapshot, budget, sql=ASSET_SQL, args=('lib',), between=None):
    if snapshot is not None:
        snapshot.bind(connection)
        budget = budget.with_request_source_snapshot(snapshot)
    access = AccessService(connection)
    with budget.attempt(connection, lambda: False) as (_check, read):
        with access._transaction():
            result = read(sql, args)
            if between is not None:
                between()
    return result


def test_exact_whitelisted_read_replays_detached_rows_without_sql(tmp_path, monkeypatch):
    path = tmp_path / 'source.sqlite'
    _database(path)
    calls = []
    original = RequestSnapshotConnection.execute

    def counted(connection, sql, *args):
        if sql == ASSET_SQL:
            calls.append(sql)
        return original(connection, sql, *args)

    monkeypatch.setattr(RequestSnapshotConnection, 'execute', counted)
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    factory = NativeSnapshotDatabase(path)
    with factory() as connection:
        first = _read(connection, snapshot, budget)
        assert first == [(1, 'image/jpeg', 16, 16, None, None, None)]
        assert calls == [ASSET_SQL]
        assert snapshot.has_baseline and snapshot.has_entries

        snapshot.request_final_replay()
        second = _read(connection, snapshot, budget)
        assert second == first and second is not first
        assert calls == [ASSET_SQL]
        assert snapshot.replay_used is True
        snapshot.close()


def test_wal_change_before_replay_disables_cache_and_reads_current_sql(tmp_path, monkeypatch):
    path = tmp_path / 'source.sqlite'
    _database(path)
    calls = []
    original = RequestSnapshotConnection.execute

    def counted(connection, sql, *args):
        if sql == ASSET_SQL:
            calls.append(sql)
        return original(connection, sql, *args)

    monkeypatch.setattr(RequestSnapshotConnection, 'execute', counted)
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    factory = NativeSnapshotDatabase(path)
    with factory() as connection:
        assert _read(connection, snapshot, budget)[0][0] == 1
        with closing(sqlite3.connect(path)) as writer, writer:
            writer.execute('UPDATE assets SET width=32 WHERE id=1')
        snapshot.request_final_replay()
        current = _read(connection, snapshot, budget)
        assert current[0][2] == 32
        assert calls == [ASSET_SQL, ASSET_SQL]
        assert snapshot.disabled is True and not snapshot.has_entries
        snapshot.close()


def test_wal_change_during_replay_bracket_requires_one_full_read_fallback(tmp_path,
                                                                          monkeypatch):
    path = tmp_path / 'source.sqlite'
    _database(path)
    calls = []
    original = RequestSnapshotConnection.execute

    def counted(connection, sql, *args):
        if sql == ASSET_SQL:
            calls.append(sql)
        return original(connection, sql, *args)

    monkeypatch.setattr(RequestSnapshotConnection, 'execute', counted)
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    factory = NativeSnapshotDatabase(path)
    with factory() as connection:
        assert _read(connection, snapshot, budget)[0][0] == 1
        snapshot.request_final_replay()

        def commit_writer():
            with closing(sqlite3.connect(path)) as writer, writer:
                writer.execute('UPDATE assets SET width=48 WHERE id=1')

        stale = _read(connection, snapshot, budget, between=commit_writer)
        assert stale[0][2] == 16
        assert snapshot.consume_fallback_required() is True
        assert snapshot.disabled is True
        fallback = _read(connection, snapshot, budget)
        assert fallback[0][2] == 48
        assert calls == [ASSET_SQL, ASSET_SQL]
        snapshot.close()


def test_snapshot_connection_refuses_mutable_environment_and_sql_writes(tmp_path):
    path = tmp_path / 'source.sqlite'
    _database(path)
    with NativeSnapshotDatabase(path)() as connection:
        snapshot = create_request_source_snapshot('lib')
        snapshot.bind(connection)
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute('CREATE TEMP TABLE injected(value)')
        with pytest.raises(sqlite3.ProgrammingError):
            connection.create_function('injected', 0, lambda: 1)
        with pytest.raises(sqlite3.ProgrammingError):
            connection._snapshot_environment_valid = True
        attempt = snapshot.begin_attempt(connection, rows_limit=100, bytes_limit=4096)
        assert attempt is not None
        assert snapshot.disabled is True


@pytest.mark.parametrize('pragma', ['query_only=OFF', 'read_uncommitted=ON'])
def test_pragma_setters_are_denied_and_sticky_disable_replay(tmp_path, pragma):
    path = tmp_path / 'source.sqlite'
    _database(path)
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    with NativeSnapshotDatabase(path)() as connection:
        assert _read(connection, snapshot, budget)
        with pytest.raises(sqlite3.DatabaseError):
            connection.execute('PRAGMA ' + pragma)
        snapshot.request_final_replay()
        # A denied environment mutation is sticky; the read remains a real SQL
        # read and the request fails closed from replay, not from normal service.
        assert _read(connection, snapshot, budget)
        assert snapshot.disabled and not snapshot.has_entries
        snapshot.close()


def test_unsupported_virtual_schema_falls_back_to_fresh_sql(tmp_path):
    path = tmp_path / 'source.sqlite'
    _database(path)
    with closing(sqlite3.connect(path)) as writer, writer:
        writer.execute('CREATE VIRTUAL TABLE search_test USING fts5(value)')
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    with NativeSnapshotDatabase(path)() as connection:
        result = _read(connection, snapshot, budget)
        assert result[0][0] == 1
        assert snapshot.disabled and not snapshot.has_entries
        snapshot.close()


def test_windows_reparse_attribute_is_not_accepted_as_regular_file(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.access import semantic_request_snapshot as snapshot_module

    fake = SimpleNamespace(st_mode=__import__('stat').S_IFREG | 0o600,
        st_nlink=1, st_dev=1, st_ino=2, st_size=10, st_mtime_ns=3,
        st_ctime_ns=4, st_file_attributes=0x400)
    monkeypatch.setattr(snapshot_module, '_os_name', 'nt')
    monkeypatch.setattr('pathlib.Path.lstat', lambda _path: fake)
    assert snapshot_module._file_identity(tmp_path / 'linked.sqlite') is False


def test_path_replacement_refuses_replay_before_any_cached_rows_are_used(tmp_path,
                                                                        monkeypatch):
    path = tmp_path / 'source.sqlite'
    _database(path, wal=False)
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    factory = NativeSnapshotDatabase(path)
    with factory() as connection:
        assert _read(connection, snapshot, budget)[0][0] == 1
        moved = tmp_path / 'old-source.sqlite'
        path.rename(moved)
        _database(path, wal=False)
        snapshot.request_final_replay()
        with pytest.raises(d.DiscoveryUnavailable):
            _read(connection, snapshot, budget)
        assert snapshot.disabled is True and not snapshot.has_entries
        snapshot.close()


def test_replay_recharges_original_limits_and_observes_cancellation(tmp_path):
    path = tmp_path / 'source.sqlite'
    _database(path)
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    factory = NativeSnapshotDatabase(path)
    with factory() as connection:
        assert _read(connection, snapshot, budget)
        snapshot.request_final_replay()
        budget.source_bytes = 1
        with pytest.raises(d.DiscoveryUnavailable):
            _read(connection, snapshot, budget)
        snapshot.close()

    path = tmp_path / 'rows.sqlite'
    _database(path)
    with closing(sqlite3.connect(path)) as writer, writer:
        writer.execute("INSERT INTO assets VALUES(2,'image/png',16,16,NULL,NULL,'active')")
        writer.execute("INSERT INTO access_asset_libraries VALUES(2,'lib')")
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=10, source_bytes=4096, seconds=5)
    with NativeSnapshotDatabase(path)() as connection:
        assert len(_read(connection, snapshot, budget)) == 2
        snapshot.request_final_replay()
        budget.rows = 1
        with pytest.raises(d.DiscoveryUnavailable):
            _read(connection, snapshot, budget)
        snapshot.close()

    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    with factory() as connection:
        assert _read(connection, snapshot, budget)
        snapshot.request_final_replay()
        view = budget.with_request_source_snapshot(snapshot)
        access = AccessService(connection)
        checks = [0]
        def cancelled():
            checks[0] += 1
            return checks[0] >= 3
        with pytest.raises(d.DiscoveryCancelled):
            with view.attempt(connection, cancelled) as (_check, read):
                with access._transaction():
                    read(ASSET_SQL, ('lib',))
        assert checks[0] >= 3
        snapshot.close()


def test_snapshot_and_attempt_state_are_opaque_and_budget_capability_is_required(tmp_path):
    path = tmp_path / 'source.sqlite'
    _database(path)
    with pytest.raises(TypeError):
        RequestSourceSnapshot('lib')
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    with NativeSnapshotDatabase(path)() as connection:
        snapshot.bind(connection)
        attempt = snapshot.begin_attempt(connection, rows_limit=20, bytes_limit=4096)
        key = snapshot.query_key(ASSET_SQL, ('lib',))
        # No public dicts or caller-created attempt can inject rows or byte counts.
        assert not hasattr(snapshot, 'baseline')
        assert not hasattr(snapshot, 'entries')
        assert not hasattr(attempt, '__dict__')
        snapshot.capture_chunk(attempt, key, [(99, 'forged')], 0)
        assert not snapshot.has_entries
        with pytest.raises(ValueError):
            budget.with_request_source_snapshot(object())
        snapshot.close()


def test_unknown_sql_falls_back_and_limits_are_recharged_on_replay(tmp_path, monkeypatch):
    path = tmp_path / 'source.sqlite'
    _database(path)
    calls = []
    original = RequestSnapshotConnection.execute
    unknown = 'SELECT width FROM assets WHERE id=?'

    def counted(connection, sql, *args):
        if sql == unknown:
            calls.append(sql)
        return original(connection, sql, *args)

    monkeypatch.setattr(RequestSnapshotConnection, 'execute', counted)
    snapshot = create_request_source_snapshot('lib')
    budget = d.ReadBudget(rows=20, source_bytes=4096, seconds=5)
    factory = NativeSnapshotDatabase(path)
    with factory() as connection:
        assert _read(connection, snapshot, budget, unknown, (1,)) == [(16,)]
        snapshot.request_final_replay()
        assert _read(connection, snapshot, budget, unknown, (1,)) == [(16,)]
        assert calls == [unknown, unknown]
        snapshot.close()

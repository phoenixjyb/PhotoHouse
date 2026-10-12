#!/usr/bin/env python3
"""Explicit offline preparation and metadata inspection for assistant stores.

This utility only prepares or inspects the isolated private workspace database.
It never starts or configures application services and does not activate a
runtime feature. Before --upgrade-v1, operators must fence every writer and
make a private backup. This utility cannot stop or verify those processes.
"""
from contextlib import closing
import argparse
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access import assistant_workspace_store as store  # noqa: E402


class Refused(Exception):
    def __init__(self, code='operation_refused'):
        self.code = code


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise Refused('invalid_arguments') from None


def _reparse_point(record):
    # Windows junctions and other reparse points are not guaranteed to report
    # as POSIX symlinks. Keep that platform check out of path resolution.
    attributes = getattr(record, 'st_file_attributes', 0)
    reparse_flag = getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)
    return bool(attributes & reparse_flag)


def _selected_path(value, *, exists):
    if type(value) is not str or not value or value.startswith('file:') or '?' in value or '#' in value:
        raise Refused('invalid_path')
    path = Path(value)
    if path.drive and ':' not in path.drive:
        raise Refused('invalid_path')
    if (not path.is_absolute() or '..' in path.parts or
            path.suffix.lower() not in ('.sqlite', '.db')):
        raise Refused('invalid_path')
    try:
        for parent in path.parents:
            parent_stat = parent.lstat()
            if _reparse_point(parent_stat) or stat.S_ISLNK(parent_stat.st_mode):
                raise Refused('invalid_path')
        parent_stat = path.parent.lstat()
        if (not stat.S_ISDIR(parent_stat.st_mode) or
                path.parent.resolve(strict=True) != path.parent):
            raise Refused('invalid_path')
        if exists:
            # The store's own path check also pins a direct regular file.
            target_stat = path.lstat()
            if _reparse_point(target_stat):
                raise Refused('invalid_path')
            store._path(path, exists=True)
        else:
            # Calling _path in non-existing mode rejects symlinked parents and
            # noncanonical traversal while allowing exclusive creation later.
            store._path(path, exists=False)
            if os.path.lexists(path):
                raise Refused('target_exists')
    except Refused:
        raise
    except Exception:
        raise Refused('invalid_path') from None
    return path


def _no_sidecars(path):
    if any(os.path.lexists(str(path) + suffix)
           for suffix in ('-wal', '-shm', '-journal')):
        raise Refused('database_not_quiescent')


def _inspect(path):
    path = _selected_path(path, exists=True)
    _no_sidecars(path)
    before = path.lstat()
    db = None
    try:
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=2,
                             isolation_level=None)
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        if (db.execute('PRAGMA application_id').fetchone()[0] != store.APPLICATION_ID or
                db.execute('PRAGMA user_version').fetchone()[0] != store.SCHEMA_VERSION or
                db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete' or
                not store._schema_shape(db, store._SCHEMA_SQL)):
            raise Refused('invalid_store')
        metadata = {
            'schema_version': db.execute('PRAGMA user_version').fetchone()[0],
            'application_id': db.execute('PRAGMA application_id').fetchone()[0],
            'journal_mode': db.execute('PRAGMA journal_mode').fetchone()[0],
            'threads': db.execute('SELECT count(*) FROM threads').fetchone()[0],
            'exchanges': db.execute('SELECT count(*) FROM exchanges').fetchone()[0],
            'turns': db.execute('SELECT count(*) FROM turn_requests').fetchone()[0],
            'preferences': db.execute('SELECT count(*) FROM preferences').fetchone()[0],
            'expiry': {
                'threads': _expiry_bounds(db, 'threads'),
                'exchanges': _expiry_bounds(db, 'exchanges'),
                'turns': _expiry_bounds(db, 'turn_requests'),
            },
        }
        after = path.lstat()
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise Refused('database_changed_during_inspection')
        _no_sidecars(path)
        return metadata
    except Refused:
        raise
    except Exception:
        raise Refused('invalid_store') from None
    finally:
        if db is not None:
            db.close()


def _expiry_bounds(db, table):
    # Only aggregate expiry timestamps are exposed; no row IDs or scope values.
    minimum, maximum = db.execute(
        f'SELECT min(expires_at), max(expires_at) FROM {table}'
    ).fetchone()
    return {'earliest': minimum, 'latest': maximum}


def _parser():
    parser = Parser(
        description='Explicit offline preparation and read-only inspection of a private assistant workspace store.',
        epilog=('Before --upgrade-v1, stop or fence every writer and make a private backup. '
                'This command cannot control or verify processes. Preparation does not activate the assistant feature.'),
    )
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--initialize', metavar='PATH', help='exclusively create a new v2 store')
    modes.add_argument('--upgrade-v1', metavar='PATH', help='offline upgrade of an existing validated v1 store')
    modes.add_argument('--inspect', metavar='PATH', help='read-only aggregate metadata for an existing v2 store')
    return parser


def _emit(value):
    sys.stdout.write(json.dumps(value, ensure_ascii=True, separators=(',', ':')) + '\n')


def main(argv=None):
    mode = 'unknown'
    try:
        args = _parser().parse_args(argv)
        if args.initialize is not None:
            mode = 'initialize'
            path = _selected_path(args.initialize, exists=False)
            _no_sidecars(path)
            created = store.initialize_v2(path)
            # Initialization uses the store's public API and returns a validated
            # store handle. Do not retain it beyond this operation.
            del created
            _emit({'mode': 'initialize', 'outcome': 'created', 'code': 'ok',
                   'schema_version': store.SCHEMA_VERSION,
                   'feature_activated': False})
        elif args.upgrade_v1 is not None:
            mode = 'upgrade-v1'
            path = _selected_path(args.upgrade_v1, exists=True)
            _no_sidecars(path)
            upgraded = store.offline_upgrade_v1(path)
            del upgraded
            _emit({'mode': 'upgrade-v1', 'outcome': 'upgraded', 'code': 'ok',
                   'schema_version': store.SCHEMA_VERSION,
                   'operator_fence_and_backup_required': True,
                   'feature_activated': False})
        else:
            mode = 'inspect'
            metadata = _inspect(args.inspect)
            _emit({'mode': 'inspect', 'outcome': 'inspected', 'code': 'ok',
                   'metadata': metadata})
        return 0
    except Refused as error:
        _emit({'mode': mode, 'outcome': 'refused', 'code': error.code})
        return 2
    except store.WorkspaceStoreUnavailable:
        _emit({'mode': mode, 'outcome': 'refused', 'code': 'invalid_store'})
        return 2
    except Exception:
        # Keep paths, SQLite diagnostics, payloads and stack traces private.
        _emit({'mode': mode, 'outcome': 'failed', 'code': 'operation_failed'})
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

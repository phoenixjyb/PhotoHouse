"""Content-free media withdrawal and offline restore verification.

No authorization, journal append, migration, commit or media unlink occurs here.
The caller owns the primary write transaction and durable append-before-withdraw
ordering. Asset parents, mappings, originals and immutable provenance are retained.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from .original_deletions import OriginalDeletionError

_SHA = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
_ID = re.compile(r'[1-9][0-9]{0,18}\Z', re.ASCII)
_LIBRARY = re.compile(r'[a-z0-9][a-z0-9._-]{0,63}\Z', re.ASCII)
_MIME = re.compile(r'(?:image|video)/[a-z0-9][a-z0-9.+-]{0,63}\Z', re.ASCII)
_FIELDS = {'version', 'asset_id', 'source_sha256', 'file_size', 'mime',
           'path_sha256', 'library_id', 'mapping_sha256'}


def _refuse():
    raise OriginalDeletionError('Asset withdrawal unavailable') from None


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False)


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _valid_id(value):
    return type(value) is int and 1 <= value <= 2**63 - 1


def parse_asset_binding(value):
    try:
        if type(value) is not str or not value.isascii() or not 1 <= len(value) <= 2048:
            _refuse()
        binding = json.loads(value)
        if (type(binding) is not dict or set(binding) != _FIELDS
                or type(binding['version']) is not int or binding['version'] != 1
                or not _valid_id(binding['asset_id'])
                or type(binding['file_size']) is not int or not 1 <= binding['file_size'] <= 2**63 - 1
                or type(binding['library_id']) is not str or not _LIBRARY.fullmatch(binding['library_id'])
                or type(binding['mime']) is not str or not _MIME.fullmatch(binding['mime'])
                or any(type(binding[name]) is not str or not _SHA.fullmatch(binding[name])
                       for name in ('source_sha256', 'path_sha256', 'mapping_sha256'))
                or _json(binding) != value):
            _refuse()
        expected = _sha(_json(['photohouse-asset-library-v1', binding['asset_id'],
                              binding['library_id']]).encode('ascii'))
        if binding['mapping_sha256'] != expected:
            _refuse()
        return binding
    except (KeyError, ValueError, TypeError, RecursionError, UnicodeError):
        _refuse()


def _snapshot(db, asset_id, library_id, *, preparing):
    if (getattr(db, 'in_transaction', None) is not True or not _valid_id(asset_id)
            or type(library_id) is not str or not _LIBRARY.fullmatch(library_id)):
        _refuse()
    try:
        row = db.execute('SELECT id,path,hash_sha256,file_size,mime,status FROM assets WHERE id=?',
                         (asset_id,)).fetchone()
        mappings = db.execute('SELECT m.library_id,l.state FROM access_asset_libraries m '
                              'LEFT JOIN access_libraries l ON l.id=m.library_id WHERE m.asset_id=?',
                              (asset_id,)).fetchall()
        uploads = db.execute('SELECT state,sha256,bytes FROM access_uploads WHERE asset_id=?',
                             (asset_id,)).fetchall()
        if (row is None or type(row[1]) is not str or not 1 <= len(row[1]) <= 4096
                or any(ord(c) < 32 for c in row[1])
                or row[5] not in (('active',) if preparing else ('active', 'deleted'))
                or len(mappings) != 1 or mappings[0][0] != library_id
                or mappings[0][1] not in (('active',) if preparing else ('active', 'closed'))
                or len(uploads) != 1 or tuple(uploads[0]) != ('assigned', row[2], row[3])):
            _refuse()
        value = _json({'version': 1, 'asset_id': asset_id, 'source_sha256': row[2],
                       'file_size': row[3], 'mime': row[4],
                       'path_sha256': _sha(row[1].encode('utf-8', errors='strict')),
                       'library_id': library_id,
                       'mapping_sha256': _sha(_json(['photohouse-asset-library-v1', asset_id,
                                                     library_id]).encode('ascii'))})
        parse_asset_binding(value)
        return value
    except (sqlite3.Error, ValueError, TypeError, UnicodeError):
        _refuse()


def prepare_asset_tombstone(db, asset_id, library_id, occurred_at):
    if type(occurred_at) is not int or not 0 <= occurred_at <= 2**63 - 1:
        _refuse()
    binding = _snapshot(db, asset_id, library_id, preparing=True)
    parsed = parse_asset_binding(binding)
    return {'collection': 'asset', 'library_id': library_id, 'object_id': str(asset_id),
            'original_kind': 'asset', 'original_sha256': parsed['source_sha256'],
            'batch': None, 'asset_id': asset_id, 'story_id': None,
            'occurred_at': occurred_at, 'asset_binding_json': binding}


def verify_asset_record(db, record):
    try:
        binding = parse_asset_binding(record['asset_binding_json'])
        if (record['collection'] != 'asset' or record['original_kind'] != 'asset'
                or type(record['object_id']) is not str or not _ID.fullmatch(record['object_id'])
                or record['object_id'] != str(binding['asset_id'])
                or type(record['asset_id']) is not int or record['asset_id'] != binding['asset_id']
                or record['library_id'] != binding['library_id']
                or record['original_sha256'] != binding['source_sha256']
                or record['batch'] is not None or record['story_id'] is not None
                or type(record['occurred_at']) is not int or record['occurred_at'] < 0
                or _snapshot(db, binding['asset_id'], binding['library_id'], preparing=False)
                   != record['asset_binding_json']):
            _refuse()
        return binding
    except (KeyError, TypeError, ValueError):
        _refuse()


def apply_asset_tombstone(db, record):
    """Withdraw the exact retained parent; do not erase originals or provenance."""
    verify_asset_record(db, record)
    try:
        if db.execute('PRAGMA secure_delete').fetchone()[0] != 1:
            _refuse()
        changed = db.execute("UPDATE assets SET status='deleted' WHERE id=? AND status IN ('active','deleted')",
                             (record['asset_id'],)).rowcount
        if changed != 1:
            _refuse()
    except sqlite3.Error:
        _refuse()


def plan_durable_asset_vector_cleanup(db, root, journal, asset_id):
    """Read-only all-version plan after a current, committed external receipt."""
    # asset_record verifies marker/head and the complete bound asset identity.
    # A status-only change or a rolled-back primary append is insufficient.
    if journal.asset_record(db, asset_id) is None:
        _refuse()
    from .visual_vector_cleanup import plan_asset_vector_cleanup
    return plan_asset_vector_cleanup(db, root, asset_id)

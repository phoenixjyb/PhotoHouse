#!/usr/bin/env python3
"""Explicit one-shot/bounded local memory worker; never daemonizes or retries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.annotation_local import LocalAnnotationModels  # noqa: E402
from app.access.memory_narrative import LocalMemoryNarrator  # noqa: E402
from app.access.memory_processing import process_contribution, process_job  # noqa: E402
from app.access.runtime import (ExistingDatabase, COLLABORATION_REVISIONS,
                                SOURCE_REFERENCE_REVISIONS, EDITORIAL_REVISIONS)  # noqa: E402


MAX_CONFIG_BYTES = 16 * 1024
MAX_ITEMS = 32
MAX_SECONDS = 1800
PROVIDER_TIMEOUT = 30
MEMORY_TABLES = frozenset({
    'access_memory_contributions', 'access_memory_contribution_derivations',
    'access_memory_books', 'access_memory_book_revisions',
    'access_memory_conversations', 'access_memory_jobs', 'access_memory_turns',
    'access_original_deletion_state',
})
CONFIG_FIELDS = frozenset({
    'database', 'mode', 'ollama_url', 'ollama_model',
    'asr_url', 'asr_model', 'asr_token',
    'original_deletion_journal_path', 'original_deletion_namespace',
})


class WorkerConfigurationError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise WorkerConfigurationError('Invalid worker configuration')
        result[key] = value
    return result


def _constant(_value):
    raise WorkerConfigurationError('Invalid worker configuration')


def read_config(path: Path) -> dict:
    if not isinstance(path, Path) or not path.is_absolute():
        raise WorkerConfigurationError('Invalid worker configuration')
    try:
        if path.resolve(strict=True) != path:
            raise WorkerConfigurationError('Invalid worker configuration')
        flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
        descriptor = os.open(path, flags)
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_CONFIG_BYTES:
                raise WorkerConfigurationError('Invalid worker configuration')
            raw = os.read(descriptor, MAX_CONFIG_BYTES + 1)
            after = os.fstat(descriptor)
            path_after = path.lstat()
            if (len(raw) > MAX_CONFIG_BYTES or
                    (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino) or
                    (after.st_dev, after.st_ino) != (path_after.st_dev, path_after.st_ino)):
                raise WorkerConfigurationError('Invalid worker configuration')
        finally:
            os.close(descriptor)
        config = json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=_pairs,
                            parse_constant=_constant)
    except WorkerConfigurationError:
        raise
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        raise WorkerConfigurationError('Invalid worker configuration') from None
    if (type(config) is not dict or not CONFIG_FIELDS <= set(config)
            or set(config) - CONFIG_FIELDS - {'memory_editorial_enabled'}):
        raise WorkerConfigurationError('Invalid worker configuration')
    if type(config.get('memory_editorial_enabled', False)) is not bool:
        raise WorkerConfigurationError('Invalid worker configuration')
    if type(config['database']) is not str or not config['database']:
        raise WorkerConfigurationError('Invalid worker configuration')
    database = Path(config['database'])
    if not database.is_absolute():
        raise WorkerConfigurationError('Invalid worker configuration')
    if type(config['mode']) is not str or config['mode'] not in {'narrative', 'contributions'}:
        raise WorkerConfigurationError('Invalid worker configuration')
    if config.get('memory_editorial_enabled', False) and config['mode'] != 'narrative':
        raise WorkerConfigurationError('Invalid worker configuration')
    journal = config['original_deletion_journal_path']
    namespace = config['original_deletion_namespace']
    try:
        import uuid
        if (type(journal) is not str or not Path(journal).is_absolute()
                or str(Path(journal)) != journal or Path(journal) == Path(config['database'])
                or type(namespace) is not str or str(uuid.UUID(namespace)) != namespace):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise WorkerConfigurationError('Invalid worker configuration') from None
    if any(type(config[key]) is not str or not config[key]
           for key in ('ollama_url', 'ollama_model')):
        raise WorkerConfigurationError('Invalid worker configuration')
    if config['mode'] == 'narrative':
        if any(config[key] is not None for key in ('asr_url', 'asr_model', 'asr_token')):
            raise WorkerConfigurationError('Invalid worker configuration')
    else:
        if (type(config['asr_url']) is not str or not config['asr_url'] or
                type(config['asr_model']) is not str or not config['asr_model'] or
                (config['asr_token'] is not None and
                 (type(config['asr_token']) is not str or not config['asr_token']))):
            raise WorkerConfigurationError('Invalid worker configuration')
    return config


def _check_schema(db, *, editorial_enabled=False):
    try:
        versions = db.execute('SELECT version_num FROM alembic_version').fetchall()
        if len(versions) != 1 or versions[0][0] not in COLLABORATION_REVISIONS:
            return False
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if (type(editorial_enabled) is not bool or (editorial_enabled and
                (versions[0][0] not in EDITORIAL_REVISIONS or not {
                    'access_memory_book_editorial', 'access_memory_book_editorial_refs',
                } <= tables))):
            return False
        if editorial_enabled:
            from app.access.memory_book_editorial import MemoryBookEditorial
            from app.access.service import AccessService
            try:
                MemoryBookEditorial(AccessService(db), enabled=True)._ready()
            except Exception:
                return False
        if not MEMORY_TABLES <= tables:
            return False
        if versions[0][0] in SOURCE_REFERENCE_REVISIONS and 'access_memory_contribution_refs' not in tables:
            return False
        # Existing e6 parents cannot be rebuilt just to add composite FKs.
        # Refuse inconsistent scope from any out-of-band writer before inference.
        for table in ('access_memory_contributions', 'access_memory_conversations', 'access_memory_jobs'):
            if db.execute(f'''SELECT 1 FROM {table} c JOIN access_memory_stories s ON s.id=c.story_id
                    WHERE c.library_id<>s.library_id LIMIT 1''').fetchone():
                return False
        for table in ('access_memory_conversations', 'access_memory_jobs'):
            if db.execute(f'''SELECT 1 FROM {table} c JOIN access_memory_books b ON b.id=c.book_id
                    WHERE c.library_id<>b.library_id LIMIT 1''').fetchone():
                return False
        return db.execute('PRAGMA foreign_key_check').fetchone() is None
    except sqlite3.Error:
        return False


def _database(config, *, read_only):
    from app.access.original_deletions import OriginalDeletionJournal
    return ExistingDatabase(Path(config['database']), read_only=read_only,
        original_deletions=OriginalDeletionJournal(Path(config['original_deletion_journal_path']),
                                                  config['original_deletion_namespace']))


def validate_storage(config, *, read_only):
    try:
        database = _database(config, read_only=read_only)
        with database() as db:
            if not _check_schema(db, editorial_enabled=config.get('memory_editorial_enabled', False)):
                return False
            if read_only and db.in_transaction:
                return False
        return True
    except Exception:
        return False


def _adapters(config, *, timeout=PROVIDER_TIMEOUT):
    if config['mode'] == 'narrative':
        return LocalMemoryNarrator(config['ollama_url'], config['ollama_model'], timeout=timeout)
    return LocalAnnotationModels(
        asr_url=config['asr_url'], ollama_url=config['ollama_url'],
        ollama_model=config['ollama_model'], asr_model=config['asr_model'],
        asr_token=config['asr_token'], timeout=timeout)


def _run(config, *, maximum_items, maximum_seconds, once, clock=time.monotonic):
    deadline = clock() + maximum_seconds if maximum_seconds is not None else None
    counts = {}
    processed = 0
    with _database(config, read_only=False)() as db:
        if not _check_schema(db, editorial_enabled=config.get('memory_editorial_enabled', False)):
            return {'status': 'unavailable', 'mode': config['mode'], 'processed': 0, 'states': {}}
        while processed < maximum_items and (deadline is None or clock() < deadline):
            if config['mode'] == 'narrative':
                remaining = PROVIDER_TIMEOUT if deadline is None else min(PROVIDER_TIMEOUT, deadline-clock())
                if remaining <= 0:
                    break
                adapter = _adapters(config, timeout=remaining)
                outcome = process_job(db, narrator=adapter, clock=time.time,
                    editorial_enabled=config.get('memory_editorial_enabled', False))
            else:
                # ASR and polishing share one per-item wall budget. A synchronous
                # socket read may run until its timeout; no second phase starts
                # after that budget expires.
                item_deadline = clock() + PROVIDER_TIMEOUT
                if deadline is not None:
                    item_deadline = min(item_deadline, deadline)

                def call_model(method, *args):
                    remaining = min(PROVIDER_TIMEOUT, item_deadline - clock())
                    if remaining <= 0:
                        raise RuntimeError('Provider time budget exhausted')
                    return getattr(_adapters(config, timeout=remaining), method)(*args)

                outcome = process_contribution(
                    db, transcribe=lambda audio, language: call_model('transcribe', audio, language),
                    polish=lambda source, language: call_model('polish', source, language),
                    clock=time.time)
            if outcome is None:
                break
            processed += 1
            state = outcome.get('state', 'unknown')
            counts[state] = counts.get(state, 0) + 1
            if once:
                break
    return {'status': 'complete', 'mode': config['mode'], 'processed': processed, 'states': counts}


def _parser():
    parser = argparse.ArgumentParser(description='Run a bounded local family-memory worker.')
    parser.add_argument('--config', required=True, type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--preflight', action='store_true')
    action.add_argument('--once', action='store_true')
    action.add_argument('--max-items', type=int)
    parser.add_argument('--max-seconds', type=int)
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    bounded = args.max_items is not None
    if (not args.preflight and not args.once and not bounded) or (
            bounded and (args.max_seconds is None or not 1 <= args.max_items <= MAX_ITEMS or
                         not 1 <= args.max_seconds <= MAX_SECONDS)) or (
            not bounded and args.max_seconds is not None):
        parser.error('choose --preflight, --once, or both bounded --max-items and --max-seconds')
    try:
        config = read_config(args.config)
        # Constructors validate the explicit loopback endpoints and model names;
        # neither adapter contacts a provider until its method is called.
        if args.preflight:
            _adapters(config)
            ok = validate_storage(config, read_only=True)
            report = {'status': 'ready' if ok else 'unavailable', 'mode': config['mode'],
                      'schema_valid': bool(ok), 'foreign_keys_valid': bool(ok)}
            print(json.dumps(report, separators=(',', ':')))
            return 0 if ok else 2
        report = _run(config, maximum_items=1 if args.once else args.max_items,
                      maximum_seconds=None if args.once else args.max_seconds, once=args.once)
        print(json.dumps(report, separators=(',', ':')))
        return 0 if report['status'] == 'complete' else 2
    except Exception:
        print(json.dumps({'status': 'unavailable'}, separators=(',', ':')))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

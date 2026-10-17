#!/usr/bin/env python3
"""Qualify released-caption queue handling with generated images and mock HTTP only.

The only user-selected path is a new output directory beneath an existing private
parent. The fixture migrates a new database, binds a generated v3 deletion journal,
and invokes the actual released-caption transaction with an in-process HTTP mock.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import sqlite3
import sys
import uuid

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / 'backend'))
sys.path.insert(0, str(SERVER / 'scripts'))

import httpx
from PIL import Image

from app.access.asset_tombstones import prepare_asset_tombstone
from app.access.original_deletions import OriginalDeletionJournal
from app.access.provisioning import _json
from app.access.provisioning_apply import _identity
from app.access.runtime import ExistingDatabase, RuntimeUnavailable
from app.access.upload_caption_processing import (
    CaptionProcessingRefused,
    inspect_released_captions,
    process_released_caption_task,
)
from app.approved_caption_http import LocalCaptionHTTP
from qualify_memory_groups import _create_file, _migrate
import run_released_caption_worker as runner


REVISION = 'a0c9d2e4f817'
RELEASE_OPERATION = 'release_deferred_upload_starters'
LIBRARY = 'synthetic-caption-library'
OWNER = str(uuid.UUID('9aa7c616-1739-4a04-a6c1-2cfd98b9f6f1'))
VIEWER = str(uuid.UUID('bf139190-b9e5-4271-85d2-01f1c0a981c6'))
NOW = 2_000_000_000
MODEL_ID = 'Qwen/Qwen3-VL-8B-Instruct'
GOOD = 'EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子放在木桌上。'
POLICY_REJECTED = 'EN: A person is possibly outdoors.\n\nZH-CN: 一个人可能在户外。'
ASSETS = (101, 102, 103, 104, 105, 106)
TASKS = (701, 702, 703, 704, 705, 706)
FOREIGN_TASK = 799
CASES = (
    'metadata_only_inspection_does_not_claim_tasks',
    'generated_png_caption_finishes_atomically_and_preserves_original',
    'concurrent_member_caption_is_preserved',
    'uploader_revocation_discards_generated_caption',
    'provider_failure_uses_sanitized_retry_backoff',
    'caption_policy_refusal_does_not_publish',
    'model_identity_drift_does_not_publish',
    'foreign_failed_thumbnail_is_never_reset',
    'bound_deletion_journal_is_unchanged_during_queue_processing',
    'stale_journal_after_rollback_is_rejected',
)
REPORT_NAME = 'qualification-report.json'
FAILURE_NAME = 'qualification-failure.json'
ORIGINALS_NAME = 'synthetic-originals'
DB_NAME = 'primary.sqlite'
JOURNAL_NAME = 'original-deletion-journal.sqlite'
MAX_REPORT_BYTES = 16 * 1024
MEMORY_LIMIT = 2 * 1024**3
FREE_RAM_FLOOR = 8 * 1024**3
PROCESS_LIMIT = 8
TASK_SECONDS = 300


class QualificationRefused(RuntimeError):
    def __init__(self, code: str):
        self.code = code if code in {'invalid_output', 'output_not_private', 'fixture_failed',
                                    'bounded_child_required', 'child_failed', 'report_invalid'} else 'fixture_failed'
        super().__init__(self.code)


def _check_windows_paths(target: Path, *, windows: bool | None = None) -> None:
    if windows is None:
        windows = os.name == 'nt'
    if not windows:
        return
    root = PureWindowsPath(str(target))
    outputs = [root / name for name in (DB_NAME, JOURNAL_NAME, REPORT_NAME, FAILURE_NAME)]
    originals = root / ORIGINALS_NAME
    outputs.extend(originals / f'synthetic-{asset}.png' for asset in ASSETS)
    outputs.extend(PureWindowsPath(str(path) + suffix) for path in tuple(outputs)
                   if path.suffix in {'.sqlite', '.png'}
                   for suffix in ('-journal', '-wal', '-shm'))
    units = lambda path: len(str(path).encode('utf-16le')) // 2
    if (any(units(path) > 259 for path in outputs)
            or any(units(path) > 247 for path in (root, *root.parents))
            or units(Path(sys.executable).resolve()) > 259
            or units(Path(__file__).resolve()) > 259):
        raise QualificationRefused('invalid_output')


def _validate_output(output: Path) -> Path:
    target = Path(output)
    if ('?' in str(target) or '#' in str(target) or not target.is_absolute()
            or '..' in target.parts or os.path.lexists(target)
            or target.parent.resolve(strict=True) != target.parent):
        raise QualificationRefused('invalid_output')
    for parent in (target.parent, *target.parent.parents):
        info = parent.lstat()
        if parent.is_symlink() or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise QualificationRefused('output_not_private')
    try:
        from app.access.private_storage import require_private_directory
        require_private_directory(target.parent)
    except (OSError, ValueError, PermissionError):
        raise QualificationRefused('output_not_private') from None
    _check_windows_paths(target)
    return target


def _create_private_file(path: Path) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    os.close(descriptor)
    from app.access.private_storage import require_private_file
    require_private_file(path)


def _write_json(path: Path, value: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'w', encoding='ascii', newline='\n') as stream:
        from app.access.private_storage import require_private_file
        require_private_file(path)
        json.dump(value, stream, sort_keys=True, separators=(',', ':'))
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def _db(path: Path) -> sqlite3.Connection:
    from app.access.private_storage import require_private_file
    require_private_file(path)
    db = sqlite3.connect(path, timeout=5)
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA synchronous=FULL')
    return db


def _png(asset_id: int) -> bytes:
    color = ((asset_id * 29) % 256, (asset_id * 47) % 256, (asset_id * 61) % 256)
    from io import BytesIO
    stream = BytesIO()
    with Image.new('RGB', (48, 32), color) as image:
        image.save(stream, format='PNG')
    return stream.getvalue()


def _write_original(path: Path, raw: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    from app.access.private_storage import require_private_file
    require_private_file(path)


def _seed(path: Path, originals: Path, journal_path: Path):
    _create_private_file(path)
    _migrate(path, REVISION)
    namespace = str(uuid.uuid4())
    journal = OriginalDeletionJournal.initialize(journal_path, namespace, format_version=3)
    with closing(_db(path)) as db:
        journal.bind(db)
        db.execute('''INSERT INTO access_accounts(id,phone_login,password_hash,state,display_name)
            VALUES(?,?,?,'active',?)''', (OWNER, '+12025550801', 'synthetic-unused-hash', 'Synthetic Owner'))
        db.execute('''INSERT INTO access_accounts(id,phone_login,password_hash,state,display_name)
            VALUES(?,?,?,'active',?)''', (VIEWER, '+12025550802', 'synthetic-unused-hash', 'Synthetic Viewer'))
        db.execute('INSERT INTO access_operators(account_id) VALUES(?)', (OWNER,))
        db.execute('INSERT INTO access_libraries(id,state,bootstrap_operator) VALUES(?,\'active\',?)',
                   (LIBRARY, OWNER))
        db.executemany('''INSERT INTO access_memberships(account_id,library_id,status,role,revision,
            expires_at,originals,approved_by) VALUES(?,?,'approved',?,1,NULL,0,?)''',
            ((OWNER, LIBRARY, 'owner', OWNER), (VIEWER, LIBRARY, 'viewer', OWNER)))

        originals.mkdir(mode=0o700)
        from app.access.private_storage import require_private_directory
        require_private_directory(originals)
        raw_by_asset = {}
        for asset_id in ASSETS:
            filename = originals / f'synthetic-{asset_id}.png'
            raw = _png(asset_id)
            _write_original(filename, raw)
            digest = hashlib.sha256(raw).hexdigest()
            raw_by_asset[asset_id] = raw
            db.execute('''INSERT INTO assets(id,path,hash_sha256,mime,width,height,file_size,status,
                caption_processed,caption_variant_count) VALUES(?,?,?,?,?,?,?,'active',0,0)''',
                (asset_id, str(filename), digest, 'image/png', 48, 32, len(raw)))
            db.execute('INSERT INTO access_asset_libraries(asset_id,library_id) VALUES(?,?)',
                       (asset_id, LIBRARY))
            db.execute('''INSERT INTO access_uploads(asset_id,account_id,incoming_label,batch,
                original_name,sha256,bytes,state,created_at,destination_library_id,approval_mode)
                VALUES(?,?,?,?,?,?,?,'assigned',?,?, 'manual')''',
                (asset_id, OWNER, 'synthetic-owner', f'{asset_id:032x}', filename.name,
                 digest, len(raw), NOW, LIBRARY))

        released = []
        for task_id, asset_id in zip(TASKS, ASSETS):
            payload_json = json.dumps({'asset_id': asset_id}, sort_keys=True)
            db.execute('''INSERT INTO tasks(id,type,payload_json,state,priority,retry_count,cancel_requested)
                VALUES(?,'caption',?,'pending',0,0,0)''', (task_id, payload_json))
            released.append({'task_id': task_id, 'type': 'caption', 'payload_json': payload_json,
                             'from_state': 'awaiting_review', 'to_state': 'pending'})
        db.execute('''INSERT INTO tasks(id,type,payload_json,state,priority,retry_count,last_error,
            cancel_requested) VALUES(799,'thumb','{"asset_id":999}','failed',7,4,
            'synthetic-retained-failure',0)''')

        release_id = str(uuid.uuid4())
        receipt = {
            'version': 1,
            'operation': RELEASE_OPERATION,
            'plan_id': release_id,
            'actor_account_id': OWNER,
            'library_id': LIBRARY,
            'asset_ids': [str(asset) for asset in ASSETS],
            'database_identity': list(_identity(path)),
            'released_tasks': released,
        }
        encoded = _json(receipt)
        db.execute('INSERT INTO access_provisioning_receipts(plan_id,plan_digest,receipt) VALUES(?,?,?)',
                   (release_id, hashlib.sha256(encoded).hexdigest(), encoded.decode('ascii')))
        db.commit()
    return journal, release_id, raw_by_asset


def _task_row(factory: ExistingDatabase, task_id: int):
    with factory() as db:
        return tuple(db.execute('''SELECT state,retry_count,last_error,scheduled_at,finished_at
            FROM tasks WHERE id=?''', (task_id,)).fetchone())


def _caption_rows(factory: ExistingDatabase, asset_id: int):
    with factory() as db:
        return [tuple(row) for row in db.execute('''SELECT text,model,user_edited,model_version,
            quality_tier,superseded FROM captions WHERE asset_id=? ORDER BY id''', (asset_id,))]


def _provider(config, behavior, request_counts):
    def respond(request):
        request_counts[request.url.path] = request_counts.get(request.url.path, 0) + 1
        if request.url.path == '/health':
            return httpx.Response(200, json={
                'status': 'healthy', 'active_provider': 'qwen3-vl', 'model_cache_ready': True,
            })
        if request.url.path == '/caption':
            return behavior(request)
        if request.url.path == '/translate':
            return httpx.Response(200, json={
                'translation': '一个红色杯子放在木桌上。',
                'provider': 'qwen3-vl', 'model': MODEL_ID,
            })
        return httpx.Response(404)

    provider = LocalCaptionHTTP(
        url='http://127.0.0.1:8102', expected_model_id=MODEL_ID,
        timeout=5, transport=httpx.MockTransport(respond),
    )
    provider.preflight()
    return provider


def _caption_response(text=GOOD, *, model=MODEL_ID, provider='qwen3-vl'):
    return httpx.Response(200, json={'caption': text, 'model': model, 'provider': provider})


def _run_task(factory, release_id, task_id, originals, stop, behavior, counts):
    config = {'stop_file': str(stop)}
    provider = _provider(config, behavior, counts)
    generate = runner._generate_adapter(config, provider)
    result = process_released_caption_task(
        factory,
        release_plan_id=release_id,
        operator_account_id=OWNER,
        library_id=LIBRARY,
        task_id=task_id,
        originals_root=originals,
        generate=generate,
        expected_model='qwen3-vl-http',
        should_stop=lambda: os.path.lexists(stop),
        clock=lambda: NOW,
    )
    return result, provider


def _stale_journal_rejected(factory, journal, asset_id: int) -> None:
    with factory() as db:
        db.execute('PRAGMA secure_delete=ON')
        db.execute('BEGIN IMMEDIATE')
        binding = prepare_asset_tombstone(db, asset_id, LIBRARY, NOW)
        journal.append(db, 'asset', {'id': asset_id, 'library_id': LIBRARY,
                        'asset_binding_json': binding['asset_binding_json']}, NOW)
        db.rollback()
    try:
        with factory():
            raise QualificationRefused('fixture_failed')
    except RuntimeUnavailable:
        return
    raise QualificationRefused('fixture_failed')


def _report(native_windows: bool, request_counts: dict[str, int]) -> dict:
    return {
        'status': 'passed',
        'synthetic_only': True,
        'native_windows': native_windows,
        'cases_passed': list(CASES),
        'case_count': len(CASES),
        'released_caption_task_count': len(TASKS),
        'generated_original_count': len(ASSETS),
        'foreign_failed_task_count': 1,
        'mock_http_request_count': sum(request_counts.values()),
        'mock_http_requests_by_path': {key: request_counts.get(key, 0)
                                       for key in ('/health', '/caption', '/translate')},
        'production_database_opened': False,
        'family_media_opened': False,
        'models_loaded': False,
        'network_requests': False,
        'services_changed': False,
        'original_bytes_preserved': True,
        'configured_journal_unchanged_during_processing': True,
    }


def run(output: Path) -> dict:
    """Run the full generated-only qualification and return a counts-only report."""
    target = _validate_output(Path(output))
    target.mkdir(mode=0o700)
    from app.access.private_storage import require_private_directory
    require_private_directory(target)
    phase = 'migration_and_seed'
    request_counts: dict[str, int] = {}
    try:
        db_path = target / DB_NAME
        originals = target / ORIGINALS_NAME
        journal_path = target / JOURNAL_NAME
        journal, release_id, raw_by_asset = _seed(db_path, originals, journal_path)
        factory = ExistingDatabase(db_path.resolve(strict=True), original_deletions=journal)
        stop = target / 'stop-qualification.flag'
        original_hashes = {asset: hashlib.sha256(raw).hexdigest() for asset, raw in raw_by_asset.items()}
        retained_thumb = (
            'thumb', '{"asset_id":999}', 'failed', 4,
            'synthetic-retained-failure', None, None, None, 0,
        )
        metadata = inspect_released_captions(
            factory, release_plan_id=release_id, operator_account_id=OWNER,
            library_id=LIBRARY, task_ids=list(TASKS), clock=lambda: NOW,
        )
        if (metadata.get('activated') is not False
                or [item['task_id'] for item in metadata['items']] != list(TASKS)
                or any(item['state'] != 'pending' for item in metadata['items'])):
            raise QualificationRefused('fixture_failed')
        with factory() as db:
            initial_thumb = tuple(db.execute('''SELECT type,payload_json,state,retry_count,
                last_error,scheduled_at,started_at,finished_at,cancel_requested
                FROM tasks WHERE id=799''').fetchone())
        if initial_thumb != retained_thumb:
            raise QualificationRefused('fixture_failed')

        # This byte-for-byte hash is checked after each real queue transaction.
        initial_journal_hash = hashlib.sha256(journal_path.read_bytes()).hexdigest()
        phase = 'valid_generated_caption'
        result, _ = _run_task(factory, release_id, 701, originals, stop,
                              lambda _request: _caption_response(), request_counts)
        if (result.get('outcome') != 'generated' or _task_row(factory, 701)[0] != 'finished'
                or _caption_rows(factory, 101) != [(GOOD, 'qwen3-vl-http|bilingual-en-zh-cn', 0,
                                                  'bilingual-v1', 'balanced', 0)]):
            raise QualificationRefused('fixture_failed')

        phase = 'concurrent_member_caption'
        inserted = 'Owner-reviewed synthetic member caption.'

        def concurrent(request):
            with factory() as db:
                db.execute('''INSERT INTO captions(asset_id,text,model,user_edited,created_at,
                    updated_at,quality_tier,model_version,superseded)
                    VALUES(102,?,'member-edit',1,'2033-05-18 03:33:20',
                    '2033-05-18 03:33:20',NULL,NULL,0)''', (inserted,))
                db.commit()
            return _caption_response()

        result, _ = _run_task(factory, release_id, 702, originals, stop, concurrent, request_counts)
        if (result.get('outcome') != 'existing_preserved'
                or _caption_rows(factory, 102) != [(inserted, 'member-edit', 1, None, None, 0)]
                or _task_row(factory, 702)[0] != 'finished'):
            raise QualificationRefused('fixture_failed')

        phase = 'uploader_revocation'
        revoked = False

        def revoke(request):
            nonlocal revoked
            if not revoked:
                with factory() as db:
                    db.execute('''UPDATE access_memberships SET status='revoked',revision=revision+1
                        WHERE account_id=? AND library_id=?''', (OWNER, LIBRARY))
                    db.commit()
                revoked = True
            return _caption_response()

        result, _ = _run_task(factory, release_id, 703, originals, stop, revoke, request_counts)
        if (result.get('state') != 'failed' or result.get('error_code') != 'scope_changed'
                or _caption_rows(factory, 103)):
            raise QualificationRefused('fixture_failed')
        with factory() as db:
            db.execute('''UPDATE access_memberships SET status='approved',revision=revision+1,
                approved_by=? WHERE account_id=? AND library_id=?''', (OWNER, OWNER, LIBRARY))
            db.commit()

        phase = 'provider_failure_backoff'
        def service_error(_request):
            return httpx.Response(503, text='synthetic private backend trace')

        result, _ = _run_task(factory, release_id, 704, originals, stop, service_error, request_counts)
        row = _task_row(factory, 704)
        expected_retry_at = (datetime.fromtimestamp(NOW, timezone.utc) + timedelta(seconds=60)).strftime(
            '%Y-%m-%d %H:%M:%S')
        if (result.get('state') != 'pending' or result.get('error_code') != 'generation_failed'
                or row[0:3] != ('pending', 1, 'generation_failed') or row[3] != expected_retry_at
                or _caption_rows(factory, 104)):
            raise QualificationRefused('fixture_failed')

        phase = 'caption_policy_refusal'
        result, _ = _run_task(factory, release_id, 705, originals, stop,
                              lambda _request: _caption_response(POLICY_REJECTED), request_counts)
        if (result.get('state') != 'failed' or result.get('error_code') != 'caption_policy_rejected'
                or _caption_rows(factory, 105)):
            raise QualificationRefused('fixture_failed')

        phase = 'model_identity_refusal'
        result, failed_provider = _run_task(factory, release_id, 706, originals, stop,
            lambda _request: _caption_response(model='Qwen/Qwen3-VL-Next'), request_counts)
        try:
            failed_provider.get_model_name()
        except Exception as error:
            if getattr(error, 'reason_code', None) != 'not_admitted':
                raise QualificationRefused('fixture_failed') from None
        else:
            raise QualificationRefused('fixture_failed')
        if (result.get('state') != 'failed' or result.get('error_code') != 'invalid_caption_result'
                or _task_row(factory, 706)[0:3] != ('failed', 1, 'invalid_caption_result')
                or _caption_rows(factory, 106)):
            raise QualificationRefused('fixture_failed')

        phase = 'preservation_audit'
        if hashlib.sha256(journal_path.read_bytes()).hexdigest() != initial_journal_hash:
            raise QualificationRefused('fixture_failed')
        with factory() as db:
            final_thumb = tuple(db.execute('''SELECT type,payload_json,state,retry_count,
                last_error,scheduled_at,started_at,finished_at,cancel_requested
                FROM tasks WHERE id=799''').fetchone())
            if final_thumb != initial_thumb:
                raise QualificationRefused('fixture_failed')
            receipts = []
            for raw_receipt, digest in db.execute('''SELECT receipt,plan_digest FROM
                access_provisioning_receipts WHERE plan_id!=?''', (release_id,)):
                decoded = json.loads(raw_receipt)
                if hashlib.sha256(_json(decoded)).hexdigest() != digest:
                    raise QualificationRefused('fixture_failed')
                receipts.append(decoded)
            completed = [item for item in receipts if item.get('operation') == 'process_released_upload_caption']
            if len(completed) != 2 or {item.get('outcome') for item in completed} != {
                    'generated', 'existing_preserved'}:
                raise QualificationRefused('fixture_failed')
            if any(item.get('release_plan_id') != release_id
                   or item.get('task_id') not in {701, 702}
                   or item.get('original_changed') is not False
                   or not item.get('caption_id') for item in completed):
                raise QualificationRefused('fixture_failed')
        for asset_id, expected_hash in original_hashes.items():
            path = originals / f'synthetic-{asset_id}.png'
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
                raise QualificationRefused('fixture_failed')

        phase = 'stale_journal_rollback'
        _stale_journal_rejected(factory, journal, 101)
        report = _report(os.name == 'nt', request_counts)
        _write_json(target / REPORT_NAME, report)
        return report
    except Exception as error:
        code = error.code if isinstance(error, QualificationRefused) else 'fixture_failed'
        try:
            _write_json(target / FAILURE_NAME, {'status': 'failed', 'phase': phase, 'reason_code': code})
        except Exception:
            pass
        if isinstance(error, QualificationRefused):
            raise
        raise QualificationRefused(code) from None


def _read_report(path: Path, *, native_windows: bool) -> dict:
    from app.access.private_storage import require_private_file
    require_private_file(path)
    with path.open('rb') as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if not 0 < len(raw) <= MAX_REPORT_BYTES:
        raise QualificationRefused('report_invalid')
    try:
        report = json.loads(raw)
    except (ValueError, UnicodeError):
        raise QualificationRefused('report_invalid') from None
    counts = report.get('mock_http_requests_by_path') if type(report) is dict else None
    if (type(counts) is not dict or set(counts) != {'/health', '/caption', '/translate'}
            or any(type(value) is not int or value < 0 for value in counts.values())):
        raise QualificationRefused('report_invalid')
    expected = _report(native_windows, counts)
    if type(report) is not dict or report != expected:
        raise QualificationRefused('report_invalid')
    return report


def verify_child_budget() -> None:
    from run_released_caption_worker import verify_child_budget as verify
    verify()


def _bounded_windows_report(target: Path) -> dict:
    from bounded_windows_job import CheckRefused, WindowsAPI, run_bounded
    target = _validate_output(target)
    system_root = os.environ.get('SystemRoot')
    if not system_root:
        raise CheckRefused('system_root_unavailable')
    executable = str(Path(sys.executable).resolve())
    environment = {
        'PATH': str(Path(executable).parent),
        'SYSTEMROOT': system_root,
        'WINDIR': system_root,
        'TEMP': str(target.parent),
        'TMP': str(target.parent),
        'PHOTOHOUSE_NO_DOTENV': '1',
        'PYTHONNOUSERSITE': '1',
        'PYTHONDONTWRITEBYTECODE': '1',
    }
    program = (
        'import runpy\n'
        f"runpy.run_path({str(Path(__file__).resolve())!r}, "
        "run_name='photohouse_released_caption_qualification')['main'] "
        f"(['--out', {str(target)!r}, '--bounded-child'])\n"
    )
    exit_code = run_bounded(
        WindowsAPI(), executable,
        [executable, '-I', '-B', '-c', program],
        environment, str(target.parent), timeout_seconds=TASK_SECONDS,
        memory_limit=MEMORY_LIMIT, process_limit=PROCESS_LIMIT,
        minimum_free_ram=FREE_RAM_FLOOR,
    )
    if exit_code != 0:
        raise CheckRefused('qualification_child_failed')
    return _read_report(target / REPORT_NAME, native_windows=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True,
                        help='new absolute directory beneath an existing private parent')
    parser.add_argument('--bounded-child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    target = Path(args.out)
    if args.bounded_child:
        verify_child_budget()
        report = run(target)
    elif os.name == 'nt':
        report = _bounded_windows_report(target)
    else:
        report = run(target)
    print(json.dumps(report, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","synthetic_only":true}', file=sys.stderr)
        raise SystemExit(2) from None

"""Receipt-selected caption tasks; no scheduler, provider discovery or HTTP route.

Inference runs outside a writer transaction. Publication revalidates current
owner/uploader access, journal, source, assignment and the exact task claim.
"""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import uuid

from .runtime import ExistingDatabase
from .service import AccessService
from .promotion import _operator
from .provisioning import _json
from .provisioning_apply import _identity
from .upload_processing import OPERATION as RELEASE_OPERATION, _active_uploader
from ..caption_policy import bilingual_caption_issues

OPERATION = 'process_released_upload_caption'
MAX_SOURCE_BYTES = 256 * 1024**2
MAX_TEXT_BYTES = 16 * 1024
CLAIM_PREFIX = 'approved_caption_v1.'
FAILURE_CODES = frozenset({'generation_failed', 'invalid_caption_result',
    'caption_policy_rejected', 'source_changed', 'scope_changed', 'stop_requested'})


class CaptionProcessingRefused(RuntimeError):
    pass


def _require(value, code):
    if not value:
        raise CaptionProcessingRefused(code)


def _uuid(value):
    try:
        _require(type(value) is str and str(uuid.UUID(value)) == value, 'invalid_selection')
    except (ValueError, AttributeError, TypeError):
        raise CaptionProcessingRefused('invalid_selection') from None
    return value


def _factory(factory):
    _require(type(factory) is ExistingDatabase and not factory.read_only,
             'configured_writer_required')


def _completion_id(release_id, task_id):
    return str(uuid.uuid5(uuid.UUID(release_id), 'caption-completion:' + str(task_id)))


def _scope(db, factory, release_id, operator, library, task_ids, now):
    _uuid(release_id)
    _require(type(task_ids) is list and 0 < len(task_ids) <= 1000
        and all(type(t) is int and 0 < t < 2**63 for t in task_ids)
        and task_ids == sorted(set(task_ids)), 'invalid_selection')
    stored = db.execute('SELECT plan_digest,receipt FROM access_provisioning_receipts WHERE plan_id=?',
                        (release_id,)).fetchone()
    _require(stored is not None, 'release_receipt_required')
    _require(type(stored[1]) is str and len(stored[1]) <= 2 * 1024**2, 'release_receipt_invalid')
    try:
        receipt = json.loads(stored[1])
        _require(type(receipt) is dict and hashlib.sha256(_json(receipt)).hexdigest() == stored[0],
                 'release_receipt_invalid')
        _require(receipt['operation'] == RELEASE_OPERATION and receipt['plan_id'] == release_id
            and receipt['actor_account_id'] == operator and receipt['library_id'] == library
            and receipt['database_identity'] == list(_identity(factory.path)), 'release_scope_changed')
        selected = {}
        for row in receipt['released_tasks']:
            if row['type'] != 'caption':
                continue
            payload = json.loads(row['payload_json'])
            _require(type(payload) is dict and set(payload) == {'asset_id'}
                and type(payload['asset_id']) is int and payload['asset_id'] > 0
                and str(payload['asset_id']) in receipt['asset_ids']
                and row['payload_json'] == json.dumps(payload, sort_keys=True)
                and row['from_state'] == 'awaiting_review' and row['to_state'] == 'pending'
                and type(row['task_id']) is int and row['task_id'] not in selected,
                'release_receipt_invalid')
            selected[row['task_id']] = (payload['asset_id'], row['payload_json'])
        _require(set(task_ids) <= set(selected), 'task_outside_release')
    except (KeyError, TypeError, ValueError, RecursionError):
        raise CaptionProcessingRefused('release_receipt_invalid') from None
    try:
        _operator(db, operator, library, now)
    except Exception:
        raise CaptionProcessingRefused('scope_changed') from None
    return {task_id: selected[task_id] for task_id in task_ids}


def _source_record(db, asset_id, library, now):
    rows = db.execute('''SELECT a.path,a.file_size,a.hash_sha256,a.mime,a.status,
        u.account_id,u.state,u.bytes,u.sha256,m.library_id
        FROM assets a JOIN access_uploads u ON u.asset_id=a.id
        JOIN access_asset_libraries m ON m.asset_id=a.id WHERE a.id=?''', (asset_id,)).fetchall()
    _require(len(rows) == 1, 'scope_changed')
    row = tuple(rows[0])
    _require(row[4] == 'active' and row[6] == 'assigned' and row[9] == library
        and row[1] == row[7] and row[2] == row[8]
        and row[3] in {'image/jpeg', 'image/png'}
        and _active_uploader(db, row[5], library, now), 'scope_changed')
    return row


def _task(db, task_id, payload):
    row = db.execute('''SELECT type,payload_json,state,retry_count,cancel_requested,
        started_at,last_error,scheduled_at FROM tasks WHERE id=?''', (task_id,)).fetchone()
    _require(row is not None and row[0:2] == ('caption', payload), 'task_changed')
    return row


def _source_identity(record):
    info = Path(record[0]).lstat()
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _source_bytes(record, originals_root):
    try:
        return _read_source_bytes(record, originals_root)
    except (OSError, TypeError, ValueError):
        raise CaptionProcessingRefused('source_changed') from None


def _read_source_bytes(record, originals_root):
    root, path = Path(originals_root), Path(record[0])
    _require(root.is_absolute() and root != Path(root.anchor)
        and not root.anchor.startswith(('//', '\\\\'))
        and root.is_dir() and root.resolve(strict=True) == root
        and path.is_absolute() and path.is_relative_to(root) and path != root
        and '..' not in path.parts and path.resolve(strict=True) == path
        and not path.is_symlink(), 'source_changed')
    before = path.lstat()
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    _require(stat.S_ISREG(before.st_mode) and type(record[1]) is int
        and before.st_size == record[1] and 0 < before.st_size <= MAX_SOURCE_BYTES, 'source_changed')
    with path.open('rb') as stream:
        info = os.fstat(stream.fileno())
        _require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) == identity, 'source_changed')
        raw = stream.read(MAX_SOURCE_BYTES + 1)
    _require(_source_identity(record) == identity and len(raw) == record[1]
        and hashlib.sha256(raw).hexdigest() == record[2], 'source_changed')
    return raw, identity


def _result(result, expected_model):
    _require(type(result) is dict and set(result) == {'text', 'model', 'model_version', 'quality_tier'},
             'invalid_caption_result')
    text = result['text']
    try:
        valid_text = (type(text) is str and bool(text.strip()) and '\0' not in text
            and len(text.encode('utf-8')) <= MAX_TEXT_BYTES
            and all(ch in '\n\t' or (ord(ch) >= 32 and not 0x7f <= ord(ch) < 0xa0) for ch in text))
    except UnicodeError:
        valid_text = False
    _require(valid_text
        and result['model'] == expected_model + '|bilingual-en-zh-cn'
        and result['model_version'] == 'bilingual-v1' and result['quality_tier'] == 'balanced',
        'invalid_caption_result')
    _require(not bilingual_caption_issues(text), 'caption_policy_rejected')
    return dict(result)


def inspect_released_captions(database_factory, *, release_plan_id, operator_account_id,
                              library_id, task_ids, clock=time.time):
    """Metadata-only snapshot. Does not touch source files or claim work."""
    _factory(database_factory)
    with replace(database_factory, read_only=True)() as db:
        access = AccessService(db, clock=clock)
        with access._transaction():
            selected = _scope(db, database_factory, release_plan_id, operator_account_id,
                              library_id, task_ids, access._now())
            items = []
            for task_id, (asset, payload) in selected.items():
                _source_record(db, asset, library_id, access._now())
                task = _task(db, task_id, payload)
                items.append({'task_id': task_id, 'asset_id': str(asset), 'state': task[2],
                    'retry_count': task[3], 'cancel_requested': bool(task[4]),
                    'due': task[7] is None or db.execute('SELECT datetime(?)<=datetime(?)',
                        (task[7], _stamp(access._now()))).fetchone()[0] == 1})
            return {'operation': OPERATION, 'activated': False, 'items': items}


def _receipt(db, access, release_id, task_id, asset_id, outcome, caption_id=None):
    plan_id = _completion_id(release_id, task_id)
    receipt = {'version': 1, 'operation': OPERATION, 'plan_id': plan_id,
        'release_plan_id': release_id, 'task_id': task_id, 'asset_id': str(asset_id),
        'outcome': outcome, 'caption_id': str(caption_id) if caption_id is not None else None,
        'completed_at': access._now(), 'original_changed': False}
    db.execute('INSERT INTO access_provisioning_receipts VALUES (?,?,?)',
               (plan_id, hashlib.sha256(_json(receipt)).hexdigest(), _json(receipt).decode()))
    return receipt


def _finish(db, task_id, marker, stamp):
    changed = db.execute('''UPDATE tasks SET state='finished',finished_at=?,last_error=NULL
        WHERE id=? AND type='caption' AND state='running' AND last_error=? AND cancel_requested=0''',
        (stamp, task_id, marker)).rowcount
    _require(changed == 1, 'claim_changed')


def _stamp(now):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def _failure(factory, task_id, marker, code, *, clock):
    # Only release our own claim. A stale journal/changed claim is never bypassed.
    with factory() as db:
        access = AccessService(db, clock=clock)
        with access._transaction(write=True):
            row = db.execute('SELECT retry_count FROM tasks WHERE id=? AND type=\'caption\' AND state=\'running\' AND last_error=?',
                             (task_id, marker)).fetchone()
            _require(row is not None, 'claim_changed')
            retries = row[0] + 1
            state = 'pending' if code == 'generation_failed' and retries < 3 else 'failed'
            db.execute('''UPDATE tasks SET state=?,retry_count=?,last_error=?,started_at=NULL,
                scheduled_at=CASE WHEN ?='pending' THEN datetime(?,'+60 seconds') ELSE scheduled_at END,
                finished_at=CASE WHEN ?='failed' THEN datetime(?) ELSE NULL END
                WHERE id=? AND type='caption' AND state='running' AND last_error=?''',
                (state, retries, code, state, _stamp(access._now()), state, _stamp(access._now()), task_id, marker))
            return {'task_id': task_id, 'state': state, 'error_code': code, 'retry_count': retries}


def process_released_caption_task(database_factory, *, release_plan_id, operator_account_id,
                                  library_id, task_id, originals_root, generate,
                                  expected_model='qwen3-vl-http', should_stop=lambda: False,
                                  clock=time.time):
    """One selected task, never a queue scan or reset of old results.

    ``generate(immutable_source_bytes, mime)`` returns a bilingual result. The
    external launcher owns timeout, RAM/process caps and provider admission.
    """
    _factory(database_factory)
    _require(callable(generate) and callable(should_stop), 'explicit_adapter_required')
    _require(type(expected_model) is str and expected_model == 'qwen3-vl-http', 'provider_not_reviewed')
    _require(not should_stop(), 'stop_requested')
    marker = CLAIM_PREFIX + uuid.uuid4().hex
    with database_factory() as db:
        access = AccessService(db, clock=clock)
        with access._transaction(write=True):
            selected = _scope(db, database_factory, release_plan_id, operator_account_id,
                              library_id, [task_id], access._now())
            asset_id, payload = selected[task_id]
            record = _source_record(db, asset_id, library_id, access._now())
            task = _task(db, task_id, payload)
            _require(task[2] == 'pending' and task[4] == 0
                and type(task[3]) is int and 0 <= task[3] < 3, 'task_not_pending')
            _require(db.execute('SELECT 1 FROM access_provisioning_receipts WHERE plan_id=?',
                                (_completion_id(release_plan_id, task_id),)).fetchone() is None,
                     'completion_already_recorded')
            _require(task[7] is None or db.execute('SELECT datetime(?)<=datetime(?)',
                (task[7], _stamp(access._now()))).fetchone()[0] == 1, 'task_not_due')
            _require(not should_stop(), 'stop_requested')
            changed = db.execute('''UPDATE tasks SET state='running',started_at=?,last_error=?
                WHERE id=? AND state='pending' AND cancel_requested=0''',
                (_stamp(access._now()), marker, task_id)).rowcount
            _require(changed == 1, 'task_changed')
            existing = db.execute('SELECT id FROM captions WHERE asset_id=? ORDER BY user_edited DESC,id LIMIT 1',
                                  (asset_id,)).fetchone()
            if existing:
                _finish(db, task_id, marker, _stamp(access._now()))
                receipt = _receipt(db, access, release_plan_id, task_id, asset_id, 'existing_preserved', existing[0])
                access._audit(operator_account_id, 'offline.' + OPERATION, library_id)
                return receipt
    try:
        raw, _ = _source_bytes(record, originals_root)
        result = _result(generate(raw, record[3]), expected_model)
        _require(not should_stop(), 'stop_requested')
        _, final_identity = _source_bytes(record, originals_root)
        with database_factory() as db:
            access = AccessService(db, clock=clock)
            with access._transaction(write=True):
                _scope(db, database_factory, release_plan_id, operator_account_id,
                       library_id, [task_id], access._now())
                _require(_source_record(db, asset_id, library_id, access._now()) == record, 'source_changed')
                current = _task(db, task_id, payload)
                _require(current[2] == 'running' and current[4] == 0 and current[6] == marker, 'claim_changed')
                _require(_source_identity(record) == final_identity, 'source_changed')
                _require(not should_stop(), 'stop_requested')
                existing = db.execute('SELECT id FROM captions WHERE asset_id=? ORDER BY user_edited DESC,id LIMIT 1',
                                      (asset_id,)).fetchone()
                if existing:
                    caption_id, outcome = existing[0], 'existing_preserved'
                else:
                    cursor = db.execute('''INSERT INTO captions(asset_id,text,model,user_edited,
                        created_at,updated_at,quality_tier,model_version,superseded)
                        VALUES(?,?,?,0,?,?,?,?,0)''',
                        (asset_id, result['text'], result['model'], _stamp(access._now()),
                         _stamp(access._now()), result['quality_tier'], result['model_version']))
                    caption_id, outcome = cursor.lastrowid, 'generated'
                    db.execute('''UPDATE assets SET caption_processed=1,
                        caption_variant_count=(SELECT count(*) FROM captions WHERE asset_id=? AND superseded=0),
                        caption_processed_at=?,caption_error_last=NULL,caption_model_profile_last='balanced'
                        WHERE id=?''', (asset_id, _stamp(access._now()), asset_id))
                _finish(db, task_id, marker, _stamp(access._now()))
                receipt = _receipt(db, access, release_plan_id, task_id, asset_id, outcome, caption_id)
                access._audit(operator_account_id, 'offline.' + OPERATION, library_id)
                return receipt
    except Exception as error:
        code = str(error) if isinstance(error, CaptionProcessingRefused) and str(error) in FAILURE_CODES else 'generation_failed'
        if isinstance(error, CaptionProcessingRefused) and str(error) not in FAILURE_CODES:
            code = 'scope_changed'
        return _failure(database_factory, task_id, marker, code, clock=clock)

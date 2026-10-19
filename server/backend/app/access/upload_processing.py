"""Explicit, receipt-bound release of upload starter tasks held for owner review.

This module has no HTTP or startup wiring. Callers must select the existing database
and its configured guards explicitly, and provide the exact task rows they reviewed.
"""
import hashlib
import json
import time
import uuid

from .provisioning import PlanRejected, _json, _library
from .provisioning_apply import _identity, plan_digest
from .promotion import PROMOTE_OPERATION, _operator
from .runtime import ExistingDatabase
from .service import AccessService

OPERATION = 'release_deferred_upload_starters'
STARTER_TYPES = frozenset({'embed', 'phash', 'thumb', 'caption', 'face', 'video_probe'})


def _selection(asset_ids):
    if (type(asset_ids) is not list or not asset_ids or len(asset_ids) > 10000
            or any(type(value) is not int or not 1 <= value <= 2**63 - 1 for value in asset_ids)
            or asset_ids != sorted(set(asset_ids))):
        raise PlanRejected('Exact sorted asset selection required')
    return asset_ids


def _expected_rows(rows, asset_ids):
    if type(rows) is not list or not rows:
        raise PlanRejected('Exact held task selection required')
    result = []
    seen = set()
    for row in rows:
        if type(row) is not dict or set(row) != {'id', 'type', 'payload_json', 'state'}:
            raise PlanRejected('Invalid held task selection')
        task_id, kind, payload, state = (row['id'], row['type'], row['payload_json'], row['state'])
        if (type(task_id) is not int or task_id < 1 or task_id in seen
                or not isinstance(kind, str) or kind not in STARTER_TYPES or state != 'awaiting_review'
                or not isinstance(payload, str)):
            raise PlanRejected('Invalid held task selection')
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            raise PlanRejected('Invalid held task payload') from None
        if type(decoded) is not dict or set(decoded) not in ({'asset_id'}, {'asset_id', 'modality'}):
            raise PlanRejected('Invalid held task payload')
        asset_id = decoded.get('asset_id')
        if type(asset_id) is not int or asset_id not in asset_ids:
            raise PlanRejected('Held task is outside the selected assets')
        if ((kind == 'embed' and decoded.get('modality') != 'image')
                or (kind != 'embed' and 'modality' in decoded)):
            raise PlanRejected('Invalid starter task payload')
        if kind == 'video_probe' and 'modality' in decoded:
            raise PlanRejected('Invalid starter task payload')
        # Match the canonical payloads emitted by UploadRuntime exactly.
        canonical = json.dumps(decoded, sort_keys=True)
        if payload != canonical:
            raise PlanRejected('Invalid starter task payload')
        seen.add(task_id)
        result.append((task_id, kind, payload, state))
    if len({json.loads(row[2])['asset_id'] for row in result}) != len(asset_ids):
        raise PlanRejected('Held tasks must cover every selected asset')
    return sorted(result)


def _actual_starters(db, asset_ids):
    found = []
    # Tasks are small metadata rows. Parsing the table avoids SQL JSON-extension
    # dependencies and detects changed state as well as newly added starter rows.
    for row in db.execute('SELECT id,type,payload_json,state,cancel_requested FROM tasks ORDER BY id'):
        try:
            payload = json.loads(row[2])
        except (TypeError, ValueError):
            continue
        if type(payload) is dict and type(payload.get('asset_id')) is int and payload['asset_id'] in asset_ids:
            if row[4] != 0:
                raise PlanRejected('A held starter task has a cancellation request')
            found.append((row[0], row[1], row[2], row[3]))
    return sorted(found)


def _active_uploader(db, account_id, library_id, now):
    row = db.execute('''SELECT a.state,m.status,m.role,m.expires_at
        FROM access_accounts a JOIN access_memberships m ON m.account_id=a.id
        WHERE a.id=? AND m.library_id=?''', (account_id, library_id)).fetchone()
    return bool(row and row[0] == 'active' and row[1] == 'approved'
                and row[2] in {'viewer', 'contributor', 'owner'}
                and (row[3] is None or row[3] > now))


def release_deferred_upload_starters(envelope, *, database_factory, database_identity,
                                     operator_account_id, library_id, asset_ids,
                                     expected_tasks, authority_reference, clock=time.time):
    """Release only the exact held starters from one deferred manual promotion.

    ``database_factory`` must be the already configured ExistingDatabase instance;
    passing it through preserves any external deletion journal guard on its connection.
    Replays fail closed, including after an earlier release partially progressed.
    """
    if type(database_factory) is not ExistingDatabase:
        raise PlanRejected('Explicit existing database factory required')
    if (not isinstance(database_identity, tuple) or len(database_identity) != 2
            or any(type(value) is not int or value < 0 for value in database_identity)):
        raise PlanRejected('Explicit database identity required')
    if _identity(database_factory.path) != database_identity:
        raise PlanRejected('Release target changed')
    digest = plan_digest(envelope)
    envelope = json.loads(_json(envelope))
    if plan_digest(envelope) != digest:
        raise PlanRejected('Promotion envelope changed')
    try:
        plan = envelope['plan']
        target = plan['target']
        original_plan_id = plan['plan_id']
    except (KeyError, TypeError):
        raise PlanRejected('Exact deferred promotion required') from None
    if type(plan) is not dict or type(target) is not dict or not isinstance(original_plan_id, str):
        raise PlanRejected('Exact deferred promotion required')
    assets = _selection(asset_ids)
    expected = _expected_rows(expected_tasks, assets)
    library = _library(library_id)
    if (plan.get('operation') != PROMOTE_OPERATION
            or target.get('operator_account_id') != operator_account_id
            or target.get('library_id') != library
            or target.get('asset_ids') != [str(item) for item in assets]):
        raise PlanRejected('Promotion selection does not match release scope')
    from .provisioning_apply import _reference
    _reference(authority_reference)

    with database_factory() as db:
        access = AccessService(db, clock=clock)
        with access._transaction(write=True):
            if _identity(database_factory.path) != database_identity:
                raise PlanRejected('Release target changed')
            now = access._now()
            _operator(db, operator_account_id, library, now)
            stored = db.execute('''SELECT plan_digest,receipt FROM access_provisioning_receipts
                WHERE plan_id=?''', (original_plan_id,)).fetchone()
            if stored is None:
                raise PlanRejected('Deferred promotion receipt required')
            try:
                original_receipt = json.loads(stored[1])
            except (TypeError, ValueError):
                raise PlanRejected('Deferred promotion receipt invalid') from None
            if type(original_receipt) is not dict:
                raise PlanRejected('Deferred promotion receipt invalid')
            if (stored[0] != digest or original_receipt.get('plan_id') != original_plan_id
                    or original_receipt.get('plan_digest') != digest
                    or original_receipt.get('operation') != PROMOTE_OPERATION
                    or original_receipt.get('processing_deferred') is not True
                    or original_receipt.get('actor_account_id') != operator_account_id
                    or original_receipt.get('library_id') != library
                    or original_receipt.get('database_identity') != list(database_identity)):
                raise PlanRejected('Promotion was not deferred for this exact scope')
            # A release receipt is immutable and uniquely tied to this original plan.
            for (raw_receipt,) in db.execute('SELECT receipt FROM access_provisioning_receipts'):
                try:
                    existing = json.loads(raw_receipt)
                except (TypeError, ValueError):
                    continue
                if type(existing) is not dict:
                    continue
                if (existing.get('operation') == OPERATION
                        and existing.get('original_plan_id') == original_plan_id):
                    raise PlanRejected('Deferred starter release already recorded')

            placeholders = ','.join('?' for _ in assets)
            upload_rows = db.execute(f'''SELECT u.asset_id,u.account_id,u.state,u.approval_mode,
                    a.status,m.library_id
                FROM access_uploads u JOIN assets a ON a.id=u.asset_id
                LEFT JOIN access_asset_libraries m ON m.asset_id=u.asset_id
                WHERE u.asset_id IN ({placeholders}) ORDER BY u.asset_id''', assets).fetchall()
            if len(upload_rows) != len(assets):
                raise PlanRejected('Selected upload assignment changed')
            for asset_id, uploader, state, mode, asset_state, assigned_library in upload_rows:
                if ((state, mode, asset_state, assigned_library) !=
                        ('assigned', 'manual', 'active', library)
                        or not _active_uploader(db, uploader, library, now)):
                    raise PlanRejected('Upload assignment or membership changed')

            actual = _actual_starters(db, set(assets))
            if actual != expected:
                raise PlanRejected('Held starter tasks changed; review again')
            if any(row[3] != 'awaiting_review' for row in actual):
                raise PlanRejected('A starter task has already started')

            released = []
            for task_id, kind, payload, state in expected:
                changed = db.execute('''UPDATE tasks SET state='pending',scheduled_at=datetime('now')
                    WHERE id=? AND type=? AND payload_json=? AND state='awaiting_review' ''',
                    (task_id, kind, payload)).rowcount
                if changed != 1:
                    raise PlanRejected('Held starter task changed during release')
                released.append({'task_id': task_id, 'type': kind,
                                 'payload_json': payload, 'from_state': state,
                                 'to_state': 'pending'})

            receipt = {'version': 1, 'operation': OPERATION,
                'plan_id': str(uuid.uuid4()), 'applied_at': now,
                'authority_reference': authority_reference,
                'actor_account_id': operator_account_id, 'library_id': library,
                'asset_ids': [str(item) for item in assets],
                'original_plan_id': original_plan_id, 'original_plan_digest': digest,
                'database_identity': list(database_identity), 'released_tasks': released,
                'original_promotion_receipt_preserved': True, 'media_writes': False}
            receipt_digest = hashlib.sha256(_json(receipt)).hexdigest()
            db.execute('INSERT INTO access_provisioning_receipts VALUES (?,?,?)',
                       (receipt['plan_id'], receipt_digest, _json(receipt).decode()))
            access._audit(operator_account_id, 'offline.' + OPERATION, library, None)
            return receipt

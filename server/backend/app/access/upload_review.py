"""Explicit operator/owner inbox for single-photo, sealed upload approval.

Pending bytes stay outside normal media roots. An admin can see uploads only from
current members of the selected library; system operator status alone grants no
family access. No anonymous TV publication, original download, or job retry.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
from pathlib import Path
import time
import uuid
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _integer, _query
from .promotion import (PROMOTE_OPERATION, PromotionPlanner, PromotionReview,
                        _operator, promote_and_assign)
from .provisioning import PlanRejected
from .provisioning_apply import _identity, plan_digest
from .runtime import ExistingDatabase
from .service import AccessDenied, AccessService
from .transport import TransportError, _body, _runtime, credentials_from_request
from .upload import UploadRuntime
from .resumable import MAX_IMAGE_BYTES, MAX_VIDEO_BYTES
from ..home_feed import Refused
from ..photo_delivery import PhotoCache, source_pin

router = APIRouter(route_class=LibraryRoute)
SOURCE = ''' FROM access_uploads u JOIN assets a ON a.id=u.asset_id
    JOIN access_accounts p ON p.id=u.account_id
    JOIN access_memberships m ON m.account_id=p.id AND m.library_id=?
    LEFT JOIN access_asset_libraries scope ON scope.asset_id=a.id
    WHERE p.state='active' AND m.status='approved'
    AND (m.expires_at IS NULL OR m.expires_at>?)
    AND (a.status IS NULL OR a.status='active')'''
PENDING = " AND u.state='incoming' AND scope.asset_id IS NULL"


@dataclass(frozen=True)
class UploadReviewRuntime:
    upload: UploadRuntime
    photo_cache: object = None

    def __post_init__(self):
        # Multiple original roots require an explicit future destination policy.
        if (not isinstance(self.upload, UploadRuntime)
                or not isinstance(self.upload.access.connection_factory, ExistingDatabase)
                or len(self.upload.original_roots) != 1):
            raise ValueError('One explicit upload destination and database required')

    @property
    def database(self):
        return self.upload.access.connection_factory.path

    def _service(self, db):
        return AccessService(db, clock=self.upload.access.clock)

    def _owner(self, access, token, library, *, operator=True):
        member = access._member(token, library, owner=True)
        if operator:
            try:
                _operator(access.db, member['account_id'], library, access._now())
            except PlanRejected:
                raise AccessDenied('Access denied') from None
        return member['account_id']

    def policies(self, token, library):
        """Owner-only readback; absence from the table means review is required."""
        with ExistingDatabase(self.database, read_only=True)() as db:
            access = self._service(db)
            with access._transaction():
                self._owner(access, token, library, operator=False)
                rows = db.execute('''SELECT p.account_id,p.enabled,p.revision
                    FROM access_upload_auto_policies p
                    JOIN access_memberships m ON m.account_id=p.account_id AND m.library_id=p.library_id
                    JOIN access_accounts a ON a.id=p.account_id
                    WHERE p.library_id=? AND m.status='approved' AND a.state='active'
                    ORDER BY p.account_id''', (library,)).fetchall()
                return {'library_id': library, 'items': [
                    {'member_id': row[0], 'enabled': bool(row[1]), 'revision': row[2]}
                    for row in rows]}

    def set_policy(self, token, library, member_id, mode):
        """Only a current owner can opt a current library member into auto approval."""
        if mode not in {'on', 'off'}:
            raise TransportError(400, 'Invalid policy')
        try:
            if str(uuid.UUID(member_id)) != member_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise TransportError(400, 'Invalid member') from None
        from .provisioning import _library
        _library(library)
        with ExistingDatabase(self.database)() as db:
            access = self._service(db)
            with access._transaction(write=True):
                owner = self._owner(access, token, library, operator=(mode == 'on'))
                target = access._one('''SELECT m.status,m.expires_at,a.state FROM access_memberships m
                    JOIN access_accounts a ON a.id=m.account_id
                    WHERE m.account_id=? AND m.library_id=?''', (member_id, library))
                if target is None or (mode == 'on' and (target['status'] != 'approved'
                        or target['state'] != 'active' or (target['expires_at'] is not None
                        and target['expires_at'] <= access._now()))):
                    raise AccessDenied('Access denied')
                prior = access._one('''SELECT revision FROM access_upload_auto_policies
                    WHERE library_id=? AND account_id=?''', (library, member_id))
                revision = prior['revision'] + 1 if prior else 1
                db.execute('''INSERT INTO access_upload_auto_policies
                    (library_id,account_id,enabled,revision,enabled_by,updated_at)
                    VALUES (?,?,?,?,?,?) ON CONFLICT(library_id,account_id) DO UPDATE SET
                    enabled=excluded.enabled,revision=excluded.revision,
                    enabled_by=excluded.enabled_by,updated_at=excluded.updated_at''',
                    (library, member_id, int(mode == 'on'), revision, owner, access._now()))
                access._audit(owner, 'upload.auto_approval.' + ('enable' if mode == 'on' else 'disable'),
                              library, member_id)
                return {'library_id': library, 'member_id': member_id,
                        'enabled': mode == 'on', 'revision': revision}

    def auto_approve(self, token, library, asset):
        """Try the sealed promotion once for a newly received, destination-bound item.

        Missing or changed authority leaves the item in the private owner inbox.
        Caller invokes this only on first receipt, never on a later policy change or
        a lost-response replay.
        """
        from .provisioning import _library
        _library(library)
        if type(asset) is not int or not 1 <= asset <= 2**63 - 1:
            raise TransportError(400, 'Invalid asset')
        try:
            with ExistingDatabase(self.database, read_only=True)() as db:
                access = self._service(db)
                with access._transaction():
                    session = access._session(token)
                    member = access._member(token, library)
                    row = access._one('''SELECT u.account_id,u.destination_library_id,u.state,
                        u.approval_mode,p.enabled,p.revision,p.enabled_by
                        FROM access_uploads u JOIN access_libraries l ON l.id=?
                        LEFT JOIN access_upload_auto_policies p
                        ON p.library_id=l.id AND p.account_id=u.account_id
                        WHERE u.asset_id=?''', (library, asset))
                    if (row is None or row['account_id'] != session['account_id']
                            or row['destination_library_id'] != library or row['state'] != 'incoming'
                            or row['approval_mode'] is not None or row['enabled'] != 1):
                        return False
                    self._pending_path(self._item(access, library, asset))
                    operator = row['enabled_by']
                    _operator(db, operator, library, access._now())
                    member_revision, policy_revision = member['revision'], row['revision']
                envelope = PromotionPlanner(db, clock=access.clock).promote(
                    library_id=library, operator_account_id=operator, asset_ids=[asset])

            def authorize(access, checked):
                if (checked['target']['library_id'] != library
                        or checked['target']['operator_account_id'] != operator
                        or checked['target']['asset_ids'] != [str(asset)]):
                    raise AccessDenied('Access denied')
                session = access._session(token)
                access._member(token, library, expected_revision=member_revision)
                policy = access._one('''SELECT enabled,revision FROM access_upload_auto_policies
                    WHERE library_id=? AND account_id=?''', (library, session['account_id']))
                upload = access._one('''SELECT account_id,destination_library_id,state,approval_mode
                    FROM access_uploads WHERE asset_id=?''', (asset,))
                if (policy is None or policy['enabled'] != 1 or policy['revision'] != policy_revision
                        or upload is None or upload['account_id'] != session['account_id']
                        or upload['destination_library_id'] != library
                        or (upload['state'], upload['approval_mode'])
                        not in {('incoming', None), ('assigned', 'automatic')}):
                    raise AccessDenied('Access denied')
                item = self._item(access, library, asset, allow_assigned=True)
                if upload['state'] == 'incoming':
                    self._pending_path(item)

            review = PromotionReview(database=self.database, database_identity=_identity(self.database),
                plan_digest=plan_digest(envelope), authority_reference='owner-auto-upload-v1',
                incoming_root=self.upload.incoming_root, originals_root=self.upload.original_roots[0])
            promote_and_assign(envelope, review=review, clock=self.upload.access.clock,
                               authorize=authorize, approval_mode='automatic')
            return True
        except (AccessDenied, PlanRejected):
            # A policy/audience race can safely fall back to owner review only if
            # the source remains an intact private incoming item after rollback.
            with ExistingDatabase(self.database, read_only=True)() as db:
                access = self._service(db)
                with access._transaction():
                    item = self._item(access, library, asset)
                    path = self._pending_path(item)
                    if path.is_file() and path.stat().st_size == item[4]:
                        return False
            raise

    def _item(self, access, library, asset, *, allow_assigned=False):
        row = access.db.execute('''SELECT a.path,u.incoming_label,u.batch,u.sha256,u.bytes,
            a.mime,a.hash_sha256,a.file_size,u.state,scope.library_id,
            u.destination_library_id''' + SOURCE + ' AND a.id=?',
            (library, access._now(), asset)).fetchone()
        if (row is None or row[10] not in (None, library)
                or not (row[8:10] == ('incoming', None) or
                        (allow_assigned and row[8:10] == ('assigned', library)))):
            raise AccessDenied('Access denied')
        if (row[3] != row[6] or row[4] != row[7] or not 0 < row[4] <= (MAX_VIDEO_BYTES if row[5] and row[5].startswith('video/') else MAX_IMAGE_BYTES)
                or row[5] not in {'image/jpeg', 'image/png','video/mp4','video/quicktime'}):
            raise TransportError(409, 'Upload changed; review again')
        return row

    def _pending_path(self, row):
        suffix = {'image/jpeg':'.jpg','image/png':'.png','video/mp4':'.mp4','video/quicktime':'.mov'}[row[5]]
        root = self.upload.incoming_root
        path = Path(row[0])
        if (not row[1] or Path(row[1]).name != row[1] or row[1] in {'.', '..'}
                or '/' in row[1] or '\\' in row[1]
                or re.fullmatch('[0-9a-f]{32}', row[2]) is None
                or re.fullmatch('[0-9a-f]{64}', row[3]) is None
                or path != root / row[1] / row[2] / (row[3] + suffix)
                or not path.is_relative_to(root) or '..' in path.parts):
            raise TransportError(409, 'Upload changed; review again')
        return path

    def list(self, token, library, page):
        with ExistingDatabase(self.database, read_only=True)() as db:
            deadline = time.monotonic() + 3
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            access = self._service(db)
            with access._transaction():
                actor = self._owner(access, token, library, operator=False)
                permitted = db.execute('SELECT 1 FROM access_operators WHERE account_id=?', (actor,)).fetchone() is not None
                result = dict(library_id=library, page=page, page_size=10, total=0,
                              can_review=permitted, items=[])
                if not permitted:
                    return result
                args = (library, access._now())
                result['total'] = db.execute('SELECT count(*)' + SOURCE + PENDING, args).fetchone()[0]
                rows = db.execute('''SELECT a.id,substr(p.display_name,1,160),u.created_at,
                    u.bytes,a.width,a.height,a.mime''' + SOURCE + PENDING +
                    ' ORDER BY u.id DESC LIMIT 10 OFFSET ?', (*args, (page-1)*10)).fetchall()
                result['items'] = [dict(id=str(r[0]), uploader=r[1] or '',
                    created_at=datetime.fromtimestamp(r[2], timezone.utc).isoformat(),
                    bytes=r[3], width=r[4], height=r[5],kind='video' if r[6].startswith('video/') else 'image',
                    preview_url=f'/admin/uploads/{r[0]}/preview?' + urlencode({'library': library})) for r in rows]
                return result

    def review(self, token, library, asset):
        with ExistingDatabase(self.database, read_only=True)() as db:
            access = self._service(db)
            with access._transaction():
                actor = self._owner(access, token, library)
                self._item(access, library, asset)
            # Planner owns its own snapshot and seals all asset and audience revisions.
            envelope = PromotionPlanner(db, clock=access.clock).promote(
                library_id=library, operator_account_id=actor, asset_ids=[asset])
            with access._transaction():
                self._owner(access, token, library)
                self._item(access, library, asset)
            expected = envelope['plan']['expected']
            return dict(asset_id=str(asset), library_id=library,
                plan=json.dumps(envelope, separators=(',', ':')),
                current_readers=expected['current_readers'],
                current_original_readers=expected['current_original_readers'])

    def approve(self, token, library, asset, raw):
        try:
            envelope = json.loads(raw)
            plan = envelope['plan']
            if (plan['operation'] != PROMOTE_OPERATION or
                    set(plan['target']) != {'library_id', 'operator_account_id', 'asset_ids'} or
                    plan['target']['library_id'] != library or plan['target']['asset_ids'] != [str(asset)]):
                raise ValueError()
        except (ValueError, TypeError, KeyError, RecursionError):
            raise TransportError(400, 'Invalid review') from None

        def authorize(access, checked):
            actor = self._owner(access, token, library)
            if actor != checked['target']['operator_account_id']:
                raise AccessDenied('Access denied')
            row = self._item(access, library, asset, allow_assigned=True)
            if row[8] == 'incoming':
                self._pending_path(row)

        review = PromotionReview(database=self.database, database_identity=_identity(self.database),
            plan_digest=plan_digest(envelope), authority_reference='web-upload-review',
            incoming_root=self.upload.incoming_root, originals_root=self.upload.original_roots[0])
        promote_and_assign(envelope, review=review, clock=self.upload.access.clock,
                           authorize=authorize, allow_replay=True)
        return dict(asset_id=str(asset), library_id=library, state='assigned')

    def preview(self, token, library, asset):
        with ExistingDatabase(self.database, read_only=True)() as db:
            access = self._service(db)
            with access._transaction():
                self._owner(access, token, library)
                row = self._item(access, library, asset)
                path = self._pending_path(row)
        if row[5].startswith('video/'):
            raise TransportError(404, 'Video preview pending preparation')
        if not isinstance(self.photo_cache, PhotoCache):
            raise TransportError(503, 'Preview unavailable')
        try:
            pin = source_pin(path, (self.upload.incoming_root,))
            if pin[2] != row[4]:
                raise TransportError(409, 'Upload changed; review again')
            raw = self.photo_cache.render(path, (self.upload.incoming_root,), pin, 'grid')
            # Decoding is outside SQLite; authorize again after the bounded worker completes.
            with ExistingDatabase(self.database, read_only=True)() as db:
                access = self._service(db)
                with access._transaction():
                    self._owner(access, token, library)
                    fresh = self._item(access, library, asset)
                    if fresh != row:
                        raise TransportError(409, 'Upload changed; review again')
                    source_pin(path, (self.upload.incoming_root,), pin)
            return raw
        except Refused as error:
            raise TransportError(error.status, 'Preview unavailable') from None


def _review_runtime(request):
    _runtime(request, allow_query=True)
    runtime = getattr(request.app.state, 'upload_review_runtime', None)
    if not isinstance(runtime, UploadReviewRuntime):
        raise TransportError(503, 'Upload review unavailable')
    return runtime


def _call(runtime, action, *args):
    try:
        return getattr(runtime, action)(*args)
    except PlanRejected:
        raise TransportError(409, 'Upload or audience changed; review again') from None


@router.get('/admin/upload-auto-approval')
async def upload_auto_policies(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    result = await run_in_threadpool(_call, _review_runtime(request), 'policies', token,
                                     query['library'])
    return JSONResponse(result)


@router.put('/admin/upload-auto-approval/{member_id}')
async def set_upload_auto_policy(member_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'mode'})
    result = await run_in_threadpool(_call, _review_runtime(request), 'set_policy', token,
                                     query['library'], member_id, body['mode'])
    return JSONResponse(result)


@router.get('/admin/uploads')
async def upload_inbox(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page'})
    result = await run_in_threadpool(_call, _review_runtime(request), 'list', token,
        query['library'], _integer(query.get('page', '1'), 100000))
    return JSONResponse(result)


@router.get('/admin/uploads/{asset_id}/preview')
async def upload_preview(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    raw = await run_in_threadpool(_call, _review_runtime(request), 'preview', token,
        query['library'], _integer(asset_id, 2**63-1))
    return Response(raw, media_type='image/jpeg')


@router.post('/admin/uploads/{asset_id}/review')
async def review_upload(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    await _body(request, set())
    result = await run_in_threadpool(_call, _review_runtime(request), 'review', token,
        query['library'], _integer(asset_id, 2**63-1))
    return JSONResponse(result)


@router.post('/admin/uploads/{asset_id}/approve')
async def approve_upload(asset_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library'})
    body = await _body(request, {'plan'})
    result = await run_in_threadpool(_call, _review_runtime(request), 'approve', token,
        query['library'], _integer(asset_id, 2**63-1), body['plan'])
    return JSONResponse(result)

"""Read-only processing evidence for the current account's own upload receipts."""
import json
import sqlite3

from .service import AccessDenied, AccessService
from .transport import TransportError
from .resumable import MAX_IMAGE_BYTES, MAX_VIDEO_BYTES


PAGE_SIZE = 10
MAX_PAGE = 100000
_STATES = {'awaiting_review', 'pending', 'running', 'finished', 'failed', 'dead'}
_TASK_TYPES = ('thumb', 'embed', 'face', 'caption', 'video_probe', 'video_embed')
_PLAYBACK_TASK_WINDOW = 512


def _stage(value):
    return value if type(value) is str and value in _STATES else 'unknown'


def _task_evidence(rows, asset_ids):
    """Resolve the highest-id task of each supported type for these page assets."""
    latest = {}
    for task_id, task_type, payload_raw, task_state, asset_id in rows:
        if type(task_id) is not int:
            continue
        try:
            payload = json.loads(payload_raw) if type(payload_raw) is str else None
        except (ValueError, TypeError, RecursionError):
            payload = None
        if type(asset_id) is not int or asset_id not in asset_ids:
            continue
        if type(payload) is not dict or type(payload.get('asset_id')) is not int or payload['asset_id'] != asset_id:
            payload = None
        # The SQL query is already ordered by descending task id. Keep the first row
        # even when its payload schema is malformed: older success must not mask it.
        key = (asset_id, task_type)
        if key not in latest:
            latest[key] = (payload, _stage(task_state))
    return latest


def _task_state(latest, asset_id, task_type, *, required_payload=None):
    value = latest.get((asset_id, task_type))
    if value is None:
        return 'unknown'
    payload, state = value
    if payload is None:
        return 'unknown'
    if required_payload is not None and set(payload) != required_payload:
        return 'unknown'
    return state


def approved_video_probe_state(access, token, library, asset_id):
    """Return pending/running only for the caller's currently assigned video.

    This is a playback-status hint, not task data or an authorization grant.
    Unknown, unavailable, finished or failed preparation never claims that work
    is still in progress.
    """
    if type(asset_id) is not int or not 1 <= asset_id <= 2**63-1:
        return None
    try:
        with access.connection_factory() as connection:
            service = AccessService(connection, clock=access.clock)
            with service._transaction():
                member = service._require(token, library, 'library.read')
                account = member['account_id']
                if not service._may_submit(account):
                    return None
                receipt = connection.execute('''SELECT u.state,a.status,a.mime,scope.library_id
                    FROM access_uploads u JOIN assets a ON a.id=u.asset_id
                    JOIN access_asset_libraries scope ON scope.asset_id=a.id AND scope.library_id=?
                    WHERE u.account_id=? AND u.asset_id=? ORDER BY u.id DESC LIMIT 1''',
                    (library, account, asset_id)).fetchone()
                if (receipt is None or receipt[0] != 'assigned' or receipt[1] not in (None, 'active')
                        or receipt[2] not in {'video/mp4', 'video/quicktime'} or receipt[3] != library):
                    return None
                # A playback hint must not scan the processing history.
                rows = connection.execute('''WITH recent AS (
                        SELECT id,type,state,CASE WHEN length(CAST(payload_json AS BLOB))<=512
                                                 THEN payload_json END AS payload_json
                        FROM tasks ORDER BY id DESC LIMIT ?)
                    SELECT id,type,payload_json,state,
                        CASE WHEN json_valid(payload_json)
                             THEN json_extract(payload_json,'$.asset_id') END AS asset_id
                    FROM recent WHERE type='video_probe'
                        AND CASE WHEN json_valid(payload_json)
                                 THEN json_extract(payload_json,'$.asset_id') END=?
                    ORDER BY id DESC LIMIT 1''', (_PLAYBACK_TASK_WINDOW, asset_id)).fetchall()
                latest = _task_evidence(rows, {asset_id})
                state = _task_state(latest, asset_id, 'video_probe', required_payload={'asset_id'})
                return state if state in {'pending', 'running'} else None
    except sqlite3.OperationalError as error:
        # Older/minimal read-only application schemas may not have the optional
        # upload journal yet. Its absence proves no pending state and retains the
        # existing not-prepared response; other storage errors remain failures.
        message = str(error).lower()
        if any(f'no such table: {table}' in message for table in ('access_uploads', 'tasks')):
            return None
        raise


class UploadPreparation:
    """Bounded snapshot of server-owned receipt and processing metadata."""

    def __init__(self, upload):
        self.upload = upload

    def page(self, token, *, page=1):
        if type(page) is not int or not 1 <= page <= MAX_PAGE:
            raise ValueError('Invalid page')

        access = self.upload.access
        with access.connection_factory() as connection:
            service = AccessService(connection, clock=access.clock)
            with service._transaction():
                account = service._session(token)['account_id']
                if not service._may_submit(account):
                    raise AccessDenied('Access denied')
                total = connection.execute(
                    'SELECT count(*) FROM access_uploads WHERE account_id=?', (account,)
                ).fetchone()[0]
                if type(total) is not int or not 0 <= total <= 2147483647:
                    raise TransportError(503, 'Upload preparation unavailable')
                rows = connection.execute('''SELECT u.asset_id,u.created_at,u.bytes,u.state,
                    a.status,a.mime,scope.library_id,
                    EXISTS(SELECT 1 FROM embeddings e WHERE e.asset_id=a.id AND e.modality='image'),
                    EXISTS(SELECT 1 FROM captions c WHERE c.asset_id=a.id AND c.superseded=0),
                    EXISTS(SELECT 1 FROM face_detections f WHERE f.asset_id=a.id)
                    FROM access_uploads u JOIN assets a ON a.id=u.asset_id
                    LEFT JOIN access_asset_libraries scope ON scope.asset_id=a.id
                    WHERE u.account_id=? ORDER BY u.id DESC LIMIT ? OFFSET ?''',
                    (account, PAGE_SIZE, (page - 1) * PAGE_SIZE)).fetchall()

                items = []
                available_ids = []
                for asset, created, size, receipt, status, mime, mapped, vector, caption, faces in rows:
                    if (type(asset) is not int or not 1 <= asset <= 2**63-1
                            or type(created) is not int or not 0 <= created <= 253402300799
                            or type(size) is not int or not 1 <= size <= (MAX_VIDEO_BYTES if mime and mime.startswith('video/') else MAX_IMAGE_BYTES)
                            or mime not in {'image/jpeg', 'image/png', 'video/mp4', 'video/quicktime'}):
                        raise TransportError(503, 'Upload preparation unavailable')
                    state, library = 'unavailable', None
                    if status in (None, 'active'):
                        if receipt == 'incoming' and mapped is None:
                            state = 'awaiting_review'
                        elif receipt == 'assigned' and mapped is not None:
                            try:
                                service._require(token, mapped, 'library.read')
                                state, library = 'available', mapped
                                available_ids.append(asset)
                            except AccessDenied:
                                pass
                    item = dict(asset_id=str(asset), created_at=created, bytes=size,
                                kind='video' if mime.startswith('video/') else 'image',
                                state=state, library_id=library, processing=None)
                    if state == 'available':
                        kind = item['kind']
                        stages = dict(
                            preview='unknown',
                            index='unknown',
                            faces='not_applicable' if kind == 'video' else 'unknown',
                            caption='unknown',
                            video_probe='not_applicable' if kind == 'image' else 'unknown',
                        )
                        item['processing'] = {'stages': stages,
                            'records': {'image_vector': bool(vector), 'caption': bool(caption),
                                        'face_detections': bool(faces)},
                            'availability': {'preview': 'unknown',
                                'playback': 'unknown' if kind == 'video' else 'not_applicable'}}
                    items.append(item)

                latest = {}
                if available_ids:
                    marks = ','.join('?' for _ in available_ids)
                    query = f'''WITH matched AS (
                        SELECT id,type,payload_json,state,
                          CASE WHEN json_valid(payload_json)
                               THEN json_extract(payload_json,'$.asset_id') END AS asset_id
                        FROM tasks
                        WHERE type IN ({','.join('?' for _ in _TASK_TYPES)})
                          AND CASE WHEN json_valid(payload_json)
                                   THEN json_extract(payload_json,'$.asset_id') END IN ({marks})
                    ), ranked AS (
                        SELECT id,type,payload_json,state,asset_id,
                          row_number() OVER (PARTITION BY asset_id,type ORDER BY id DESC) AS rank
                        FROM matched
                    )
                    SELECT id,type,payload_json,state,asset_id FROM ranked
                    WHERE rank=1 ORDER BY id DESC'''
                    task_rows = connection.execute(query, _TASK_TYPES + tuple(available_ids)).fetchall()
                    latest = _task_evidence(task_rows, set(available_ids))

                for item in items:
                    if item['processing'] is None:
                        continue
                    aid = int(item['asset_id'])
                    stages = item['processing']['stages']
                    if item['kind'] == 'image':
                        stages['preview'] = _task_state(latest, aid, 'thumb', required_payload={'asset_id'})
                        stages['index'] = _task_state(latest, aid, 'embed', required_payload={'asset_id', 'modality'})
                        # The upload contract's image embed task is specifically modality=image.
                        entry = latest.get((aid, 'embed'))
                        if entry is not None and entry[0] is not None and entry[0].get('modality') != 'image':
                            stages['index'] = 'unknown'
                        stages['faces'] = _task_state(latest, aid, 'face', required_payload={'asset_id'})
                        stages['caption'] = _task_state(latest, aid, 'caption', required_payload={'asset_id'})
                    else:
                        # The video pipeline has its own asset-scoped embedding job;
                        # it is distinct from image `embed` and says nothing about playback.
                        stages['index'] = _task_state(latest, aid, 'video_embed', required_payload={'asset_id'})
                        stages['video_probe'] = _task_state(latest, aid, 'video_probe', required_payload={'asset_id'})
                        # Video workers schedule one asset-scoped caption job after
                        # keyframe extraction; this reports only that task lifecycle.
                        stages['caption'] = _task_state(latest, aid, 'caption', required_payload={'asset_id'})

                return dict(version=1, page=page, page_size=PAGE_SIZE, total=total, items=items)

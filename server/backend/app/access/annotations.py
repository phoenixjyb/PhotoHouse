"""Private, immutable upload descriptions and recorded family voice notes.

The original words or bounded WAV bytes live in SQLite. Pending items are readable
only by their uploader or a current owner/operator reviewer. Assigned items follow
the selected library's current membership. No model or legacy voice service is
called by this intake route.
"""
import hashlib
import io
import json
import re
import struct
import uuid
import wave
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool

from .library import LibraryRoute, _integer, _query
from .promotion import _operator
from .provisioning import PlanRejected
from .service import AccessDenied, AccessService
from .transport import TransportError, _body, _runtime, _single, credentials_from_request

router = APIRouter(route_class=LibraryRoute)
BATCH = re.compile('[0-9a-f]{32}')
TEXT_BYTES = 16 * 1024
AUDIO_BYTES = 2 * 1024 * 1024
PAGE_SIZE = 20
REVIEW_PAGE_SIZE = 10
MAX_BATCH_NOTES = 500
MAX_BATCH_AUDIO_BYTES = 128 * 1024 * 1024
LANGUAGES = {'en', 'zh', 'mixed', 'und'}


def _uuid(value):
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise TransportError(400, 'Invalid identifier') from None
    return value


def _target(batch, asset_id, language, consent):
    if not isinstance(batch, str) or BATCH.fullmatch(batch) is None:
        raise TransportError(400, 'Invalid batch')
    if not isinstance(asset_id, str) or (asset_id and
            (len(asset_id) > 19 or not asset_id.isascii() or not asset_id.isdecimal() or asset_id.startswith('0')
             or int(asset_id) > 2**63-1)):
        raise TransportError(400, 'Invalid asset')
    if language not in LANGUAGES or consent not in {'yes', 'no'}:
        raise TransportError(400, 'Invalid annotation options')
    return int(asset_id) if asset_id else None


def _wav(data):
    if (not isinstance(data, bytes) or not 44 <= len(data) <= AUDIO_BYTES
            or data[:4] != b'RIFF' or data[8:12] != b'WAVE'
            or struct.unpack_from('<I', data, 4)[0] + 8 != len(data)):
        raise TransportError(422, 'Unsupported recording')
    try:
        with wave.open(io.BytesIO(data), 'rb') as recording:
            frames = recording.getnframes()
            rate = recording.getframerate()
            if (recording.getcomptype() != 'NONE' or recording.getnchannels() != 1
                    or recording.getsampwidth() != 2 or rate not in {16000, 48000}
                    or not rate // 2 <= frames <= rate * 60
                    or len(recording.readframes(frames)) != frames * 2):
                raise TransportError(422, 'Unsupported recording')
    except (EOFError, OSError, ValueError, wave.Error, struct.error):
        raise TransportError(422, 'Unsupported recording') from None
    return frames * 1000 // rate


class Annotations:
    def __init__(self, access):
        self.access = access
        self.db = access.db

    def _upload(self, token, library, asset):
        session = self.access._session(token)
        upload = self.access._one('''SELECT u.account_id,u.batch,u.destination_library_id,
            u.state,m.library_id AS assigned_library FROM access_uploads u
            LEFT JOIN access_asset_libraries m ON m.asset_id=u.asset_id
            WHERE u.asset_id=?''', (asset,))
        if upload is None or upload['destination_library_id'] != library:
            raise AccessDenied('Access denied')
        if upload['state'] == 'assigned' and upload['assigned_library'] == library:
            self.access._member(token, library)
        elif upload['state'] == 'incoming' and upload['assigned_library'] is None:
            self.access._member(token, library)
            if session['account_id'] != upload['account_id']:
                member = self.access._member(token, library, owner=True)
                try:
                    _operator(self.db, member['account_id'], library, self.access._now())
                except PlanRejected:
                    raise AccessDenied('Access denied') from None
                uploader = self.access._one('''SELECT 1 FROM access_memberships m
                    JOIN access_accounts a ON a.id=m.account_id
                    WHERE m.account_id=? AND m.library_id=? AND m.status='approved'
                    AND a.state='active' AND (m.expires_at IS NULL OR m.expires_at>?)''',
                    (upload['account_id'], library, self.access._now()))
                if uploader is None:
                    raise AccessDenied('Access denied')
        else:
            raise AccessDenied('Access denied')
        return upload

    def _write_target(self, token, library, batch, asset):
        member = self.access._member(token, library)
        account = member['account_id']
        if asset is None:
            row = self.access._one('''SELECT 1 FROM access_uploads u
                LEFT JOIN access_asset_libraries m ON m.asset_id=u.asset_id
                WHERE u.account_id=? AND u.destination_library_id=? AND u.batch=?
                AND ((u.state='incoming' AND m.library_id IS NULL)
                OR (u.state='assigned' AND m.library_id=?)) LIMIT 1''',
                (account, library, batch, library))
        else:
            upload = self._upload(token, library, asset)
            row = upload if upload['account_id'] == account and upload['batch'] == batch else None
        if row is None:
            raise AccessDenied('Access denied')
        return account

    def _present(self, row, library, selected_asset):
        derived = self.access._one('''SELECT revision,state,transcript,polished_text,
            provider,model,error_code FROM access_annotation_derivations
            WHERE annotation_id=? ORDER BY revision DESC LIMIT 1''', (row['id'],))
        tags = self.db.execute('''SELECT tag,status,revision FROM access_annotation_tag_proposals
            WHERE annotation_id=? AND revision=? ORDER BY tag LIMIT 30''',
            (row['id'], derived['revision'] if derived is not None else 0)).fetchall()
        return {'id': row['id'], 'scope': 'folder' if row['asset_id'] is None else 'item',
            'asset_id': str(row['asset_id']) if row['asset_id'] is not None else None,
            'batch': row['batch'], 'library_id': library, 'author_id': row['author_id'],
            'kind': row['kind'], 'original_text': row['original_text'],
            'audio_url': ('/upload-annotations/' + row['id'] + '/audio?' + urlencode(
                {'library': library, 'asset_id': str(selected_asset)})) if row['kind'] == 'audio' else None,
            'mime': row['mime'], 'duration_ms': row['duration_ms'], 'sha256': row['sha256'],
            'language': row['language'],
            'local_processing_consent': 'yes' if row['consent'] else 'no',
            'created_at': row['created_at'],
            'derivation': dict(derived) if derived is not None else None,
            'tags': [{'tag': tag, 'status': status, 'revision': revision}
                     for tag, status, revision in tags]}

    def create(self, token, library, batch, asset, language, consent, mutation,
               *, text=None, audio=None, duration_ms=None):
        _uuid(mutation)
        kind = 'text' if text is not None else 'audio'
        original = text.encode('utf-8') if text is not None else audio
        digest = hashlib.sha256(original).hexdigest()
        request_digest = hashlib.sha256(json.dumps(
            [library, batch, asset, language, consent, kind, digest],
            separators=(',', ':')).encode()).hexdigest()
        with self.access._transaction(write=True):
            author = self._write_target(token, library, batch, asset)
            old = self.access._one('''SELECT * FROM access_upload_annotations
                WHERE author_id=? AND mutation_id=?''', (author, mutation))
            if old:
                if old['request_digest'] != request_digest:
                    raise TransportError(409, 'Annotation request changed')
                return self._present(old, library, asset or self._first_asset(author, library, batch))
            count, used = self.db.execute('''SELECT count(*),coalesce(sum(length(original_audio)),0)
                FROM access_upload_annotations WHERE author_id=? AND library_id=? AND batch=?''',
                (author, library, batch)).fetchone()
            if count >= MAX_BATCH_NOTES or used + (len(audio) if audio else 0) > MAX_BATCH_AUDIO_BYTES:
                raise TransportError(413, 'Annotation storage limit reached')
            identifier = str(uuid.uuid4())
            now = self.access._now()
            self.db.execute('''INSERT INTO access_upload_annotations
                (id,author_id,library_id,batch,asset_id,kind,original_text,original_audio,
                 mime,duration_ms,sha256,language,consent,mutation_id,request_digest,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (identifier, author, library, batch, asset, kind, text, audio,
                 'audio/wav' if audio is not None else None, duration_ms, digest, language,
                 int(consent == 'yes'), mutation, request_digest, now))
            self.db.execute('''INSERT INTO access_annotation_derivations
                (annotation_id,revision,state,created_at,updated_at)
                VALUES (?,1,?,?,?)''', (identifier, 'waiting' if consent == 'yes' else 'held', now, now))
            self.access._audit(author, 'annotation.create_' + kind, library)
            return self._present(self.access._one(
                'SELECT * FROM access_upload_annotations WHERE id=?', (identifier,)),
                library, asset or self._first_asset(author, library, batch))

    def _first_asset(self, author, library, batch):
        row = self.db.execute('''SELECT asset_id FROM access_uploads WHERE account_id=?
            AND destination_library_id=? AND batch=? ORDER BY asset_id LIMIT 1''',
            (author, library, batch)).fetchone()
        if row is None:
            raise AccessDenied('Access denied')
        return row[0]

    def list(self, token, library, asset, page):
        with self.access._transaction():
            upload = self._upload(token, library, asset)
            args = (upload['account_id'], library, upload['batch'], asset)
            summary = {state: 0 for state in
                ('held', 'waiting', 'running', 'completed', 'failed', 'dead')}
            for state, count in self.db.execute('''SELECT d.state,count(*)
                FROM access_upload_annotations a
                JOIN access_annotation_derivations d ON d.annotation_id=a.id
                    AND d.revision=(SELECT max(revision) FROM access_annotation_derivations
                        WHERE annotation_id=a.id)
                WHERE a.author_id=? AND a.library_id=? AND a.batch=?
                    AND (a.asset_id IS NULL OR a.asset_id=?)
                GROUP BY d.state''', args):
                summary[state] = count
            total = sum(summary.values())
            cursor = self.db.execute('''SELECT * FROM access_upload_annotations
                WHERE author_id=? AND library_id=? AND batch=?
                AND (asset_id IS NULL OR asset_id=?)
                ORDER BY created_at,id LIMIT ? OFFSET ?''',
                (*args, PAGE_SIZE, (page-1)*PAGE_SIZE))
            names = [column[0] for column in cursor.description]
            rows = [dict(zip(names, row)) for row in cursor]
            return {'library_id': library, 'asset_id': str(asset), 'batch': upload['batch'], 'page': page,
                'page_size': PAGE_SIZE, 'total': total, 'processing_summary': summary,
                'items': [self._present(row, library, asset) for row in rows]}

    def original_audio(self, token, library, asset, identifier):
        with self.access._transaction():
            upload = self._upload(token, library, asset)
            note = self.access._one('''SELECT original_audio FROM access_upload_annotations
                WHERE id=? AND author_id=? AND library_id=? AND batch=?
                AND (asset_id IS NULL OR asset_id=?) AND kind='audio' ''',
                (identifier, upload['account_id'], library, upload['batch'], asset))
            if note is None:
                raise AccessDenied('Access denied')
            return note['original_audio']

    def delete_original(self, token, library, asset, identifier, digest):
        """Owner erases one original and its derived rows from the active database."""
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise TransportError(400, 'Invalid annotation digest')
        # SQLite must overwrite freed cells, including the original audio BLOB.
        if self.db.execute('PRAGMA secure_delete=ON').fetchone()[0] != 1:
            raise TransportError(503, 'Annotation deletion unavailable')
        with self.access._transaction(write=True):
            owner = self.access._member(token, library, owner=True)
            upload = self._upload(token, library, asset)
            note = self.access._one('''SELECT * FROM access_upload_annotations
                WHERE id=? AND author_id=? AND library_id=? AND batch=?
                AND (asset_id IS NULL OR asset_id=?)''',
                (identifier, upload['account_id'], library, upload['batch'], asset))
            if note is None:
                raise AccessDenied('Access denied')
            if note['sha256'] != digest:
                raise TransportError(409, 'Annotation changed; refresh')
            running = self.db.execute('''SELECT 1 FROM access_annotation_derivations
                WHERE annotation_id=? AND state='running' LIMIT 1''', (identifier,)).fetchone()
            if running:
                raise TransportError(409, 'Annotation is processing; try again later')
            if self.access.original_deletions is not None:
                try:
                    self.access.original_deletions.append(self.db, 'upload', note, self.access._now())
                except RuntimeError:
                    raise TransportError(503, 'Annotation deletion unavailable') from None
            self.db.execute('DELETE FROM access_annotation_tag_proposals WHERE annotation_id=?',
                            (identifier,))
            self.db.execute('DELETE FROM access_annotation_derivations WHERE annotation_id=?',
                            (identifier,))
            self.db.execute('DELETE FROM access_upload_annotations WHERE id=?', (identifier,))
            self.access._audit(owner['account_id'], 'annotation.delete', library)
            return {'annotation_id': identifier, 'deleted': True}

    def review_tag(self, token, library, asset, identifier, revision, tag, decision):
        """Owner decision for one current local proposal; never edit authored text."""
        with self.access._transaction(write=True):
            owner = self.access._member(token, library, owner=True)
            upload = self._upload(token, library, asset)
            note = self.access._one('''SELECT a.id,a.author_id,a.batch,a.asset_id,d.revision,d.state
                FROM access_upload_annotations a JOIN access_annotation_derivations d
                ON d.annotation_id=a.id AND d.revision=(SELECT max(revision)
                    FROM access_annotation_derivations WHERE annotation_id=a.id)
                WHERE a.id=? AND a.library_id=?''', (identifier, library))
            if (note is None or note['author_id'] != upload['account_id']
                    or note['batch'] != upload['batch']
                    or note['asset_id'] not in (None, asset)):
                raise AccessDenied('Access denied')
            if note['revision'] != revision or note['state'] != 'completed':
                raise TransportError(409, 'Tag proposal changed; refresh')
            proposal = self.access._one('''SELECT status FROM access_annotation_tag_proposals
                WHERE annotation_id=? AND revision=? AND tag=?''', (identifier, revision, tag))
            if proposal is None:
                raise AccessDenied('Access denied')
            if proposal['status'] == decision:
                return {'annotation_id': identifier, 'revision': revision,
                        'tag': tag, 'status': decision}
            if proposal['status'] != 'proposed':
                raise TransportError(409, 'Tag decision changed; refresh')
            changed = self.db.execute('''UPDATE access_annotation_tag_proposals SET status=?
                WHERE annotation_id=? AND revision=? AND tag=? AND status='proposed' ''',
                (decision, identifier, revision, tag)).rowcount
            if changed != 1:
                raise TransportError(409, 'Tag decision changed; refresh')
            self.access._audit(owner['account_id'], 'annotation.tag_' + decision, library)
            return {'annotation_id': identifier, 'revision': revision,
                    'tag': tag, 'status': decision}

    def proposed_tags(self, token, library, page):
        """Owner inbox of current proposals on assigned, active library assets."""
        with self.access._transaction():
            self.access._member(token, library, owner=True)
            sql = '''WITH eligible AS (
                SELECT n.id AS annotation_id,n.batch,n.asset_id AS note_asset_id,
                    n.kind,n.original_text,n.created_at,d.transcript,d.polished_text,
                    p.revision,p.tag,min(u.asset_id) AS selected_asset
                FROM access_annotation_tag_proposals p
                JOIN access_upload_annotations n ON n.id=p.annotation_id
                JOIN access_annotation_derivations d ON d.annotation_id=n.id
                    AND d.revision=p.revision
                JOIN access_uploads u ON u.account_id=n.author_id AND u.batch=n.batch
                    AND u.destination_library_id=n.library_id AND u.state='assigned'
                    AND (n.asset_id IS NULL OR n.asset_id=u.asset_id)
                JOIN assets a ON a.id=u.asset_id
                JOIN access_asset_libraries m ON m.asset_id=a.id AND m.library_id=n.library_id
                WHERE n.library_id=:library AND p.status='proposed' AND d.state='completed'
                    AND (a.status IS NULL OR a.status='active')
                    AND d.revision=(SELECT max(revision) FROM access_annotation_derivations
                        WHERE annotation_id=n.id)
                GROUP BY n.id,p.revision,p.tag
            ) '''
            params = {'library': library, 'limit': REVIEW_PAGE_SIZE,
                      'offset': (page - 1) * REVIEW_PAGE_SIZE}
            total = self.db.execute(sql + 'SELECT count(*) FROM eligible', params).fetchone()[0]
            rows = self.db.execute(sql + '''SELECT annotation_id,batch,note_asset_id,kind,
                original_text,created_at,transcript,polished_text,revision,tag,selected_asset
                FROM eligible ORDER BY created_at DESC,annotation_id,tag LIMIT :limit OFFSET :offset''',
                params).fetchall()
            items = []
            for row in rows:
                identifier, batch, note_asset, kind, original, created, transcript, polished, revision, tag, selected = row
                items.append({'annotation_id': identifier, 'batch': batch,
                    'asset_id': str(selected), 'scope': 'folder' if note_asset is None else 'item',
                    'kind': kind, 'original_text': original, 'created_at': created,
                    'transcript': transcript, 'polished_text': polished, 'revision': revision,
                    'tag': tag, 'audio_url': ('/upload-annotations/' + identifier + '/audio?' + urlencode(
                        {'library': library, 'asset_id': str(selected)})) if kind == 'audio' else None})
            return {'library_id': library, 'page': page, 'page_size': REVIEW_PAGE_SIZE,
                    'total': total, 'items': items}


def _call(runtime, method, *args, **kwargs):
    with runtime.connection_factory() as db:
        return getattr(Annotations(AccessService(db, clock=runtime.clock)), method)(*args, **kwargs)


def _require_intake(request):
    if request.app.state.annotation_intake_enabled is not True:
        raise TransportError(503, 'Family description intake unavailable')


@router.post('/upload-annotations/text')
async def create_text_annotation(request: Request):
    _require_intake(request)
    token, _ = credentials_from_request(request, allow_query=True)
    library = _query(request, {'library'})['library']
    body = await _body(request, {'batch', 'asset_id', 'language', 'consent', 'mutation_id', 'text'},
                       max_body=TEXT_BYTES * 6 + 2048)
    asset = _target(body['batch'], body['asset_id'], body['language'], body['consent'])
    value = body['text']
    if not value.strip() or '\x00' in value or len(value.encode('utf-8')) > TEXT_BYTES:
        raise TransportError(422, 'Invalid description')
    result = await run_in_threadpool(_call, _runtime(request, allow_query=True), 'create',
        token, library, body['batch'], asset, body['language'], body['consent'],
        body['mutation_id'], text=value)
    return JSONResponse(result, status_code=201)


@router.post('/upload-annotations/audio')
async def create_audio_annotation(request: Request):
    _require_intake(request)
    token, _ = credentials_from_request(request, allow_query=True)
    library = _query(request, {'library'})['library']
    if _single(request, 'content-encoding') is not None or (
            (_single(request, 'content-type') or '').split(';')[0].strip().lower()
            not in {'audio/wav', 'audio/x-wav'}):
        raise TransportError(400, 'Invalid recording request')
    batch, raw_asset = _single(request, 'x-annotation-batch'), _single(request, 'x-annotation-asset-id')
    language, consent = _single(request, 'x-annotation-language'), _single(request, 'x-local-processing-consent')
    mutation = _single(request, 'x-annotation-mutation-id')
    asset = _target(batch, raw_asset if raw_asset is not None else '', language, consent)
    _uuid(mutation)
    length = _single(request, 'content-length')
    if length is not None and (not length.isascii() or not length.isdecimal()
            or int(length) > AUDIO_BYTES):
        raise TransportError(413, 'Recording too large')
    chunks = bytearray()
    async for part in request.stream():
        if len(chunks) + len(part) > AUDIO_BYTES:
            raise TransportError(413, 'Recording too large')
        chunks.extend(part)
    audio = bytes(chunks)
    duration_ms = _wav(audio)
    result = await run_in_threadpool(_call, _runtime(request, allow_query=True), 'create',
        token, library, batch, asset, language, consent, mutation,
        audio=audio, duration_ms=duration_ms)
    return JSONResponse(result, status_code=201)


@router.get('/upload-annotations')
async def list_upload_annotations(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'asset_id', 'page'})
    asset = _integer(query['asset_id'], 2**63-1)
    page = _integer(query.get('page', '1'), 100000)
    result = await run_in_threadpool(_call, _runtime(request, allow_query=True), 'list',
                                     token, query['library'], asset, page)
    result['intake_enabled'] = request.app.state.annotation_intake_enabled is True
    return JSONResponse(result)


@router.get('/upload-annotations/{annotation_id}/audio')
async def read_original_audio(annotation_id: str, request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'asset_id'})
    audio = await run_in_threadpool(_call, _runtime(request, allow_query=True),
        'original_audio', token, query['library'], _integer(query['asset_id'], 2**63-1),
        _uuid(annotation_id))
    return Response(audio, media_type='audio/wav')


@router.post('/admin/upload-annotations/delete')
async def delete_upload_annotation(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    library = _query(request, {'library'})['library']
    body = await _body(request, {'asset_id', 'annotation_id', 'sha256'})
    result = await run_in_threadpool(_call, _runtime(request, allow_query=True), 'delete_original',
        token, library, _integer(body['asset_id'], 2**63-1), _uuid(body['annotation_id']),
        body['sha256'])
    return JSONResponse(result)


@router.post('/admin/upload-annotation-tags/review')
async def review_annotation_tag(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    library = _query(request, {'library'})['library']
    body = await _body(request, {'asset_id', 'annotation_id', 'revision', 'tag', 'decision'},
                       max_body=2048)
    asset = _integer(body['asset_id'], 2**63-1)
    identifier = _uuid(body['annotation_id'])
    revision = _integer(body['revision'], 2**31-1)
    tag = body['tag']
    if (not tag.strip() or len(tag) > 128 or len(tag.encode('utf-8')) > 512
            or any(ord(character) < 32 or ord(character) == 127 for character in tag)
            or body['decision'] not in {'accepted', 'rejected'}):
        raise TransportError(400, 'Invalid tag review')
    result = await run_in_threadpool(_call, _runtime(request, allow_query=True), 'review_tag',
        token, library, asset, identifier, revision, tag, body['decision'])
    return JSONResponse(result)


@router.get('/admin/upload-annotation-tags')
async def list_proposed_annotation_tags(request: Request):
    token, _ = credentials_from_request(request, allow_query=True)
    query = _query(request, {'library', 'page'})
    result = await run_in_threadpool(_call, _runtime(request, allow_query=True), 'proposed_tags',
        token, query['library'], _integer(query.get('page', '1'), 100000))
    return JSONResponse(result)

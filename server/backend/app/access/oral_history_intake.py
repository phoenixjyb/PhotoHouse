"""Internal, opt-in local recording-section intake; no routes or provider work.

Accepted source bytes and exact mutation receipts commit together. This foundation
is private to its author, even from library owners. It cannot publish, transcribe,
delete, restore or activate a production oral-history feature.
"""
from __future__ import annotations

import hashlib
import json
import struct
import unicodedata
import uuid

from .oral_history_schema import (SESSION, SECTION, MUTATION, MAX_SECTIONS,
    MAX_SECTION_FRAMES, MAX_SECTION_BYTES, MAX_TOTAL_BYTES, MAX_TOTAL_FRAMES,
    MAX_SESSIONS_PER_AUTHOR, assert_schema)
from .service import AccessDenied
from .original_deletions import OriginalDeletionError
from .transport import TransportError

LANGUAGES = {'zh', 'en', 'mixed', 'und'}
CREATE_FIELDS = {'request_id', 'title', 'subject_label', 'narrator_label',
                 'language', 'processing_consent'}
STATUS_FIELDS = {'version', 'session_id', 'library_id', 'author_id', 'title',
                 'subject_label', 'narrator_label', 'language', 'processing_consent',
                 'state', 'revision', 'section_count', 'next_ordinal', 'total_bytes',
                 'total_frames', 'duration_ms', 'manifest_sha256'}


def _uuid(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError):
        raise TransportError(400, 'Invalid recording identifier') from None
    return value


def _integer(value, maximum, *, minimum=0):
    if type(value) is not int or not minimum <= value <= maximum:
        raise TransportError(400, 'Invalid recording sequence')
    return value


def _text(value, budget, *, required=False):
    if type(value) is not str:
        raise TransportError(422, 'Invalid recording description')
    try:
        if (len(value.encode('utf-8', 'strict')) > budget
                or any(unicodedata.category(c) == 'Cc' and c not in '\n\t' for c in value)
                or (required and not value.strip())):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise TransportError(422, 'Invalid recording description') from None
    return value


def _json(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode('ascii')).hexdigest()


def wav_frames(audio):
    """Canonical client PCM WAV, mono 16-bit/16kHz, at most 20s; pauses and endings may produce shorter sections."""
    if type(audio) is not bytes or not 46 <= len(audio) <= MAX_SECTION_BYTES:
        raise TransportError(422, 'Unsupported recording section')
    count = len(audio) - 44
    if count % 2 or not 1 <= count // 2 <= MAX_SECTION_FRAMES:
        raise TransportError(422, 'Unsupported recording section')
    header = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', count + 36, b'WAVE',
                         b'fmt ', 16, 1, 1, 16000, 32000, 2, 16, b'data', count)
    if audio[:44] != header:
        raise TransportError(422, 'Unsupported recording section')
    return count // 2


def _seed(row):
    return _digest({'version': 1, 'id': row['id'], 'library': row['library_id'],
                    'author': row['author_id'], 'title': row['title'],
                    'subject': row['subject_label'], 'narrator': row['narrator_label'],
                    'language': row['language'], 'consent': bool(row['processing_consent'])})


def _next(head, ordinal, start, frames, size, source):
    return _digest({'version': 1, 'parent': head, 'ordinal': ordinal, 'start_frame': start,
                    'frames': frames, 'byte_count': size, 'sha256': source})


def _one(db, sql, args):
    cursor=db.execute(sql,args)
    row=cursor.fetchone()
    return dict(zip((c[0] for c in cursor.description),row)) if row is not None else None


def session_snapshot(db, actor, library, ident, *, allow_withdrawn=False):
    """Internal bounded metadata verifier; caller owns its authorization/transaction."""
    row = _one(db, f'SELECT * FROM {SESSION} WHERE id=? AND library_id=? AND author_id=?',
                           (ident, library, actor))
    if row is None:
        raise AccessDenied('Access denied')
    if row['state']=='withdrawn' and not allow_withdrawn:
        raise AccessDenied('Access denied')
    try:
        _text(row['title'],512,required=True)
        _text(row['subject_label'],512)
        _text(row['narrator_label'],256)
        if (row['language'] not in LANGUAGES or row['processing_consent'] not in (0,1)
                or row['state'] not in {'open','completed','cancelled','withdrawn'}):
            raise ValueError()
        for key, maximum in (('revision',MAX_SECTIONS+3),('section_count',MAX_SECTIONS),
                             ('total_bytes',MAX_TOTAL_BYTES),('total_frames',MAX_TOTAL_FRAMES)):
            _integer(row[key],maximum)
    except (ValueError, TypeError, TransportError):
        raise TransportError(503, 'Recording storage unavailable') from None
    logical_state=row['withdrawn_from'] if row['state']=='withdrawn' else row['state']
    if logical_state not in {'open','completed','cancelled'}:
        raise TransportError(503, 'Recording storage unavailable')
    # Verify a bounded source manifest/counters; raw audio is verified separately on read.
    parts = db.execute(f'''SELECT ordinal,start_frame,frames,byte_count,sha256,
        parent_manifest,manifest_sha256 FROM {SECTION} WHERE session_id=? ORDER BY ordinal
        LIMIT ?''', (ident, MAX_SECTIONS + 1)).fetchall()
    head, frames, size = _seed(row), 0, 0
    for ordinal, part in enumerate(parts):
        n, start, length, byte_count, sha, parent, after = part
        if (type(length) is not int or not 1 <= length <= MAX_SECTION_FRAMES
                or type(byte_count) is not int or byte_count != 44+length*2
                or any(type(value) is not str or len(value)!=64
                       or any(c not in '0123456789abcdef' for c in value)
                       for value in (sha,parent,after))):
            raise TransportError(503, 'Recording storage unavailable')
        if (n != ordinal or start != frames or parent != head
                or after != _next(head, ordinal, start, length, byte_count, sha)):
            raise TransportError(503, 'Recording storage unavailable')
        head = after
        frames += length
        size += byte_count
    if (len(parts) > MAX_SECTIONS or frames > MAX_TOTAL_FRAMES or size > MAX_TOTAL_BYTES
            or (row['section_count'], row['total_frames'], row['total_bytes'], row['manifest_sha256'])
            != (len(parts), frames, size, head)
            or row['revision'] != 1 + len(parts) + int(logical_state != 'open') + int(row['state']=='withdrawn')):
        raise TransportError(503, 'Recording storage unavailable')
    return row


class OralHistoryIntake:
    def __init__(self, access, *, enabled=False, withdrawal_enabled=False, journal=None):
        if type(enabled) is not bool or type(withdrawal_enabled) is not bool:
            raise ValueError('Explicit oral history opt-in required')
        if withdrawal_enabled and (journal is None or access.original_deletions is not journal):
            raise ValueError('Recording withdrawal requires its bound shared journal')
        self.withdrawal_enabled,self.journal=withdrawal_enabled,journal
        self.access, self.db, self.enabled = access, access.db, enabled

    def _ready(self):
        try:
            if not self.enabled:
                raise ValueError()
            assert_schema(self.db)
            # A completed SQLite commit must not use the no-durability profiles.
            if (self.db.execute('PRAGMA synchronous').fetchone()[0] < 2
                    or self.db.execute('PRAGMA journal_mode').fetchone()[0] not in {'delete', 'wal'}):
                raise ValueError()
        except ValueError:
            raise TransportError(503, 'Recording storage unavailable') from None

    def _member(self, token, library):
        member = self.access._require(token, library, 'library.read')
        self._ready()
        return member

    def _session(self, actor, library, ident):
        if self.access.original_deletions is not None:
            try:
                self.access.original_deletions.assert_recording_available(self.db, ident)
            except OriginalDeletionError:
                raise TransportError(503, 'Recording storage unavailable') from None
        return session_snapshot(self.db,actor,library,ident)

    @staticmethod
    def _status(row):
        return {'version': 1, 'session_id': row['id'], 'library_id': row['library_id'],
                'author_id': row['author_id'], 'title': row['title'],
                'subject_label': row['subject_label'], 'narrator_label': row['narrator_label'],
                'language': row['language'], 'processing_consent': bool(row['processing_consent']),
                'state': row['state'], 'revision': row['revision'],
                'section_count': row['section_count'], 'next_ordinal': row['section_count'],
                'total_bytes': row['total_bytes'], 'total_frames': row['total_frames'],
                'duration_ms': (row['total_frames'] * 1000 + 15999) // 16000,
                'manifest_sha256': row['manifest_sha256']}

    def _retry(self, actor, request, digest, operation, ident=None):
        prior = self.access._one(f'SELECT request_digest,receipt_json,receipt_sha256,session_id,operation FROM {MUTATION} WHERE author_id=? AND request_id=?',
                                 (actor, request))
        if prior is None:
            return None
        if prior['request_digest'] != digest:
            raise TransportError(409, 'Recording request identifier already used')
        try:
            raw = prior['receipt_json']
            if (type(raw) is not str or len(raw.encode('utf-8', 'strict')) > 16384
                    or hashlib.sha256(raw.encode('utf-8')).hexdigest() != prior['receipt_sha256']
                    or prior['operation'] != operation
                    or (ident is not None and prior['session_id'] != ident)):
                raise ValueError()
            result = json.loads(raw)
            keys = STATUS_FIELDS
            extra = {'ordinal', 'section_sha256'} if operation == 'append' else set()
            if (type(result) is not dict or set(result) != keys | {'request_id','operation'} | extra
                    or result['version'] != 1 or result['session_id'] != prior['session_id']
                    or result['author_id'] != actor or result['request_id'] != request
                    or result['operation'] != operation):
                raise ValueError()
            _uuid(result['session_id'])
            parent = self.access._one(f'SELECT * FROM {SESSION} WHERE id=? AND author_id=?',
                                      (prior['session_id'], actor))
            if parent is None:
                raise ValueError()
            for key in ('library_id','title','subject_label','narrator_label','language'):
                if type(result[key]) is not str or result[key] != parent[key]:
                    raise ValueError()
            if (type(result['version']) is not int or type(result['processing_consent']) is not bool
                    or result['processing_consent'] != bool(parent['processing_consent'])
                    or result['state'] != ('completed' if operation=='complete' else
                        'cancelled' if operation=='cancel' else 'open')):
                raise ValueError()
            for key, maximum in (('revision',MAX_SECTIONS+2),('section_count',MAX_SECTIONS),
                                 ('next_ordinal',MAX_SECTIONS),('total_bytes',MAX_TOTAL_BYTES),
                                 ('total_frames',MAX_TOTAL_FRAMES),('duration_ms',3600000)):
                _integer(result[key],maximum)
            if (result['revision'] != 1+result['section_count']+int(operation in {'complete','cancel'})
                    or result['next_ordinal'] != result['section_count']
                    or result['section_count'] > parent['section_count']
                    or result['duration_ms'] != (result['total_frames']*1000+15999)//16000):
                raise ValueError()
            if operation=='append':
                _integer(result['ordinal'],MAX_SECTIONS-1)
                if result['ordinal'] != result['section_count']-1:
                    raise ValueError()
                part = self.access._one(f'SELECT sha256,manifest_sha256 FROM {SECTION} WHERE session_id=? AND ordinal=?',
                                        (prior['session_id'],result['ordinal']))
                if (part is None or part['sha256'] != result['section_sha256']
                        or part['manifest_sha256'] != result['manifest_sha256']):
                    raise ValueError()
            elif operation=='create':
                if result['section_count'] != 0 or result['total_frames'] != 0 or result['total_bytes'] != 0 or result['manifest_sha256'] != _seed(parent):
                    raise ValueError()
            elif result['manifest_sha256'] != parent['manifest_sha256']:
                raise ValueError()
            return result
        except (ValueError, TypeError, UnicodeError, TransportError):
            raise TransportError(503, 'Recording receipt unavailable') from None

    def _record(self, actor, request, operation, digest, row, extra=None):
        result = self._status(row)
        result.update({'request_id': request, 'operation': operation})
        result.update(extra or {})
        raw = _json(result)
        self.db.execute(f'''INSERT INTO {MUTATION}
            (author_id,request_id,session_id,operation,request_digest,receipt_json,receipt_sha256)
            VALUES (?,?,?,?,?,?,?)''',
            (actor, request, row['id'], operation, digest, raw, hashlib.sha256(raw.encode('ascii')).hexdigest()))
        self.access._audit(actor, 'oral_history.' + operation, row['library_id'])
        return result

    def create(self, token, library, body):
        _text(library,128,required=True)
        if type(body) is not dict or set(body) != CREATE_FIELDS:
            raise TransportError(400, 'Invalid recording request')
        request = _uuid(body['request_id'])
        _text(body['title'], 512, required=True)
        _text(body['subject_label'], 512)
        _text(body['narrator_label'], 256)
        if (type(body['language']) is not str or body['language'] not in LANGUAGES
                or type(body['processing_consent']) is not bool):
            raise TransportError(422, 'Invalid recording options')
        digest = _digest(['create', library, body])
        with self.access._transaction(write=True):
            actor = self._member(token, library)['account_id']
            prior = self._retry(actor, request, digest, 'create')
            if prior is not None:
                self._session(actor, library, prior['session_id'])
                return prior
            count = self.db.execute(f'SELECT count(*) FROM {SESSION} WHERE author_id=?', (actor,)).fetchone()[0]
            if count >= MAX_SESSIONS_PER_AUTHOR:
                raise TransportError(409, 'Recording storage quota reached')
            row = {**body, 'id': str(uuid.uuid4()), 'author_id': actor, 'library_id': library}
            self.db.execute(f'''INSERT INTO {SESSION}
                (id,library_id,author_id,title,subject_label,narrator_label,language,processing_consent,
                 state,revision,section_count,total_bytes,total_frames,manifest_sha256,created_at)
                VALUES (?,?,?,?,?,?,?,?,'open',1,0,0,0,?,?)''',
                (row['id'], library, actor, body['title'], body['subject_label'], body['narrator_label'],
                 body['language'], int(body['processing_consent']), _seed(row), self.access._now()))
            return self._record(actor, request, 'create', digest, self._session(actor, library, row['id']))

    def append(self, token, library, ident, *, request_id, expected_revision, ordinal, audio):
        _text(library,128,required=True)
        ident, request = _uuid(ident), _uuid(request_id)
        revision = _integer(expected_revision, MAX_SECTIONS + 2, minimum=1)
        ordinal = _integer(ordinal, MAX_SECTIONS - 1)
        frames = wav_frames(audio)
        sha = hashlib.sha256(audio).hexdigest()
        digest = _digest(['append', library, ident, request, revision, ordinal, sha])
        with self.access._transaction(write=True):
            actor = self._member(token, library)['account_id']
            row = self._session(actor, library, ident)
            prior = self._retry(actor, request, digest, 'append', ident)
            if prior is not None:
                return prior
            if row['state'] != 'open' or row['revision'] != revision or row['section_count'] != ordinal:
                raise TransportError(409, 'Recording changed; refresh before adding a section')
            if row['total_frames'] + frames > MAX_TOTAL_FRAMES or row['total_bytes'] + len(audio) > MAX_TOTAL_BYTES:
                raise TransportError(409, 'Recording storage quota reached')
            after = _next(row['manifest_sha256'], ordinal, row['total_frames'], frames, len(audio), sha)
            self.db.execute(f'''INSERT INTO {SECTION}
                (session_id,ordinal,start_frame,frames,byte_count,audio,sha256,parent_manifest,manifest_sha256,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (ident, ordinal, row['total_frames'], frames, len(audio), audio, sha,
                 row['manifest_sha256'], after, self.access._now()))
            self.db.execute(f'''UPDATE {SESSION} SET revision=revision+1,section_count=section_count+1,
                total_frames=total_frames+?,total_bytes=total_bytes+?,manifest_sha256=? WHERE id=?''',
                (frames, len(audio), after, ident))
            return self._record(actor, request, 'append', digest, self._session(actor, library, ident),
                                {'ordinal': ordinal, 'section_sha256': sha})

    def status(self, token, library, ident):
        _text(library,128,required=True)
        ident = _uuid(ident)
        with self.access._transaction():
            actor = self._member(token, library)['account_id']
            return self._status(self._session(actor, library, ident))

    def audio(self, token, library, ident, ordinal):
        _text(library,128,required=True)
        ident = _uuid(ident)
        ordinal = _integer(ordinal, MAX_SECTIONS - 1)
        with self.access._transaction():
            actor = self._member(token, library)['account_id']
            self._session(actor, library, ident)
            row = self.access._one(f'SELECT audio,sha256,frames FROM {SECTION} WHERE session_id=? AND ordinal=?',
                                   (ident, ordinal))
            if row is None:
                raise AccessDenied('Access denied')
            try:
                audio = bytes(row['audio'])
                if wav_frames(audio) != row['frames'] or hashlib.sha256(audio).hexdigest() != row['sha256']:
                    raise ValueError()
            except (ValueError, TypeError, TransportError):
                raise TransportError(503, 'Recording source unavailable') from None
            return audio

    def close(self, token, library, ident, *, request_id, expected_revision, cancel=False):
        _text(library,128,required=True)
        ident, request = _uuid(ident), _uuid(request_id)
        revision = _integer(expected_revision, MAX_SECTIONS + 2, minimum=1)
        if type(cancel) is not bool:
            raise TransportError(400, 'Invalid recording close request')
        operation = 'cancel' if cancel else 'complete'
        digest = _digest([operation, library, ident, request, revision])
        with self.access._transaction(write=True):
            actor = self._member(token, library)['account_id']
            row = self._session(actor, library, ident)
            prior = self._retry(actor, request, digest, operation, ident)
            if prior is not None:
                return prior
            if (row['state'] != 'open' or row['revision'] != revision
                    or (not cancel and row['section_count'] == 0)):
                raise TransportError(409, 'Recording changed; refresh before closing')
            self.db.execute(f'UPDATE {SESSION} SET state=?,revision=revision+1 WHERE id=?',
                            ('cancelled' if cancel else 'completed', ident))
            return self._record(actor, request, operation, digest, self._session(actor, library, ident))

    def withdraw(self, token, library, ident, *, request_id, expected_revision):
        """Explicit author-only withdrawal; retain raw source, append external V4 first."""
        _text(library,128,required=True)
        ident,request=_uuid(ident),_uuid(request_id)
        revision=_integer(expected_revision,MAX_SECTIONS+2,minimum=1)
        digest=_digest(['withdraw',library,ident,request,revision])
        if not self.withdrawal_enabled:
            raise TransportError(503,'Recording withdrawal unavailable')
        from .oral_history_withdrawal import prepare_recording_tombstone, apply_recording_tombstone
        from .original_deletions import OriginalDeletionError
        try:
            with self.access._transaction(write=True):
                actor=self._member(token,library)['account_id']
                row=session_snapshot(self.db,actor,library,ident,allow_withdrawn=True)
                self.journal.require_oral_format()
                if self.db.execute('PRAGMA secure_delete=ON').fetchone()[0]!=1:
                    raise TransportError(503,'Recording withdrawal unavailable')
                if row['state']=='withdrawn':
                    if row['withdrawal_request_id']!=request or row['withdrawal_request_digest']!=digest:
                        raise TransportError(409,'Recording withdrawal request differs')
                    self.journal.oral_record(self.db,ident)
                else:
                    if row['revision']!=revision:
                        raise TransportError(409,'Recording changed; refresh before withdrawing')
                    tombstone=prepare_recording_tombstone(self.db,ident,library,actor,
                        revision,request,digest,self.access._now())
                    self.journal.append(self.db,'oral_history',{'id':ident,'library_id':library,
                        'author_id':actor,'revision':revision,'request_id':request,
                        'request_digest':digest,'oral_binding_json':tombstone['oral_binding_json']},
                        self.access._now())
                    apply_recording_tombstone(self.db,tombstone)
                    self.access._audit(actor,'oral_history.withdraw',library)
                    row=session_snapshot(self.db,actor,library,ident,allow_withdrawn=True)
                return {'version':1,'session_id':ident,'request_id':request,
                        'state':'withdrawn','revision':row['revision']}
        except OriginalDeletionError:
            raise TransportError(503,'Recording withdrawal unavailable') from None

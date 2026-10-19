"""Real migrated ASGI transfer lifecycle with synthetic media; no runtime access."""
from contextlib import closing
import errno
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import test_upload as fixture
from app.access.resumable import Transfers, CHUNK_BYTES, MAX_IMAGE_BYTES, MAX_VIDEO_BYTES, _acquire_windows_byte_lock
from app.access.transport import COOKIE
from app.access.transport import TransportError


class ResumableUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.UploadTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.UploadTests.tearDownClass()
    def setUp(self):
        self.f=fixture.UploadTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        self.client=self.f.client();self.headers={'Authorization':'Bearer '+self.f.member_token}
        self.data=fixture.png(64,64,b'synthetic-media')
    def create(self,data=None,**overrides):
        data=self.data if data is None else data
        body=dict(request_id='1'*32,batch='2'*32,filename='photo.png',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),kind='image');body.update(overrides)
        response=self.client.post('/upload-sessions',headers=self.headers,json=body)
        self.assertEqual(201,response.status_code,response.text)
        return response.json(),body
    def append(self,row,data=None,offset=0,**headers):
        data=self.data if data is None else data
        return self.client.put('/upload-sessions/'+row['upload_id'],headers={**self.headers,'Content-Type':'application/octet-stream','Upload-Offset':str(offset),'X-Chunk-SHA256':hashlib.sha256(data).hexdigest(),**headers},content=data)
    def complete(self,row): return self.client.post('/upload-sessions/'+row['upload_id']+'/complete',headers=self.headers,json={})
    def mutate(self,sql,args=()):
        with closing(self.f.connection()) as db:db.execute(sql,args);db.commit()

    def test_restart_resume_and_complete_retry_is_one_receipt_and_no_library(self):
        row,body=self.create();self.assertEqual(row['offset'],0)
        first=self.data[:16];self.assertEqual(self.append(row,first).json()['offset'],16)
        with self.f.client() as restarted:
            current=restarted.get('/upload-sessions/'+row['upload_id'],headers=self.headers).json();self.assertEqual(current['offset'],16)
        self.assertEqual(self.append(row,self.data[16:],16).status_code,200)
        result=self.complete(row);self.assertEqual(200,result.status_code,result.text)
        received=result.json();self.assertEqual(received['state'],'complete')
        self.assertEqual(received,self.complete(row).json())
        self.assertEqual(received,self.client.post('/upload-sessions',headers=self.headers,json=body).json())
        self.assertEqual(1,len(self.f.rows('SELECT * FROM access_uploads')))
        self.assertEqual(5,len(self.f.rows('SELECT * FROM tasks')))
        self.assertEqual([],self.f.rows('SELECT * FROM access_asset_libraries WHERE asset_id=?',(received['asset_id'],)))
        # Retrying after approval must still return the same receipt, not rely on incoming dedup.
        self.mutate("UPDATE access_uploads SET state='assigned'")
        self.assertEqual(received,self.complete(row).json())

    def test_duplicate_chunk_conflicts_and_get_reports_confirmed_offset(self):
        row,_=self.create();self.assertEqual(self.append(row).status_code,200)
        self.assertEqual(self.append(row).status_code,409)
        result=self.client.get('/upload-sessions/'+row['upload_id'],headers=self.headers)
        self.assertEqual(len(self.data),result.json()['offset']);self.assertIn('no-store',result.headers['cache-control'])

    def test_create_retry_requires_exact_parameters(self):
        row,body=self.create();body['filename']='changed.png'
        self.assertEqual(409,self.client.post('/upload-sessions',headers=self.headers,json=body).status_code)
        self.assertEqual(1,len(self.f.rows('SELECT * FROM access_upload_transfers')))

    def test_another_account_cannot_read_append_complete_cancel_or_learn_name(self):
        row,_=self.create();self.headers={'Authorization':'Bearer '+self.f.owner_token}
        self.assertEqual(404,self.client.get('/upload-sessions/'+row['upload_id'],headers=self.headers).status_code)
        self.assertEqual(404,self.append(row).status_code)
        self.assertEqual(404,self.complete(row).status_code)
        self.assertEqual(404,self.client.delete('/upload-sessions/'+row['upload_id'],headers=self.headers).status_code)

    def test_cancel_is_durable_retriable_and_never_creates_asset(self):
        row,_=self.create();self.append(row,self.data[:10])
        path=self.f.incoming/'.transfers'/(row['upload_id']+'.part');self.assertTrue(path.exists())
        result=self.client.delete('/upload-sessions/'+row['upload_id'],headers=self.headers)
        self.assertEqual('cancelled',result.json()['state']);self.assertFalse(path.exists())
        self.assertEqual(result.json(),self.client.delete('/upload-sessions/'+row['upload_id'],headers=self.headers).json())
        self.assertEqual(409,self.complete(row).status_code);self.assertEqual([],self.f.rows('SELECT * FROM access_uploads'))

    def test_revoked_membership_stops_transfer_before_reading_body(self):
        row,_=self.create();self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",(self.f.member_id,))
        self.assertEqual(401,self.append(row).status_code);self.assertEqual(401,self.complete(row).status_code)
        self.assertFalse((self.f.incoming/'.transfers').exists())

    def test_bad_chunk_digest_and_full_digest_fail_without_receipt(self):
        row,_=self.create(sha256='0'*64)
        self.assertEqual(422,self.append(row,**{'X-Chunk-SHA256':'f'*64}).status_code)
        self.assertEqual(200,self.append(row).status_code)
        self.assertEqual(422,self.complete(row).status_code);self.assertEqual([],self.f.rows('SELECT * FROM access_uploads'))

    def test_incomplete_finish_and_overshoot_refused(self):
        row,_=self.create();self.assertEqual(409,self.complete(row).status_code)
        self.assertEqual(413,self.append(row,self.data+b'extra').status_code)
        self.assertEqual(0,self.client.get('/upload-sessions/'+row['upload_id'],headers=self.headers).json()['offset'])

    def test_crash_extra_bytes_truncate_to_committed_offset(self):
        row,_=self.create();self.append(row,self.data[:10])
        path=self.f.incoming/'.transfers'/(row['upload_id']+'.part')
        with path.open('ab') as stream:stream.write(b'crash-tail')
        self.assertEqual(200,self.append(row,self.data[10:],10).status_code)
        self.assertEqual(hashlib.sha256(self.data).hexdigest(),hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(200,self.complete(row).status_code)

    def test_commit_failure_rolls_back_offset_and_retry_repairs_tail(self):
        row,_=self.create()
        self.mutate("CREATE TRIGGER fail_offset BEFORE UPDATE OF offset ON access_upload_transfers BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        self.assertEqual(503,self.append(row).status_code)
        self.mutate('DROP TRIGGER fail_offset')
        self.assertEqual(0,self.client.get('/upload-sessions/'+row['upload_id'],headers=self.headers).json()['offset'])
        self.assertEqual(200,self.append(row).status_code);self.assertEqual(200,self.complete(row).status_code)

    def test_video_uses_only_probe_job_and_history_video_kind(self):
        data=(Path(__file__).parent/'fixtures/home-video.mp4').read_bytes()
        row,_=self.create(data,kind='video',filename='movie.mp4');self.assertEqual(200,self.append(row,data).status_code)
        result=self.complete(row);self.assertEqual(200,result.status_code,result.text)
        self.assertEqual(['video_probe'],[r[0] for r in self.f.rows('SELECT type FROM tasks')])
        history=self.client.get('/uploads?page=1',headers=self.headers).json()['items'][0]
        self.assertEqual('video',history['kind']);self.assertEqual('awaiting_review',history['state'])

    def test_type_spoof_and_missing_video_boxes_refused(self):
        for i,data in enumerate((self.data,b'not a movie',b'\x00\x00\x00\x18ftypisom0000isommp42')):
            row,_=self.create(data,kind='video',filename='movie.mp4',request_id=f'{i:032x}')
            self.assertEqual(200,self.append(row,data).status_code);self.assertEqual(415,self.complete(row).status_code)
        self.assertEqual([],self.f.rows('SELECT * FROM access_uploads'))

    def test_larger_than_old_limit_uses_only_bounded_chunks(self):
        head=fixture.png(64,64);block=b'0'*(1024*1024);size=len(head)+26*len(block)
        digest=hashlib.sha256(head)
        for _ in range(26):digest.update(block)
        row,_=self.create(bytes=size,sha256=digest.hexdigest())
        offset=0
        for data in (head,*([block]*26)):
            response=self.append(row,data,offset);self.assertEqual(200,response.status_code);offset+=len(data)
        result=self.complete(row);self.assertEqual(200,result.status_code,result.text)
        self.assertEqual(size,result.json()['bytes'])

    def test_limits_and_filename_traversal_are_rejected(self):
        _,body=self.create()
        for changes,status in [({'bytes':MAX_IMAGE_BYTES+1},413),({'kind':'video','bytes':MAX_VIDEO_BYTES+1},413),({'bytes':True},400),({'filename':'../secret'},400),({'filename':'C:\\secret'},400),({'kind':'audio'},400)]:
            self.assertEqual(status,self.client.post('/upload-sessions',headers=self.headers,json={**body,**changes}).status_code)
        self.assertEqual(400,self.client.post('/upload-sessions?page=1',headers=self.headers,json=body).status_code)

    def test_cookie_csrf_and_anonymous_denied(self):
        _,body=self.create()
        self.assertEqual(401,self.client.post('/upload-sessions',json=body).status_code)
        self.assertEqual(403,self.client.post('/upload-sessions',headers={'Cookie':COOKIE+'='+self.f.member_token},json=body).status_code)

    def test_oversized_chunk_rejected_and_slots_released(self):
        row,_=self.create(bytes=CHUNK_BYTES+1)
        self.assertEqual(413,self.append(row,b'x'*(CHUNK_BYTES+1)).status_code)
        self.assertEqual(200,self.append(row,b'x').status_code)

    def test_completion_commit_failure_can_retry_without_duplicate_asset(self):
        row,_=self.create();self.append(row)
        self.mutate("CREATE TRIGGER fail_finish BEFORE UPDATE OF state ON access_upload_transfers BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        self.assertEqual(503,self.complete(row).status_code)
        self.assertEqual([],self.f.rows('SELECT * FROM access_uploads'))
        self.mutate('DROP TRIGGER fail_finish')
        result=self.complete(row);self.assertEqual(200,result.status_code,result.text)
        self.assertEqual(1,len(self.f.rows('SELECT * FROM access_uploads')))

    def test_untrusted_nested_json_is_invalid_not_an_internal_error(self):
        _,body=self.create()
        for value in ([],{},None):
            response=self.client.post('/upload-sessions',headers=self.headers,json={**body,'kind':value})
            self.assertEqual(400,response.status_code,response.text)

    def test_valid_cookie_csrf_can_create_session(self):
        from app.access.transport import csrf_token
        _,body=self.create()
        response=self.client.post('/upload-sessions',headers={'Cookie':COOKIE+'='+self.f.member_token,
            'Origin':'https://photohouse.test','X-CSRF-Token':csrf_token(self.f.member_token)},json=body)
        self.assertEqual(201,response.status_code,response.text)

    def test_same_transfer_busy_lock_refuses_without_waiting(self):
        row,_=self.create();transfers=Transfers(self.f.runtime)
        with transfers.lock(self.f.member_token,row['upload_id']):
            self.assertEqual(429,self.append(row).status_code)
        self.assertEqual(200,self.append(row).status_code)

    def test_windows_crt_busy_errno_is_normalized_only_at_lock_acquisition(self):
        class FakeMsvcrt:
            LK_NBLCK=1
            def __init__(self,error):self.error=error
            def locking(self,fd,mode,count):raise self.error

        with tempfile.TemporaryFile() as stream:
            with self.assertRaises(BlockingIOError):
                _acquire_windows_byte_lock(stream.fileno(),FakeMsvcrt(OSError(errno.EACCES,'busy')))
        with tempfile.TemporaryFile() as stream:
            with self.assertRaises(OSError) as raised:
                _acquire_windows_byte_lock(stream.fileno(),FakeMsvcrt(OSError(errno.EIO,'storage failure')))
            self.assertEqual(errno.EIO,raised.exception.errno)
        with tempfile.TemporaryFile() as stream:
            with patch('app.access.resumable.os.write',side_effect=PermissionError(errno.EACCES,'storage denied')):
                with self.assertRaises(PermissionError) as raised:
                    _acquire_windows_byte_lock(stream.fileno(),FakeMsvcrt(None))
            self.assertEqual(errno.EACCES,raised.exception.errno)

    def test_lock_body_error_propagates_closes_descriptor_and_allows_retry(self):
        row,_=self.create();transfers=Transfers(self.f.runtime);opened=[]
        original_open=os.open
        def capture_lock_descriptor(path,*args,**kwargs):
            fd=original_open(path,*args,**kwargs)
            if str(path).endswith('.lock'):opened.append(fd)
            return fd
        with patch('app.access.resumable.os.open',side_effect=capture_lock_descriptor):
            with self.assertRaisesRegex(BlockingIOError,'synthetic body failure'):
                with transfers.lock(self.f.member_token,row['upload_id']):
                    raise BlockingIOError('synthetic body failure')
        self.assertEqual(1,len(opened))
        with self.assertRaises(OSError):os.fstat(opened[0])
        self.assertEqual(200,self.append(row).status_code)

    def test_windows_eacces_lock_contention_returns_upload_busy(self):
        row,_=self.create();transfers=Transfers(self.f.runtime)
        def locked_out(*_args):
            raise OSError(errno.EACCES, 'synthetic Windows lock contention')
        msvcrt=SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=locked_out)
        with patch.dict(sys.modules, {'msvcrt': msvcrt}), \
                patch('app.access.resumable._is_windows', return_value=True):
            with self.assertRaises(TransportError) as caught:
                with transfers.lock(self.f.member_token,row['upload_id']):
                    self.fail('contended lock must not be acquired')
        self.assertEqual(429,caught.exception.status)
        self.assertEqual('Upload busy',caught.exception.message)

    def test_windows_unrelated_lock_error_remains_visible(self):
        row,_=self.create();transfers=Transfers(self.f.runtime)
        def failed_lock(*_args):
            raise OSError(errno.EIO, 'synthetic Windows lock I/O failure')
        msvcrt=SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=failed_lock)
        with patch.dict(sys.modules, {'msvcrt': msvcrt}), \
                patch('app.access.resumable._is_windows', return_value=True):
            with self.assertRaises(OSError) as caught:
                with transfers.lock(self.f.member_token,row['upload_id']):
                    self.fail('failed lock must not be acquired')
        self.assertEqual(errno.EIO,caught.exception.errno)

    def test_lock_body_blocking_error_is_not_rewritten_as_upload_busy(self):
        row,_=self.create();transfers=Transfers(self.f.runtime)
        msvcrt=SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2, locking=lambda *_args: None)
        with patch.dict(sys.modules, {'msvcrt': msvcrt}), \
                patch('app.access.resumable._is_windows', return_value=True):
            with self.assertRaises(BlockingIOError):
                with transfers.lock(self.f.member_token,row['upload_id']):
                    raise BlockingIOError('synthetic transfer-body error')

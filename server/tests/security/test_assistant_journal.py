"""Synthetic durable receipt, retention, replay and policy regression checks."""
from contextlib import closing
import io
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
import wave
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from app.access.assistant_journal import (Journal, JournalUnavailable, JournalConflict,
    JournalMissing, RETENTION_SECONDS, initialize)
from app.access.assistant_speech import LocalAssistantAsr
from app.access.transport import COOKIE, csrf_token
import test_assistant_http as fixture
from test_assistant_http import ORIGIN, TOKEN, SECOND, NOW


def ident():
    return str(uuid.uuid4())


class JournalStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve()/'private.sqlite'
        self.now = 2000000000
        initialize(self.path)
        self.journal = Journal(self.path, clock=lambda:self.now)

    def test_expiry_purge_secure_delete_and_metadata_only_inspection(self):
        request = ident()
        text = 'synthetic-private-command-marker'
        self.journal.begin('author','library','turn',request,text=text)
        self.journal.finish(request,'succeeded',http_status=200,kind='results',total=2)
        self.assertNotIn(text, str(self.journal.inspect()))
        self.assertIn(text, str(self.journal.inspect(include_input=True)))
        self.now += RETENTION_SECONDS
        with self.assertRaises(JournalMissing):
            self.journal.get(request,'author','library')
        self.assertEqual(self.journal.maintenance(),1)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],0)
        self.assertNotIn(text.encode(),self.path.read_bytes())
        self.assertFalse(Path(str(self.path)+'-wal').exists())

    def test_exclusive_initialization_no_implicit_creation_or_symlink(self):
        with self.assertRaises(FileExistsError):
            initialize(self.path)
        absent = self.path.with_name('mistyped.sqlite')
        with self.assertRaises(JournalUnavailable):
            Journal(absent)
        self.assertFalse(absent.exists())
        link = self.path.with_name('link.sqlite')
        link.symlink_to(self.path)
        with self.assertRaises(JournalUnavailable):
            Journal(link)

    def test_restart_preserves_received_trace_and_marks_interrupted(self):
        request = ident()
        self.journal.begin('author','library','transcribe',request)
        self.journal.stage(request,'provider_started')
        reopened = Journal(self.path,clock=lambda:self.now)
        reopened.maintenance(interrupt=True)
        receipt = reopened.get(request,'author','library')
        self.assertEqual(receipt['status'],'interrupted')
        self.assertEqual(receipt['error_code'],'server_interrupted')
        with self.assertRaises(JournalConflict):
            reopened.begin('author','library','transcribe',request)


class JournalHttpTests(unittest.TestCase):
    setUp = fixture.AssistantHttpTests.setUp
    connection = fixture.AssistantHttpTests.connection
    turn = fixture.AssistantHttpTests.turn
    update = fixture.AssistantHttpTests.update

    def journal(self):
        path = Path(self.temp.name).resolve()/'assistant.sqlite'
        initialize(path)
        self.app.state.assistant_journal = Journal(path,clock=lambda:NOW)
        return self.app.state.assistant_journal

    def receipt(self, request, headers=None, library='family-a'):
        return self.client.get('/assistant/v1/receipts/'+request+'?library_id='+library,
            headers=self.auth if headers is None else headers)

    def outcome(self, request, outcome='displayed', headers=None):
        return self.client.post('/assistant/v1/receipts/'+request+'/outcome',
            json={'library_id':'family-a','outcome':outcome},headers=self.auth if headers is None else headers)

    def wav(self):
        output=io.BytesIO()
        with wave.open(output,'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
            wav.writeframes(b'\0\0'*1600)
        return output.getvalue()

    def asr(self, provider):
        self.app.state.assistant_asr = LocalAssistantAsr(url='http://127.0.0.1:7350/transcribe',
            model='synthetic',transport=httpx.MockTransport(provider))

    def transcribe(self, request, content=None):
        return self.client.post('/assistant/v1/transcribe',content=self.wav() if content is None else content,
            headers=dict(self.auth, **{'Content-Type':'audio/wav','X-PhotoHouse-Library-Id':'family-a',
                                       'X-PhotoHouse-Request-Id':request}))

    def test_legacy_json_compatibility_generated_receipt_and_client_report(self):
        journal=self.journal()
        response=self.turn('找照片')
        self.assertEqual(response.status_code,200,response.text)
        request=response.headers['x-photohouse-request-id']
        self.assertEqual(response.headers['x-photohouse-receipt-status'],'succeeded')
        self.assertNotIn('request_id',response.json())
        receipt=self.receipt(request)
        self.assertEqual(receipt.status_code,200,receipt.text)
        self.assertEqual(receipt.json()['input_text'],'找照片')
        self.assertEqual(receipt.json()['operation'],'turn')
        self.assertEqual(self.outcome(request).status_code,200)
        self.assertEqual(self.outcome(request).status_code,200)
        self.assertEqual(self.receipt(request).json()['client_outcome'],'displayed')
        self.assertEqual(journal.inspect()['items'][0]['stages'][-1]['stage'],'client_displayed')
        self.app.state.assistant_journal=None
        untracked=self.turn('找照片')
        self.assertEqual(untracked.headers['x-photohouse-tracking'],'disabled')
        self.assertNotIn('x-photohouse-request-id',untracked.headers)

    def test_owner_other_account_revocation_csrf_and_route_boundary(self):
        self.journal()
        request=self.turn('找照片').headers['x-photohouse-request-id']
        other={'Authorization':'Bearer '+SECOND}
        self.assertEqual(self.receipt(request,headers=other).status_code,404)
        self.assertEqual(self.outcome(request,headers=other).status_code,404)
        self.assertEqual(self.receipt(request,library='family-b').status_code,401)
        web={'Cookie':COOKIE+'='+TOKEN,'Origin':ORIGIN}
        self.assertEqual(self.outcome(request,headers=web).status_code,403)
        self.assertEqual(self.outcome(request,headers=dict(web,**{'X-CSRF-Token':csrf_token(TOKEN)})).status_code,200)
        self.assertEqual(self.client.get('/assistant/v1/receipts/'+request+'/outcome',headers=self.auth).status_code,403)
        self.assertEqual(self.client.post('/assistant/v1/receipts/'+request,json={},headers=self.auth).status_code,403)
        self.update("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        self.assertEqual(self.receipt(request).status_code,401)
        self.assertEqual(self.outcome(request).status_code,401)

    def test_transcription_link_duplicate_refusal_and_no_raw_audio(self):
        journal=self.journal(); calls=[]
        self.asr(lambda req: calls.append(req.content) or httpx.Response(200,json={'success':True,'text':'找照片'}))
        request=ident(); response=self.transcribe(request)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.receipt(request).json()['recognized_text'],'找照片')
        self.assertEqual(self.transcribe(request).status_code,409)
        self.assertEqual(len(calls),1)
        turn_id=ident()
        result=self.turn('找照片',headers=dict(self.auth,**{'X-PhotoHouse-Request-Id':turn_id,
                              'X-PhotoHouse-Parent-Request-Id':request}))
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(self.receipt(turn_id).json()['parent_request_id'],request)
        wrong=self.turn('找照片',headers=dict(self.auth,**{'X-PhotoHouse-Parent-Request-Id':turn_id}))
        self.assertEqual(wrong.status_code,404)
        self.assertNotIn(self.wav(),journal.path.read_bytes())
        self.assertNotIn(TOKEN.encode(),journal.path.read_bytes())

    def test_failures_have_receipts_and_do_not_save_provider_error(self):
        journal=self.journal()
        self.asr(lambda req: httpx.Response(500,text='secret-provider-stack'))
        request=ident(); response=self.transcribe(request)
        self.assertEqual(response.status_code,503,response.text)
        self.assertEqual(response.headers['x-photohouse-receipt-status'],'failed')
        self.assertEqual(self.receipt(request).json()['error_code'],'speech_unavailable')
        bad=ident(); self.assertEqual(self.transcribe(bad,b'bad').status_code,400)
        self.assertEqual(self.receipt(bad).json()['error_code'],'invalid_request')
        self.assertNotIn(b'secret-provider-stack',journal.path.read_bytes())

    def test_storage_failure_prevents_provider_and_durable_completion_claim(self):
        journal=self.journal(); calls=[]
        self.asr(lambda req: calls.append(req) or httpx.Response(200,json={'success':True,'text':'find photos'}))
        with patch.object(journal,'begin',side_effect=JournalUnavailable()):
            response=self.transcribe(ident())
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json()['error'],'tracking_unavailable')
        self.assertEqual(calls,[])
        request=ident()
        with patch.object(journal,'finish',side_effect=JournalUnavailable()):
            response=self.transcribe(request)
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.headers['x-photohouse-receipt-status'],'received')
        self.assertEqual(self.receipt(request).json()['status'],'received')

    def test_expired_or_unauthorized_inputs_are_not_disclosed_or_recorded(self):
        journal=self.journal()
        denied=self.turn('private text',library='family-b')
        self.assertEqual(denied.status_code,401)
        self.assertEqual(journal.inspect()['count'],0)
        request=self.turn('找照片').headers['x-photohouse-request-id']
        journal.clock=lambda:NOW+RETENTION_SECONDS
        self.assertEqual(self.receipt(request).status_code,404)
        self.assertEqual(self.outcome(request).status_code,404)

    def test_configured_journal_records_unavailable_engine_and_outcomes_do_not_regress(self):
        self.journal()
        self.app.state.discovery_runtime = None
        response=self.turn('find photos')
        self.assertEqual(response.status_code,503)
        request=response.headers['x-photohouse-request-id']
        self.app.state.discovery_runtime = self.discovery
        self.assertEqual(self.receipt(request).json()['error_code'],'assistant_unavailable')
        request=self.turn('find photos').headers['x-photohouse-request-id']
        self.assertEqual(self.outcome(request,'displayed').status_code,200)
        self.assertEqual(self.outcome(request,'open_requested').status_code,200)
        self.assertEqual(self.outcome(request,'displayed').status_code,409)
        self.assertEqual(self.outcome(request,'failed').status_code,409)
        self.assertEqual(self.receipt(request).json()['client_outcome'],'open_requested')

    def test_retention_failure_and_revocation_during_asr_fail_closed(self):
        journal=self.journal(); calls=[]
        def provider(req):
            calls.append(1)
            self.update("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
            return httpx.Response(200,json={'success':True,'text':'private-derived-text'})
        self.asr(provider)
        self.app.state.assistant_journal_healthy=False
        result=self.transcribe(ident())
        self.assertEqual(result.json()['error'],'tracking_unavailable')
        self.assertEqual(calls,[])
        self.app.state.assistant_journal_healthy=True
        request=ident(); result=self.transcribe(request)
        self.assertEqual(result.status_code,401)
        self.assertEqual(len(calls),1)
        saved=journal.get(request,'one','family-a')
        self.assertEqual(saved['status'],'failed')
        self.assertIsNone(saved['recognized_text'])
        self.assertNotIn(b'private-derived-text',journal.path.read_bytes())

    def test_lifespan_reconciles_interrupted_records(self):
        journal=self.journal()
        request=ident(); journal.begin('one','family-a','turn',request,text='find photos')
        with TestClient(self.app,base_url=ORIGIN) as client:
            result=client.get('/assistant/v1/receipts/'+request+'?library_id=family-a',headers=self.auth)
            self.assertEqual(result.json()['status'],'interrupted')

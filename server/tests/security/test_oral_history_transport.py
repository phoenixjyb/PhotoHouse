"""Generated HTTP coverage for default-off, resumable author-private intake."""
from contextlib import closing, contextmanager
import uuid
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import httpx

import test_oral_history_intake as fixture
from app.main import create_app
from app.access.assistant_speech import LocalAssistantAsr
from app.access.oral_history_schema import SESSION, SECTION, MUTATION, STATEMENTS
from app.access.transport import AccessRuntime, COOKIE, csrf_token
from app.access.oral_history_intake import STATUS_FIELDS
from app.access.service import AccessService


class OralHistoryTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.OralHistoryIntakeTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.OralHistoryIntakeTests.tearDownClass()

    def setUp(self):
        self.base = fixture.OralHistoryIntakeTests()
        self.base.setUp()
        self.addCleanup(self.base.doCleanups)
        self.member, self.owner = self.base.member, self.base.owner
        self.connect = self.base.connect

        @contextmanager
        def connection_factory():
            db = self.connect()
            try:
                yield db
            finally:
                db.close()

        self.runtime = AccessRuntime(connection_factory, 'https://photohouse.test',
                                     clock=lambda: fixture.foundation.NOW)
        self.client = self.build()
        self.addCleanup(self.client.close)

    def build(self, *, enabled=True, asr=None):
        return TestClient(create_app(access_runtime=self.runtime, assistant_asr=asr,
            oral_history_intake_enabled=enabled, oral_history_transcription_enabled=asr is not None),
            base_url='https://photohouse.test',
            client=('192.0.2.30', 24567))

    def request(self, method, path, *, body=None, content=None, headers=None, client=None):
        return (client or self.client).request(method, path,
            headers={'Authorization':'Bearer '+self.member} | (headers or {}),
            json=body, content=content)

    def create_body(self, **changes):
        return self.base.body(**({'processing_consent': False} | changes))

    @staticmethod
    def session_path(ident, library='family-a'):
        return f'/oral-history/v1/libraries/{library}/sessions/{ident}'

    def append(self, record, *, request_id, audio=None, token=None):
        headers={'X-PhotoHouse-Request-Id':request_id,
            'X-PhotoHouse-Expected-Revision':str(record['revision']),
            'X-PhotoHouse-Ordinal':str(record['next_ordinal']), 'Content-Type':'audio/wav'}
        if token: headers['Authorization']='Bearer '+token
        return self.request('POST', self.session_path(record['session_id'])+'/sections',
            content=audio if audio is not None else fixture.wav(), headers=headers)

    def completed_record(self, *, library='family-a', token=None, audio=None,
                         processing_consent=False):
        headers={'Authorization':'Bearer '+token} if token else None
        created=self.request('POST',f'/oral-history/v1/libraries/{library}/sessions',
            body=self.create_body(processing_consent=processing_consent),headers=headers).json()
        append_headers={'X-PhotoHouse-Request-Id':str(uuid.uuid4()),
            'X-PhotoHouse-Expected-Revision':str(created['revision']),
            'X-PhotoHouse-Ordinal':str(created['next_ordinal']),'Content-Type':'audio/wav'}
        if token: append_headers['Authorization']='Bearer '+token
        appended=self.request('POST',self.session_path(created['session_id'],library)+'/sections',
            content=audio or fixture.wav(800),headers=append_headers)
        self.assertEqual(appended.status_code,200,appended.text)
        closed=self.request('POST',self.session_path(created['session_id'],library)+'/complete',
            body={'request_id':str(uuid.uuid4()),'expected_revision':appended.json()['revision']},headers=headers)
        self.assertEqual(closed.status_code,200,closed.text)
        return closed.json()

    def counts(self):
        with closing(self.connect()) as db:
            return tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                         for table in (SESSION, SECTION, MUTATION))

    def assert_private(self, response):
        self.assertEqual(response.headers.get('cache-control'), 'no-store')
        self.assertEqual(response.headers.get('pragma'), 'no-cache')

    def transcription_client(self, provider):
        asr = LocalAssistantAsr(url='http://127.0.0.1:19001/transcribe', model='synthetic',
                                transport=httpx.MockTransport(provider))
        client = self.build(asr=asr)
        self.addCleanup(client.close)
        return client

    def preview(self, record, *, client=None, token=None, revision=None):
        path = self.session_path(record['session_id']) + '/sections/0/transcription'
        return self.request('POST', path,
                            body={'expected_revision': record['revision'] if revision is None else revision},
                            headers={'Authorization': 'Bearer ' + token} if token else None,
                            client=client)

    def test_transcript_requires_author_consent_and_explicit_current_section(self):
        calls = []

        def speech(request):
            calls.append(request.content)
            return httpx.Response(200, json={'text': '公园 in the morning'})

        audio = fixture.wav(800)
        client = self.transcription_client(speech)
        opted_in = self.completed_record(audio=audio, processing_consent=True)
        opted_out = self.completed_record()
        before = self.counts()
        self.assertEqual(self.preview(opted_in).status_code, 503)
        self.assertEqual(self.preview(opted_out, client=client).status_code, 403)
        self.assertEqual(self.preview(opted_in, client=client, token=self.owner).status_code, 401)
        self.assertEqual(self.preview(opted_in, client=client, revision=2).status_code, 409)
        self.assertEqual(calls, [])

        result = self.preview(opted_in, client=client)
        self.assertEqual(result.status_code, 200, result.text)
        self.assert_private(result)
        self.assertEqual(result.json(), {'version': 1, 'session_id': opted_in['session_id'],
                         'revision': opted_in['revision'], 'ordinal': 0, 'language': 'mixed',
                         'text': '公园 in the morning', 'saved': False})
        self.assertEqual(calls, [audio])
        self.assertEqual(self.counts(), before)
        status = self.request('GET', self.session_path(opted_in['session_id']))
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json(), {key: opted_in[key] for key in STATUS_FIELDS})

    def test_transcript_is_withheld_when_the_source_withdraws_during_local_asr(self):
        record = self.completed_record(processing_consent=True)
        calls = []

        def speech(request):
            calls.append(request.content)
            with closing(self.connect()) as db:
                db.execute(f"UPDATE {SESSION} SET state='withdrawn',withdrawn_from='completed',"
                           "withdrawal_request_id=?,withdrawal_request_digest=?,revision=revision+1 WHERE id=?",
                           (str(uuid.uuid4()), 'a' * 64, record['session_id']))
                db.commit()
            return httpx.Response(200, json={'text': 'Generated private transcript'})

        response = self.preview(record, client=self.transcription_client(speech))
        self.assertEqual(response.status_code, 401)
        self.assert_private(response)
        self.assertNotIn('Generated private transcript', response.text)
        self.assertEqual(len(calls), 1)

    def test_transcription_busy_refuses_without_a_second_provider_call(self):
        def unused(_request):
            self.fail('busy recording preview must not call the provider')

        client = self.transcription_client(unused)
        record = self.completed_record(processing_consent=True)
        lock = client.app.state.oral_history_transcription_lock
        with lock:
            response = self.preview(record, client=client)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json(), {'detail': 'Recording transcription is busy'})

    def test_transcription_provider_failure_releases_the_slot_for_an_explicit_retry(self):
        replies = iter((httpx.Response(200, json={'text': ''}),
                        httpx.Response(200, json={'text': 'A later machine transcript'})))
        client = self.transcription_client(lambda _request: next(replies))
        record = self.completed_record(processing_consent=True)
        failed = self.preview(record, client=client)
        self.assertEqual(failed.status_code, 422)
        self.assertEqual(failed.json(), {'detail': 'Recording transcription unavailable'})
        retried = self.preview(record, client=client)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(retried.json()['text'], 'A later machine transcript')

    def test_create_append_restart_status_exact_retry_and_next_section(self):
        create_body=self.create_body()
        created_response=self.request('POST','/oral-history/v1/libraries/family-a/sessions',body=create_body)
        self.assertEqual(created_response.status_code,201,created_response.text);self.assert_private(created_response)
        created=created_response.json()
        self.assertTrue(created['retention_consent']);self.assertFalse(created['processing_consent'])
        self.assertEqual((created['state'],created['revision'],created['next_ordinal']),('open',1,0))
        self.assertNotIn('audio',created_response.json())

        audio=fixture.wav(1600);append_id=str(uuid.uuid4())
        first_response=self.append(created,request_id=append_id,audio=audio)
        self.assertEqual(first_response.status_code,200,first_response.text);self.assert_private(first_response)
        first=first_response.json();self.assertEqual((first['revision'],first['ordinal'],first['section_count']),(2,0,1))

        # A new client/app instance reopens the generated SQLite file before
        # recovering status and replaying the response-lost append.
        reopened=self.build();self.addCleanup(reopened.close)
        path=self.session_path(created['session_id'])
        status_response=self.request('GET',path,client=reopened)
        self.assertEqual(status_response.status_code,200,status_response.text);self.assert_private(status_response)
        status=status_response.json()
        self.assertEqual((status['state'],status['revision'],status['section_count'],status['next_ordinal'],
                          status['retention_consent'],status['processing_consent']),
                         ('open',2,1,1,True,False))
        self.assertNotIn('audio',status)
        cookie_headers={'Cookie':f'{COOKIE}={self.member}','Origin':'https://photohouse.test',
            'Sec-Fetch-Site':'same-origin','X-CSRF-Token':csrf_token(self.member)}
        cookie_status=reopened.get(path,headers=cookie_headers)
        self.assertEqual(cookie_status.status_code,200,'the protected cookie path remains usable for current status')
        self.assert_private(cookie_status)
        replay=self.append(created,request_id=append_id,audio=audio)
        self.assertEqual(replay.status_code,200,replay.text);self.assertEqual(replay.json(),first)
        self.assertEqual(self.counts(),(1,1,2),'an exact retry after reopen adds no section or receipt')

        next_response=self.append(first,request_id=str(uuid.uuid4()),audio=fixture.wav(3200))
        self.assertEqual(next_response.status_code,200,next_response.text)
        next_section=next_response.json()
        self.assertEqual((next_section['revision'],next_section['ordinal'],next_section['section_count']), (3,1,2))
        refreshed=self.request('GET',path,client=reopened).json()
        self.assertEqual((refreshed['section_count'],refreshed['next_ordinal'],refreshed['total_frames']),(2,2,4800))
        self.assertEqual(self.counts(),(1,2,3))

        closed=self.request('POST',path+'/complete',body={'request_id':str(uuid.uuid4()),'expected_revision':3})
        self.assertEqual(closed.status_code,200,closed.text);self.assertEqual(closed.json()['state'],'completed')
        self.assert_private(closed)

    def test_declined_consent_is_empty_and_typed_json_is_strict(self):
        before=self.counts();body=self.create_body(retention_consent=False)
        declined=self.request('POST','/oral-history/v1/libraries/family-a/sessions',body=body)
        self.assertEqual(declined.status_code,422,declined.text);self.assert_private(declined)
        self.assertEqual(self.counts(),before,'declined retention creates no session, section, or receipt')
        cookie_headers={'Cookie':f'{COOKIE}={self.member}','Origin':'https://photohouse.test',
            'Sec-Fetch-Site':'same-origin','X-CSRF-Token':csrf_token(self.member)}
        cookie_declined=self.client.post('/oral-history/v1/libraries/family-a/sessions',
            json=body,headers=cookie_headers)
        self.assertEqual(cookie_declined.status_code,422,'same-origin cookie mutation succeeds through CSRF validation')
        bad_csrf=self.client.post('/oral-history/v1/libraries/family-a/sessions',
            json=body,headers=cookie_headers|{'X-CSRF-Token':'0'*64})
        self.assertEqual(bad_csrf.status_code,403,'cookie mutations require the existing CSRF token')
        self.assertEqual(self.counts(),before)
        malformed=self.create_body(retention_consent=1)
        invalid=self.request('POST','/oral-history/v1/libraries/family-a/sessions',body=malformed)
        self.assertEqual(invalid.status_code,400,invalid.text);self.assertEqual(self.counts(),before)
        raw='{"request_id":"'+str(uuid.uuid4())+'","request_id":"'+str(uuid.uuid4())+'"}'
        duplicate=self.request('POST','/oral-history/v1/libraries/family-a/sessions',content=raw,
            headers={'Content-Type':'application/json'})
        self.assertEqual(duplicate.status_code,400);self.assertEqual(self.counts(),before)

    def test_open_session_collection_is_author_and_library_scoped_resume_status(self):
        collection='/oral-history/v1/libraries/{}/sessions'
        member_body=self.create_body()
        created=self.request('POST',collection.format('family-a'),body=member_body).json()
        self.append(created,request_id=str(uuid.uuid4()),audio=fixture.wav(800))

        owner_created=self.request('POST',collection.format('family-a'),body=self.create_body(),
            headers={'Authorization':'Bearer '+self.owner}).json()
        cancelled_record=self.request('POST',collection.format('family-a'),body=self.create_body()).json()
        cancelled=self.request('POST',self.session_path(cancelled_record['session_id'])+'/cancel',
            body={'request_id':str(uuid.uuid4()),'expected_revision':1})
        self.assertEqual(cancelled.status_code,200,cancelled.text)
        other_library=self.request('POST',collection.format('family-b'),body=self.create_body())
        self.assertEqual(other_library.status_code,201,other_library.text)
        other_library_id=other_library.json()['session_id']

        reopened=self.build();self.addCleanup(reopened.close)
        listed_response=self.request('GET',collection.format('family-a'),client=reopened)
        self.assertEqual(listed_response.status_code,200,listed_response.text);self.assert_private(listed_response)
        listing=listed_response.json()
        self.assertEqual((listing['version'],listing['library_id']),(2,'family-a'))
        self.assertEqual([item['session_id'] for item in listing['items']],[created['session_id']],
            'open-session collection hides another author, another library, and cancelled sessions')
        status=listing['items'][0]
        self.assertEqual(set(status),STATUS_FIELDS,'the collection returns only the established bounded status DTO')
        self.assertEqual((status['section_count'],status['next_ordinal'],status['revision']),(1,1,2))
        self.assertFalse({'audio','sources','transcript','original_text'} & set(status))

        resumed=self.append(status,request_id=str(uuid.uuid4()),audio=fixture.wav(1200))
        self.assertEqual(resumed.status_code,200,resumed.text)
        self.assertEqual((resumed.json()['ordinal'],resumed.json()['revision']),(1,3))
        self.assertEqual([item['session_id'] for item in self.request('GET',collection.format('family-b')).json()['items']],
                         [other_library_id])

        owner_listing=self.request('GET',collection.format('family-a'),
            headers={'Authorization':'Bearer '+self.owner}).json()
        self.assertEqual([item['session_id'] for item in owner_listing['items']],[owner_created['session_id']],
            'library owners list only their own recordings')
        with closing(self.connect()) as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
                       (self.base.actor,));db.commit()
        revoked=self.request('GET',collection.format('family-a'))
        self.assertEqual(revoked.status_code,401,'revoked authors cannot discover their sessions')
        with closing(self.connect()) as db:
            db.execute("UPDATE access_memberships SET status='approved' WHERE account_id=? AND library_id='family-a'",
                       (self.base.actor,))
            db.execute("UPDATE access_accounts SET state='disabled' WHERE id=?",(self.base.actor,));db.commit()
        disabled=self.request('GET',collection.format('family-a'))
        self.assertEqual(disabled.status_code,401,'disabled accounts cannot discover their sessions')

    def test_completed_collection_reuses_bounded_author_status(self):
        collection='/oral-history/v1/libraries/{}/sessions/completed'
        own=self.completed_record(audio=fixture.wav(800))
        other_author=self.completed_record(token=self.owner)
        other_library=self.completed_record(library='family-b')
        open_record=self.request('POST','/oral-history/v1/libraries/family-a/sessions',
            body=self.create_body()).json()
        cancelled=self.request('POST',self.session_path(open_record['session_id'])+'/cancel',
            body={'request_id':str(uuid.uuid4()),'expected_revision':1})
        self.assertEqual(cancelled.status_code,200,cancelled.text)

        reopened=self.build();self.addCleanup(reopened.close)
        response=self.request('GET',collection.format('family-a'),client=reopened)
        self.assertEqual(response.status_code,200,response.text);self.assert_private(response)
        listing=response.json()
        self.assertEqual((listing['version'],listing['library_id']),(2,'family-a'))
        self.assertEqual([item['session_id'] for item in listing['items']],[own['session_id']])
        item=listing['items'][0]
        self.assertEqual(set(item),STATUS_FIELDS)
        self.assertEqual((item['state'],item['revision'],item['section_count']),('completed',3,1))
        self.assertFalse({'audio','sources','transcript','original_text'} & set(item))
        family_b=self.request('GET',collection.format('family-b')).json()
        self.assertEqual([item['session_id'] for item in family_b['items']],[other_library['session_id']])
        owner=self.request('GET',collection.format('family-a'),
            headers={'Authorization':'Bearer '+self.owner}).json()
        self.assertEqual([item['session_id'] for item in owner['items']],[other_author['session_id']])

    def test_completed_section_is_revision_pinned_author_only_and_verified(self):
        audio=fixture.wav(1600)
        completed=self.completed_record(audio=audio)
        path=self.session_path(completed['session_id'])+'/sections/0'
        headers={'X-PhotoHouse-Expected-Revision':str(completed['revision'])}
        response=self.request('GET',path,headers=headers)
        self.assertEqual(response.status_code,200,response.text);self.assert_private(response)
        self.assertEqual(response.content,audio)
        self.assertEqual(response.headers['content-type'],'audio/wav')
        self.assertEqual(response.headers['content-length'],str(len(audio)))

        stale=self.request('GET',path,headers={'X-PhotoHouse-Expected-Revision':str(completed['revision']-1)})
        self.assertEqual(stale.status_code,409)
        for bad_headers in ({}, {'X-PhotoHouse-Expected-Revision':'0'},
                            {'X-PhotoHouse-Expected-Revision':'03'}):
            invalid=self.request('GET',path,headers=bad_headers)
            self.assertEqual(invalid.status_code,400)
        duplicate=self.client.get(path,headers=[('Authorization','Bearer '+self.member),
            ('X-PhotoHouse-Expected-Revision',str(completed['revision'])),
            ('X-PhotoHouse-Expected-Revision',str(completed['revision']))])
        self.assertEqual(duplicate.status_code,400,'expected revision must appear exactly once')
        for ordinal in ('00','180','-1'):
            invalid=self.request('GET',self.session_path(completed['session_id'])+f'/sections/{ordinal}',
                headers=headers)
            self.assertEqual(invalid.status_code,400,ordinal+': '+invalid.text)

        owner=self.request('GET',path,headers={'Authorization':'Bearer '+self.owner} | headers)
        self.assertEqual(owner.status_code,401,'library owner cannot read another author’s audio')
        cross_library=self.request('GET',f'/oral-history/v1/libraries/family-b/sessions/{completed["session_id"]}/sections/0',
            headers=headers)
        self.assertEqual(cross_library.status_code,401)

        open_record=self.request('POST','/oral-history/v1/libraries/family-a/sessions',
            body=self.create_body()).json()
        open_audio=self.request('GET',self.session_path(open_record['session_id'])+'/sections/0',
            headers={'X-PhotoHouse-Expected-Revision':'1'})
        self.assertEqual(open_audio.status_code,409,'open sessions are never exposed through completed-source reads')

        with closing(self.connect()) as db:
            db.execute(f"UPDATE {SESSION} SET state='withdrawn',withdrawn_from='completed',"
                       "withdrawal_request_id=?,withdrawal_request_digest=?,revision=revision+1 WHERE id=?",
                       (str(uuid.uuid4()),'a'*64,completed['session_id']));db.commit()
        withdrawn=self.request('GET',path,headers=headers)
        self.assertEqual(withdrawn.status_code,401,'withdrawn source is hidden')

    def test_completed_section_checks_blob_length_before_loading_audio(self):
        completed=self.completed_record(audio=fixture.wav(800))
        path=self.session_path(completed['session_id'])+'/sections/0'
        headers={'X-PhotoHouse-Expected-Revision':str(completed['revision'])}
        trigger=next(sql for sql in STATEMENTS if 'CREATE TRIGGER oral_history_section_update ' in sql)
        with closing(self.connect()) as db:
            db.execute('DROP TRIGGER oral_history_section_update')
            db.execute('PRAGMA ignore_check_constraints=ON')
            db.execute(f'UPDATE {SECTION} SET audio=zeroblob(byte_count+1) WHERE session_id=? AND ordinal=0',
                       (completed['session_id'],))
            db.execute(trigger)
            db.commit()
        original_one=AccessService._one
        raw_reads=[]
        def note_raw_read(service, sql, args):
            if sql.lstrip().lower().startswith('select audio from'):
                raw_reads.append(sql)
            return original_one(service,sql,args)
        with patch.object(AccessService,'_one',note_raw_read):
            corrupt=self.request('GET',path,headers=headers)
        self.assertEqual(corrupt.status_code,503,'blob length is checked against the manifest before Python loads audio')
        self.assertEqual(corrupt.json(),{'detail':'Recording source unavailable'})
        self.assertEqual(raw_reads,[])

    def test_completed_section_requires_current_library_permission(self):
        completed=self.completed_record(audio=fixture.wav(800))
        path=self.session_path(completed['session_id'])+'/sections/0'
        headers={'X-PhotoHouse-Expected-Revision':str(completed['revision'])}
        with closing(self.connect()) as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
                       (self.base.actor,));db.commit()
        revoked=self.request('GET',path,headers=headers)
        self.assertEqual(revoked.status_code,401)

    def test_author_scope_revocation_and_default_route_remain_closed(self):
        created=self.request('POST','/oral-history/v1/libraries/family-a/sessions',body=self.create_body()).json()
        args={'request_id':str(uuid.uuid4()),'expected_revision':1,'ordinal':0,'audio':fixture.wav()}
        owner_headers={'Authorization':'Bearer '+self.owner,
            'X-PhotoHouse-Request-Id':args['request_id'],'X-PhotoHouse-Expected-Revision':'1',
            'X-PhotoHouse-Ordinal':'0','Content-Type':'audio/wav'}
        owner=self.client.post(self.session_path(created['session_id'])+'/sections',
            content=args['audio'],headers=owner_headers)
        self.assertEqual(owner.status_code,401,'library owner cannot read another author’s source')
        cross_library=self.request('GET',f"/oral-history/v1/libraries/family-b/sessions/{created['session_id']}")
        self.assertEqual(cross_library.status_code,401)
        with closing(self.connect()) as db:
            db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
                       (self.base.actor,));db.commit()
        with patch('app.access.oral_history_transport._audio_body',
                   new=AsyncMock(side_effect=AssertionError('revoked audio body must not be read'))):
            denied=self.append(created,request_id=args['request_id'],audio=args['audio'])
        self.assertEqual(denied.status_code,401)
        self.assertEqual(self.counts(),(1,0,1),'revoked author cannot append source bytes')

        off=self.build(enabled=False)
        self.addCleanup(off.close)
        response=self.request('POST','/oral-history/v1/libraries/family-a/sessions',body=self.create_body(),client=off)
        self.assertEqual(response.status_code,403,'default app does not mount the oral-history routes')
        listing=self.request('GET','/oral-history/v1/libraries/family-a/sessions',client=off)
        self.assertEqual(listing.status_code,403,'the open-session discovery method is also absent by default')
        completed=self.request('GET','/oral-history/v1/libraries/family-a/sessions/completed',client=off)
        self.assertEqual(completed.status_code,403,'completed-session discovery remains default-off')
        section=self.request('GET',self.session_path(created['session_id'])+'/sections/0',
            headers={'X-PhotoHouse-Expected-Revision':'2'},client=off)
        self.assertEqual(section.status_code,403,'completed-section reads remain default-off')
        with self.assertRaises(ValueError):
            create_app(oral_history_intake_enabled=True)

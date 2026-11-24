"""Generated HTTP coverage for default-off, resumable author-private intake."""
from contextlib import closing, contextmanager
import uuid
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

import test_oral_history_intake as fixture
from app.main import create_app
from app.access.oral_history_schema import SESSION, SECTION, MUTATION
from app.access.transport import AccessRuntime, COOKIE, csrf_token


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

    def build(self, *, enabled=True):
        return TestClient(create_app(access_runtime=self.runtime,
            oral_history_intake_enabled=enabled), base_url='https://photohouse.test',
            client=('192.0.2.30', 24567))

    def request(self, method, path, *, body=None, content=None, headers=None, client=None):
        return (client or self.client).request(method, path,
            headers={'Authorization':'Bearer '+self.member} | (headers or {}),
            json=body, content=content)

    def create_body(self, **changes):
        return self.base.body(processing_consent=False, **changes)

    @staticmethod
    def session_path(ident):
        return f'/oral-history/v1/libraries/family-a/sessions/{ident}'

    def append(self, record, *, request_id, audio=None):
        headers={'X-PhotoHouse-Request-Id':request_id,
            'X-PhotoHouse-Expected-Revision':str(record['revision']),
            'X-PhotoHouse-Ordinal':str(record['next_ordinal']), 'Content-Type':'audio/wav'}
        return self.request('POST', self.session_path(record['session_id'])+'/sections',
            content=audio if audio is not None else fixture.wav(), headers=headers)

    def counts(self):
        with closing(self.connect()) as db:
            return tuple(db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                         for table in (SESSION, SECTION, MUTATION))

    def assert_private(self, response):
        self.assertEqual(response.headers.get('cache-control'), 'no-store')
        self.assertEqual(response.headers.get('pragma'), 'no-cache')

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
        with self.assertRaises(ValueError):
            create_app(oral_history_intake_enabled=True)

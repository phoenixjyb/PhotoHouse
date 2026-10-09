"""Protected contribution review and deletion against synthetic stories only."""

import io
import json
import uuid
import wave
import unittest

import test_library_reads as fixture
from app.access.memory_contributions import MemoryContributions
from app.access.service import AccessDenied, AccessService
from app.access.transport import TransportError


class MemoryContributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.LibraryReadTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.LibraryReadTests.tearDownClass()

    def setUp(self):
        self.f = fixture.LibraryReadTests(); self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.story = self._make_story()
        self.viewer = self.f.member_token

    def _make_story(self):
        response = self.f.client.post('/story-workspace/preview?library=family-a',
            headers={'Authorization': 'Bearer ' + self.f.owner_token},
            json={'asset_ids': '101,102', 'title': '家庭相册', 'theme': 'everyday', 'language': 'zh'})
        self.assertEqual(response.status_code, 200, response.text)
        draft = response.json()
        chapter = draft['chapters'][0] | {'narration': '这一天我们一起散步。'}
        body = {'title': draft['title'], 'theme': draft['theme'], 'language': 'zh',
            'asset_ids': '101,102', 'chapters': json.dumps([chapter]),
            'selection_revision': draft['selection_revision'], 'revision': '0',
            'mutation_id': str(uuid.uuid4())}
        response = self.f.client.post('/memory-stories?library=family-a',
            headers={'Authorization': 'Bearer ' + self.f.owner_token}, json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['id']

    def call(self, method, *args):
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            return getattr(MemoryContributions(access), method)(*args)

    def body(self, **updates):
        return {'kind': 'text', 'text': '奶奶记得那天的阳光。', 'language': 'zh',
            'byline': '家人', 'consent': '1', 'chapter_id': 'chapter-1',
            'revision': '1', 'mutation_id': str(uuid.uuid4())} | updates

    def create(self, token=None, body=None, audio=None):
        return self.call('create', token or self.viewer, 'family-a', self.story,
                         body or self.body(), audio)

    @staticmethod
    def wav(rate=16000, channels=1, width=2, frames=1600):
        out = io.BytesIO()
        with wave.open(out, 'wb') as target:
            target.setnchannels(channels); target.setsampwidth(width); target.setframerate(rate)
            target.writeframes(b'\0' * frames * channels * width)
        return out.getvalue()

    def test_viewer_can_contribute_but_cannot_review_and_owner_accepts(self):
        contribution = self.create()
        self.assertEqual(contribution['state'], 'pending')
        self.assertEqual(contribution['text'], '奶奶记得那天的阳光。')
        self.assertEqual(self.call('list', self.viewer, 'family-a', self.story, 1)['items'][0]['id'],
                         contribution['id'])
        with self.assertRaises(AccessDenied):
            self.call('review', self.viewer, 'family-a', self.story, contribution['id'], 'accepted', 1)
        accepted = self.call('review', self.f.owner_token, 'family-a', self.story,
                             contribution['id'], 'accepted', 1)
        self.assertEqual(accepted['state'], 'accepted')
        owner_detail = self.call('get', self.f.owner_token, 'family-a', self.story, contribution['id'])
        self.assertEqual(owner_detail['derivation']['state'], 'waiting')
        with self.assertRaises(TransportError):
            self.call('review', self.f.owner_token, 'family-a', self.story,
                      contribution['id'], 'accepted', 1)
        with self.f.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM access_memory_contribution_derivations WHERE contribution_id=?", (contribution['id'],)).fetchone()[0], 1)
        self.assertEqual(self.call('get', self.viewer, 'family-a', self.story,
                                   contribution['id'])['state'], 'accepted')

    def test_accepted_is_visible_to_other_current_library_readers(self):
        contribution = self.create()
        self.call('review', self.f.owner_token, 'family-a', self.story,
                  contribution['id'], 'accepted', 1)
        with self.f.connection() as db:
            access = AccessService(db, clock=lambda: self.f.now)
            code = access.invite(self.f.owner_token, 'family-a', '+12025550104')
            other = access.register('+12025550104', fixture.PASSWORD, code, 'Another Reader')
        visible = self.call('list', other, 'family-a', self.story, 1)
        self.assertEqual(visible['items'][0]['id'], contribution['id'])
        self.assertEqual(visible['items'][0]['author_id'], fixture.LibraryReadTests.member_id)
        self.assertFalse(visible['can_review'])

    def test_consent_off_does_not_queue_and_owner_sees_other_pending(self):
        first = self.create(body=self.body(consent='0'))
        self.assertEqual(self.call('get', self.f.owner_token, 'family-a', self.story,
                                   first['id'])['derivation'], None)
        self.assertEqual(len(self.call('list', self.f.owner_token, 'family-a', self.story, 1)['items']), 1)

    def test_decline_cancels_existing_lease_and_outputs(self):
        item = self.create()
        with self.f.connection() as db:
            db.execute("INSERT INTO access_memory_contribution_derivations(contribution_id,revision,state,transcript,polished_text,tags,lease_id,lease_until,created_at,updated_at) VALUES(?,1,'running','private transcript','private proposal','[\"tag\"]','lease',?, ?,?)",
                       (item['id'], self.f.now + 120, self.f.now, self.f.now))
            db.commit()
        self.call('review', self.f.owner_token, 'family-a', self.story, item['id'], 'declined', 1)
        with self.f.connection() as db:
            derivation = db.execute("SELECT state,transcript,polished_text,tags,lease_id,lease_until FROM access_memory_contribution_derivations WHERE contribution_id=?", (item['id'],)).fetchone()
        self.assertEqual(tuple(derivation), ('cancelled', None, None, '[]', None, None))

    def test_retry_is_idempotent_after_parent_revision_changes_and_bad_reuse_conflicts(self):
        body = self.body()
        first = self.create(body=body)
        self.f.mutate("UPDATE access_memory_stories SET revision=revision+1 WHERE id=?", (self.story,))
        retried = self.create(body=body)
        self.assertEqual(retried['id'], first['id'])
        with self.assertRaises(TransportError) as caught:
            self.create(body=body | {'text': 'different'})
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(TransportError) as stale:
            self.create(body=self.body(revision='1'))
        self.assertEqual(stale.exception.status, 409)

    def test_accepted_original_is_immutable_and_review_uses_parent_revision_cas(self):
        item = self.create()
        self.f.mutate("UPDATE access_memory_stories SET revision=revision+1 WHERE id=?", (self.story,))
        with self.assertRaises(TransportError) as stale:
            self.call('review', self.f.owner_token, 'family-a', self.story, item['id'], 'accepted', 1)
        self.assertEqual(stale.exception.status, 409)
        self.call('review', self.f.owner_token, 'family-a', self.story, item['id'], 'accepted', 2)
        current = self.call('get', self.f.owner_token, 'family-a', self.story, item['id'])
        self.assertEqual(current['text'], '奶奶记得那天的阳光。')
        with self.assertRaises(TransportError):
            self.call('review', self.f.owner_token, 'family-a', self.story,
                      item['id'], 'declined', 2)

    def test_audio_is_validated_and_only_authorized_bytes_are_returned(self):
        payload = self.wav()
        item = self.create(body=self.body(kind='audio', text='', chapter_id=''), audio=payload)
        self.assertEqual(item['duration_ms'], 100)
        self.assertEqual(self.call('audio', self.viewer, 'family-a', self.story, item['id']), payload)
        with self.assertRaises(TransportError):
            self.create(body=self.body(kind='audio', text=''), audio=self.wav(channels=2))
        with self.assertRaises(AccessDenied):
            self.call('audio', self.f.other_token, 'family-a', self.story, item['id'])

    def test_text_unicode_limits_and_current_chapter_are_enforced(self):
        self.assertEqual(self.create(body=self.body(text='a' * 8192))['state'], 'pending')
        for invalid in ('', 'x' * 8193, 'bad\x00text', 'bad\x7ftext', '\ud800'):
            with self.subTest(invalid=repr(invalid)):
                with self.assertRaises(TransportError):
                    self.create(body=self.body(text=invalid))
        with self.assertRaises(TransportError):
            self.create(body=self.body(chapter_id='chapter-2'))

    def test_moved_media_and_revoked_membership_hide_all_contributions(self):
        item = self.create()
        self.f.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101")
        with self.assertRaises(AccessDenied):
            self.call('get', self.viewer, 'family-a', self.story, item['id'])
        with self.assertRaises(AccessDenied):
            self.call('list', self.f.owner_token, 'family-a', self.story, 1)
        self.f.mutate("UPDATE access_asset_libraries SET library_id='family-a' WHERE asset_id=101")
        self.f.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=?",
                      (fixture.LibraryReadTests.member_id,))
        with self.assertRaises(AccessDenied):
            self.call('get', self.viewer, 'family-a', self.story, item['id'])

    def test_owner_delete_clears_proposals_audio_derivations_and_audits(self):
        item = self.create()
        self.call('review', self.f.owner_token, 'family-a', self.story, item['id'], 'accepted', 1)
        with self.f.connection() as db:
            owner_id = AccessService(db, clock=lambda: self.f.now).profile(self.f.owner_token)['account_id']
            db.execute("INSERT INTO access_memory_conversations(id,library_id,actor_id,story_id,created_at,expires_at) VALUES('conv','family-a',?,?,?,?)",
                       (fixture.LibraryReadTests.member_id, self.story, self.f.now, self.f.now + 3600))
            db.execute("INSERT INTO access_memory_jobs(id,library_id,actor_id,story_id,conversation_id,kind,state,mutation_id,request_digest,base_revision,source_fingerprint,input_json,output_json,created_at,updated_at,expires_at) VALUES('job','family-a',? ,?,'conv','chat','running','job-mutation','digest',1,'fingerprint','{\"raw\":\"private\"}','{\"reply\":\"private\"}',?,?,?)",
                       (fixture.LibraryReadTests.member_id, self.story, self.f.now,
                        self.f.now + 1, self.f.now + 3600))
            db.execute("INSERT INTO access_memory_turns(id,conversation_id,sequence,mutation_id,request_digest,input_text,reply_text,reply_kind,job_id,created_at) VALUES('turn','conv',1,'turn-mutation','digest','Question','private reply','text','job',2)")
            db.execute("INSERT INTO access_memory_books(id,library_id,author_id,revision,content,created_at,updated_at) VALUES('book','family-a',?,1,?,1,2)",
                       (owner_id, json.dumps({'story_ids': [self.story]})))
            db.execute("INSERT INTO access_memory_conversations(id,library_id,actor_id,book_id,created_at,expires_at) VALUES('book-conv','family-a',?,'book',?,?)",
                       (fixture.LibraryReadTests.member_id, self.f.now, self.f.now + 3600))
            db.execute("INSERT INTO access_memory_jobs(id,library_id,actor_id,book_id,conversation_id,kind,state,mutation_id,request_digest,base_revision,source_fingerprint,input_json,output_json,created_at,updated_at,expires_at) VALUES('book-job','family-a',?,'book','book-conv','narrative','ready','book-job-mutation','digest',1,'fingerprint','{\"raw\":\"private\"}','{\"reply\":\"private\"}',?,?,?)",
                       (fixture.LibraryReadTests.member_id, self.f.now,
                        self.f.now + 1, self.f.now + 3600))
            db.execute("INSERT INTO access_memory_turns(id,conversation_id,sequence,mutation_id,request_digest,input_text,reply_text,reply_kind,job_id,created_at) VALUES('book-turn','book-conv',1,'book-turn-mutation','digest','Question','private book reply','text','book-job',2)")
            db.commit()
        with self.assertRaises(AccessDenied):
            self.call('delete', self.viewer, 'family-a', self.story, item['id'])
        self.assertEqual(self.call('delete', self.f.owner_token, 'family-a', self.story, item['id']),
                         {'deleted': True, 'id': item['id']})
        with self.f.connection() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM access_memory_contributions WHERE id=?", (item['id'],)).fetchone()[0], 0)
            job = db.execute("SELECT state,input_json,output_json,lease_id FROM access_memory_jobs WHERE id='job'").fetchone()
            self.assertEqual(tuple(job), ('cancelled', '{}', None, None))
            self.assertEqual(db.execute("SELECT reply_text,reply_kind FROM access_memory_turns WHERE id='turn'").fetchone(), (None, None))
            book_job = db.execute("SELECT state,input_json,output_json FROM access_memory_jobs WHERE id='book-job'").fetchone()
            self.assertEqual(tuple(book_job), ('ready', '{}', None))
            self.assertEqual(db.execute("SELECT reply_text,reply_kind FROM access_memory_turns WHERE id='book-turn'").fetchone(), (None, None))
            self.assertEqual(db.execute("SELECT action FROM access_audit WHERE action='memory.contribution_delete' ORDER BY rowid DESC LIMIT 1").fetchone()[0], 'memory.contribution_delete')


if __name__ == '__main__': unittest.main()

"""Synthetic authorization and original-retention checks for upload annotations."""
from contextlib import closing
import hashlib
import io
import sqlite3
import sys
import unittest
import uuid
import wave
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
import test_promotion as fixture_module
from app.main import create_app
from app.access.annotation_processing import process_one, retry_failed


def wav_bytes():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b'\0\0' * 16000)
    return buffer.getvalue()


class UploadAnnotationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture_module.PromotionTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture_module.PromotionTests.tearDownClass()

    def setUp(self):
        self.fixture = fixture_module.PromotionTests(
            'test_promotion_moves_the_file_and_makes_the_photo_visible')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.client = TestClient(create_app(access_runtime=self.fixture.access,
                                            upload_runtime=self.fixture.uploads,
                                            annotation_intake_enabled=True),
                                 base_url='https://photohouse.test', client=('192.0.2.44', 24567))
        self.addCleanup(self.client.close)
        self.batch = '4' * 32
        self.raw = fixture_module.png(640, 501)
        self.asset = int(self.fixture.uploads.store(
            self.fixture.member_token, self.raw, 'family.png', self.batch, 'family-a')['asset_id'])

    def headers(self, token):
        return {'Authorization': 'Bearer ' + token}

    def text(self, content, *, asset='', mutation=None, consent='yes', token=None):
        return self.client.post('/upload-annotations/text?library=family-a',
            headers=self.headers(token or self.fixture.member_token), json={
                'batch': self.batch, 'asset_id': asset, 'language': 'en',
                'consent': consent, 'mutation_id': mutation or str(uuid.uuid4()),
                'text': content})

    def list(self, token=None, library='family-a'):
        return self.client.get(f'/upload-annotations?library={library}&asset_id={self.asset}',
                               headers=self.headers(token or self.fixture.member_token))

    def review_tag(self, identifier, tag, *, token=None, asset=None, revision='1', decision='accepted'):
        return self.client.post('/admin/upload-annotation-tags/review?library=family-a',
            headers=self.headers(token or self.fixture.owner_token), json={
                'asset_id': str(asset or self.asset), 'annotation_id': identifier,
                'revision': revision, 'tag': tag, 'decision': decision})

    def proposed_tags(self, token=None, page='1'):
        return self.client.get('/admin/upload-annotation-tags?library=family-a&page=' + page,
                               headers=self.headers(token or self.fixture.owner_token))

    def delete_note(self, note, *, token=None, digest=None, asset=None, library='family-a'):
        return self.client.post('/admin/upload-annotations/delete?library=' + library,
            headers=self.headers(token or self.fixture.owner_token), json={
                'asset_id': str(asset or self.asset), 'annotation_id': note['id'],
                'sha256': digest or note['sha256']})

    def test_intake_is_closed_by_default_but_reads_stay_available(self):
        closed = TestClient(create_app(access_runtime=self.fixture.access,
                                      upload_runtime=self.fixture.uploads),
                            base_url='https://photohouse.test')
        self.addCleanup(closed.close)
        text_response = closed.post('/upload-annotations/text?library=family-a',
                                    headers=self.headers(self.fixture.member_token), content=b'bad')
        audio_response = closed.post('/upload-annotations/audio?library=family-a',
                                     headers=self.headers(self.fixture.member_token), content=wav_bytes())
        self.assertEqual(503, text_response.status_code)
        self.assertEqual(503, audio_response.status_code)
        listing = closed.get(
            f'/upload-annotations?library=family-a&asset_id={self.asset}',
            headers=self.headers(self.fixture.member_token)).json()
        self.assertEqual(0, listing['total'])
        self.assertIs(listing['intake_enabled'], False)

    def test_owner_deletion_waits_for_running_local_processing(self):
        note = self.text('A note awaiting local processing.', asset=str(self.asset)).json()
        with closing(sqlite3.connect(self.fixture.path)) as db:
            db.execute("UPDATE access_annotation_derivations SET state='running' WHERE annotation_id=?",
                       (note['id'],))
            db.commit()
        self.assertEqual(409, self.delete_note(note).status_code)
        self.assertEqual(1, self.list().json()['total'])

    def test_only_owner_can_erase_original_and_all_derivations(self):
        text_note = self.text('Please keep this exact memory.', asset=str(self.asset)).json()
        audio_note = self.client.post('/upload-annotations/audio?library=family-a',
            headers={**self.headers(self.fixture.member_token), 'Content-Type': 'audio/wav',
                'X-Annotation-Batch': self.batch, 'X-Annotation-Asset-Id': str(self.asset),
                'X-Annotation-Language': 'en', 'X-Local-Processing-Consent': 'yes',
                'X-Annotation-Mutation-Id': str(uuid.uuid4())}, content=wav_bytes()).json()
        member_delete = self.delete_note(text_note, token=self.fixture.member_token)
        self.assertEqual(401, member_delete.status_code, member_delete.text)
        self.assertEqual(409, self.delete_note(text_note, digest='0' * 64).status_code)
        self.assertEqual(401, self.delete_note(text_note, library='family-b').status_code)
        self.assertEqual(2, self.list().json()['total'])
        for note in (text_note, audio_note):
            erased = self.delete_note(note)
            self.assertEqual(200, erased.status_code, erased.text)
            self.assertEqual(note['id'], erased.json()['annotation_id'])
        self.assertEqual(0, self.list().json()['total'])
        with closing(sqlite3.connect(self.fixture.path)) as db:
            for table in ('access_upload_annotations', 'access_annotation_derivations',
                          'access_annotation_tag_proposals'):
                self.assertEqual(0, db.execute('SELECT count(*) FROM ' + table).fetchone()[0])
            self.assertEqual(2, db.execute("SELECT count(*) FROM access_audit WHERE action='annotation.delete'").fetchone()[0])

    def test_processing_summary_uses_latest_revision_and_selected_item_scope(self):
        second_asset = int(self.fixture.uploads.store(
            self.fixture.member_token, fixture_module.png(641, 501), 'second.png',
            self.batch, 'family-a')['asset_id'])
        folder = self.text('The whole batch.')
        first = self.text('First item.', asset=str(self.asset))
        second = self.text('Second item.', asset=str(second_asset), consent='no')
        for response in (folder, first, second):
            self.assertEqual(201, response.status_code, response.text)
        with closing(sqlite3.connect(self.fixture.path)) as db:
            db.execute("UPDATE access_annotation_derivations SET state='completed' WHERE annotation_id=?",
                       (first.json()['id'],))
            db.execute('''INSERT INTO access_annotation_derivations
                (annotation_id,revision,state,created_at,updated_at)
                VALUES (?,2,'failed',2,2)''', (first.json()['id'],))
            db.commit()
        selected = self.list().json()
        self.assertEqual(2, selected['total'])
        self.assertEqual({'held': 0, 'waiting': 1, 'running': 0,
                          'completed': 0, 'failed': 1, 'dead': 0},
                         selected['processing_summary'])
        later_page = self.client.get(
            f'/upload-annotations?library=family-a&asset_id={self.asset}&page=2',
            headers=self.headers(self.fixture.member_token)).json()
        self.assertEqual([], later_page['items'])
        self.assertEqual(selected['processing_summary'], later_page['processing_summary'])
        other = self.client.get(
            f'/upload-annotations?library=family-a&asset_id={second_asset}',
            headers=self.headers(self.fixture.member_token)).json()
        self.assertEqual(2, other['total'])
        self.assertEqual(1, other['processing_summary']['held'])
        self.assertEqual(0, other['processing_summary']['failed'])

    def test_folder_and_item_text_remain_distinct_and_originals_are_immutable(self):
        folder = self.text('We celebrated together.')
        item = self.text('The blue cake was handmade.', asset=str(self.asset))
        self.assertEqual(201, folder.status_code, folder.text)
        self.assertEqual(201, item.status_code, item.text)
        self.assertEqual('folder', folder.json()['scope'])
        self.assertEqual('item', item.json()['scope'])
        self.assertEqual('We celebrated together.', folder.json()['original_text'])
        self.assertEqual('waiting', folder.json()['derivation']['state'])
        listing = self.list()
        self.assertEqual(200, listing.status_code, listing.text)
        self.assertEqual(2, listing.json()['total'])
        self.assertEqual(self.batch, listing.json()['batch'])
        self.assertEqual({'folder', 'item'}, {row['scope'] for row in listing.json()['items']})
        with closing(sqlite3.connect(self.fixture.path)) as db:
            with self.assertRaises(sqlite3.DatabaseError):
                db.execute('UPDATE access_upload_annotations SET original_text=? WHERE id=?',
                           ('changed', folder.json()['id']))

    def test_idempotent_mutation_and_later_policy_do_not_rewrite_original(self):
        mutation = str(uuid.uuid4())
        first = self.text('Keep these exact words.', mutation=mutation, consent='no')
        retry = self.text('Keep these exact words.', mutation=mutation, consent='no')
        changed = self.text('Different words.', mutation=mutation, consent='no')
        self.assertEqual(201, first.status_code, first.text)
        self.assertEqual(first.json()['id'], retry.json()['id'])
        self.assertEqual('held', first.json()['derivation']['state'])
        self.assertEqual(409, changed.status_code, changed.text)
        self.assertEqual(1, self.list().json()['total'])

    def test_bounded_wav_is_in_database_and_served_only_with_current_scope(self):
        raw = wav_bytes()
        mutation = str(uuid.uuid4())
        headers = {**self.headers(self.fixture.member_token),
            'Content-Type': 'audio/wav', 'X-Annotation-Batch': self.batch,
            'X-Annotation-Asset-Id': str(self.asset), 'X-Annotation-Language': 'en',
            'X-Local-Processing-Consent': 'yes', 'X-Annotation-Mutation-Id': mutation}
        created = self.client.post('/upload-annotations/audio?library=family-a',
                                   headers=headers, content=raw)
        self.assertEqual(201, created.status_code, created.text)
        note = created.json()
        self.assertEqual('audio', note['kind'])
        self.assertEqual(1000, note['duration_ms'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), note['sha256'])
        with closing(sqlite3.connect(self.fixture.path)) as db:
            self.assertEqual(raw, db.execute('''SELECT original_audio FROM access_upload_annotations
                WHERE id=?''', (note['id'],)).fetchone()[0])
        heard = self.client.get(note['audio_url'], headers=self.headers(self.fixture.member_token))
        self.assertEqual(200, heard.status_code, heard.text)
        self.assertEqual(raw, heard.content)
        self.assertEqual(401, self.client.get(note['audio_url'],
            headers=self.headers(self.fixture.other_token)).status_code)
        bad = self.client.post('/upload-annotations/audio?library=family-a',
            headers={**headers, 'X-Annotation-Mutation-Id': str(uuid.uuid4())}, content=b'not a recording')
        self.assertEqual(422, bad.status_code, bad.text)

    def test_pending_reviewer_then_assigned_members_can_read_but_not_foreign_library(self):
        note = self.text('Only this family can see it.')
        self.assertEqual(201, note.status_code, note.text)
        self.assertEqual(200, self.list(self.fixture.owner_token).status_code)
        self.assertEqual(401, self.list(self.fixture.other_token).status_code)
        self.assertEqual(401, self.text('Owner cannot impersonate uploader.',
            token=self.fixture.owner_token).status_code)
        self.fixture.mutate('''INSERT INTO access_memberships
            (account_id,library_id,status,role,revision,expires_at,originals,approved_by)
            VALUES (?,'family-a','approved','viewer',1,NULL,0,?)''',
            (self.fixture.other_id, self.fixture.owner_id))
        # A nonoperator pending reader who is merely a member is still denied.
        self.assertEqual(401, self.list(self.fixture.other_token).status_code)
        envelope = self.fixture.planned('promote', library_id='family-a',
            operator_account_id=self.fixture.owner_id, asset_ids=[self.asset])
        from app.access.promotion import promote_and_assign
        promote_and_assign(envelope, review=self.fixture.review(envelope),
                           clock=lambda: fixture_module.NOW)
        self.assertEqual(200, self.list(self.fixture.other_token).status_code)
        self.assertEqual(401, self.list(self.fixture.other_token, 'family-b').status_code)

    def test_local_derivation_keeps_original_and_proposes_reviewable_tags(self):
        note = self.text('  We had a lovely birthday.  ')
        self.assertEqual(201, note.status_code)
        with closing(sqlite3.connect(self.fixture.path)) as db:
            result = process_one(db, transcribe=lambda *_: self.fail('Text must not use ASR'),
                polish=lambda text, language: {'text': text.strip(), 'tags': ['birthday', 'family'],
                    'provider': 'windows-local', 'model': 'synthetic'}, clock=lambda: fixture_module.NOW)
            self.assertEqual({'id': note.json()['id'], 'state': 'completed'}, result)
            original, state, wording = db.execute('''SELECT a.original_text,d.state,d.polished_text
                FROM access_upload_annotations a JOIN access_annotation_derivations d ON d.annotation_id=a.id
                WHERE a.id=?''', (note.json()['id'],)).fetchone()
            self.assertEqual('  We had a lovely birthday.  ', original)
            self.assertEqual(('completed', 'We had a lovely birthday.'), (state, wording))
        item = self.list().json()['items'][0]
        self.assertEqual('  We had a lovely birthday.  ', item['original_text'])
        self.assertEqual(['birthday', 'family'], [tag['tag'] for tag in item['tags']])
        self.assertEqual({'proposed'}, {tag['status'] for tag in item['tags']})

    def test_owner_reviews_current_tag_and_only_assigned_library_asset_is_searchable(self):
        note = self.text('A vivid birthday memory.', asset=str(self.asset))
        self.assertEqual(201, note.status_code, note.text)
        identifier = note.json()['id']
        with closing(sqlite3.connect(self.fixture.path)) as db:
            processed = process_one(db, transcribe=lambda *_: self.fail('Text must not use ASR'),
                polish=lambda text, language: {'text': text, 'tags': ['birthday', 'private-skip'],
                    'provider': 'windows-local', 'model': 'synthetic'}, clock=lambda: fixture_module.NOW)
            self.assertEqual({'id': identifier, 'state': 'completed'}, processed)
        self.assertEqual(401, self.review_tag(identifier, 'birthday',
            token=self.fixture.member_token).status_code)
        self.assertEqual(401, self.review_tag(str(uuid.uuid4()), 'birthday').status_code)
        self.assertEqual(409, self.review_tag(identifier, 'birthday', revision='2').status_code)
        accepted = self.review_tag(identifier, 'birthday')
        self.assertEqual(200, accepted.status_code, accepted.text)
        self.assertEqual('accepted', accepted.json()['status'])
        self.assertEqual(accepted.json(), self.review_tag(identifier, 'birthday').json())
        self.assertEqual(200, self.review_tag(identifier, 'private-skip',
            decision='rejected').status_code)
        self.assertEqual(409, self.review_tag(identifier, 'private-skip').status_code)
        def search(word, library='family-a', source='all'):
            return self.client.post('/library/search?library=' + library,
                headers=self.headers(self.fixture.member_token), json={
                    'text': word, 'source': source, 'media': 'all', 'page': '1'})
        self.assertEqual(0, search('birthday').json()['total'])  # still pending
        envelope = self.fixture.planned('promote', library_id='family-a',
            operator_account_id=self.fixture.owner_id, asset_ids=[self.asset])
        from app.access.promotion import promote_and_assign
        promote_and_assign(envelope, review=self.fixture.review(envelope),
                           clock=lambda: fixture_module.NOW)
        found = search('birthday')
        self.assertEqual(200, found.status_code, found.text)
        self.assertEqual([str(self.asset)], [item['id'] for item in found.json()['items']])
        self.assertEqual('family', found.json()['items'][0]['match']['source'])
        self.assertEqual(1, search('A vivid birthday memory.', source='family').json()['total'])
        self.assertEqual(0, search('birthday', source='ai').json()['total'])
        self.assertEqual(0, search('private-skip').json()['total'])
        family_tags = self.client.get('/family-tags?library=family-a',
            headers=self.headers(self.fixture.member_token))
        self.assertEqual(200, family_tags.status_code, family_tags.text)
        self.assertEqual([{'name': 'birthday', 'asset_count': 1}], family_tags.json()['items'])
        self.assertEqual(401, self.client.get('/family-tags?library=family-a',
            headers=self.headers(self.fixture.other_token)).status_code)
        tagged = self.client.post('/family-tags/assets?library=family-a',
            headers=self.headers(self.fixture.member_token), json={'tag': 'birthday', 'page': '1'})
        self.assertEqual(200, tagged.status_code, tagged.text)
        self.assertEqual([str(self.asset)], [item['id'] for item in tagged.json()['items']])
        self.assertEqual(401, self.client.post('/family-tags/assets?library=family-a',
            headers=self.headers(self.fixture.other_token),
            json={'tag': 'birthday', 'page': '1'}).status_code)
        self.assertEqual(401, self.client.post('/family-tags/assets?library=family-a',
            headers=self.headers(self.fixture.member_token),
            json={'tag': 'private-skip', 'page': '1'}).status_code)
        self.assertEqual('accepted', next(tag for tag in self.list().json()['items'][0]['tags']
            if tag['tag'] == 'birthday')['status'])
        self.fixture.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=?",
                            (self.asset,))
        self.assertEqual(0, search('birthday').json()['total'])
        self.assertEqual(0, self.client.get('/family-tags?library=family-a',
            headers=self.headers(self.fixture.member_token)).json()['total'])

    def test_accepted_folder_tag_fans_out_only_to_assigned_batch_items(self):
        second = int(self.fixture.uploads.store(self.fixture.member_token,
            fixture_module.png(642, 503), 'second.png', self.batch, 'family-a')['asset_id'])
        note = self.text('The entire picnic batch.')
        identifier = note.json()['id']
        with closing(sqlite3.connect(self.fixture.path)) as db:
            process_one(db, transcribe=lambda *_: self.fail('Text must not use ASR'),
                polish=lambda text, language: {'text': text, 'tags': ['picnic'],
                    'provider': 'windows-local', 'model': 'synthetic'}, clock=lambda: fixture_module.NOW)
        self.assertEqual(200, self.review_tag(identifier, 'picnic').status_code)
        envelope = self.fixture.planned('promote', library_id='family-a',
            operator_account_id=self.fixture.owner_id, asset_ids=[self.asset, second])
        from app.access.promotion import promote_and_assign
        promote_and_assign(envelope, review=self.fixture.review(envelope),
                           clock=lambda: fixture_module.NOW)
        result = self.client.post('/library/search?library=family-a',
            headers=self.headers(self.fixture.member_token),
            json={'text': 'picnic', 'source': 'family', 'media': 'image', 'page': '1'})
        self.assertEqual(200, result.status_code, result.text)
        self.assertEqual({str(self.asset), str(second)},
                         {item['id'] for item in result.json()['items']})
        folder_words = self.client.post('/library/search?library=family-a',
            headers=self.headers(self.fixture.member_token),
            json={'text': 'The entire picnic batch.', 'source': 'family',
                  'media': 'image', 'page': '1'}).json()
        self.assertEqual({str(self.asset), str(second)},
                         {item['id'] for item in folder_words['items']})
        catalog = self.client.get('/family-tags?library=family-a',
            headers=self.headers(self.fixture.member_token)).json()
        self.assertEqual([{'name': 'picnic', 'asset_count': 2}], catalog['items'])
        assets = self.client.post('/family-tags/assets?library=family-a',
            headers=self.headers(self.fixture.member_token),
            json={'tag': 'picnic', 'page': '1'}).json()
        self.assertEqual({str(self.asset), str(second)},
                         {item['id'] for item in assets['items']})
        duplicate_note = self.text('Another picnic detail.', asset=str(second))
        with closing(sqlite3.connect(self.fixture.path)) as db:
            process_one(db, transcribe=lambda *_: self.fail('Text must not use ASR'),
                polish=lambda text, language: {'text': text, 'tags': ['picnic'],
                    'provider': 'windows-local', 'model': 'synthetic'},
                clock=lambda: fixture_module.NOW)
        self.assertEqual(200, self.review_tag(duplicate_note.json()['id'], 'picnic',
            asset=second).status_code)
        self.assertEqual(2, self.client.get('/family-tags?library=family-a',
            headers=self.headers(self.fixture.member_token)).json()['items'][0]['asset_count'])

    def test_owner_inbox_shows_current_assigned_proposals_and_source(self):
        note = self.text('Original words stay here.', asset=str(self.asset))
        identifier = note.json()['id']
        with closing(sqlite3.connect(self.fixture.path)) as db:
            process_one(db, transcribe=lambda *_: self.fail('Text must not use ASR'),
                polish=lambda text, language: {'text': 'Gentle polished words.',
                    'tags': ['garden'], 'provider': 'windows-local', 'model': 'synthetic'},
                clock=lambda: fixture_module.NOW)
        self.assertEqual(401, self.proposed_tags(self.fixture.member_token).status_code)
        self.assertEqual(0, self.proposed_tags().json()['total'])  # incoming stays private
        envelope = self.fixture.planned('promote', library_id='family-a',
            operator_account_id=self.fixture.owner_id, asset_ids=[self.asset])
        from app.access.promotion import promote_and_assign
        promote_and_assign(envelope, review=self.fixture.review(envelope),
                           clock=lambda: fixture_module.NOW)
        inbox = self.proposed_tags()
        self.assertEqual(200, inbox.status_code, inbox.text)
        self.assertEqual(1, inbox.json()['total'])
        item = inbox.json()['items'][0]
        self.assertEqual({'annotation_id': identifier, 'batch': self.batch,
            'asset_id': str(self.asset), 'scope': 'item', 'kind': 'text',
            'original_text': 'Original words stay here.', 'created_at': fixture_module.NOW,
            'transcript': None, 'polished_text': 'Gentle polished words.', 'revision': 1,
            'tag': 'garden', 'audio_url': None}, item)
        self.assertEqual(200, self.review_tag(identifier, 'garden').status_code)
        self.assertEqual(0, self.proposed_tags().json()['total'])

    def test_audio_derivation_and_consent_hold(self):
        held = self.text('Keep this private.', consent='no')
        raw = wav_bytes()
        audio = self.client.post('/upload-annotations/audio?library=family-a',
            headers={**self.headers(self.fixture.member_token), 'Content-Type': 'audio/wav',
                'X-Annotation-Batch': self.batch, 'X-Annotation-Asset-Id': str(self.asset),
                'X-Annotation-Language': 'en', 'X-Local-Processing-Consent': 'yes',
                'X-Annotation-Mutation-Id': str(uuid.uuid4())}, content=raw)
        self.assertEqual(201, audio.status_code, audio.text)
        with closing(sqlite3.connect(self.fixture.path)) as db:
            processed = process_one(db, transcribe=lambda data, language: {
                'text': 'Grandma sang.', 'provider': 'windows-asr', 'model': 'synthetic-asr'},
                polish=lambda text, language: {'text': 'Grandma sang at the party.',
                    'tags': ['grandma'], 'provider': 'windows-llm', 'model': 'synthetic-llm'},
                clock=lambda: fixture_module.NOW)
            self.assertEqual(audio.json()['id'], processed['id'])
            self.assertIsNone(process_one(db, transcribe=lambda *_: self.fail('Held note processed'),
                polish=lambda *_: self.fail('Held note processed'), clock=lambda: fixture_module.NOW))
            self.assertEqual(raw, db.execute('SELECT original_audio FROM access_upload_annotations WHERE id=?',
                (audio.json()['id'],)).fetchone()[0])
        listing = self.list().json()['items']
        self.assertEqual('held', next(row for row in listing if row['id'] == held.json()['id'])['derivation']['state'])
        self.assertEqual('Grandma sang.', next(row for row in listing if row['id'] == audio.json()['id'])['derivation']['transcript'])
        envelope = self.fixture.planned('promote', library_id='family-a',
            operator_account_id=self.fixture.owner_id, asset_ids=[self.asset])
        from app.access.promotion import promote_and_assign
        promote_and_assign(envelope, review=self.fixture.review(envelope),
                           clock=lambda: fixture_module.NOW)
        inbox = self.proposed_tags().json()['items']
        self.assertEqual(1, len(inbox))
        self.assertEqual('Grandma sang.', inbox[0]['transcript'])
        self.assertEqual('Grandma sang at the party.', inbox[0]['polished_text'])
        self.assertIsNone(inbox[0]['original_text'])
        self.assertEqual(raw, self.client.get(inbox[0]['audio_url'],
            headers=self.headers(self.fixture.owner_token)).content)
        self.assertEqual(401, self.client.get(inbox[0]['audio_url']).status_code)
        for phrase in ('Grandma sang.', 'Grandma sang at the party.', 'Keep this private.'):
            result = self.client.post('/library/search?library=family-a',
                headers=self.headers(self.fixture.member_token),
                json={'text': phrase, 'source': 'family', 'media': 'all', 'page': '1'})
            self.assertEqual(200, result.status_code, result.text)
            self.assertEqual([str(self.asset)], [item['id'] for item in result.json()['items']])

    def test_processing_rechecks_membership_before_saving_derived_words(self):
        note = self.text('Only while I am a member.')
        self.assertEqual(201, note.status_code, note.text)
        def revoke_during_processing(text, language):
            self.fixture.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id=? AND library_id='family-a'",
                                (self.fixture.member_id,))
            return {'text': text, 'tags': ['family'], 'provider': 'windows-local', 'model': 'synthetic'}
        with closing(sqlite3.connect(self.fixture.path)) as db:
            result = process_one(db, transcribe=lambda *_: self.fail('Text must not use ASR'),
                polish=revoke_during_processing, clock=lambda: fixture_module.NOW)
            self.assertEqual({'id': note.json()['id'], 'state': 'dead'}, result)
            self.assertEqual(('dead', None), tuple(db.execute('''SELECT state,polished_text
                FROM access_annotation_derivations WHERE annotation_id=?''',
                (note.json()['id'],)).fetchone()))
            self.assertEqual([], db.execute('SELECT tag FROM access_annotation_tag_proposals').fetchall())

    def test_moved_item_cannot_receive_an_old_destination_note(self):
        self.fixture.mutate('''INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (?,'family-b')''',
                            (self.asset,))
        self.fixture.mutate("UPDATE access_uploads SET state='assigned' WHERE asset_id=?", (self.asset,))
        self.assertEqual(401, self.text('Old item note.', asset=str(self.asset)).status_code)
        self.assertEqual(401, self.text('Old folder note.').status_code)
        self.assertEqual(401, self.list().status_code)

    def test_failed_local_derivation_has_an_explicit_versioned_retry(self):
        note = self.text('A story from the garden.')
        self.assertEqual(201, note.status_code, note.text)
        identifier = note.json()['id']
        with closing(sqlite3.connect(self.fixture.path)) as db:
            failed = process_one(db, transcribe=lambda *_: self.fail('Text must not use ASR'),
                polish=lambda *_: (_ for _ in ()).throw(RuntimeError('Synthetic model offline')),
                clock=lambda: fixture_module.NOW)
            self.assertEqual({'id': identifier, 'state': 'failed'}, failed)
            self.assertEqual({'id': identifier, 'revision': 2, 'state': 'waiting'},
                             retry_failed(db, identifier, clock=lambda: fixture_module.NOW))
            completed = process_one(db, transcribe=lambda *_: self.fail('Text must not use ASR'),
                polish=lambda text, language: {'text': 'A garden memory.', 'tags': ['garden'],
                    'provider': 'windows-local', 'model': 'synthetic'},
                clock=lambda: fixture_module.NOW)
            self.assertEqual({'id': identifier, 'state': 'completed'}, completed)
            self.assertEqual([(1, 'failed'), (2, 'completed')], [tuple(row) for row in db.execute('''
                SELECT revision,state FROM access_annotation_derivations
                WHERE annotation_id=? ORDER BY revision''', (identifier,))])
            self.assertEqual('A story from the garden.', db.execute('''SELECT original_text
                FROM access_upload_annotations WHERE id=?''', (identifier,)).fetchone()[0])


if __name__ == '__main__':
    unittest.main()

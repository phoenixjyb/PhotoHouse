"""Private memory conversation and proposal lifecycle against synthetic data."""
import json
import unittest
import uuid
from unittest.mock import patch

import test_memory_books as fixture
from app.access.memory_jobs import MemoryJobs, RETENTION, context
from app.access.service import AccessDenied, AccessService
from app.access.stories import Stories
from app.access.transport import TransportError


class MemoryJobTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture.MemoryBookTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        fixture.MemoryBookTests.tearDownClass()

    def setUp(self):
        self.f = fixture.MemoryBookTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.library = self.f.library_fixture
        self.owner = self.f.owner
        self.member = self.f.member
        self.story_id = self.f.story('Companion target')

    def call(self, method, token, *args, **kwargs):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            return getattr(MemoryJobs(access), method)(token, 'family-a', *args, **kwargs)

    def start(self, token=None, *, target_type='story', target_id=None, ident=None):
        return self.call('start', token or self.member, target_type,
                         target_id or self.story_id, ident or str(uuid.uuid4()))

    def send(self, conversation, message='Tell me about this day.', *, token=None,
             revision='1', mutation=None):
        return self.call('send', token or self.member, conversation, revision,
                         mutation or str(uuid.uuid4()), message)

    def narrative(self, *, target_type='story', target_id=None, token=None,
                  revision='1', mutation=None, instructions=''):
        return self.call('narrative', token or self.owner, target_type,
                         target_id or self.story_id, revision,
                         mutation or str(uuid.uuid4()), instructions)

    def mark_ready(self, ident, *, output=None):
        output = output or {'version': 1, 'reply': 'A reviewed suggestion.', 'source_ids': []}
        with self.library.connection() as db:
            db.execute("""UPDATE access_memory_jobs SET state='ready',output_json=?,
                lease_id=NULL,lease_until=NULL,updated_at=? WHERE id=?""",
                (json.dumps(output, ensure_ascii=False), self.library.now, ident))
            db.commit()

    def turn_rows(self, conversation):
        with self.library.connection() as db:
            return db.execute('''SELECT sequence,mutation_id,input_text,reply_text,reply_kind,job_id
                FROM access_memory_turns WHERE conversation_id=? ORDER BY sequence''',
                (conversation,)).fetchall()

    def test_conversation_is_private_actor_scoped_and_viewer_chat_is_allowed(self):
        conversation = self.start()
        self.assertEqual(conversation['target_type'], 'story')
        self.assertEqual(conversation['target_id'], self.story_id)
        self.assertEqual(conversation['expires_at'] - self.library.now, RETENTION)
        with self.assertRaises(AccessDenied):
            self.call('turns', self.owner, conversation['id'], 1)
        with self.assertRaises(AccessDenied):
            self.send(conversation['id'], token=self.owner)

        owner_conversation = self.start(self.owner, ident=str(uuid.uuid4()))
        self.assertEqual(self.call('turns', self.owner, owner_conversation['id'], 1)['items'], [])
        with self.assertRaises(AccessDenied):
            self.call('turns', self.member, owner_conversation['id'], 1)
        with self.assertRaises(AccessDenied):
            self.start(self.library.other_token, ident=str(uuid.uuid4()))

    def test_conversation_history_lists_only_actor_current_unexpired_parents(self):
        first=self.start()
        second=self.start(self.owner,ident=str(uuid.uuid4()))
        member_history=self.call('conversations',self.member,'story',self.story_id)
        owner_history=self.call('conversations',self.owner,'story',self.story_id)
        self.assertEqual([item['id'] for item in member_history['items']],[first['id']])
        self.assertEqual([item['id'] for item in owner_history['items']],[second['id']])
        self.library.mutate('UPDATE access_memory_conversations SET created_at=?,expires_at=? WHERE id=?',
                            (self.library.now-RETENTION,self.library.now,first['id']))
        self.assertEqual(self.call('conversations',self.member,'story',self.story_id)['items'],[])
        self.library.mutate('UPDATE access_asset_libraries SET library_id=\'family-b\' WHERE asset_id=101')
        with self.assertRaises(AccessDenied):
            self.call('conversations',self.owner,'story',self.story_id)

    def test_conversation_previews_are_opt_in_bounded_first_turn_and_scope_checked(self):
        member_thread=self.start()
        first='  <b>第一条回忆</b>\n继续 😊  '+'后'*100
        first_job=self.send(member_thread['id'],first)
        self.mark_ready(first_job['id'])
        self.send(member_thread['id'],'A later message must not replace the preview')
        legacy=self.call('conversations',self.member,'story',self.story_id)
        self.assertEqual(set(legacy['items'][0]),{'id','created_at','expires_at'})
        preview=self.call('conversations',self.member,'story',self.story_id,preview=True)
        normalized=' '.join(first.split())
        self.assertEqual(preview['items'][0]['first_message_preview'],normalized[:80])
        self.assertEqual(len(preview['items'][0]['first_message_preview']),80)
        self.assertIn('<b>',preview['items'][0]['first_message_preview'])
        self.library.mutate('UPDATE access_memory_turns SET input_text=? WHERE conversation_id=? AND sequence=1',
                            ('a'*79+' b',member_thread['id']))
        clipped=self.call('conversations',self.member,'story',self.story_id,preview=True)['items'][0]['first_message_preview']
        self.assertEqual(clipped,'a'*79)
        self.assertFalse(clipped.endswith(' '),'clipped previews remove a trailing canonical separator')
        self.library.mutate('UPDATE access_memory_turns SET input_text=? WHERE conversation_id=? AND sequence=1',
                            ('legacy\x00control',member_thread['id']))
        self.assertEqual(self.call('conversations',self.member,'story',self.story_id,preview=True)['items'][0]['first_message_preview'],'')

        empty_owner_thread=self.start(self.owner,ident=str(uuid.uuid4()))
        owner_preview=self.call('conversations',self.owner,'story',self.story_id,preview=True)
        self.assertEqual(owner_preview['items'][0]['id'],empty_owner_thread['id'])
        self.assertEqual(owner_preview['items'][0]['first_message_preview'],'')
        self.assertEqual(self.call('conversations',self.owner,'story',self.story_id,preview=True)['items'][0]['first_message_preview'],'')
        self.assertEqual(self.call('conversations',self.member,'story',self.story_id,preview=True)['items'][0]['id'],member_thread['id'])

        book_story=self.f.story('Book preview child',assets='102')
        book=self.f.domain('save',self.owner,self.f.body([book_story],title='Book preview isolation'))
        book_thread=self.start(self.member,target_type='book',target_id=book['id'],ident=str(uuid.uuid4()))
        book_job=self.send(book_thread['id'],'This message belongs only to the book target.')
        self.mark_ready(book_job['id'])
        book_preview=self.call('conversations',self.member,'book',book['id'],preview=True)
        self.assertEqual([(item['id'],item['first_message_preview']) for item in book_preview['items']],
                         [(book_thread['id'],'This message belongs only to the book target.')])
        self.assertEqual([item['id'] for item in self.call('conversations',self.member,'story',self.story_id,preview=True)['items']],
                         [member_thread['id']])

        other_story=self.f.story('Another protected target')
        self.assertEqual(self.call('conversations',self.member,'story',other_story,preview=True)['items'],[])
        self.library.mutate("UPDATE access_memory_conversations SET library_id='family-b' WHERE id=?",(member_thread['id'],))
        self.assertEqual(self.call('conversations',self.member,'story',self.story_id,preview=True)['items'],[])
        self.library.mutate('UPDATE access_memory_conversations SET library_id=\'family-a\',created_at=?,expires_at=? WHERE id=?',
                            (self.library.now-1,self.library.now,member_thread['id']))
        self.assertEqual(self.call('conversations',self.member,'story',self.story_id,preview=True)['items'],[])
        self.library.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101")
        with self.assertRaises(AccessDenied):
            self.call('conversations',self.member,'story',self.story_id,preview=True)

    def test_viewer_can_chat_but_cannot_start_narrative_write(self):
        conversation = self.start()
        job = self.send(conversation['id'])
        self.assertEqual((job['kind'], job['state']), ('chat', 'queued'))
        with self.assertRaises(AccessDenied):
            self.narrative(token=self.member)
        owner_job = self.narrative()
        self.assertEqual((owner_job['kind'], owner_job['state']), ('narrative', 'queued'))

    def test_turns_are_ordered_pending_turn_serializes_and_retry_does_not_append(self):
        conversation = self.start()
        mutation = str(uuid.uuid4())
        first = self.send(conversation['id'], 'First thought', mutation=mutation)
        self.assertEqual(first['state'], 'queued')
        retried = self.send(conversation['id'], 'First thought', mutation=mutation)
        self.assertEqual(retried['id'], first['id'])
        with self.assertRaises(TransportError) as reused:
            self.send(conversation['id'], 'Changed thought', mutation=mutation)
        self.assertEqual(reused.exception.status, 409)
        with self.assertRaises(TransportError) as pending:
            self.send(conversation['id'], 'Second thought')
        self.assertEqual(pending.exception.status, 409)
        self.assertEqual(len(self.turn_rows(conversation['id'])), 1)

        self.mark_ready(first['id'])
        second = self.send(conversation['id'], 'Second thought')
        self.assertEqual(second['state'], 'queued')
        turns = self.call('turns', self.member, conversation['id'], 1)['items']
        self.assertEqual([turn['sequence'] for turn in turns], [1, 2])
        self.assertEqual([turn['input_text'] for turn in turns], ['First thought', 'Second thought'])
        self.assertEqual([turn['job_id'] for turn in turns], [first['id'], second['id']])

    def test_recent_history_pages_resume_latest_turn_and_preserve_legacy_order(self):
        conversation = self.start()
        jobs = []
        for sequence in range(1, 36):
            job = self.send(conversation['id'], f'Thought {sequence}')
            jobs.append(job['id'])
            if sequence < 35:
                self.mark_ready(job['id'])
        legacy = self.call('turns', self.member, conversation['id'], 1)
        self.assertEqual([item['sequence'] for item in legacy['items']], list(range(1, 17)))
        self.assertTrue(legacy['has_more'])
        pages = [self.call('turns', self.member, conversation['id'], page,
                          reply_context=True, recent_first=True) for page in (1, 2, 3)]
        self.assertEqual([[item['sequence'] for item in page['items']] for page in pages],
                         [list(range(20, 36)), list(range(4, 20)), [1, 2, 3]])
        self.assertEqual([page['has_more'] for page in pages], [True, True, False])
        self.assertEqual((pages[0]['items'][-1]['job_id'], pages[0]['items'][-1]['state']),
                         (jobs[-1], 'queued'))
        self.assertEqual(len({item['id'] for page in pages for item in page['items']}), 35)
        self.assertTrue(all('reply_questions' in item for page in pages for item in page['items']))
        self.assertEqual(self.call('turns', self.member, conversation['id'], 4,
                                   recent_first=True)['items'], [])
        with self.assertRaises(AccessDenied):
            self.call('turns', self.owner, conversation['id'], 1, recent_first=True)
        with self.assertRaises(TransportError) as invalid:
            self.call('turns', self.member, conversation['id'], 1, recent_first=1)
        self.assertEqual(invalid.exception.status, 400)
        self.mark_ready(jobs[-1])
        newest = self.send(conversation['id'], 'Thought 36')
        refreshed = self.call('turns', self.member, conversation['id'], 1, recent_first=True)
        self.assertEqual([item['sequence'] for item in refreshed['items']], list(range(21, 37)))
        self.assertEqual(refreshed['items'][-1]['job_id'], newest['id'])

    def test_expiry_denies_reads_and_start_prunes_expired_conversation_and_job(self):
        conversation = self.start()
        job = self.send(conversation['id'], 'Will expire')
        expired_created = self.library.now - RETENTION + 1
        self.library.mutate('UPDATE access_memory_conversations SET created_at=?,expires_at=? WHERE id=?',
                            (expired_created, self.library.now - 1, conversation['id']))
        self.library.mutate('UPDATE access_memory_jobs SET created_at=?,updated_at=?,expires_at=? WHERE id=?',
                            (expired_created, expired_created + 1, self.library.now - 1, job['id']))
        with self.assertRaises(AccessDenied):
            self.call('turns', self.member, conversation['id'], 1)
        with self.assertRaises(AccessDenied):
            self.call('get', self.member, job['id'])
        fresh = self.start()
        self.assertNotEqual(fresh['id'], conversation['id'])
        with self.library.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_conversations WHERE id=?',
                                        (conversation['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_jobs WHERE id=?',
                                        (job['id'],)).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM access_memory_turns WHERE conversation_id=?',
                                        (conversation['id'],)).fetchone()[0], 0)

    def ready_chat_with_metadata(self):
        conversation = self.start()
        job = self.send(conversation['id'])
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            member = access._require(self.member, 'family-a', 'library.read')
            bundle, _, _ = context(access, 'family-a', member, 'story', self.story_id)
        result = {'version': 1, 'kind': 'answer', 'reply': 'A cautious answer.',
                  'source_ids': [bundle['sources'][0]['id']],
                  'questions': ['Who else remembers this moment?'], 'proposal': None}
        self.mark_ready(job['id'], output=result)
        self.library.mutate('UPDATE access_memory_turns SET reply_text=?,reply_kind=? WHERE job_id=?',
                            (result['reply'], result['kind'], job['id']))
        return conversation, job, result

    def test_history_rehydrates_reviewed_reply_questions_and_current_source_ids(self):
        conversation, _, result = self.ready_chat_with_metadata()
        turn = self.call('turns', self.member, conversation['id'], 1, reply_context=True)['items'][0]
        self.assertEqual(turn['reply_text'], result['reply'])
        self.assertEqual(turn['reply_questions'], result['questions'])
        self.assertEqual(turn['reply_source_ids'], result['source_ids'])
        self.assertNotIn('proposal', turn)
        self.assertNotIn('sources', turn)
        legacy = self.call('turns', self.member, conversation['id'], 1)['items'][0]
        self.assertNotIn('reply_source_ids', legacy)
        self.assertNotIn('reply_questions', legacy)
        with self.assertRaises(AccessDenied):
            self.call('turns', self.owner, conversation['id'], 1)

    def test_history_metadata_refuses_bad_references_bounds_and_mismatched_reply(self):
        conversation, job, result = self.ready_chat_with_metadata()
        for changes in ({'source_ids': ['foreign-source']},
                        {'questions': ['too many'] * 4},
                        {'questions': ['长' * 200]},
                        {'reply': 'A different turn'}, {'kind': 'clarification'},
                        {'extra': 'not a companion field'}):
            with self.subTest(changes=changes):
                self.mark_ready(job['id'], output={**result, **changes})
                turn = self.call('turns', self.member, conversation['id'], 1, reply_context=True)['items'][0]
                self.assertEqual(turn['reply_text'], result['reply'])
                self.assertEqual(turn['reply_questions'], [])
                self.assertEqual(turn['reply_source_ids'], [])
        for raw in ('{invalid', '{"version":1,"version":1}', '[' * 1100 + '0' + ']' * 1100):
            self.library.mutate('UPDATE access_memory_jobs SET output_json=? WHERE id=?', (raw, job['id']))
            turn = self.call('turns', self.member, conversation['id'], 1, reply_context=True)['items'][0]
            self.assertEqual(turn['reply_questions'], [])
            self.assertEqual(turn['reply_source_ids'], [])

    def test_history_clears_reply_metadata_on_changed_expired_or_foreign_job(self):
        for mutation, parameters in (
            ("UPDATE captions SET text='changed-source' WHERE id=101", ()),
            ('UPDATE access_memory_jobs SET created_at=?,expires_at=? WHERE id=?', ('expired',)),
            ('UPDATE access_memory_jobs SET actor_id=? WHERE id=?', ('other',)),
            ('UPDATE access_memory_jobs SET conversation_id=? WHERE id=?', ('other-conversation',)),
            ('UPDATE access_memory_jobs SET story_id=? WHERE id=?', ('other-story',)),
        ):
            with self.subTest(mutation=mutation):
                conversation, job, _ = self.ready_chat_with_metadata()
                params = parameters
                if parameters:
                    if parameters[0] == 'expired':
                        params = (self.library.now - RETENTION, self.library.now, job['id'])
                    elif parameters[0] == 'other':
                        with self.library.connection() as db:
                            access = AccessService(db, clock=lambda: self.library.now)
                            actor = access._require(self.owner, 'family-a', 'library.read')['account_id']
                        params = (actor, job['id'])
                    elif parameters[0] == 'other-story':
                        params = (self.f.story('Other companion target'), job['id'])
                    else:
                        params = (self.start()['id'], job['id'])
                self.library.mutate(mutation, params)
                turn = self.call('turns', self.member, conversation['id'], 1, reply_context=True)['items'][0]
                self.assertEqual(turn['state'], 'stale')
                self.assertIsNone(turn['reply_text'])
                self.assertEqual(turn['reply_questions'], [])
                self.assertEqual(turn['reply_source_ids'], [])

    def test_narrative_uses_expected_story_revision_and_job_has_no_source_copy(self):
        instructions = 'Keep the family wording.'
        job = self.narrative(instructions=instructions)
        self.assertEqual(job['base_revision'], '1')
        with self.library.connection() as db:
            stored = db.execute('SELECT input_json,source_fingerprint FROM access_memory_jobs WHERE id=?',
                                 (job['id'],)).fetchone()
        self.assertEqual(json.loads(stored[0]), {'instructions': instructions})
        self.assertNotIn('private-child-source-', stored[0])
        self.assertTrue(stored[1])

        self.library.mutate('UPDATE access_memory_stories SET revision=revision+1 WHERE id=?',
                            (self.story_id,))
        with self.assertRaises(TransportError) as stale:
            self.narrative(revision='1')
        self.assertEqual(stale.exception.status, 409)

    def test_context_keeps_family_transcript_and_editorial_provenance_distinct(self):
        class Rows:
            def fetchone(self):
                return ('uuid', 'Grandpa', 1)

            def fetchall(self):
                return [
                    ('contribution-audio', 'chapter-1', 'audio', None, 'hash',
                     'Grandma', 'We planted tulips.', None, 1, 'ready'),
                    ('contribution-text', 'chapter-1', 'text', 'I wrote this memory.', 'hash',
                     'Aunt', None, None, 1, None),
                ]

        class DB:
            def execute(self, sql, *_args):
                if 'alembic_version' in sql:
                    return type('VersionRows', (), {'fetchall': lambda self: []})()
                return Rows()

        detail = {'id': 'story-uuid', 'revision': '1', 'items': [
            {'id': 'asset-1', 'evidence': [
                {'id': 'family-uuid', 'source': 'family', 'text': 'I remember spring.', 'revision': 1},
                {'id': 'caption-1', 'source': 'ai', 'text': 'A garden caption.'}]}],
            'chapters': [{'id': 'chapter-1', 'title': 'Planting day',
                          'narration': 'The saved editorial draft.',
                          'asset_ids': ['asset-1']} ]}
        stored = {'title': 'Spring', 'language': 'en', 'theme': 'everyday'}
        with patch('app.access.memory_jobs.parent', return_value=(
                {'content': '{}', 'revision': 1}, [detail], True, stored)):
            bundle, _, _ = context(type('Access', (), {'db': DB()})(), 'library-a',
                                   {'account_id': 'member'}, 'story', 'story-uuid')

        by_id = {source['id']: source for source in bundle['sources']}
        self.assertEqual(by_id['family-uuid']['kind'], 'family')
        self.assertEqual(by_id['family-uuid']['author'], 'Grandpa')
        self.assertEqual(by_id['caption-1']['kind'], 'ai')
        self.assertEqual(by_id['contribution-contribution-audio']['kind'], 'transcript')
        self.assertEqual(by_id['contribution-contribution-audio']['author'], 'Grandma')
        self.assertEqual(by_id['contribution-contribution-text']['kind'], 'family')
        self.assertEqual(by_id['editorial-story-uuid-chapter-1']['kind'], 'editorial')
        self.assertEqual(set(bundle['chapters'][0]['evidence_ids']), set(by_id))
        self.assertFalse(any(source['kind'] == 'metadata' for source in bundle['sources']))

    def test_asset_note_authorship_is_current_scoped_and_changes_job_fingerprint(self):
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            note = Stories(access).save(self.owner, 'family-a', {
                'title': 'Planting day', 'text': 'We planted the roses together.',
                'language': 'en', 'byline': '奶奶', 'mutation_id': str(uuid.uuid4()),
            }, asset_id=102)
            with access._transaction():
                member = access._require(self.member, 'family-a', 'library.read')
                before, fingerprint_before, _ = context(access, 'family-a', member,
                                                        'story', self.story_id)
        source_id = 'family-' + note['id']
        sources = {item['id']: item for item in before['sources']}
        self.assertEqual(sources[source_id]['author'], '奶奶')
        self.assertEqual(sources[source_id]['kind'], 'family')
        self.assertNotIn('account_id', sources[source_id])
        self.assertNotIn('author_id', sources[source_id])
        queued = self.narrative()
        # Same-revision corruption also changes the dependency fingerprint; a
        # source label is not taken only from the truncated item projection.
        self.library.mutate('UPDATE access_stories SET byline=? WHERE id=?', ('姥姥', note['id']))
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            with access._transaction():
                member = access._require(self.member, 'family-a', 'library.read')
                after, fingerprint_after, _ = context(access, 'family-a', member,
                                                      'story', self.story_id)
        self.assertEqual(next(item for item in after['sources'] if item['id']==source_id)['author'], '姥姥')
        self.assertNotEqual(fingerprint_before, fingerprint_after)
        self.mark_ready(queued['id'])
        result = self.call('get', self.owner, queued['id'])
        self.assertEqual(result['state'], 'stale')
        self.assertEqual(result['error_code'], 'source_changed')
        self.assertIsNone(result['result'])
        self.library.mutate('UPDATE access_stories SET byline=? WHERE id=?', (' \t ', note['id']))
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            with access._transaction():
                member = access._require(self.member, 'family-a', 'library.read')
                blank, _, _ = context(access, 'family-a', member, 'story', self.story_id)
        self.assertIsNone(next(item for item in blank['sources'] if item['id']==source_id)['author'])
        # Another library's note on the same asset cannot supply family words or a label.
        self.library.mutate('UPDATE access_stories SET library_id=? WHERE id=?', ('family-b', note['id']))
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            with access._transaction():
                member = access._require(self.member, 'family-a', 'library.read')
                scoped, _, _ = context(access, 'family-a', member, 'story', self.story_id)
        self.assertNotIn(source_id, {item['id'] for item in scoped['sources']})

    def test_memoir_context_keeps_opening_note_and_child_titles_with_editorial_provenance(self):
        second = self.f.story('Another perspective', assets='102')
        opening = 'We remember this summer differently. Keep both perspectives.'
        book = self.f.save(self.owner, self.f.body([self.story_id, second], introduction=opening))
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            member = access._require(self.owner, 'family-a', 'library.read')
            bundle, fingerprint, _ = context(access, 'family-a', member, 'book', book['id'])
        source_id = 'editorial-book-' + book['id']
        source = next(item for item in bundle['sources'] if item['id'] == source_id)
        self.assertEqual(source, {'id': source_id, 'kind': 'editorial', 'text': opening,
                                 'asset_id': None, 'author': None})
        self.assertTrue(all(source_id in chapter['evidence_ids'] for chapter in bundle['chapters']))
        self.assertTrue(bundle['chapters'][0]['title'].startswith('Companion target · '))
        self.assertTrue(bundle['chapters'][-1]['title'].startswith('Another perspective · '))
        changed = self.f.save(self.owner, self.f.body([self.story_id, second], revision='1',
                           introduction='A revised editorial direction.'), book['id'])
        with self.library.connection() as db:
            access = AccessService(db, clock=lambda: self.library.now)
            member = access._require(self.owner, 'family-a', 'library.read')
            revised, revised_fingerprint, _ = context(access, 'family-a', member, 'book', changed['id'])
        self.assertNotEqual(fingerprint, revised_fingerprint)
        self.assertEqual(revised['sources'][0]['text'], 'A revised editorial direction.')

    def test_memoir_opening_note_counts_toward_source_limit_and_blank_note_is_omitted(self):
        class DB:
            def execute(self, *_args):
                return type('Rows', (), {'fetchall': lambda self: []})()

        detail = {'id': 'child', 'title': 'Child', 'revision': '1', 'items': [
            {'id': 'asset-1', 'evidence': [
                {'id': 'source-' + str(i), 'source': 'family', 'text': 'Known fact.'}
                for i in range(96)]}], 'chapters': [
            {'id': 'chapter-1', 'title': 'Chapter', 'narration': '', 'asset_ids': ['asset-1']}]}
        stored = {'title': 'Memoir', 'language': 'en', 'introduction': 'Opening words'}
        access = type('Access', (), {'db': DB()})()
        with patch('app.access.memory_jobs.parent', return_value=(
                {'content': '{}', 'revision': 1}, [detail], True, stored)):
            with self.assertRaises(TransportError) as caught:
                context(access, 'library-a', {}, 'book', 'book-id')
            self.assertEqual(caught.exception.status, 422)
            stored['introduction'] = ' \n\t'
            bundle, _, _ = context(access, 'library-a', {}, 'book', 'book-id')
        self.assertEqual(len(bundle['sources']), 96)
        self.assertFalse(any(s['id'].startswith('editorial-book-') for s in bundle['sources']))

    def test_memoir_long_unicode_story_title_preserves_chapter_label_within_budget(self):
        class DB:
            def execute(self, *_args):
                return type('Rows', (), {'fetchall': lambda self: []})()

        detail = {'id': 'child', 'title': '长' * 170, 'revision': '1', 'items': [],
                  'chapters': [{'id': 'chapter-1', 'title': '章' * 170,
                                'narration': '', 'asset_ids': []}]}
        stored = {'title': 'Memoir', 'language': 'zh', 'introduction': ''}
        with patch('app.access.memory_jobs.parent', return_value=(
                {'content': '{}', 'revision': 1}, [detail], True, stored)):
            bundle, _, _ = context(type('Access', (), {'db': DB()})(), 'library-a', {},
                                   'book', 'book-id')
        title = bundle['chapters'][0]['title']
        self.assertTrue(title.startswith('长'))
        self.assertTrue(title.endswith('章'))
        self.assertIn(' · ', title)
        self.assertLessEqual(len(title.encode('utf-8')), 512)

    def test_context_refuses_distinct_source_overflow_including_editorial_source(self):
        class DB:
            last_story_count = 1

            def execute(self, _sql, params=()):
                if 'alembic_version' in _sql:
                    return type('VersionRows', (), {'fetchall': lambda self: []})()
                story_index = int(params[0].rsplit('-', 1)[1])
                count = 16 if story_index < 6 else self.last_story_count
                rows = [(f'row-{story_index}-{i}', 'chapter-1', 'text', 'Memory words.',
                         'hash', 'Family', None, None, 1, None) for i in range(count)]
                return type('Rows', (), {'fetchall': lambda self: rows})()

        details = [{'id': f'story-uuid-{i}', 'revision': '1', 'items': [],
                    'chapters': [{'id': 'chapter-1', 'title': 'Chapter',
                                  'narration': '', 'asset_ids': []}]}
                   for i in range(7)]
        stored = {'title': 'Spring', 'language': 'en', 'theme': 'memoir'}
        access = type('Access', (), {'db': DB()})()
        for last_count, final_narration, case in ((1, '', '97th distinct contribution'),
                                                   (0, 'Existing editorial words.', 'editorial would overflow')):
            access.db.last_story_count = last_count
            details[-1]['chapters'][0]['narration'] = final_narration
            with self.subTest(case=case), patch('app.access.memory_jobs.parent', return_value=(
                    {'content': '{}', 'revision': 1}, details, True, stored)):
                with self.assertRaises(TransportError) as caught:
                    context(access, 'library-a', {'account_id': 'member'}, 'book', 'book-uuid')
                self.assertEqual(caught.exception.status, 422)

    def test_cancel_clears_output_lease_and_chat_reply(self):
        conversation = self.start()
        job = self.send(conversation['id'], 'Cancel this')
        self.library.mutate('''UPDATE access_memory_jobs SET state='running',output_json=?,
            lease_id='lease',lease_until=?,updated_at=? WHERE id=?''',
            ('{"reply":"private draft"}', self.library.now + 30, self.library.now, job['id']))
        self.library.mutate('''UPDATE access_memory_turns SET reply_text='private draft',reply_kind='answer'
            WHERE job_id=?''', (job['id'],))
        cancelled = self.call('get', self.member, job['id'], cancel=True)
        self.assertEqual(cancelled['state'], 'cancelled')
        self.assertIsNone(cancelled['result'])
        with self.library.connection() as db:
            row = db.execute('SELECT state,output_json,lease_id,lease_until FROM access_memory_jobs WHERE id=?',
                             (job['id'],)).fetchone()
            turn = db.execute('SELECT reply_text,reply_kind FROM access_memory_turns WHERE job_id=?',
                              (job['id'],)).fetchone()
        self.assertEqual(tuple(row), ('cancelled', None, None, None))
        self.assertEqual(tuple(turn), (None, None))

    def test_ready_proposal_becomes_stale_after_source_edit_and_media_move_denies(self):
        mutation = str(uuid.uuid4())
        job = self.narrative(mutation=mutation)
        result = {'version': 1, 'title': 'Proposed',
                  'chapters': [{'id': 'chapter-1', 'narration': 'Draft words.', 'source_ids': []}],
                  'questions': [], 'needs_review': True}
        self.mark_ready(job['id'], output=result)
        before = self.call('get', self.owner, job['id'])
        self.assertEqual(before['state'], 'ready')
        self.assertEqual(before['result'], result)

        self.library.mutate("UPDATE captions SET text='changed-current-source' WHERE id=101")
        stale = self.call('get', self.owner, job['id'])
        self.assertEqual(stale['state'], 'stale')
        self.assertIsNone(stale['result'])
        self.assertEqual(stale['error_code'], 'source_changed')
        # An exact retry remains idempotent, but must not re-disclose a ready
        # result whose source snapshot is now stale.
        try:
            retried = self.narrative(mutation=mutation)
        except TransportError as error:
            self.assertEqual(error.status, 409)
        else:
            self.assertFalse(retried['state'] == 'ready' and retried['result'] == result)

        refreshed = self.narrative(mutation=str(uuid.uuid4()))
        self.mark_ready(refreshed['id'], output=result)
        self.library.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101")
        with self.assertRaises(AccessDenied):
            self.call('get', self.owner, refreshed['id'])

    def test_book_conversation_reauthorizes_every_child_story(self):
        book = self.f.save(self.owner, self.f.body([self.story_id]))
        conversation = self.start(self.member, target_type='book', target_id=book['id'])
        self.assertEqual(conversation['target_type'], 'book')
        self.library.mutate("UPDATE assets SET status='deleted' WHERE id=101")
        with self.assertRaises(AccessDenied):
            self.send(conversation['id'], 'Remember this', token=self.member)
        with self.assertRaises(AccessDenied):
            self.call('turns', self.member, conversation['id'], 1)

    def test_chat_input_accepts_limit_and_rejects_control_or_oversized_unicode(self):
        conversation = self.start()
        exact = self.send(conversation['id'], '😀' * 1024)
        self.assertEqual(exact['state'], 'queued')
        for invalid in ('😀' * 1025, 'bad\x00control', 'bad\x7fcontrol',
                        'bad\u0085control', '\ud800', ''):
            with self.subTest(invalid=repr(invalid)[:80]):
                with self.assertRaises(TransportError):
                    self.send(conversation['id'], invalid)


if __name__ == '__main__':
    unittest.main()

"""Private memoir composition domain against a disposable protected library."""
import json
import unittest
import uuid

import test_memory_stories as story_fixture
from app.access.memory_books import MemoryBooks
from app.access.service import AccessDenied, AccessService
from app.access.transport import TransportError


class MemoryBookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        story_fixture.MemoryStoryTests.setUpClass()

    @classmethod
    def tearDownClass(cls):
        story_fixture.MemoryStoryTests.tearDownClass()

    def setUp(self):
        self.f = story_fixture.MemoryStoryTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.library_fixture = self.f.f
        self.owner = self.library_fixture.owner_token
        self.member = self.library_fixture.member_token

    def domain(self, method, token, *args):
        with self.library_fixture.connection() as db:
            access = AccessService(db, clock=lambda: self.library_fixture.now)
            return getattr(MemoryBooks(access), method)(token, 'family-a', *args)

    def story(self, title, assets='102,101', token=None):
        headers = {'Authorization': 'Bearer ' + (token or self.owner)}
        preview = self.f.client.post('/story-workspace/preview?library=family-a',
            headers=headers, json={'asset_ids': assets, 'title': title,
                                   'theme': 'everyday', 'language': 'en'})
        self.assertEqual(preview.status_code, 200, preview.text)
        draft = preview.json()
        draft['chapters'][0]['narration'] = 'private-child-source-' + title
        body = {'title': title, 'theme': draft['theme'], 'language': 'en',
                'asset_ids': ','.join(item['id'] for item in draft['items']),
                'chapters': json.dumps(draft['chapters']),
                'selection_revision': draft['selection_revision'], 'revision': '0',
                'mutation_id': str(uuid.uuid4())}
        response = self.f.save(body, headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['id']

    def body(self, story_ids, *, title='Family memoir', revision='0', mutation=None,
             introduction='Opening words', language='en'):
        return {'title': title, 'language': language, 'introduction': introduction,
                'story_ids': ','.join(story_ids), 'revision': revision,
                'mutation_id': mutation or str(uuid.uuid4())}

    def save(self, token, body, ident=None):
        return self.domain('save', token, body, ident)

    def test_save_reopen_ordered_fresh_story_summaries_and_no_source_copy(self):
        first = self.story('First child story')
        second = self.story('Second child story', assets='102')
        body = self.body([second, first], title='Our summer')
        saved = self.save(self.owner, body)
        self.assertEqual(saved['type'], 'memoir')
        self.assertEqual(saved['revision'], '1')
        self.assertEqual(saved['title'], 'Our summer')
        self.assertEqual([item['id'] for item in saved['stories']], [second, first])
        self.assertEqual(saved['stories'][0]['item_count'], 1)
        with self.library_fixture.connection() as db:
            content = db.execute('SELECT content FROM access_memory_books WHERE id=?',
                                 (saved['id'],)).fetchone()[0]
        stored = json.loads(content)
        self.assertEqual(set(stored), {'title', 'language', 'introduction', 'kind', 'story_ids'})
        self.assertEqual(stored['story_ids'], [second, first])
        self.assertNotIn('private-child-source-', content)
        reopened = self.domain('get', self.owner, saved['id'])
        self.assertEqual(reopened, saved)

    def test_viewer_read_only_contributor_owns_book_and_owner_can_edit_any(self):
        child = self.story('Shared child')
        owner_book = self.save(self.owner, self.body([child]))
        self.assertFalse(self.domain('get', self.member, owner_book['id'])['can_edit'])
        with self.assertRaises(AccessDenied):
            self.save(self.member, self.body([child]))

        self.library_fixture.mutate("UPDATE access_memberships SET role='contributor' WHERE account_id=?",
                                    (self.library_fixture.member_id,))
        contributor_book = self.save(self.member, self.body([child], title='Member book'))
        self.assertTrue(contributor_book['can_edit'])
        with self.assertRaises(AccessDenied):
            self.save(self.member, self.body([child], revision='1'), owner_book['id'])
        owner_edit = self.save(self.owner, self.body([child], title='Owner revised', revision='1'),
                               contributor_book['id'])
        self.assertEqual(owner_edit['revision'], '2')
        self.assertTrue(owner_edit['can_edit'])

    def test_revision_conflict_idempotent_retry_and_reused_mutation(self):
        child = self.story('Retry child')
        body = self.body([child], mutation=str(uuid.uuid4()))
        first = self.save(self.owner, body)
        self.assertEqual(self.save(self.owner, body), first)
        with self.assertRaises(TransportError) as reused:
            self.save(self.owner, {**body, 'introduction': 'changed payload'})
        self.assertEqual(reused.exception.status, 409)
        edit = self.body([child], title='Edited', revision='1')
        self.assertEqual(self.save(self.owner, edit, first['id'])['revision'], '2')
        stale = self.body([child], title='Stale', revision='1')
        with self.assertRaises(TransportError) as conflict:
            self.save(self.owner, stale, first['id'])
        self.assertEqual(conflict.exception.status, 409)

    def test_unavailable_child_hides_whole_book_and_foreign_story_is_denied(self):
        child = self.story('Scoped child')
        book = self.save(self.owner, self.body([child]))
        self.library_fixture.mutate("UPDATE assets SET status='deleted' WHERE id=101")
        self.assertEqual(self.domain('list', self.owner, 1)['items'], [])
        with self.assertRaises(AccessDenied):
            self.domain('get', self.owner, book['id'])
        self.library_fixture.mutate("UPDATE assets SET status='active' WHERE id=101")
        self.library_fixture.mutate("UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101")
        self.assertEqual(self.domain('list', self.owner, 1)['items'], [])
        with self.assertRaises(AccessDenied):
            self.save(self.owner, self.body([child]))

        other_headers = {'Authorization': 'Bearer ' + self.library_fixture.other_token}
        preview = self.f.client.post('/story-workspace/preview?library=family-b',
            headers=other_headers, json={'asset_ids': '201', 'title': 'Foreign child',
                                         'theme': 'everyday', 'language': 'en'})
        self.assertEqual(preview.status_code, 200, preview.text)
        draft = preview.json()
        story_body = {'title': draft['title'], 'theme': draft['theme'], 'language': 'en',
            'asset_ids': '201', 'chapters': json.dumps(draft['chapters']),
            'selection_revision': draft['selection_revision'], 'revision': '0',
            'mutation_id': str(uuid.uuid4())}
        response = self.f.client.post('/memory-stories?library=family-b',
                                      headers=other_headers, json=story_body)
        self.assertEqual(response.status_code, 200, response.text)
        foreign = response.json()['id']
        with self.assertRaises(AccessDenied):
            self.save(self.owner, self.body([foreign]))

    def test_pagination_filters_unavailable_books_before_page_boundaries(self):
        visible_child = self.story('Visible child', assets='102')
        hidden_child = self.story('Hidden child', assets='101')
        visible = [self.save(self.owner, self.body([visible_child])) for _ in range(9)]
        hidden = self.save(self.owner, self.body([hidden_child]))
        self.library_fixture.mutate('UPDATE access_memory_books SET updated_at=? WHERE id=?',
                                    (self.library_fixture.now - 10, hidden['id']))
        self.library_fixture.mutate("UPDATE assets SET status='deleted' WHERE id=101")
        first = self.domain('list', self.owner, 1)
        second = self.domain('list', self.owner, 2)
        self.assertEqual(len(first['items']), 8)
        self.assertTrue(first['has_more'])
        self.assertEqual(len(second['items']), 1)
        self.assertFalse(second['has_more'])
        self.assertEqual({item['id'] for item in first['items'] + second['items']},
                         {item['id'] for item in visible})

    def test_request_is_bounded_and_validated_before_database_access(self):
        child = self.story('Bounded child')
        invalid = self.body([child], title='x' * 513)
        with self.assertRaises(TransportError):
            self.save(self.owner, invalid)
        invalid = self.body([child], introduction='x' * 6001)
        with self.assertRaises(TransportError):
            self.save(self.owner, invalid)
        with self.assertRaises(TransportError):
            self.save(self.owner, self.body([child], language='fr'))
        with self.assertRaises(TransportError):
            self.save(self.owner, self.body([child, child]))


if __name__ == '__main__':
    unittest.main()

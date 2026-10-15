"""Negotiated assistant search v2 on synthetic SQLite; no runtime services."""
from contextlib import closing, contextmanager
from dataclasses import asdict, replace
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests' / 'security'))

from fastapi.testclient import TestClient
from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider, ProjectedIndex, ReviewedPerson
from app.access.assistant_search import name_hits
from app.access.discovery_transport import DiscoveryRuntime
from app.access.transport import AccessRuntime
from app.access.service import AccessService
from app.main import create_app
from phone_discovery_fixture import create, reviewed, TOKEN, SECOND, OTHER, NOW

ORIGIN = 'https://photohouse.example.test'
SEARCH_V2 = {'X-PhotoHouse-Search-Version': '2'}


class AssistantJointSearchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='assistant-joint-search-')
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'synthetic.sqlite'
        self.trace = []
        with closing(sqlite3.connect(self.database)) as db, db:
            create(db)
            # Make the authored and generated text sources deliberately distinct.
            db.execute("UPDATE assets SET taken_at='2032-09-01' WHERE id=101")
            db.execute("UPDATE assets SET taken_at='2032-09-02' WHERE id=103")
            db.execute("UPDATE captions SET text='海边 Ｆａｍｉｌｙ Beach Day 示例儿童',user_edited=1 WHERE id=1")
            db.execute("UPDATE captions SET text='海边 at sunset',user_edited=0 WHERE id=2")
            db.execute("UPDATE captions SET text='海边 generated view',user_edited=0 WHERE id=3")
            db.execute('''CREATE TABLE access_stories (
                id TEXT PRIMARY KEY, asset_id INTEGER NOT NULL, library_id TEXT NOT NULL,
                author_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
                text TEXT NOT NULL, updated_at INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)''')
            db.executemany('''INSERT INTO access_stories
                (id,asset_id,library_id,author_id,revision,title,text,updated_at,deleted)
                VALUES(?,?,?,?,?,?,?,?,?)''', [
                    ('note-101', 101, 'family-a', 'one', 1, '海边回忆', 'Family beach visit secret memory phrase', NOW, 0),
                    ('note-103', 103, 'family-a', 'one', 1, '海边的一天', '在海边玩 children picnic', NOW, 0),
                ])
            db.commit()
            self.index = reviewed(AccessService(db, clock=lambda: NOW))

        self.access = AccessRuntime(self.connection, ORIGIN, clock=lambda: NOW)
        self.install(self.index)
        self.auth = {'Authorization': 'Bearer ' + TOKEN}

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database, timeout=.25)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA query_only=ON')
        db.set_trace_callback(self.trace.append)
        try:
            yield db
        finally:
            db.close()

    def install(self, index):
        self.index = index
        provider = MemoryIndexProvider((index,))
        runtime = DiscoveryRuntime(self.access, provider, d.ReadBudget())
        self.discovery_runtime = runtime
        app = create_app(access_runtime=self.access, discovery_runtime=runtime,
                         assistant_enabled=True)
        client = TestClient(app, base_url=ORIGIN)
        old = getattr(self, 'client', None)
        if old is not None:
            old.close()
        self.client = client
        self.addCleanup(client.close)

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute(sql, args)

    def turn(self, words, *, context=None, v2=True, token=TOKEN):
        headers = {'Authorization': 'Bearer ' + token}
        if v2:
            headers.update(SEARCH_V2)
        return self.client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': words, 'context': context},
            headers=headers)

    def test_text_union_dedup_reasons_and_authored_first_order(self):
        response = self.turn('帮我找包含“海边”的照片')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['version'], 2)
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters'], {'media': ['image'], 'text': '海边'})
        ids = [item['id'] for item in body['items']]
        # Family notes and edited captions rank before generated captions;
        # each asset appears once even when both source types match.
        self.assertEqual(ids, ['103', '101'])
        by_id = {item['id']: item for item in body['items']}
        self.assertEqual({reason['source'] for reason in by_id['101']['match_reasons']},
                         {'photo_memory', 'edited_caption'})
        self.assertEqual(by_id['101']['match_reasons'][0]['revision'], 1)
        self.assertTrue(all({'source', 'source_id'} <= set(reason)
                            for item in body['items'] for reason in item['match_reasons']))
        self.assertNotIn('Family beach visit', response.text)
        self.assertNotIn('在海边玩', response.text)

    def test_two_character_unicode_text_and_quoted_mixed_language_phrase(self):
        chinese = self.turn('找包含“海边”的照片')
        self.assertEqual(chinese.status_code, 200, chinese.text)
        self.assertEqual(chinese.json()['filters']['text'], '海边')
        self.assertEqual([item['id'] for item in chinese.json()['items']], ['103', '101'])

        english = self.turn('please find photos containing "Family beach"')
        self.assertEqual(english.status_code, 200, english.text)
        self.assertEqual(english.json()['filters']['text'], 'Family beach')
        self.assertEqual([item['id'] for item in english.json()['items']], ['101'])
        self.assertEqual({reason['source'] for reason in english.json()['items'][0]['match_reasons']},
                         {'photo_memory', 'edited_caption'})

    def test_quoted_reviewed_person_name_remains_a_literal_text_filter(self):
        response = self.turn('找包含“示例儿童”的照片')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters']['text'], '示例儿童')
        # Quoted content is kept as a literal phrase and is not reinterpreted
        # as an identity constraint merely because it equals a reviewed name.
        self.assertNotIn('people', body['filters'])
        self.assertEqual([item['id'] for item in body['items']], ['101'])

    def test_ascii_identity_boundaries_allow_chinese_suffix_without_matching_longer_name(self):
        self.assertIn('Synthetic Person 500',
                      name_hits('找Synthetic Person 500的照片', 'Synthetic Person 500'))
        self.assertEqual(name_hits('Annabelle beach photos', 'Ann'), [])
        self.assertIn('Ann', name_hits('Ann beach photos', 'Ann'))

    def test_quoted_date_media_and_negation_are_content_not_silent_filters(self):
        quoted = self.turn('找包含“2032年9月视频”的照片')
        self.assertEqual(quoted.status_code, 200, quoted.text)
        body = quoted.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters'], {'media': ['image'], 'text': '2032年9月视频'})
        self.assertNotIn('date', body['filters'])

        literal_negative = self.turn('找包含“不要海边”的照片')
        self.assertEqual(literal_negative.status_code, 200, literal_negative.text)
        self.assertEqual(literal_negative.json()['kind'], 'results', literal_negative.json())
        self.assertEqual(literal_negative.json()['filters']['text'], '不要海边')

    def test_version_two_capability_and_unknown_header_are_explicit(self):
        path = '/assistant/v1/capabilities?library_id=family-a'
        capabilities = self.client.get(path, headers=self.auth | SEARCH_V2)
        self.assertEqual(capabilities.status_code, 200, capabilities.text)
        self.assertEqual(capabilities.json()['version'], 2)
        self.assertEqual(capabilities.json()['search']['version'], 2)
        self.assertEqual(capabilities.json()['search']['text_sources'],
                         ['current_caption', 'photo_memory'])

        rejected = self.client.post('/assistant/v1/turns',
            json={'library_id': 'family-a', 'text': '找照片', 'context': None},
            headers=self.auth | {'X-PhotoHouse-Search-Version': '3'})
        self.assertEqual(rejected.status_code, 400, rejected.text)

    def test_projected_media_date_index_still_uses_current_caption_text(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute('PRAGMA query_only=ON')
            def read(sql, args):
                return db.execute(sql, args).fetchall()
            source = d.projected_source('family-a', read, ('date', 'media'))
        record = asdict(self.index)
        record.update(enabled=('date', 'media'), people=(), pinned_ids=(), assignments=(),
                      places=(), regions=(), source_digest=d.digest(source))
        index = ProjectedIndex(**record)
        self.install(index)
        response = self.turn('找包含“Family beach”的照片')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters'], {'media': ['image'], 'text': 'Family beach'})
        self.assertEqual([item['id'] for item in body['items']], ['101'])

    def test_people_any_all_text_date_and_media_remain_joint_hard_filters(self):
        together = self.turn('找示例儿童和示例成人一起在海边玩的2032年9月照片')
        self.assertEqual(together.status_code, 200, together.text)
        all_body = together.json()
        self.assertEqual(all_body['kind'], 'results', all_body)
        self.assertEqual(all_body['filters'], {
            'date': {'from': '2032-09-01', 'to': '2032-09-30'},
            'media': ['image'], 'people': {'ids': ['301', '302'], 'match': 'all'},
            'text': '海边'})
        self.assertEqual([item['id'] for item in all_body['items']], ['103'])

        either = self.turn('找示例儿童或示例成人在海边玩的2032年9月照片')
        self.assertEqual(either.status_code, 200, either.text)
        any_body = either.json()
        self.assertEqual(any_body['kind'], 'results', any_body)
        self.assertEqual(any_body['filters']['people'], {'ids': ['301', '302'], 'match': 'any'})
        self.assertEqual([item['id'] for item in any_body['items']], ['103', '101'])

        # Existing v60 clients must also keep a conjunction as all, rather
        # than newly accepting Chinese 和 and executing a broader any query.
        legacy = self.turn('找示例儿童和示例成人的照片', v2=False)
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json()['filters']['people'], {'ids': ['301', '302'], 'match': 'all'})
        self.assertEqual([item['id'] for item in legacy.json()['items']], ['103'])

    def test_ambiguous_unknown_and_negated_constraints_clarify_without_results(self):
        shared = ReviewedPerson('family-a', '303', 'Other Person', ('示例儿童',), True)
        self.install(replace(self.index, people=self.index.people + (shared,)))
        for words in ('找示例儿童的照片', '找不存在人物在海边玩的照片',
                      '找不要含“海边”的照片'):
            with self.subTest(words=words):
                response = self.turn(words)
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertIn(body['kind'], ('clarification', 'unsupported'), body)
                self.assertEqual(body['items'], [])
                self.assertIsNone(body['context'])
                self.assertIsNone(body['effect'])

    def test_roster_over_500_is_resolved_in_one_authorized_candidate_read(self):
        people = list(self.index.people)
        people.extend(ReviewedPerson('family-a', str(1000 + number),
                                     f'Synthetic Person {number}', (), True)
                      for number in range(501))
        self.install(replace(self.index, people=tuple(people)))
        self.trace.clear()
        response = self.turn('找Synthetic Person 500的照片')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters']['people'], {'ids': ['1500'], 'match': 'any'})
        people_reads = [sql for sql in self.trace if 'FROM face_detections' in sql]
        # One whole-roster resolution read and one read for final source-digest
        # revalidation; unlike facet pagination, this count is constant-sized.
        self.assertEqual(len(people_reads), 2, people_reads)

    def test_note_edit_delete_and_scope_changes_invalidate_context(self):
        initial = self.turn('找包含“Family beach visit”的照片')
        self.assertEqual(initial.status_code, 200, initial.text)
        context = initial.json()['context']
        self.assertIsNotNone(context)

        self.mutate("UPDATE access_stories SET text='mountain trip',revision=2 WHERE id='note-101'")
        stale = self.turn('介绍这些结果', context=context)
        self.assertEqual(stale.status_code, 409, stale.text)
        current = self.turn('找包含“Family beach visit”的照片')
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()['items'], [])

        initial = self.turn('找包含“children picnic”的照片')
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual([item['id'] for item in initial.json()['items']], ['103'])
        context = initial.json()['context']
        self.mutate("UPDATE access_stories SET deleted=1,revision=2 WHERE id='note-103'")
        stale = self.turn('介绍这些结果', context=context)
        self.assertEqual(stale.status_code, 409, stale.text)
        current = self.turn('找包含“children picnic”的照片')
        self.assertEqual(current.status_code, 200, current.text)
        self.assertEqual(current.json()['items'], [])

    def test_parent_scope_foreign_rows_and_revoked_membership_never_leak(self):
        self.mutate('''INSERT INTO access_stories
            (id,asset_id,library_id,author_id,revision,title,text,updated_at,deleted)
            VALUES('foreign-parent',101,'family-b','foreign',1,'foreign title','foreign-only-phrase',?,0)''', (NOW,))
        response = self.turn('找包含“foreign-only-phrase”的照片')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['total'], 0)
        self.assertNotIn('foreign title', response.text)
        self.assertFalse(response.json()['items'])

        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        denied = self.turn('找包含“海边”的照片')
        self.assertEqual(denied.status_code, 401, denied.text)

    def test_hidden_or_moved_assets_and_stale_reviewed_index_fail_closed(self):
        first = self.turn('找包含“海边”的照片')
        self.assertEqual(first.status_code, 200, first.text)
        for sql in ("UPDATE assets SET status='hidden' WHERE id=101",
                    "UPDATE access_asset_libraries SET library_id='family-b' WHERE asset_id=101"):
            with self.subTest(sql=sql):
                self.mutate(sql)
                changed = self.turn('介绍这些结果', context=first.json()['context'])
                self.assertEqual(changed.status_code, 409, changed.text)
                self.mutate("UPDATE assets SET status='active' WHERE id=101")
                self.mutate("UPDATE access_asset_libraries SET library_id='family-a' WHERE asset_id=101")

    def test_v1_default_shape_and_v2_text_context_downgrade_are_separate(self):
        legacy = self.turn('找去年视频', v2=False)
        self.assertEqual(legacy.status_code, 200, legacy.text)
        self.assertEqual(legacy.json()['version'], 1)
        self.assertNotIn('match_reasons', legacy.text)

        modern = self.turn('找包含“海边”的照片')
        self.assertEqual(modern.status_code, 200, modern.text)
        self.assertEqual(modern.json()['version'], 2)
        downgraded = self.turn('介绍这些结果', context=modern.json()['context'], v2=False)
        # The v1 reader's binding omits the v2 text projection, so it refuses
        # the frozen v2 context before attempting the v1 query.
        self.assertEqual(downgraded.status_code, 409, downgraded.text)

    def test_search_reads_current_sources_without_private_assistant_journals(self):
        self.trace.clear()
        response = self.turn('找包含“海边”的照片')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(any('FROM access_stories' in sql for sql in self.trace))
        self.assertTrue(any('FROM captions' in sql for sql in self.trace))
        journal_tables = ('assistant_journal', 'assistant_workspace', 'assistant_turn',
                          'assistant_exchange', 'assistant_receipt')
        self.assertFalse(any(any(table in sql.casefold() for table in journal_tables)
                             for sql in self.trace))

    def test_refinement_and_open_use_the_current_ranked_text_context(self):
        found = self.turn('找包含“海边”的照片').json()
        opened = self.turn('打开第二个', context=found['context'])
        self.assertEqual(opened.status_code, 200, opened.text)
        self.assertEqual(opened.json()['effect'], {'type': 'open_asset', 'asset_id': '101'})
        refined = self.turn('只看示例成人去年九月的', context=found['context'])
        self.assertEqual(refined.status_code, 200, refined.text)
        body = refined.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters']['text'], '海边')
        self.assertEqual(body['filters']['people'], {'ids': ['302'], 'match': 'any'})
        self.assertEqual(body['filters']['date'], {'from': '2032-09-01', 'to': '2032-09-30'})
        self.assertEqual([item['id'] for item in body['items']], ['103'])
        # Even a forged client-visible order cannot redirect the open effect.
        changed = dict(found['context'], visible_ids=['101', '103'])
        refused = self.turn('打开第二个', context=changed)
        self.assertEqual(refused.status_code, 409, refused.text)

    def test_pagination_deduplicates_and_preserves_authored_first_order(self):
        from app.access.assistant_search import AssistantSearchReads
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute('PRAGMA foreign_keys=ON')
            for aid in range(401, 423):
                db.execute("INSERT INTO assets VALUES(?, 'synthetic', 'active', 'image/jpeg', 8,8,NULL,NULL)", (aid,))
                db.execute("INSERT INTO access_asset_libraries VALUES(?, 'family-a')", (aid,))
                db.execute("INSERT INTO captions VALUES(?,?, '海边',0,0)", (aid, aid))
            db.commit()
            index = reviewed(AccessService(db, clock=lambda: NOW))
        self.install(index)
        with self.connection() as db:
            reader = AssistantSearchReads(AccessService(db, clock=lambda: NOW),
                                         MemoryIndexProvider((index,)), d.ReadBudget())
            binding = reader.entities(TOKEN, 'family-a', words='找照片')['binding']
            first = reader.search(TOKEN, 'family-a', binding=binding,
                                  filters={'text': '海边', 'media': ['image']}, page_size=5)
            second = reader.search(TOKEN, 'family-a', binding=binding,
                                   filters={'text': '海边', 'media': ['image']},
                                   page=2, page_size=5, fingerprint=first['fingerprint'])
        self.assertEqual(first['total'], 24)
        self.assertTrue(first['has_more'])
        self.assertEqual([item['id'] for item in first['items']], ['103', '101', '422', '421', '420'])
        self.assertEqual([item['id'] for item in second['items']], ['419', '418', '417', '416', '415'])

    def test_private_workspace_does_not_accept_the_new_search_contract(self):
        for endpoint in ('capabilities', 'saved-memory-capabilities',
                         'saved-memory-followup-capabilities', 'saved-memory-reader-capabilities'):
            with self.subTest(endpoint=endpoint):
                response = self.client.get('/assistant/workspace/v1/' + endpoint + '?library_id=family-a',
                                           headers=self.auth | SEARCH_V2)
                self.assertEqual(response.status_code, 400, response.text)


if __name__ == '__main__':
    unittest.main()

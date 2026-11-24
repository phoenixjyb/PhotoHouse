"""Generated protected conversations retain an unresolved date request."""
from dataclasses import replace
import json
import unittest
import uuid

from app.access.assistant_workspace_store import initialize_v2
from app.access.search_intent_view import REDACTION_MARKER
from phone_discovery_fixture import NOW, TOKEN, OTHER, SECOND, RELOGIN
import test_assistant_intent_search as intent_fixture


class AssistantPendingIntentTests(unittest.TestCase):
    connection = intent_fixture.AssistantIntentSearchTests.connection
    mutate = intent_fixture.AssistantIntentSearchTests.mutate
    install = intent_fixture.AssistantIntentSearchTests.install

    def setUp(self):
        intent_fixture.AssistantIntentSearchTests.setUp(self)
        self.now = [NOW]
        self.access = replace(self.access, clock=lambda: self.now[0])
        self.install(self.index)
        self.store = initialize_v2(self.database.parent.resolve() / 'pending-workspace.sqlite',
                                   clock=lambda: self.now[0])
        self.app.state.assistant_workspace_store = self.store
        self.app.state.assistant_workspace_healthy = True
        self.base = '/assistant/workspace/v1'
        self.headers = {'Authorization': 'Bearer ' + TOKEN, 'X-PhotoHouse-Search-Version': '3'}
        self.thread = self.new_thread()

    def new_thread(self):
        response = self.client.post(self.base + '/threads', json={'library_id': 'family-a'},
                                    headers={'Authorization': self.headers['Authorization']})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['thread']['thread_id']

    def send(self, words, revision=0, *, thread=None, rid=None, headers=None):
        return self.client.post(f'{self.base}/threads/{thread or self.thread}/turns',
            headers=headers or self.headers,
            json={'library_id': 'family-a', 'request_id': rid or str(uuid.uuid4()),
                  'expected_revision': revision, 'text': words})

    def ask(self, words='find photos of Sample Child from childhood playing in snow red coat'):
        response = self.send(words)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual((result['version'], result['kind']), (3, 'clarification'))
        self.assertIsNone(result['context'])
        self.assertNotIn('pending_intent', response.text)
        self.assertEqual(self.planner.calls, [])
        return response.json()

    def month_correction_fixture(self):
        self.mutate("UPDATE assets SET taken_at='2032-08-21' WHERE id=101")
        self.mutate("UPDATE captions SET text=text || ' Example day' WHERE id IN (1, 2)")
        with self.connection() as db:
            index = intent_fixture.reviewed(intent_fixture.AccessService(db, clock=lambda: NOW))
        self.install(index)
        self.app.state.assistant_workspace_store = self.store
        self.app.state.assistant_workspace_healthy = True

    def saved_search_result(self, words, revision, *, thread, headers, rid=None):
        response = self.send(words, revision, thread=thread, headers=headers, rid=rid)
        self.assertEqual(response.status_code, 200, response.text)
        value = response.json()
        self.assertEqual(value['revision'], revision + 1)
        return value['result']

    def test_month_only_correction_keeps_search_year_and_opens_expected_photo(self):
        self.month_correction_fixture()
        find_en = 'find photos of Sample Child in Example region in 2032 containing "Example day"'
        find_zh = '找示例儿童2032年在示例地区的照片，包含“Example day”'
        journeys = (
            (find_en, 'earlier', 'no, I meant August', 'open the first result'),
            (find_zh, '再早一点', '我说的是八月份', '打开第一个'),
            (find_zh, 'earlier一点', 'I meant八月份', 'open the first result'),
        )
        for version in (2, 3):
            headers = {**self.headers, 'X-PhotoHouse-Search-Version': str(version)}
            for find, unclear, correct, open_photo in journeys:
                with self.subTest(version=version, correction=correct):
                    thread = self.new_thread()
                    found = self.saved_search_result(find, 0, thread=thread, headers=headers)
                    self.assertEqual((found['version'], found['kind']), (version, 'results'))
                    self.assertEqual(found['filters'], {
                        'date': {'from': '2032-01-01', 'to': '2032-12-31'}, 'media': ['image'],
                        'people': {'ids': ['301'], 'match': 'any'}, 'locations': ['601'], 'text': 'Example day',
                    })
                    self.assertCountEqual([item['id'] for item in found['items']], ['101', '103'])
                    question = self.saved_search_result(unclear, 1, thread=thread, headers=headers)
                    self.assertEqual((question['kind'], question['context'], question['items'], question['effect']),
                                     ('clarification', found['context'], found['items'], None))

                    changed = self.saved_search_result(correct, 2, thread=thread, headers=headers)
                    self.assertEqual(changed['kind'], 'results', changed)
                    self.assertEqual(changed['filters'], {**found['filters'],
                        'date': {'from': '2032-08-01', 'to': '2032-08-31'}})
                    self.assertEqual([item['id'] for item in changed['items']], ['101'])
                    self.assertIsNone(changed['effect'])
                    request_id = str(uuid.uuid4())
                    opened = self.saved_search_result(open_photo, 3, thread=thread, headers=headers, rid=request_id)
                    self.assertEqual((opened['kind'], opened['effect']),
                                     ('open', {'type': 'open_asset', 'asset_id': '101'}))
                    recovered = self.client.get(f'{self.base}/threads/{thread}/requests/{request_id}',
                        params={'library_id': 'family-a'}, headers=headers)
                    self.assertEqual(recovered.status_code, 200, recovered.text)
                    self.assertTrue(recovered.json()['recovered'])
                    self.assertEqual(recovered.json()['result']['items'], changed['items'])
                    self.assertIsNone(recovered.json()['result']['effect'])
                    self.assertEqual(self.planner.calls, [])

    def test_paired_month_correction_checks_old_year_and_keeps_caption_clue(self):
        self.month_correction_fixture()
        options = {'thread': self.new_thread(), 'headers': self.headers}
        found = self.saved_search_result(
            'find photos of Sample Child playing in snow in Example region in September 2032', 0, **options)
        self.assertEqual(found['filters']['descriptive']['concepts'][0]['surface'], 'playing in snow')
        self.assertEqual([item['id'] for item in found['items']], ['103'])
        mismatch = self.saved_search_result('not September 2031, but August', 1, **options)
        self.assertEqual((mismatch['kind'], mismatch['context'], mismatch['items']),
                         ('clarification', found['context'], found['items']))
        changed = self.saved_search_result('不是九月，是八月', 2, **options)
        self.assertEqual(changed['kind'], 'results', changed)
        self.assertEqual(changed['filters'], {**found['filters'],
            'date': {'from': '2032-08-01', 'to': '2032-08-31'}})
        self.assertEqual([item['id'] for item in changed['items']], ['101'])
        self.assertEqual(len(self.planner.calls), 1)

    def test_month_correction_requires_clear_year_and_current_access(self):
        self.month_correction_fixture()
        searches = []
        for version in (2, 3):
            with self.subTest(version=version):
                headers = {**self.headers, 'X-PhotoHouse-Search-Version': str(version)}
                options = {'thread': self.new_thread(), 'headers': headers}
                found = self.saved_search_result(
                    'find photos of Sample Child in Example region from 2031 to 2032', 0, **options)
                self.assertEqual(found['filters']['date'], {'from': '2031-01-01', 'to': '2032-12-31'})
                for revision, words in enumerate(('I meant August', 'I meant August 2032 videos'), 1):
                    unclear = self.saved_search_result(words, revision, **options)
                    self.assertEqual((unclear['kind'], unclear['context'], unclear['items'], unclear['effect']),
                                     ('clarification', found['context'], found['items'], None))
                explicit = self.saved_search_result('I meant September 2032', 3, **options)
                self.assertEqual(explicit['filters'], {**found['filters'],
                    'date': {'from': '2032-09-01', 'to': '2032-09-30'}})
                self.assertEqual([item['id'] for item in explicit['items']], ['103'])
                other_year = self.saved_search_result('I meant August 2031', 4, **options)
                self.assertEqual(other_year['filters'], {**found['filters'],
                    'date': {'from': '2031-08-01', 'to': '2031-08-31'}})
                self.assertEqual(other_year['items'], [])
                searches.append(options)

        self.mutate("UPDATE captions SET text='new generated evidence' WHERE id=1")
        for options in searches:
            stale = self.send('I meant August', 5, **options)
            self.assertEqual(stale.status_code, 409, stale.text)
            self.assertNotIn('items', stale.json())
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        for options in searches:
            denied = self.send('I meant August', 5, **options)
            self.assertIn(denied.status_code, (401, 403), denied.text)
            self.assertNotIn('items', denied.json())
        self.assertEqual(self.planner.calls, [])

    def test_short_date_answer_retains_bilingual_request_and_original_inputs(self):
        queries = ('find photos of Sample Child from childhood playing in snow red coat',
                   '找示例儿童小时候玩雪红外套的照片',
                   'find示例儿童小时候playing in snow red coat的photos')
        for query in queries:
            with self.subTest(query=query):
                self.thread = self.new_thread()
                self.planner.calls.clear()
                asked = self.ask(query)
                response = self.send('September 2032', 1)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()['result']
                self.assertEqual(result['kind'], 'results', result)
                self.assertEqual({item['id'] for item in result['items']}, {'101', '103'})
                self.assertEqual(result['filters']['people'], {'ids': ['301'], 'match': 'any'})
                self.assertEqual(result['filters']['media'], ['image'])
                self.assertEqual(result['filters']['date'], {'from': '2032-09-01', 'to': '2032-09-30'})
                self.assertEqual(len(result['filters']['descriptive']['concepts']), 2)
                self.assertEqual(len(self.planner.calls), 1)
                self.assertNotIn('September 2032', self.planner.calls[0][0])
                history = self.client.get(f'{self.base}/threads/{self.thread}?library_id=family-a',
                    headers={'Authorization': self.headers['Authorization']})
                self.assertEqual(history.status_code, 200, history.text)
                self.assertEqual([row['input_text'] for row in history.json()['exchanges']],
                                 [query, 'September 2032'])
                self.assertNotIn('pending_intent', history.text)
                readback = self.client.get(
                    f'{self.base}/threads/{self.thread}/requests/{asked["request_id"]}?library_id=family-a',
                    headers=self.headers)
                self.assertEqual(readback.status_code, 200, readback.text)
                self.assertNotIn('pending_intent', readback.text)

    def test_approximate_age_clarification_retains_the_exact_scene_without_guessing_dates(self):
        cases = (
            ('find photos of Sample Child maybe two summers ago playing in snow red coat',
             'maybe two summers ago', ['playing in snow', 'red coat']),
            ('找示例儿童大概两年前玩雪红外套的照片', '大概两年前', ['玩雪', '红外套']),
            ('find示例儿童可能是两年前playing in snow red coat的photos',
             '可能是两年前', ['playing in snow', 'red coat']),
            ('find photos of Sample Child from long ago playing in snow red coat',
             'long ago', ['playing in snow', 'red coat']),
        )
        for query, phrase, surfaces in cases:
            with self.subTest(query=query):
                self.thread = self.new_thread()
                self.planner.calls.clear()
                asked = self.ask(query)
                if phrase == 'long ago':
                    pending = self.store.get_turn('one', 'family-a', self.thread,
                        asked['request_id'])['result_summary']['pending_intent']
                    self.assertEqual(pending['version'], 3)
                    self.assertEqual('long ago', pending['query'][pending['start']:pending['end']])
                clarification = asked['result']
                self.assertTrue(
                    'year' in clarification['reply'].lower() or
                    '年份' in clarification['reply'] or '哪几个月' in clarification['reply'])
                self.assertIsNone(clarification['filters'])
                self.assertEqual(clarification['items'], [])
                self.assertNotIn('pending_intent', str(asked))
                self.assertEqual(self.planner.calls, [])

                response = self.send('September 2032', 1)
                self.assertEqual(response.status_code, 200, response.text)
                result = response.json()['result']
                self.assertEqual(result['kind'], 'results', result)
                self.assertEqual({item['id'] for item in result['items']}, {'101', '103'})
                self.assertEqual(result['filters']['people'], {'ids': ['301'], 'match': 'any'})
                self.assertEqual(result['filters']['media'], ['image'])
                self.assertEqual(result['filters']['date'],
                                 {'from': '2032-09-01', 'to': '2032-09-30'})
                self.assertEqual([concept['surface'] for concept in
                                  result['filters']['descriptive']['concepts']],
                                 surfaces)
                expected = query.replace(phrase, REDACTION_MARKER * len(phrase), 1)
                command = 'find' if expected.startswith('find') else '找'
                expected = REDACTION_MARKER * len(command) + expected[len(command):]
                for protected in ('Sample Child', '示例儿童', 'photos', '照片'):
                    expected = expected.replace(protected, ''.join(
                        ' ' if char == ' ' else REDACTION_MARKER for char in protected))
                self.assertEqual(len(self.planner.calls), 1)
                self.assertEqual(self.planner.calls[0][0], expected)
                self.assertFalse(self.planner.calls[0][2])

                history = self.client.get(
                    f'{self.base}/threads/{self.thread}?library_id=family-a',
                    headers={'Authorization': self.headers['Authorization']})
                self.assertEqual(history.status_code, 200, history.text)
                self.assertEqual([row['input_text'] for row in history.json()['exchanges']],
                                 [query, 'September 2032'])

    def test_legacy_v2_pending_readback_survives_but_new_ambiguity_blocks_continuation(self):
        asked = self.ask()
        request_id = asked['request_id']
        original = 'Find photos from childhood and long ago'
        start = original.index('from childhood')
        with self.store.connection() as db:
            row = db.execute('''SELECT input_text,result_summary FROM turn_requests
                WHERE request_id=?''', (request_id,)).fetchone()
            summary = json.loads(row['result_summary'])
            summary['pending_intent'].update({
                'version': 2, 'query': original, 'start': start,
                'end': start + len('from childhood'),
            })
            db.execute('''UPDATE turn_requests SET input_text=?,result_summary=?
                WHERE request_id=?''',
                (original, json.dumps(summary, ensure_ascii=False), request_id))

        saved = self.store.get_turn('one', 'family-a', self.thread, request_id)
        self.assertEqual(saved['result_summary']['pending_intent']['version'], 2)
        self.assertEqual(saved['result_summary']['pending_intent']['query'], original)
        self.planner.calls.clear()
        readback = self.client.get(
            f'{self.base}/threads/{self.thread}/requests/{request_id}?library_id=family-a',
            headers=self.headers)
        self.assertEqual(readback.status_code, 200, readback.text)
        self.assertEqual(readback.json()['result']['kind'], 'clarification')
        self.assertNotIn('pending_intent', readback.text)
        self.assertEqual(self.planner.calls, [])

        ambiguous = self.send('September 2032', 1)
        self.assertEqual(ambiguous.status_code, 409, ambiguous.text)
        self.assertEqual(self.planner.calls, [])

    def test_invalid_answer_keeps_the_original_question_without_extending_expiry(self):
        asked = self.ask()
        original = self.store.get_turn('one', 'family-a', self.thread,
                                       asked['request_id'])['result_summary']['pending_intent']
        self.now[0] += 10
        invalid = self.send('2018 and share everything', 1)
        self.assertEqual(invalid.status_code, 200, invalid.text)
        self.assertEqual(invalid.json()['result']['kind'], 'clarification')
        carried = self.store.get_turn('one', 'family-a', self.thread,
            invalid.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(carried, original)
        valid = self.send('2032年9月', 2)
        self.assertEqual(valid.status_code, 200, valid.text)
        self.assertEqual(valid.json()['result']['kind'], 'results')
        self.assertEqual(len(self.planner.calls), 1)

    def test_request_recovery_replays_the_resolved_search_without_planning_again(self):
        self.ask()
        rid = str(uuid.uuid4())
        first = self.send('September 2032', 1, rid=rid)
        self.assertEqual(first.status_code, 200, first.text)
        calls = len(self.planner.calls)
        self.planner.failure = True
        replay = self.send('September 2032', 1, rid=rid)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(replay.json()['recovered'])
        self.assertEqual(replay.json()['result'], first.json()['result'])
        self.assertEqual(len(self.planner.calls), calls)

    def test_provider_outage_can_retry_the_same_answer_and_source_edit_during_planning_withholds(self):
        self.ask()
        self.planner.failure = True
        unavailable = self.send('September 2032', 1)
        self.assertEqual(unavailable.status_code, 200, unavailable.text)
        self.assertEqual(unavailable.json()['result']['kind'], 'clarification')
        saved = self.store.get_turn('one', 'family-a', self.thread,
            unavailable.json()['request_id'])['result_summary']
        self.assertIn('pending_intent', saved)
        self.planner.failure = False
        recovered = self.send('September 2032', 2)
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()['result']['kind'], 'results')
        self.assertEqual(len(self.planner.calls), 2)

        self.thread = self.new_thread()
        self.planner.calls.clear()
        self.ask()
        self.planner.before_reply = lambda: self.mutate(
            "UPDATE captions SET text='new evidence during the generated proposal' WHERE id=1")
        changed = self.send('September 2032', 1)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertNotIn('items', changed.json())

    def test_expiry_explains_instead_of_reinterpreting_a_short_answer_as_a_broader_search(self):
        self.ask()
        self.now[0] += 901
        response = self.send('September 2032', 1)
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()['result']
        self.assertEqual(result['kind'], 'clarification')
        self.assertIn('expired', result['reply'])
        self.assertIsNone(result['context'])
        self.assertEqual(self.planner.calls, [])

    def test_source_session_membership_and_thread_changes_cannot_resume_old_request(self):
        self.ask()
        other = self.send('September 2032', 1,
            headers={**self.headers, 'Authorization': 'Bearer ' + OTHER})
        self.assertIn(other.status_code, (401, 403))
        other_account = self.send('September 2032', 1,
            headers={**self.headers, 'Authorization': 'Bearer ' + SECOND})
        self.assertEqual(other_account.status_code, 404, other_account.text)
        session = self.send('September 2032', 1,
            headers={**self.headers, 'Authorization': 'Bearer ' + RELOGIN})
        self.assertEqual(session.status_code, 409, session.text)
        self.assertEqual(self.planner.calls, [])
        another_thread = self.new_thread()
        fresh = self.send('September 2032', thread=another_thread)
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['result']['kind'], 'clarification')
        self.assertIsNone(fresh.json()['result']['context'])
        self.mutate("UPDATE access_stories SET text='changed synthetic evidence' WHERE id='note-101'")
        changed = self.send('September 2032', 1)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(self.planner.calls, [])
        independent = self.send('find photos of Sample Adult', 1)
        self.assertEqual(independent.status_code, 200, independent.text)
        self.assertEqual(independent.json()['result']['filters'],
                         {'media': ['image'], 'people': {'ids': ['302'], 'match': 'any'}})

    def test_quoted_time_phrase_stays_literal_and_v2_pending_date_is_versioned(self):
        quoted = self.send('find photos containing "childhood"')
        self.assertEqual(quoted.status_code, 200, quoted.text)
        self.assertEqual(quoted.json()['result']['filters']['text'], 'childhood')
        headers = {**self.headers, 'X-PhotoHouse-Search-Version': '2'}
        thread = self.new_thread()
        v2 = self.send('find photos from childhood', thread=thread, headers=headers)
        self.assertEqual(v2.status_code, 200, v2.text)
        self.assertEqual((v2.json()['result']['version'], v2.json()['result']['kind']),
                         (2, 'clarification'))
        self.assertNotIn('pending_intent', v2.text)
        pending = self.store.get_turn('one', 'family-a', thread,
            v2.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(pending['version'], 3)  # date-slot grammar version, independent of wire v2
        self.assertEqual(self.planner.calls, [])
        answered = self.send('September 2032', 1, thread=thread, headers=headers)
        self.assertEqual(answered.status_code, 200, answered.text)
        result = answered.json()['result']
        self.assertEqual((result['version'], result['kind']), (2, 'results'))
        self.assertEqual(result['filters'], {
            'date': {'from': '2032-09-01', 'to': '2032-09-30'}, 'media': ['image']})
        self.assertEqual(self.planner.calls, [])

    def test_v2_bilingual_pending_date_retains_only_fully_compiled_filters(self):
        self.mutate("UPDATE captions SET text='A child at the beach 示范在海边玩' WHERE id=1")
        self.mutate("UPDATE captions SET text='示例儿童在海边玩 at the beach' WHERE id=2")
        with self.connection() as db:
            db.execute('PRAGMA foreign_keys=ON')
            index = intent_fixture.reviewed(intent_fixture.AccessService(db, clock=lambda: NOW))
        self.install(index)
        self.app.state.assistant_workspace_store = self.store
        self.app.state.assistant_workspace_healthy = True
        headers = {**self.headers, 'X-PhotoHouse-Search-Version': '2'}
        queries = (
            ('find photos of Sample Child from childhood at the beach', 'beach'),
            ('找示例儿童小时候在海边的照片', '海边'),
            ('find示例儿童小时候at the beach的photos', 'beach'),
        )
        for query, literal in queries:
            with self.subTest(query=query):
                thread = self.new_thread()
                before_calls = len(self.planner.calls)
                asked = self.send(query, thread=thread, headers=headers)
                self.assertEqual(asked.status_code, 200, asked.text)
                question = asked.json()['result']
                self.assertEqual((question['version'], question['kind']), (2, 'clarification'))
                self.assertIsNone(question['context'])
                self.assertNotIn('pending_intent', asked.text)
                self.assertEqual(len(self.planner.calls), before_calls)
                readback = self.client.get(
                    f'{self.base}/threads/{thread}/requests/{asked.json()["request_id"]}?library_id=family-a',
                    headers=headers)
                self.assertEqual(readback.status_code, 200, readback.text)
                self.assertEqual(readback.json()['result'], question)

                answer_id = str(uuid.uuid4())
                answer = self.send('2032年9月', 1, thread=thread, rid=answer_id,
                                   headers=headers)
                self.assertEqual(answer.status_code, 200, answer.text)
                result = answer.json()['result']
                self.assertEqual((result['version'], result['kind']), (2, 'results'), result)
                self.assertEqual(result['filters']['people'], {'ids': ['301'], 'match': 'any'})
                self.assertEqual(result['filters']['media'], ['image'])
                self.assertEqual(result['filters']['text'], literal)
                self.assertEqual(result['filters']['date'],
                                 {'from': '2032-09-01', 'to': '2032-09-30'})
                self.assertEqual({item['id'] for item in result['items']}, {'101', '103'})
                self.assertEqual(len(self.planner.calls), before_calls)
                replay = self.send('2032年9月', 1, thread=thread, rid=answer_id,
                                   headers=headers)
                self.assertEqual(replay.status_code, 200, replay.text)
                self.assertTrue(replay.json()['recovered'])
                self.assertEqual(replay.json()['result'], result)
                self.assertEqual(len(self.planner.calls), before_calls)
                history = self.client.get(f'{self.base}/threads/{thread}?library_id=family-a',
                    headers={'Authorization': headers['Authorization']})
                self.assertEqual(history.status_code, 200, history.text)
                self.assertEqual([row['input_text'] for row in history.json()['exchanges']],
                                 [query, '2032年9月'])
                self.assertNotIn('pending_intent', history.text)

    def test_cued_vague_time_words_remain_literal_for_v2_and_v3(self):
        cases = (
            ('find photos containing childhood snow', 'childhood snow'),
            ('找包含小时候玩雪的照片', '小时候玩雪'),
            ('find photos about childhood red coat', 'childhood red coat'),
        )
        for version in (2, 3):
            headers = {**self.headers, 'X-PhotoHouse-Search-Version': str(version)}
            for query, literal in cases:
                with self.subTest(version=version, query=query):
                    thread = self.new_thread()
                    before_calls = len(self.planner.calls)
                    response = self.send(query, thread=thread, headers=headers)
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()['result']
                    self.assertEqual((result['version'], result['kind']),
                                     (version, 'results'), result)
                    self.assertEqual(result['filters']['text'], literal)
                    self.assertNotIn('date', result['filters'])
                    self.assertNotIn('pending_intent', response.text)
                    self.assertEqual(len(self.planner.calls), before_calls)

    def test_about_approximate_date_still_clarifies_before_literal_retrieval(self):
        cases = ('find photos of Sample Child about two years ago containing "birthday cake"',
                 'find photos of Sample Child about a few winters ago containing "birthday cake"')
        for version in (2, 3):
            headers = {**self.headers, 'X-PhotoHouse-Search-Version': str(version)}
            for query in cases:
                with self.subTest(version=version, query=query):
                    thread = self.new_thread()
                    before_calls = len(self.planner.calls)
                    asked = self.send(query, thread=thread, headers=headers)
                    self.assertEqual(asked.status_code, 200, asked.text)
                    question = asked.json()['result']
                    self.assertEqual((question['version'], question['kind']),
                                     (version, 'clarification'), question)
                    self.assertIsNone(question['filters'])
                    self.assertEqual(len(self.planner.calls), before_calls)

                    answer = self.send('September 2032', 1, thread=thread, headers=headers)
                    self.assertEqual(answer.status_code, 200, answer.text)
                    result = answer.json()['result']
                    self.assertEqual((result['version'], result['kind']),
                                     (version, 'results'), result)
                    self.assertEqual(result['filters']['people'],
                                     {'ids': ['301'], 'match': 'any'})
                    self.assertEqual(result['filters']['media'], ['image'])
                    self.assertEqual(result['filters']['text'], 'birthday cake')
                    self.assertEqual(result['filters']['date'],
                                     {'from': '2032-09-01', 'to': '2032-09-30'})
                    self.assertNotIn('descriptive', result['filters'])
                    self.assertEqual(len(self.planner.calls), before_calls)

    def test_plain_about_approximate_date_accepts_a_short_answer_without_text_filter(self):
        for version in (2, 3):
            headers = {**self.headers, 'X-PhotoHouse-Search-Version': str(version)}
            for query in ('find photos about two years ago',
                          'find photos about a few winters ago'):
                with self.subTest(version=version, query=query):
                    thread = self.new_thread()
                    asked = self.send(query, thread=thread, headers=headers)
                    self.assertEqual(asked.status_code, 200, asked.text)
                    self.assertEqual(asked.json()['result']['kind'], 'clarification')
                    pending = self.store.get_turn('one', 'family-a', thread,
                        asked.json()['request_id'])['result_summary']['pending_intent']
                    self.assertTrue(pending['query'][pending['start']:pending['end']].startswith('about '))
                    answered = self.send('2032年9月', 1, thread=thread, headers=headers)
                    self.assertEqual(answered.status_code, 200, answered.text)
                    result = answered.json()['result']
                    self.assertEqual((result['version'], result['kind']), (version, 'results'))
                    self.assertEqual(result['filters'], {'media': ['image'],
                        'date': {'from': '2032-09-01', 'to': '2032-09-30'}})
                    self.assertEqual(self.planner.calls, [])

    def test_v2_date_question_requires_original_protocol_for_bound_continuation(self):
        v2 = {**self.headers, 'X-PhotoHouse-Search-Version': '2'}
        v3 = {**self.headers, 'X-PhotoHouse-Search-Version': '3'}
        thread = self.new_thread()
        asked = self.send('find photos of Sample Child from childhood',
                          thread=thread, headers=v2)
        self.assertEqual(asked.status_code, 200, asked.text)
        self.assertEqual((asked.json()['result']['version'], asked.json()['result']['kind']),
                         (2, 'clarification'))
        before_calls = len(self.planner.calls)

        answered = self.send('September 2032', 1, thread=thread, headers=v3)
        self.assertEqual(answered.status_code, 409, answered.text)
        self.assertEqual(len(self.planner.calls), before_calls)
        pending = self.store.get_turn('one', 'family-a', thread,
            asked.json()['request_id'])['result_summary']['pending_intent']
        self.assertEqual(pending['version'], 3)

        # The rejected negotiation change does not invalidate the pending
        # question; its original v2 binding still accepts the date answer.
        answered = self.send('September 2032', 1, thread=thread, headers=v2)
        self.assertEqual(answered.status_code, 200, answered.text)
        result = answered.json()['result']
        self.assertEqual((result['version'], result['kind']), (2, 'results'), result)
        self.assertEqual(result['filters'], {
            'date': {'from': '2032-09-01', 'to': '2032-09-30'},
            'media': ['image'], 'people': {'ids': ['301'], 'match': 'any'}})
        self.assertEqual(len(self.planner.calls), before_calls)

    def test_v2_pending_refuses_unsupported_residue_and_preserves_expiry_and_binding(self):
        headers = {**self.headers, 'X-PhotoHouse-Search-Version': '2'}
        unsupported = self.send('find photos of Sample Child from childhood happy trip',
                                headers=headers)
        self.assertEqual(unsupported.status_code, 200, unsupported.text)
        self.assertEqual(unsupported.json()['result']['kind'], 'clarification')
        self.assertNotIn('pending_intent', unsupported.json()['result'])
        self.assertEqual(self.planner.calls, [])

        thread = self.new_thread()
        asked = self.send('find photos from childhood', thread=thread, headers=headers)
        self.assertEqual(asked.status_code, 200, asked.text)
        self.now[0] += 901
        expired = self.send('September 2032', 1, thread=thread, headers=headers)
        self.assertEqual(expired.status_code, 200, expired.text)
        self.assertIn('expired', expired.json()['result']['reply'].lower())
        self.assertEqual(expired.json()['result']['version'], 2)
        self.assertEqual(self.planner.calls, [])

        self.now[0] = NOW
        thread = self.new_thread()
        asked = self.send('find photos from childhood', thread=thread, headers=headers)
        self.assertEqual(asked.status_code, 200, asked.text)
        wrong_session = self.send('September 2032', 1, thread=thread,
            headers={**headers, 'Authorization': 'Bearer ' + RELOGIN})
        self.assertEqual(wrong_session.status_code, 409, wrong_session.text)

        thread = self.new_thread()
        asked = self.send('find photos at the beach from childhood', thread=thread,
                          headers=headers)
        self.assertEqual(asked.status_code, 200, asked.text)
        self.mutate("UPDATE captions SET text='changed after the date question' WHERE id=1")
        changed = self.send('September 2032', 1, thread=thread, headers=headers)
        self.assertEqual(changed.status_code, 409, changed.text)
        self.assertEqual(self.planner.calls, [])

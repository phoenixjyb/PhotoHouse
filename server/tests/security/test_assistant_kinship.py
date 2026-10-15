"""Assistant kinship constraints over the synthetic authorized search fixture."""
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
import sqlite3
import json
import os
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests' / 'security'))

from fastapi.testclient import TestClient
from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider, ReviewedPerson
from app.access.discovery_transport import DiscoveryRuntime
from app.access.transport import AccessRuntime
from app.access.service import AccessService
from app.access.kinship import KinshipGraph
from app.main import create_app
from phone_discovery_fixture import create, reviewed, TOKEN, SECOND, NOW


ORIGIN = 'https://photohouse.example.test'
SEARCH_V2 = {'X-PhotoHouse-Search-Version': '2'}
DEFAULT_BINDING = object()


def assistant_graph(*, revision='kinship-revision-1', perspective='child',
                    parent_binding=DEFAULT_BINDING, parent_name='Parent One'):
    return {
        'schema': 1,
        'graph_id': 'fictional-assistant-graph',
        'revision': revision,
        'perspective_id': perspective,
        'scope': {'account_id': 'one', 'library_id': 'family-a'},
        'people': [
            {'id': 'child', 'name_en': 'Child One', 'name_zh': '示例儿童',
             'aliases': [], 'catalog_binding': {'person_id': '301',
                 'label': 'Sample Child / 示例儿童'}},
            {'id': 'parent', 'name_en': parent_name, 'name_zh': '示例家长一',
             'aliases': ['Mom One', '妈妈'], 'catalog_binding':
                 {'person_id': '302', 'label': 'Sample Adult / 示例成人'}
                 if parent_binding is DEFAULT_BINDING else parent_binding},
        ],
        'assertions': [
            {'id': 'relationship-one', 'subject_id': 'child', 'relation': 'mother',
             'object_id': 'parent', 'source': 'user'},
        ],
    }


class MutableKinshipProvider:
    def __init__(self, graph=None):
        self.graph = graph
        self.scope = {'account_id': 'one', 'library_id': 'family-a'}
        self.calls = []
        self.cycle_on_read = None
        self.cycle_graph = None

    def get(self, account_id, library_id):
        self.calls.append((account_id, library_id))
        if self.cycle_on_read is not None and len(self.calls) == self.cycle_on_read:
            self.graph = self.cycle_graph
            self.scope = self.cycle_graph_scope
            self.cycle_on_read = None
        if self.graph is None:
            return None
        if (self.scope.get('account_id') != account_id or
                self.scope.get('library_id') != library_id):
            return None
        return self.graph

    def install(self, document):
        self.graph = KinshipGraph(document)
        self.scope = document['scope']
        self.cycle_on_read = None
        self.cycle_graph = None


class AssistantKinshipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='assistant-kinship-')
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'synthetic.sqlite'
        self.trace = []
        with closing(sqlite3.connect(self.database)) as db, db:
            create(db)
            # Keep this fixture deliberately fictional and useful for a joint
            # people constraint: asset 103 has both reviewed fixture people.
            db.execute("UPDATE captions SET text='Sample Child and Sample Adult at Example Park' WHERE id=2")
            db.execute("UPDATE captions SET user_edited=1 WHERE id=2")
            db.execute('''CREATE TABLE access_stories (
                id TEXT PRIMARY KEY, asset_id INTEGER NOT NULL, library_id TEXT NOT NULL,
                author_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
                text TEXT NOT NULL, updated_at INTEGER NOT NULL,
                deleted INTEGER NOT NULL DEFAULT 0)''')
            db.commit()
            self.index = reviewed(AccessService(db, clock=lambda: NOW))
        self.access = AccessRuntime(self.connection, ORIGIN, clock=lambda: NOW)
        self.kinship = MutableKinshipProvider()
        self.kinship.install(assistant_graph())
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
        runtime = DiscoveryRuntime(self.access, MemoryIndexProvider((index,)), d.ReadBudget())
        self.discovery_runtime = runtime
        app = create_app(access_runtime=self.access, discovery_runtime=runtime,
                         assistant_enabled=True, assistant_kinship_provider=self.kinship)
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

    def turn(self, words, *, context=None, token=TOKEN, library='family-a'):
        return self.client.post('/assistant/v1/turns',
            json={'library_id': library, 'text': words, 'context': context},
            headers={'Authorization': 'Bearer ' + token} | SEARCH_V2)

    def test_bare_mom_resolves_to_current_reviewed_catalog_person(self):
        response = self.turn('找妈妈的照片')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters']['people'], {'ids': ['302'], 'match': 'any'})
        self.assertEqual([item['id'] for item in body['items']], ['103'])
        self.assertNotIn('Child One', response.text)
        self.assertNotIn('Parent One', response.text)
        self.assertNotIn('示例家长一', response.text)

    def test_conjunction_keeps_anchor_and_relative_as_all_filter(self):
        response = self.turn('找示例儿童和妈妈一起的照片')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters']['people'], {'ids': ['301', '302'], 'match': 'all'})
        self.assertEqual([item['id'] for item in body['items']], ['103'])

    def test_quoted_kinship_word_stays_a_literal_text_filter(self):
        response = self.turn('找包含“妈妈”的照片')
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body['kind'], 'results', body)
        self.assertEqual(body['filters'], {'media': ['image'], 'text': '妈妈'})
        self.assertNotIn('people', body['filters'])

    def test_foreign_account_or_library_never_uses_this_private_graph(self):
        self.kinship.calls.clear()
        other_account = self.turn('找妈妈的照片', token=SECOND)
        self.assertEqual(other_account.status_code, 200, other_account.text)
        self.assertIn(other_account.json()['kind'], ('clarification', 'unsupported'))
        self.assertEqual(other_account.json()['items'], [])
        self.assertEqual(self.kinship.calls, [('two', 'family-a')])

        self.kinship.calls.clear()
        unauthorized_library = self.turn('找妈妈的照片', library='family-b')
        self.assertEqual(unauthorized_library.status_code, 401, unauthorized_library.text)
        self.assertEqual(self.kinship.calls, [])

    def test_membership_revocation_precedes_private_graph_read(self):
        self.kinship.calls.clear()
        self.mutate("UPDATE access_memberships SET status='revoked' WHERE account_id='one'")
        denied = self.turn('找妈妈的照片')
        self.assertEqual(denied.status_code, 401, denied.text)
        self.assertEqual(self.kinship.calls, [])

    def test_missing_or_ambiguous_catalog_binding_clarifies_without_search_results(self):
        cases = (
            ('missing', assistant_graph(parent_binding={'person_id': '999', 'label': 'Missing Person'}), None),
            ('ambiguous', assistant_graph(parent_binding=None, parent_name='Sample Adult'),
             ReviewedPerson('family-a', '303', 'Other Sample Adult', ('Sample Adult',), True)),
        )
        for label, document, extra in cases:
            with self.subTest(label=label):
                self.kinship.install(document)
                index = self.index
                if extra is not None:
                    index = replace(index, people=index.people + (extra,))
                self.install(index)
                response = self.turn('找妈妈的照片')
                self.assertEqual(response.status_code, 200, response.text)
                body = response.json()
                self.assertIn(body['kind'], ('clarification', 'unsupported'), body)
                self.assertEqual(body['items'], [])
                self.assertIsNone(body['context'])

    def test_graph_revision_or_perspective_change_invalidates_old_context(self):
        first = self.turn('找妈妈的照片')
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['kind'], 'results', first.json())
        context = first.json()['context']
        for document in (assistant_graph(revision='kinship-revision-2'),
                         assistant_graph(perspective='parent')):
            with self.subTest(revision=document['revision'], perspective=document['perspective_id']):
                self.kinship.install(document)
                stale = self.turn('介绍这些结果', context=context)
                self.assertEqual(stale.status_code, 409, stale.text)

    def test_graph_change_during_response_preparation_withholds_results(self):
        changed = assistant_graph(revision='kinship-revision-during-query')
        self.kinship.cycle_graph = KinshipGraph(changed)
        self.kinship.cycle_graph_scope = changed['scope']
        self.kinship.cycle_on_read = len(self.kinship.calls) + 2

        response = self.turn('找妈妈的照片')
        self.assertIn(response.status_code, (200, 409), response.text)
        if response.status_code == 200:
            self.assertNotEqual(response.json()['kind'], 'results', response.json())
            self.assertEqual(response.json()['items'], [])
        self.assertNotIn('Parent One', response.text)
        self.assertNotIn('示例家长一', response.text)

    def test_graph_deletion_fails_closed_for_old_context_and_fresh_relative_query(self):
        first = self.turn('找妈妈的照片')
        self.assertEqual(first.status_code, 200, first.text)
        context = first.json()['context']
        self.kinship.graph = None

        stale = self.turn('介绍这些结果', context=context)
        self.assertEqual(stale.status_code, 409, stale.text)
        fresh = self.turn('找妈妈的照片')
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertIn(fresh.json()['kind'], ('clarification', 'unsupported'))
        self.assertEqual(fresh.json()['items'], [])

    def test_shared_allowlist_uses_real_private_loader_and_removal_withholds_old_results(self):
        from app.access.kinship import PrivateKinshipProvider
        root = self.database.parent.resolve()
        path = root / 'private-kinship.json'
        document = assistant_graph()
        document['scope'] = {'account_ids': ['one', 'two'], 'library_id': 'family-a'}
        path.write_text(json.dumps(document), encoding='utf-8')
        os.chmod(path, 0o600)
        self.kinship = PrivateKinshipProvider(path, source_root=ROOT.parent)
        self.install(self.index)
        first = self.turn('找妈妈的照片', token=SECOND)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['filters']['people'], {'ids': ['302'], 'match': 'any'})
        self.assertEqual(self.turn('找妈妈的照片').json()['kind'], 'results')
        document['scope']['account_ids'] = ['one']
        document['revision'] = 'allowlist-revision-two'
        path.write_text(json.dumps(document), encoding='utf-8')
        stale = self.turn('介绍这些结果', context=first.json()['context'], token=SECOND)
        self.assertEqual(stale.status_code, 409, stale.text)
        fresh = self.turn('找妈妈的照片', token=SECOND)
        self.assertEqual(fresh.status_code, 200, fresh.text)
        self.assertEqual(fresh.json()['kind'], 'clarification', fresh.json())
        self.assertEqual(fresh.json()['items'], [])


if __name__ == '__main__':
    unittest.main()

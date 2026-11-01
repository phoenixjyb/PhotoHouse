"""Bounded reviewed-name context for saved-story refinement; synthetic SQLite only."""
from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests' / 'security')]

from app.access import discovery as d
from app.access.discovery_provider import MemoryIndexProvider, ReviewedPerson
from app.access.discovery_transport import DiscoveryRuntime
from app.access.kinship import KinshipGraph
from app.access.runtime import AccessRuntime
from app.access.service import AccessService
from app.access.story_refinement_context import (
    MAX_RELATED_PEOPLE, StoryRefinementContextError, resolve,
)
from phone_discovery_fixture import create, reviewed, TOKEN, NOW

_DEFAULT = object()


class StoryRefinementContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='story-refinement-context-')
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / 'fixture.sqlite'
        with closing(sqlite3.connect(self.database)) as db:
            create(db)
            self.index = reviewed(AccessService(db, clock=lambda: NOW))
        self.access_runtime = AccessRuntime(self.connection, 'https://fixture.example.test',
                                            clock=lambda: NOW)
        self.install(self.index)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.database, timeout=.25)
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
        finally:
            db.close()

    def install(self, index):
        self.index = index
        self.discovery_runtime = DiscoveryRuntime(
            self.access_runtime, MemoryIndexProvider((index,)), d.ReadBudget())

    def call(self, narration, *, token=TOKEN, library='family-a',
             discovery_runtime=_DEFAULT, kinship_provider=None):
        with self.connection() as db:
            access = AccessService(db, clock=lambda: NOW)
            with access._transaction():
                principal = access._member(token, library)
                return resolve(access, library, principal, narration,
                    discovery_runtime=(self.discovery_runtime if discovery_runtime is _DEFAULT
                                       else discovery_runtime),
                    kinship_provider=kinship_provider)

    def graph(self, *, account='one', library='family-a', person_id='301',
              binding_label='Sample Child / 示例儿童', graph_id='fixture-graph', revision=1,
              name_en='Avery Chen', name_zh='周雨桐', aliases=()):
        return KinshipGraph({
            'schema': 1, 'graph_id': graph_id, 'revision': revision,
            'perspective_id': 'person-self',
            'scope': {'account_id': account, 'library_id': library},
            'people': [
                {'id': 'person-self', 'name_en': 'Self', 'name_zh': None,
                 'aliases': [], 'catalog_binding': None},
                {'id': 'person-reviewed', 'name_en': name_en, 'name_zh': name_zh,
                 'aliases': list(aliases),
                 'catalog_binding': {'person_id': person_id, 'label': binding_label}},
            ],
            'assertions': [],
        })

    def test_only_mentioned_reviewed_people_are_returned_in_closed_dto(self):
        people, _identity = self.call('Sample Child joined the picnic.')
        self.assertEqual(people, [{'name': 'Sample Child / 示例儿童',
                                  'aliases': ['Sample Child', '示例儿童']}])
        self.assertEqual(set(people[0]), {'name', 'aliases'})
        self.assertNotIn('id', people[0])
        self.assertNotIn('library_id', people[0])

    def test_graph_adds_chinese_canonical_name_only_after_unique_reviewed_join(self):
        first = replace(self.index.people[0], label='Avery Chen', aliases=('Avery',))
        self.install(replace(self.index, people=(first, self.index.people[1])))
        provider = lambda *_args: self.graph(binding_label='Avery Chen')
        class Provider:
            def get(self, account, library):
                return provider(account, library)
        people, _identity = self.call('Avery arrived.', kinship_provider=Provider())
        self.assertEqual(people, [{'name': '周雨桐', 'aliases': ['Avery Chen', 'Avery']}])

    def test_english_graph_alias_finds_a_chinese_catalog_identity_in_multiline_narration(self):
        first = replace(self.index.people[0], label='周雨桐', aliases=())
        self.install(replace(self.index, people=(first, self.index.people[1])))
        graph = self.graph(binding_label='周雨桐', name_en='Avery Chen', aliases=('Avery',))
        class Provider:
            def get(self, account, library):
                return graph
        people, _identity = self.call('回忆标题\nAvery或者雨同在公园玩耍。', kinship_provider=Provider())
        self.assertEqual(people, [{'name': '周雨桐', 'aliases': ['Avery Chen', 'Avery']}])

    def test_ambiguous_graph_name_binding_adds_no_graph_identity(self):
        first = replace(self.index.people[0], label='Avery Chen', aliases=())
        second = replace(self.index.people[1], label='Sample Adult', aliases=())
        self.install(replace(self.index, people=(first, second)))
        graph = self.graph(name_en='Avery Chen', name_zh='周雨桐', aliases=('Sample Adult',))
        class Provider:
            def get(self, account, library):
                return graph
        people, _identity = self.call('Avery Chen arrived.', kinship_provider=Provider())
        self.assertEqual(people, [{'name': 'Avery Chen', 'aliases': []}])

    def test_rejects_wrong_member_scope_before_provider_lookup(self):
        class ExplodingProvider:
            def get(self, _library):
                raise AssertionError('provider lookup must follow member scope check')
        wrong_scope = DiscoveryRuntime(self.access_runtime, ExplodingProvider(), d.ReadBudget())
        with self.connection() as db:
            access = AccessService(db, clock=lambda: NOW)
            with access._transaction():
                principal = access._member(TOKEN, 'family-a')
                with self.assertRaises(StoryRefinementContextError):
                    resolve(access, 'family-b', principal, 'Avery Chen',
                            discovery_runtime=wrong_scope)

    def test_busy_shared_discovery_budget_is_transient_not_source_staleness(self):
        from app.access.story_refinement_context import StoryRefinementContextBusy
        budget=self.discovery_runtime.budget
        held=[]
        while budget.slots.acquire(blocking=False):
            held.append(True)
        try:
            with self.assertRaises(StoryRefinementContextBusy):
                self.call('Sample Child')
        finally:
            for _ in held:
                budget.slots.release()
        self.assertTrue(self.call('Sample Child')[0])

    def test_rejects_stale_index_source(self):
        with closing(sqlite3.connect(self.database)) as db, db:
            db.execute("UPDATE captions SET text='changed source' WHERE id=1")
        with self.assertRaises(StoryRefinementContextError):
            self.call('Sample Child')

    def test_rejects_configured_index_from_another_library(self):
        tampered = replace(self.index, library_id='family-b')
        class Provider:
            def get(self, _library):
                return tampered
        wrong_runtime = DiscoveryRuntime(self.access_runtime,
            Provider(), d.ReadBudget())
        with self.assertRaises(StoryRefinementContextError):
            self.call('Sample Child', discovery_runtime=wrong_runtime)

    def test_reviewed_alias_changes_change_identity_digest(self):
        first = replace(self.index.people[0], label='Avery Chen', aliases=('Avery',))
        self.install(replace(self.index, people=(first, self.index.people[1])))
        _people1, identity1 = self.call('Avery')
        changed = replace(first, aliases=('Avery', 'A. Chen'))
        self.install(replace(self.index, people=(changed, self.index.people[1])))
        _people2, identity2 = self.call('Avery')
        self.assertNotEqual(identity1, identity2)

    def test_unmentioned_person_update_does_not_invalidate_the_selected_name_context(self):
        people1, identity1 = self.call('Sample Child joined the picnic.')
        other = replace(self.index.people[1], label='An Unmentioned Adult', aliases=('Other',))
        self.install(replace(self.index,revision='2',
                             people=(self.index.people[0],other)))
        people2, identity2 = self.call('Sample Child joined the picnic.')
        self.assertEqual(people1,people2)
        self.assertEqual(identity1,identity2)

    def test_graph_account_scope_mismatch_fails_closed(self):
        graph = self.graph(account='another-account')
        class Provider:
            def get(self, _account, _library):
                return graph
        with self.assertRaises(StoryRefinementContextError):
            self.call('Avery Chen', kinship_provider=Provider())

    def test_more_than_bound_related_people_refuses_context(self):
        people = tuple(ReviewedPerson('family-a', str(1000 + n),
                    f'Fictional Person {n:02d}') for n in range(MAX_RELATED_PEOPLE + 1))
        self.install(replace(self.index, people=people))
        narration = ' '.join(person.label for person in people)
        with self.assertRaises(StoryRefinementContextError):
            self.call(narration)

    def test_absent_optional_sources_yield_empty_context(self):
        people, identity = self.call('No reviewed person mentioned.', discovery_runtime=None,
                                     kinship_provider=None)
        self.assertEqual(people, [])
        self.assertRegex(identity, r'^[0-9a-f]{64}$')


if __name__ == '__main__':
    unittest.main()

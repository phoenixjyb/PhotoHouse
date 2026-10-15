"""Readiness uses protected search facts, not a second metadata inventory."""
from dataclasses import replace
from contextlib import closing
import json
import sqlite3
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]
import test_assistant_joint_search as fixture_module
from app.access import discovery as d
from app.access.assistant_search import SearchRuntime
from app.access.discovery_provider import ReviewedPerson
from app.access.kinship import KinshipGraph
from app.access.service import AccessDenied
from phone_discovery_fixture import TOKEN, OTHER


class SearchReadinessTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.AssistantJointSearchTests('test_text_union_dedup_reasons_and_authored_first_order')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def engine(self):
        return SearchRuntime(self.fixture.discovery_runtime)

    def test_counts_distinguish_catalog_indexed_and_searchable_video_dates(self):
        result = self.engine().call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertEqual((result['version'], result['search_version'], result['status']), (1, 2, 'current'))
        self.assertEqual((result['catalog_assets'], result['indexed_assets']), (4, 4))
        self.assertEqual(result['by_media']['image']['text_searchable'], 2)
        self.assertEqual(result['by_media']['image']['photo_memory'], 2)
        self.assertEqual(result['by_media']['image']['edited_caption'], 1)
        self.assertEqual(result['by_media']['video']['capture_dates_missing'], 1)
        self.assertEqual(result['by_media']['video']['capture_dates_searchable'], 0)
        self.assertEqual(result['reviewed_person_count'], 2)
        self.assertFalse(result['relevance_measured'])
        packed = json.dumps(result)
        for private in (TOKEN, 'family-a', 'Sample Child', '海边', 'note-101', 'one', 'not-a-real-path'):
            self.assertNotIn(private, packed)

    def test_unindexed_valid_dates_are_reported_without_claiming_searchability(self):
        self.fixture.mutate("UPDATE assets SET taken_at='2025-01-02' WHERE id=102")
        from phone_discovery_fixture import reviewed, NOW
        from app.access.service import AccessService
        with self.fixture.connection() as connection:
            index = reviewed(AccessService(connection, clock=lambda: NOW))
        self.fixture.install(replace(index, indexed_ids=tuple(a for a in index.indexed_ids if a != '102')))
        result = self.engine().call('readiness', TOKEN, 'family-a', lambda: False, {})
        video = result['by_media']['video']
        self.assertEqual((video['catalog_assets'], video['indexed_assets'], video['unindexed_assets']), (1, 0, 1))
        self.assertEqual((video['capture_dates_recorded'], video['capture_dates_searchable']), (1, 0))
        self.assertFalse(result['index_complete'])

    def test_disabled_date_people_fields_remain_unsearchable(self):
        self.fixture.install(replace(self.fixture.index, enabled=('media',)))
        result = self.engine().call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertEqual(result['enabled'], ['media', 'text'])
        self.assertEqual(result['by_media']['image']['capture_dates_recorded'], 2)
        self.assertEqual(result['by_media']['image']['capture_dates_searchable'], 0)
        self.assertEqual(result['reviewed_person_count'], 0)
        self.assertEqual(result['by_media']['image']['people_searchable'], 0)
        self.assertGreater(result['by_media']['image']['text_searchable'], 0)

    def test_authorization_precedes_provider_access_and_source_changes_refuse(self):
        class ExplodingProvider:
            def get(self, library):
                raise AssertionError('provider opened before membership')
        from app.access.discovery_transport import DiscoveryRuntime
        runtime = self.fixture.discovery_runtime
        engine = SearchRuntime(DiscoveryRuntime(runtime.access, ExplodingProvider(), runtime.budget))
        with self.assertRaises(AccessDenied):
            engine.call('readiness', OTHER, 'family-a', lambda: False, {})
        engine = self.engine()
        old = engine.call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.fixture.mutate("UPDATE captions SET text='changed' WHERE id=1")
        with self.assertRaises(d.DiscoveryChanged):
            engine.call('readiness', TOKEN, 'family-a', lambda: False, {'binding': old['binding']})

    def test_explicit_text_allowance_preserves_legacy_limits_and_shared_admission(self):
        budget = d.ReadBudget(source_bytes=32, search_source_bytes=256, concurrency=1)
        view = budget.search_view()
        self.assertIs(view.slots, budget.slots)
        self.assertEqual((view.rows, view.seconds, view.response_bytes, view.index_bytes),
                         (budget.rows, budget.seconds, budget.response_bytes, budget.index_bytes))
        with closing(sqlite3.connect(':memory:')) as db:
            with self.assertRaises(d.DiscoveryUnavailable):
                with budget.attempt(db, lambda: False) as (_, read):
                    read('SELECT ?', ('字' * 20,))
            with view.attempt(db, lambda: False) as (_, read):
                self.assertEqual(read('SELECT ?', ('字' * 20,)), [('字' * 20,)])
                with self.assertRaises(d.DiscoveryBusy):
                    with budget.attempt(db, lambda: False):
                        self.fail('search must not bypass shared admission')
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises(d.DiscoveryInvalid):
                d.ReadBudget(search_source_bytes=invalid)
        from app.access.discovery_index import shared_budget
        production = shared_budget(None)
        self.assertEqual((production.source_bytes, production.search_source_bytes),
                         (16 * 1024**2, 64 * 1024**2))
        self.assertEqual((production.seconds, production.search_seconds), (2.0, 5.0))

    def test_selected_text_deadline_stays_bounded_without_changing_legacy(self):
        elapsed = [0.0]
        budget = d.ReadBudget(seconds=2, search_seconds=5, clock=lambda: elapsed[0])
        with closing(sqlite3.connect(':memory:')) as db:
            with budget.attempt(db, lambda: False) as (check, _):
                elapsed[0] = 3.0
                with self.assertRaises(d.DiscoveryUnavailable):
                    check()
            elapsed[0] = 0.0
            with budget.search_view().attempt(db, lambda: False) as (check, _):
                elapsed[0] = 3.0
                check()
                elapsed[0] = 6.0
                with self.assertRaises(d.DiscoveryUnavailable):
                    check()
        for invalid in (0, -1, True, float('nan'), float('inf')):
            with self.assertRaises(d.DiscoveryInvalid):
                d.ReadBudget(search_seconds=invalid)

    def test_superseded_history_does_not_exhaust_current_text_projection(self):
        from app.access.discovery_provider import ProjectedIndex, MemoryIndexProvider
        from app.access.discovery_transport import DiscoveryRuntime
        with self.fixture.connection() as db:
            # This fixture connection is query-only; source writes use its own
            # mutation helper so ordinary reads retain the protected boundary.
            source = d.projected_source('family-a', lambda sql, args: db.execute(sql, args).fetchall(), ('media',))
        ids = tuple(str(row[0]) for row in source['assets'])
        index = ProjectedIndex(library_id='family-a', revision='1', scope_ids=ids,
                               indexed_ids=ids, source_digest=d.digest(source),
                               people=(), pinned_ids=(), assignments=(), places=(),
                               regions=(), enabled=('media',))
        self.fixture.mutate('''INSERT INTO captions(id,asset_id,text,user_edited,superseded)
                              SELECT 1000+value,101,?,0,1 FROM json_each(?)''',
                            ('old history ' * 100, json.dumps(list(range(100)))))
        budget = d.ReadBudget(rows=20, source_bytes=1024, search_source_bytes=32768)
        engine = SearchRuntime(DiscoveryRuntime(self.fixture.access, MemoryIndexProvider((index,)), budget))
        before = engine.call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertGreater(before['by_media']['image']['text_searchable'], 0)
        self.fixture.mutate("UPDATE captions SET text='changed old history' WHERE id=1000")
        after = engine.call('readiness', TOKEN, 'family-a', lambda: False, {'binding': before['binding']})
        self.assertEqual(after['binding'], before['binding'])
        self.fixture.mutate("UPDATE captions SET text='changed current caption' WHERE id=1")
        with self.assertRaises(d.DiscoveryChanged):
            engine.call('readiness', TOKEN, 'family-a', lambda: False, {'binding': before['binding']})

    def test_people_readiness_status_and_counts_are_aggregate(self):
        base_index = self.fixture.index
        engine = self.engine()
        result = engine.call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertEqual(result['people_readiness']['status'], 'available')
        self.assertEqual(result['people_readiness']['reviewed_people_with_assignments'], 2)
        self.assertEqual(result['people_readiness']['assigned_assets_searchable'], 2)

        disabled = replace(base_index, enabled=('date', 'media'), people=(),
                           pinned_ids=(), assignments=())
        self.fixture.install(disabled)
        result = self.engine().call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertEqual(result['people_readiness']['status'], 'disabled')

        empty = replace(base_index, people=(), pinned_ids=(), assignments=())
        self.fixture.install(empty)
        result = self.engine().call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertEqual(result['people_readiness']['status'], 'empty_roster')

        zero = replace(base_index,
                       people=(ReviewedPerson('family-a', '399', 'Synthetic Roster Person', (), True),),
                       pinned_ids=('399',), assignments=())
        self.fixture.install(zero)
        result = self.engine().call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertEqual(result['people_readiness']['status'], 'zero_assigned')
        self.assertEqual(result['people_readiness']['reviewed_people_allow_zero'], 1)

        partial = replace(base_index,
                          indexed_ids=tuple(a for a in base_index.indexed_ids if a != '102'))
        self.fixture.install(partial)
        result = self.engine().call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertEqual(result['people_readiness']['status'], 'partial_coverage')

    def test_date_readiness_issues_do_not_invent_capture_dates(self):
        disabled = replace(self.fixture.index, enabled=('media',), people=(),
                           pinned_ids=(), assignments=())
        self.fixture.install(disabled)
        result = self.engine().call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertIn({'code': 'capture_dates_recorded_but_index_disabled', 'count': 3},
                      result['issues'])
        self.assertEqual(result['date_basis'], 'capture')

        self.fixture.install(self.fixture.index)
        self.fixture.mutate("UPDATE assets SET taken_at='2025-01-02' WHERE id=102")
        from phone_discovery_fixture import reviewed, NOW
        from app.access.service import AccessService
        with self.fixture.connection() as connection:
            current = reviewed(AccessService(connection, clock=lambda: NOW))
        partial = replace(current,
                          indexed_ids=tuple(a for a in current.indexed_ids if a != '102'))
        self.fixture.install(partial)
        result = self.engine().call('readiness', TOKEN, 'family-a', lambda: False, {})
        self.assertIn({'code': 'capture_date_index_missing_coverage', 'count': 1}, result['issues'])

    def test_private_graph_binding_statuses_use_current_reviewed_catalog(self):
        base_index = self.fixture.index

        def document(*, child_binding=None, parent_binding=None, parent_name='Sample Adult'):
            if child_binding is None:
                child_binding = {'person_id': '301', 'label': 'Sample Child / 示例儿童'}
            if parent_binding is ...:
                parent_binding = {'person_id': '302', 'label': 'Sample Adult / 示例成人'}
            return {
                'schema': 1, 'graph_id': 'synthetic-graph', 'revision': 1,
                'perspective_id': 'child',
                'scope': {'account_id': 'one', 'library_id': 'family-a'},
                'people': [
                    {'id': 'child', 'name_en': 'Sample Child', 'name_zh': '示例儿童',
                     'aliases': [], 'catalog_binding': child_binding},
                    {'id': 'parent', 'name_en': parent_name, 'name_zh': '示例家长',
                     'aliases': [], 'catalog_binding': parent_binding},
                ],
                'assertions': [{'id': 'parent-one', 'subject_id': 'child',
                    'relation': 'mother', 'object_id': 'parent', 'source': 'user'}],
            }

        class Provider:
            def __init__(self, graph): self.graph = graph
            def get(self, account, library): return self.graph

        def report(graph, index=None):
            self.fixture.install(index if index is not None else base_index)
            return SearchRuntime(self.fixture.discovery_runtime, Provider(graph)).call(
                'readiness', TOKEN, 'family-a', lambda: False, {})

        current = report(KinshipGraph(document()))
        self.assertEqual(current['kinship_bindings']['status'], 'current')
        self.assertEqual((current['kinship_bindings']['unique'],
                          current['kinship_bindings']['unique_with_assignments']), (2, 2))
        serialized = json.dumps(current)
        for private in ('Sample Child', 'Sample Adult', 'synthetic-graph', '301', '302', 'family-a'):
            self.assertNotIn(private, serialized)

        stale = report(KinshipGraph(document(parent_binding={
            'person_id': '302', 'label': 'Old reviewed label'})))
        self.assertEqual(stale['kinship_bindings']['stale'], 1)

        missing = report(KinshipGraph(document(parent_binding=None, parent_name='Unlisted Person')))
        self.assertEqual(missing['kinship_bindings']['missing'], 1)

        ambiguous_index = replace(self.fixture.index, people=self.fixture.index.people + (
            ReviewedPerson('family-a', '303', 'Another Adult', ('Sample Adult',), True),))
        ambiguous = report(KinshipGraph(document(parent_binding=None)), ambiguous_index)
        self.assertEqual(ambiguous['kinship_bindings']['ambiguous'], 1)

        collision = report(KinshipGraph(document(child_binding={
            'person_id': '302', 'label': 'Sample Adult / 示例成人'})))
        self.assertEqual(collision['kinship_bindings']['ambiguous'], 2)

        allow_zero_index = replace(self.fixture.index,
            assignments=tuple(item for item in self.fixture.index.assignments if item.person_id != '302'),
            people=tuple(replace(item, allow_zero=True) if item.id == '302' else item
                         for item in self.fixture.index.people))
        allow_zero = report(KinshipGraph(document()), allow_zero_index)
        self.assertEqual(allow_zero['kinship_bindings']['unique_allow_zero'], 1)


if __name__ == '__main__':
    unittest.main()

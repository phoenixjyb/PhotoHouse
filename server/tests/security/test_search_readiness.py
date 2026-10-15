"""Readiness uses protected search facts, not a second metadata inventory."""
from dataclasses import replace
import json
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]
import test_assistant_joint_search as fixture_module
from app.access import discovery as d
from app.access.assistant_search import SearchRuntime
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


if __name__ == '__main__':
    unittest.main()

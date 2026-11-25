"""Focused checks for the exact image-only semantic derived-facts path."""
from contextlib import closing
import sqlite3
import unittest
from unittest.mock import patch

import test_semantic_bulk_search as bulk
import test_semantic_eligibility_search as eligibility
from app.access import discovery as d
from app.access.semantic_search import SemanticSearchReads
from phone_discovery_fixture import SECOND


class SemanticMediaOnlyFactsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = bulk.SemanticBulkEndpointTests(
            'test_bulk_matches_legacy_scores_order_and_paging_with_no_npy_query_reads')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_empty_filter_uses_exact_media_path_and_matches_general_response(self):
        original = SemanticSearchReads._facts

        def general_facts(reader, *args, **kwargs):
            enabled = reader._media_only_facts
            reader._media_only_facts = False
            try:
                return original(reader, *args, **kwargs)
            finally:
                reader._media_only_facts = enabled

        for query in ('family beach', '海边的孩子', 'Family beach 家庭'):
            with self.subTest(query=query):
                with patch.object(SemanticSearchReads, '_facts', general_facts):
                    general = self.fixture.query(query=query)
                fast = self.fixture.query(query=query)
                self.assertEqual(general.status_code, 200, general.text)
                self.assertEqual(fast.status_code, 200, fast.text)
                self.assertEqual(fast.json(), general.json())
                if fast.json()['has_more']:
                    args = {'query': query, 'filters': {}, 'page': 2,
                            'page_size': fast.json()['page_size'],
                            'binding': fast.json()['binding'],
                            'fingerprint': fast.json()['fingerprint']}
                    with patch.object(SemanticSearchReads, '_facts', general_facts):
                        general_page = self.fixture.query(**args)
                    fast_page = self.fixture.query(**args)
                    self.assertEqual(general_page.status_code, 200, general_page.text)
                    self.assertEqual(fast_page.status_code, 200, fast_page.text)
                    self.assertEqual(fast_page.json(), general_page.json())

    def test_any_additional_filter_keeps_general_facts_path(self):
        original = SemanticSearchReads._facts
        modes = []

        def observed(reader, *args, **kwargs):
            modes.append(reader._media_only_facts)
            return original(reader, *args, **kwargs)

        cases = (
            {'people': {'ids': ['301'], 'match': 'all'}},
            {'date': {'from': '2032-09-01', 'to': '2032-09-01'}},
            {'tags': {'ids': ['501'], 'match': 'all'}},
            {'locations': ['601']},
            {'text': 'Family beach'},
            {'caption': 'Family beach'},
        )
        with patch.object(SemanticSearchReads, '_facts', observed):
            for filters in cases:
                with self.subTest(filters=filters):
                    before = len(modes)
                    response = self.fixture.query(filters=filters)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(modes[before:], [False])
            before = len(modes)
            unsupported_descriptive = self.fixture.query(
                filters={'descriptive': 'red jacket'})
            self.assertEqual(unsupported_descriptive.status_code, 400,
                             unsupported_descriptive.text)
            self.assertEqual(modes[before:], [False])
            before = len(modes)
            unknown = self.fixture.query(filters={'unexpected': 'value'})
            self.assertEqual(unknown.status_code, 400, unknown.text)
            self.assertEqual(modes[before:], [False])
            before = len(modes)
            explicit_media = self.fixture.query(filters={'media': ['image']})
            self.assertEqual(explicit_media.status_code, 200, explicit_media.text)
            self.assertEqual(modes[before:], [True])
        self.assertTrue(modes)
        self.assertEqual(modes.count(True), 1)

    def test_media_only_mode_refuses_misconfigured_filters_and_keeps_consistency_checks(self):
        from app.access.service import AccessService

        with closing(sqlite3.connect(self.fixture.fixture.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            reader = SemanticSearchReads(AccessService(db),
                self.fixture.fixture.discovery_runtime.provider,
                self.fixture.runtime.discovery.budget,
                vector_root=self.fixture.root, encoder=self.fixture.encoder,
                query='scene', bulk_vectors=self.fixture.store,
                text_projection_required=False, media_only_facts=True)
            with self.assertRaises(d.DiscoveryUnavailable):
                reader._search_action('family-a', None,
                    {'media': ['video']}, allow_unbound_first_page=True)

            index = self.fixture.fixture.discovery_runtime.provider.get('family-a')
            people, places = d.validate(index, 'family-a', 100000)
            source = {'assets': [], 'faces': []}
            with self.assertRaises(d.DiscoveryChanged):
                reader._facts(index, source, people, places, lambda: None)

            source['faces'] = [
                (face.id, face.asset_id, face.person_id, face.source)
                for face in index.assignments]
            source.update(captions=[], tags=[], blocks=[], links=[])
            source['assets'] = [
                (int(asset_id), None, 64, 64, None, 'invalid-date', 11)
                for asset_id in index.scope_ids]
            reader._media_only_facts = False
            general_facts = reader._facts(index, source, people, places, lambda: None)
            reader._media_only_facts = True
            media_facts = reader._facts(index, source, people, places, lambda: None)
            self.assertEqual(media_facts[0], general_facts[0])

            unapproved = dict(people)
            from app.access.discovery_provider import ReviewedPerson
            unapproved['999'] = ReviewedPerson('family-a', '999', 'Unmatched', (), False)
            with self.assertRaises(d.DiscoveryUnavailable):
                reader._facts(index, source, unapproved, places, lambda: None)

    def test_cancellation_is_polled_for_each_indexed_row(self):
        from app.access.service import AccessService

        with closing(sqlite3.connect(self.fixture.fixture.database)) as db:
            db.execute('PRAGMA foreign_keys=ON')
            reader = SemanticSearchReads(AccessService(db),
                self.fixture.fixture.discovery_runtime.provider,
                self.fixture.runtime.discovery.budget,
                vector_root=self.fixture.root, encoder=self.fixture.encoder,
                query='scene', bulk_vectors=self.fixture.store,
                text_projection_required=False, media_only_facts=True)
            index = self.fixture.fixture.discovery_runtime.provider.get('family-a')
            people, places = d.validate(index, 'family-a', 100000)
            source = {'assets': [], 'faces': [
                (face.id, face.asset_id, face.person_id, face.source)
                for face in index.assignments]}
            checks = 0

            def cancel_on_first_indexed_row():
                nonlocal checks
                checks += 1
                if checks == len(source['assets']) + len(index.assignments) + 1:
                    raise d.DiscoveryCancelled()

            with self.assertRaises(d.DiscoveryCancelled):
                reader._facts(index, source, people, places,
                              cancel_on_first_indexed_row)
            self.assertEqual(checks,
                len(source['assets']) + len(index.assignments) + 1)


class SemanticMediaOnlyQualificationGuardTests(unittest.TestCase):
    def setUp(self):
        self.fixture = eligibility.SemanticEligibilityEndpointTests(
            'test_policy_change_during_encoding_and_after_warm_cache_refuses')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_policy_source_and_membership_changes_still_refuse_after_provider(self):
        from app.access.semantic_eligibility import SemanticEligibilityStore

        original_extra = SemanticSearchReads._extra_source_fresh
        original_policy = SemanticEligibilityStore.read_and_validate
        counts = {'fresh_source': 0, 'policy': 0}

        def count_extra(reader, *args, **kwargs):
            counts['fresh_source'] += 1
            return original_extra(reader, *args, **kwargs)

        def count_policy(store, *args, **kwargs):
            counts['policy'] += 1
            return original_policy(store, *args, **kwargs)

        with patch.object(SemanticSearchReads, '_extra_source_fresh', count_extra), \
                patch.object(SemanticEligibilityStore, 'read_and_validate', count_policy):
            warm = self.fixture.query()
        self.assertEqual(warm.status_code, 200, warm.text)
        self.assertEqual(counts, {'fresh_source': 2, 'policy': 2})

        policy_bytes = self.fixture.policy_path.read_bytes()
        self.fixture.during_encode = lambda: self.fixture.policy_path.write_bytes(
            policy_bytes + b' ')
        changed_policy = self.fixture.query()
        self.assertEqual(changed_policy.status_code, 503, changed_policy.text)
        self.assertNotIn('items', changed_policy.json())
        self.fixture.during_encode = None
        self.fixture.policy_path.write_bytes(policy_bytes)

        self.fixture.during_encode = lambda: self.fixture.fixture.mutate(
            "UPDATE captions SET text='changed during encoding' WHERE id=1")
        changed_source = self.fixture.query()
        self.assertEqual(changed_source.status_code, 409, changed_source.text)
        self.assertNotIn('items', changed_source.json())
        self.fixture.during_encode = None
        self.fixture.fixture.mutate(
            "UPDATE captions SET text='海边 Ｆａｍｉｌｙ Beach Day 示例儿童' WHERE id=1")

        self.fixture.during_encode = lambda: self.fixture.fixture.mutate(
            "UPDATE access_memberships SET status='revoked' WHERE account_id='two'")
        revoked = self.fixture.query(token=SECOND)
        self.assertIn(revoked.status_code, (401, 403), revoked.text)
        self.assertNotIn('items', revoked.json())

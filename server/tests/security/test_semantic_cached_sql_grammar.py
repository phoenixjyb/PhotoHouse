"""Focused checks for reusing only an exact Store-cohort SQL grammar proof."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import test_semantic_bulk_search as endpoint_tests
import test_semantic_eligibility_search as eligibility_tests
from app.access.semantic_bulk_vectors import BulkVectorStore, BulkVectorUnavailable, _CacheGeneration
from app.access.visual_vector_loader import _COLUMNS


class SemanticCachedSQLGrammarEndpointTests(unittest.TestCase):
    """Exercise the bridge through the existing synthetic API fixture."""

    query = endpoint_tests.SemanticBulkEndpointTests.query
    add_generated_cohort = endpoint_tests.SemanticBulkEndpointTests.add_generated_cohort
    _install_runtime = endpoint_tests.SemanticBulkEndpointTests._install_runtime
    _client = endpoint_tests.SemanticBulkEndpointTests._client
    select_policy = eligibility_tests.SemanticEligibilityEndpointTests.select_policy

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='semantic-cached-grammar-')
        self.addCleanup(directory.cleanup)
        self.bulk_directory = Path(directory.name).resolve()
        self.generation = 0
        eligibility_tests.SemanticEligibilityEndpointTests.setUp(self)

    def test_next_request_uses_exact_store_grammar_proof_with_full_response_parity(self):
        from app.access import semantic_search

        first = self.query()
        self.assertEqual(first.status_code, 200, first.text)
        original_bridge = BulkVectorStore._artifacts_from_current_sql
        bridge_calls = []

        def count_bridge(store, *args, **kwargs):
            result = original_bridge(store, *args, **kwargs)
            bridge_calls.append(result is not None)
            return result

        with patch.object(BulkVectorStore, '_artifacts_from_current_sql', count_bridge), \
                patch.object(semantic_search, '_validated_rows',
                             side_effect=AssertionError('warm exact cohort should reuse grammar proof')):
            second = self.query()
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(bridge_calls)
        self.assertTrue(any(bridge_calls))
        self.assertEqual(second.json(), first.json())

    def test_cold_store_miss_falls_back_to_full_artifact_parser(self):
        from app.access import semantic_search

        original_bridge = BulkVectorStore._artifacts_from_current_sql
        bridge_calls = []

        def observe_cold_miss(store, *args, **kwargs):
            result = original_bridge(store, *args, **kwargs)
            bridge_calls.append(result)
            return result

        with patch.object(BulkVectorStore, '_artifacts_from_current_sql', observe_cold_miss), \
                patch.object(semantic_search, '_validated_rows',
                             wraps=semantic_search._validated_rows) as validate:
            response = self.query()
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(bridge_calls)
        self.assertTrue(all(result is None for result in bridge_calls))
        self.assertEqual(validate.call_count, 1)

    def test_changed_sql_row_misses_bridge_parses_and_refuses_stale_bulk_cohort(self):
        from app.access import semantic_search

        self.assertEqual(self.query().status_code, 200)
        original_extra = semantic_search.SemanticSearchReads._extra_source_fresh

        def changed_sql(reader, index, source, read, check):
            def changed_read(sql, args):
                rows = read(sql, args)
                if 'FROM image_vector_artifacts v' not in sql:
                    return rows
                changed = list(rows)
                first = list(changed[0])
                first[14] += 1
                changed[0] = tuple(first)
                return changed
            return original_extra(reader, index, source, changed_read, check)

        with patch.object(semantic_search.SemanticSearchReads, '_extra_source_fresh', changed_sql), \
                patch.object(semantic_search, '_validated_rows',
                             wraps=semantic_search._validated_rows) as validate:
            response = self.query()
        self.assertEqual(response.status_code, 503, response.text)
        self.assertNotIn('items', response.json())
        self.assertEqual(validate.call_count, 1)

    def test_bridge_requires_exact_order_types_values_and_current_pins(self):
        from app.access import semantic_bulk_vectors as bulk

        warm = self.query()
        self.assertEqual(warm.status_code, 200, warm.text)
        store = self.store
        identity = self.runtime.encoder.binding.image_identity
        columns = tuple(_COLUMNS.split(','))
        # The exact rows are also retained on the reader path; these generated
        # SQL-shaped primitives provide input for the Store's proof bridge.
        rows = tuple(tuple(getattr(record, name) if name != 'asset_id'
                           else int(record.asset_id) for name in columns)
                     for record in self.records)

        # A warmed generation is required; before it exists the bridge is a
        # clean miss and ordinary grammar validation remains authoritative.
        cold = BulkVectorStore(store.path, store.file_sha256, store.library_id, identity)
        self.assertIsNone(cold._artifacts_from_current_sql(
            rows, library_id='family-a', identity=identity))

        copies = store._artifacts_from_current_sql(
            rows, library_id='family-a', identity=identity)
        self.assertIsNotNone(copies)
        self.assertEqual(tuple(copies), tuple(record.asset_id for record in self.records))
        self.assertTrue(all(copies[record.asset_id] == record
                            and copies[record.asset_id] is not record for record in self.records))
        generation = store._cache
        malformed_row = list(generation[1][0])
        malformed_row[8] = True  # bool must not pass as the cached integer dimension.
        malformed_cohort = (tuple(malformed_row), *generation[1][1:])
        with self.assertRaises(BulkVectorUnavailable):
            _CacheGeneration(generation[0], malformed_cohort, generation[2])

        variants = []
        class StringSubclass(str):
            pass

        for position, value in enumerate(rows[0]):
            changed = list(rows[0])
            changed[position] = value + 1 if type(value) is int else value + '-changed'
            variants.append((tuple(changed), *rows[1:]))
            changed = list(rows[0])
            changed[position] = (float(value) if type(value) is int else None)
            variants.append((tuple(changed), *rows[1:]))
        changed = list(rows[0]); changed[0] = StringSubclass(changed[0])
        variants.append((tuple(changed), *rows[1:]))
        for variant in variants:
            with self.subTest(row=variant[0]):
                self.assertIsNone(store._artifacts_from_current_sql(
                    variant, library_id='family-a', identity=identity))
        self.assertIsNone(store._artifacts_from_current_sql(
            rows[:-1], library_id='family-a', identity=identity))
        self.assertIsNone(store._artifacts_from_current_sql(
            (*rows, rows[-1]), library_id='family-a', identity=identity))
        self.assertIsNone(store._artifacts_from_current_sql(
            tuple(reversed(rows)), library_id='family-a', identity=identity))
        self.assertIsNone(store._artifacts_from_current_sql(
            (rows[0], rows[0]), library_id='family-a', identity=identity))
        self.assertIsNone(store._artifacts_from_current_sql(
            (rows[0][:-1], *rows[1:]), library_id='family-a', identity=identity))
        self.assertIsNone(store._artifacts_from_current_sql(
            rows, library_id='family-b', identity=identity))
        self.assertIsNone(store._artifacts_from_current_sql(
            rows, library_id='family-a',
            identity=type(identity)(identity.artifact_sha256, identity.preprocessing_sha256,
                identity.vector_space_id, 'different-model', identity.dimension,
                identity.normalization)))

        with patch.object(bulk, '_ARTIFACT_SQL_FIELDS', tuple(reversed(columns))):
            self.assertIsNone(store._artifacts_from_current_sql(
                rows, library_id='family-a', identity=identity))

        original_cache = store._cache
        object.__setattr__(store, '_cache', ())
        try:
            with self.assertRaises(BulkVectorUnavailable):
                store._artifacts_from_current_sql(
                    rows, library_id='family-a', identity=identity)
        finally:
            object.__setattr__(store, '_cache', original_cache)

        prior_file_sha = store.file_sha256
        object.__setattr__(store, 'file_sha256', 'f' * 64)
        try:
            self.assertIsNone(store._artifacts_from_current_sql(
                rows, library_id='family-a', identity=identity))
        finally:
            object.__setattr__(store, 'file_sha256', prior_file_sha)

    def test_callback_mutation_cannot_publish_a_stale_match(self):
        self.assertEqual(self.query().status_code, 200)
        rows = tuple(tuple(getattr(record, name) if name != 'asset_id'
                           else int(record.asset_id) for name in _COLUMNS.split(','))
                     for record in self.records)
        original_cache = self.store._cache
        checks = [0]

        def replace_cache():
            checks[0] += 1
            if checks[0] == 2:
                object.__setattr__(self.store, '_cache', None)

        result = self.store._artifacts_from_current_sql(
            rows, library_id='family-a',
            identity=self.runtime.encoder.binding.image_identity, check=replace_cache)
        self.assertIsNone(result)
        self.assertIsNot(self.store._cache, original_cache)

        object.__setattr__(self.store, '_cache', original_cache)
        checks[0] = 0
        identity = self.store.identity
        original_version = identity.model_version

        def mutate_identity():
            checks[0] += 1
            if checks[0] == 2:
                object.__setattr__(identity, 'model_version', 'mutated-generation')

        try:
            result = self.store._artifacts_from_current_sql(
                rows, library_id='family-a', identity=identity, check=mutate_identity)
        finally:
            object.__setattr__(identity, 'model_version', original_version)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()

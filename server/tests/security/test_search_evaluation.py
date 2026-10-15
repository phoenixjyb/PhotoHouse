"""Private relevance evaluator: bounded reports and protected local search only."""
from contextlib import closing, contextmanager
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests' / 'security'))

from app.access import discovery as d
from app.access.assistant_search import SearchRuntime
from app.access.discovery_provider import MemoryIndexProvider
from app.access.discovery_transport import DiscoveryRuntime
from app.access.search_evaluation import evaluate_cases
from app.access.service import AccessDenied, AccessService
from app.access.transport import AccessRuntime
from phone_discovery_fixture import create, reviewed, TOKEN, NOW


class FakeEngine:
    def __init__(self):
        self.calls = []
        self.presentation_count = 0
        self.fail_presentation = None

    def call(self, operation, token, library, cancelled, values):
        self.calls.append((operation, dict(values)))
        if operation == 'readiness':
            return {'version': 1, 'search_version': 2, 'binding': 'a' * 64}
        if operation == 'presentation':
            self.presentation_count += 1
            if self.fail_presentation == self.presentation_count:
                raise d.DiscoveryChanged()
            return {'version': 2}
        raise AssertionError(operation)


class SearchEvaluationTests(unittest.TestCase):
    def test_fake_turn_metrics_are_bounded_and_do_not_return_private_values(self):
        engine = FakeEngine()
        seen_previous = []

        def turn(_engine, _token, _library, words, previous, clock):
            seen_previous.append(previous)
            if words == 'private query one':
                return {'kind': 'results', 'context': {'opaque': 'context-secret'},
                        'filters': {'text': 'caption-secret'}, 'items': [
                            {'id': '103', 'label': 'private label'}, {'id': '101'}],
                        'total': 2, 'has_more': False, 'effect': None, 'reply': 'private reply'}
            return {'kind': 'open', 'context': previous, 'filters': {},
                    'items': [{'id': '103'}], 'total': 1,
                    'has_more': False,
                    'effect': {'type': 'open_asset', 'asset_id': '103'}, 'reply': 'private reply'}

        document = {'version': 1, 'cases': [
            {'id': 'first', 'text': 'private query one', 'expect': {
                'kind': 'results', 'filters': {'text': 'caption-secret'},
                'top_ids': ['103', '101'], 'relevant_ids': ['101'],
                'absent_ids': ['999'], 'total': 2, 'effect': None}},
            {'id': 'second', 'text': 'private query two', 'after': 'first', 'expect': {
                'kind': 'open', 'relevant_ids': ['103'],
                'effect': {'type': 'open_asset', 'asset_id': '103'}}},
        ]}
        ticks = iter((10.0, 10.005, 11.0, 11.002))
        with patch('app.access.assistant._turn', side_effect=turn):
            report = evaluate_cases(engine, TOKEN, 'family-a', document,
                                    clock=lambda: NOW, monotonic=lambda: next(ticks))

        self.assertEqual(report['version'], 1)
        self.assertEqual((report['case_count'], report['passed_count'], report['failed_count']), (2, 2, 0))
        self.assertEqual(report['cases'][0]['result_count'], 2)
        self.assertTrue(report['cases'][0]['hit_at_20'])
        self.assertEqual(report['cases'][0]['reciprocal_rank_at_20'], .5)
        self.assertEqual(report['relevance'], {'evaluated_case_count': 2, 'hit_count': 2, 'mrr_at_20': .75})
        self.assertIsNone(seen_previous[0])
        self.assertEqual(seen_previous[1], {'opaque': 'context-secret'})
        self.assertEqual([name for name, _ in engine.calls].count('presentation'), 4)
        packed = json.dumps(report, sort_keys=True)
        for private in ('private query', 'caption-secret', 'context-secret', 'private label',
                        'private reply', '103', '101', '999'):
            self.assertNotIn(private, packed)

    def test_validation_rejects_entire_document_before_engine_access(self):
        engine = FakeEngine()
        malformed = {'version': 1, 'cases': [
            {'id': 'ok', 'text': 'query', 'expect': {'kind': 'results'}},
            {'id': 'bad', 'text': 'query', 'expect': {'kind': 'results', 'unknown': True}},
        ]}
        with self.assertRaises(d.DiscoveryInvalid):
            evaluate_cases(engine, TOKEN, 'family-a', malformed, clock=lambda: NOW)
        self.assertEqual(engine.calls, [])

    def test_clarification_records_relevance_miss_and_skips_missing_context_dependency(self):
        engine = FakeEngine()
        turns = []

        def turn(_engine, _token, _library, words, previous, clock):
            turns.append((words, previous))
            return {'kind': 'clarification', 'context': None, 'filters': None,
                    'items': [], 'total': 0, 'has_more': False, 'effect': None}

        document = {'version': 1, 'cases': [
            {'id': 'clarify', 'text': 'private uncertain query', 'expect': {
                'kind': 'clarification', 'relevant_ids': ['103']}},
            {'id': 'followup', 'text': 'private followup query', 'after': 'clarify', 'expect': {
                'kind': 'results', 'relevant_ids': ['103']}},
        ]}
        with patch('app.access.assistant._turn', side_effect=turn):
            report = evaluate_cases(engine, TOKEN, 'family-a', document,
                                    clock=lambda: NOW, monotonic=iter((1.0, 1.01, 2.0, 2.01)).__next__)

        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0][1], None)
        self.assertTrue(report['cases'][0]['checks']['kind'])
        self.assertFalse(report['cases'][0]['passed'])
        self.assertFalse(report['cases'][0]['checks']['relevant_ids'])
        self.assertFalse(report['cases'][0]['hit_at_20'])
        self.assertEqual(report['cases'][0]['reciprocal_rank_at_20'], 0.0)
        self.assertTrue(report['cases'][1]['checks']['context_missing'])
        self.assertFalse(report['cases'][1]['passed'])
        self.assertEqual(report['cases'][1]['result_count'], 0)
        self.assertFalse(report['cases'][1]['hit_at_20'])
        self.assertEqual(report['relevance'], {'evaluated_case_count': 2, 'hit_count': 0, 'mrr_at_20': 0.0})
        packed = json.dumps(report)
        self.assertNotIn('private', packed)
        self.assertNotIn('103', packed)

    def test_absent_ids_are_unproven_when_more_results_exist(self):
        engine = FakeEngine()
        document = {'version': 1, 'cases': [
            {'id': 'page', 'text': 'private query', 'expect': {
                'kind': 'results', 'absent_ids': ['101']}}]}
        with patch('app.access.assistant._turn', return_value={
                'kind': 'results', 'context': {}, 'filters': {}, 'items': [{'id': '103'}],
                'total': 2, 'has_more': True, 'effect': None}):
            report = evaluate_cases(engine, TOKEN, 'family-a', document, clock=lambda: NOW)
        self.assertFalse(report['cases'][0]['checks']['absent_ids'])
        self.assertFalse(report['cases'][0]['passed'])

    def test_empty_results_are_a_relevance_miss_not_an_evaluator_error(self):
        engine = FakeEngine()
        document = {'version': 1, 'cases': [
            {'id': 'empty', 'text': 'private query', 'expect': {
                'kind': 'results', 'relevant_ids': ['103'], 'total': 0}}]}
        with patch('app.access.assistant._turn', return_value={
                'kind': 'results', 'context': None, 'filters': {}, 'items': [],
                'total': 0, 'has_more': False, 'effect': None}):
            report = evaluate_cases(engine, TOKEN, 'family-a', document, clock=lambda: NOW)
        self.assertFalse(report['cases'][0]['checks']['relevant_ids'])
        self.assertFalse(report['cases'][0]['passed'])
        self.assertFalse(report['cases'][0]['hit_at_20'])
        self.assertEqual(report['cases'][0]['reciprocal_rank_at_20'], 0.0)

    def test_backwards_monotonic_clock_is_rejected(self):
        engine = FakeEngine()
        document = {'version': 1, 'cases': [
            {'id': 'clock', 'text': 'private query', 'expect': {'kind': 'results'}}]}
        with patch('app.access.assistant._turn', return_value={
                'kind': 'results', 'context': {}, 'filters': {}, 'items': [],
                'total': 0, 'has_more': False, 'effect': None}):
            with self.assertRaises(d.DiscoveryInvalid):
                evaluate_cases(engine, TOKEN, 'family-a', document, clock=lambda: NOW,
                               monotonic=iter((2.0, 1.0)).__next__)

    def test_authorization_and_source_drift_raise_without_report_or_prose(self):
        import io
        from contextlib import redirect_stdout

        class Denied(FakeEngine):
            def call(self, operation, *args):
                if operation == 'readiness':
                    raise AccessDenied()
                return super().call(operation, *args)

        document = {'version': 1, 'cases': [
            {'id': 'one', 'text': 'private query', 'expect': {'kind': 'results'}}]}
        for engine, error in ((Denied(), AccessDenied()), (FakeEngine(), d.DiscoveryChanged())):
            if isinstance(engine, FakeEngine) and type(engine) is FakeEngine:
                engine.fail_presentation = 2
            output = io.StringIO()
            with redirect_stdout(output), patch('app.access.assistant._turn', return_value={
                    'kind': 'results', 'context': {}, 'filters': {}, 'items': [], 'total': 0}):
                with self.assertRaises(type(error)):
                    evaluate_cases(engine, TOKEN, 'family-a', document, clock=lambda: NOW)
            self.assertEqual(output.getvalue(), '')

    def test_real_sqlite_search_refine_and_open_chain_uses_actual_context(self):
        temporary = tempfile.TemporaryDirectory(prefix='search-evaluation-')
        self.addCleanup(temporary.cleanup)
        database = Path(temporary.name) / 'synthetic.sqlite'
        with closing(sqlite3.connect(database)) as db, db:
            create(db)
            db.execute("UPDATE assets SET taken_at='2032-09-01' WHERE id=101")
            db.execute("UPDATE assets SET taken_at='2032-09-02' WHERE id=103")
            db.execute("UPDATE captions SET text='海边 Family beach',user_edited=1 WHERE id=1")
            db.execute("UPDATE captions SET text='海边 at sunset',user_edited=0 WHERE id=2")
            db.execute('''CREATE TABLE access_stories (
                id TEXT PRIMARY KEY, asset_id INTEGER NOT NULL, library_id TEXT NOT NULL,
                author_id TEXT NOT NULL, revision INTEGER NOT NULL, title TEXT NOT NULL,
                text TEXT NOT NULL, updated_at INTEGER NOT NULL, deleted INTEGER NOT NULL DEFAULT 0)''')
            db.commit()
            index = reviewed(AccessService(db, clock=lambda: NOW))

        @contextmanager
        def connection():
            conn = sqlite3.connect(database, timeout=.25)
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA query_only=ON')
            try:
                yield conn
            finally:
                conn.close()

        access = AccessRuntime(connection, 'https://photohouse.example.test', clock=lambda: NOW)
        discovery = DiscoveryRuntime(access, MemoryIndexProvider((index,)), d.ReadBudget())

        engine = SearchRuntime(discovery)
        document = {'version': 1, 'cases': [
            {'id': 'search', 'text': '找包含“海边”的照片', 'expect': {
                'kind': 'results', 'filters': {'media': ['image'], 'text': '海边'},
                'relevant_ids': ['103', '101'], 'total': 2}},
            {'id': 'refine', 'text': '只看2032年9月的照片', 'after': 'search', 'expect': {
                'kind': 'results',
                'filters': {'date': {'from': '2032-09-01', 'to': '2032-09-30'},
                            'media': ['image'], 'text': '海边'},
                'relevant_ids': ['103', '101'], 'total': 2}},
            {'id': 'open', 'text': '打开第一张', 'after': 'refine', 'expect': {
                'kind': 'open', 'effect': {'type': 'open_asset', 'asset_id': '101'}}},
        ]}
        report = evaluate_cases(engine, TOKEN, 'family-a', document, clock=lambda: NOW)
        self.assertEqual((report['case_count'], report['passed_count'], report['failed_count']),
                         (3, 3, 0), report)
        self.assertEqual(report['relevance']['evaluated_case_count'], 2)
        self.assertEqual(report['cases'][2]['checks']['effect'], True)
        encoded = json.dumps(report)
        self.assertNotIn('海边', encoded)
        self.assertNotIn('asset_id', encoded)
        self.assertNotIn('103', encoded)


if __name__ == '__main__':
    unittest.main()

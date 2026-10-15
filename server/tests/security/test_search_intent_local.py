"""Offline transport and lifecycle checks for the opt-in local intent adapter."""
import json
from pathlib import Path
import sys
import threading
import unittest

import httpx
from httpx import SyncByteStream

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

from app.access.search_intent import IntentUnavailable
from app.access.search_intent_local import LocalIntentPlanner, MAX_PROVIDER_BYTES


def model_response(query, *, surface='red cake', alternatives=None, model='intent-local', done=True):
    proposal = {'version': 1, 'status': 'ready', 'question': None, 'concepts': [{
        'surface': surface, 'alternatives': alternatives or [surface, '红色蛋糕'],
    }]}
    envelope = {'model': model, 'done': done,
                'response': json.dumps(proposal, ensure_ascii=False)}
    return httpx.Response(200, json=envelope)


class LocalIntentPlannerTests(unittest.TestCase):
    def planner(self, handler, **kwargs):
        return LocalIntentPlanner('http://127.0.0.1:11434', 'intent-local',
                                  transport=httpx.MockTransport(handler), **kwargs)

    def test_request_is_loopback_scoped_and_contains_only_the_query_context(self):
        query = 'find red cake photos'
        seen = []

        def handler(request):
            seen.append(request)
            body = json.loads(request.content)
            self.assertEqual('intent-local', body['model'])
            self.assertFalse(body['stream'])
            self.assertIs(body['think'], False)
            self.assertIs(body['truncate'], False)
            self.assertEqual('json', body['format'])
            prompt = body['prompt']
            self.assertIn('"query": "find red cake photos"', prompt)
            self.assertNotIn('301', prompt)
            self.assertNotIn('private roster', prompt)
            self.assertNotIn('tool_data', prompt)
            return model_response(query)

        with self.assertLogs('httpx', level='INFO') as captured:
            proposal = self.planner(handler).propose(query, '2032-09-14', False)
        self.assertTrue(captured.output)
        self.assertNotIn(query, '\n'.join(captured.output))
        self.assertEqual([{'start': 5, 'end': 13,
                           'alternatives': ['red cake', '红色蛋糕']}], proposal['concepts'])
        self.assertEqual('127.0.0.1', seen[0].url.host)
        self.assertEqual('/api/generate', seen[0].url.path)

    def test_constructor_rejects_non_loopback_or_ambiguous_model_settings(self):
        for url in ('https://127.0.0.1:11434', 'http://example.com:11434',
                    'http://127.0.0.1:11434/redirect?target=example.com'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                LocalIntentPlanner(url, 'intent-local')
        for model in ('', ' intent-local', 'intent-local\nsecond', 'm' * 121):
            with self.subTest(model=model[:12]), self.assertRaises(ValueError):
                LocalIntentPlanner('http://127.0.0.1:11434', model)
        for timeout in (True, 0, 46, float('inf'), float('nan')):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                LocalIntentPlanner('http://127.0.0.1:11434', 'intent-local', timeout=timeout)

    def test_strict_json_and_provider_envelope_are_required(self):
        query = 'find red cake photos'
        bodies = [
            b'{"model":"intent-local","done":true,"response":"{}","done":true}',
            b'{"model":"intent-local","done":NaN,"response":"{}"}',
        ]
        for raw in bodies:
            with self.subTest(raw=raw):
                planner = self.planner(lambda _, body=raw: httpx.Response(200, content=body))
                with self.assertRaises(IntentUnavailable):
                    planner.propose(query, '2032-09-14', False)
        for value in (
            {'model': 'other', 'done': True, 'response': '{}'},
            {'model': 'intent-local', 'done': False, 'response': '{}'},
            {'model': 'intent-local', 'done': 1, 'response': '{}'},
            {'model': 'intent-local', 'done': True, 'response': '{"x":1,"x":2}'},
        ):
            with self.subTest(value=value):
                planner = self.planner(lambda _, envelope=value: httpx.Response(200, json=envelope))
                with self.assertRaises(IntentUnavailable):
                    planner.propose(query, '2032-09-14', False)

    def test_exact_surface_copy_and_unique_occurrence_are_enforced(self):
        for query, surface in (
            ('find red cake photos', 'Red cake'),
            ('find red cake and red cake photos', 'red cake'),
        ):
            with self.subTest(query=query):
                planner = self.planner(lambda _, q=query, s=surface: model_response(q, surface=s))
                with self.assertRaises(IntentUnavailable):
                    planner.propose(query, '2032-09-14', False)
        # The source substring is copied byte-for-byte into the compiled offsets.
        query = 'find ＲＥＤ cake photos'
        planner = self.planner(lambda _: model_response(query, surface='ＲＥＤ cake',
                                                          alternatives=['red cake']))
        result = planner.propose(query, '2032-09-14', False)
        self.assertEqual(query[5:13], 'ＲＥＤ cake')
        self.assertEqual({'start': 5, 'end': 13,
                          'alternatives': ['red cake']}, result['concepts'][0])

    def test_body_cap_status_and_redirect_fail_closed_without_following_redirect(self):
        consumed = []

        class Oversized(SyncByteStream):
            def __iter__(self):
                consumed.append('first')
                yield b'{' + b' ' * MAX_PROVIDER_BYTES
                raise AssertionError('adapter read past response byte cap')

            def close(self):
                pass

        planner = self.planner(lambda _: httpx.Response(200, stream=Oversized()))
        with self.assertRaises(IntentUnavailable):
            planner.propose('find red cake photos', '2032-09-14', False)
        self.assertEqual(['first'], consumed)

        calls = []
        def redirect(request):
            calls.append(request)
            return httpx.Response(302, headers={'Location': 'http://example.com/secret'})
        with self.assertRaises(IntentUnavailable):
            self.planner(redirect).propose('find red cake photos', '2032-09-14', False)
        self.assertEqual(1, len(calls))

        with self.assertRaises(IntentUnavailable):
            self.planner(lambda _: httpx.Response(503)).propose(
                'find red cake photos', '2032-09-14', False)

    def test_deadline_is_enforced_after_transport_returns(self):
        ticks = iter([1.0, 1.0, 1.0, 1.0, 46.0])
        planner = self.planner(lambda _: model_response('find red cake photos'),
                               timeout=20, monotonic=lambda: next(ticks))
        with self.assertRaises(IntentUnavailable):
            planner.propose('find red cake photos', '2032-09-14', False)

    def test_semaphore_stays_owned_during_call_and_is_released_after_disconnect(self):
        entered, release = threading.Event(), threading.Event()
        calls = []

        def handler(request):
            calls.append(request)
            if len(calls) == 1:
                entered.set()
                self.assertTrue(release.wait(3))
                raise httpx.ReadError('private transport detail')
            return model_response('find red cake photos')

        planner = self.planner(handler)
        failures = []

        def first_call():
            try:
                planner.propose('find red cake photos', '2032-09-14', False)
            except Exception as error:  # captured for assertions in the main test thread
                failures.append(error)

        worker = threading.Thread(target=first_call)
        worker.start()
        self.assertTrue(entered.wait(3))
        with self.assertRaises(IntentUnavailable):
            planner.propose('find red cake photos', '2032-09-14', False)
        release.set()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(1, len(failures))
        self.assertIsInstance(failures[0], IntentUnavailable)
        self.assertNotIn('private transport detail', str(failures[0]))
        self.assertEqual('ready', planner.propose(
            'find red cake photos', '2032-09-14', False)['status'])
        self.assertEqual(2, len(calls))

    def test_exception_and_disconnect_do_not_strand_the_single_call_lease(self):
        calls = []

        class BrokenStream(SyncByteStream):
            def __iter__(self):
                raise httpx.ReadError('private stream detail')
                yield b''

            def close(self):
                pass

        def handler(_):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(200, stream=BrokenStream())
            return model_response('find red cake photos')

        planner = self.planner(handler)
        with self.assertRaises(IntentUnavailable):
            planner.propose('find red cake photos', '2032-09-14', False)
        self.assertEqual('ready', planner.propose(
            'find red cake photos', '2032-09-14', False)['status'])


if __name__ == '__main__':
    unittest.main()

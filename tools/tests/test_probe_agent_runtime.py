from __future__ import annotations

import copy
import http.client
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import probe_agent_runtime as probe


def fixture_report(scenario='allowed', tools=None):
    fixture = probe.Fixture(scenario)
    if tools is None:
        tools = [{'type': 'namespace', 'name': 'mcp__photohouse_domain',
                  'tools': [{'type': 'function', 'name': name} for name in probe.TOOLS]}]
    fixture.requests = [{'path': '/v1/responses', 'body': {'tools': tools}},
                        {'path': '/v1/responses', 'body': {'input': [
                            {'type': 'function_call_output', 'call_id': 'call_synthetic',
                             'output': json.dumps(probe.SELECTOR)}]}}]
    fixture.mcp = [{'message': {'method': 'tools/call', 'params': {'name': 'search_media', 'arguments': {},
                               '_meta': {'callId': 'call_synthetic'}}}}]
    report = {'terminal': {'params': {'turn': {'status': 'completed', 'items': [
        {'type': 'agentMessage', 'text': json.dumps(probe.SELECTOR)}]}}}}
    return fixture, report


class AssessmentTests(unittest.TestCase):
    def test_allowed_requires_actual_tool_result_continuation(self):
        fixture, report = fixture_report()
        probe.assess(report, fixture)
        self.assertTrue(report['allowed_round_trip'])
        self.assertEqual(report['ph_a0'], 'incomplete')  # No real model/native qualification.
        fixture.mcp = []
        probe.assess(report, fixture)
        self.assertFalse(report['allowed_round_trip'])

    def test_round_trip_binds_domain_name_arguments_and_call_id(self):
        for field, value in (('name', 'get_search_capabilities'), ('arguments', {'query': 'invented'}),
                             ('_meta', {'callId': 'other-call'})):
            fixture, report = fixture_report()
            fixture.mcp[0]['message']['params'][field] = value
            probe.assess(report, fixture)
            self.assertFalse(report['allowed_round_trip'])

    def test_terminal_selector_does_not_hide_resource_dispatch(self):
        fixture, report = fixture_report('forbidden_resource')
        fixture.mcp = [{'message': {'method': 'resources/list'}}]
        probe.assess(report, fixture)
        self.assertTrue(report['matching_final_selector'])
        self.assertTrue(report['forbidden_resource_dispatched'])
        self.assertEqual(report['ph_a0'], 'failed_capability_ceiling')

    def test_extra_and_duplicate_tools_fail_exact_ceiling(self):
        for name in ('list_mcp_resources', 'mcp__photohouse_domain.search_media'):
            fixture, report = fixture_report()
            fixture.requests[0]['body']['tools'].append({'type': 'function', 'name': name})
            probe.assess(report, fixture)
            self.assertFalse(report['exact_tool_advertisement'])
            self.assertEqual(report['ph_a0'], 'failed_capability_ceiling')

    def test_invalid_or_ambiguous_final_is_not_a_round_trip(self):
        for final in ('{"outcome_handle":"wrong"}', '{"outcome_handle":"wrong","outcome_handle":"synthetic-outcome-a0"}', 'null'):
            fixture, report = fixture_report()
            report['terminal']['params']['turn']['items'][0]['text'] = final
            probe.assess(report, fixture)
            self.assertFalse(report['allowed_round_trip'])
        fixture, report = fixture_report()
        report['terminal']['params']['turn']['items'] *= 2
        probe.assess(report, fixture)
        self.assertFalse(report['matching_final_selector'])

    def test_failed_terminal_cannot_pass_allowed_or_negative_retry_check(self):
        fixture, report = fixture_report()
        report['terminal']['params']['turn']['status'] = 'failed'
        probe.assess(report, fixture)
        self.assertFalse(report['allowed_round_trip'])
        fixture.scenario = 'http_503'
        probe.assess(report, fixture)
        self.assertFalse(report['negative_transport_single_attempt'])  # Two requests.
        fixture.requests.pop()
        probe.assess(report, fixture)
        self.assertTrue(report['negative_transport_single_attempt'])

    def test_missing_inference_is_incomplete(self):
        fixture, report = probe.Fixture('allowed'), {}
        probe.assess(report, fixture)
        self.assertEqual(report['ph_a0'], 'incomplete')
        self.assertFalse(report['allowed_round_trip'])


class BoundaryTests(unittest.TestCase):
    def test_strict_json_rejects_duplicate_and_nonfinite_values(self):
        for value in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.assertRaises(ValueError):
                probe.strict_json(value)

    def test_captures_redact_capability(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'capture.json'
            probe.capture(path, b'{"unexpected":"private-token"}', 'private-token')
            self.assertEqual(path.read_bytes(), b'{"unexpected":"<redacted>"}')

    def test_catalog_disables_native_tools_without_mutating_input(self):
        original = {'models': [{'slug': 'source', 'shell_type': 'unified_exec',
                                'base_instructions': 'original', 'tool_mode': 'code_mode_only'}]}
        before = copy.deepcopy(original)
        model = probe.catalog_for_probe(original)['models'][0]
        self.assertEqual(original, before)
        self.assertEqual(model['shell_type'], 'disabled')
        self.assertIsNone(model['apply_patch_tool_type'])
        self.assertEqual(model['tool_mode'], 'direct')
        self.assertEqual(model['slug'], 'photohouse-synthetic-probe')

    def test_digest_mismatch_refuses_before_evidence_or_execution(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence = Path(temporary) / 'evidence'
            with self.assertRaisesRegex(ValueError, 'binary_digest_mismatch'):
                probe.run_probe(Path(sys.executable), '0' * 64, evidence, 'allowed')
            self.assertFalse(evidence.exists())

    def test_fixture_auth_origin_host_and_size_before_dispatch(self):
        fixture = probe.Fixture('allowed')
        port = fixture.start('mcp')
        try:
            good = {'Authorization': 'Bearer ' + fixture.token, 'Host': f'127.0.0.1:{port}'}
            for headers, expected in (({}, 403), ({**good, 'Origin': 'http://example.invalid'}, 403),
                                      ({**good, 'Host': 'example.invalid'}, 403), (good, 200)):
                connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                connection.request('POST', '/mcp', json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}), headers)
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                body = response.read()
                if expected == 200:
                    tools = {tool['name']: tool for tool in json.loads(body)['result']['tools']}
                    self.assertEqual(set(tools), set(probe.TOOLS))
                    self.assertEqual(tools['search_media']['inputSchema']['properties'], {})
                    self.assertEqual(tools['inspect_current_results']['inputSchema']['required'], ['outcome_handle'])
                connection.close()
            self.assertEqual(len(fixture.mcp), 1)
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
            connection.request('POST', '/mcp', b'', {**good, 'Content-Length': str(probe.MAX_FRAME + 1)})
            response = connection.getresponse()
            self.assertEqual(response.status, 413)
            response.read()
            connection.close()
            self.assertEqual(len(fixture.mcp), 1)
        finally:
            fixture.close()

    def test_fixture_resource_handler_is_denied_but_attempt_is_recorded(self):
        fixture = probe.Fixture('forbidden_resource')
        port = fixture.start('mcp')
        try:
            connection = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
            connection.request('POST', '/mcp', json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'resources/list'}),
                               {'Authorization': 'Bearer ' + fixture.token})
            response = connection.getresponse()
            self.assertEqual(json.loads(response.read())['error']['code'], -32601)
            self.assertEqual(fixture.mcp[0]['message']['method'], 'resources/list')
            connection.close()
        finally:
            fixture.close()

    @unittest.skipUnless(sys.platform != 'win32', 'POSIX-only developer probe')
    def test_owned_child_output_limit_and_teardown(self):
        with tempfile.TemporaryDirectory() as temporary:
            child = probe.Child([sys.executable, '-c', 'import sys,time; sys.stdout.write("x" * 1048577); sys.stdout.flush(); time.sleep(20)'], {}, temporary)
            try:
                with self.assertRaisesRegex(RuntimeError, 'child_output_limit'):
                    child.until(lambda event: False, time.monotonic() + 3)
            finally:
                self.assertIsNotNone(child.close())

    @unittest.skipUnless(sys.platform != 'win32', 'POSIX-only developer probe')
    def test_unexpected_host_request_is_denied_and_fails_probe(self):
        with tempfile.TemporaryDirectory() as temporary:
            program = 'import json,time; print(json.dumps({"id":9,"method":"approval/request"}),flush=True); time.sleep(20)'
            child = probe.Child([sys.executable, '-c', program], {}, temporary)
            try:
                with self.assertRaisesRegex(RuntimeError, 'unexpected_host_request'):
                    child.until(lambda event: False, time.monotonic() + 3)
            finally:
                self.assertIsNotNone(child.close())


if __name__ == '__main__':
    unittest.main()

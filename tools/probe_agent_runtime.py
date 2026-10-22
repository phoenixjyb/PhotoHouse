#!/usr/bin/env python3
"""Developer-only synthetic Codex capability probe; never a PH-A0 pass certificate.

No application/store/model is opened. The explicitly selected binary is run in
an empty temporary cwd and CODEX_HOME, against owned loopback Responses/MCP
fixtures. Only synthetic requests are retained. POSIX process cleanup here is
not the product's native containment/restart implementation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import secrets
import signal
import subprocess
import tempfile
import threading
import time

TOOLS = ('get_search_capabilities', 'search_media', 'inspect_current_results')
SELECTOR = {'outcome_handle': 'synthetic-outcome-a0'}
MAX_FRAME = 1024 * 1024
MAX_TOTAL = 8 * MAX_FRAME
SCENARIOS = ('allowed', 'forbidden_resource', 'unknown', 'http_503', 'dropped_stream', 'connection_close')


def encoded(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=False).encode()


def strict_json(value):
    def pairs(items):
        result = {}
        for key, item in items:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = item
        return result

    def invalid_constant(_value):
        raise ValueError('nonfinite_json')

    return json.loads(value, object_pairs_hook=pairs, parse_constant=invalid_constant)


def capture(path, value, token):
    path.write_bytes(value.replace(token.encode(), b'<redacted>'))


def catalog_for_probe(catalog):
    """Use this binary's metadata shape; never claim a synthetic alias is a model."""
    model = copy.deepcopy(catalog['models'][0])
    model.update(slug='photohouse-synthetic-probe', display_name='Synthetic protocol fixture',
                 shell_type='disabled', apply_patch_tool_type=None, tool_mode='direct',
                 base_instructions='Synthetic protocol qualification. Use only the three domain tools.',
                 experimental_supported_tools=[], node_repl_disabled=True,
                 use_responses_lite=False, supports_search_tool=False,
                 input_modalities=['text'], context_window=32768,
                 max_context_window=32768, include_skills_usage_instructions=False,
                 include_plugin_usage_instructions=False, include_apps_usage_instructions=False)
    return {'models': [model]}


def config_text(catalog, model_port, mcp_port):
    return f'''model = "photohouse-synthetic-probe"
model_provider = "photohouse_probe"
model_catalog_json = {json.dumps(str(catalog))}
web_search = "disabled"
sandbox_mode = "read-only"
approval_policy = "never"
[model_providers.photohouse_probe]
name = "Synthetic loopback fixture"
base_url = "http://127.0.0.1:{model_port}/v1"
wire_api = "responses"
requires_openai_auth = false
env_key = "PHOTOHOUSE_PROBE_PROVIDER_TOKEN"
supports_websockets = false
supports_standalone_web_search = false
request_max_retries = 0
stream_max_retries = 0
stream_idle_timeout_ms = 5000
[model_providers.photohouse_probe.capabilities]
external_web_access = false
remote_compaction = "unsupported"
[features]
shell_tool = false
view_image = false
shell_snapshot = false
memories = false
multi_agent = false
plugins = false
hooks = false
apps = false
goals = false
browser_use = false
browser_use_external = false
browser_use_full_cdp_access = false
computer_use = false
unbounded_connection_retries = false
mcp_2026_07_28 = false
[history]
persistence = "none"
[memories]
generate_memories = false
use_memories = false
[analytics]
enabled = false
[feedback]
enabled = false
[otel]
exporter = "none"
trace_exporter = "none"
metrics_exporter = "none"
log_user_prompt = false
[mcp_servers.photohouse_domain]
url = "http://127.0.0.1:{mcp_port}/mcp"
bearer_token_env_var = "PHOTOHOUSE_PROBE_MCP_TOKEN"
enabled = true
required = true
enabled_tools = ["get_search_capabilities", "search_media", "inspect_current_results"]
startup_readiness = "connection"
startup_timeout_sec = 5
tool_timeout_sec = 5
'''


def function_names(tools):
    names = []
    for tool in tools:
        if tool.get('type') == 'namespace':
            names.extend(f"{tool['name']}.{name}" for name in function_names(tool.get('tools', [])))
        else:
            names.append(tool.get('name', tool.get('type', '<unknown>')))
    return names


def domain_tool(name):
    schema = {'type': 'object', 'properties': {}, 'additionalProperties': False}
    if name == 'inspect_current_results':
        schema.update(properties={'outcome_handle': {'type': 'string'}}, required=['outcome_handle'])
    return {'name': name, 'description': 'Synthetic read-only domain fixture', 'inputSchema': schema,
            'annotations': {'readOnlyHint': True, 'destructiveHint': False, 'openWorldHint': False}}


class Fixture:
    def __init__(self, scenario):
        self.scenario = scenario
        self.token = secrets.token_urlsafe(32)
        self.requests = []
        self.mcp = []
        self.errors = []
        self.servers = []

    def start(self, kind):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def reply(self, status, body, content_type='application/json'):
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.reply(405, b'{}')

            def do_DELETE(self):
                self.reply(405, b'{}')

            def do_POST(self):
                self.connection.settimeout(5)
                try:
                    size = int(self.headers.get('Content-Length', '-1'))
                    if not 0 <= size <= MAX_FRAME:
                        return self.reply(413, b'{}')
                    data = strict_json(self.rfile.read(size))
                    if not isinstance(data, dict):
                        return self.reply(400, b'{}')
                    if (self.headers.get('Authorization') != 'Bearer ' + fixture.token
                            or self.headers.get('Origin') is not None
                            or self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}'):
                        return self.reply(403, b'{}')
                    if kind == 'mcp':
                        if self.path != '/mcp':
                            return self.reply(404, b'{}')
                        fixture.mcp.append({'message': data, 'protocol': self.headers.get('MCP-Protocol-Version')})
                        if len(fixture.mcp) > 64:
                            return self.reply(429, b'{}')
                        if 'id' not in data:
                            return self.reply(202, b'')
                        method = data.get('method')
                        if method == 'initialize':
                            result = {'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}},
                                      'serverInfo': {'name': 'photohouse-synthetic', 'version': '1'}}
                        elif method == 'tools/list':
                            result = {'tools': [domain_tool(name) for name in TOOLS]}
                        elif method == 'tools/call' and data.get('params', {}).get('name') in TOOLS:
                            result = {'content': [{'type': 'text', 'text': json.dumps(SELECTOR)}]}
                        elif method == 'ping':
                            result = {}
                        else:
                            return self.reply(200, encoded({'jsonrpc': '2.0', 'id': data['id'],
                                                           'error': {'code': -32601, 'message': 'Fixture denies method'}}))
                        return self.reply(200, encoded({'jsonrpc': '2.0', 'id': data['id'], 'result': result}))
                    if self.path != '/v1/responses':
                        return self.reply(404, b'{}')
                    fixture.requests.append({'path': self.path, 'body': data})
                    index = len(fixture.requests)
                    if index > 4:
                        return self.reply(429, b'{}')
                    if fixture.scenario == 'http_503':
                        return self.reply(503, b'{"error":{"message":"synthetic unavailable"}}')
                    if fixture.scenario == 'connection_close':
                        self.close_connection = True
                        return
                    output = fixture.output(index, data)
                    response_id = f'resp_synthetic_{index}'
                    events = [({'type': 'response.created', 'response': {'id': response_id, 'status': 'in_progress', 'output': []}})]
                    for item in output:
                        events.append({'type': 'response.output_item.added', 'output_index': 0, 'item': item})
                        events.append({'type': 'response.output_item.done', 'output_index': 0, 'item': item})
                    events.append({'type': 'response.completed', 'response': {'id': response_id, 'status': 'completed',
                                  'output': output, 'usage': {'input_tokens': 1, 'output_tokens': 1, 'total_tokens': 2}}})
                    if fixture.scenario == 'dropped_stream':
                        events = events[:1]
                    payload = b''.join(b'event: ' + event['type'].encode() + b'\ndata: ' + encoded(event) + b'\n\n' for event in events)
                    self.reply(200, payload, 'text/event-stream')
                except (ValueError, OSError, KeyError, TypeError) as error:
                    fixture.errors.append(type(error).__name__)
                    self.close_connection = True

        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.servers.append(server)
        return server.server_port

    def output(self, index, request):
        if index != 1:
            return [{'type': 'message', 'id': 'msg_synthetic', 'role': 'assistant',
                     'status': 'completed', 'content': [{'type': 'output_text', 'text': json.dumps(SELECTOR), 'annotations': []}]}]
        if self.scenario == 'allowed':
            name, namespace, arguments = 'search_media', 'mcp__photohouse_domain', '{}'
        elif self.scenario == 'forbidden_resource':
            name, namespace, arguments = 'list_mcp_resources', None, '{"server":"photohouse_domain"}'
        else:
            name, namespace, arguments = 'photohouse_forbidden_unknown', None, '{}'
        item = {'type': 'function_call', 'id': 'fc_synthetic', 'call_id': 'call_synthetic',
                'name': name, 'arguments': arguments, 'status': 'completed'}
        if namespace:
            item['namespace'] = namespace
        return [item]

    def close(self):
        for server in self.servers:
            server.shutdown()
            server.server_close()


def assess(report, fixture):
    """Report observed gates separately; a terminal selector cannot hide tool denial."""
    report['fixture_errors'] = fixture.errors
    report['inference_requests'] = len(fixture.requests)
    report['model_tools'] = function_names(fixture.requests[0]['body'].get('tools', [])) if fixture.requests else []
    report['mcp_methods'] = [item['message'].get('method') for item in fixture.mcp]
    report['exact_tool_advertisement'] = (len(report['model_tools']) == len(TOOLS)
                                        and set(report['model_tools']) == {f'mcp__photohouse_domain.{tool}' for tool in TOOLS})
    report['forbidden_resource_dispatched'] = 'resources/list' in report['mcp_methods']
    report['ph_a0'] = ('failed_capability_ceiling' if fixture.requests and not report['exact_tool_advertisement']
                       or report['forbidden_resource_dispatched'] else 'incomplete')
    terminal = report.get('terminal', {}).get('params', {}).get('turn', {})
    report['turn_status'] = terminal.get('status')
    final = [item.get('text') for item in terminal.get('items', []) if item.get('type') == 'agentMessage']
    try:
        report['matching_final_selector'] = len(final) == 1 and strict_json(final[0]) == SELECTOR
    except (ValueError, TypeError):
        report['matching_final_selector'] = False
    calls = [item for item in fixture.mcp if item['message'].get('method') == 'tools/call']
    params = calls[0]['message'].get('params', {}) if len(calls) == 1 else {}
    canonical_call = (params.get('name') == 'search_media' and params.get('arguments') == {}
                      and params.get('_meta', {}).get('callId') == 'call_synthetic')
    outputs = [item for request in fixture.requests[1:] for item in request['body'].get('input', [])
               if item.get('type') == 'function_call_output' and item.get('call_id') == 'call_synthetic']
    result_seen = False
    for item in outputs:
        content = item.get('output')
        texts = [content] if isinstance(content, str) else [part.get('text') for part in content or [] if isinstance(part, dict)]
        for text in texts:
            try:
                result_seen |= strict_json(text) == SELECTOR
            except (ValueError, TypeError):
                pass
    report['tool_result_continuation'] = bool(canonical_call and result_seen)
    report['allowed_round_trip'] = (fixture.scenario == 'allowed' and len(fixture.requests) == 2
                                    and len(calls) == 1 and report['tool_result_continuation']
                                    and report['turn_status'] == 'completed' and report['matching_final_selector'])
    report['response_paths'] = [request['path'] for request in fixture.requests]
    report['previous_response_id_present'] = any('previous_response_id' in request['body'] for request in fixture.requests)
    report['negative_transport_single_attempt'] = (fixture.scenario in ('http_503', 'dropped_stream', 'connection_close')
                                                  and len(fixture.requests) == 1 and report['turn_status'] == 'failed')


class Child:
    def __init__(self, command, env, cwd):
        self.events = queue.Queue(maxsize=4096)
        self.transcript = []
        self.stderr = bytearray()
        self.failure = None
        self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        self.threads = [threading.Thread(target=self.drain, args=(self.process.stdout, False), daemon=True),
                        threading.Thread(target=self.drain, args=(self.process.stderr, True), daemon=True)]
        for thread in self.threads:
            thread.start()

    def drain(self, stream, stderr):
        total = 0
        try:
            while True:
                line = stream.readline(MAX_FRAME + 1)
                if not line:
                    return
                total += len(line)
                if len(line) > MAX_FRAME or total > (MAX_FRAME if stderr else MAX_TOTAL):
                    self.failure = 'child_output_limit'
                    return
                if stderr:
                    self.stderr.extend(line)
                else:
                    event = strict_json(line)
                    if not isinstance(event, dict):
                        raise ValueError('invalid_event_shape')
                    self.transcript.append(event)
                    self.events.put_nowait(event)
        except (ValueError, queue.Full, RecursionError):
            self.failure = 'child_protocol_limit'

    def send(self, value):
        self.process.stdin.write(encoded(value) + b'\n')
        self.process.stdin.flush()

    def until(self, predicate, deadline):
        while time.monotonic() < deadline:
            if self.failure:
                raise RuntimeError(self.failure)
            try:
                event = self.events.get(timeout=min(.2, max(.001, deadline - time.monotonic())))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise RuntimeError('child_exited')
                continue
            # No approval/permission/elicitation is granted by this fixture.
            if 'method' in event and 'id' in event:
                self.send({'id': event['id'], 'error': {'code': -32601, 'message': 'Probe denies host requests'}})
                raise RuntimeError('unexpected_host_request')
            if predicate(event):
                return event
        raise RuntimeError('probe_deadline')

    def rpc(self, request_id, method, params, deadline):
        self.send({'id': request_id, 'method': method, 'params': params})
        event = self.until(lambda event: type(event.get('id')) is int and event['id'] == request_id
                           and 'method' not in event, deadline)
        if 'error' in event:
            raise RuntimeError('rpc_error:' + str(event['error']))
        return event['result']

    def close(self):
        # This is cleanup of our new session, never a shared provider/server.
        if self.process.poll() is None:
            os.killpg(self.process.pid, signal.SIGTERM)
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid, signal.SIGKILL)
                self.process.wait(timeout=2)
        for thread in self.threads:
            thread.join(timeout=1)
        if any(thread.is_alive() for thread in self.threads):
            raise RuntimeError('owned_drains_unsettled')
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()
        return self.process.returncode


def run_probe(binary, expected_sha256, evidence, scenario):
    if os.name != 'posix':
        raise ValueError('probe_requires_posix_not_native_qualification')
    binary = binary.resolve(strict=True)
    with binary.open('rb') as binary_file:
        digest = hashlib.file_digest(binary_file, 'sha256').hexdigest()
    if digest != expected_sha256:
        raise ValueError('binary_digest_mismatch')
    evidence.mkdir(mode=0o700, parents=True, exist_ok=False)
    report = {'scope': 'synthetic_protocol_probe_only', 'binary_sha256': digest,
              'scenario': scenario, 'ph_a0': 'incomplete', 'real_model': 'not_run',
              'deployment_performed': False,
              'probe_source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    fixture, child, temporary = Fixture(scenario), None, None
    try:
        temporary = tempfile.TemporaryDirectory(prefix='photohouse-a0-')
        try:
            root = Path(temporary.name)
            home, cwd = root / 'home', root / 'cwd'
            home.mkdir(mode=0o700)
            cwd.mkdir(mode=0o700)
            env = {key: value for key, value in os.environ.items() if key in ('PATH', 'TMPDIR', 'LANG', 'LC_ALL')}
            env.update(CODEX_HOME=str(home), PHOTOHOUSE_PROBE_MCP_TOKEN=fixture.token,
                       PHOTOHOUSE_PROBE_PROVIDER_TOKEN=fixture.token,
                       HTTP_PROXY='', HTTPS_PROXY='', ALL_PROXY='', NO_PROXY='127.0.0.1,localhost')
            version = subprocess.run([str(binary), '--version'], cwd=cwd, env=env, capture_output=True, timeout=10, check=True)
            report['binary_version'] = version.stdout.decode().strip()
            result = subprocess.run([str(binary), 'debug', 'models', '--bundled'], cwd=cwd, env=env,
                                    capture_output=True, timeout=10, check=True)
            catalog = home / 'catalog.json'
            catalog.write_bytes(encoded(catalog_for_probe(json.loads(result.stdout))))
            config = config_text(catalog, fixture.start('model'), fixture.start('mcp'))
            (home / 'config.toml').write_text(config)
            # These fixtures contain no credentials; runtime token is never saved.
            (evidence / 'config.toml').write_text(config)
            (evidence / 'catalog.json').write_bytes(catalog.read_bytes())
            child = Child([str(binary), 'app-server', '--strict-config', '--listen', 'stdio://'], env, cwd)
            deadline = time.monotonic() + 30
            report['initialize'] = child.rpc(1, 'initialize', {'clientInfo': {'name': 'photohouse_probe', 'version': '1'}}, deadline)
            child.send({'method': 'initialized', 'params': {}})
            thread = child.rpc(2, 'thread/start', {'ephemeral': True, 'cwd': str(cwd), 'model': 'photohouse-synthetic-probe',
                               'modelProvider': 'photohouse_probe', 'sandbox': 'read-only', 'approvalPolicy': 'never'}, deadline)
            thread_id = thread['thread']['id']
            report['thread_start'] = thread
            turn = child.rpc(3, 'turn/start', {'threadId': thread_id, 'input': [{'type': 'text', 'text': 'Synthetic capability probe.'}],
                            'outputSchema': {'type': 'object', 'properties': {'outcome_handle': {'type': 'string'}},
                                             'required': ['outcome_handle'], 'additionalProperties': False}}, deadline)
            turn_id = turn['turn']['id']
            terminal = child.until(lambda event: event.get('method') == 'turn/completed'
                                   and event.get('params', {}).get('threadId') == thread_id
                                   and event['params']['turn']['id'] == turn_id, deadline)
            report['terminal'] = terminal
        finally:
            if child:
                try:
                    report['owned_root_exit'] = child.close()
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    report['cleanup_error'] = type(error).__name__
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError, KeyError) as error:
        report['probe_error'] = str(error)[:2000]
    finally:
        if child:
            capture(evidence / 'app-server.json', encoded(child.transcript), fixture.token)
            capture(evidence / 'stderr.txt', bytes(child.stderr), fixture.token)
        fixture.close()
        if temporary:
            temporary.cleanup()
        capture(evidence / 'responses.json', encoded(fixture.requests), fixture.token)
        capture(evidence / 'mcp.json', encoded(fixture.mcp), fixture.token)
        assess(report, fixture)
        capture(evidence / 'report.json', encoded(report), fixture.token)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--sha256', required=True)
    parser.add_argument('--evidence', type=Path, required=True, help='New private directory; synthetic captures only')
    parser.add_argument('--scenario', choices=SCENARIOS, required=True)
    args = parser.parse_args(argv)
    report = run_probe(args.binary, args.sha256, args.evidence, args.scenario)
    print(json.dumps({key: report.get(key) for key in ('scope', 'binary_version', 'scenario', 'probe_error', 'inference_requests',
                                                     'model_tools', 'exact_tool_advertisement', 'ph_a0')}, indent=2))
    # Completed protocol traffic is not a successful capability qualification.
    if report['ph_a0'] == 'failed_capability_ceiling':
        return 2
    return 0 if report.get('terminal') and not report.get('probe_error') else 1


if __name__ == '__main__':
    raise SystemExit(main())

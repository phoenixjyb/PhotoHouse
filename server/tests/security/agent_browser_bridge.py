"""Browser bridge using generated protected media and scripted agent decisions.

The ScriptedDecisionProvider below is a test fixture. It drives the real
LocalToolAgentRuntime and protected Search tools but is not model execution
evidence.
"""
import ast
import base64
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))

# Reuse the existing generated-media ASGI fixture setup while omitting its own
# stdin loop, so this bridge can install the explicitly scripted agent runtime.
fixture_source = ROOT / 'tests/security/assistant_workspace_browser_bridge.py'
fixture_tree = ast.parse(fixture_source.read_text(encoding='utf-8'),
                         filename=str(fixture_source))
if not fixture_tree.body or not isinstance(fixture_tree.body[-1], ast.Try):
    raise RuntimeError('Expected the established browser fixture loop')
fixture_tree.body.pop()
fixture_namespace = {'__name__': '_agent_browser_fixture_', '__file__': str(fixture_source)}
exec(compile(fixture_tree, str(fixture_source), 'exec'), fixture_namespace)
client = fixture_namespace['client']
fixture = fixture_namespace['fixture']

from app.access.agent_local_runtime import LocalToolAgentRuntime
from app.access.assistant_agent import AgentSupervisor


class ScriptedDecisionProvider:
    """Deterministic decisions for integration only; no model is invoked."""
    def __init__(self):
        self.calls = []

    async def decide(self, state, _scope):
        self.calls.append(state)
        observations = state['observations']
        if not observations:
            return {'tool': 'get_search_capabilities'}
        if len(observations) == 1:
            return {'tool': 'search_media'}
        result = observations[-1]['result']
        if len(observations) == 2:
            return {'tool': 'inspect_current_results',
                    'outcome_handle': result['outcome_handle']}
        return {'finish': result['outcome_handle']}

    async def stop_and_reconcile(self, _scope):
        return True


provider = ScriptedDecisionProvider()
agent_runtime = LocalToolAgentRuntime(provider, enabled=True)
supervisor = None


def install_agent(enabled):
    global supervisor
    if not enabled:
        if supervisor is not None:
            supervisor.healthy = False
        return
    if supervisor is None or supervisor.closed or not supervisor.healthy:
        supervisor = AgentSupervisor(agent_runtime)
    client.app.state.assistant_agent_supervisor = supervisor


try:
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        command = message.get('command')
        if command == 'quit':
            break
        if command == 'agent-enable':
            install_agent(True)
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if command == 'agent-disable':
            install_agent(False)
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if command == 'agent-stats':
            print(json.dumps({'id': message['id'], 'calls': len(provider.calls),
                              'tools': list(agent_runtime.last_trace['tools'])
                              if agent_runtime.last_trace else []}), flush=True)
            continue
        client.cookies.clear()
        response = client.request(message['method'], message['path'],
            headers=message['headers'],
            content=base64.b64decode(message.get('body', '')),
            follow_redirects=False)
        client.cookies.clear()
        print(json.dumps({'id': message['id'], 'status': response.status_code,
            'headers': dict(response.headers),
            'body': base64.b64encode(response.content).decode()}), flush=True)
finally:
    client.close()
    fixture.doCleanups()
    from test_library_reads import LibraryReadTests
    LibraryReadTests.tearDownClass()

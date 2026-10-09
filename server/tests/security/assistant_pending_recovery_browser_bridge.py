"""Synthetic ASGI stdin bridge for the assistant pending-turn browser test."""
import base64
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
sys.path.insert(0, str(ROOT / 'scripts'))

from fastapi.testclient import TestClient
from test_library_reads import LibraryReadTests
from app.access.assistant_journal import initialize
from app.access.runtime import RuntimeConfiguration

fixture = LibraryReadTests()
LibraryReadTests.setUpClass()
fixture.setUp()
fixture.client.close()
root = fixture.path.parent.resolve()
originals, derived = root / 'originals', root / 'derived'
originals.mkdir()
derived.mkdir()

import prepare_access_discovery_index as producer
from contextlib import closing
with closing(producer.open_read_only(fixture.path.resolve(), time.monotonic())) as db:
    index, _catalog = producer.derive(db, producer.library('family-a'), producer.revision('1'))
index_path = root / 'discovery-index.json'
producer.write_new(index_path, json.dumps(asdict(index), sort_keys=True, ensure_ascii=True,
    separators=(',', ':')).encode())

journal_path = root / 'assistant-receipts.sqlite'
initialize(journal_path)
client = TestClient(RuntimeConfiguration(fixture.path.resolve(), 'https://photohouse.test',
    (originals,), derived, discovery_indexes=(index_path,), assistant_enabled=True,
    assistant_journal_path=journal_path).build_app(clock=lambda: fixture.now),
    base_url='https://photohouse.test', client=('192.0.2.25', 23461))
fixture.addCleanup(client.close)
fixture.client = client
fixture.client.headers['Sec-Fetch-Site'] = 'same-origin'
discovery = client.app.state.discovery_runtime

try:
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        command = message.get('command')
        if command == 'quit':
            break
        if command == 'discovery-off':
            client.app.state.discovery_runtime = None
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if command == 'discovery-on':
            client.app.state.discovery_runtime = discovery
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        client.cookies.clear()
        response = client.request(message['method'], message['path'], headers=message['headers'],
            content=base64.b64decode(message.get('body', '')), follow_redirects=False)
        client.cookies.clear()
        print(json.dumps({'id': message['id'], 'status': response.status_code,
            'headers': dict(response.headers), 'body': base64.b64encode(response.content).decode()}), flush=True)
finally:
    client.close()
    fixture.doCleanups()
    LibraryReadTests.tearDownClass()

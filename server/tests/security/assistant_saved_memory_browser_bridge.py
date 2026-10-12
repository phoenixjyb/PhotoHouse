"""Synthetic browser-to-ASGI bridge for saved-memory card UI checks."""
import base64
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
sys.path.insert(0, str(ROOT / 'scripts'))

from fastapi.testclient import TestClient
from test_library_reads import LibraryReadTests
from app.access.assistant_workspace_store import initialize_v2
from app.access.runtime import RuntimeConfiguration

fixture = LibraryReadTests()
LibraryReadTests.setUpClass()
fixture.setUp()
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


def runtime(*, assistant=False, workspace=None):
    return RuntimeConfiguration(
        fixture.path.resolve(), 'https://photohouse.test', (originals,), derived,
        discovery_indexes=(index_path,), memory_collaboration_enabled=True,
        assistant_enabled=assistant, assistant_workspace_path=workspace,
        assistant_saved_memory_cards_enabled=assistant,
    )


# Seed through the existing protected story/memoir APIs with generated assets
# in the disposable LibraryReadTests database. No real media or provider runs.
seed_client = TestClient(runtime().build_app(clock=lambda: fixture.now),
    base_url='https://photohouse.test', client=('192.0.2.26', 23463))
owner_headers = {'Authorization': 'Bearer ' + fixture.owner_token}
preview = seed_client.post('/story-workspace/preview?library=family-a',
    headers=owner_headers, json={
        'asset_ids': '102,101',
        'title': '湖边 <img src=x onerror=window.__savedMemoryXss=1>',
        'theme': 'everyday', 'language': 'zh',
    })
if preview.status_code != 200:
    raise RuntimeError('Could not seed synthetic saved story')
draft = preview.json()
draft['chapters'][0]['narration'] = (
    '野餐时，全家在湖边散步，留下了这段合成回忆。'
    '<img src=x onerror=window.__savedMemoryXss=2>'
)
story_body = {
    'title': '湖边 <img src=x onerror=window.__savedMemoryXss=1>',
    'theme': draft['theme'], 'language': 'zh',
    'asset_ids': ','.join(item['id'] for item in draft['items']),
    'chapters': json.dumps(draft['chapters'], ensure_ascii=False),
    'selection_revision': draft['selection_revision'], 'revision': '0',
    'mutation_id': str(uuid.uuid4()),
}
saved_story = seed_client.post('/memory-stories?library=family-a',
    headers=owner_headers, json=story_body)
if saved_story.status_code != 200:
    raise RuntimeError('Could not seed synthetic saved story')
story_id = saved_story.json()['id']
memoir_title = '夏日回忆册 <img src=x onerror=window.__savedMemoryXss=3>'
saved_memoir = seed_client.post('/memory-community/v1/books?library=family-a',
    headers=owner_headers, json={
        'title': memoir_title, 'language': 'zh',
        'introduction': '野餐之后，我们记下了家人一起度过的时光。',
        'story_ids': story_id, 'revision': '0', 'mutation_id': str(uuid.uuid4()),
    })
if saved_memoir.status_code != 200:
    raise RuntimeError('Could not seed synthetic saved memoir')
memoir_id = saved_memoir.json()['id']
seed_client.close()

workspace_path = root / 'assistant-workspace-v2.sqlite'
initialize_v2(workspace_path, clock=lambda: fixture.now)
client = TestClient(runtime(assistant=True, workspace=workspace_path).build_app(
        clock=lambda: fixture.now), base_url='https://photohouse.test',
    client=('192.0.2.27', 23464))
fixture.addCleanup(client.close)
fixture.client = client
fixture.client.headers['Sec-Fetch-Site'] = 'same-origin'

try:
    print(json.dumps({'ready': True, 'story_id': story_id, 'memoir_id': memoir_id,
        'story_title': story_body['title'], 'story_excerpt': draft['chapters'][0]['narration'],
        'memoir_title': memoir_title}, ensure_ascii=False), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('command') == 'quit':
            break
        if message.get('command') == 'saved-memory-off':
            client.app.state.assistant_saved_memory_cards_enabled = False
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if message.get('command') == 'saved-memory-on':
            client.app.state.assistant_saved_memory_cards_enabled = True
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
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
    seed_client.close()
    fixture.doCleanups()
    LibraryReadTests.tearDownClass()

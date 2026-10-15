"""Native-browser synthetic fixture for negotiated assistant search v3."""
import base64
from contextlib import closing
from dataclasses import asdict, replace
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
sys.path.insert(0, str(ROOT / 'scripts'))

from fastapi.testclient import TestClient
from test_library_reads import LibraryReadTests
from app.access.assistant_workspace_store import initialize_v2
from app.access.runtime import RuntimeConfiguration


class FixturePlanner:
    """Deterministic stand-in returning only exact query spans."""
    def __init__(self):
        self.calls = []

    def propose(self, query, today, has_previous_search):
        self.calls.append((query, today, has_previous_search))
        concepts = []
        for surface, alternatives in (
                ('playing in snow', ['playing in snow', '在雪地玩']),
                ('red coat', ['red coat', '红色外套']),
                ('blue coat', ['blue coat', '蓝外套']),
                ('green coat', ['green coat', '绿外套'])):
            start = query.find(surface)
            if start >= 0:
                concepts.append({'start': start, 'end': start + len(surface),
                                 'alternatives': alternatives})
        if not concepts:
            return {'version': 1, 'status': 'clarification', 'concepts': [],
                    'question': 'description'}
        return {'version': 1, 'status': 'ready',
                'concepts': sorted(concepts, key=lambda item: item['start']),
                'question': None}


fixture = LibraryReadTests()
LibraryReadTests.setUpClass()
fixture.setUp()
fixture.client.close()
root = fixture.path.parent.resolve()
originals, derived = root / 'originals', root / 'derived'
originals.mkdir()
derived.mkdir()

# The catalog remains generated test media. Only fictional captions and one
# fictional reviewed identity are supplied as search evidence.
with closing(sqlite3.connect(fixture.path)) as db, db:
    db.execute("UPDATE assets SET status='active',mime='image/jpeg',taken_at='2032-09-02' WHERE id=101")
    db.execute("UPDATE assets SET status='active',mime='video/mp4',taken_at='2032-09-02' WHERE id=102")
    db.execute("UPDATE assets SET status='active',mime='image/jpeg',taken_at='2032-09-02' WHERE id=103")
    db.execute("UPDATE captions SET text='A child playing in snow wearing a red coat with secret memory phrase',user_edited=1 WHERE id=101")
    db.execute("UPDATE captions SET text='A child playing in snow wearing a red coat with secret memory phrase',user_edited=1 WHERE id=102")
    db.execute("UPDATE captions SET text='A child playing in snow wearing a blue coat with secret memory phrase',user_edited=1 WHERE id=103")
    db.executemany('INSERT INTO persons(id,display_name,face_count) VALUES(?,?,2)',
                   [(301, 'Sample Child / 示例儿童'),
                    (302, 'Sample Adult / 示例成人')])
    db.executemany('''INSERT INTO face_detections
        (id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h,label_source)
        VALUES(?,?,?,0,0,1,1,'manual')''', [(1, 101, 301), (2, 101, 302), (3, 103, 301)])

import prepare_access_discovery_index as producer
with closing(producer.open_read_only(fixture.path.resolve(), time.monotonic())) as db:
    index, _catalog = producer.derive(db, producer.library('family-a'), producer.revision('1'))
    from app.access import discovery as d
    from app.access.discovery_provider import ReviewedFace, ReviewedIndex, ReviewedPerson
    source = d.scoped_source('family-a', lambda sql, args: db.execute(sql, args).fetchall())
    scope = tuple(str(row[0]) for row in source['assets'])
    search_index = ReviewedIndex('family-a', '1', scope, scope, d.digest(source),
        people=(ReviewedPerson('family-a', '301', 'Sample Child / 示例儿童',
                               ('示例儿童', 'Sample Child')),
                ReviewedPerson('family-a', '302', 'Sample Adult / 示例成人',
                               ('示例成人', 'Sample Adult'))),
        assignments=(ReviewedFace('1', '101', '301'),
                     ReviewedFace('2', '101', '302'),
                     ReviewedFace('3', '103', '301')))
index_path = root / 'discovery-index.json'
producer.write_new(index_path, json.dumps(asdict(index), sort_keys=True,
    ensure_ascii=True, separators=(',', ':')).encode())

workspace_path = root / 'assistant-workspace-v2.sqlite'
initialize_v2(workspace_path, clock=lambda: fixture.now)
client = TestClient(RuntimeConfiguration(fixture.path.resolve(), 'https://photohouse.test',
    (originals,), derived, discovery_indexes=(index_path,), assistant_enabled=True,
    assistant_workspace_path=workspace_path).build_app(clock=lambda: fixture.now),
    base_url='https://photohouse.test', client=('192.0.2.25', 23462))
fixture.addCleanup(client.close)
fixture.client = client
fixture.client.headers['Sec-Fetch-Site'] = 'same-origin'

from app.access.discovery_provider import MemoryIndexProvider
from test_assistant_kinship import MutableKinshipProvider, assistant_graph
client.app.state.discovery_runtime = replace(client.app.state.discovery_runtime,
    provider=MemoryIndexProvider((search_index,)))
graph = assistant_graph()
graph['scope'] = {'account_id': fixture.member_id, 'library_id': 'family-a'}
kinship = MutableKinshipProvider()
kinship.install(graph)
client.app.state.assistant_kinship_provider = kinship
planner = FixturePlanner()
client.app.state.assistant_intent_planner = planner


try:
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('command') == 'quit':
            break
        if message.get('command') == 'planner-stats':
            print(json.dumps({'id': message['id'], 'ok': True,
                              'calls': len(planner.calls)}), flush=True)
            continue
        if message.get('command') == 'planner-off':
            client.app.state.assistant_intent_planner = None
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
    fixture.doCleanups()
    LibraryReadTests.tearDownClass()

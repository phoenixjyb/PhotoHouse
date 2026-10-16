"""Synthetic ASGI bridge for the private assistant workspace browser test."""
import base64
from dataclasses import asdict, replace
import json
import os
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
fixture.client.close()
root = fixture.path.parent.resolve()
originals, derived = root / 'originals', root / 'derived'
originals.mkdir()
derived.mkdir()

import prepare_access_discovery_index as producer
from contextlib import closing
scene_fixture = os.environ.get('PH_SCENE_FIXTURE') == '1'
search_fixture = os.environ.get('PH_SEARCH_FIXTURE') == '1' or scene_fixture
scene_calls = []
scene_encoder_off = False
if scene_fixture:
    import hashlib
    import httpx
    import sqlite3
    from types import SimpleNamespace
    from test_visual_vector_loader import VisualVectorLoaderTests, IDENTITY
    from app.access.visual_vector_schema import create_visual_vector_schema
    from app.access.semantic_encoder import JointSpaceBinding, LocalSemanticEncoder
    from app.access.semantic_search import SemanticSearchRuntime
    from app.access.visual_candidates import canonical_vector_checksum
    vector_root = root / 'synthetic-vectors'
    vector_root.mkdir()
    vector_files = []
    with closing(sqlite3.connect(fixture.path)) as db, db:
        for aid, in db.execute('SELECT id FROM assets').fetchall():
            db.execute('UPDATE assets SET hash_sha256=? WHERE id=?', (hashlib.sha256(str(aid).encode()).hexdigest(), aid))
        create_visual_vector_schema(db)
        holder = SimpleNamespace(db=db, root=vector_root)
        for aid, vector in ((101, (0.0, 1.0)), (102, (1.0, 0.0))):
            path, _ = VisualVectorLoaderTests.add_vector(holder, aid, vector, source_hash=hashlib.sha256(str(aid).encode()).hexdigest())
            vector_files.append(path)
    pair = JointSpaceBinding(IDENTITY, replace(IDENTITY, artifact_sha256='c'*64, preprocessing_sha256='d'*64, model_version='text-v1'), 'e'*64)
    def encode(request):
        if scene_encoder_off:
            raise AssertionError('Scene recovery invoked the encoder')
        body = json.loads(request.content)
        scene_calls.append(body['query'])
        vector = [1.0, 0.0]
        return httpx.Response(200, json={'version': 1, 'binding_sha256': pair.binding_sha256,
            'query_sha256': hashlib.sha256(body['query'].encode()).hexdigest(), 'vector': vector,
            'checksum_sha256': canonical_vector_checksum(vector)})
    scene_encoder = LocalSemanticEncoder(pair, 'http://127.0.0.1:43210/v1/encode-text', transport=httpx.MockTransport(encode))
if search_fixture:
    # Explicit synthetic identities; no face inference or household data.
    import sqlite3
    with closing(sqlite3.connect(fixture.path)) as db, db:
        db.executemany('INSERT INTO persons(id,display_name,face_count) VALUES(?,?,2)',
                       [(301, 'Sample Child / 示例儿童'), (302, 'Sample Adult / 示例成人')])
        db.executemany('''INSERT INTO face_detections
            (id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h,label_source)
            VALUES(?,?,?,0,0,1,1,'manual')''',
            [(1,101,301), (2,101,302), (3,102,301), (4,102,302)])
        db.execute("UPDATE captions SET text='海边 beach synthetic evidence',user_edited=0 WHERE id IN (101,102)")
        db.execute('''INSERT INTO access_stories
            (id,asset_id,library_id,author_id,revision,title,text,language,byline,created_at,updated_at,deleted)
            VALUES(?,101,'family-a',?,1,'海边回忆','Synthetic original wording kept private','zh','',?,?,0)''',
            ('11111111-1111-4111-8111-111111111111', fixture.member_id, fixture.now, fixture.now))
with closing(producer.open_read_only(fixture.path.resolve(), time.monotonic())) as db:
    index, _catalog = producer.derive(db, producer.library('family-a'), producer.revision('1'))
    if search_fixture:
        from app.access import discovery as d
        from app.access.discovery_provider import ReviewedIndex, ReviewedPerson, ReviewedFace
        source = d.scoped_source('family-a', lambda sql, args: db.execute(sql, args).fetchall())
        scope = tuple(str(row[0]) for row in source['assets'])
        search_index = ReviewedIndex('family-a', '1', scope, scope, d.digest(source),
            people=(ReviewedPerson('family-a','301','Sample Child / 示例儿童',('示例儿童','Sample Child')),
                    ReviewedPerson('family-a','302','Sample Adult / 示例成人',('示例成人','Sample Adult'))),
            assignments=tuple(ReviewedFace(str(fid),str(aid),str(pid)) for fid,aid,pid in
                [(1,101,301), (2,101,302), (3,102,301), (4,102,302)]))
index_path = root / 'discovery-index.json'
producer.write_new(index_path, json.dumps(asdict(index), sort_keys=True, ensure_ascii=True,
    separators=(',', ':')).encode())

# Initialization is confined to this disposable synthetic test directory.
workspace_path = root / 'assistant-workspace-v2.sqlite'
initialize_v2(workspace_path, clock=lambda: fixture.now)
client = TestClient(RuntimeConfiguration(fixture.path.resolve(), 'https://photohouse.test',
    (originals,), derived, discovery_indexes=(index_path,), assistant_enabled=True,
    assistant_workspace_path=workspace_path).build_app(clock=lambda: fixture.now),
    base_url='https://photohouse.test', client=('192.0.2.25', 23462))
fixture.addCleanup(client.close)
fixture.client = client
fixture.client.headers['Sec-Fetch-Site'] = 'same-origin'
discovery = client.app.state.discovery_runtime
if search_fixture:
    from app.access.discovery_provider import MemoryIndexProvider
    from test_assistant_kinship import MutableKinshipProvider, assistant_graph
    discovery = replace(discovery, provider=MemoryIndexProvider((search_index,)))
    client.app.state.discovery_runtime = discovery
    graph = assistant_graph()
    graph['scope'] = {'account_id': fixture.member_id, 'library_id': 'family-a'}
    kinship = MutableKinshipProvider()
    kinship.install(graph)
    client.app.state.assistant_kinship_provider = kinship

if scene_fixture:
    client.app.state.semantic_search_runtime = SemanticSearchRuntime(discovery, vector_root, scene_encoder)
    client.app.state.assistant_semantic_search_enabled = True

def append_synthetic_exchange(store, account_id, thread_id, revision, question, reply):
    request_id = str(uuid.uuid4())
    started = store.begin_turn(account_id, 'family-a', thread_id, request_id,
                               revision, question)
    summary = dict(version=1, kind='clarification', reply=reply, context=None,
                   filters=None, total=0, has_more=False, effect=None)
    return store.complete_turn(account_id, 'family-a', thread_id, request_id,
                               started['lease_id'], summary)

try:
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('command') == 'quit':
            break
        if scene_fixture and message.get('command') == 'scene-stats':
            print(json.dumps({'id': message['id'], 'calls': len(scene_calls)}), flush=True)
            continue
        if scene_fixture and message.get('command') == 'scene-encoder-off':
            scene_encoder_off = True
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if scene_fixture and message.get('command') == 'scene-off':
            client.app.state.assistant_semantic_search_enabled = False
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if scene_fixture and message.get('command') == 'scene-corrupt':
            vector_files[0].write_bytes(b'corrupt synthetic vector')
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if message.get('command') == 'discovery-off':
            client.app.state.discovery_runtime = None
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if message.get('command') == 'discovery-on':
            client.app.state.discovery_runtime = discovery
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if message.get('command') == 'workspace-unhealthy':
            client.app.state.assistant_workspace_healthy = False
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if message.get('command') == 'workspace-healthy':
            client.app.state.assistant_workspace_healthy = True
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if message.get('command') == 'seed-private-history':
            store = client.app.state.assistant_workspace_store
            thread = store.create_thread(fixture.member_id, 'family-a')['thread_id']
            first_question = '  <img src=x onerror=alert(1)> 家庭 🌟  '
            for revision in range(45):
                question = (first_question if revision == 0 else
                            f'Synthetic private question {revision + 1}')
                append_synthetic_exchange(store, fixture.member_id, thread, revision, question,
                    f'Synthetic private reply {revision + 1}')
            print(json.dumps({'id': message['id'], 'ok': True,
                              'thread_id': thread, 'first_question': first_question.strip()}), flush=True)
            continue
        if message.get('command') == 'append-private-history':
            store = client.app.state.assistant_workspace_store
            thread = message.get('thread_id')
            current = store.get_thread(fixture.member_id, 'family-a', thread)
            revision = current['thread']['revision']
            append_synthetic_exchange(store, fixture.member_id, thread, revision,
                f'Synthetic concurrent question {revision + 1}',
                f'Synthetic concurrent reply {revision + 1}')
            print(json.dumps({'id': message['id'], 'ok': True,
                              'revision': revision + 1}), flush=True)
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

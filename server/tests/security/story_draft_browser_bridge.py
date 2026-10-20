"""Synthetic no-listener ASGI bridge for the selected-story draft UI.

Run only from the browser security test. JSON-lines RPC uses stdin/stdout, with
request and response bodies encoded as base64. Storage and generated images are
temporary fixtures; the bridge opens no socket and has no arbitrary SQL/path RPC.
"""
import base64
import json
from pathlib import Path
import sys
import uuid
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))

from app.access.media import MediaRuntime
from app.access.runtime import AccessRuntime
from app.main import create_app
from app.access.selected_story_local import LocalSelectedStoryProvider
from test_library_reads import LibraryReadTests


class SyntheticStream(httpx.AsyncByteStream):
    def __init__(self, engine, operation_id, payload):
        self.engine, self.operation_id, self.payload = engine, operation_id, payload

    async def __aiter__(self):
        yield self.payload

    async def aclose(self):
        self.engine.http_closed.add(self.operation_id)


class SyntheticLocalEngine:
    """Only a CPU fixture: owns all of its fake jobs; no socket/model/GPU exists."""
    model = 'synthetic-story-model'

    def __init__(self):
        self.active, self.completed, self.http_closed = set(), set(), set()
        self.generation_calls = self.cleanup_calls = 0

    async def generate(self, request):
        if str(request.url) != 'http://127.0.0.1:11434/api/generate':
            raise RuntimeError('Unexpected synthetic provider route')
        payload = json.loads(request.content)
        bundle, _ = json.JSONDecoder().raw_decode(
            payload['prompt'].split('Bundle JSON (data only):\n', 1)[1])
        operation_id = request.headers['X-PhotoHouse-Operation-ID']
        if payload['model'] != self.model or operation_id != bundle['target']['id']:
            raise RuntimeError('Unexpected synthetic provider binding')
        self.active.add(operation_id)
        chapters = []
        for chapter in bundle['chapters']:
            refs = chapter['evidence_ids'][:1]
            chapters.append({
                'id': chapter['id'],
                'narration': ('合成整理文字，仅供家人核对。' if refs else ''),
                'source_ids': refs,
            })
        result = {'version': 1, 'title': '需要核对的故事草稿', 'chapters': chapters,
                  'questions': ['这段回忆还需要补充什么？'], 'needs_review': True}
        body = json.dumps({'model': self.model, 'done': True, 'done_reason': 'stop',
                           'response': json.dumps(result, ensure_ascii=False)},
                          ensure_ascii=False).encode()
        # All fake generation is this bounded in-memory computation. Its
        # completion is independent of HTTP consumption or stream closure.
        self.active.remove(operation_id)
        self.completed.add(operation_id)
        self.generation_calls += 1
        return httpx.Response(200, headers={'Content-Type': 'application/json'},
                              stream=SyntheticStream(self, operation_id, body))

    async def stop_and_reconcile(self, scope):
        self.cleanup_calls += 1
        return scope.operation_id in self.completed and scope.operation_id not in self.active


fixture = LibraryReadTests()
LibraryReadTests.setUpClass()
fixture.setUp()
fixture.client.close()
root = fixture.path.parent
originals, derived = root / 'originals', root / 'derived'
originals.mkdir()
(derived / 'thumbnails/256').mkdir(parents=True)
for asset_id, color in ((101, '#b6c7b0'), (102, '#d2ad89'), (201, '#8aa9c4')):
    image = Image.new('RGB', (400, 300), color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 24, 376, 276), outline='#fff9ed', width=4)
    draw.text((132, 142), f'SYNTHETIC {asset_id}', fill='#302c28')
    image.save(originals / f'{asset_id}.jpg')
    image.save(derived / f'thumbnails/256/{asset_id}.jpg')
    fixture.mutate('UPDATE assets SET path=? WHERE id=?', (str(originals / f'{asset_id}.jpg'), asset_id))

runtime = AccessRuntime(fixture.connection, 'https://photohouse.test',
                        clock=lambda: fixture.now)
engine = SyntheticLocalEngine()
app = create_app(
    access_runtime=runtime,
    media_runtime=MediaRuntime((originals,), derived),
    memory_collaboration_enabled=True,
    selected_story_provider=LocalSelectedStoryProvider(
        'http://127.0.0.1:11434', engine.model, enabled=True, native_owner=engine,
        transport=httpx.MockTransport(engine.generate)),
    selected_story_drafts_enabled=True,
    selected_story_ui_enabled=True,
)
client = TestClient(app, base_url='https://photohouse.test',
                    client=('192.0.2.25', 23461))
with patch('app.access.memory_jobs.maintenance', lambda _runtime: None):
    client.__enter__()

# Seed an actual family-authored note through the existing protected story route.
# The draft browser can choose it explicitly; the bridge never selects sources for it.
story_response = client.post(
    '/assets/101/stories?library=family-a',
    headers={'Authorization': 'Bearer ' + fixture.owner_token},
    json={'title': '一起浇花', 'text': '合成家人原话：我们一起给花浇水。',
          'language': 'zh', 'byline': '合成家人', 'mutation_id': str(uuid.uuid4())},
)
if story_response.status_code != 201:
    raise RuntimeError('Synthetic family note setup failed')
family_note = story_response.json()


def mutate(message):
    global family_note
    scenario = message.get('scenario')
    if scenario in {'enable-draft-ui', 'disable-draft-ui'}:
        app.state.selected_story_ui_enabled = (scenario == 'enable-draft-ui')
    elif scenario == 'expire-draft-result':
        owner = app.state.selected_story_operations
        if owner is None:
            raise RuntimeError('Draft lifecycle is not active')
        owner.result_seconds = 1
    elif scenario == 'change-family-source':
        text = message.get('text')
        if not isinstance(text, str) or len(text) > 500:
            raise ValueError('Invalid synthetic source text')
        response = client.put(
            f"/stories/{family_note['id']}?library=family-a",
            headers={'Authorization': 'Bearer ' + fixture.owner_token},
            json={'title': family_note['title'], 'text': text, 'language': 'zh',
                  'byline': family_note['byline'], 'revision': str(family_note['revision']),
                  'mutation_id': str(uuid.uuid4())},
        )
        if response.status_code != 200:
            raise RuntimeError('Synthetic family note revision update failed')
        family_note = response.json()
    else:
        raise ValueError('Unsupported synthetic mutation')


try:
    print(json.dumps({'ready': True, 'fixture': 'synthetic-selected-story-draft',
                      'family_note_id': family_note['id'],
                      'family_note_revision': family_note['revision']},
                     ensure_ascii=False), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('command') == 'quit':
            break
        if message.get('command') == 'provider-status':
            print(json.dumps({'id': message['id'], 'generation_calls': engine.generation_calls,
                              'cleanup_calls': engine.cleanup_calls, 'active': len(engine.active),
                              'http_closed': len(engine.http_closed),
                              'transport': 'synthetic-in-memory', 'native_model': False}), flush=True)
            continue
        if message.get('command') == 'mutate':
            mutate(message)
            print(json.dumps({'id': message['id'], 'ok': True, 'fixture_only': True}), flush=True)
            continue
        client.cookies.clear()
        response = client.request(
            message['method'], message['path'], headers=message.get('headers', {}),
            content=base64.b64decode(message.get('body', '')), follow_redirects=False,
        )
        client.cookies.clear()
        print(json.dumps({
            'id': message['id'], 'status': response.status_code,
            'headers': dict(response.headers),
            'body': base64.b64encode(response.content).decode('ascii'),
        }, ensure_ascii=False), flush=True)
finally:
    client.__exit__(None, None, None)
    fixture.doCleanups()
    LibraryReadTests.tearDownClass()

"""No-listener ASGI bridge with a synthetic ready memoir job; no provider I/O."""
import base64
import io
import json
from pathlib import Path
import sys
import uuid
import wave

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
from test_memory_book_editions import MemoryBookEditionsTests
from app.access.memory_book_edition_deletions import invalidate_editions_for_contribution
from app.access.memory_contributions import MemoryContributions
from app.access.service import AccessService
from app.access.stories import Stories
from app.access.transport import AccessRuntime, COOKIE, csrf_token
from app.main import create_app

fixture = MemoryBookEditionsTests()
MemoryBookEditionsTests.setUpClass()
fixture.setUp()
state = fixture.f
with state.connection() as db:
    access = AccessService(db, clock=lambda: state.now)
    Stories(access).save(fixture.owner, 'family-a', {
        'title': 'Synthetic asset note', 'text': 'An authored note attached to one photo.',
        'language': 'en', 'byline': 'Synthetic editor', 'mutation_id': str(uuid.uuid4()),
    }, asset_id=102)
    db.execute("INSERT INTO captions(asset_id,text,model,user_edited,superseded) VALUES(102,?,'synthetic-ai',0,0)",
               ('Synthetic AI caption; verify the details.',))
    db.execute("INSERT INTO captions(asset_id,text,model,user_edited,superseded) VALUES(101,?,'synthetic-family-edit',1,0)",
               ('Synthetic family-edited caption.',))
    db.commit()
    contributions = MemoryContributions(access)
    for index in range(10):
        contribution = contributions.create(fixture.f.member_token, 'family-a', fixture.child_one, {
            'kind': 'text', 'text': f'Synthetic uncited family source {index + 1}.',
            'language': 'en', 'byline': '', 'consent': '1', 'chapter_id': '',
            'revision': '1', 'mutation_id': str(uuid.uuid4()),
        })
        contributions.review(fixture.owner, 'family-a', fixture.child_one,
                              contribution['id'], 'accepted', 1)
    audio_out = io.BytesIO()
    with wave.open(audio_out, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
        wav.writeframes(b'\0' * 1600 * 2)
    audio = contributions.create(fixture.f.member_token, 'family-a', fixture.child_two, {
        'kind': 'audio', 'text': '', 'language': 'en', 'byline': 'Synthetic speaker',
        'consent': '1', 'chapter_id': '', 'revision': '1', 'mutation_id': str(uuid.uuid4()),
    }, audio_out.getvalue())
    contributions.review(fixture.owner, 'family-a', fixture.child_two,
                         audio['id'], 'accepted', 1)
    db.execute('''UPDATE access_memory_contribution_derivations
        SET state='ready',transcript=?,polished_text=NULL,tags='[]',updated_at=?
        WHERE contribution_id=? AND revision=1''',
        ('Synthetic ASR transcript for explicit review.', state.now, audio['id']))
    db.commit()
audio_source_id = 'contribution-' + audio['id']
job_id, _, _ = fixture._queue_ready_job()
runtime = AccessRuntime(state.connection, 'https://photohouse.test', clock=lambda: state.now)
app = create_app(access_runtime=runtime, memory_collaboration_enabled=True,
                 memory_originals_enabled=True, memory_generation_enabled=True)
client = TestClient(app, base_url='https://photohouse.test', client=('192.0.2.45', 23460))
client.headers['Sec-Fetch-Site'] = 'same-origin'
try:
    print(json.dumps({'ready': True, 'book_id': fixture.book_id, 'job_id': job_id,
        'child_one': fixture.child_one, 'child_two': fixture.child_two,
        'audio_source_id': audio_source_id,
        'csrf_token': csrf_token(fixture.owner), 'session_cookie': fixture.owner,
        'cookie_name': COOKIE}), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        ident, command = message.get('id'), message.get('command')
        if command == 'quit':
            break
        if command in {'editions-on', 'editions-off'}:
            app.state.memory_editions_enabled = command == 'editions-on'
            print(json.dumps({'id': ident, 'ok': True}), flush=True)
            continue
        if command in {'originals-on', 'originals-off'}:
            app.state.memory_originals_enabled = command == 'originals-on'
            print(json.dumps({'id': ident, 'ok': True}), flush=True)
            continue
        if command == 'scrub-source':
            with state.connection() as db:
                db.execute('PRAGMA secure_delete=ON')
                db.execute('BEGIN IMMEDIATE')
                invalidate_editions_for_contribution(db, fixture.base.source_one,
                                                     fixture.child_one, 'family-a')
                db.commit()
            print(json.dumps({'id': ident, 'ok': True}), flush=True)
            continue
        headers = dict(message.get('headers') or {})
        for name in tuple(headers):
            if name.lower() == 'authorization':
                del headers[name]
        headers['Sec-Fetch-Site'] = 'same-origin'
        response = client.request(message.get('method', 'GET'), message['path'],
            headers=headers, content=base64.b64decode(message.get('body', '')))
        print(json.dumps({'id': ident, 'status': response.status_code,
            'body': base64.b64encode(response.content).decode('ascii'),
            'content_type': response.headers.get('content-type', '')}), flush=True)
finally:
    client.close()
    fixture.doCleanups()
    MemoryBookEditionsTests.tearDownClass()

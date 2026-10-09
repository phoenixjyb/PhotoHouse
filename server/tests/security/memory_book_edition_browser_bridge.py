"""No-listener ASGI bridge with a synthetic ready memoir job; no provider I/O."""
import base64
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
from test_memory_book_editions import MemoryBookEditionsTests
from app.access.memory_book_edition_deletions import invalidate_editions_for_contribution
from app.access.service import AccessService
from app.access.transport import AccessRuntime, COOKIE, csrf_token
from app.main import create_app

fixture = MemoryBookEditionsTests()
MemoryBookEditionsTests.setUpClass()
fixture.setUp()
state = fixture.f
job_id, _, _ = fixture._queue_ready_job()
runtime = AccessRuntime(state.connection, 'https://photohouse.test', clock=lambda: state.now)
app = create_app(access_runtime=runtime, memory_collaboration_enabled=True,
                 memory_generation_enabled=True)
client = TestClient(app, base_url='https://photohouse.test', client=('192.0.2.45', 23460))
client.headers['Sec-Fetch-Site'] = 'same-origin'
try:
    print(json.dumps({'ready': True, 'book_id': fixture.book_id, 'job_id': job_id,
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

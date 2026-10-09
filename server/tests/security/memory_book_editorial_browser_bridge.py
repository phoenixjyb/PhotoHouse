"""Synthetic ASGI pipe bridge for memoir editorial browser tests."""
import base64
import io
import json
import sys
import uuid
import wave

from fastapi.testclient import TestClient

ROOT = __import__('pathlib').Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
from test_memory_book_editorial_service import MemoryBookEditorialServiceTests
from app.access.runtime import AccessRuntime
from app.main import create_app
from app.access.transport import COOKIE, csrf_token
from app.access.service import AccessService
from app.access.memory_contributions import MemoryContributions
from app.access.memory_source_refs import TABLE as SOURCE_REFS_TABLE

fixture = MemoryBookEditorialServiceTests()
MemoryBookEditorialServiceTests.setUpClass()
fixture.setUp()
state = fixture.f
buffer = io.BytesIO()
with wave.open(buffer, 'wb') as wav:
    wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(16000)
    wav.writeframes(b'\x00\x00' * 1600)
audio_bytes = buffer.getvalue()
with state.connection() as db:
    db.execute('UPDATE access_memory_contributions SET byline=? WHERE id=?',
               ('Synthetic family byline', fixture.source_one))
    db.commit()
    contributions = MemoryContributions(AccessService(db, clock=lambda: state.now))
    created_audio = contributions.create(state.member_token, 'family-a', fixture.child_one, {
        'kind': 'audio', 'text': '', 'language': 'en', 'byline': 'synthetic audio',
        'consent': '1', 'chapter_id': 'chapter-1', 'revision': '1',
        'mutation_id': str(uuid.uuid4()),
    }, audio=audio_bytes)
    accepted_audio = contributions.review(state.owner_token, 'family-a', fixture.child_one,
                                           created_audio['id'], 'accepted', 1)
    db.execute(f'''INSERT INTO {SOURCE_REFS_TABLE}
        (story_id,revision,chapter_id,ordinal,contribution_id)
        VALUES(?,1,'chapter-1',1,?)''', (fixture.child_one, accepted_audio['id']))
    db.execute('''UPDATE access_memory_contribution_derivations
        SET state='ready',transcript=?,polished_text=? WHERE contribution_id=?''',
        ('synthetic dictated words', 'synthetic derived draft', fixture.source_two))
    db.commit()
runtime = AccessRuntime(state.connection, 'https://photohouse.test', clock=lambda: state.now)
app = create_app(access_runtime=runtime, memory_collaboration_enabled=True,
                 memory_originals_enabled=True,
                 memory_editorial_enabled=True)
client = TestClient(app, base_url='https://photohouse.test',
                    client=('192.0.2.44', 23460))
client.headers['Sec-Fetch-Site'] = 'same-origin'
session_cookie = fixture.owner
try:
    print(json.dumps({'ready': True, 'book_id': fixture.book_id,
                      'text_source_id': fixture.source_one,
                      'second_text_source_id': fixture.source_two,
                      'first_story_id': fixture.child_one,
                      'second_story_id': fixture.child_two,
                      'audio_source_id': accepted_audio['id'],
                      'audio_sha256': accepted_audio['sha256'],
                      'csrf_token': csrf_token(session_cookie),
                      'session_cookie': session_cookie,
                      'cookie_name': COOKIE}), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('command') == 'quit':
            break
        ident = message.get('id')
        if message.get('command') == 'editorial-off':
            app.state.memory_editorial_enabled = False
            print(json.dumps({'id': ident, 'ok': True}), flush=True)
            continue
        if message.get('command') == 'editorial-on':
            app.state.memory_editorial_enabled = True
            print(json.dumps({'id': ident, 'ok': True}), flush=True)
            continue
        if message.get('command') == 'large-catalog':
            created_count = 0
            with state.connection() as db:
                access = AccessService(db, clock=lambda: state.now)
                contributions = MemoryContributions(access)
                for story_id, ordinals in ((fixture.child_one, (*range(0, 1), *range(2, 12))),
                                           (fixture.child_two, range(1, 12))):
                    for ordinal in ordinals:
                        created = contributions.create(
                            state.member_token, 'family-a', story_id, {
                                'kind': 'text', 'text': f'synthetic chooser source {created_count + 1}',
                                'language': 'en', 'byline': 'synthetic chooser fixture',
                                'consent': '1', 'chapter_id': 'chapter-1', 'revision': '1',
                                'mutation_id': str(uuid.uuid4()),
                            })
                        accepted = contributions.review(
                            state.owner_token, 'family-a', story_id, created['id'], 'accepted', 1)
                        db.execute(f'''INSERT INTO {SOURCE_REFS_TABLE}
                            (story_id,revision,chapter_id,ordinal,contribution_id)
                            VALUES(?,1,'chapter-1',?,?)''',
                            (story_id, ordinal, accepted['id']))
                        db.commit()
                        created_count += 1
            print(json.dumps({'id': ident, 'created': created_count}), flush=True)
            continue
        if message.get('command') == 'delete-source':
            response = client.delete(
                f'/memory-community/v1/stories/{fixture.child_one}/contributions/{fixture.source_one}?library=family-a',
                headers={'Cookie': f'{COOKIE}={session_cookie}',
                         'Origin': 'https://photohouse.test',
                         'X-CSRF-Token': csrf_token(session_cookie),
                         'Sec-Fetch-Site': 'same-origin'})
            print(json.dumps({'id': ident, 'status': response.status_code}), flush=True)
            continue
        headers = dict(message.get('headers') or {})
        for key in tuple(headers):
            if key.lower() == 'authorization':
                headers.pop(key)
        headers['Sec-Fetch-Site'] = 'same-origin'
        body = base64.b64decode(message.get('body', ''))
        response = client.request(message.get('method', 'GET'), message['path'],
                                  headers=headers, content=body)
        print(json.dumps({'id': ident, 'status': response.status_code,
                          'body': base64.b64encode(response.content).decode('ascii'),
                          'content_type': response.headers.get('content-type', '')}), flush=True)
finally:
    client.close()
    fixture.doCleanups()
    MemoryBookEditorialServiceTests.tearDownClass()

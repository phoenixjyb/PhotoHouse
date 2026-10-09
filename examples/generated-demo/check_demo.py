"""Generated-data, no-listener family story and memoir journey.

Run from the curated repository with its CPU demo dependencies installed.
This is an in-process development check, not a production server entry point.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import sys
import tempfile
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'server' / 'backend'
sys.path.insert(0, str(BACKEND))


def check():
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine
    from fastapi.testclient import TestClient
    from PIL import Image, ImageDraw
    from app.main import create_app
    from app.access.bootstrap import bootstrap_owner
    from app.access.service import AccessService
    from app.access.transport import AccessRuntime
    from app.access.media import MediaRuntime

    # Reserved fictional numbers are used only inside the temporary database.
    owner, member = '+12025550100', '+12025550102'
    password = secrets.token_urlsafe(32)
    origin = 'https://photohouse.test'
    library = 'generated-family'
    with tempfile.TemporaryDirectory(prefix='photohouse-generated-demo-') as temp:
        root = Path(temp)
        path = root / 'demo.sqlite'
        originals, derived = root / 'originals', root / 'derived'
        originals.mkdir()
        (derived / 'thumbnails' / '256').mkdir(parents=True)
        (derived / 'thumbnails' / '1024').mkdir(parents=True)
        engine = create_engine('sqlite:///' + str(path))
        try:
            with engine.begin() as connection:
                cfg = Config()
                cfg.set_main_option('script_location', str(BACKEND / 'migrations'))
                cfg.attributes['connection'] = connection
                command.upgrade(cfg, 'head')
        finally:
            engine.dispose()

        @contextmanager
        def database():
            db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True)
            db.execute('PRAGMA foreign_keys=ON')
            try:
                yield db
            finally:
                if db.in_transaction:
                    db.rollback()
                db.close()

        with database() as db:
            bootstrap_owner(db, phone=owner, password=password, library_id=library)
            access = AccessService(db)
            owner_token = access.login(owner, password)
            access.register(member, password, access.invite(owner_token, library, member), '演示家人')
            for ident, color in ((101, '#b6c7b0'), (102, '#d2ad89')):
                image = Image.new('RGB', (320, 240), color)
                draw = ImageDraw.Draw(image)
                draw.rectangle((20, 20, 300, 220), outline='#fff9ed', width=4)
                draw.ellipse((120, 80, 200, 160), fill='#fff9ed')
                original = originals / f'{ident}.jpg'
                image.save(original, 'JPEG')
                for size in (256, 1024):
                    preview = image.copy()
                    preview.thumbnail((size, size))
                    preview.save(derived / 'thumbnails' / str(size) / f'{ident}.jpg', 'JPEG')
                digest = hashlib.sha256(original.read_bytes()).hexdigest()
                db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
                    VALUES (?,?,?,'active','image/jpeg',320,240,?)''',
                    (ident, str(original), digest, f'2026-01-0{ident-100}'))
                db.execute('INSERT INTO access_asset_libraries VALUES (?,?)', (ident, library))
            db.commit()

        app = create_app(access_runtime=AccessRuntime(database, origin),
            media_runtime=MediaRuntime((originals,), derived),
            memory_collaboration_enabled=True, memory_originals_enabled=True,
            memory_generation_enabled=False, memory_editorial_enabled=True)
        with TestClient(app, base_url=origin, client=('192.0.2.21', 23000)) as client:
            client.headers['Sec-Fetch-Site'] = 'same-origin'

            def require(response, status=200):
                if response.status_code != status:
                    raise RuntimeError('Generated demo request failed')
                return response

            def login(phone):
                response = require(client.post('/auth/login', json={
                    'phone': phone, 'password': password, 'transport': 'native'}))
                return {'Authorization': 'Bearer ' + response.json()['access_token']}

            owner_headers, member_headers = login(owner), login(member)
            require(client.get('/assets?library=' + library), 401)
            require(client.get('/memory-community/v1/books?library=' + library), 401)
            gallery = require(client.get('/assets?library=' + library, headers=member_headers)).json()
            if gallery['total'] != 2:
                raise RuntimeError('Generated gallery is incomplete')
            preview = require(client.get('/assets/101/thumbnail?library=' + library,
                                         headers=member_headers))
            if preview.headers['content-type'] != 'image/jpeg' or not preview.content.startswith(b'\xff\xd8'):
                raise RuntimeError('Generated preview is invalid')

            def create_story(title, asset_ids, narration):
                ids = ','.join(str(ident) for ident in asset_ids)
                draft = require(client.post('/story-workspace/preview?library=' + library,
                    headers=owner_headers, json={'asset_ids': ids, 'title': title,
                        'theme': 'everyday', 'language': 'zh'})).json()
                chapter = draft['chapters'][0] | {'narration': narration}
                body = {'title': draft['title'], 'theme': draft['theme'],
                    'language': 'zh', 'asset_ids': ids,
                    'chapters': json.dumps([chapter], ensure_ascii=False),
                    'selection_revision': draft['selection_revision'], 'revision': '0',
                    'mutation_id': str(uuid.uuid4())}
                saved = require(client.post('/memory-stories?library=' + library,
                    headers=owner_headers, json=body)).json()
                return saved, body

            def contribute_and_accept(story, text):
                base = '/memory-community/v1/stories/' + story['id']
                created = require(client.post(base + '/contributions/text?library=' + library,
                    headers=member_headers, json={'kind': 'text', 'text': text,
                        'language': 'zh', 'byline': '演示家人', 'consent': '1',
                        'chapter_id': 'chapter-1', 'revision': story['revision'],
                        'mutation_id': str(uuid.uuid4())})).json()
                if created['state'] != 'pending' or not created['processing_consent']:
                    raise RuntimeError('Generated family contribution was not pending with consent')
                accepted = require(client.post(base + '/contributions/' + created['id']
                    + '/review?library=' + library, headers=owner_headers,
                    json={'state': 'accepted', 'revision': story['revision']})).json()
                if accepted['state'] != 'accepted' or not accepted['processing_consent']:
                    raise RuntimeError('Generated family contribution was not accepted')
                reopened = require(client.get(base + '/contributions/' + created['id']
                    + '?library=' + library, headers=member_headers)).json()
                if reopened['text'] != text:
                    raise RuntimeError('Generated original contribution did not persist')
                return created['id'], base

            def edit_story_references(story, base_body, contribution_ids):
                body = base_body | {'revision': story['revision'],
                                    'mutation_id': str(uuid.uuid4()),
                                    'contribution_refs': json.dumps([{
                                        'chapter_id': 'chapter-1',
                                        'contribution_ids': contribution_ids,
                                    }], ensure_ascii=False)}
                return require(client.put('/memory-stories/' + story['id']
                    + '?library=' + library + '&contribution_refs=1',
                    headers=owner_headers, json=body)).json()

            first_story, first_body = create_story('湖边的一天', [101, 102],
                '这是一段明确标记为演示的合成故事。')
            first_contribution, first_path = contribute_and_accept(first_story,
                '演示家人记得湖边有轻柔的风。')
            first_story = edit_story_references(first_story, first_body, [first_contribution])

            second_story, second_body = create_story('回家路上的灯光', [102],
                '这是另一段手动撰写的合成故事。')
            second_contribution, second_path = contribute_and_accept(second_story,
                '演示家人记得回家时窗边亮着暖色的灯。')
            second_story = edit_story_references(second_story, second_body, [second_contribution])

            first_refs = require(client.get('/memory-stories/' + first_story['id']
                + '/contribution-refs?library=' + library + '&revision=' + first_story['revision'],
                headers=owner_headers)).json()
            second_refs = require(client.get('/memory-stories/' + second_story['id']
                + '/contribution-refs?library=' + library + '&revision=' + second_story['revision'],
                headers=owner_headers)).json()
            if (first_refs['chapters'][0]['contribution_ids'] != [first_contribution]
                    or second_refs['chapters'][0]['contribution_ids'] != [second_contribution]):
                raise RuntimeError('Accepted source references were not linked to both stories')

            book_body = {'title': '演示家庭回忆录', 'language': 'zh',
                'introduction': 'DEMO 手工开场；这段文字由演示流程提供，不是模型生成。',
                'story_ids': first_story['id'] + ',' + second_story['id'],
                'revision': '0', 'mutation_id': str(uuid.uuid4())}
            book = require(client.post('/memory-community/v1/books?library=' + library,
                headers=owner_headers, json=book_body)).json()
            book_id = book['id']
            book_path = '/memory-community/v1/books/' + book_id
            detail = require(client.get(book_path + '?library=' + library,
                headers=owner_headers)).json()
            if [item['id'] for item in detail['stories']] != [first_story['id'], second_story['id']]:
                raise RuntimeError('Generated memoir did not preserve selected story order')
            require(client.get(book_path + '?library=' + library), 401)

            first_ref = {'story_id': first_story['id'], 'story_revision': first_story['revision'],
                'chapter_id': 'chapter-1', 'contribution_id': first_contribution}
            second_ref = {'story_id': second_story['id'], 'story_revision': second_story['revision'],
                'chapter_id': 'chapter-1', 'contribution_id': second_contribution}
            transition_text = 'DEMO 手工衔接：从湖边的风，走到回家路上的灯光。'

            def save_editorial(expected_revision, *, references=True):
                editorial = {'version': 1, 'revision': expected_revision,
                    'mutation_id': str(uuid.uuid4()),
                    'children': [
                        {'story_id': first_story['id'], 'revision': first_story['revision']},
                        {'story_id': second_story['id'], 'revision': second_story['revision']},
                    ],
                    'introduction_source_refs': [first_ref] if references else [],
                    'transitions': [{
                        'left_story_id': first_story['id'], 'right_story_id': second_story['id'],
                        'text': transition_text if references else '',
                        'source_refs': [second_ref] if references else [],
                    }]}
                return require(client.put(book_path + '/editorial?library=' + library,
                    headers=owner_headers, json=editorial)).json()

            require(client.get(book_path + '/editorial?library=' + library), 401)
            saved_editorial = save_editorial('1')
            reopened_editorial = require(client.get(book_path + '/editorial?library=' + library,
                headers=owner_headers)).json()
            if (saved_editorial['state'] != 'current'
                    or reopened_editorial['transitions'][0]['text'] != transition_text
                    or len(reopened_editorial['introduction_source_refs']) != 1
                    or len(reopened_editorial['transitions'][0]['source_refs']) != 1):
                raise RuntimeError('Generated memoir editorial did not save and reopen with citations')

            # Explicitly remove a story's source links. The contribution itself
            # remains an independent original that its author can still read.
            removed_story_refs_body = second_body | {
                'revision': second_story['revision'], 'mutation_id': str(uuid.uuid4()),
                'contribution_refs': '[]'}
            second_story = require(client.put('/memory-stories/' + second_story['id']
                + '?library=' + library + '&contribution_refs=1',
                headers=owner_headers, json=removed_story_refs_body)).json()
            no_refs = require(client.get('/memory-stories/' + second_story['id']
                + '/contribution-refs?library=' + library + '&revision=' + second_story['revision'],
                headers=owner_headers)).json()
            remaining_original = require(client.get(second_path + '/contributions/'
                + second_contribution + '?library=' + library,
                headers=member_headers)).json()
            if (no_refs['chapters'][0]['contribution_ids']
                    or remaining_original['text'] != '演示家人记得回家时窗边亮着暖色的灯。'
                    or not remaining_original['processing_consent']):
                raise RuntimeError('Removing a story reference changed its original contribution')
            stale_after_removal = require(client.get(book_path + '/editorial?library=' + library,
                headers=owner_headers)).json()
            if (stale_after_removal['state'] != 'source_changed'
                    or stale_after_removal['transitions']
                    or stale_after_removal['introduction_source_refs']):
                raise RuntimeError('Removed child source references did not withhold stale memoir prose')

            # Relink the same accepted original and author a current editorial
            # snapshot before demonstrating a separate child revision change.
            second_story = edit_story_references(second_story, second_body, [second_contribution])
            second_ref = {'story_id': second_story['id'], 'story_revision': second_story['revision'],
                'chapter_id': 'chapter-1', 'contribution_id': second_contribution}
            refreshed_editorial = save_editorial(stale_after_removal['revision'])
            reopened_editorial = require(client.get(book_path + '/editorial?library=' + library,
                headers=owner_headers)).json()
            if (refreshed_editorial['state'] != 'current'
                    or reopened_editorial['transitions'][0]['text'] != transition_text):
                raise RuntimeError('Updated story citations did not reopen with current prose')

            # A title-only child revision preserves story citations, while the
            # memoir snapshot correctly stops presenting prose bound to old revisions.
            changed_story_body = second_body | {'revision': second_story['revision'],
                'mutation_id': str(uuid.uuid4()), 'title': '回家路上的灯光（修订）'}
            changed_story = require(client.put('/memory-stories/' + second_story['id']
                + '?library=' + library, headers=owner_headers, json=changed_story_body)).json()
            changed_editorial = require(client.get(book_path + '/editorial?library=' + library,
                headers=owner_headers)).json()
            if (changed_story['revision'] == second_story['revision']
                    or changed_editorial['state'] != 'source_changed'
                    or changed_editorial['transitions']
                    or changed_editorial['introduction_source_refs']
                    or transition_text in json.dumps(changed_editorial, ensure_ascii=False)):
                raise RuntimeError('Changed child revision did not hide prior memoir prose')
            retained_original = require(client.get(second_path + '/contributions/'
                + second_contribution + '?library=' + library,
                headers=member_headers)).json()
            if retained_original['text'] != '演示家人记得回家时窗边亮着暖色的灯。':
                raise RuntimeError('Child revision changed the original family contribution')

            capabilities = require(client.get('/memory-community/v1/capabilities?library=' + library,
                headers=member_headers)).json()
            if capabilities['generation_enabled']:
                raise RuntimeError('Generated demo unexpectedly enabled a model')
        return {'profile': 'generated-no-listener', 'photos': 2, 'stories': 2,
            'reviewed_contributions': 2, 'ordered_memoir_created': True,
            'editorial_saved_and_reopened': True,
            'story_reference_removal_preserved_original': True,
            'removed_reference_withheld_stale_editorial': True,
            'changed_child_revision_withheld_old_prose': True,
            'anonymous_reads_denied': True, 'generation_enabled': False,
            'models_loaded': False, 'production_connections': False,
            'listening_socket': False, 'child_processes': False}


if __name__ == '__main__':
    # Real ASGI requests and SQLite, with accidental external I/O refused.
    with patch('socket.socket.bind', side_effect=RuntimeError('Listener refused')), \
         patch('socket.socket.connect', side_effect=RuntimeError('Network refused')), \
         patch('subprocess.Popen', side_effect=RuntimeError('Process refused')):
        print(json.dumps(check(), ensure_ascii=False, sort_keys=True))

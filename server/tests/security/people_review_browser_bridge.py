"""Synthetic browser-to-ASGI bridge for the owner visual-review journey."""
import base64
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from test_people_visual_review import VisualPeopleReviewTests
from app.access.runtime import RuntimeConfiguration
from app.access.discovery import ReadBudget
from app.access.discovery_transport import DiscoveryRuntime

fixture = VisualPeopleReviewTests('runTest')
VisualPeopleReviewTests.setUpClass()
try:
    fixture.setUp()
    root = fixture.f.path.parent
    originals, derived = root / 'originals', root / 'derived'
    (derived / 'thumbnails/256').mkdir(parents=True, exist_ok=True)
    (derived / 'faces/256').mkdir(parents=True, exist_ok=True)
    originals.mkdir(exist_ok=True)
    for asset_id, color in ((101, '#b6c7b0'), (102, '#d2ad89')):
        image = Image.new('RGB', (400, 300), color)
        draw = ImageDraw.Draw(image)
        draw.rectangle((24, 24, 376, 276), outline='#fff9ed', width=3)
        draw.text((130, 144), f'SYNTHETIC {asset_id}', fill='#302c28')
        image.save(originals / f'{asset_id}.jpg')
        image.save(derived / f'thumbnails/256/{asset_id}.jpg')
    for face_id, color in ((11, '#b6c7b0'), (12, '#d2ad89'), (13, '#8aa9c4'), (14, '#d7b1c4'), (15, '#c9bb90'), (16, '#aaa9c4'), (17, '#b8a2a3')):
        Image.new('RGB', (120, 120), color).save(derived / f'faces/256/{face_id}.jpg')
    with fixture.f.connection() as db:
        for asset_id in (101, 102):
            db.execute('UPDATE assets SET path=? WHERE id=?', (str(originals / f'{asset_id}.jpg'), asset_id))
        # A second editable library person gives the correction picker a real synthetic target.
        db.execute("INSERT INTO persons(id,display_name,face_count) VALUES(7,'Other sample',1)")
        db.execute("INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h,label_source) VALUES(15,102,7,0,0,1,1,'manual')")
        db.execute("INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h,label_source) VALUES(16,102,1,0,0,1,1,'manual')")
        db.execute("INSERT INTO face_detections(id,asset_id,person_id,bbox_x,bbox_y,bbox_w,bbox_h,label_source) VALUES(17,101,1,0,0,1,1,'manual')")
        db.commit()
    app = RuntimeConfiguration(fixture.f.path.resolve(), 'https://photohouse.test',
        (originals.resolve(),), derived.resolve()).build_app(clock=lambda: fixture.f.now)
    app.state.discovery_runtime = DiscoveryRuntime(app.state.access_runtime, fixture.provider, ReadBudget())
    from fastapi.testclient import TestClient
    client = TestClient(app, base_url='https://photohouse.test', client=('192.0.2.20', 23456))
    client.headers['Sec-Fetch-Site'] = 'same-origin'
    print(json.dumps({'ready': True}), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('command') == 'quit':
            break
        if message.get('command') == 'revoke':
            with fixture.f.connection() as db:
                db.execute('UPDATE access_sessions SET revoked=1')
                db.commit()
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        client.cookies.clear()
        response = client.request(message['method'], message['path'], headers=message.get('headers'),
                                  content=base64.b64decode(message.get('body', '')))
        print(json.dumps({'id': message['id'], 'status': response.status_code,
                          'headers': dict(response.headers),
                          'body': base64.b64encode(response.content).decode()}), flush=True)
    client.close()
finally:
    fixture.doCleanups()
    VisualPeopleReviewTests.tearDownClass()

"""Synthetic gallery fixture for the photo-stack browser contract."""
import base64
import json
import sys
from pathlib import Path

from test_library_reads import LibraryReadTests, OWNER, OTHER_OWNER, MEMBER, PASSWORD
from app.access.service import AccessService
from app.access.media import MediaRuntime
from PIL import Image, ImageDraw

fixture = LibraryReadTests()
LibraryReadTests.setUpClass()
fixture.setUp()

# Make two authorized libraries available to the same synthetic member. This is
# test-only fixture state; no real account or media is opened.
with fixture.connection() as db:
    service = AccessService(db, clock=lambda: fixture.now)
    invitation = service.invite(fixture.other_token, 'family-b', MEMBER)
    service.accept_invitation(fixture.member_token, invitation)
    db.execute("UPDATE assets SET taken_at='2026-04-05 12:00:00', perceptual_hash=? WHERE id=101", ('0' * 16,))
    db.execute("UPDATE assets SET taken_at='2026-04-05 12:04:00', perceptual_hash=? WHERE id=102", ('0' * 15 + 'f',))
    db.execute("""INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at,perceptual_hash)
        VALUES (100,'private-synthetic/100.jpg','private-hash-100','active','image/jpeg',640,480,
                '2026-04-05 12:03:00',?)""", ('0' * 15 + '7',))
    db.execute("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (100,'family-a')")
    db.execute("""INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,duration_sec,taken_at)
        VALUES (104,'private-synthetic/104.mp4','private-hash-104','active','video/mp4',640,360,12.0,'2026-04-06 12:00:00')""")
    db.execute("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (104,'family-a')")
    db.execute("""INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
        VALUES (106,'private-synthetic/106.jpg','private-hash-106','active','image/jpeg',640,480,'2026-04-04 12:00:00')""")
    db.execute("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (106,'family-a')")
    db.execute("""INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
        VALUES (202,'private-synthetic/202.jpg','private-hash-202','active','image/jpeg',640,480,'2026-04-07 12:00:00')""")
    db.execute("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (202,'family-b')")
    db.commit()

# One local generated preview exercises the normal cover/count card appearance.
# It contains no household media and is served through the existing authorized route.
media_root = Path(fixture.path.parent) / 'photo-stack-media'
derived_root = media_root / 'derived'
thumbnail_dir = derived_root / 'thumbnails' / '256'
thumbnail_dir.mkdir(parents=True)
media_root.mkdir(parents=True, exist_ok=True)
preview = Image.new('RGB', (480, 320), '#d2ad89')
ImageDraw.Draw(preview).rectangle((28, 28, 452, 292), outline='#fff9ed', width=5)
ImageDraw.Draw(preview).text((170, 150), 'SYNTHETIC 102', fill='#302c28')
preview.save(thumbnail_dir / '102.jpg', format='JPEG')
fixture.client.app.state.media_runtime = MediaRuntime((media_root,), derived_root)

print(json.dumps({'ready': True}), flush=True)
for line in sys.stdin:
    message = json.loads(line)
    if message.get('command') == 'quit':
        break
    request = message.get('request')
    if request:
        headers = request.get('headers') or {}
        headers.pop('content-length', None)
        body = base64.b64decode(request.get('body') or '')
        response = fixture.client.request(request['method'], request['path'], headers=headers,
                                          content=body if body else None)
        print(json.dumps({'id': message['id'], 'status': response.status_code,
                          'headers': dict(response.headers),
                          'body': base64.b64encode(response.content).decode('ascii')}), flush=True)
    else:
        print(json.dumps({'id': message['id'], 'ok': True}), flush=True)

fixture.doCleanups()
LibraryReadTests.tearDownClass()

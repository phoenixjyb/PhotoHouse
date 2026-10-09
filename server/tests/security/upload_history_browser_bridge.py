"""Synthetic browser -> real ASGI approval workflow; no network listener or real media."""
import base64
import io
import json
import sys
import tempfile
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
import test_promotion as promotion_module
from test_promotion import BATCH, PromotionTests
from test_access_foundation import NOW
from app.access.runtime import AccessRuntime, ExistingDatabase, RuntimeConfiguration
from app.access.original_deletions import OriginalDeletionJournal
import app.access.promotion as promotion_runtime
from app.photo_delivery import PhotoCache

fixture = PromotionTests()
PromotionTests.setUpClass()
deletion_journal_temp = None
try:
    fixture.setUp()
    image = Image.new('RGB', (640, 480), '#b6c7b0')
    buffer = io.BytesIO(); image.save(buffer, format='JPEG')
    upload = fixture.uploads.store(fixture.member_token, buffer.getvalue(),
                                  'synthetic.jpg', BATCH, 'family-a')
    uploads = [upload]
    for color in [f'#{v:02x}ad89' for v in range(30, 41)]:
        buffer = io.BytesIO(); Image.new('RGB', (640, 480), color).save(buffer, format='JPEG')
        upload = fixture.uploads.store(fixture.member_token,
            buffer.getvalue()+color.encode('ascii'), 'synthetic.jpg', BATCH, 'family-a')
        uploads.append(upload)
    # Put more than one gallery page of dated existing assets ahead of the upload receipt time.
    # Their real captured dates must continue to sort chronologically, while the approved upload
    # (which has taken_at NULL) should use its access_uploads.created_at fallback.
    dated = [(1000 + i, datetime.fromtimestamp(NOW - (i + 1) * 86400, timezone.utc).isoformat())
             for i in range(25)]
    with closing(fixture.connection()) as db:
        db.executemany('''INSERT INTO assets(id,path,hash_sha256,status,mime,width,height,taken_at)
            VALUES (?,?,?,'active','image/jpeg',640,480,?)''',
            [(asset_id, f'captured/{asset_id}.jpg', f'hash-{asset_id}', taken_at)
             for asset_id, taken_at in dated])
        db.executemany('INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (?,?)',
                       [(asset_id, 'family-a') for asset_id, _ in dated])
        db.commit()
    derived = fixture.root/'derived'
    (derived/'thumbnails/256').mkdir(parents=True)
    image.save(derived/'thumbnails/256/900.jpg')
    for item in uploads:
        image.save(derived/f"thumbnails/256/{item['asset_id']}.jpg")
    image.save(fixture.originals/'900.jpg')
    with closing(fixture.connection()) as db:
        db.execute('UPDATE assets SET path=? WHERE id=900', (str(fixture.originals/'900.jpg'),)); db.commit()
    # The generated browser fixture enables original-note intake, whose runtime
    # requires a deletion journal even though this UI journey does not erase notes.
    # Keep the journal beside the isolated temporary database with a test namespace.
    deletion_journal_temp=tempfile.TemporaryDirectory(prefix='upload-history-deletions-',
        dir=Path(tempfile.gettempdir()).resolve())
    journal=(Path(deletion_journal_temp.name).resolve()/'deletions.sqlite')
    namespace='d0000000-0000-4000-8000-000000000099'
    selected=OriginalDeletionJournal.initialize(journal,namespace)
    with closing(fixture.connection()) as db:selected.bind(db)
    # Promotion helpers open this same synthetic database outside the ASGI app.
    # Keep their connection factory on the same verified journal contract too.
    fixture.access=AccessRuntime(ExistingDatabase(fixture.path.resolve(),original_deletions=selected),
                                 fixture.access.web_origin,clock=fixture.access.clock)
    journaled_database=lambda path,**options: ExistingDatabase(path,original_deletions=selected,**options)
    promotion_module.ExistingDatabase=journaled_database
    promotion_runtime.ExistingDatabase=journaled_database
    client = TestClient(RuntimeConfiguration(fixture.path, 'https://photohouse.test',
        (fixture.originals,), fixture.root/'derived',
        incoming_root=fixture.incoming, upload_review_enabled=True,
        annotation_intake_enabled=True,
        original_deletion_journal_path=journal,original_deletion_namespace=namespace,
        # Resource admission is tested separately; this tiny synthetic image uses the real decoder.
        photo_cache=PhotoCache(fixture.root/'preview-cache', guard_factory=lambda _: lambda *a, **kw: None)).build_app(clock=fixture.access.clock),
        base_url='https://photohouse.test', client=('192.0.2.20', 23456))
    print(json.dumps(dict(ready=True, asset_id=upload['asset_id'],
                          other_asset_id=uploads[-2]['asset_id'])), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('command') == 'quit': break
        if message.get('command') == 'revoke':
            with closing(fixture.connection()) as db:
                db.execute('UPDATE access_sessions SET revoked=1'); db.commit()
            print(json.dumps(dict(id=message['id'], ok=True)), flush=True); continue
        if message.get('command') == 'approve':
            fixture.promote(int(upload['asset_id']))
            print(json.dumps(dict(id=message['id'], ok=True)), flush=True); continue
        client.cookies.clear()
        response = client.request(message['method'], message['path'], headers=message.get('headers'),
                                  content=base64.b64decode(message.get('body', '')))
        print(json.dumps(dict(id=message['id'], status=response.status_code,
            headers=dict(response.headers), body=base64.b64encode(response.content).decode())), flush=True)
    client.close()
finally:
    fixture.doCleanups()
    if deletion_journal_temp is not None:deletion_journal_temp.cleanup()
    PromotionTests.tearDownClass()

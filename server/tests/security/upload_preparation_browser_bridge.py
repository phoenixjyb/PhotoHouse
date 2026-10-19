"""Synthetic authenticated ASGI bridge for the own-upload preparation browser journeys."""
import base64
import json
import sys
from contextlib import closing

from test_upload import BATCH, UploadTests, png

fixture = UploadTests()
UploadTests.setUpClass()
try:
    fixture.setUp()
    first = fixture.upload(png(64, 64, b'first'))
    owner_receipt = fixture.upload(png(64, 64, b'owner-private'), token=fixture.owner_token)
    # Distinct receipt bytes provide a second real history page for late-page checks.
    for i in range(11):
        fixture.upload(png(64, 64, bytes([i + 1]) * (i + 1)), batch=BATCH)
    # Promote only generated records inside the isolated fixture so the v1
    # contract legitimately includes processing for available receipts.
    with closing(fixture.connection()) as db:
        ids=[row[0] for row in db.execute('SELECT asset_id FROM access_uploads').fetchall()]
        db.executemany("UPDATE assets SET status='active' WHERE id=?", [(asset_id,) for asset_id in ids])
        db.executemany("UPDATE access_uploads SET state='assigned' WHERE asset_id=?", [(asset_id,) for asset_id in ids])
        db.executemany("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (?,'family-a')", [(asset_id,) for asset_id in ids])
        db.commit()
    client = fixture.client()
    print(json.dumps({'ready': True, 'account_id': fixture.member_id,
                      'owner_asset_id': owner_receipt['asset_id'],
                      'asset_ids': [row[0] for row in fixture.rows(
                          'SELECT asset_id FROM access_uploads ORDER BY id DESC')]}), flush=True)
    for line in sys.stdin:
        message = json.loads(line)
        if message.get('command') == 'quit':
            break
        if message.get('command') == 'revoke-member':
            with closing(fixture.connection()) as db:
                db.execute("UPDATE access_memberships SET status='revoked' WHERE account_id=?", (fixture.member_id,))
                db.commit()
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        if message.get('command') == 'revoke':
            with closing(fixture.connection()) as db:
                db.execute('UPDATE access_sessions SET revoked=1')
                db.commit()
            print(json.dumps({'id': message['id'], 'ok': True}), flush=True)
            continue
        client.cookies.clear()
        response = client.request(message['method'], message['path'], headers=message.get('headers'),
                                  content=base64.b64decode(message.get('body', '')))
        print(json.dumps({'id': message['id'], 'status': response.status_code,
                          'headers': dict(response.headers),
                          'body': base64.b64encode(response.content).decode('ascii')}), flush=True)
finally:
    fixture.doCleanups()
    UploadTests.tearDownClass()

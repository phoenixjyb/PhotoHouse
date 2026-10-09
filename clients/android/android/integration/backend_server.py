"""Disposable real ASGI/SQLite TLS test server. Never a deployment entry point.

Invoked only by BackendIntegrationTest in a private temporary directory. Backend
source is an immutable, verified Git export. No caller-supplied database or media
path is accepted, and controls are finite synthetic scenarios over parent pipes.
"""
import argparse
from contextlib import ExitStack, closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import tempfile
import threading
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--certificate', type=Path, required=True)
    parser.add_argument('--key', type=Path, required=True)
    args = parser.parse_args()
    work = Path.cwd().resolve()
    if not (work / 'synthetic-test-only').is_file():
        raise RuntimeError('A private synthetic test directory is required')
    for path in (args.certificate, args.key):
        if path.resolve().parent != work:
            raise RuntimeError('Test TLS inputs must belong to the private test directory')
    tempfile.tempdir = str(work)
    sys.path[:0] = [str(args.source / 'backend'), str(args.source / 'tests/security')]
    from test_library_reads import LibraryReadTests
    from test_access_foundation import OWNER, OTHER_OWNER, MEMBER, NEW, PASSWORD, NOW
    from app.access.service import AccessService
    from app.access.runtime import RuntimeConfiguration
    from PIL import Image, ImageDraw
    import uvicorn

    with ExitStack() as cleanup:
        # Reuse the pinned backend's migrated synthetic template, not its setUp
        # (which intentionally prohibits sockets for its own ASGI-only tests).
        LibraryReadTests.setUpClass()
        cleanup.callback(LibraryReadTests.tearDownClass)
        db_path = work / 'synthetic.sqlite'
        with closing(sqlite3.connect(db_path)) as db:
            LibraryReadTests.template.backup(db)
        originals = work / 'originals'
        derived = work / 'derived'
        originals.mkdir()
        (derived / 'thumbnails/256').mkdir(parents=True)

        def connection():
            db = sqlite3.connect(db_path)
            db.execute('PRAGMA foreign_keys=ON')
            return db

        with closing(connection()) as db:
            for asset_id, color in ((101, '#b6c7b0'), (102, '#d2ad89'), (201, '#8aa9c4')):
                image = Image.new('RGB', (256, 192), color)
                ImageDraw.Draw(image).rectangle((20, 20, 236, 172), outline='white', width=3)
                image.save(derived / f'thumbnails/256/{asset_id}.jpg')
                image.save(originals / f'{asset_id}.jpg')
                db.execute('UPDATE assets SET path=? WHERE id=?', (str(originals / f'{asset_id}.jpg'), asset_id))
            db.execute('UPDATE captions SET text=? WHERE id=101', ('<b>Synthetic 原文</b>',))
            db.commit()

        clock = [NOW]
        listener = cleanup.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        app = RuntimeConfiguration(db_path, f'https://localhost:{port}', (originals,), derived).build_app(clock=lambda: clock[0])
        server = uvicorn.Server(uvicorn.Config(
            app, host='127.0.0.1', port=port, ssl_certfile=str(args.certificate),
            ssl_keyfile=str(args.key), proxy_headers=False, access_log=False,
            log_level='critical', lifespan='off', loop='asyncio', http='h11',
            timeout_keep_alive=1,
        ))
        # The only listener was explicitly created above. The app cannot start
        # providers/processes or make outbound connections during this test.
        for target in ('socket.socket.bind', 'socket.socket.connect', 'socket.socket.connect_ex',
                       'socket.create_connection', 'subprocess.Popen', 'os.system'):
            cleanup.enter_context(patch(target, side_effect=AssertionError('External test I/O forbidden')))
        thread = threading.Thread(target=server.run, kwargs={'sockets': [listener]}, daemon=True)
        thread.start()

        def stop():
            server.should_exit = True
            thread.join(timeout=5)

        cleanup.callback(stop)
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() >= deadline:
                raise RuntimeError('Synthetic TLS startup failed')
            time.sleep(0.01)
        print(json.dumps({'ready': True, 'port': port}), flush=True)
        for line in sys.stdin:
            if len(line) > 256:
                raise ValueError('Oversized test control')
            command = json.loads(line)['command']
            if command == 'quit':
                break
            result = {'ok': True}
            if command == 'remove-thumbnail':
                (derived / 'thumbnails/256/101.jpg').unlink()
            elif command == 'use-synthetic-video':
                video = Path(__file__).resolve().parents[1] / 'connected/src/androidTest/assets/synthetic-video.mp4'
                import shutil
                shutil.copyfile(video, originals / '102.mp4')
                with closing(connection()) as db:
                    db.execute('UPDATE assets SET path=?, mime=?, width=320, height=180, duration_sec=20 WHERE id=102', (str(originals / '102.mp4'), 'video/mp4'))
                    db.commit()
            elif command == 'storage-unavailable':
                db_path.rename(work / 'unavailable.sqlite')
            elif command == 'advance-admission-window':
                clock[0] += 601
            else:
                with closing(connection()) as db:
                    service = AccessService(db, clock=lambda: clock[0])
                    if command == 'invite-new':
                        result['code'] = service.invite(LibraryReadTests.owner_token, 'family-a', NEW)
                    elif command == 'invite-second-library':
                        result['code'] = service.invite(LibraryReadTests.other_token, 'family-b', NEW)
                    elif command == 'revoke-member':
                        service.decide_membership(LibraryReadTests.owner_token, 'family-a', LibraryReadTests.member_id,
                            expected_revision=service.profile(LibraryReadTests.member_token)['memberships'][0]['revision'], status='revoked')
                    elif command in {'allow-originals', 'deny-originals'}:
                        service.decide_membership(LibraryReadTests.owner_token, 'family-a', LibraryReadTests.member_id,
                            expected_revision=service.profile(LibraryReadTests.member_token)['memberships'][0]['revision'],
                            status='approved', originals=command == 'allow-originals')
                    elif command == 'expire-sessions':
                        db.execute('UPDATE access_sessions SET expires_at=0')
                        db.commit()
                    else:
                        raise ValueError('Unknown synthetic control')
            # Dynamically issued invitation codes travel only through private
            # parent pipes. Tests never put them in URLs, logs or result files.
            print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()

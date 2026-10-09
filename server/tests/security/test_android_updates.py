"""Public update delivery stays opt-in and serves only verified app binaries."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
from app.main import create_app
from publish_android_update import LOCK_NAME, PublicationBusy, publish


class UpdateDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.apk = b'synthetic signed APK placeholder'
        self.sha = hashlib.sha256(self.apk).hexdigest()
        (self.root / f'{self.sha}.apk').write_bytes(self.apk)
        self.manifest = {'schema_version': 1, 'channel': 'phone',
                         'package_name': 'dev.photohouse.connected', 'version_code': 26,
                         'version_name': '0.27-ota', 'bytes': len(self.apk),
                         'sha256': self.sha, 'signing_cert_sha256': 'a' * 64}
        (self.root / 'phone.json').write_text(json.dumps(self.manifest))

    def test_closed_by_default_and_no_path_selection(self):
        with TestClient(create_app()) as client:
            self.assertEqual(client.get('/updates/v1/phone').status_code, 503)
            self.assertEqual(client.get(f'/updates/v1/phone/{self.sha}.apk').status_code, 503)
            for path in ('/updates/v1/phone/../../secret', '/updates/v1/qa',
                         '/updates/v1/tv/../../secret', '/updates/v1/phone/secret.apk'):
                self.assertIn(client.get(path).status_code, (403, 404))

    def test_only_current_digest_is_served_and_tampering_fails_closed(self):
        with TestClient(create_app(update_root=self.root)) as client:
            feed = client.get('/updates/v1/phone')
            self.assertEqual(feed.status_code, 200)
            self.assertEqual(feed.json(), {**self.manifest,
                'apk_url': f'/updates/v1/phone/{self.sha}.apk'})
            self.assertEqual(feed.headers['cache-control'], 'no-store')
            response = client.get(feed.json()['apk_url'])
            self.assertEqual(response.content, self.apk)
            self.assertEqual(response.headers['content-type'], 'application/vnd.android.package-archive')
            self.assertEqual(client.get(f'/updates/v1/phone/{"0" * 64}.apk').status_code, 503)
            self.assertEqual(client.get('/updates/v1/tv').status_code, 503)
            (self.root / f'{self.sha}.apk').write_bytes(b'changed')
            self.assertEqual(client.get('/updates/v1/phone').status_code, 503)
            self.assertEqual(client.get(feed.json()['apk_url']).status_code, 503)

    def test_manifest_cannot_switch_package_or_point_at_another_file(self):
        with TestClient(create_app(update_root=self.root)) as client:
            for field, value in [('package_name', 'dev.photohouse.connected.qa'),
                                 ('sha256', '../' + self.sha), ('bytes', len(self.apk) + 1)]:
                broken = dict(self.manifest, **{field: value})
                (self.root / 'phone.json').write_text(json.dumps(broken))
                self.assertEqual(client.get('/updates/v1/phone').status_code, 503)
            (self.root / 'phone.json').write_text('{"channel":"phone","channel":"tv"}')
            self.assertEqual(client.get('/updates/v1/phone').status_code, 503)
            (self.root / 'phone.json').write_text(json.dumps(dict(self.manifest, schema_version=True)))
            self.assertEqual(client.get('/updates/v1/phone').status_code, 503)


class PublicationTests(unittest.TestCase):
    def test_first_publish_then_higher_version_same_signer_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / 'updates'; root.mkdir()
            apk = base / 'signed.apk'; apk.write_bytes(b'synthetic-package')
            cert = 'a' * 64
            with patch('publish_android_update.inspect_apk', return_value=('dev.photohouse.tv', 22, '0.22', cert)):
                first = publish(root, apk, 'tv', cert, Path('/aapt'), Path('/apksigner'))
            pointer = (root / 'tv.json').read_bytes()
            self.assertEqual(first['sha256'], hashlib.sha256(apk.read_bytes()).hexdigest())
            for metadata in [('dev.photohouse.tv', 22, '0.22', cert),
                             ('dev.photohouse.tv', 23, '0.23', 'b' * 64),
                             ('dev.photohouse.connected', 23, '0.23', cert)]:
                with self.subTest(metadata=metadata), patch('publish_android_update.inspect_apk', return_value=metadata):
                    with self.assertRaises(ValueError):
                        publish(root, apk, 'tv', cert, Path('/aapt'), Path('/apksigner'))
                    self.assertEqual((root / 'tv.json').read_bytes(), pointer)
            with patch('publish_android_update.inspect_apk', return_value=('dev.photohouse.tv', 23, '0.23', cert)):
                self.assertEqual(publish(root, apk, 'tv', cert, Path('/aapt'), Path('/apksigner'))['version_code'], 23)

    def test_first_phone_publish_can_pin_both_pointers_absent_and_never_touches_tv(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / 'updates'; root.mkdir()
            apk = base / 'phone.apk'; apk.write_bytes(b'phone-v1')
            cert = 'a' * 64
            with patch('publish_android_update.inspect_apk', return_value=('dev.photohouse.connected', 1, '1.0', cert)):
                result = publish(
                    root, apk, 'phone', cert, Path('/aapt'), Path('/apksigner'),
                    expected_current_pointer_sha256=None,
                    expected_other_pointer_sha256=None,
                )
            self.assertEqual('phone', result['channel'])
            self.assertTrue((root / 'phone.json').is_file())
            self.assertFalse((root / 'tv.json').exists())
            self.assertFalse((root / LOCK_NAME).exists())

    def test_expected_pointer_digests_gate_writes_and_preserve_other_channel(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve()
            root = base / 'updates'; root.mkdir()
            apk = base / 'phone.apk'; apk.write_bytes(b'phone-v27')
            cert = 'a' * 64
            phone_pointer = root / 'phone.json'
            tv_pointer = root / 'tv.json'
            old_phone = json.dumps({'channel': 'phone', 'package_name': 'dev.photohouse.connected',
                                    'version_code': 26, 'signing_cert_sha256': cert}).encode()
            old_tv = b'{"channel":"tv","version_code":22}\n'
            phone_pointer.write_bytes(old_phone); tv_pointer.write_bytes(old_tv)
            phone_before = hashlib.sha256(old_phone).hexdigest()
            tv_before = hashlib.sha256(old_tv).hexdigest()
            with patch('publish_android_update.inspect_apk', return_value=('dev.photohouse.connected', 27, '0.27', cert)):
                result = publish(
                    root, apk, 'phone', cert, Path('/aapt'), Path('/apksigner'),
                    expected_current_pointer_sha256=phone_before,
                    expected_other_pointer_sha256=tv_before,
                )
            self.assertEqual(27, result['version_code'])
            self.assertEqual(old_tv, tv_pointer.read_bytes())

            stable_phone = phone_pointer.read_bytes()
            other_apk = base / 'another.apk'; other_apk.write_bytes(b'phone-v28')
            with patch('publish_android_update.inspect_apk', return_value=('dev.photohouse.connected', 28, '0.28', cert)):
                with self.assertRaisesRegex(ValueError, 'expected snapshot'):
                    publish(
                        root, other_apk, 'phone', cert, Path('/aapt'), Path('/apksigner'),
                        expected_current_pointer_sha256=phone_before,
                        expected_other_pointer_sha256=tv_before,
                    )
            self.assertEqual(stable_phone, phone_pointer.read_bytes())
            self.assertFalse((root / f'{hashlib.sha256(other_apk.read_bytes()).hexdigest()}.apk').exists())

    def test_wrong_expected_other_pointer_refuses_before_copy(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(); root = base / 'updates'; root.mkdir()
            apk = base / 'phone.apk'; apk.write_bytes(b'phone-v1')
            (root / 'tv.json').write_bytes(b'{"channel":"tv"}')
            cert = 'a' * 64
            with patch('publish_android_update.inspect_apk', return_value=('dev.photohouse.connected', 1, '1.0', cert)):
                with self.assertRaisesRegex(ValueError, 'Other channel pointer changed'):
                    publish(root, apk, 'phone', cert, Path('/aapt'), Path('/apksigner'),
                            expected_other_pointer_sha256='0' * 64)
            self.assertFalse((root / 'phone.json').exists())
            self.assertFalse((root / f'{hashlib.sha256(apk.read_bytes()).hexdigest()}.apk').exists())

    def test_pointer_drift_during_attempt_is_not_overwritten(self):
        for drift_channel in ('phone', 'tv'):
            with self.subTest(drift_channel=drift_channel), tempfile.TemporaryDirectory() as temporary:
                base = Path(temporary).resolve(); root = base / 'updates'; root.mkdir()
                apk = base / 'phone.apk'; apk.write_bytes(b'phone-v28')
                cert = 'a' * 64
                phone_pointer = root / 'phone.json'; tv_pointer = root / 'tv.json'
                old_phone = json.dumps({'channel': 'phone', 'package_name': 'dev.photohouse.connected',
                                        'version_code': 26, 'signing_cert_sha256': cert}).encode()
                old_tv = b'{"channel":"tv","version_code":22}\n'
                phone_pointer.write_bytes(old_phone); tv_pointer.write_bytes(old_tv)
                raced = b'{"channel":"' + drift_channel.encode() + b'","external":"newer"}'

                def mutate_pointer(*_):
                    (phone_pointer if drift_channel == 'phone' else tv_pointer).write_bytes(raced)
                    return 'dev.photohouse.connected', 28, '0.28', cert

                with patch('publish_android_update.inspect_apk', side_effect=mutate_pointer):
                    with self.assertRaisesRegex(ValueError, 'changed during publication'):
                        publish(root, apk, 'phone', cert, Path('/aapt'), Path('/apksigner'))
                self.assertEqual(raced if drift_channel == 'phone' else old_phone, phone_pointer.read_bytes())
                self.assertEqual(raced if drift_channel == 'tv' else old_tv, tv_pointer.read_bytes())
                self.assertFalse(any(root.glob('.phone-*.json')))
                self.assertFalse((root / LOCK_NAME).exists())

    def test_existing_foreign_or_stale_lock_is_never_removed(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(); root = base / 'updates'; root.mkdir()
            apk = base / 'phone.apk'; apk.write_bytes(b'phone-v1')
            lock = root / LOCK_NAME; lock.write_bytes(b'foreign lock marker')
            cert = 'a' * 64
            with patch('publish_android_update.LOCK_WAIT_SECONDS', 0):
                with patch('publish_android_update.inspect_apk') as inspect:
                    with self.assertRaises(PublicationBusy):
                        publish(root, apk, 'phone', cert, Path('/aapt'), Path('/apksigner'))
            inspect.assert_not_called()
            self.assertEqual(b'foreign lock marker', lock.read_bytes())
            self.assertFalse((root / 'phone.json').exists())

    def test_shared_lock_serializes_competing_phone_and_tv_publishers(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(); root = base / 'updates'; root.mkdir()
            phone_apk = base / 'phone.apk'; phone_apk.write_bytes(b'phone-v1')
            tv_apk = base / 'tv.apk'; tv_apk.write_bytes(b'tv-v1')
            cert = 'a' * 64
            phone_entered = threading.Event(); release_phone = threading.Event()
            tv_entered = threading.Event(); active_lock = threading.Lock()
            active = 0; overlapped = []
            results = []; errors = []

            def inspect(apk, *_):
                nonlocal active
                with active_lock:
                    active += 1
                    if active > 1: overlapped.append(True)
                try:
                    if apk == phone_apk:
                        phone_entered.set()
                        if not release_phone.wait(2): raise AssertionError('test release timed out')
                        return 'dev.photohouse.connected', 1, '1.0', cert
                    tv_entered.set()
                    return 'dev.photohouse.tv', 1, '1.0', cert
                finally:
                    with active_lock: active -= 1

            def run(apk, channel):
                try:
                    results.append(publish(root, apk, channel, cert, Path('/aapt'), Path('/apksigner')))
                except BaseException as exc:
                    errors.append(exc)

            with patch('publish_android_update.inspect_apk', side_effect=inspect):
                first = threading.Thread(target=run, args=(phone_apk, 'phone'))
                second = threading.Thread(target=run, args=(tv_apk, 'tv'))
                first.start()
                try:
                    self.assertTrue(phone_entered.wait(1))
                    second.start()
                    self.assertFalse(tv_entered.wait(0.05))
                finally:
                    release_phone.set()
                    first.join(2)
                    if second.ident is not None:
                        second.join(2)
            self.assertFalse(first.is_alive()); self.assertFalse(second.is_alive())
            self.assertEqual([], errors)
            self.assertEqual(2, len(results))
            self.assertFalse(overlapped)
            self.assertTrue((root / 'phone.json').is_file())
            self.assertTrue((root / 'tv.json').is_file())
            self.assertFalse((root / LOCK_NAME).exists())

    def test_exception_releases_owned_lock_and_stale_rollback_snapshot_refuses(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary).resolve(); root = base / 'updates'; root.mkdir()
            apk = base / 'phone.apk'; apk.write_bytes(b'phone-v27')
            cert = 'a' * 64
            pointer = root / 'phone.json'
            previous = json.dumps({'channel': 'phone', 'package_name': 'dev.photohouse.connected',
                                   'version_code': 26, 'signing_cert_sha256': cert}).encode()
            pointer.write_bytes(previous)
            previous_digest = hashlib.sha256(previous).hexdigest()
            with patch('publish_android_update.inspect_apk', side_effect=RuntimeError('synthetic inspect failure')):
                with self.assertRaisesRegex(RuntimeError, 'synthetic inspect failure'):
                    publish(root, apk, 'phone', cert, Path('/aapt'), Path('/apksigner'))
            self.assertEqual(previous, pointer.read_bytes())
            self.assertFalse((root / LOCK_NAME).exists())

            with patch('publish_android_update.inspect_apk', return_value=('dev.photohouse.connected', 27, '0.27', cert)):
                publish(root, apk, 'phone', cert, Path('/aapt'), Path('/apksigner'),
                        expected_current_pointer_sha256=previous_digest)
            current = pointer.read_bytes()
            rollback_apk = base / 'rollback.apk'; rollback_apk.write_bytes(b'phone-v26')
            with patch('publish_android_update.inspect_apk', return_value=('dev.photohouse.connected', 26, '0.26', cert)):
                with self.assertRaisesRegex(ValueError, 'expected snapshot'):
                    publish(root, rollback_apk, 'phone', cert, Path('/aapt'), Path('/apksigner'),
                            expected_current_pointer_sha256=previous_digest)
            self.assertEqual(current, pointer.read_bytes())
            with patch('publish_android_update.inspect_apk', return_value=('dev.photohouse.connected', 26, '0.26', cert)):
                with self.assertRaisesRegex(ValueError, 'increase version code'):
                    publish(root, rollback_apk, 'phone', cert, Path('/aapt'), Path('/apksigner'),
                            expected_current_pointer_sha256=hashlib.sha256(current).hexdigest())
            self.assertEqual(current, pointer.read_bytes())
            self.assertFalse((root / f'{hashlib.sha256(rollback_apk.read_bytes()).hexdigest()}.apk').exists())


if __name__ == '__main__':
    unittest.main()

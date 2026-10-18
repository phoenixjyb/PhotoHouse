"""Keep the upload ASGI fixture compatible with CPython's TCP socketpair fallback."""
import os
import socket
import subprocess
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'tests/security'))
import test_network_guard


def _tcp_socketpair(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0):
    """Equivalent of CPython's fallback when that private helper is unavailable."""
    host = '::1' if family == socket.AF_INET6 else '127.0.0.1'
    with socket.socket(family, type, proto) as listener:
        listener.bind((host, 0))
        listener.listen(1)
        writer = socket.socket(family, type, proto)
        try:
            writer.connect(listener.getsockname()[:2])
            reader, _ = listener.accept()
            return reader, writer
        except BaseException:
            writer.close()
            raise


class UploadSocketpairGuardTests(unittest.TestCase):
    def test_testclient_works_with_stdlib_fallback_and_external_io_stays_denied(self):
        fallback = getattr(socket, '_fallback_socketpair', _tcp_socketpair)
        calls = []

        def forced_fallback(*args, **kwargs):
            calls.append(True)
            return fallback(*args, **kwargs)

        # Import locally so unittest discovery does not collect UploadTests a second time.
        import test_upload

        fixture = test_upload.UploadTests(
            'test_route_accepts_an_upload_that_stays_out_of_every_library')
        test_upload.UploadTests.setUpClass()
        try:
            with patch.object(test_network_guard, '_PAIR', forced_fallback):
                fixture.setUp()
                try:
                    fixture.test_route_accepts_an_upload_that_stays_out_of_every_library()
                    self.assertGreater(len(calls), 0, 'the forced stdlib fallback was not exercised')

                    with socket.socket() as connection:
                        for address in (('127.0.0.1', 0), ('127.0.0.1', 8002), ('192.0.2.1', 80)):
                            with self.subTest(operation='bind', address=address):
                                with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                                    connection.bind(address)
                            with self.subTest(operation='connect', address=address):
                                with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                                    connection.connect(address)

                    with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                        subprocess.Popen(['not-executed'])
                    with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                        os.system('not-executed')
                finally:
                    fixture.doCleanups()
        finally:
            test_upload.UploadTests.tearDownClass()


if __name__ == '__main__':
    unittest.main()

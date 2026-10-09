"""Portable regression for Windows TCP socketpair under fixture network mocks."""
import socket
import threading
import unittest

from test_network_guard import no_external_sockets


def tcp_pair(family=socket.AF_INET):
    """Exercise the same ephemeral bind/connect used by Windows stdlib."""
    host = '::1' if family == socket.AF_INET6 else '127.0.0.1'
    with socket.socket(family) as listener:
        listener.bind((host, 0))
        listener.listen(1)
        writer = socket.socket(family)
        try:
            writer.connect(listener.getsockname()[:2])
            reader, _ = listener.accept()
            return reader, writer
        except BaseException:
            writer.close()
            raise


class FixtureNetworkGuardTests(unittest.TestCase):
    def test_ipv6_pair_uses_the_same_endpoint_without_scope_or_flow_fields(self):
        with no_external_sockets(pair_factory=tcp_pair):
            reader, writer = socket.socketpair(socket.AF_INET6)
            with reader, writer:
                writer.sendall(b'v6')
                self.assertEqual(reader.recv(2), b'v6')

    def test_internal_tcp_pair_roundtrip_while_normal_network_is_denied(self):
        with no_external_sockets(pair_factory=tcp_pair):
            reader, writer = socket.socketpair()
            with reader, writer:
                writer.sendall(b'wakeup')
                self.assertEqual(reader.recv(6), b'wakeup')
            with socket.socket() as connection:
                for method in (connection.bind, connection.connect):
                    for address in [('127.0.0.1', 0), ('127.0.0.1', 8002), ('192.0.2.1', 80)]:
                        with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                            method(address)

    def test_pair_may_not_connect_to_a_different_loopback_endpoint(self):
        def invalid_pair():
            with socket.socket() as listener, socket.socket() as peer:
                listener.bind(('127.0.0.1', 0))
                with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                    peer.connect(('127.0.0.1', 8002))
                with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                    peer.bind(('127.0.0.1', 0))
        with no_external_sockets(pair_factory=invalid_pair):
            socket.socketpair()

    def test_pair_exception_restores_normal_denial(self):
        def broken_pair():
            raise ValueError('synthetic pair failure')
        with no_external_sockets(pair_factory=broken_pair):
            with self.assertRaises(ValueError):
                socket.socketpair()
            with socket.socket() as connection:
                with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                    connection.bind(('127.0.0.1', 0))

    def test_other_thread_cannot_use_active_pair_allowance(self):
        denied = []
        def other_thread():
            with socket.socket() as connection:
                try:
                    connection.bind(('127.0.0.1', 0))
                except AssertionError:
                    denied.append(True)
        def pair():
            thread = threading.Thread(target=other_thread)
            thread.start(); thread.join()
        with no_external_sockets(pair_factory=pair):
            socket.socketpair()
        self.assertEqual(denied, [True])

    def test_nested_guards_restore_the_outer_guard_and_original_methods(self):
        original = (socket.socket.bind, socket.socket.connect, socket.socketpair)
        with no_external_sockets(pair_factory=tcp_pair):
            outer = socket.socket.bind
            with no_external_sockets(pair_factory=tcp_pair):
                reader, writer = socket.socketpair()
                reader.close(); writer.close()
            self.assertIs(socket.socket.bind, outer)
            with socket.socket() as connection:
                with self.assertRaisesRegex(AssertionError, 'External I/O forbidden'):
                    connection.bind(('127.0.0.1', 0))
        self.assertEqual((socket.socket.bind, socket.socket.connect, socket.socketpair), original)


if __name__ == '__main__':
    unittest.main()

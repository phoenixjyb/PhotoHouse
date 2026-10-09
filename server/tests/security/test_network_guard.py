"""Fixture guard permitting only stdlib's internal socketpair wakeup channel."""
from contextlib import contextmanager
import socket
import threading
from unittest.mock import patch


_BIND = socket.socket.bind
_CONNECT = socket.socket.connect
_PAIR = socket.socketpair


@contextmanager
def no_external_sockets(*, pair_factory=None):
    """Keep network mocks strict without breaking Windows asyncio.

    Only the creating thread may bind one ephemeral loopback listener and
    connect another socket to that exact listener while stdlib socketpair runs.
    Ordinary loopback, remote endpoints and other threads remain forbidden.
    The rehearsal's separate Python audit hook still checks real socket calls.
    """
    state = threading.local()

    def bind(connection, address):
        if (not getattr(state, 'active', False)
                or getattr(state, 'listener', None) is not None
                or not isinstance(address, tuple) or len(address) < 2
                or address[0] not in ('127.0.0.1', '::1') or address[1] != 0):
            raise AssertionError('External I/O forbidden')
        state.listener = connection
        return _BIND(connection, address)

    def connect(connection, address):
        listener = getattr(state, 'listener', None)
        if (not getattr(state, 'active', False) or listener is None
                or not isinstance(address, tuple) or len(address) < 2
                or address[:2] != listener.getsockname()[:2]
                or any(address[2:])):
            raise AssertionError('External I/O forbidden')
        return _CONNECT(connection, address)

    def pair(*args, **kwargs):
        previous = (getattr(state, 'active', False), getattr(state, 'listener', None))
        state.active, state.listener = True, None
        try:
            return (pair_factory or _PAIR)(*args, **kwargs)
        finally:
            state.active, state.listener = previous

    with patch.object(socket.socket, 'bind', bind), \
            patch.object(socket.socket, 'connect', connect), \
            patch.object(socket, 'socketpair', pair):
        yield


def install_no_external_sockets(test_case):
    guard = no_external_sockets()
    guard.__enter__()
    test_case.addCleanup(guard.__exit__, None, None, None)

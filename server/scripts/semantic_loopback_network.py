"""Explicit private loopback HTTP/TLS helpers for offline qualification.

Importing this module does not import Uvicorn/HTTPX, open files, create sockets,
or start listeners. Network resources are created only by explicit calls.
"""
from contextlib import contextmanager
import math
import os
from pathlib import Path
import socket
import ssl
import threading
import time
from urllib.parse import urlsplit


class LoopbackUnavailable(RuntimeError):
    """Fixed refusal for an invalid or unavailable temporary loopback boundary."""

    def __init__(self):
        super().__init__("semantic_loopback_unavailable")


_START_POLL_SECONDS = 0.01
_STOP_JOIN_SECONDS = 1.0
_FORCE_JOIN_SECONDS = 1.0
_MAX_SERVER_TIMEOUT_SECONDS = 30.0


def _refuse():
    raise LoopbackUnavailable() from None


def _private_absolute_file(value):
    if not isinstance(value, (str, os.PathLike)):
        _refuse()
    try:
        path = Path(value)
        if not path.is_absolute() or ".." in path.parts:
            _refuse()
        from app.access.private_storage import require_private_file
        require_private_file(path)
    except LoopbackUnavailable:
        raise
    except Exception:
        _refuse()
    return path


def _validate_socket(sock):
    try:
        if (sock is None or sock.family != socket.AF_INET
                or sock.type & socket.SOCK_STREAM != socket.SOCK_STREAM
                or sock.fileno() < 0):
            _refuse()
        address = sock.getsockname()
        if (not isinstance(address, tuple) or len(address) < 2
                or address[0] != "127.0.0.1" or type(address[1]) is not int
                or not 1024 <= address[1] <= 65535
                or any(address[2:])):
            _refuse()
        if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1:
            _refuse()
        return address[1]
    except LoopbackUnavailable:
        raise
    except Exception:
        _refuse()


def reserve_socket():
    """Return an owned, listening IPv4 socket bound only to 127.0.0.1:ephemeral."""
    sock = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(8)
        _validate_socket(sock)
        return sock
    except LoopbackUnavailable:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        raise
    except Exception:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        _refuse()


@contextmanager
def server(app, sock, certificate=None, private_key=None, timeout_seconds=5):
    """Serve one ASGI app on an owned prebound loopback socket.

    TLS is configured only when both certificate and private key are supplied;
    both files must be private absolute paths. The socket is always closed here,
    including validation/startup failures.
    """
    server_obj = None
    thread = None
    thread_errors = []
    body_error = None
    cleanup_error = False
    owned_socket = sock
    try:
        if not callable(app):
            _refuse()
        if (type(timeout_seconds) not in (int, float)
                or not math.isfinite(float(timeout_seconds))
                or not 0 < float(timeout_seconds) <= _MAX_SERVER_TIMEOUT_SECONDS):
            _refuse()
        port = _validate_socket(sock)
        if (certificate is None) != (private_key is None):
            _refuse()
        tls_options = {}
        if certificate is not None:
            certificate_path = _private_absolute_file(certificate)
            key_path = _private_absolute_file(private_key)
            tls_options = {"ssl_certfile": str(certificate_path),
                           "ssl_keyfile": str(key_path),
                           "ssl_version": ssl.PROTOCOL_TLS_SERVER}

        import uvicorn

        config = uvicorn.Config(app, host="127.0.0.1", port=port, workers=1,
            access_log=False, log_config=None, proxy_headers=False,
            forwarded_allow_ips="", timeout_keep_alive=1,
            timeout_graceful_shutdown=1, limit_concurrency=8, backlog=8,
            h11_max_incomplete_event_size=8192, **tls_options)
        server_obj = uvicorn.Server(config)

        def run_server():
            try:
                server_obj.run(sockets=[sock])
            except BaseException:
                thread_errors.append(True)

        thread = threading.Thread(target=run_server,
            name="semantic-loopback-uvicorn", daemon=True)
        thread.start()
        deadline = time.monotonic() + float(timeout_seconds)
        while True:
            if thread_errors or not thread.is_alive():
                _refuse()
            if getattr(server_obj, "started", False):
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                _refuse()
            time.sleep(min(_START_POLL_SECONDS, remaining))
        yield server_obj
    except BaseException as error:
        body_error = error
        raise
    finally:
        try:
            if server_obj is not None and thread is not None:
                try:
                    server_obj.should_exit = True
                    thread.join(_STOP_JOIN_SECONDS)
                    if thread.is_alive():
                        server_obj.force_exit = True
                        thread.join(_FORCE_JOIN_SECONDS)
                    if thread.is_alive() or thread_errors:
                        cleanup_error = True
                except Exception:
                    cleanup_error = True
        finally:
            if owned_socket is not None:
                try:
                    owned_socket.close()
                except Exception:
                    cleanup_error = True
        if cleanup_error and body_error is None:
            _refuse()


def _origin(value):
    if type(value) is not str:
        _refuse()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError):
        _refuse()
    if (parsed.scheme not in ("http", "https")
            or parsed.hostname != "127.0.0.1" or port is None
            or not 1024 <= port <= 65535 or parsed.username is not None
            or parsed.password is not None or parsed.path or parsed.query
            or parsed.fragment or parsed.netloc != f"127.0.0.1:{port}"):
        _refuse()
    return parsed.scheme


@contextmanager
def http_client(origin, ca_file=None):
    """Yield an actual bounded HTTPX client to an exact loopback origin."""
    scheme = _origin(origin)
    if scheme == "http" and ca_file is not None:
        _refuse()
    if scheme == "https" and ca_file is None:
        _refuse()
    verify = None
    if scheme == "https":
        ca_path = _private_absolute_file(ca_file)
        try:
            verify = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            verify.load_verify_locations(cafile=str(ca_path))
            verify.check_hostname = True
            verify.verify_mode = ssl.CERT_REQUIRED
            verify.minimum_version = ssl.TLSVersion.TLSv1_2
        except Exception:
            _refuse()
    import httpx

    options = {"base_url": origin, "trust_env": False,
               "follow_redirects": False, "timeout": 2.0}
    if verify is not None:
        options["verify"] = verify
    try:
        client = httpx.Client(**options)
    except Exception:
        _refuse()
    try:
        yield client
    finally:
        try:
            client.close()
        except Exception:
            _refuse()

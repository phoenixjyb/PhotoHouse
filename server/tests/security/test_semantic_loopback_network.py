"""No-network contract tests for the explicit semantic loopback helper."""
from pathlib import Path
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "scripts"), str(ROOT / "backend")]
import semantic_loopback_network as loopback


class FakeSocket:
    family = socket.AF_INET
    type = socket.SOCK_STREAM

    def __init__(self, address=("127.0.0.1", 49152), *, listening=True):
        self.address = address
        self.listening = listening
        self.closed = False
        self.bind_args = None
        self.listen_args = None

    def bind(self, address):
        self.bind_args = address
        self.address = (address[0], 49152)

    def listen(self, backlog):
        self.listen_args = backlog

    def getsockname(self):
        return self.address

    def getsockopt(self, level, option):
        assert (level, option) == (socket.SOL_SOCKET, socket.SO_ACCEPTCONN)
        return int(self.listening)

    def fileno(self):
        return -1 if self.closed else 42

    def close(self):
        self.closed = True


class FakeUvicorn:
    def __init__(self, behavior="ready"):
        self.behavior = behavior
        self.configs = []
        self.servers = []

    def Config(self, app, **options):
        config = SimpleNamespace(app=app, options=options)
        self.configs.append(config)
        return config

    def Server(self, config):
        server = FakeServer(config, self.behavior)
        self.servers.append(server)
        return server


class FakeServer:
    def __init__(self, config, behavior):
        self.config = config
        self.behavior = behavior
        self.started = False
        self.should_exit = False
        self.force_exit = False
        self.release = threading.Event()
        self.runner = None

    def run(self, *, sockets):
        self.runner = threading.current_thread()
        self.sockets = tuple(sockets)
        assert len(sockets) == 1
        if self.behavior == "raises":
            raise RuntimeError("synthetic startup error")
        if self.behavior == "timeout":
            while not self.should_exit:
                self.release.wait(0.001)
            return
        self.started = True
        if self.behavior == "stuck":
            self.release.wait()
            return
        while not (self.should_exit or self.force_exit):
            self.release.wait(0.001)


def install_uvicorn(monkeypatch, behavior="ready"):
    fake = FakeUvicorn(behavior)
    monkeypatch.setitem(sys.modules, "uvicorn", fake)
    return fake


def private_file(path):
    path.write_bytes(b"private fixture")
    path.chmod(0o600)
    return path


def test_reserve_socket_uses_only_ephemeral_ipv4_loopback_and_closes_on_failure(monkeypatch):
    made = []

    def factory(family, kind):
        assert (family, kind) == (socket.AF_INET, socket.SOCK_STREAM)
        result = FakeSocket()
        made.append(result)
        return result

    monkeypatch.setattr(loopback.socket, "socket", factory)
    result = loopback.reserve_socket()
    assert result is made[0]
    assert result.bind_args == ("127.0.0.1", 0)
    assert result.listen_args == 8
    assert not result.closed
    result.close()

    made.clear()
    def bad_factory(_family, _kind):
        result = FakeSocket(listening=False)
        made.append(result)
        return result

    monkeypatch.setattr(loopback.socket, "socket", bad_factory)
    with pytest.raises(loopback.LoopbackUnavailable):
        loopback.reserve_socket()
    assert made[0].closed


@pytest.mark.parametrize("sock", [
    FakeSocket(("0.0.0.0", 49152)),
    FakeSocket(("127.0.0.1", 0)),
    FakeSocket(listening=False),
])
def test_server_rejects_nonloopback_or_unbound_or_nonlistening_socket(sock, monkeypatch):
    fake = install_uvicorn(monkeypatch)
    with pytest.raises(loopback.LoopbackUnavailable):
        with loopback.server(lambda _scope: None, sock):
            pytest.fail("invalid socket reached the server")
    assert sock.closed
    assert fake.configs == []


def test_server_uses_bounded_loopback_profile_and_exact_prebound_socket(monkeypatch):
    fake = install_uvicorn(monkeypatch)
    sock = FakeSocket()
    app = lambda _scope: None
    with loopback.server(app, sock) as actual:
        assert actual is fake.servers[0]
        assert not sock.closed
    options = fake.configs[0].options
    assert options["host"] == "127.0.0.1"
    assert options["port"] == 49152
    assert options["workers"] == 1
    assert options["access_log"] is False
    assert options["log_config"] is None
    assert options["proxy_headers"] is False
    assert options["forwarded_allow_ips"] == ""
    assert options["timeout_keep_alive"] == 1
    assert options["limit_concurrency"] == 8
    assert options["backlog"] == 8
    assert options["h11_max_incomplete_event_size"] == 8192
    assert fake.servers[0].should_exit is True
    assert fake.servers[0].sockets == (sock,)
    assert not fake.servers[0].runner.is_alive()
    assert sock.closed


def test_server_configures_tls_only_with_private_absolute_cert_and_key(monkeypatch, tmp_path):
    fake = install_uvicorn(monkeypatch)
    cert = private_file(tmp_path / "localhost.crt")
    key = private_file(tmp_path / "localhost.key")
    sock = FakeSocket()
    with loopback.server(lambda _scope: None, sock, cert, key):
        pass
    options = fake.configs[0].options
    assert options["ssl_certfile"] == str(cert)
    assert options["ssl_keyfile"] == str(key)
    assert options["ssl_version"] == loopback.ssl.PROTOCOL_TLS_SERVER

    second = FakeSocket()
    with pytest.raises(loopback.LoopbackUnavailable):
        with loopback.server(lambda _scope: None, second, certificate=cert):
            pytest.fail("incomplete TLS pair reached the server")
    assert second.closed

    third = FakeSocket()
    with pytest.raises(loopback.LoopbackUnavailable):
        with loopback.server(lambda _scope: None, third,
                certificate=cert.relative_to(tmp_path), private_key=key):
            pytest.fail("relative TLS path reached the server")
    assert third.closed


def test_server_start_failure_and_readiness_timeout_close_resources(monkeypatch):
    fake = install_uvicorn(monkeypatch, "raises")
    sock = FakeSocket()
    with pytest.raises(loopback.LoopbackUnavailable):
        with loopback.server(lambda _scope: None, sock):
            pytest.fail("failed server reached caller")
    assert sock.closed and fake.servers[0].should_exit

    fake = install_uvicorn(monkeypatch, "timeout")
    sock = FakeSocket()
    with pytest.raises(loopback.LoopbackUnavailable):
        with loopback.server(lambda _scope: None, sock, timeout_seconds=0.005):
            pytest.fail("server without startup signal reached caller")
    assert sock.closed and fake.servers[0].should_exit
    assert not fake.servers[0].runner.is_alive()


def test_server_fails_closed_when_force_exit_cannot_stop_thread(monkeypatch):
    fake = install_uvicorn(monkeypatch, "stuck")
    monkeypatch.setattr(loopback, "_STOP_JOIN_SECONDS", 0.001)
    monkeypatch.setattr(loopback, "_FORCE_JOIN_SECONDS", 0.001)
    sock = FakeSocket()
    with pytest.raises(loopback.LoopbackUnavailable):
        with loopback.server(lambda _scope: None, sock):
            pass
    running = fake.servers[0]
    assert running.should_exit and running.force_exit and sock.closed
    running.release.set()
    running.runner.join(0.1)
    assert not running.runner.is_alive()


class FakeHttpClient:
    def __init__(self, **options):
        self.options = options
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.closed = True

    def close(self):
        self.closed = True


def test_http_client_is_real_loopback_client_and_rejects_nonloopback_or_mode_mismatch(monkeypatch):
    import httpx
    clients = []

    def client(**options):
        result = FakeHttpClient(**options)
        clients.append(result)
        return result

    monkeypatch.setattr(httpx, "Client", client)
    with loopback.http_client("http://127.0.0.1:49152") as actual:
        assert actual is clients[-1]
    assert clients[-1].closed
    assert clients[-1].options == {
        "base_url": "http://127.0.0.1:49152",
        "trust_env": False, "follow_redirects": False, "timeout": 2.0,
    }

    for origin, ca in [
        ("http://localhost:49152", None),
        ("http://192.0.2.1:49152", None),
        ("http://127.0.0.1:49152/path", None),
        ("http://127.0.0.1:49152/", None),
        ("http://127.0.0.1:49152?query=1", None),
        ("http://127.0.0.1:49152#fragment", None),
        ("http://127.0.0.1:049152", None),
        ("http://user@127.0.0.1:49152", None),
        ("http://127.0.0.1:49152@192.0.2.1", None),
        ("http://127.0.0.1:49152", "/private/ca.pem"),
        ("https://127.0.0.1:49152", None),
    ]:
        with pytest.raises(loopback.LoopbackUnavailable):
            with loopback.http_client(origin, ca):
                pytest.fail("invalid origin or CA combination reached HTTPX")


def test_https_client_uses_only_private_ca_and_strict_tls(monkeypatch, tmp_path):
    import httpx
    ca = private_file(tmp_path / "pilot-ca.pem")
    contexts = []

    class FakeSSLContext:
        def __init__(self, protocol):
            self.protocol = protocol
            self.loaded = None
            self.check_hostname = False
            self.verify_mode = None
            self.minimum_version = None
            self.default_certs_loaded = False
            contexts.append(self)

        def load_verify_locations(self, *, cafile):
            self.loaded = cafile

        def load_default_certs(self, *_args, **_kwargs):
            self.default_certs_loaded = True

    monkeypatch.setattr(loopback.ssl, "SSLContext", FakeSSLContext)
    clients = []

    def client(**options):
        result = FakeHttpClient(**options)
        clients.append(result)
        return result

    monkeypatch.setattr(httpx, "Client", client)
    with loopback.http_client("https://127.0.0.1:49152", ca) as actual:
        assert actual is clients[-1]
    context = contexts[0]
    assert context.protocol == loopback.ssl.PROTOCOL_TLS_CLIENT
    assert context.loaded == str(ca)
    assert context.check_hostname is True
    assert context.verify_mode == loopback.ssl.CERT_REQUIRED
    assert context.minimum_version == loopback.ssl.TLSVersion.TLSv1_2
    assert context.default_certs_loaded is False
    options = clients[-1].options
    assert options["verify"] is context
    assert options["base_url"] == "https://127.0.0.1:49152"
    assert options["trust_env"] is False
    assert options["follow_redirects"] is False
    assert options["timeout"] == 2.0
    assert clients[-1].closed

    broad = tmp_path / "not-private.pem"
    broad.write_bytes(b"fixture")
    broad.chmod(0o644)
    with pytest.raises(loopback.LoopbackUnavailable):
        with loopback.http_client("https://127.0.0.1:49152", broad):
            pytest.fail("non-private CA path reached HTTPX")


def test_import_is_side_effect_free_and_does_not_import_network_clients():
    source = r'''
import builtins, socket, sys
sys.path.insert(0, %r)
def denied(*_a, **_k): raise AssertionError("network operation on import")
socket.socket.bind = denied
socket.socket.listen = denied
socket.socket.connect = denied
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.split('.')[0] in {'uvicorn', 'httpx', 'torch', 'transformers', 'PIL', 'numpy', 'torchvision'}:
        raise AssertionError("optional client or ML package imported on module import")
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
import semantic_loopback_network
assert semantic_loopback_network.LoopbackUnavailable
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c",
        source % str(ROOT / "scripts")], capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr

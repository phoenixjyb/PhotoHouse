from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.product_roadmap import FILES, RoadmapGateway, attach_routes


class RoadmapGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in FILES:
            (self.root / name).write_text(f"public:{name}", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def security_headers(response):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        csp = response.headers["content-security-policy"]
        assert "default-src 'none'" in csp
        assert "script-src 'self'" in csp
        assert "style-src 'self'" in csp

    def test_redirect_preserves_query_and_security_headers(self):
        with TestClient(RoadmapGateway(FastAPI(), root=self.root)) as client:
            response = client.get("/roadmap?lang=zh&view=full", follow_redirects=False)
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/roadmap/?lang=zh&view=full")
        self.assertEqual(response.content, b"")
        self.security_headers(response)

    def test_fixed_assets_are_served_with_expected_types_and_headers(self):
        with TestClient(RoadmapGateway(FastAPI(), root=self.root)) as client:
            for name, media_type in FILES.items():
                with self.subTest(name=name):
                    response = client.get(f"/roadmap/{name}")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, f"public:{name}".encode())
                    self.assertEqual(response.headers["content-type"], media_type)
                    if name == "roadmap.md":
                        self.assertEqual(response.headers["content-disposition"], 'attachment; filename="roadmap.md"')
                    self.security_headers(response)

    def test_root_directory_serves_index(self):
        with TestClient(RoadmapGateway(FastAPI(), root=self.root)) as client:
            response = client.get("/roadmap/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"public:index.html")

    def test_head_has_file_length_and_no_body(self):
        expected = (self.root / "data.js").stat().st_size
        with TestClient(RoadmapGateway(FastAPI(), root=self.root)) as client:
            response = client.head("/roadmap/data.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
        self.assertEqual(response.headers["content-length"], str(expected))
        self.security_headers(response)

    def test_nonallowlisted_encoded_and_nested_paths_are_not_served(self):
        app = RoadmapGateway(FastAPI(), root=self.root)
        with TestClient(app) as client:
            paths = ["/roadmap/private.txt", "/roadmap/app.js/extra", "/roadmap/%2Fapp.js",
                     "/%72oadmap/app.js"]
            for path in paths:
                with self.subTest(path=path):
                    response = client.get(path, follow_redirects=False)
                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(response.content, b"")
                    self.security_headers(response)
        # Exercise a raw traversal path without a client library normalizing it first.
        status, headers, body = asyncio.run(_direct_response(app, b"/roadmap/%2e%2e/private"))
        self.assertEqual(status, 404)
        self.assertEqual(body, b"")
        self.assertIn((b"x-content-type-options", b"nosniff"), headers)

    def test_non_get_head_methods_are_closed(self):
        with TestClient(RoadmapGateway(FastAPI(), root=self.root)) as client:
            response = client.post("/roadmap/data.js", content=b"ignored")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.headers["allow"], "GET, HEAD")
        self.assertEqual(response.content, b"")
        self.security_headers(response)

    def test_missing_and_symlink_assets_fail_closed_without_path_text(self):
        (self.root / "data.js").unlink()
        (self.root / "data.js").symlink_to(self.root / "roadmap.md")
        with TestClient(RoadmapGateway(FastAPI(), root=self.root)) as client:
            missing = client.get("/roadmap/not-an-asset")
            symlink = client.get("/roadmap/data.js")
        for response in (missing, symlink):
            self.assertEqual(response.status_code, 404)
            self.assertEqual(response.content, b"")
            self.assertNotIn(str(self.root), response.text)
            self.security_headers(response)

    def test_oversized_asset_fails_closed(self):
        (self.root / "app.js").write_bytes(b"x" * (1024 * 1024 + 1))
        with TestClient(RoadmapGateway(FastAPI(), root=self.root)) as client:
            response = client.get("/roadmap/app.js")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b"")

    def test_other_http_lifespan_and_websocket_scopes_delegate(self):
        class Delegate:
            def __init__(self):
                self.events = []

            async def __call__(self, scope, receive, send):
                self.events.append(scope["type"])
                if scope["type"] == "http":
                    await send({"type": "http.response.start", "status": 200,
                                "headers": [(b"content-type", b"text/plain")]})
                    await send({"type": "http.response.body", "body": b"delegated"})
                elif scope["type"] == "lifespan":
                    while True:
                        message = await receive()
                        if message["type"] == "lifespan.startup":
                            await send({"type": "lifespan.startup.complete"})
                        elif message["type"] == "lifespan.shutdown":
                            await send({"type": "lifespan.shutdown.complete"})
                            return
                elif scope["type"] == "websocket":
                    await send({"type": "websocket.accept"})
                    await send({"type": "websocket.close", "code": 1000})

        delegate = Delegate()
        with TestClient(RoadmapGateway(delegate, root=self.root)) as client:
            response = client.get("/api/health")
            with client.websocket_connect("/socket"):
                pass
        self.assertEqual(response.text, "delegated")
        self.assertIn("lifespan", delegate.events)
        self.assertIn("http", delegate.events)
        self.assertIn("websocket", delegate.events)

    def test_real_application_mount_does_not_open_household_routes(self):
        from app.main import create_app
        with TestClient(create_app()) as client:
            self.assertEqual(client.get("/roadmap/?lang=zh").status_code, 200)
            payload = client.get("/roadmap/data.js")
            self.assertEqual(payload.status_code, 200)
            self.assertTrue('"zh":' in payload.text and '"en":' in payload.text)
            self.assertEqual(client.get("/roadmap/private-config.json").status_code, 404)
            self.assertEqual(client.get("/not-a-reviewed-route").status_code, 403)
            self.assertEqual(client.get("/libraries").status_code, 403)

    def test_fastapi_attach_helper_retains_app_and_serves_gateway(self):
        app = FastAPI()
        identity = attach_routes(app, self.root)
        self.assertIs(identity, app)
        with TestClient(app) as client:
            response = client.get("/roadmap?lang=en", follow_redirects=False)
            custom_method = client.request("CUSTOM", "/roadmap/app.js")
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/roadmap/?lang=en")
        self.security_headers(response)
        self.assertEqual(custom_method.status_code, 405)
        self.assertEqual(custom_method.headers["allow"], "GET, HEAD")
        self.security_headers(custom_method)


async def _direct_response(app, raw_path):
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "GET", "scheme": "http", "path": "/roadmap/private",
        "raw_path": raw_path, "query_string": b"", "headers": [],
        "server": ("testserver", 80), "client": ("127.0.0.1", 1234),
    }
    messages = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await app(scope, receive, send)
    start, body = messages
    return start["status"], start["headers"], body["body"]


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
from pathlib import Path
import sys
import threading
import time
import unittest

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.access.semantic_encoder import JointSpaceBinding, TextVector  # noqa: E402
from app.access.semantic_provider_transport import create_provider_app  # noqa: E402
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum  # noqa: E402


TOKEN = "t" * 40
PORT = 8912


def _identity(artifact: str, preprocessing: str, model: str) -> VectorSpaceIdentity:
    return VectorSpaceIdentity(artifact, preprocessing, "shared-v1", model, 2, "unit_l2")


def _binding() -> JointSpaceBinding:
    return JointSpaceBinding(_identity("a" * 64, "b" * 64, "image-v1"),
                             _identity("c" * 64, "d" * 64, "text-v1"), "e" * 64)


class FakeProvider:
    def __init__(self, *, delay: threading.Event | None = None, failure: bool = False):
        self.binding = _binding()
        self.calls: list[str] = []
        self.started = threading.Event()
        self.finished = threading.Event()
        self.release = delay
        self.failure = failure

    def encode(self, query: str, *, check=lambda: None) -> TextVector:
        self.calls.append(query)
        self.started.set()
        try:
            check()
            if self.release is not None:
                self.release.wait(1.0)
            if self.failure:
                raise RuntimeError("private provider path and secret")
            vector = (1.0, 0.0)
            return TextVector(self.binding.binding_sha256,
                              hashlib.sha256(query.encode("utf-8")).hexdigest(),
                              vector, canonical_vector_checksum(vector))
        finally:
            self.finished.set()


class SemanticProviderTransportTests(unittest.TestCase):
    def setUp(self):
        self.provider = FakeProvider()
        self.app = create_provider_app(self.provider, bearer_token=TOKEN, port=PORT)
        self.client = TestClient(self.app, base_url=f"http://127.0.0.1:{PORT}",
                                 client=("127.0.0.1", 50000))

    def tearDown(self):
        self.client.close()

    def _request(self, body: bytes | None = None, *, headers=None, **kwargs):
        request_headers = {"authorization": f"Bearer {TOKEN}",
                           "content-type": "application/json"}
        request_headers.update(headers or {})
        return self.client.post("/v1/encode-text", content=body if body is not None else json.dumps({
            "version": 1, "binding_sha256": self.provider.binding.binding_sha256,
            "query": "blue sky",
        }), headers=request_headers, **kwargs)

    def test_exact_protocol_response_and_security_headers(self):
        response = self._request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {
            "version", "binding_sha256", "query_sha256", "vector", "checksum_sha256"})
        self.assertEqual(response.json()["vector"], [1.0, 0.0])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["cross-origin-resource-policy"], "same-origin")
        self.assertIsNone(self.app.openapi_url)
        self.assertIsNone(self.app.docs_url)

    def test_invalid_credentials_are_rejected_before_body_receive(self):
        async def invoke():
            scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                     "method": "POST", "scheme": "http", "path": "/v1/encode-text",
                     "raw_path": b"/v1/encode-text", "query_string": b"", "root_path": "",
                     "client": ("127.0.0.1", 4), "server": ("127.0.0.1", PORT),
                     "headers": [(b"host", f"127.0.0.1:{PORT}".encode()),
                                 (b"authorization", b"Bearer wrong"),
                                 (b"content-type", b"application/json")]}
            messages = []
            async def receive():
                raise AssertionError("unauthenticated request body was read")
            async def send(message):
                messages.append(message)
            await self.app(scope, receive, send)
            return messages
        import asyncio
        messages = asyncio.run(invoke())
        self.assertEqual(messages[0]["status"], 401)
        self.assertEqual(json.loads(messages[1]["body"]), {"error": "unauthorized"})
        self.assertEqual(self.provider.calls, [])

    def test_loopback_host_and_browser_proxy_boundary(self):
        self.assertEqual(self._request(headers={"host": "localhost:8912"}).status_code, 200)
        self.assertEqual(self._request(headers={"host": "127.0.0.1:8913"}).status_code, 403)
        self.assertEqual(self._request(headers={"origin": "http://127.0.0.1"}).status_code, 403)
        self.assertEqual(self._request(headers={"forwarded": "for=127.0.0.1"}).status_code, 403)
        self.assertEqual(self._request(headers={"x-forwarded-for": "127.0.0.1"}).status_code, 403)

    def test_non_loopback_peer_is_rejected(self):
        remote = TestClient(self.app, base_url=f"http://127.0.0.1:{PORT}",
                            client=("192.0.2.10", 50000))
        try:
            response = remote.post("/v1/encode-text", content=b"not read",
                                   headers={"authorization": f"Bearer {TOKEN}",
                                            "content-type": "application/json"})
        finally:
            remote.close()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.provider.calls, [])

    def test_duplicate_headers_bad_json_unknown_fields_and_wrong_binding_are_refused(self):
        duplicate = self.client.post("/v1/encode-text", content=b"{}", headers=[
            ("authorization", f"Bearer {TOKEN}"), ("authorization", f"Bearer {TOKEN}"),
            ("content-type", "application/json")])
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(self._request(b'{"version":1,').status_code, 400)
        self.assertEqual(self._request(b'{"version":1,"version":1,"binding_sha256":"x","query":"x"}').status_code, 400)
        payload = {"version": 1, "binding_sha256": "0" * 64, "query": "blue sky"}
        self.assertEqual(self._request(json.dumps(payload).encode()).status_code, 400)
        payload = {"version": 1, "binding_sha256": self.provider.binding.binding_sha256,
                   "query": "hello\u0085world"}
        self.assertEqual(self._request(json.dumps(payload).encode()).status_code, 400)
        self.assertEqual(self.provider.calls, [])

    def test_content_encoding_and_streamed_body_limit_are_refused(self):
        self.assertEqual(self._request(headers={"content-encoding": "gzip"}).status_code, 415)
        self.assertEqual(self._request(b"x" * 4097).status_code, 413)
        self.assertEqual(self.provider.calls, [])

    def test_provider_failures_are_redacted_and_invalid_vectors_are_withheld(self):
        failing = FakeProvider(failure=True)
        client = TestClient(create_provider_app(failing, bearer_token=TOKEN, port=PORT),
                            base_url=f"http://127.0.0.1:{PORT}", client=("127.0.0.1", 50000))
        try:
            response = client.post("/v1/encode-text", json={
                "version": 1, "binding_sha256": failing.binding.binding_sha256, "query": "secret query"},
                headers={"authorization": f"Bearer {TOKEN}"})
        finally:
            client.close()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.text)
        self.assertNotIn("secret query", response.text)

        class BadVector(FakeProvider):
            def encode(self, query, *, check=lambda: None):
                vector = (1.0, 1.0)
                return TextVector(self.binding.binding_sha256,
                                  hashlib.sha256(query.encode()).hexdigest(), vector,
                                  canonical_vector_checksum(vector))
        bad = BadVector()
        client = TestClient(create_provider_app(bad, bearer_token=TOKEN, port=PORT),
                            base_url=f"http://127.0.0.1:{PORT}", client=("127.0.0.1", 50000))
        try:
            response = client.post("/v1/encode-text", json={
                "version": 1, "binding_sha256": bad.binding.binding_sha256, "query": "q"},
                headers={"authorization": f"Bearer {TOKEN}"})
        finally:
            client.close()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"error": "provider_unavailable"})

    def test_encoded_response_is_capped_at_client_protocol_limit(self):
        large_binding = JointSpaceBinding(
            VectorSpaceIdentity("a" * 64, "b" * 64, "large-v1", "image-v1", 4096, "unit_l2"),
            VectorSpaceIdentity("c" * 64, "d" * 64, "large-v1", "text-v1", 4096, "unit_l2"),
            "e" * 64)
        class LargeVectorProvider:
            binding = large_binding
            def encode(self, query, *, check=lambda: None):
                values = (0.0156250000001,) * 4096
                return TextVector(large_binding.binding_sha256,
                                  hashlib.sha256(query.encode()).hexdigest(), values,
                                  canonical_vector_checksum(values))
        client = TestClient(create_provider_app(LargeVectorProvider(), bearer_token=TOKEN, port=PORT),
                            base_url=f"http://127.0.0.1:{PORT}", client=("127.0.0.1", 50000))
        try:
            response = client.post("/v1/encode-text", json={
                "version": 1, "binding_sha256": large_binding.binding_sha256, "query": "q"},
                headers={"authorization": f"Bearer {TOKEN}"})
        finally:
            client.close()
        self.assertEqual(response.status_code, 503)
        self.assertLessEqual(len(response.content), 64 * 1024)

    def test_inference_slot_stays_leased_while_worker_is_running(self):
        release = threading.Event()
        provider = FakeProvider(delay=release)
        client1 = TestClient(create_provider_app(provider, bearer_token=TOKEN, port=PORT),
                             base_url=f"http://127.0.0.1:{PORT}", client=("127.0.0.1", 50000))
        client2 = TestClient(client1.app, base_url=f"http://127.0.0.1:{PORT}",
                             client=("127.0.0.1", 50001))
        body = {"version": 1, "binding_sha256": provider.binding.binding_sha256, "query": "q"}
        headers = {"authorization": f"Bearer {TOKEN}"}
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                first = pool.submit(client1.post, "/v1/encode-text", json=body, headers=headers)
                self.assertTrue(provider.started.wait(1.0))
                second = client2.post("/v1/encode-text", json=body, headers=headers)
                self.assertEqual(second.status_code, 429)
                release.set()
                self.assertEqual(first.result(timeout=2).status_code, 200)
        finally:
            release.set()
            client1.close()
            client2.close()

    def test_explicit_cpu_budget_allows_work_beyond_default_deadline(self):
        class SlowProvider(FakeProvider):
            def encode(self, query, *, check=lambda: None):
                time.sleep(2.1)
                return super().encode(query, check=check)
        for budget, expected in ((None, 504), (15.0, 200)):
            with self.subTest(budget=budget):
                provider = SlowProvider()
                kwargs = {} if budget is None else {"seconds": budget}
                app = create_provider_app(provider, bearer_token=TOKEN, port=PORT, **kwargs)
                with TestClient(app, base_url=f"http://127.0.0.1:{PORT}",
                                client=("127.0.0.1", 50000)) as client:
                    response = client.post("/v1/encode-text", headers={
                        "authorization": f"Bearer {TOKEN}"}, json={
                        "version": 1, "binding_sha256": provider.binding.binding_sha256,
                        "query": "slow CPU request"})
                    self.assertEqual(response.status_code, expected)

    def test_explicit_budget_remains_finite_positive_and_bounded(self):
        for budget in (True, 0, -1, float("nan"), float("inf"), 30.01, "15"):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                create_provider_app(self.provider, bearer_token=TOKEN, port=PORT, seconds=budget)
        create_provider_app(self.provider, bearer_token=TOKEN, port=PORT, seconds=30.0)

    def test_timed_out_worker_keeps_lease_and_late_exception_is_consumed(self):
        release = threading.Event()
        provider = FakeProvider(delay=release, failure=True)
        app = create_provider_app(provider, bearer_token=TOKEN, port=PORT, seconds=0.15)
        body = {"version": 1, "binding_sha256": provider.binding.binding_sha256, "query": "late failure"}
        headers = {"authorization": f"Bearer {TOKEN}"}
        logger = logging.getLogger("asyncio")
        old_level = logger.level
        records = []
        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)
        capture = Capture()
        logger.addHandler(capture)
        logger.setLevel(logging.ERROR)
        try:
            with TestClient(app, base_url=f"http://127.0.0.1:{PORT}",
                            client=("127.0.0.1", 50000)) as client:
                timed_out = client.post("/v1/encode-text", json=body, headers=headers)
                self.assertEqual(timed_out.status_code, 504)
                self.assertTrue(provider.started.is_set())
                self.assertFalse(provider.finished.is_set())

                busy = client.post("/v1/encode-text", json=body, headers=headers)
                self.assertEqual(busy.status_code, 429)
                self.assertEqual(len(provider.calls), 1)

                release.set()
                self.assertTrue(provider.finished.wait(1.0))
                retry_deadline = time.monotonic() + 1.0
                while True:
                    retry = client.post("/v1/encode-text", json=body, headers=headers)
                    if retry.status_code != 429 or time.monotonic() >= retry_deadline:
                        break
                    time.sleep(0.01)
                self.assertEqual(retry.status_code, 503)
                self.assertEqual(len(provider.calls), 2)
                # Let call_soon_threadsafe and both Future done callbacks drain.
                time.sleep(0.02)
            self.assertFalse(any("Future exception was never retrieved" in record.getMessage()
                                 for record in records))
            self.assertFalse(any("private provider path and secret" in record.getMessage()
                                 for record in records))
        finally:
            release.set()
            logger.removeHandler(capture)
            logger.setLevel(old_level)


if __name__ == "__main__":
    unittest.main()

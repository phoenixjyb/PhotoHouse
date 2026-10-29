"""Authenticated loopback ASGI transport for an explicitly configured provider.

This module does not load models or start a listener. The caller owns binding the
returned ASGI application to an explicitly selected loopback socket.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
import json
import math
import re
import threading
import time
from typing import Any, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.access.semantic_encoder import (JointSpaceBinding, TextVector, _query_digest,
                                         _unique_object, _valid_query, SemanticUnsupported)
from app.access.visual_candidates import VectorRecord, _canonical_components
from app.access.search_policy import requires_semantic_clarification
from app.access.search_policy_binding import (
    QueryPolicyUnavailable,
    capture_current_query_policy_binding,
    verify_query_policy_binding,
)


_PATH = "/v1/encode-text"
_MAX_BODY = 4096
_MAX_RESPONSE = 64 * 1024
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_-]{32,128}\Z", re.ASCII)
_C1_CONTROL = re.compile(r"[\x80-\x9f]")
_SAFE_HEADERS = ((b"cache-control", b"no-store"),
                 (b"x-content-type-options", b"nosniff"),
                 (b"cross-origin-resource-policy", b"same-origin"))


def _json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


class _Boundary:
    """ASGI boundary that validates routing and credentials before body reads."""

    def __init__(self, app: Any, *, port: int, token: bytes, seconds: float) -> None:
        self.inner = app
        self.port = port
        self.token = token
        self.seconds = seconds

    async def _reply(self, send: Any, status: int, reason: str) -> None:
        body = _json_bytes({"error": reason})
        headers = list(_SAFE_HEADERS) + [(b"content-type", b"application/json; charset=utf-8"),
                                        (b"content-length", str(len(body)).encode("ascii"))]
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body, "more_body": False})

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.inner(scope, receive, send)
            return

        client = scope.get("client")
        if not isinstance(client, (tuple, list)) or not client or client[0] not in ("127.0.0.1", "::1"):
            await self._reply(send, 403, "forbidden")
            return

        headers = scope.get("headers", ())
        grouped: dict[bytes, list[bytes]] = {}
        for key, value in headers:
            grouped.setdefault(key.lower(), []).append(value)
        if (b"origin" in grouped or b"forwarded" in grouped
                or any(key.startswith(b"x-forwarded-") for key in grouped)):
            await self._reply(send, 403, "forbidden")
            return
        if any(len(grouped.get(key, ())) != 1 for key in (b"host", b"authorization")):
            await self._reply(send, 400, "invalid_request")
            return
        host = grouped[b"host"][0]
        if host not in (f"127.0.0.1:{self.port}".encode("ascii"),
                        f"localhost:{self.port}".encode("ascii")):
            await self._reply(send, 403, "forbidden")
            return
        if scope.get("method") != "POST" or scope.get("path") != _PATH:
            await self._reply(send, 404, "not_found")
            return
        if scope.get("query_string", b""):
            await self._reply(send, 400, "invalid_request")
            return

        auth = grouped[b"authorization"][0]
        expected = b"Bearer " + self.token
        if not hmac.compare_digest(auth, expected):
            await self._reply(send, 401, "unauthorized")
            return

        content_types = grouped.get(b"content-type", ())
        if len(content_types) != 1:
            await self._reply(send, 415, "invalid_request")
            return
        content_type = content_types[0].strip().lower()
        if content_type not in (b"application/json", b"application/json; charset=utf-8"):
            await self._reply(send, 415, "invalid_request")
            return
        if b"content-encoding" in grouped:
            await self._reply(send, 415, "invalid_request")
            return
        if (len(grouped.get(b"content-length", ())) > 1
                or b"transfer-encoding" in grouped):
            await self._reply(send, 400, "invalid_request")
            return
        length: int | None = None
        if b"content-length" in grouped:
            raw_length = grouped[b"content-length"][0]
            if not raw_length or not raw_length.isdigit() or len(raw_length) > 10:
                await self._reply(send, 400, "invalid_request")
                return
            length = int(raw_length)
            if length > _MAX_BODY:
                await self._reply(send, 413, "invalid_request")
                return

        started = time.monotonic()
        deadline = started + self.seconds
        body = bytearray()
        more = True
        while more:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                await self._reply(send, 408, "request_timeout")
                return
            try:
                message = await asyncio.wait_for(receive(), timeout=remaining)
            except asyncio.TimeoutError:
                await self._reply(send, 408, "request_timeout")
                return
            except Exception:
                await self._reply(send, 400, "invalid_request")
                return
            if message.get("type") == "http.disconnect":
                return
            if message.get("type") != "http.request":
                await self._reply(send, 400, "invalid_request")
                return
            chunk = message.get("body", b"")
            if not isinstance(chunk, bytes) or len(body) + len(chunk) > _MAX_BODY:
                await self._reply(send, 413, "invalid_request")
                return
            body.extend(chunk)
            more = bool(message.get("more_body", False))
        if length is not None and len(body) != length:
            await self._reply(send, 400, "invalid_request")
            return

        # Replay the bounded body once; later reads remain connected to the
        # server receive channel so the route can observe client disconnects.
        replayed = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        scope.setdefault("state", {})["semantic_provider"] = {
            "deadline": deadline,
            "body": bytes(body),
            "disconnect_receive": replay_receive,
        }

        async def secure_send(message: dict[str, Any]) -> None:
            if message.get("type") == "http.response.start":
                original = [(key, value) for key, value in message.get("headers", ())
                            if key.lower() not in {name for name, _ in _SAFE_HEADERS}]
                message = dict(message)
                message["headers"] = original + list(_SAFE_HEADERS)
            await send(message)

        await self.inner(scope, replay_receive, secure_send)


def create_provider_app(provider: Any, *, bearer_token: str, port: int,
                        seconds: float = 2.0) -> FastAPI:
    """Return the private ASGI adapter with a bounded, explicit request budget.

    Ordinary callers retain the two-second default. CPU deployments may select
    up to thirty seconds; authentication, one-worker admission and cancellation
    use the same deadline for either budget.
    """
    if (type(port) is not int or not 1024 <= port <= 65535
            or type(bearer_token) is not str or _SAFE_TOKEN.fullmatch(bearer_token) is None
            or type(seconds) not in (int, float) or not math.isfinite(float(seconds))
            or not 0 < float(seconds) <= 30.0):
        raise ValueError("invalid_provider_transport_configuration")
    binding = getattr(provider, "binding", None)
    if (type(binding) is not JointSpaceBinding
            or not callable(getattr(provider, "encode", None))):
        raise ValueError("invalid_provider_transport_configuration")

    try:
        process_policy_binding = capture_current_query_policy_binding()
    except QueryPolicyUnavailable:
        raise ValueError("invalid_provider_transport_configuration") from None

    lock = threading.Lock()
    lease = {"active": False}
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="semantic-provider")

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            # Do not wait for, or claim to preempt, an in-progress provider call.
            executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)

    @app.post("/v1/encode-text")
    async def encode_text(request: Request):
        state = request.scope.get("state", {}).get("semantic_provider", {})
        body = state.get("body", b"")
        deadline = state.get("deadline", 0.0)
        try:
            text = body.decode("utf-8", errors="strict")
            data = json.loads(text, object_pairs_hook=_unique_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid_json")))
        except Exception:
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        if (type(data) is not dict or set(data) != {"version", "binding_sha256", "query"}
                or type(data.get("version")) is not int or data["version"] != 1
                or type(data.get("binding_sha256")) is not str
                or data["binding_sha256"] != getattr(binding, "binding_sha256", None)
                or not _valid_query(data.get("query")) or _C1_CONTROL.search(data["query"])):
            return JSONResponse({"error": "invalid_request"}, status_code=400)
        query = data["query"]
        try:
            verify_query_policy_binding(process_policy_binding)
        except QueryPolicyUnavailable:
            return JSONResponse({"error": "provider_unavailable"}, status_code=503)
        query_sha256 = _query_digest(query)
        refusal_headers = request.headers.getlist('x-photohouse-semantic-refusal')
        if refusal_headers not in ([], ['1']):
            return JSONResponse({'error': 'invalid_request'}, status_code=400)
        refusal_opt_in = refusal_headers == ['1']

        with lock:
            if lease["active"]:
                return JSONResponse({"error": "busy"}, status_code=429)
            lease["active"] = True

        cancelled = threading.Event()

        def check() -> None:
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise RuntimeError("request_unavailable")

        def encode_supported() -> TextVector:
            check()
            if requires_semantic_clarification(query):
                raise SemanticUnsupported()
            return provider.encode(query, check=check)

        try:
            check()
            worker = executor.submit(encode_supported)
        except Exception:
            with lock:
                lease["active"] = False
            return JSONResponse({"error": "provider_unavailable"}, status_code=503)

        def release(_future: Any) -> None:
            with lock:
                lease["active"] = False

        worker.add_done_callback(release)

        disconnect = asyncio.Event()

        async def watch_disconnect() -> None:
            receive = state.get("disconnect_receive")
            if receive is None:
                return
            while not disconnect.is_set():
                try:
                    message = await asyncio.wait_for(receive(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                except Exception:
                    disconnect.set()
                    cancelled.set()
                    return
                if message.get("type") == "http.disconnect":
                    disconnect.set()
                    cancelled.set()
                    return

        watcher = asyncio.create_task(watch_disconnect())
        disconnect_task = asyncio.create_task(disconnect.wait())
        wrapped = asyncio.wrap_future(worker)
        shielded = asyncio.shield(wrapped)

        def consume_exception(future: asyncio.Future[Any]) -> None:
            try:
                future.exception()
            except (asyncio.CancelledError, Exception):
                pass

        # A request may time out or disconnect before this worker raises. Both
        # asyncio futures need an exception observer even when nobody awaits them.
        wrapped.add_done_callback(consume_exception)
        shielded.add_done_callback(consume_exception)
        remaining = max(0.0, deadline - time.monotonic())
        try:
            done, _ = await asyncio.wait((shielded, disconnect_task),
                                         timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            if not done:
                cancelled.set()
                return JSONResponse({"error": "request_timeout"}, status_code=504)
            if disconnect.is_set():
                cancelled.set()
                return JSONResponse({"error": "request_unavailable"}, status_code=408)
            check()
            try:
                result = wrapped.result()
            except SemanticUnsupported:
                check()
                if refusal_opt_in and getattr(provider, 'binding', None) == binding:
                    try:
                        verify_query_policy_binding(process_policy_binding, check=check)
                        check()
                    except Exception:
                        return JSONResponse({"error": "provider_unavailable"}, status_code=503)
                    return JSONResponse({'version': 1, 'error': 'unsupported_query',
                        'binding_sha256': binding.binding_sha256,
                        'query_sha256': query_sha256}, status_code=422)
                return JSONResponse({'error': 'provider_unavailable'}, status_code=503)
            except Exception:
                return JSONResponse({"error": "provider_unavailable"}, status_code=503)
            if type(result) is not TextVector:
                return JSONResponse({"error": "provider_unavailable"}, status_code=503)
            if (result.binding_sha256 != binding.binding_sha256
                    or result.query_sha256 != query_sha256):
                return JSONResponse({"error": "provider_unavailable"}, status_code=503)
            try:
                record = VectorRecord("1", binding.text_identity, result.vector,
                                      result.checksum_sha256)
                _canonical_components(record, binding.text_identity)
                response = _json_bytes({
                    "version": 1,
                    "binding_sha256": result.binding_sha256,
                    "query_sha256": result.query_sha256,
                    "vector": list(result.vector),
                    "checksum_sha256": result.checksum_sha256,
                })
                if len(response) > _MAX_RESPONSE:
                    raise ValueError("response_too_large")
            except Exception:
                return JSONResponse({"error": "provider_unavailable"}, status_code=503)
            check()
            try:
                verify_query_policy_binding(process_policy_binding, check=check)
                check()
            except Exception:
                return JSONResponse({"error": "provider_unavailable"}, status_code=503)
            return Response(response, status_code=200,
                            headers={"content-type": "application/json; charset=utf-8"})
        except asyncio.CancelledError:
            cancelled.set()
            raise
        except Exception:
            cancelled.set()
            return JSONResponse({"error": "provider_unavailable"}, status_code=503)
        finally:
            watcher.cancel()
            disconnect_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await watcher
            with suppress(asyncio.CancelledError, Exception):
                await disconnect_task
            # The asyncio wrapper may be cancelled with the request. The
            # concurrent Future callback owns release of the inference lease.

    app.add_middleware(_Boundary, port=port, token=bearer_token.encode("ascii"),
                       seconds=float(seconds))
    return app

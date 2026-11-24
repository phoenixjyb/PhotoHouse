"""Small, bounded static gateway for the public product roadmap documents."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote_to_bytes


MAX_ASSET_BYTES = 1024 * 1024
FILES = {
    "index.html": "text/html; charset=utf-8",
    "styles.css": "text/css; charset=utf-8",
    "app.js": "application/javascript; charset=utf-8",
    "data.js": "application/javascript; charset=utf-8",
    "roadmap.md": "text/markdown; charset=utf-8",
}
SECURITY_HEADERS = [
    (b"cache-control", b"no-store"),
    (b"content-security-policy", (
        b"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
        b"font-src 'self'; connect-src 'none'; media-src 'none'; object-src 'none'; "
        b"base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )),
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
]
ROUTE_PREFIX = "/roadmap"
ROUTE_PREFIX_BYTES = b"/roadmap"


def _safe_read(root: Path, name: str) -> bytes | None:
    """Read one allowlisted regular file, rejecting links and oversized assets."""
    path = root / name
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_ASSET_BYTES:
            return None
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            if (not stat.S_ISREG(opened.st_mode) or
                    (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or
                    opened.st_size > MAX_ASSET_BYTES):
                return None
            chunks = bytearray()
            while len(chunks) <= MAX_ASSET_BYTES:
                chunk = os.read(fd, min(64 * 1024, MAX_ASSET_BYTES + 1 - len(chunks)))
                if not chunk:
                    break
                chunks.extend(chunk)
            if len(chunks) > MAX_ASSET_BYTES:
                return None
            return bytes(chunks)
        finally:
            os.close(fd)
    except (OSError, ValueError):
        return None


def _request_result(scope: dict[str, Any], root: Path) -> tuple[int, list[tuple[bytes, bytes]], bytes]:
    """Build a response tuple for a request already routed to the roadmap."""
    raw_path = scope.get("raw_path")
    if not isinstance(raw_path, bytes):
        raw_path = str(scope.get("path", "")).encode("utf-8", errors="replace")
    path = str(scope.get("path", ""))
    method = str(scope.get("method", "GET")).upper()

    if raw_path == ROUTE_PREFIX_BYTES and path == ROUTE_PREFIX:
        if method not in {"GET", "HEAD"}:
            return 405, SECURITY_HEADERS + [(b"allow", b"GET, HEAD"), (b"content-length", b"0")], b""
        query = scope.get("query_string", b"")
        location = b"/roadmap/" + ((b"?" + query) if query else b"")
        headers = SECURITY_HEADERS + [(b"location", location), (b"content-length", b"0")]
        return 307, headers, b""

    if raw_path == b"/roadmap/" and path == "/roadmap/":
        name = "index.html"
    elif raw_path.startswith(ROUTE_PREFIX_BYTES + b"/") and path.startswith(ROUTE_PREFIX + "/"):
        candidate = raw_path[len(ROUTE_PREFIX_BYTES) + 1:]
        try:
            name = candidate.decode("ascii")
        except UnicodeDecodeError:
            name = ""
    else:
        name = ""

    if name not in FILES:
        expected_raw_path = b""
    elif name == "index.html" and raw_path == b"/roadmap/":
        expected_raw_path = b"/roadmap/"
    else:
        expected_raw_path = b"/roadmap/" + name.encode("ascii")
    if name not in FILES or raw_path != expected_raw_path:
        return 404, SECURITY_HEADERS + [(b"content-length", b"0")], b""
    if method not in {"GET", "HEAD"}:
        return 405, SECURITY_HEADERS + [(b"allow", b"GET, HEAD"), (b"content-length", b"0")], b""

    body = _safe_read(root, name)
    if body is None:
        return 404, SECURITY_HEADERS + [(b"content-length", b"0")], b""
    headers = SECURITY_HEADERS + [
        (b"content-type", FILES[name].encode("ascii")),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if name == "roadmap.md":
        headers.append((b"content-disposition", b'attachment; filename="roadmap.md"'))
    return 200, headers, b"" if method == "HEAD" else body


def _is_roadmap_path(scope: dict[str, Any]) -> bool:
    path = str(scope.get("path", ""))
    raw_path = scope.get("raw_path", b"")
    if path == ROUTE_PREFIX or path.startswith(ROUTE_PREFIX + "/"):
        return True
    if not isinstance(raw_path, bytes):
        return False
    decoded_path = unquote_to_bytes(raw_path)
    return (decoded_path == ROUTE_PREFIX_BYTES or
            decoded_path.startswith(ROUTE_PREFIX_BYTES + b"/"))


class RoadmapGateway:
    """ASGI wrapper serving only the fixed roadmap asset set."""

    def __init__(self, app: Callable[..., Any], *, root: Path):
        self.app = app
        self.root = Path(root)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or not _is_roadmap_path(scope):
            await self.app(scope, receive, send)
            return

        status, headers, body = _request_result(scope, self.root)
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})


def attach_routes(app, root: Path):
    """Install the ASGI gateway on an existing FastAPI app and return that app."""
    app.add_middleware(RoadmapGateway, root=Path(root))
    return app

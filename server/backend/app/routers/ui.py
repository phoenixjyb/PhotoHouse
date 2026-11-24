from functools import lru_cache
import gzip
import hashlib
from pathlib import Path
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response

router = APIRouter()
oral_history_ui_router = APIRouter()

UI_DIR = Path(__file__).resolve().parents[1] / "ui" / "access"
INDEX_FILE = UI_DIR / "index.html"
_ORAL_HISTORY_PANEL = '<details id="oral-history-panel" class="access-panel" hidden>'
_ORAL_HISTORY_SCRIPT = '    <script data-module="oral-history" src="/ui/oral-history.js"></script>\n'
APP_FILE = UI_DIR / "app.js"
STYLE_FILE = UI_DIR / "styles.css"
ICON_FILE = UI_DIR.parent / "photohouse-icon.svg"
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; media-src 'self' blob:; connect-src 'self'; font-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'; worker-src 'none'",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=()",
}
ASSET_MEDIA_TYPES = {
    "app.js": "application/javascript",
    "story-draft-store.js": "application/javascript",
    "story-workspace.js": "application/javascript",
    "memory-groups.js": "application/javascript",
    "memory-community.js": "application/javascript",
    "oral-history.js": "application/javascript",
    "styles.css": "text/css",
    "assistant-private-workspace.js": "application/javascript",
    "voice-session-control.js": "application/javascript",
    "voice-turn-timing.js": "application/javascript",
    "photohouse-icon.svg": "image/svg+xml",
}
UI_ASSET_PATHS = frozenset(f"/ui/{name}" for name in ASSET_MEDIA_TYPES)
VERSIONED_UI_ASSET = "photohouse.versioned_ui_asset"
VERSIONED_HEADERS = {
    **{key: value for key, value in NO_CACHE_HEADERS.items()
       if key not in {"Cache-Control", "Pragma", "Expires"}},
    "Cache-Control": "public, max-age=31536000, immutable",
}
_ASSET_REF = re.compile(r'((?:src|href)\s*=\s*)([\"\'])/ui/([A-Za-z0-9._-]+)\2', re.I)


@lru_cache(maxsize=32)
def _read_asset_cached(path: Path, identity: tuple[int, ...]) -> tuple[bytes, str]:
    # Identity keys the cache by the file behind the currently bound UI path.
    data = path.read_bytes()
    return data, hashlib.sha256(data).hexdigest()


def _read_asset(path: Path) -> tuple[bytes, str]:
    try:
        info = path.stat()
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        return _read_asset_cached(path, identity)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail=f"UI asset missing: {path.name}",
                            headers=NO_CACHE_HEADERS) from None


@lru_cache(maxsize=32)
def _gzip(data: bytes) -> bytes:
    return gzip.compress(data, compresslevel=6, mtime=0)


def _accepts_gzip(header: str) -> bool:
    quality = {}
    for part in header.split(","):
        coding, *parameters = [value.strip().lower() for value in part.split(";")]
        q = 1.0
        for parameter in parameters:
            name, _, value = parameter.partition("=")
            if name.strip() == "q":
                try:
                    q = float(value)
                except ValueError:
                    q = 0.0
                if not 0 <= q <= 1:
                    q = 0.0
                break
        quality[coding] = q
    gzip_quality = quality.get("gzip", quality.get("*", 0.0))
    return gzip_quality > 0 and gzip_quality >= quality.get("identity", 0.0)


def _static_response(request: Request, data: bytes, media_type: str, headers: dict[str, str]) -> Response:
    headers = {**headers, "Vary": "Accept-Encoding"}
    if len(data) >= 512 and _accepts_gzip(request.headers.get("accept-encoding", "")):
        data = _gzip(data)
        headers["Content-Encoding"] = "gzip"
    return Response(data, media_type=media_type, headers=headers)


def _asset_response(request: Request, name: str, version: str | None) -> Response:
    path, media_type = _asset_path(name), ASSET_MEDIA_TYPES[name]
    if version is None:
        if not path.is_file():
            raise HTTPException(status_code=500, detail=f"UI asset missing: {path.name}", headers=NO_CACHE_HEADERS)
        return FileResponse(path, media_type=media_type, headers=NO_CACHE_HEADERS)
    if not re.fullmatch(r"[0-9a-f]{64}", version):
        raise HTTPException(status_code=404, detail="UI asset version not found", headers=NO_CACHE_HEADERS)
    data, digest = _read_asset(path)
    if version != digest:
        raise HTTPException(status_code=404, detail="UI asset version not found", headers=NO_CACHE_HEADERS)
    request.scope[VERSIONED_UI_ASSET] = True
    return _static_response(request, data, media_type, VERSIONED_HEADERS)


def _asset_path(name: str) -> Path:
    if name == "app.js":
        return APP_FILE
    if name == "styles.css":
        return STYLE_FILE
    if name == "photohouse-icon.svg":
        return ICON_FILE
    return UI_DIR / name


@lru_cache(maxsize=4)
def _referenced_assets(html: str) -> tuple[str, ...]:
    return tuple(sorted({match.group(3) for match in _ASSET_REF.finditer(html)
                         if match.group(3) in ASSET_MEDIA_TYPES}))


@lru_cache(maxsize=4)
def _versioned_shell(html: str, versions: tuple[tuple[str, str], ...]) -> bytes:
    by_name = dict(versions)

    def replace(match):
        attribute, quote, name = match.groups()
        if name not in by_name:
            return match.group(0)
        return f"{attribute}{quote}/ui/{name}?v={by_name[name]}{quote}"

    return _ASSET_REF.sub(replace, html).encode("utf-8")


@router.get("/ui")
def ui_home(request: Request):
    html = _read_asset(INDEX_FILE)[0].decode("utf-8")
    if getattr(request.app.state, 'oral_history_intake_enabled', False):
        flags = ''.join(
            f' data-{name}="enabled"'
            for name, option in (
                ('transcription', 'oral_history_transcription_enabled'),
                ('reviewed-text', 'oral_history_reviewed_text_enabled'),
            )
            if getattr(request.app.state, option, False)
        )
        html = html.replace(_ORAL_HISTORY_PANEL,
                            _ORAL_HISTORY_PANEL.removesuffix(" hidden>") + flags + ">", 1)
    else:
        html = html.replace(_ORAL_HISTORY_SCRIPT, "", 1)
    versions = tuple((name, _read_asset(_asset_path(name))[1]) for name in _referenced_assets(html))
    return _static_response(request, _versioned_shell(html, versions), "text/html", NO_CACHE_HEADERS)


@router.get("/ui/app.js")
def ui_js(request: Request, v: str | None = None):
    return _asset_response(request, "app.js", v)


@router.get("/ui/story-draft-store.js")
def ui_story_draft_store(request: Request, v: str | None = None):
    return _asset_response(request, "story-draft-store.js", v)


@router.get("/ui/story-workspace.js")
def ui_story_workspace(request: Request, v: str | None = None):
    return _asset_response(request, "story-workspace.js", v)


@router.get("/ui/memory-groups.js")
def ui_memory_groups(request: Request, v: str | None = None):
    return _asset_response(request, "memory-groups.js", v)


@router.get("/ui/memory-community.js")
def ui_memory_community(request: Request, v: str | None = None):
    return _asset_response(request, "memory-community.js", v)


@oral_history_ui_router.get("/ui/oral-history.js")
def ui_oral_history(request: Request, v: str | None = None):
    return _asset_response(request, "oral-history.js", v)


@router.get("/ui/styles.css")
def ui_css(request: Request, v: str | None = None):
    return _asset_response(request, "styles.css", v)


@router.get("/ui/assistant-private-workspace.js")
def ui_assistant_private_workspace(request: Request, v: str | None = None):
    return _asset_response(request, "assistant-private-workspace.js", v)


@router.get("/ui/voice-session-control.js")
def ui_voice_session_control(request: Request, v: str | None = None):
    return _asset_response(request, "voice-session-control.js", v)


@router.get("/ui/voice-turn-timing.js")
def ui_voice_turn_timing(request: Request, v: str | None = None):
    return _asset_response(request, "voice-turn-timing.js", v)


@router.get("/ui/photohouse-icon.svg")
def ui_icon(request: Request, v: str | None = None):
    return _asset_response(request, "photohouse-icon.svg", v)


@router.get("/ui/search")
def ui_search():
    # Legacy deep links reach the safe shell without copying private query text.
    return RedirectResponse(url="/ui")


@router.get("/ui/admin")
def ui_admin():
    return RedirectResponse(url="/ui")

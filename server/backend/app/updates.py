"""Opt-in, read-only delivery of operator-published Android packages."""
import hashlib
import json
from pathlib import Path
import re
import stat

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter()
CHANNELS = {'phone': 'dev.photohouse.connected', 'tv': 'dev.photohouse.tv'}
NO_STORE = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}
MAX_APK_BYTES = 160 * 1024 * 1024


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate update field')
        value[key] = item
    return value


def _regular(path: Path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or path.resolve(strict=True) != path:
        raise ValueError('Invalid update file')
    return info


def _release(root: Path, channel: str):
    if channel not in CHANNELS:
        raise ValueError('Invalid update channel')
    manifest = root / f'{channel}.json'
    if _regular(manifest).st_size > 4096:
        raise ValueError('Invalid update manifest')
    value = json.loads(manifest.read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
    if (type(value) is not dict or set(value) != {'schema_version', 'channel', 'package_name',
            'version_code', 'version_name', 'bytes', 'sha256', 'signing_cert_sha256'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['channel'] != channel
            or value['package_name'] != CHANNELS[channel]
            or type(value['version_code']) is not int or not 1 <= value['version_code'] <= 2147483647
            or type(value['version_name']) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._+ -]{0,79}', value['version_name'])
            or type(value['bytes']) is not int or not 0 < value['bytes'] <= MAX_APK_BYTES
            or type(value['sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['sha256'])
            or type(value['signing_cert_sha256']) is not str
            or not re.fullmatch('[0-9a-f]{64}', value['signing_cert_sha256'])):
        raise ValueError('Invalid update manifest')
    apk = root / f"{value['sha256']}.apk"
    if _regular(apk).st_size != value['bytes']:
        raise ValueError('Invalid update package')
    digest = hashlib.sha256()
    with apk.open('rb') as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(part)
    if digest.hexdigest() != value['sha256']:
        raise ValueError('Invalid update package')
    return value, apk


def _available(request: Request, channel: str):
    root = getattr(request.app.state, 'update_root', None)
    if root is None:
        return None
    try:
        return _release(root, channel)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return None


@router.get('/updates/v1/{channel}')
def update_manifest(channel: str, request: Request):
    release = _available(request, channel)
    if release is None:
        return JSONResponse({'detail': 'Updates unavailable'}, status_code=503, headers=NO_STORE)
    value, _ = release
    return JSONResponse({**value, 'apk_url': f"/updates/v1/{channel}/{value['sha256']}.apk"}, headers=NO_STORE)


@router.get('/updates/v1/{channel}/{sha256}.apk')
def update_apk(channel: str, sha256: str, request: Request):
    release = _available(request, channel)
    if release is None or sha256 != release[0]['sha256']:
        return JSONResponse({'detail': 'Updates unavailable'}, status_code=503, headers=NO_STORE)
    return FileResponse(release[1], media_type='application/vnd.android.package-archive',
                        headers={**NO_STORE, 'Content-Disposition': 'attachment; filename="PhotoHouse.apk"'})

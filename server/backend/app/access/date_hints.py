"""Conservative display date hints for assets without capture metadata."""

from datetime import datetime, timezone
from pathlib import PureWindowsPath
import re


_LITERAL = re.compile(
    r'(?<!\d)((?:19|20)\d{2})[-_. ]?(0[1-9]|1[0-2])[-_. ]?'
    r'(0[1-9]|[12]\d|3[01])'
    r'(?:[T_ .-]?([01]\d|2[0-3])[:._-]?([0-5]\d)[:._-]?([0-5]\d))?'
    r'(?!\d)'
)
_WECHAT_EPOCH = re.compile(r'^(?:mmexport|wx_camera_)(\d{13})(?:\D|$)', re.IGNORECASE)


def filename_date(path):
    """Return only a valid calendar date or recognized WeChat export epoch."""
    name = PureWindowsPath(path).name
    match = _LITERAL.search(name)
    if match:
        try:
            parts = [int(part) if part is not None else 0 for part in match.groups()]
            value = datetime(*parts)
        except ValueError:
            return None
        return value.strftime('%Y-%m-%d %H:%M:%S') if match.group(4) else value.date().isoformat()
    match = _WECHAT_EPOCH.match(name)
    if match:
        try:
            value = datetime.fromtimestamp(int(match.group(1)) / 1000, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        if 2000 <= value.year <= 2099:
            return value.isoformat().replace('+00:00', 'Z')
    return None


def date_hint(path, taken_at, received_epoch):
    """Keep filename and PhotoHouse receipt evidence separate from capture time."""
    if taken_at:
        return None
    value = filename_date(path)
    if value:
        return {'value': value, 'source': 'filename'}
    if type(received_epoch) in (int, float):
        try:
            value = datetime.fromtimestamp(received_epoch, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        if 2000 <= value.year <= 2099:
            return {'value': value.isoformat().replace('+00:00', 'Z'), 'source': 'received'}
    return None

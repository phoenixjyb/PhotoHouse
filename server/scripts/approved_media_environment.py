"""Bind existing, fingerprinted media executables to a worker environment."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat


def bind_media_tools(environment, bindings):
    """Return a child environment after verifying both operator-selected tools."""
    if set(bindings) != {'ffmpeg', 'ffprobe'}:
        raise ValueError('media_tool_binding_required')
    directories = []
    result = dict(environment)
    for name in ('ffmpeg', 'ffprobe'):
        binding = bindings[name]
        if set(binding) != {'path', 'sha256'} or not re.fullmatch(
                r'[0-9a-f]{64}', binding['sha256']):
            raise ValueError('media_tool_binding_invalid')
        path = Path(binding['path'])
        if not path.is_absolute() or path.name.lower() not in (name, name + '.exe'):
            raise ValueError('media_tool_path_invalid')
        for part in (path, *path.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ValueError('media_tool_reparse_refused')
        before = path.stat()
        if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= 512 * 1024**2:
            raise ValueError('media_tool_file_invalid')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        after = path.stat()
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
        if identity(before) != identity(after) or digest != binding['sha256']:
            raise ValueError('media_tool_fingerprint_mismatch')
        directory = str(path.parent)
        if directory not in directories:
            directories.append(directory)
        result[name.upper() + '_EXE'] = str(path)
    result['PATH'] = os.pathsep.join(directories + ([result['PATH']] if result.get('PATH') else []))
    return result

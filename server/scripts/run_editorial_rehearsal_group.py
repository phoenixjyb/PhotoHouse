"""Run one fixed synthetic editorial test group in a disposable directory.

This entry point does not stage source, install dependencies, control services,
or migrate a household database. A caller owns native resource limits. The
Python audit hook catches accidental network and database access in this process;
it is an additional check, not an operating-system sandbox.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
from contextlib import contextmanager
from urllib.parse import parse_qsl, unquote, urlsplit

GROUPS = (
    (47, ("test_memory_book_editorial_migration.py", "test_memory_book_editorial_http.py",
          "test_memory_book_editorial_service.py", "test_memory_book_editorial_deletions.py",
          "test_memory_book_editorial_contract.py", "test_memory_book_editorial_schema.py",
          "test_memory_book_editorial_erasure.py")),
    (12, ("test_approved_cpu_worker.py",)),
    (8, ("test_approved_face_worker.py",)),
    (14, ("test_approved_image_embed_worker.py",)),
    (7, ("test_approved_video_embed_worker.py",)),
    (15, ("test_approved_video_worker.py",)),
    (14, ("test_apply_memory_editorial_schema.py",)),
    (22, ("test_approved_face_queue.py", "test_approved_face_pipeline.py")),
    (12, ("test_editorial_rehearsal_database_guard.py",)),
)


def sqlite_uri_filename(value: str, *, windows: bool) -> str:
    """Decode a local SQLite file URI without interpreting a drive as a host.

    SQLite treats the /X:/ prefix as a Windows volume. Keep URI handling
    separate from native filesystem resolution so both platform forms can be
    checked without opening a database. Auxiliary VFS/file options are outside
    this generated-data rehearsal.
    """
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('invalid_sqlite_uri')
    if re.search(r'%(?![0-9a-fA-F]{2})', value):
        raise ValueError('invalid_sqlite_uri_escape')
    uri = urlsplit(value)
    if uri.scheme != 'file' or uri.netloc not in ('', 'localhost'):
        raise ValueError('nonlocal_sqlite_uri')
    options = parse_qsl(uri.query, keep_blank_values=True, strict_parsing=True,
                        max_num_fields=4)
    allowed = {'mode': {'ro', 'rw', 'rwc', 'memory'},
               'cache': {'private', 'shared'}, 'immutable': {'0', '1'}}
    seen = set()
    for key, option in options:
        if key in seen or option not in allowed.get(key, set()):
            raise ValueError('unsupported_sqlite_uri_option')
        seen.add(key)
    filename = unquote(uri.path, encoding='utf-8', errors='strict')
    if not filename or '\\' in filename or any(ord(c) < 32 or ord(c) == 127 for c in filename):
        raise ValueError('invalid_sqlite_uri_path')
    if windows:
        if re.match(r'^/[a-zA-Z]:/', filename):
            filename = filename[1:]
        if re.match(r'^/?[a-zA-Z]:(?!/)', filename):
            raise ValueError('drive_relative_sqlite_uri')
    return filename


def database_within(path: object, root: Path) -> bool:
    if isinstance(path, bytes):
        path = os.fsdecode(path)
    if not isinstance(path, (str, os.PathLike)):
        return False
    try:
        value = os.fsdecode(os.fspath(path))
        if value.startswith('file:'):
            value = sqlite_uri_filename(value, windows=os.name == 'nt')
        if value == ':memory:':
            return True
        return Path(value).resolve().is_relative_to(root.resolve())
    except (ValueError, OSError, UnicodeError):
        return False


class SocketPairAllowance:
    """Allow only the stdlib socketpair's own ephemeral loopback connection.

    Windows uses TCP for asyncio's internal wakeup pair. Track its listener in
    the creating thread; this cannot authorize arbitrary loopback endpoints.
    """
    def __init__(self):
        self.state = threading.local()

    @contextmanager
    def creating(self):
        previous = (getattr(self.state, 'active', False), getattr(self.state, 'listener', None))
        self.state.active, self.state.listener = True, None
        try:
            yield
        finally:
            self.state.active, self.state.listener = previous

    def permits(self, event, args):
        if not getattr(self.state, 'active', False) or event not in {'socket.bind', 'socket.connect'}:
            return False
        connection, address = args[:2]
        if not isinstance(address, tuple) or len(address) < 2 or address[0] not in ('127.0.0.1', '::1'):
            return False
        if event == 'socket.bind' and address[1] == 0 and self.state.listener is None:
            self.state.listener = connection
            return True
        listener = self.state.listener
        return event == 'socket.connect' and listener is not None and address[:2] == listener.getsockname()[:2]


def audit_guard(root: Path, pair_allowance: SocketPairAllowance | None = None):
    def audit(event, args):
        if event in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.gethostbyname"}:
            if pair_allowance is not None and pair_allowance.permits(event, args):
                return
            raise RuntimeError("rehearsal_network_access_refused")
        if event == "sqlite3.connect" and not database_within(args[0], root):
            raise RuntimeError("rehearsal_database_outside_candidate")
    return audit


def run(source: Path, output: Path, group: int) -> dict:
    source = source.resolve(strict=True)
    output = output.resolve(strict=True)
    if not output.is_dir() or not output.is_relative_to(source.parent) or output == source:
        raise ValueError("private_output_required")
    if not 1 <= group <= len(GROUPS):
        raise ValueError("unknown_group")
    expected, names = GROUPS[group - 1]
    paths = [source / "tests" / "security" / name for name in names]
    if any(p.is_symlink() or not p.is_file() for p in paths):
        raise ValueError("test_source_missing")
    run_root = output / f"group-{group}"
    run_root.mkdir()  # never reuse a previous test's outputs
    temporary = run_root / "temporary"
    temporary.mkdir()
    os.environ.update({
        "TEMP": str(temporary), "TMP": str(temporary), "TMPDIR": str(temporary),
        "PHOTOHOUSE_NO_DOTENV": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "AUTO_MIGRATE": "false", "ENABLE_INLINE_WORKER": "false",
        "VLM_DATA_ROOT": str(run_root / "runtime"),
        "ORIGINALS_PATH": str(run_root / "originals"), "DERIVED_PATH": str(run_root / "derived"),
        "VLM_TMP_DIR": str(temporary),
        "DATABASE_URL": "sqlite:///" + (run_root / "guard.sqlite").as_posix(),
        "CAPTION_PROVIDER": "stub", "FACE_EMBED_PROVIDER": "stub", "FACE_DETECT_PROVIDER": "stub",
        "IMAGE_TAG_PROVIDER": "stub", "VOICE_ENABLED": "false", "VIDEO_ENABLED": "false",
    })
    tempfile.tempdir = str(temporary)
    os.chdir(source)
    sys.path[:0] = [str(source / "backend"), str(source / "tests" / "security")]
    import socket
    pair_allowance = SocketPairAllowance()
    original_pair = socket.socketpair
    def guarded_pair(*args, **kwargs):
        with pair_allowance.creating():
            return original_pair(*args, **kwargs)
    socket.socketpair = guarded_pair
    sys.addaudithook(audit_guard(source.parent, pair_allowance))
    import pytest

    class Counts:
        collected = 0
        skipped = 0
        failed = 0

        def pytest_collection_finish(self, session):
            # pytest assigns testscollected after this hook; count the collected
            # items here rather than mistaking a passing group for zero tests.
            self.collected = len(session.items)

        def pytest_runtest_logreport(self, report):
            self.skipped += int(report.skipped)
            self.failed += int(report.failed)

    counts = Counts()
    status = int(pytest.main([
        "-o", "addopts=", "-p", "no:cacheprovider", "-q",
        "--basetemp", str(temporary / "pytest"),
        "--junitxml", str(run_root / "tests.xml"), *(str(p) for p in paths),
    ], plugins=[counts]))
    result = {"group": group, "collected": counts.collected, "expected": expected,
              "failed": counts.failed, "skipped": counts.skipped, "exit_code": status,
              "passed": status == 0 and counts.collected == expected and counts.failed == counts.skipped == 0}
    with (run_root / "result.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True)
        stream.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--group", type=int, required=True)
    args = parser.parse_args()
    try:
        result = run(args.source, args.output, args.group)
    except (OSError, ValueError, RuntimeError):
        print(json.dumps({"passed": False, "code": "synthetic_group_refused"}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

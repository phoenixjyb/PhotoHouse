#!/usr/bin/env python3
"""Create optional, content-free local receipts for source-check invocations."""
from __future__ import annotations

import hashlib
import errno
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
PROFILE_INPUTS = {
    "api": ("server/backend", "server/tests", "config", "examples/generated-demo"),
    "memory": ("server/backend", "server/tests", "config"),
    "windows-cpu": ("server/backend", "server/tests", "config"),
    "web": ("server/backend", "server/tests/security"),
    "android": ("clients/android/android",),
}
COMMON_INPUTS = ("tools/check.py", "tools/check_receipt.py")
EXPANSION = {"api": ("api",), "memory": ("memory",), "windows-cpu": ("windows-cpu",),
             "android": ("android",), "web": ("web",), "all": ("api", "android")}
EXCLUDED_PARTS = {".git", ".gradle", ".kotlin", ".pytest_cache", "__pycache__", "build",
                  "node_modules", ".venv", ".runtime", "out"}
_HEAD = re.compile(rb"[0-9a-f]{40,64}\Z")


class ReceiptError(ValueError):
    """Safe fixed reason code for receipt preflight or publication failures."""


def expanded_profiles(profile: str) -> tuple[str, ...]:
    try:
        return EXPANSION[profile]
    except KeyError:
        raise ReceiptError("profile_invalid") from None


def _git_env() -> dict[str, str]:
    allowed = {"PATH", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "HOME",
               "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP", "TMPDIR", "LANG",
               "LC_ALL", "LC_CTYPE", "TZ"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
    return env


def _selected(path: str, profiles: tuple[str, ...]) -> bool:
    if path in COMMON_INPUTS:
        return True
    return any(path == prefix or path.startswith(prefix + "/")
               for profile in profiles for prefix in PROFILE_INPUTS[profile])


def _path_identity(path: Path) -> tuple[int, int, int, int, int]:
    item = path.lstat()
    return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, stat.S_IMODE(item.st_mode)


def _hash_source_file(root: Path, relative: str, digest) -> None:
    pure = PurePosixPath(relative)
    if (not relative or "\\" in relative or pure.is_absolute() or
            any(part in ("", ".", "..") for part in pure.parts)):
        raise ReceiptError("source_path_invalid")
    path = root
    try:
        for index, part in enumerate(pure.parts):
            path = path / part
            item = path.lstat()
            if stat.S_ISLNK(item.st_mode):
                raise ReceiptError("source_symlink_refused")
            if index < len(pure.parts) - 1 and not stat.S_ISDIR(item.st_mode):
                raise ReceiptError("source_path_invalid")
        before = _path_identity(path)
        item = path.lstat()
        if not stat.S_ISREG(item.st_mode):
            raise ReceiptError("source_file_not_regular")
        header = relative.encode("utf-8", "strict")
        digest.update(len(header).to_bytes(8, "big"))
        digest.update(header)
        digest.update(before[4].to_bytes(4, "big"))
        digest.update(before[2].to_bytes(8, "big"))
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            opened_identity = (opened.st_dev, opened.st_ino, opened.st_size,
                               opened.st_mtime_ns, stat.S_IMODE(opened.st_mode))
            if opened_identity != before or not stat.S_ISREG(opened.st_mode):
                raise ReceiptError("source_changed_during_read")
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
            after = os.fstat(stream.fileno())
        final_identity = _path_identity(path)
        identity = (after.st_dev, after.st_ino, after.st_size,
                    after.st_mtime_ns, stat.S_IMODE(after.st_mode))
        if identity != before or final_identity != before:
            raise ReceiptError("source_changed_during_read")
    except ReceiptError:
        raise
    except (OSError, UnicodeError):
        raise ReceiptError("source_unreadable") from None


def _receipt_relative(root: Path, receipt_path: Path | None) -> str | None:
    if receipt_path is None:
        return None
    try:
        relative = os.path.relpath(os.path.abspath(receipt_path), os.path.abspath(root))
    except ValueError:
        return None
    if relative == os.pardir or relative.startswith(os.pardir + os.sep) or os.path.isabs(relative):
        return None
    return Path(relative).as_posix()


def source_identity(root: Path, profiles: tuple[str, ...], receipt_path: Path | None = None) -> dict[str, str | None]:
    """Hash profile inputs from Git's tracked and nonignored untracked inventory."""
    root = Path(root)
    head: str | None = None
    try:
        result = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], cwd=root,
                                env=_git_env(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                check=True)
        raw_head = result.stdout.strip()
        if _HEAD.fullmatch(raw_head) is None:
            raise ReceiptError("git_head_invalid")
        head = raw_head.decode("ascii")
        result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                                cwd=root, env=_git_env(), stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, check=True)
        files = result.stdout.split(b"\0")
        selected: list[tuple[bytes, str]] = []
        excluded = _receipt_relative(root, receipt_path)
        for raw_path in files:
            if not raw_path:
                continue
            try:
                relative = raw_path.decode("utf-8", "strict")
            except UnicodeDecodeError:
                raise ReceiptError("source_path_invalid") from None
            parts = PurePosixPath(relative).parts
            if any(part in EXCLUDED_PARTS for part in parts):
                continue
            if relative == excluded or not _selected(relative, profiles):
                continue
            selected.append((raw_path, relative))
        for profile in profiles:
            for prefix in PROFILE_INPUTS[profile]:
                if not any(relative == prefix or relative.startswith(prefix + "/")
                           for _, relative in selected):
                    raise ReceiptError("profile_input_missing")
        selected.sort(key=lambda item: item[0])
        digest = hashlib.sha256()
        for _, relative in selected:
            _hash_source_file(root, relative, digest)
        return {"head": head, "source_sha256": digest.hexdigest(), "reason": None}
    except ReceiptError as error:
        return {"head": head, "source_sha256": None, "reason": str(error)}
    except (OSError, subprocess.SubprocessError):
        return {"head": head, "source_sha256": None, "reason": "git_or_source_unavailable"}


def preflight_destination(destination: Path, root: Path = ROOT) -> Path:
    """Resolve a new receipt path, refusing any existing file before checks run."""
    destination = Path(destination)
    if not destination.is_absolute():
        destination = Path.cwd() / destination
    destination = Path(os.path.abspath(destination))
    try:
        destination.lstat()
    except FileNotFoundError:
        pass
    except OSError:
        raise ReceiptError("destination_unavailable") from None
    else:
        raise ReceiptError("destination_exists")
    try:
        parent = destination.parent
        item = parent.lstat()
        if stat.S_ISLNK(item.st_mode) or not stat.S_ISDIR(item.st_mode):
            raise ReceiptError("destination_parent_invalid")
    except ReceiptError:
        raise
    except OSError:
        raise ReceiptError("destination_parent_invalid") from None
    try:
        relative = os.path.relpath(destination, Path(root).absolute())
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep) and not os.path.isabs(relative):
            tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", Path(relative).as_posix()],
                                     cwd=root, env=_git_env(), stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL, check=False)
            if tracked.returncode == 0:
                raise ReceiptError("destination_tracks_source")
    except ReceiptError:
        raise
    except (OSError, ValueError):
        # Source identity can be unavailable outside a Git checkout; the
        # filesystem no-overwrite checks above still apply.
        pass
    return destination


def make_receipt(profile: str, profiles: tuple[str, ...], started_at: str, finished_at: str,
                 start: dict[str, str | None], end: dict[str, str | None], exit_code: int) -> dict:
    start_available = start.get("head") is not None and start.get("source_sha256") is not None
    end_available = end.get("head") is not None and end.get("source_sha256") is not None
    unchanged = bool(start_available and end_available and
                     start["head"] == end["head"] and start["source_sha256"] == end["source_sha256"])
    return {
        "schema": 1,
        "kind": "local_check_invocation",
        "profile": profile,
        "expanded_profiles": list(profiles),
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "head_start": start.get("head"),
        "head_end": end.get("head"),
        "source_sha256_start": start.get("source_sha256"),
        "source_sha256_end": end.get("source_sha256"),
        "source_identity": "available" if start_available and end_available else "unavailable",
        "source_identity_reason_start": start.get("reason"),
        "source_identity_reason_end": end.get("reason"),
        "source_unchanged": unchanged,
        "exit_code": int(exit_code),
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_receipt(destination: Path, receipt: dict) -> None:
    """Publish mode-0600 JSON atomically without replacing an existing path."""
    temporary: str | None = None
    try:
        fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.tmp-", dir=destination.parent)
        try:
            os.fchmod(fd, 0o600)
        except (AttributeError, NotImplementedError):
            # Windows does not expose fchmod consistently. chmod still sets
            # the restrictive mode where supported; the receipt stays local
            # and contains no secrets or raw check output.
            os.chmod(temporary, 0o600)
        except OSError as error:
            unsupported = {getattr(errno, "ENOSYS", None), getattr(errno, "EOPNOTSUPP", None),
                           getattr(errno, "EINVAL", None)}
            if error.errno not in unsupported:
                raise
            os.chmod(temporary, 0o600)
        payload = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # A hard link is an atomic no-clobber publication on the same filesystem.
        try:
            # ``follow_symlinks`` is not implemented by every Python/platform
            # pair. This is a regular file created by mkstemp in this folder,
            # so the portable form remains a no-clobber hard-link publish.
            os.link(temporary, destination, follow_symlinks=False)
        except (NotImplementedError, TypeError):
            os.link(temporary, destination)
        os.unlink(temporary)
        temporary = None
        try:
            dir_fd = os.open(destination.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except FileExistsError:
        raise ReceiptError("destination_exists") from None
    except ReceiptError:
        raise
    except OSError:
        raise ReceiptError("receipt_write_failed") from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass

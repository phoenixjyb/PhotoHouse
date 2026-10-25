"""Fresh source binding for the current semantic query policy.

This module is deliberately independent of optional model code. It binds the
policy file, the supported public SigLIP guard, and this verifier's own bytes;
the legacy encoder receipt remains a separate identity.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat


POLICY_VERSION = 3
EXPECTED_POLICY_SOURCE_SHA256 = "cb7aeb07d6e1642de82acd764ad089e46471d1d9cb589e5fd8ab2b4ac6ec4444"
MAX_SOURCE_BYTES = 256 * 1024
_VERSION_LINE = re.compile(rb"(?m)^EXCLUSION_POLICY_VERSION\s*=\s*([0-9]+)\s*$")
_HERE = Path(__file__).absolute()
_SERVER_ROOT = _HERE.parents[3]
_POLICY_PATH = _HERE.with_name("search_policy.py")
_PUBLIC_GUARD_PATH = _SERVER_ROOT / "scripts" / "semantic_siglip.py"


class QueryPolicyUnavailable(RuntimeError):
    """Current policy bytes or a bound guard cannot be verified."""


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_source(path: Path) -> bytes:
    try:
        if not isinstance(path, Path) or not path.is_absolute() or path.resolve(strict=True) != path:
            raise QueryPolicyUnavailable()
        before = path.lstat()
        if (not stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode)
                or before.st_size <= 0 or before.st_size > MAX_SOURCE_BYTES):
            raise QueryPolicyUnavailable()
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise QueryPolicyUnavailable()
            data = stream.read(MAX_SOURCE_BYTES + 1)
            after = os.fstat(stream.fileno())
        final = path.lstat()
        if (len(data) != before.st_size or len(data) > MAX_SOURCE_BYTES
                or _identity(before) != _identity(opened)
                or _identity(opened) != _identity(after)
                or _identity(after) != _identity(final)):
            raise QueryPolicyUnavailable()
        return data
    except QueryPolicyUnavailable:
        raise
    except (OSError, TypeError, ValueError):
        raise QueryPolicyUnavailable() from None


def _canonical_document(policy_version: int, policy_sha256: str,
                        public_guard_sha256: str, verifier_sha256: str) -> dict:
    body = {
        "schema": "photohouse.semantic_query_policy_binding.v1",
        "policy_version": policy_version,
        "policy_source_sha256": policy_sha256,
        "public_guard_source_sha256": public_guard_sha256,
        "binding_verifier_source_sha256": verifier_sha256,
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode("ascii")
    return {**body, "binding_sha256": hashlib.sha256(canonical).hexdigest()}


def _capture(policy_path: Path, guard_path: Path, verifier_path: Path,
             *, expected_policy_sha256: str | None = None) -> dict:
    policy_bytes = _read_source(policy_path)
    matches = _VERSION_LINE.findall(policy_bytes)
    if len(matches) != 1:
        raise QueryPolicyUnavailable()
    try:
        version = int(matches[0])
    except (ValueError, OverflowError):
        raise QueryPolicyUnavailable() from None
    if version != POLICY_VERSION:
        raise QueryPolicyUnavailable()
    policy_sha256 = hashlib.sha256(policy_bytes).hexdigest()
    if expected_policy_sha256 is not None and policy_sha256 != expected_policy_sha256:
        raise QueryPolicyUnavailable()
    guard_sha256 = hashlib.sha256(_read_source(guard_path)).hexdigest()
    verifier_sha256 = hashlib.sha256(_read_source(verifier_path)).hexdigest()
    return _canonical_document(version, policy_sha256, guard_sha256, verifier_sha256)


_PROCESS_BINDING = _capture(_POLICY_PATH, _PUBLIC_GUARD_PATH, _HERE,
                            expected_policy_sha256=EXPECTED_POLICY_SOURCE_SHA256)


def capture_current_query_policy_binding(*, check=lambda: None) -> dict:
    """Return the current immutable policy binding or refuse stale process bytes."""
    check()
    current = _capture(_POLICY_PATH, _PUBLIC_GUARD_PATH, _HERE,
                       expected_policy_sha256=EXPECTED_POLICY_SOURCE_SHA256)
    check()
    if current != _PROCESS_BINDING:
        raise QueryPolicyUnavailable()
    return dict(current)


def verify_query_policy_binding(expected: object, *, check=lambda: None) -> dict:
    """Freshly reread all bound sources and require exact canonical equality."""
    fields = {
        "schema", "policy_version", "policy_source_sha256",
        "public_guard_source_sha256", "binding_verifier_source_sha256",
        "binding_sha256",
    }
    if (type(expected) is not dict
            or any(type(key) is not str for key in expected)
            or set(expected) != fields):
        raise QueryPolicyUnavailable()
    if (type(expected["schema"]) is not str
            or expected["schema"] != "photohouse.semantic_query_policy_binding.v1"
            or type(expected["policy_version"]) is not int
            or expected["policy_version"] != POLICY_VERSION
            or any(type(expected[name]) is not str
                   or re.fullmatch(r"[0-9a-f]{64}", expected[name], re.ASCII) is None
                   for name in fields - {"schema", "policy_version"})):
        raise QueryPolicyUnavailable()
    canonical = _canonical_document(
        expected["policy_version"], expected["policy_source_sha256"],
        expected["public_guard_source_sha256"],
        expected["binding_verifier_source_sha256"],
    )
    if canonical != expected:
        raise QueryPolicyUnavailable()
    current = capture_current_query_policy_binding(check=check)
    if current != expected:
        raise QueryPolicyUnavailable()
    return current

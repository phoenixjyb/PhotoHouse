#!/usr/bin/env python3
"""Verify current files against the source export and ordered public overlays.

This release qualification check is independent of Git history and performs no
builds, network access, provider calls, or writes. Failure output contains only
a fixed reason code and, when applicable, a ledger-declared relative path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = "docs/source-export-manifest.json"
BRAND_PATH = "docs/generic-brand-transform.json"
DOCUMENTATION_PATH = "docs/documentation-transform.json"
FEATURES_PATH = "docs/feature-source-changes.json"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXES = {"server": "server", "android": "clients/android"}
MAX_LEDGER_BYTES = 4 * 1024 * 1024


class VerificationError(ValueError):
    """A fixed safe reason and optional manifest-relative path."""

    def __init__(self, reason: str, path: str | None = None):
        self.reason = reason
        self.path = path
        super().__init__(reason)


def _fail(reason: str, path: str | None = None) -> None:
    raise VerificationError(reason, path)


def _relative_path(value: object) -> str:
    if (type(value) is not str or not value or "\\" in value or "\x00" in value
            or any(ord(ch) < 32 for ch in value) or value.startswith("/")
            or re.match(r"^[A-Za-z]:", value)):
        _fail("unsafe_path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        _fail("unsafe_path")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        _fail("unsafe_path")
    return value


def _digest_field(record: dict[str, Any], key: str, path: str) -> str:
    value = record.get(key)
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        _fail("invalid_digest", path)
    return value


def _candidate_digest(record: dict[str, Any], path: str) -> str:
    """Read the public candidate hash, never source_sha256."""
    key = "candidate_sha256" if "candidate_sha256" in record else "sha256"
    return _digest_field(record, key, path)


def _check_file(root: Path, relative: str) -> str:
    """Hash one path while refusing symlinks, escapes and non-regular files."""
    rel = _relative_path(relative)
    root = Path(root)
    try:
        root_stat = root.lstat()
    except OSError:
        _fail("root_unavailable")
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        _fail("root_not_directory")

    path = root
    try:
        for index, part in enumerate(PurePosixPath(rel).parts):
            path = path / part
            item = path.lstat()
            if stat.S_ISLNK(item.st_mode):
                _fail("symlink_refused", rel)
            if index < len(PurePosixPath(rel).parts) - 1 and not stat.S_ISDIR(item.st_mode):
                _fail("path_component_not_directory", rel)
        before = path.lstat()
    except VerificationError:
        raise
    except FileNotFoundError:
        _fail("file_missing", rel)
    except OSError:
        _fail("file_unreadable", rel)
    if not stat.S_ISREG(before.st_mode):
        _fail("not_regular_file", rel)

    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        digest = hashlib.sha256()
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
                _fail("file_changed", rel)
            while True:
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
            after_fd = os.fstat(stream.fileno())
        after_path = path.lstat()
    except VerificationError:
        raise
    except OSError:
        _fail("file_unreadable", rel)
    if (_identity(after_fd) != _identity(before) or _identity(after_path) != _identity(before)
            or stat.S_ISLNK(after_path.st_mode)):
        _fail("file_changed", rel)
    return digest.hexdigest()


def _identity(item: os.stat_result) -> tuple[int, int, int, int]:
    return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns


def _load_ledger(root: Path, relative: str) -> Any:
    rel = _relative_path(relative)
    root = Path(root)
    try:
        if stat.S_ISLNK(root.lstat().st_mode) or not stat.S_ISDIR(root.lstat().st_mode):
            _fail("root_not_directory")
        path = root
        parts = PurePosixPath(rel).parts
        for index, part in enumerate(parts):
            path = path / part
            item = path.lstat()
            if stat.S_ISLNK(item.st_mode):
                _fail("symlink_refused", rel)
            if index < len(parts) - 1 and not stat.S_ISDIR(item.st_mode):
                _fail("path_component_not_directory", rel)
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            _fail("ledger_shape_invalid", rel)
        if before.st_size > MAX_LEDGER_BYTES:
            _fail("ledger_too_large", rel)
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if _identity(opened) != _identity(before) or not stat.S_ISREG(opened.st_mode):
                _fail("file_changed", rel)
            raw = stream.read(MAX_LEDGER_BYTES + 1)
            after_fd = os.fstat(stream.fileno())
        after_path = path.lstat()
        if len(raw) > MAX_LEDGER_BYTES:
            _fail("ledger_too_large", rel)
        if (_identity(after_fd) != _identity(before) or _identity(after_path) != _identity(before)
                or stat.S_ISLNK(after_path.st_mode)):
            _fail("file_changed", rel)
        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    _fail("duplicate_json_key", rel)
                result[key] = value
            return result
        return json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=unique_object)
    except VerificationError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        _fail("ledger_unreadable", rel)


def _validate_document(doc: object, key: str, ledger_path: str) -> list[Any]:
    if type(doc) is not dict or type(doc.get(key)) is not list:
        _fail("ledger_shape_invalid", ledger_path)
    return doc[key]


def _transform_records(doc: object, ledger_path: str) -> list[Any]:
    return _validate_document(doc, "transformations", ledger_path)


def _set_expected(expected: dict[str, str], path: str, digest: str) -> None:
    expected[path] = digest


def _apply_transforms(expected: dict[str, str], records: list[Any], ledger_path: str,
                      seen_all: set[str]) -> int:
    local_seen: set[str] = set()
    for record in records:
        if type(record) is not dict:
            _fail("transform_shape_invalid", ledger_path)
        path = _relative_path(record.get("path"))
        if path in local_seen or path in seen_all:
            _fail("duplicate_transform_path", path)
        local_seen.add(path)
        seen_all.add(path)
        operation = record.get("operation")
        if operation not in ("replace", "add") or type(operation) is not str:
            _fail("transform_operation_invalid", path)
        before = record.get("before_sha256")
        if before is not None:
            if type(before) is not str or _DIGEST.fullmatch(before) is None:
                _fail("invalid_digest", path)
        if operation == "replace":
            if path not in expected:
                _fail("replace_target_missing", path)
            if before is not None and before != expected[path]:
                _fail("before_digest_mismatch", path)
            after_key = "candidate_sha256" if "candidate_sha256" in record else "after_sha256"
            _set_expected(expected, path, _digest_field(record, after_key, path))
        else:
            if before is not None:
                _fail("add_has_before_digest", path)
            if path in expected:
                _fail("add_target_exists", path)
            _set_expected(expected, path, _candidate_digest(record, path))
    return len(records)


def _apply_feature_overlays(expected: dict[str, str], doc: object, ledger_path: str) -> tuple[int, int]:
    changes = _validate_document(doc, "changes", ledger_path)
    feature_names: set[str] = set()
    file_count = 0
    for feature in changes:
        if type(feature) is not dict or type(feature.get("feature")) is not str or not feature["feature"]:
            _fail("feature_shape_invalid", ledger_path)
        if feature["feature"] in feature_names:
            _fail("duplicate_feature", ledger_path)
        feature_names.add(feature["feature"])
        files = feature.get("files")
        if type(files) is not list:
            _fail("feature_files_invalid", ledger_path)
        local_seen: set[str] = set()
        for record in files:
            if type(record) is not dict:
                _fail("feature_file_invalid", ledger_path)
            path = _relative_path(record.get("path"))
            if path in local_seen:
                _fail("duplicate_overlay_path", path)
            local_seen.add(path)
            has_before = "before_sha256" in record
            before = record.get("before_sha256")
            if has_before and before is not None:
                if type(before) is not str or _DIGEST.fullmatch(before) is None:
                    _fail("invalid_digest", path)
                if path not in expected or expected[path] != before:
                    _fail("before_digest_mismatch", path)
            elif has_before and path in expected:
                _fail("overlay_add_target_exists", path)
            _set_expected(expected, path, _candidate_digest(record, path))
            file_count += 1
    return len(feature_names), file_count


def verify_current_source(root: Path, baseline_manifest: object, brand_transform: object,
                          documentation_transform: object, feature_changes: object) -> dict[str, object]:
    """Verify a candidate tree against supplied ledgers without Git or I/O side effects."""
    if type(baseline_manifest) is not dict:
        _fail("baseline_shape_invalid", BASELINE_PATH)
    if baseline_manifest.get("historical_git_imported") is not False:
        _fail("historical_git_imported", BASELINE_PATH)
    exported = _validate_document(baseline_manifest, "exported_files", BASELINE_PATH)
    expected: dict[str, str] = {}
    for record in exported:
        if type(record) is not dict:
            _fail("baseline_record_invalid", BASELINE_PATH)
        repo = record.get("repo")
        if type(repo) is not str or repo not in _PREFIXES:
            _fail("unknown_repository", BASELINE_PATH)
        source_path = _relative_path(record.get("source_path"))
        relative = _relative_path(_PREFIXES[repo] + "/" + source_path)
        if relative in expected:
            _fail("duplicate_baseline_path", relative)
        expected[relative] = _candidate_digest(record, relative)

    transform_paths: set[str] = set()
    transform_count = 0
    for document, ledger_path in ((brand_transform, BRAND_PATH),
                                   (documentation_transform, DOCUMENTATION_PATH)):
        if type(document) is not dict:
            _fail("ledger_shape_invalid", ledger_path)
        transform_count += _apply_transforms(expected, _transform_records(document, ledger_path),
                                             ledger_path, transform_paths)
    feature_count, feature_file_count = _apply_feature_overlays(
        expected, feature_changes, FEATURES_PATH)

    for relative, wanted in expected.items():
        actual = _check_file(Path(root), relative)
        if actual != wanted:
            _fail("content_digest_mismatch", relative)
    return {
        "status": "verified",
        "baseline_files": len(exported),
        "public_transform_records": transform_count,
        "feature_overlays": feature_count,
        "feature_file_records": feature_file_count,
        "current_files_verified": len(expected),
        "historical_git_imported": False,
    }


def verify_tree(root: Path = ROOT) -> dict[str, object]:
    root = Path(root)
    return verify_current_source(
        root,
        _load_ledger(root, BASELINE_PATH),
        _load_ledger(root, BRAND_PATH),
        _load_ledger(root, DOCUMENTATION_PATH),
        _load_ledger(root, FEATURES_PATH),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="source candidate root")
    args = parser.parse_args(argv)
    try:
        report = verify_tree(args.root)
    except VerificationError as exc:
        safe = {"status": "refused", "reason": exc.reason}
        if exc.path is not None:
            safe["path"] = exc.path
        print(json.dumps(safe, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

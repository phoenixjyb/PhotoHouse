#!/usr/bin/env python3
"""Create a verified ZIP of clean, tracked source without Git history."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from typing import Callable

if __package__:
    from .verify_current_source import VerificationError, verify_tree
else:  # script execution places this directory, rather than its parent, on sys.path
    from verify_current_source import VerificationError, verify_tree

ROOT = Path(__file__).resolve().parents[1]
_OID = re.compile(rb"[0-9a-f]{40,64}\Z")
_CRLF_PATH = "clients/android/android/gradlew.bat"
_ARCHIVE_NAME = "source.zip"
_REPORT_NAME = "verification.json"


class PackageError(ValueError):
    """Safe packaging refusal with an optional repository-relative path."""

    def __init__(self, reason: str, path: str | None = None):
        self.reason = reason
        self.path = path
        super().__init__(reason)


def _git(root: Path, args: list[str], *, input_bytes: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(
            ["git", *args], cwd=root, input=input_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except OSError:
        raise PackageError("git_unavailable") from None
    if result.returncode != 0:
        raise PackageError("git_command_failed")
    return result.stdout


def _safe_member(value: str) -> str:
    if (not value or "\\" in value or "\x00" in value
            or any(ord(character) < 32 for character in value)
            or value.startswith("/") or re.match(r"^[A-Za-z]:", value)):
        raise PackageError("unsafe_archive_path")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise PackageError("unsafe_archive_path")
    if PurePosixPath(value).is_absolute() or PurePosixPath(value).as_posix() != value:
        raise PackageError("unsafe_archive_path")
    return value


def _identity(item: os.stat_result) -> tuple[int, int, int, int]:
    return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns


def _tracked(root: Path) -> list[dict[str, object]]:
    raw = _git(root, ["ls-files", "--stage", "-z"])
    records: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            mode_raw, oid, stage_raw = metadata.split(b" ")
            path = raw_path.decode("utf-8", "strict")
            mode = mode_raw.decode("ascii", "strict")
            stage = int(stage_raw)
        except (ValueError, UnicodeDecodeError):
            raise PackageError("tracked_index_invalid") from None
        _safe_member(path)
        if path in seen:
            raise PackageError("duplicate_tracked_path", path)
        seen.add(path)
        if stage != 0:
            raise PackageError("index_conflict", path)
        if mode not in ("100644", "100755") or not _OID.fullmatch(oid):
            raise PackageError("tracked_file_type_refused", path)
        records.append({"path": path, "mode": mode, "oid": oid.decode("ascii")})
    if not records:
        raise PackageError("tracked_files_empty")
    records.sort(key=lambda item: str(item["path"]).encode("utf-8"))
    return records


def _blob_contents(root: Path, records: list[dict[str, object]]) -> dict[str, bytes]:
    oids = [str(record["oid"]) for record in records]
    raw = _git(root, ["cat-file", "--batch"], input_bytes=("\n".join(oids) + "\n").encode("ascii"))
    position = 0
    result: dict[str, bytes] = {}
    for expected_oid in oids:
        newline = raw.find(b"\n", position)
        if newline < 0:
            raise PackageError("git_blob_response_invalid")
        header = raw[position:newline].split(b" ")
        if len(header) != 3 or header[0].decode("ascii", "ignore") != expected_oid or header[1] != b"blob":
            raise PackageError("git_blob_response_invalid")
        try:
            size = int(header[2])
        except ValueError:
            raise PackageError("git_blob_response_invalid") from None
        position = newline + 1
        end = position + size
        if size < 0 or end >= len(raw) or raw[end:end + 1] != b"\n":
            raise PackageError("git_blob_response_invalid")
        result[expected_oid] = raw[position:end]
        position = end + 1
    if position != len(raw):
        raise PackageError("git_blob_response_invalid")
    return result


def _read_worktree_file(root: Path, relative: str) -> tuple[bytes, tuple[int, int, int, int]]:
    current = root
    parts = PurePosixPath(relative).parts
    try:
        for index, part in enumerate(parts):
            current = current / part
            before = current.lstat()
            if stat.S_ISLNK(before.st_mode):
                raise PackageError("symlink_refused", relative)
            if index < len(parts) - 1:
                if not stat.S_ISDIR(before.st_mode):
                    raise PackageError("path_component_not_directory", relative)
                continue
            if not stat.S_ISREG(before.st_mode):
                raise PackageError("not_regular_file", relative)
            fd = os.open(current, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
            with os.fdopen(fd, "rb") as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(before):
                    raise PackageError("file_changed", relative)
                data = stream.read()
                after_fd = os.fstat(stream.fileno())
            after_path = current.lstat()
            if (_identity(after_fd) != _identity(before)
                    or _identity(after_path) != _identity(before)
                    or stat.S_ISLNK(after_path.st_mode)):
                raise PackageError("file_changed", relative)
            return data, _identity(after_path)
    except PackageError:
        raise
    except OSError:
        raise PackageError("file_unreadable", relative) from None
    raise PackageError("file_missing", relative)


def _has_declared_crlf(root: Path, relative: str) -> bool:
    raw = _git(root, ["check-attr", "-z", "text", "eol", "--", relative])
    fields = raw.split(b"\0")
    if fields and fields[-1] == b"":
        fields.pop()
    if len(fields) != 6:
        raise PackageError("git_attribute_response_invalid", relative)
    values = {}
    for index in (1, 4):
        if fields[index - 1].decode("utf-8", "strict") != relative:
            raise PackageError("git_attribute_response_invalid", relative)
        values[fields[index].decode("ascii", "strict")] = fields[index + 1].decode("ascii", "strict")
    return values == {"text": "set", "eol": "crlf"}


def _working_contents(root: Path, records: list[dict[str, object]], blobs: dict[str, bytes]) -> tuple[dict[str, bytes], list[dict[str, str]]]:
    working: dict[str, bytes] = {}
    eol_records: list[dict[str, str]] = []
    for record in records:
        path, oid = str(record["path"]), str(record["oid"])
        data, _identity_value = _read_worktree_file(root, path)
        blob = blobs[oid]
        if data != blob:
            allowed = (path == _CRLF_PATH and _has_declared_crlf(root, path)
                       and b"\r" not in blob and data == blob.replace(b"\n", b"\r\n"))
            if not allowed:
                raise PackageError("working_tree_blob_mismatch", path)
            eol_records.append({"path": path, "git_blob_eol": "LF", "zip_eol": "CRLF",
                                "declared_attribute": "text eol=crlf"})
        working[path] = data
    return working, eol_records


def _output_target(root: Path, output_dir: Path) -> tuple[Path, Path]:
    if not output_dir.is_absolute():
        raise PackageError("output_path_must_be_absolute")
    try:
        parent = output_dir.parent.resolve(strict=True)
    except OSError:
        raise PackageError("output_parent_unavailable") from None
    if not parent.is_dir():
        raise PackageError("output_parent_not_directory")
    target = parent / output_dir.name
    if target.exists() or target.is_symlink():
        raise PackageError("output_must_be_absent")
    if target == root or root in target.parents:
        raise PackageError("output_inside_repository")
    return target, parent


def _ensure_clean(root: Path) -> None:
    status = _git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all"])
    if status:
        raise PackageError("dirty_worktree")


def _head(root: Path) -> str:
    value = _git(root, ["rev-parse", "--verify", "HEAD"]).decode("ascii", "strict").strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", value):
        raise PackageError("head_invalid")
    return value


def _git_archive(root: Path, head: str, path: Path) -> None:
    _git(root, ["archive", "--format=zip", f"--output={path}", head])


def _archive_members(archive: zipfile.ZipFile, expected: set[str]) -> dict[str, zipfile.ZipInfo]:
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(names) != len(set(names)):
        raise PackageError("duplicate_archive_member")
    files: dict[str, zipfile.ZipInfo] = {}
    for info in infos:
        name = info.filename
        directory = info.is_dir()
        clean_name = name[:-1] if directory and name.endswith("/") else name
        _safe_member(clean_name)
        if directory:
            if clean_name in expected or not any(path.startswith(clean_name + "/") for path in expected):
                raise PackageError("unexpected_archive_directory", clean_name)
            continue
        if name in files:
            raise PackageError("duplicate_archive_member", name)
        if info.flag_bits & 0x1:
            raise PackageError("archive_member_type_refused", name)
        files[name] = info
    if set(files) != expected:
        raise PackageError("archive_path_set_mismatch")
    return files


def _verified_zip_bytes(data: bytes, records: list[dict[str, object]],
                        blobs: dict[str, bytes], working: dict[str, bytes]) -> None:
    expected = {str(record["path"]) for record in records}
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            members = _archive_members(archive, expected)
            bad = archive.testzip()
            if bad is not None:
                raise PackageError("archive_crc_failed", bad)
            for record in records:
                path, oid = str(record["path"]), str(record["oid"])
                payload = archive.read(members[path])
                if payload != working[path]:
                    raise PackageError("archive_content_mismatch", path)
                expected_permissions = 0o755 if record["mode"] == "100755" else 0o644
                archive_mode = members[path].external_attr >> 16
                if (stat.S_IFMT(archive_mode) != stat.S_IFREG
                        or stat.S_IMODE(archive_mode) != expected_permissions):
                    raise PackageError("archive_mode_mismatch", path)
                if payload != blobs[oid]:
                    allowed = (path == _CRLF_PATH and payload == blobs[oid].replace(b"\n", b"\r\n"))
                    if not allowed:
                        raise PackageError("archive_blob_mismatch", path)
    except PackageError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError):
        raise PackageError("archive_invalid") from None


def package_source(root: Path, output_dir: Path, *,
                   _verifier: Callable[[Path], dict[str, object]] | None = None) -> dict[str, object]:
    """Package a clean committed tree; `_verifier` is an internal test seam.

    The CLI always supplies the repository's mandatory imported-source verifier.
    """
    try:
        root = Path(root).resolve(strict=True)
        output_dir = Path(output_dir)
        actual_root = Path(_git(root, ["rev-parse", "--show-toplevel"]).decode("utf-8", "strict").strip()).resolve(strict=True)
        if actual_root != root:
            raise PackageError("root_not_repository_root")
        target, parent = _output_target(root, output_dir)
        _ensure_clean(root)
        head = _head(root)
        records = _tracked(root)
        verify = _verifier or verify_tree
        try:
            source_report = verify(root)
        except VerificationError as exc:
            raise PackageError("source_verification_failed", exc.path) from None
        except PackageError:
            raise
        except Exception:
            raise PackageError("source_verification_failed") from None
        if type(source_report) is not dict or source_report.get("status") != "verified":
            raise PackageError("source_verification_failed")
        _ensure_clean(root)
        if _head(root) != head:
            raise PackageError("head_changed")
        blobs = _blob_contents(root, records)
        working, eol_records = _working_contents(root, records, blobs)

        stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.package-", dir=parent))
        try:
            archive_path = stage / "git-archive.zip"
            _git_archive(root, head, archive_path)
            archive_data = archive_path.read_bytes()
            _verified_git_archive(archive_data, records, blobs, eol_records)
            source_path = stage / _ARCHIVE_NAME
            _rewrite_archive(archive_data, source_path, records, working)
            final_bytes = source_path.read_bytes()
            _verified_zip_bytes(final_bytes, records, blobs, working)
            files = []
            for record in records:
                path = str(record["path"])
                payload = working[path]
                files.append({"path": path, "git_mode": str(record["mode"]),
                              "git_blob": str(record["oid"]), "bytes": len(payload),
                              "sha256": hashlib.sha256(payload).hexdigest()})
            report = {
                "status": "verified",
                "head": head,
                "archive": _ARCHIVE_NAME,
                "archive_bytes": len(final_bytes),
                "archive_sha256": hashlib.sha256(final_bytes).hexdigest(),
                "tracked_file_count": len(records),
                "tracked_files": files,
                "eol_serializations": eol_records,
                "imported_source_verification": source_report,
            }
            _ensure_clean(root)
            if _head(root) != head:
                raise PackageError("head_changed")
            _recheck_working_tree(root, records, blobs, working, eol_records)
            archive_path.unlink()
            _publish_output(stage / _ARCHIVE_NAME, target, report)
            shutil.rmtree(stage, ignore_errors=True)
            stage = None  # type: ignore[assignment]
            return report
        finally:
            if stage is not None:
                shutil.rmtree(stage, ignore_errors=True)
    except PackageError:
        raise
    except (OSError, UnicodeError, zipfile.BadZipFile):
        raise PackageError("packaging_failed") from None


def _verified_git_archive(data: bytes, records: list[dict[str, object]],
                          blobs: dict[str, bytes],
                          eol_records: list[dict[str, str]]) -> None:
    expected = {str(record["path"]) for record in records}
    crlf_paths = {item["path"] for item in eol_records}
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(data), "r") as archive:
            members = _archive_members(archive, expected)
            bad = archive.testzip()
            if bad is not None:
                raise PackageError("archive_crc_failed", bad)
            for record in records:
                path, oid = str(record["path"]), str(record["oid"])
                payload = archive.read(members[path])
                expected_payload = blobs[oid]
                if path in crlf_paths:
                    expected_payload = expected_payload.replace(b"\n", b"\r\n")
                if payload != expected_payload:
                    raise PackageError("git_archive_blob_mismatch", path)
    except PackageError:
        raise
    except (OSError, zipfile.BadZipFile, RuntimeError):
        raise PackageError("archive_invalid") from None


def _rewrite_archive(data: bytes, destination: Path, records: list[dict[str, object]],
                     working: dict[str, bytes]) -> None:
    import io
    expected = {str(record["path"]) for record in records}
    with zipfile.ZipFile(io.BytesIO(data), "r") as source, zipfile.ZipFile(destination, "w") as output:
        members = _archive_members(source, expected)
        for record in records:
            path = str(record["path"])
            info = copy.copy(members[path])
            permissions = 0o755 if record["mode"] == "100755" else 0o644
            info.external_attr = (stat.S_IFREG | permissions) << 16 | (info.external_attr & 0xFFFF)
            output.writestr(info, working[path])


def _write_json(path: Path, value: dict[str, object]) -> None:
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    identity = None
    try:
        with path.open("xb") as stream:
            opened = os.fstat(stream.fileno())
            identity = (opened.st_dev, opened.st_ino)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        if identity is not None:
            _unlink_if_same(path, identity)
        raise


def _entry_identity(path: Path) -> tuple[int, int]:
    item = path.lstat()
    return item.st_dev, item.st_ino


def _unlink_if_same(path: Path, identity: tuple[int, int]) -> None:
    try:
        if _entry_identity(path) == identity:
            path.unlink()
    except FileNotFoundError:
        pass


def _publish_output(source_archive: Path, target: Path,
                    report: dict[str, object]) -> None:
    """Claim an absent destination exclusively; manifest marks completion."""
    try:
        target.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError:
        raise PackageError("output_must_be_absent") from None
    directory_identity = _entry_identity(target)
    archive_target = target / _ARCHIVE_NAME
    archive_identity = None
    try:
        os.link(source_archive, archive_target)
        archive_identity = _entry_identity(archive_target)
        _write_json(target / _REPORT_NAME, report)
    except BaseException:
        if archive_identity is not None:
            _unlink_if_same(archive_target, archive_identity)
        try:
            if _entry_identity(target) == directory_identity:
                target.rmdir()  # succeeds only if no foreign entries remain
        except OSError:
            pass
        raise


def _recheck_working_tree(root: Path, records: list[dict[str, object]],
                          blobs: dict[str, bytes], working: dict[str, bytes],
                          eol_records: list[dict[str, str]]) -> None:
    allowed = {item["path"] for item in eol_records}
    for record in records:
        path, oid = str(record["path"]), str(record["oid"])
        current, _identity_value = _read_worktree_file(root, path)
        if current != working[path]:
            raise PackageError("working_tree_changed", path)
        if current != blobs[oid] and path not in allowed:
            raise PackageError("working_tree_blob_mismatch", path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", type=Path, help="absolute absent output directory outside the repository")
    args = parser.parse_args(argv)
    try:
        report = package_source(ROOT, args.output_dir)
    except PackageError as exc:
        result: dict[str, str] = {"status": "refused", "reason": exc.reason}
        if exc.path is not None:
            result["path"] = exc.path
        print(json.dumps(result, sort_keys=True))
        return 1
    summary = {key: report[key] for key in ("status", "head", "archive_sha256", "tracked_file_count")}
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

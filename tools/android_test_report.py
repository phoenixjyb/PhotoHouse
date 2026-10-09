#!/usr/bin/env python3
"""Read existing Gradle unit-test reports without running a build or tests."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("core", "protocol", "live-core", "home-core", "playback-core",
           "story-fixture-core", "connected", "tv")
MAX_REPORTS = 512
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 32 * 1024 * 1024
FIELDS = ("tests", "failures", "errors", "skipped")


class ReportError(ValueError):
    """A fixed reason code; report contents and local paths are never printed."""


def directory(path: Path) -> bool:
    try:
        item = path.lstat()
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(item.st_mode) or not stat.S_ISDIR(item.st_mode):
        raise ReportError("report_directory_not_regular")
    return True


def read_report(path: Path) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_REPORT_BYTES:
        raise ReportError("report_file_refused")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        raw = stream.read(MAX_REPORT_BYTES + 1)
        after = os.fstat(stream.fileno())
    identity = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    if (identity(before) != identity(opened) or identity(before) != identity(after)
            or identity(before) != identity(path.lstat()) or len(raw) > MAX_REPORT_BYTES):
        raise ReportError("report_changed_or_oversized")
    return raw


def counts(raw: bytes) -> dict[str, int]:
    # Gradle writes ordinary UTF-8 XML. Refuse declarations with entity expansion.
    if b"\x00" in raw or re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.IGNORECASE):
        raise ReportError("report_xml_declaration_refused")
    try:
        suite = ET.fromstring(raw)
    except ET.ParseError:
        raise ReportError("report_xml_invalid") from None
    if suite.tag != "testsuite":
        raise ReportError("report_suite_invalid")
    result = {}
    for key in FIELDS:
        value = suite.get(key)
        if value is None or re.fullmatch(r"(?:0|[1-9][0-9]{0,5})", value) is None:
            raise ReportError("report_count_invalid")
        result[key] = int(value)
    cases = suite.findall("testcase")
    observed = {"tests": len(cases), **{
        key: sum(case.find(tag) is not None for case in cases)
        for key, tag in (("failures", "failure"), ("errors", "error"), ("skipped", "skipped"))
    }}
    if result != observed or sum(result[key] for key in FIELDS[1:]) > result["tests"]:
        raise ReportError("report_count_mismatch")
    return result


def collect(project: Path) -> dict:
    project = Path(project)
    if not directory(project):
        raise ReportError("project_missing")
    rows, missing, reports_read, bytes_read = [], [], 0, 0
    for module in MODULES:
        task = "testDebugUnitTest" if module in ("connected", "tv") else "test"
        location = project
        available = True
        for part in (module, "build", "test-results", task):
            location = location / part
            if not directory(location):
                available = False
                break
        files = sorted(location.glob("TEST-*.xml")) if available else []
        totals = dict.fromkeys(FIELDS, 0)
        if not files and module != "protocol":
            missing.append(module)
        for path in files:
            reports_read += 1
            if reports_read > MAX_REPORTS:
                raise ReportError("report_count_limit")
            raw = read_report(path)
            bytes_read += len(raw)
            if bytes_read > MAX_TOTAL_BYTES:
                raise ReportError("report_bytes_limit")
            for key, value in counts(raw).items():
                totals[key] += value
        rows.append({"module": module, "report_files": len(files),
                     "state": "reported" if files else "no_report", **totals})
    return {"kind": "existing_gradle_unit_report_inventory", "read_only": True,
            "tests_run_by_this_tool": False, "source_revision_bound": False,
            "artifact_or_device_qualified": False,
            "complete_required_reports": not missing, "missing_modules": missing,
            "optional_report_modules": ["protocol"], "modules": rows,
            "totals": {key: sum(row[key] for row in rows) for key in FIELDS}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path,
                        default=ROOT / "clients" / "android" / "android")
    args = parser.parse_args()
    try:
        report = collect(args.project_root)
    except (ReportError, OSError) as error:
        reason = str(error) if isinstance(error, ReportError) else "report_io_unavailable"
        print(json.dumps({"kind": "existing_gradle_unit_report_inventory", "status": "unavailable", "reason": reason}))
        return 1
    print(json.dumps(report, indent=2))
    return 0 if report["complete_required_reports"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

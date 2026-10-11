#!/usr/bin/env python3
"""Summarize an existing AndroidJUnitRunner ``am instrument -w -r`` log.

This tool reads a saved log only. It does not invoke ADB or infer which APK,
device, source revision, or provider produced the output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

MAX_LOG_BYTES = 8 * 1024 * 1024
NUMTESTS = re.compile(r"(?:0|[1-9][0-9]{0,6})\Z")
CURRENT = re.compile(r"[1-9][0-9]{0,6}\Z")
OK_SUMMARY = re.compile(r"OK \(([1-9][0-9]{0,6}) tests?\)\Z")
STATUS_FIELD = re.compile(r"INSTRUMENTATION_STATUS:\s*([A-Za-z0-9_]+)=(.*?)\s*\Z")
STATUS_CODE = re.compile(r"INSTRUMENTATION_STATUS_CODE:\s*(-?[0-9]{1,3})\s*\Z")
RESULT_CODE = re.compile(r"INSTRUMENTATION_CODE:\s*(-?[0-9]{1,3})\s*\Z")


def _result(reason: str, **counts: int | None) -> dict:
    result = {"kind": "existing_android_instrumentation_run", "status": "unavailable",
              "complete": False, "reason": reason}
    for name in ("tests", "passed", "failures", "errors", "skipped", "unknown_statuses"):
        value = counts.get(name)
        if value is not None:
            result[name] = value
    return result


def summarize(raw: bytes) -> dict:
    """Return a privacy-safe result; never include names or raw log text."""
    if not raw or len(raw) > MAX_LOG_BYTES or b"\x00" in raw:
        return _result("log_empty_or_invalid")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return _result("log_encoding_invalid")
    if not text.endswith("\n"):
        return _result("log_truncated")

    lines = text.splitlines()
    events: list[tuple[int, dict[str, list[str]]]] = []
    fields: dict[str, list[str]] = {}
    result_codes: list[int] = []
    ok_summaries: list[tuple[int, int]] = []
    failures_marker = False
    aborted_marker = False
    unknown_statuses = 0
    terminal_line_index = -1

    for index, line in enumerate(lines):
        if line.startswith("INSTRUMENTATION_STATUS_CODE"):
            status = STATUS_CODE.fullmatch(line)
            if status is None:
                return _result("status_control_invalid")
            events.append((int(status.group(1)), fields))
            fields = {}
        elif line.startswith("INSTRUMENTATION_CODE"):
            result = RESULT_CODE.fullmatch(line)
            if result is None:
                return _result("terminal_control_invalid")
            result_codes.append(int(result.group(1)))
            terminal_line_index = index
        elif line.startswith("INSTRUMENTATION_STATUS"):
            field = STATUS_FIELD.fullmatch(line)
            if field is None:
                return _result("status_field_invalid")
            key, value = field.groups()
            fields.setdefault(key, []).append(value)
        summary = OK_SUMMARY.fullmatch(line.strip())
        if summary:
            ok_summaries.append((int(summary.group(1)), index))
        if "FAILURES!!!" in line:
            failures_marker = True
        if ("INSTRUMENTATION_FAILED" in line or
                line.startswith("INSTRUMENTATION_RESULT: shortMsg=") or
                line.startswith("INSTRUMENTATION_RESULT: error=")):
            aborted_marker = True

    if fields:
        return _result("status_field_unpaired")
    counts = {"tests": None, "passed": 0, "failures": 0, "errors": 0,
              "skipped": 0, "unknown_statuses": 0}
    required = ("current", "numtests", "id", "test", "class")
    if not events or any(any(len(event_fields.get(key, ())) != 1 for key in required)
                         for _, event_fields in events):
        return _result("test_status_fields_missing_or_duplicate")
    numtests_values = [event_fields["numtests"][0] for _, event_fields in events]
    if any(NUMTESTS.fullmatch(value) is None for value in numtests_values):
        return _result("numtests_missing_or_invalid")
    unique_totals = {int(value) for value in numtests_values}
    if len(unique_totals) != 1:
        return _result("numtests_conflict")
    total = unique_totals.pop()
    counts["tests"] = total
    if total <= 0:
        return _result("zero_tests", **counts)

    if len(events) != 2 * total:
        return _result("test_status_count_mismatch", **counts)
    completions: list[int] = []
    for test_index in range(total):
        start_code, start_fields = events[2 * test_index]
        end_code, end_fields = events[2 * test_index + 1]
        if start_code != 1 or end_code == 1:
            return _result("test_status_order_invalid", **counts)
        if any(start_fields[key] != end_fields[key] for key in required):
            return _result("test_status_pair_mismatch", **counts)
        if start_fields["id"][0] != "AndroidJUnitRunner":
            return _result("runner_id_invalid", **counts)
        current_value = start_fields["current"][0]
        if CURRENT.fullmatch(current_value) is None or int(current_value) != test_index + 1:
            return _result("test_current_mismatch", **counts)
        completions.append(end_code)

    unknown_statuses = sum(code not in (0, -1, -2, -3, -4) for code in completions)
    counts.update({
        "passed": completions.count(0),
        "failures": completions.count(-2),
        "errors": completions.count(-1),
        "skipped": completions.count(-3) + completions.count(-4),
        "unknown_statuses": unknown_statuses,
    })
    if unknown_statuses:
        return _result("unknown_test_status", **counts)
    if counts["skipped"]:
        return _result("test_skipped_or_assumption_failed", **counts)
    if counts["failures"] or counts["errors"] or failures_marker:
        return _result("test_failure_or_error", **counts)
    if aborted_marker:
        return _result("instrumentation_aborted", **counts)
    if len(result_codes) != 1 or result_codes[0] != -1 or terminal_line_index != len(lines) - 1:
        return _result("instrumentation_terminal_missing_or_conflicting", **counts)
    if len(ok_summaries) != 1 or ok_summaries[0][1] >= terminal_line_index:
        return _result("summary_missing_or_conflicting", **counts)
    if any(line.strip() for line in lines[ok_summaries[0][1] + 1:terminal_line_index]):
        return _result("summary_missing_or_conflicting", **counts)
    if ok_summaries[0][0] != total:
        return _result("summary_count_mismatch", **counts)
    if counts["passed"] != total:
        return _result("test_status_count_mismatch", **counts)

    return {"kind": "existing_android_instrumentation_run", "status": "passed",
            "complete": True, "tests": total, "passed": total, "failures": 0,
            "errors": 0, "skipped": 0, "unknown_statuses": 0,
            "instrumentation_code": -1}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="existing am instrument output log")
    args = parser.parse_args(argv)
    try:
        if args.log.is_symlink() or not args.log.is_file() or args.log.stat().st_size > MAX_LOG_BYTES:
            result = _result("log_file_refused")
        else:
            with args.log.open("rb") as stream:
                raw = stream.read(MAX_LOG_BYTES + 1)
            result = summarize(raw)
    except OSError:
        result = _result("log_io_unavailable")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Plan safe recovery for a sanitized bad-video checkpoint snapshot.

This tool is deliberately offline: it reads bounded JSON from stdin or a file,
writes a path-free plan to stdout, and never opens media, a database, or the
network. Snapshot schema is {"rows": [{"id", "reason",
"source_size", "header_hex"?}, ...]}.

Source provenance: imported from the clean legacy source at commit
84b772831c102b96280e3e7423647ff4787794d9, file
scripts/plan_bad_video_recovery.py, SHA-256
8ca6446de26b92c9259e076b77957a396b5f5b4d5de62b157d3488df60e0309f.
The import preserves the path-free planner classifications and adds bounded,
strict JSON intake and fixed privacy-safe CLI errors.
"""
import json
import sys

REASONS = {"source_empty", "preparation_failed", "source_decode_failed"}
ROW_KEYS = {"id", "reason", "source_size", "header_hex"}
MAX_SNAPSHOT_BYTES = 1_048_576
MAX_ROWS = 5_000
MAX_SQLITE_INTEGER = (1 << 63) - 1
APPLEDOUBLE_MAGIC = bytes.fromhex("00051607")
APPLEDOUBLE_V2 = bytes.fromhex("00020000")


class DuplicateJSONKey(ValueError):
    """Raised when a JSON object repeats a key."""


class InvalidJSONConstant(ValueError):
    """Raised for non-standard JSON constants such as NaN or Infinity."""


class SnapshotTooLarge(ValueError):
    """Raised when bounded snapshot input exceeds the accepted size."""


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKey
        result[key] = value
    return result


def _reject_json_constant(_value):
    raise InvalidJSONConstant


def read_snapshot(stream):
    """Read and decode one bounded UTF-8 JSON snapshot."""
    raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    elif not isinstance(raw, bytes):
        raise ValueError("invalid_input")
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise SnapshotTooLarge
    text = raw.decode("utf-8")
    return json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_json_constant,
    )


def classify(row):
    reason = row.get("reason")
    size = row.get("source_size")
    header = row.get("header_hex", "")
    try:
        prefix = bytes.fromhex(header[:16])
    except (TypeError, ValueError):
        prefix = b""

    if size == 0:
        return {
            "class": "source_empty",
            "evidence": "zero_byte_source",
            "recovery": "locate an independent original or backup; verify its identity against a trusted receipt, then prepare a fresh derived copy",
            "recoverable_from_current_bytes": False,
        }
    if prefix[:4] == APPLEDOUBLE_MAGIC and prefix[4:8] == APPLEDOUBLE_V2:
        return {
            "class": "container_metadata_artifact",
            "evidence": "AppleDouble_sidecar_signature",
            "recovery": "retain this catalog row for review; use the separately cataloged real video asset, and never rename or transcode this sidecar as video",
            "recoverable_from_current_bytes": False,
        }
    if reason == "source_decode_failed":
        return {
            "class": "source_decode_failure",
            "evidence": "checkpoint_records_full_decode_failure",
            "recovery": "seek a verified independent original; if none exists, review a separate salvage experiment that writes to a fresh candidate and passes strict full decode and playback checks",
            "recoverable_from_current_bytes": "unknown_without_a_separate_decode_review",
        }
    if size is not None and size < 8192:
        return {
            "class": "source_suspiciously_small",
            "evidence": "small_nonempty_source_without_a_known_container_signature",
            "recovery": "compare against an independent original or backup; do not infer that a playable video can be reconstructed from these bytes",
            "recoverable_from_current_bytes": False,
        }
    return {
        "class": "container_or_transcode_failure",
        "evidence": "preparation_error_requires_source_and_container_diagnosis",
        "recovery": "verify an independent original, then diagnose container and decoder support in an isolated fresh candidate before any retry",
        "recoverable_from_current_bytes": "unknown_without_a_separate_decode_review",
    }


def build_plan(payload):
    if type(payload) is not dict or set(payload) != {"rows"} or type(payload["rows"]) is not list:
        raise ValueError("invalid_snapshot")
    rows = payload["rows"]
    if len(rows) > MAX_ROWS:
        raise ValueError("too_many_rows")
    ids = []
    result = []
    for row in rows:
        if (type(row) is not dict or not set(row) <= ROW_KEYS
                or not {"id", "reason", "source_size"} <= set(row)
                or type(row.get("id")) is not int or not 0 < row["id"] <= MAX_SQLITE_INTEGER
                or type(row.get("reason")) is not str or row["reason"] not in REASONS
                or type(row.get("source_size")) is not int
                or not 0 <= row["source_size"] <= MAX_SQLITE_INTEGER):
            raise ValueError("invalid_row")
        header = row.get("header_hex", "")
        if (type(header) is not str or len(header) > 128 or len(header) % 2
                or any(ch not in "0123456789abcdefABCDEF" for ch in header)):
            raise ValueError("invalid_header_hex")
        if (row["reason"] == "source_empty") != (row["source_size"] == 0):
            raise ValueError("reason_size_conflict")
        ids.append(row["id"])
        classification = classify(row)
        result.append({"id": row["id"], "reason": row["reason"], **classification})
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate_asset_id")
    return {"mode": "read_only_recovery_plan", "rows": result}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["-h"], ["--help"]):
        print("usage: plan_bad_video_recovery.py [SNAPSHOT_JSON]")
        return 0
    if len(args) > 1 or (args and args[0].startswith("-")):
        print("refused: expected at most one snapshot path", file=sys.stderr)
        return 2
    try:
        if args:
            with open(args[0], "rb") as stream:
                payload = read_snapshot(stream)
        else:
            payload = read_snapshot(sys.stdin.buffer)
        print(json.dumps(build_plan(payload), indent=2, sort_keys=True))
    except SnapshotTooLarge:
        print("refused: snapshot exceeds the input limit", file=sys.stderr)
        return 2
    except OSError:
        print("refused: unable to read snapshot", file=sys.stderr)
        return 2
    except (
        UnicodeDecodeError, json.JSONDecodeError, DuplicateJSONKey,
        InvalidJSONConstant, RecursionError,
    ):
        print("refused: malformed JSON snapshot", file=sys.stderr)
        return 2
    except ValueError:
        print("refused: snapshot does not match the sanitized schema", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

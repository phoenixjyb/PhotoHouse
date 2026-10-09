#!/usr/bin/env python3
"""Plan or make one bounded request for a synthetic memoir quality case.

Planning is offline. Execution requires an explicit private configuration file
and a new private output directory; it never reads or writes family storage.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
from typing import Sequence, TextIO


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPOSITORY_ROOT / "server" / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import plan_memoir_quality_cases as planner  # noqa: E402


MAX_TIMEOUT_SECONDS = 30
COLD_START_MAX_TIMEOUT_SECONDS = 90
CASE_IDS = frozenset({
    "synthetic-coherence", "synthetic-conflict", "synthetic-provenance",
})
EXPECTED_TASKS = {
    "synthetic-coherence": "narrative",
    "synthetic-conflict": "narrative",
    "synthetic-provenance": "companion",
}


class CanaryError(ValueError):
    """A fixed refusal code; never contains paths, endpoints or model names."""

    def __init__(self, code: str):
        self.code = code if code in {
            "arguments_invalid", "configuration_unavailable", "configuration_invalid",
            "output_location_invalid", "output_exists", "output_unavailable",
            "case_unavailable", "provider_failure", "internal_failure",
        } else "internal_failure"
        super().__init__(self.code)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message):
        raise CanaryError("arguments_invalid")


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), sort_keys=True).encode("utf-8", errors="strict")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _load_configuration(path: Path, cold_start: bool = False) -> dict:
    if type(cold_start) is not bool:
        raise CanaryError("configuration_invalid")
    maximum_timeout = COLD_START_MAX_TIMEOUT_SECONDS if cold_start else MAX_TIMEOUT_SECONDS
    try:
        from app.access.model_deployment import DeploymentError, _load_private_document
        from app.access.annotation_local import local_url
    except Exception:
        raise CanaryError("configuration_invalid") from None

    try:
        document = _load_private_document(path, source_root=REPOSITORY_ROOT)
        if (type(document) is not dict or set(document) != {
                "format_version", "ollama_url", "ollama_model", "timeout_seconds"}):
            raise ValueError("shape")
        if type(document["format_version"]) is not int or document["format_version"] != 1:
            raise ValueError("version")
        model = document["ollama_model"]
        if (type(model) is not str or not model or model != model.strip()
                or len(model.encode("utf-8", errors="strict")) > 120
                or any(ord(char) < 32 or 0x7f <= ord(char) < 0xa0
                       or 0xd800 <= ord(char) <= 0xdfff for char in model)):
            raise ValueError("model")
        timeout = document["timeout_seconds"]
        if (type(timeout) not in (int, float) or not 0 < timeout <= maximum_timeout):
            raise ValueError("timeout")
        local_url(document["ollama_url"])
        return {"ollama_url": document["ollama_url"], "ollama_model": model,
                "timeout_seconds": float(timeout)}
    except DeploymentError:
        raise CanaryError("configuration_unavailable") from None
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        raise CanaryError("configuration_invalid") from None


def _case_plan(case_id: str) -> tuple[dict, list[str]]:
    try:
        plan = planner.build_plan()
        case = next(item for item in plan["cases"] if item["case_id"] == case_id)
        case_bytes = _canonical(case["bundle"])
        if _sha256(case_bytes) != case["bundle_sha256"]:
            raise ValueError("bundle hash")
        quality = json.loads((REPOSITORY_ROOT / "models" / "quality-cases.json").read_text(encoding="utf-8"))
        quality_case = next(item for suite in quality["suites"] if suite["role"] == "narrative"
                            for item in suite["cases"] if item["id"] == case_id)
        if quality_case["input_sha256"] != case["bundle_sha256"]:
            raise ValueError("quality case hash")
        if case["task"] != EXPECTED_TASKS[case_id]:
            raise ValueError("task")
        return case, list(quality_case["criteria"])
    except (OSError, ValueError, KeyError, StopIteration, TypeError, RecursionError):
        raise CanaryError("case_unavailable") from None


def _validated_plan() -> list[tuple[dict, list[str]]]:
    return [_case_plan(case_id) for case_id in sorted(CASE_IDS)]


def _validate_output_target(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts or path.name in {"", ".", ".."}:
        raise CanaryError("output_location_invalid")
    root = REPOSITORY_ROOT.resolve()
    try:
        target = path.resolve(strict=False)
        if target == root or target.is_relative_to(root):
            raise CanaryError("output_location_invalid")
        for entry in (*reversed(path.parents), path.parent):
            info = entry.lstat()
            if (stat.S_ISLNK(info.st_mode)
                    or getattr(info, "st_file_attributes", 0) & 0x400
                    or not stat.S_ISDIR(info.st_mode)):
                raise CanaryError("output_location_invalid")
        from app.access.private_storage import require_private_directory
        require_private_directory(path.parent)
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            raise CanaryError("output_exists")
        return target
    except CanaryError:
        raise
    except (OSError, ValueError, TypeError):
        raise CanaryError("output_location_invalid") from None


def _write_exclusive(directory: Path, name: str, payload: bytes) -> None:
    path = directory / name
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
        from app.access.private_storage import require_private_file
        require_private_file(path)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, ValueError):
        raise CanaryError("output_unavailable") from None
    finally:
        if "descriptor" in locals() and descriptor >= 0:
            os.close(descriptor)


def _public_report(*, status: str, case_id: str | None = None, task: str | None = None,
                   input_sha256: str | None = None, output_sha256: str | None = None,
                   error_code: str | None = None) -> dict:
    report = {
        "status": status,
        "case_id": case_id,
        "task": task,
        "input_sha256": input_sha256,
        "output_sha256": output_sha256,
        "quality_evaluated": False,
        "activation_performed": False,
        "resource_limits_verified": False,
    }
    if error_code is not None:
        report["error_code"] = error_code
    return report


def _run_case(case: dict, criteria: list[str], configuration: dict,
              output_path: Path, *, narrator_factory=None) -> dict:
    case_id, task, bundle = case["case_id"], case["task"], case["bundle"]
    input_bytes = _canonical(bundle)
    input_hash = _sha256(input_bytes)
    configuration_hash = _sha256(_canonical(configuration))
    target = _validate_output_target(output_path)
    try:
        target.mkdir(mode=0o700)
    except FileExistsError:
        raise CanaryError("output_exists") from None
    except OSError:
        raise CanaryError("output_unavailable") from None

    try:
        from app.access.private_storage import require_private_directory
        require_private_directory(target)
    except Exception:
        raise CanaryError("output_unavailable") from None

    # Persist the exact submitted synthetic input before the sole request.
    _write_exclusive(target, "input-bundle.json", input_bytes)
    if narrator_factory is None:
        try:
            from app.access.memory_narrative import LocalMemoryNarrator
            narrator_factory = LocalMemoryNarrator
        except Exception:
            raise CanaryError("internal_failure") from None
    try:
        narrator = narrator_factory(configuration["ollama_url"], configuration["ollama_model"],
                                    timeout=configuration["timeout_seconds"])
    except Exception:
        raise CanaryError("configuration_invalid") from None

    started = _utc_now()
    start_clock = time.monotonic()
    try:
        result = getattr(narrator, task)(bundle)
        output_bytes = _canonical(result)
    except Exception as error:
        ended = _utc_now()
        duration = max(0.0, time.monotonic() - start_clock)
        # Only the adapter's three fixed categories can appear in the record.
        from app.access.memory_narrative import LocalMemoryNarrativeError
        error_code = (error.category if isinstance(error, LocalMemoryNarrativeError)
                      and error.category in {"transport", "provider", "invalid_response"}
                      else "provider_failure")
        record = {
            "schema": 1,
            "status": "request_failed",
            "case_id": case_id,
            "task": task,
            "input_sha256": input_hash,
            "output_sha256": None,
            "configuration_identity_sha256": configuration_hash,
            "provider_configuration": dict(configuration),
            "started_at": started,
            "ended_at": ended,
            "duration_seconds": round(duration, 3),
            "timeout_seconds": configuration["timeout_seconds"],
            "quality": {criterion: "unreviewed" for criterion in criteria},
            "quality_evaluated": False,
            "activation_performed": False,
            "resource_limits_verified": False,
            "failure_category": error_code,
        }
        _write_exclusive(target, "record.json", _canonical(record) + b"\n")
        return _public_report(status="request_failed", case_id=case_id, task=task,
                              input_sha256=input_hash, error_code=error_code)

    output_hash = _sha256(output_bytes)
    ended = _utc_now()
    duration = max(0.0, time.monotonic() - start_clock)
    record = {
        "schema": 1,
        "status": "captured_for_human_review",
        "case_id": case_id,
        "task": task,
        "input_sha256": input_hash,
        "output_sha256": output_hash,
        "configuration_identity_sha256": configuration_hash,
        "provider_configuration": dict(configuration),
        "started_at": started,
        "ended_at": ended,
        "duration_seconds": round(duration, 3),
        "timeout_seconds": configuration["timeout_seconds"],
        "quality": {criterion: "unreviewed" for criterion in criteria},
        "quality_evaluated": False,
        "activation_performed": False,
        "resource_limits_verified": False,
    }
    # Persistence failures are reported as output failures and are never
    # reclassified as provider failures or followed by a duplicate record write.
    _write_exclusive(target, "output.json", output_bytes)
    _write_exclusive(target, "record.json", _canonical(record))
    return _public_report(status="captured_for_human_review", case_id=case_id,
                          task=task, input_sha256=input_hash, output_sha256=output_hash)


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="make one provider request for one case")
    parser.add_argument("--cold-start", action="store_true",
                        help="allow the longer cold-start timeout for one explicit run")
    parser.add_argument("--case", choices=sorted(CASE_IDS))
    parser.add_argument("--configuration", type=Path)
    parser.add_argument("--output-directory", type=Path)
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    output = stdout if stdout is not None else sys.stdout
    try:
        parser = _parser()
        args = parser.parse_args(argv)
        if not args.run:
            if (args.cold_start or args.case is not None or args.configuration is not None
                    or args.output_directory is not None):
                raise CanaryError("arguments_invalid")
            cases = _validated_plan()
            report = {
                "status": "plan_only",
                "cases": [{"case_id": case["case_id"], "task": case["task"],
                           "input_sha256": case["bundle_sha256"]} for case, _criteria in cases],
                "quality_evaluated": False,
                "activation_performed": False,
                "resource_limits_verified": False,
            }
        else:
            if (args.case not in CASE_IDS or args.configuration is None
                    or args.output_directory is None):
                raise CanaryError("arguments_invalid")
            if not args.configuration.is_absolute():
                raise CanaryError("configuration_invalid")
            configuration = _load_configuration(args.configuration, cold_start=args.cold_start)
            case, criteria = _case_plan(args.case)
            report = _run_case(case, criteria, configuration, args.output_directory)
        output.write(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n")
        return 0 if report["status"] in {"plan_only", "captured_for_human_review"} else 2
    except CanaryError as error:
        output.write(json.dumps(_public_report(status="refused", error_code=error.code),
                                separators=(",", ":")) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

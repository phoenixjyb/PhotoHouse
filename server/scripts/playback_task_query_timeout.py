"""Prepare a byte-preserving, bounded-timeout patch for a pinned worker source.

This module never imports or executes the worker.  Its CLI only writes a new
prepared source file after the caller supplies the expected source digest.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


class Refused(ValueError):
    """Closed refusal raised for an unrecognized source or exhausted budget."""


_HELPER_NAME = "_run_bounded_playback_task_query"
_WORKER_CLASS = "OnlyPinnedTaskQuery"
_QUERY_METHOD = "run"
_MAIN_FUNCTION = "main"
_MAX_SOURCE_BYTES = 2 * 1024 * 1024
_PATCHED_CALL = (
    "_run_bounded_playback_task_query(original_run, powershell, argv, kwargs, started)"
)
_ORIGINAL_CALL_SOURCE = (
    "original_run([str(powershell), *argv[1:]], "
    "executable=str(powershell), **kwargs)"
)
_HELPER_SOURCE = '''def _run_bounded_playback_task_query(original_run, powershell, argv, kwargs, started):
    """Run one original task query within the parent run's reserved deadline."""
    need(callable(original_run), 'task_query_runner')
    need(isinstance(kwargs, dict) and kwargs.get('timeout') == 15, 'task_query_original_timeout')
    need(isinstance(started, (int, float)) and not isinstance(started, bool), 'task_query_started_clock')
    started = float(started)
    need(started == started and started not in (float('inf'), float('-inf')) and started >= 0,
         'task_query_started_clock')
    now = time.monotonic()
    need(isinstance(now, (int, float)) and not isinstance(now, bool), 'task_query_clock')
    now = float(now)
    need(now == now and now not in (float('inf'), float('-inf')) and now >= started,
         'task_query_clock')
    remaining = 900.0 - (now - started) - 90.0
    need(remaining == remaining and remaining not in (float('inf'), float('-inf'))
         and remaining >= 15.0, 'task_query_budget_exhausted')
    timeout = min(45.0, remaining)
    call_kwargs = dict(kwargs)
    call_kwargs['timeout'] = timeout
    try:
        return original_run([str(powershell), *argv[1:]], executable=str(powershell), **call_kwargs)
    except subprocess.TimeoutExpired as exc:
        raise Refused('task_query_timed_out') from exc
'''


def _need(condition: bool, code: str) -> None:
    if not condition:
        raise Refused(code)


def _line_byte_offsets(raw: bytes) -> list[int]:
    starts = [0]
    for index, byte in enumerate(raw):
        if byte == 10:
            starts.append(index + 1)
    return starts


def _byte_offset(raw: bytes, starts: list[int], line: int, utf8_column: int) -> int:
    _need(1 <= line <= len(starts) and utf8_column >= 0, "source_location")
    line_start = starts[line - 1]
    line_end = starts[line] if line < len(starts) else len(raw)
    line_bytes = raw[line_start:line_end]
    # AST columns are UTF-8 byte offsets; verify the endpoint is within this line.
    _need(utf8_column <= len(line_bytes), "source_location")
    return line_start + utf8_column


def _started_assignment(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "started"
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and isinstance(node.value.func.value, ast.Name)
        and node.value.func.value.id == "time"
        and node.value.func.attr == "monotonic"
        and not node.value.args
        and not node.value.keywords
    )


def _find_target(tree: ast.Module) -> tuple[ast.FunctionDef, ast.ClassDef, ast.FunctionDef, ast.Assign, ast.Call]:
    mains = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == _MAIN_FUNCTION]
    _need(len(mains) == 1, "main_function_shape")
    main = mains[0]
    _need(not main.decorator_list, "main_decorator_shape")
    classes = [node for node in ast.walk(main) if isinstance(node, ast.ClassDef) and node.name == _WORKER_CLASS]
    _need(len(classes) == 1 and classes[0] in main.body, "worker_class_scope")
    cls = classes[0]
    starts = [index for index, stmt in enumerate(main.body) if _started_assignment(stmt)]
    _need(len(starts) == 1, "started_assignment_shape")
    class_index = main.body.index(cls)
    _need(starts[0] < class_index, "started_assignment_order")
    methods = [node for node in cls.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
               and node.name == _QUERY_METHOD]
    _need(len(methods) == 1 and isinstance(methods[0], ast.FunctionDef), "query_method_shape")
    method = methods[0]
    calls = [node for node in ast.walk(method)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == "original_run"]
    _need(len(calls) == 1, "query_call_count")
    call = calls[0]
    parent = next((stmt for stmt in method.body if call in ast.walk(stmt)), None)
    _need(parent is not None and isinstance(parent, ast.Assign), "query_call_statement_shape")
    _need(len(parent.targets) == 1 and isinstance(parent.targets[0], ast.Name)
          and parent.targets[0].id == "value" and parent.value is call, "query_assignment_shape")
    assign = parent
    expected = ast.parse(_ORIGINAL_CALL_SOURCE, mode="eval").body
    _need(ast.dump(call, include_attributes=False) == ast.dump(expected, include_attributes=False),
          "query_call_shape")
    return main, cls, method, assign, call


def _normalized_original(tree: ast.Module) -> ast.Module:
    """Return an AST with the inserted helper removed and call restored."""
    tree = copy.deepcopy(tree)
    helpers = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == _HELPER_NAME]
    _need(len(helpers) == 1, "patched_helper_shape")
    tree.body.remove(helpers[0])
    mains = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == _MAIN_FUNCTION]
    _need(len(mains) == 1, "main_function_shape")
    classes = [node for node in ast.walk(mains[0]) if isinstance(node, ast.ClassDef)
               and node.name == _WORKER_CLASS]
    _need(len(classes) == 1 and classes[0] in mains[0].body, "worker_class_scope")
    methods = [node for node in classes[0].body if isinstance(node, ast.FunctionDef)
               and node.name == _QUERY_METHOD]
    _need(len(methods) == 1, "query_method_shape")
    method = methods[0]
    calls = [node for node in ast.walk(method)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
             and node.func.id == _HELPER_NAME]
    _need(len(calls) == 1, "patched_query_call_shape")
    call = calls[0]
    parent = next((stmt for stmt in method.body if call in ast.walk(stmt)), None)
    _need(parent is not None and isinstance(parent, ast.Assign), "query_call_statement_shape")
    _need(len(parent.targets) == 1 and isinstance(parent.targets[0], ast.Name)
          and parent.targets[0].id == "value" and parent.value is call, "query_assignment_shape")
    assign = parent
    expected = ast.parse(_PATCHED_CALL, mode="eval").body
    _need(ast.dump(call, include_attributes=False) == ast.dump(expected, include_attributes=False),
          "patched_query_call_shape")
    restored = ast.parse(_ORIGINAL_CALL_SOURCE, mode="eval").body
    assign.value = restored
    return tree


def prepare_patch(source: bytes, expected_sha256: str) -> tuple[bytes, dict[str, object]]:
    """Patch one exact source byte string and prove normalized AST equivalence."""
    _need(isinstance(source, bytes), "source_bytes_required")
    _need(len(source) <= _MAX_SOURCE_BYTES, "source_size_refused")
    _need(isinstance(expected_sha256, str) and re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is not None,
          "expected_sha256_shape")
    actual_sha256 = hashlib.sha256(source).hexdigest()
    _need(actual_sha256 == expected_sha256, "source_sha256_mismatch")
    try:
        decoded = source.decode("utf-8")
        original_tree = ast.parse(decoded)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise Refused("source_parse_refused") from exc
    _need(not any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == _HELPER_NAME
                  for node in ast.walk(original_tree)), "already_patched")
    main, _cls, _method, _assign, call = _find_target(original_tree)
    starts = _line_byte_offsets(source)
    call_start = _byte_offset(source, starts, call.lineno, call.col_offset)
    call_end = _byte_offset(source, starts, call.end_lineno, call.end_col_offset)
    main_start = _byte_offset(source, starts, main.lineno, 0)
    _need(main_start <= call_start < call_end <= len(source), "source_span_order")
    replacement = _PATCHED_CALL.encode("ascii")
    helper = (_HELPER_SOURCE + "\n").encode("ascii")
    patched = source[:main_start] + helper + source[main_start:call_start] + replacement + source[call_end:]
    try:
        patched_tree = ast.parse(patched.decode("utf-8"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise Refused("patched_source_parse_refused") from exc
    normalized = _normalized_original(patched_tree)
    _need(ast.dump(normalized, include_attributes=False) == ast.dump(original_tree, include_attributes=False),
          "normalized_ast_mismatch")
    meta = {
        "status": "PREPARED",
        "source_sha256": actual_sha256,
        "prepared_sha256": hashlib.sha256(patched).hexdigest(),
        "source_bytes": len(source),
        "prepared_bytes": len(patched),
        "replacement_span": {"start": call_start, "end": call_end},
        "helper_insert_offset": main_start,
        "helper_bytes": len(helper),
        "normalized_ast_equal": True,
    }
    return patched, meta


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path,
                        help="new prepared source path; existing files are refused")
    args = parser.parse_args()
    try:
        source = args.source.read_bytes()
        patched, metadata = prepare_patch(source, args.expected_sha256)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        fd = os.open(args.output, flags, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(patched)
            stream.flush()
            os.fsync(stream.fileno())
        print(json.dumps(metadata, sort_keys=True, separators=(",", ":")))
        return 0
    except Refused as exc:
        print(json.dumps({"status": "REFUSED", "code": str(exc)}, sort_keys=True))
        return 2
    except FileExistsError:
        print(json.dumps({"status": "REFUSED", "code": "output_already_exists"}, sort_keys=True))
        return 2
    except OSError as exc:
        print(json.dumps({"status": "REFUSED", "code": "source_or_output_io_refused",
                          "error_type": type(exc).__name__}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())

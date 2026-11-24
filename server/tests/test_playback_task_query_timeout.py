import ast
import hashlib
import subprocess
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from playback_task_query_timeout import Refused, prepare_patch


SOURCE = (
    '"""Référence fixture."""\n'
    'import subprocess\n'
    'import time\n'
    'def main():\n'
    '    started = time.monotonic()\n'
    '    class OnlyPinnedTaskQuery:\n'
    '        @staticmethod\n'
    '        def run(original_run, powershell, argv, kwargs):\n'
    '            before = pinned_windows_executable(powershell)\n'
    '            pré = "保留"; value = original_run([str(powershell), *argv[1:]], executable=str(powershell), **kwargs)\n'
    '            after = pinned_windows_executable(powershell)\n'
    '            return value, before, after\n'
    '    return OnlyPinnedTaskQuery\n'
).encode("utf-8")


def prepared(source=SOURCE):
    return prepare_patch(source, hashlib.sha256(source).hexdigest())


def generated_helper(patched, metadata, *, now=0):
    start = metadata["helper_insert_offset"]
    raw = patched[start:start + metadata["helper_bytes"]]
    namespace = {
        "need": lambda ok, code: None if ok else (_ for _ in ()).throw(Refused(code)),
        "Refused": Refused,
        "time": SimpleNamespace(monotonic=lambda: now),
        "subprocess": subprocess,
    }
    exec(compile(raw.decode("ascii"), "<generated-helper-fixture>", "exec"), namespace)
    return namespace["_run_bounded_playback_task_query"]


def test_nested_main_patch_preserves_bytes_and_normalized_ast_with_utf8_offsets():
    patched, metadata = prepared()
    assert metadata["normalized_ast_equal"] is True
    assert metadata["source_sha256"] == hashlib.sha256(SOURCE).hexdigest()
    assert metadata["prepared_sha256"] == hashlib.sha256(patched).hexdigest()
    assert '"Référence fixture."'.encode("utf-8") in patched
    assert '"保留"'.encode("utf-8") in patched

    span = metadata["replacement_span"]
    helper_len = metadata["helper_bytes"]
    patched_call_start = span["start"] + helper_len
    patched_call_end = patched_call_start + len(
        b"_run_bounded_playback_task_query(original_run, powershell, argv, kwargs, started)")
    restored = (patched[:metadata["helper_insert_offset"]]
                + patched[metadata["helper_insert_offset"] + helper_len:patched_call_start]
                + SOURCE[span["start"]:span["end"]]
                + patched[patched_call_end:])
    assert restored == SOURCE

    original_tree = ast.parse(SOURCE.decode("utf-8"))
    patched_tree = ast.parse(patched.decode("utf-8"))
    original_main = next(node for node in original_tree.body if isinstance(node, ast.FunctionDef)
                         and node.name == "main")
    patched_main = next(node for node in patched_tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "main")
    original_class = next(node for node in original_main.body if isinstance(node, ast.ClassDef))
    patched_class = next(node for node in patched_main.body if isinstance(node, ast.ClassDef))
    assert original_class.name == patched_class.name == "OnlyPinnedTaskQuery"
    assert next(node.lineno for node in patched_tree.body if isinstance(node, ast.FunctionDef)
                and node.name == "_run_bounded_playback_task_query") < patched_main.lineno


def test_actual_generated_helper_forwards_bounded_call_once_without_mutating_inputs():
    patched, metadata = prepared()
    helper = generated_helper(patched, metadata, now=870)
    calls = []
    kwargs = {"timeout": 15, "check": True, "text": True}
    argv = ["powershell.exe", "-NoProfile", "-Command", "query"]

    def original_run(command, **options):
        calls.append((command, options))
        return "result"

    assert helper(original_run, "powershell.exe", argv, kwargs, 100) == "result"
    assert len(calls) == 1
    assert calls[0][0] == argv
    assert calls[0][1] == {"timeout": 40.0, "check": True, "text": True,
                           "executable": "powershell.exe"}
    assert kwargs == {"timeout": 15, "check": True, "text": True}
    assert argv == ["powershell.exe", "-NoProfile", "-Command", "query"]


def test_actual_generated_helper_caps_at_45_seconds():
    patched, metadata = prepared()
    helper = generated_helper(patched, metadata, now=0)
    calls = []
    helper(lambda command, **options: calls.append(options) or "ok",
           "pwsh", ["pwsh", "-Command", "x"], {"timeout": 15}, 0)
    assert calls == [{"timeout": 45.0, "executable": "pwsh"}]


def test_actual_generated_helper_timeout_is_closed_and_never_retried():
    patched, metadata = prepared()
    helper = generated_helper(patched, metadata, now=0)
    calls = []

    def timed_out(*args, **kwargs):
        calls.append(1)
        raise subprocess.TimeoutExpired("pwsh", kwargs["timeout"])

    with pytest.raises(Refused, match="task_query_timed_out") as caught:
        helper(timed_out, "pwsh", ["pwsh", "-Command", "x"], {"timeout": 15}, 0)
    assert isinstance(caught.value.__cause__, subprocess.TimeoutExpired)
    assert len(calls) == 1


def test_actual_generated_helper_propagates_unexpected_error_without_retry():
    patched, metadata = prepared()
    helper = generated_helper(patched, metadata, now=0)
    calls = []

    def broken(*args, **kwargs):
        calls.append(1)
        raise OSError("fixture")

    with pytest.raises(OSError, match="fixture"):
        helper(broken, "pwsh", ["pwsh", "-Command", "x"], {"timeout": 15}, 0)
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("started", "now", "kwargs", "code"),
    [
        (0, 796, {"timeout": 15}, "task_query_budget_exhausted"),
        (100, 99, {"timeout": 15}, "task_query_clock"),
        (float("nan"), 100, {"timeout": 15}, "task_query_started_clock"),
        (0, float("inf"), {"timeout": 15}, "task_query_clock"),
        (True, 100, {"timeout": 15}, "task_query_started_clock"),
        (0, 100, {"timeout": 14}, "task_query_original_timeout"),
    ],
)
def test_actual_generated_helper_refuses_invalid_or_exhausted_budget(started, now, kwargs, code):
    patched, metadata = prepared()
    helper = generated_helper(patched, metadata, now=now)
    calls = []
    with pytest.raises(Refused, match=code):
        helper(lambda *a, **k: calls.append(1), "pwsh", ["pwsh", "-Command", "x"], kwargs, started)
    assert calls == []


@pytest.mark.parametrize(
    ("source", "expected", "code"),
    [
        (SOURCE, "0" * 64, "source_sha256_mismatch"),
        (b"class Other: pass\n", hashlib.sha256(b"class Other: pass\n").hexdigest(),
         "main_function_shape"),
        (SOURCE.replace(b"    started = time.monotonic()\n", b""),
         hashlib.sha256(SOURCE.replace(b"    started = time.monotonic()\n", b"")).hexdigest(),
         "started_assignment_shape"),
        (SOURCE.replace(b"original_run([str(powershell), *argv[1:]], executable=str(powershell), **kwargs)",
                        b"original_run(argv, **kwargs)"),
         hashlib.sha256(SOURCE.replace(
             b"original_run([str(powershell), *argv[1:]], executable=str(powershell), **kwargs)",
             b"original_run(argv, **kwargs)")).hexdigest(), "query_call_shape"),
    ],
)
def test_source_and_scope_refusals(source, expected, code):
    with pytest.raises(Refused, match=code):
        prepare_patch(source, expected)


def test_refuses_wrong_scope_duplicate_and_already_patched_sources():
    top_level = (
        'def main():\n'
        '    started = time.monotonic()\n'
        '    if True:\n'
        '        class OnlyPinnedTaskQuery:\n'
        '            @staticmethod\n'
        '            def run(original_run, powershell, argv, kwargs):\n'
        '                value = original_run([str(powershell), *argv[1:]], executable=str(powershell), **kwargs)\n'
        '                return value\n'
    ).encode("utf-8")
    with pytest.raises(Refused, match="worker_class_scope"):
        prepare_patch(top_level, hashlib.sha256(top_level).hexdigest())

    duplicate = SOURCE.replace(
        b"            after = pinned_windows_executable(powershell)\n",
        b"            value2 = original_run([str(powershell), *argv[1:]], executable=str(powershell), **kwargs)\n"
        b"            after = pinned_windows_executable(powershell)\n",
    )
    with pytest.raises(Refused, match="query_call_count"):
        prepare_patch(duplicate, hashlib.sha256(duplicate).hexdigest())

    patched, _ = prepared()
    with pytest.raises(Refused, match="already_patched"):
        prepare_patch(patched, hashlib.sha256(patched).hexdigest())


def test_refuses_source_above_closed_size_cap():
    source = b"#" * (2 * 1024 * 1024 + 1)
    with pytest.raises(Refused, match="source_size_refused"):
        prepare_patch(source, hashlib.sha256(source).hexdigest())


def test_cli_prepares_new_output_and_reports_existing_output_without_paths(tmp_path):
    import json
    source = tmp_path / "source.py"
    output = tmp_path / "prepared.py"
    source.write_bytes(SOURCE)
    tool = Path(__file__).resolve().parents[1] / "scripts" / "playback_task_query_timeout.py"
    argv = [sys.executable, "-I", "-B", str(tool), "--source", str(source),
            "--expected-sha256", hashlib.sha256(SOURCE).hexdigest(), "--output", str(output)]
    first = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert first.returncode == 0 and first.stderr == ""
    assert json.loads(first.stdout)["prepared_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    original = output.read_bytes()
    repeated = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert repeated.returncode == 2 and repeated.stderr == ""
    assert json.loads(repeated.stdout) == {"status": "REFUSED", "code": "output_already_exists"}
    assert str(tmp_path) not in repeated.stdout
    assert output.read_bytes() == original


def test_cli_missing_source_reports_only_closed_error_type(tmp_path):
    import json
    tool = Path(__file__).resolve().parents[1] / "scripts" / "playback_task_query_timeout.py"
    result = subprocess.run([sys.executable, "-I", "-B", str(tool), "--source", str(tmp_path / "missing.py"),
                             "--expected-sha256", "0" * 64, "--output", str(tmp_path / "new.py")],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2 and result.stderr == ""
    assert json.loads(result.stdout) == {"status": "REFUSED", "code": "source_or_output_io_refused",
                                        "error_type": "FileNotFoundError"}
    assert str(tmp_path) not in result.stdout and not (tmp_path / "new.py").exists()

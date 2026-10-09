import contextlib
import io
import json
import sqlite3
import sys
from pathlib import Path
from unittest import mock

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

import home_preparation_resources as resources
import run_approved_cpu_worker as cpu_worker
import run_approved_face_pipeline as face_pipeline
import run_approved_image_embed_worker as image_worker
import run_approved_video_embed_worker as video_worker


def _cli_failure(module, error):
    stdout = io.StringIO()
    stderr = io.StringIO()
    arguments = ['--database', 'private-db', '--originals-root', 'private-originals',
                 '--derived-root', 'private-derived', '--stop-file', 'private-stop', '--execute']
    if module is image_worker:
        arguments.extend(['--checkpoint', 'private-checkpoint', '--checkpoint-sha256', '0' * 64,
                          '--image-model', 'model', '--model-version', 'version', '--device', 'cpu'])
    elif module is video_worker:
        arguments.extend(['--checkpoint', 'private-checkpoint', '--checkpoint-sha256', '0' * 64,
                          '--image-model', 'model', '--model-version', 'version', '--device', 'cpu'])
    elif module is face_pipeline:
        arguments = ['--database', 'private-db', '--originals', 'private-originals',
                     '--derived', 'private-derived', '--stop-file', 'private-stop',
                     '--insightface-root', 'private-model-root', '--model-path', 'private-model',
                     '--gpu-uuid', 'GPU-private']
    with mock.patch.object(module, 'run', side_effect=error):
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = module.main(arguments)
    return code, stdout.getvalue(), stderr.getvalue()


@pytest.mark.parametrize('module,refused_type', [
    (cpu_worker, cpu_worker.Refused),
    (image_worker, image_worker.Refused),
    (video_worker, video_worker.Refused),
    (face_pipeline, face_pipeline.Refused),
])
@pytest.mark.parametrize('message,expected', [
    ('Supported migrated database required', 'unsupported_schema'),
    ('Explicit absolute local path required', 'path_refused'),
    ('Another approved image embedding worker owns this database', 'worker_lock_busy'),
    ('Stop request already present', 'stop_requested'),
    ('private/path/schema/GPU-123', 'refused'),
])
def test_cli_failure_report_is_sanitized(module, refused_type, message, expected):
    code, stdout, stderr = _cli_failure(module, refused_type(message))
    assert code == 2
    assert stdout == ''
    report = json.loads(stderr)
    assert report['phase'] == 'worker_entry'
    assert report['reason' if module is face_pipeline else 'failure'] == expected
    assert message not in stderr
    if module is face_pipeline:
        assert report['face_pipeline'] == 'refused'
    else:
        assert report['worker'] == 'refused-or-interrupted'
        assert report['inspect_task_state'] is True


@pytest.mark.parametrize('module,refused_type,invalid_args', [
    (cpu_worker, cpu_worker.Refused, ['--database', '/private/db', '--bad-private-argument']),
    (image_worker, image_worker.Refused, ['--database', '/private/db', '--bad-private-argument']),
    (video_worker, video_worker.Refused, ['--database', '/private/db', '--bad-private-argument']),
    (face_pipeline, face_pipeline.Refused, ['--database', '/private/db', '--bad-private-argument']),
])
def test_argument_errors_use_sanitized_json(module, refused_type, invalid_args):
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = module.main(invalid_args)
    assert code == 2
    assert stdout.getvalue() == ''
    report = json.loads(stderr.getvalue())
    assert report['phase'] == 'worker_entry'
    assert report['reason' if module is face_pipeline else 'failure'] == 'invalid_arguments'
    assert '/private/db' not in stderr.getvalue()
    assert 'bad-private-argument' not in stderr.getvalue()


@pytest.mark.parametrize('sqlite_code,expected', [
    (sqlite3.SQLITE_BUSY, 'database_busy'),
    (sqlite3.SQLITE_BUSY_TIMEOUT, 'database_busy'),
    (sqlite3.SQLITE_LOCKED_SHAREDCACHE, 'database_busy'),
    (sqlite3.SQLITE_ERROR, 'database_error'),
])
def test_sqlite_numeric_error_classification(sqlite_code, expected):
    error = sqlite3.OperationalError('private database path and SQL')
    error.sqlite_errorcode = sqlite_code
    assert resources._failure_code(error) == expected


def test_failure_type_and_os_error_classification():
    assert resources._failure_code(KeyboardInterrupt()) == 'interrupted'
    assert resources._failure_code(PermissionError('private path')) == 'permission_denied'
    assert resources._failure_code(FileNotFoundError('private path')) == 'file_missing'
    assert resources._failure_code(OSError('private path')) == 'io_error'
    # A recognizable enum string in the wrong exception type stays generic.
    assert resources._failure_code(RuntimeError('Supported migrated database required')) == 'unexpected_failure'
    assert resources._failure_code(ValueError('operator_stop')) == 'unexpected_failure'


@pytest.mark.parametrize('message,expected', [
    ('memory_pressure', 'resource_limit'),
    ('owned_memory_limit', 'resource_limit'),
    ('run_time_limit', 'task_time_limit'),
    ('private memory detail', 'unexpected_failure'),
])
def test_owned_resource_guard_failures_are_classified(message, expected):
    assert resources._failure_code(resources.JobStopped(message)) == expected


def test_child_routes_keep_their_existing_private_exit_behavior():
    for module, arguments, child in (
        (image_worker, ['_probe', 'private-child-argument'], '_probe_or_embed_child'),
        (video_worker, ['_video_embed', 'private-child-argument'], '_child'),
    ):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(module, child, side_effect=RuntimeError('private child detail')) as run_child:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                assert module.main(arguments) == 2
        run_child.assert_called_once()
        assert stdout.getvalue() == stderr.getvalue() == ''


@pytest.mark.parametrize('module,foreign_error,expected', [
    (video_worker, image_worker.Refused('Explicit absolute local path required'), 'path_refused'),
    (face_pipeline, image_worker.Refused('Explicit absolute local path required'), 'path_refused'),
    (face_pipeline, face_pipeline.QueueRefused('required_table_missing'), 'unsupported_schema'),
])
def test_imported_refusal_types_are_sanitized(module, foreign_error, expected):
    code, stdout, stderr = _cli_failure(module, foreign_error)
    assert code == 2
    assert stdout == ''
    report = json.loads(stderr)
    assert report['reason' if module is face_pipeline else 'failure'] == expected


def test_terminal_interrupts_and_unknown_errors_do_not_leak_text():
    for module, refused_type in ((cpu_worker, cpu_worker.Refused),
                                 (image_worker, image_worker.Refused),
                                 (video_worker, video_worker.Refused),
                                 (face_pipeline, face_pipeline.Refused)):
        for error, expected in ((KeyboardInterrupt('private stop detail'), 'interrupted'),
                                (RuntimeError('private traceback path and GPU ID'), 'unexpected_failure')):
            code, stdout, stderr = _cli_failure(module, error)
            assert code == 2
            assert stdout == ''
            report = json.loads(stderr)
            assert report['reason' if module is face_pipeline else 'failure'] == expected
            assert 'private' not in stderr and 'GPU' not in stderr

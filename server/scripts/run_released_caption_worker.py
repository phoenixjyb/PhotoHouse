#!/usr/bin/env python3
"""Metadata preflight by default; explicit serial Windows jobs for released captions.

No task registration, service startup, migration, broad queue claim or model loading.
The HTTP model service is separately operated and is outside this CPU client's Job.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import io
import json
import math
import os
from pathlib import Path
import sys
import time
import uuid

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / 'backend'))
sys.path.insert(0, str(SERVER / 'scripts'))

from app.access.annotation_local import _strict_json
from app.access.original_deletions import OriginalDeletionJournal
from app.access.runtime import ExistingDatabase
from app.access.private_storage import require_private_directory, require_private_file
from app.access.upload_caption_processing import (CaptionProcessingRefused,
    inspect_released_captions, process_released_caption_task)
from bounded_windows_job import (WindowsAPI, run_bounded, _ExtendedLimits,
    JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, JOB_OBJECT_LIMIT_ACTIVE_PROCESS,
    JOB_OBJECT_LIMIT_JOB_MEMORY, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)

MEMORY_LIMIT = 2 * 1024**3
FREE_RAM_FLOOR = 8 * 1024**3
PROCESS_LIMIT = 8
TASK_SECONDS = 300
MAX_TASKS = 128
MAX_RUN_SECONDS = 2 * 60 * 60
FIELDS = frozenset({'database', 'originals_root', 'original_deletion_journal_path',
    'original_deletion_namespace', 'operator_account_id', 'library_id', 'release_plan_id',
    'task_ids', 'caption_url', 'expected_model_id', 'stop_file', 'provider_timeout_seconds'})


class WorkerRefused(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise WorkerRefused(code)


def selected_path(value, *, existing=False, directory=False):
    require(type(value) is str and bool(value), 'invalid_path')
    path = Path(value)
    require(path.is_absolute() and '..' not in path.parts and path != Path(path.anchor)
        and not path.anchor.startswith(('//', '\\\\'))
        and path.parent.resolve(strict=True) == path.parent, 'invalid_path')
    if existing or os.path.lexists(path):
        require(path.resolve(strict=True) == path and not path.is_symlink()
            and (path.is_dir() if directory else path.is_file()), 'invalid_path')
    return path


def read_config(path):
    path = selected_path(str(path), existing=True)
    require_private_file(path)
    before = path.stat()
    require(before.st_size <= 32 * 1024, 'invalid_config')
    raw = path.read_bytes()
    after = path.stat()
    identity = lambda value: (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    require(len(raw) <= 32 * 1024 and identity(after) == identity(before), 'config_changed')
    try:
        config = _strict_json(raw)
        require(type(config) is dict and set(config) == FIELDS, 'invalid_config')
        for key in ('original_deletion_namespace', 'operator_account_id', 'release_plan_id'):
            require(type(config[key]) is str and str(uuid.UUID(config[key])) == config[key], 'invalid_config')
        tasks = config['task_ids']
        require(type(tasks) is list and 0 < len(tasks) <= MAX_TASKS
            and all(type(n) is int and 0 < n < 2**63 for n in tasks)
            and tasks == sorted(set(tasks)), 'invalid_selection')
        require(type(config['library_id']) is str and 0 < len(config['library_id']) <= 128,
                'invalid_config')
        require(type(config['provider_timeout_seconds']) in (int, float)
            and math.isfinite(config['provider_timeout_seconds'])
            and 0 < config['provider_timeout_seconds'] <= 60, 'invalid_config')
        from app.approved_caption_http import LocalCaptionHTTP
        LocalCaptionHTTP(url=config['caption_url'], expected_model_id=config['expected_model_id'],
                         timeout=config['provider_timeout_seconds'])
        database = selected_path(config['database'], existing=True)
        journal = selected_path(config['original_deletion_journal_path'], existing=True)
        originals = selected_path(config['originals_root'], existing=True, directory=True)
        stop = selected_path(config['stop_file'])
        require(database != journal and stop not in (database, journal, path)
            and not stop.is_relative_to(originals) and not path.is_relative_to(originals), 'invalid_config')
    except WorkerRefused:
        raise
    except Exception:
        raise WorkerRefused('invalid_config') from None
    return config, hashlib.sha256(raw).hexdigest()


def factory_for(config):
    return ExistingDatabase(Path(config['database']), original_deletions=OriginalDeletionJournal(
        Path(config['original_deletion_journal_path']), config['original_deletion_namespace']))


def scope_for(config):
    return {key: config[key] for key in ('release_plan_id', 'operator_account_id', 'library_id')}


def preflight(config):
    return inspect_released_captions(factory_for(config), **scope_for(config), task_ids=config['task_ids'])


def _read_result(path):
    require_private_file(path)
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 64 * 1024,
            'child_report_unavailable')
    result = _strict_json(path.read_bytes())
    require(type(result) is dict, 'child_report_invalid')
    return result


def _save_new(path, value):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, 'O_NOFOLLOW', 0), 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        require_private_file(path)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())


def new_report_path(path, config_path, config):
    path = selected_path(str(path))
    require_private_directory(path.parent)
    require(not os.path.lexists(path) and path not in (config_path,
        Path(config['database']), Path(config['original_deletion_journal_path']), Path(config['stop_file']))
        and not path.is_relative_to(Path(config['originals_root'])), 'new_private_report_required')
    return path


def _update_owned(path, value, nonce):
    require(_read_result(path).get('run_id') == nonce, 'report_ownership_changed')
    temporary = path.with_name(path.name + '.' + nonce + '.tmp')
    _save_new(temporary, value)
    require(_read_result(path).get('run_id') == nonce, 'report_ownership_changed')
    os.replace(temporary, path)


def verify_child_budget():
    require(sys.platform == 'win32', 'windows_required')
    api = WindowsAPI(); limits = _ExtendedLimits()
    require(api.k32.QueryInformationJobObject(None, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
        ctypes.byref(limits), ctypes.sizeof(limits), None), 'child_budget_unavailable')
    expected = JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    require(limits.BasicLimitInformation.LimitFlags == expected
        and limits.JobMemoryLimit == MEMORY_LIMIT
        and limits.BasicLimitInformation.ActiveProcessLimit == PROCESS_LIMIT, 'child_budget_unavailable')
    require(api.free_ram() >= FREE_RAM_FLOOR, 'free_ram_below_minimum')


def _provider(config):
    from app.approved_caption_http import LocalCaptionHTTP
    provider = LocalCaptionHTTP(url=config['caption_url'], expected_model_id=config['expected_model_id'],
                               timeout=config['provider_timeout_seconds'])
    provider.preflight()
    return provider


def _generate_adapter(config, provider):
    from PIL import Image, ImageOps
    from app.approved_caption_generation import CaptionGenerationRefused, generate_caption_result
    stop = Path(config['stop_file'])

    class StopAware:
        supports_image_preparation = True
        supports_text_translation = True
        def __getattr__(self, name):
            method = getattr(provider, name)
            def call(*args, **kwargs):
                if os.path.lexists(stop): raise CaptionProcessingRefused('stop_requested')
                return method(*args, **kwargs)
            return call

    def generate(raw, mime):
        if os.path.lexists(stop): raise CaptionProcessingRefused('stop_requested')
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if (image.format not in {'JPEG', 'PNG'} or image.width * image.height > 64_000_000
                        or getattr(image, 'n_frames', 1) != 1
                        or {'JPEG': 'image/jpeg', 'PNG': 'image/png'}[image.format] != mime):
                    raise CaptionProcessingRefused('source_changed')
                with ImageOps.exif_transpose(image) as upright:
                    with upright.convert('RGB') as rgb:
                        return generate_caption_result(rgb, provider=StopAware())
        except CaptionGenerationRefused as error:
            if os.path.lexists(stop): raise CaptionProcessingRefused('stop_requested') from None
            if error.reason_code == 'policy_refused':
                raise CaptionProcessingRefused('caption_policy_rejected') from None
            if error.reason_code in {'invalid_output', 'provider_identity', 'invalid_input'}:
                raise CaptionProcessingRefused('invalid_caption_result') from None
            raise CaptionProcessingRefused('generation_failed') from None
        except (OSError, Image.DecompressionBombError):
            raise CaptionProcessingRefused('source_changed') from None
    return generate


def task_child(config_path, digest, task_id, result_path):
    verify_child_budget()  # Refuse direct/unbounded invocation before opening the DB.
    config, actual = read_config(config_path)
    require(actual == digest and task_id in config['task_ids'], 'config_changed')
    result_path = new_report_path(result_path, Path(config_path), config)
    provider = _provider(config)  # An unavailable model does not consume a task attempt.
    result = process_released_caption_task(factory_for(config), **scope_for(config), task_id=task_id,
        originals_root=Path(config['originals_root']), generate=_generate_adapter(config, provider),
        should_stop=lambda: os.path.lexists(config['stop_file']))
    _save_new(result_path, result)


def run(config_path, *, execute=False, report_path=None, api_factory=WindowsAPI, launch=run_bounded):
    config_path = selected_path(str(config_path), existing=True)
    config, digest = read_config(config_path)
    snapshot = preflight(config)
    if not execute:
        return dict(snapshot, provider_checked=False, config_sha256=digest)
    require(not os.path.lexists(config['stop_file']), 'stop_requested')
    require(not any(item['state'] == 'running' for item in snapshot['items']), 'running_claim_requires_review')
    if not any(item['state'] == 'pending' and not item['cancel_requested']
               and item['retry_count'] < 3 and item['due'] for item in snapshot['items']):
        return dict(snapshot, state='no_due_tasks', provider_checked=False,
                    all_selected_finished=all(item['state'] == 'finished' for item in snapshot['items']))
    require(sys.platform == 'win32', 'windows_required')
    report_path = new_report_path(report_path, config_path, config)
    api = api_factory()
    require(api.free_ram() >= FREE_RAM_FLOOR, 'free_ram_below_minimum')
    _provider(config)  # Read-only health admission; no inference or task claim.
    nonce = uuid.uuid4().hex
    report = {'run_id': nonce, 'config_sha256': digest, 'state': 'running', 'results': [],
              'skipped': [], 'memory_limit_bytes': MEMORY_LIMIT, 'free_ram_admission_bytes': FREE_RAM_FLOOR,
              'process_limit': PROCESS_LIMIT, 'task_timeout_seconds': TASK_SECONDS,
              'run_limit_seconds': MAX_RUN_SECONDS, 'all_selected_finished': False}
    _save_new(report_path, report)
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {'PATH', 'SYSTEMROOT', 'WINDIR', 'USERPROFILE', 'LOCALAPPDATA', 'PROGRAMDATA', 'TEMP', 'TMP'}}
    env.update(PHOTOHOUSE_NO_DOTENV='1', PYTHONDONTWRITEBYTECODE='1')
    deadline = time.monotonic() + MAX_RUN_SECONDS
    try:
        for item in snapshot['items']:
            require(not os.path.lexists(config['stop_file']), 'stop_requested')
            if (item['state'] != 'pending' or item['cancel_requested']
                    or item['retry_count'] >= 3 or not item['due']):
                report['skipped'].append({'task_id': item['task_id'], 'state': item['state']})
                continue
            require(time.monotonic() + TASK_SECONDS <= deadline, 'run_budget_exhausted')
            require(read_config(config_path)[1] == digest, 'config_changed')
            result_path = report_path.with_name(report_path.name + '.' + str(item['task_id']) + '.json')
            require(not os.path.lexists(result_path), 'new_private_report_required')
            argv = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--config', str(config_path),
                    '--bounded-task', str(item['task_id']), '--config-sha256', digest, '--result', str(result_path)]
            exit_code = launch(api, sys.executable, argv, env, str(SERVER), timeout_seconds=TASK_SECONDS,
                memory_limit=MEMORY_LIMIT, process_limit=PROCESS_LIMIT, minimum_free_ram=FREE_RAM_FLOOR)
            require(exit_code == 0, 'child_interrupted_inspect_owned_claim')
            result = _read_result(result_path)
            require(result.get('task_id') == item['task_id'] and
                (result.get('outcome') in {'generated', 'existing_preserved'} or
                 result.get('state') in {'pending', 'failed'}), 'child_report_invalid')
            report['results'].append(result)
            _update_owned(report_path, report, nonce)
        latest = preflight(config)
        report['all_selected_finished'] = all(item['state'] == 'finished' for item in latest['items'])
        report['state'] = 'attempts_finished'
    except Exception:
        report['state'] = 'stopped_requires_review'
        _update_owned(report_path, report, nonce)
        raise
    _update_owned(report_path, report, nonce)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--bounded-task', type=int)
    parser.add_argument('--config-sha256')
    parser.add_argument('--result', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.bounded_task is not None:
            require(not args.execute and args.report is None and args.config_sha256 is not None
                    and args.result is not None, 'invalid_mode')
            task_child(args.config, args.config_sha256, args.bounded_task, args.result)
        else:
            require(args.config_sha256 is None and args.result is None
                and (args.report is not None if args.execute else args.report is None), 'invalid_mode')
            print(json.dumps(run(args.config, execute=args.execute, report_path=args.report)))
        return 0
    except Exception:
        print(json.dumps({'operation_status': 'refused_or_interrupted',
            'processing_may_have_started': bool(args.execute or args.bounded_task is not None),
            'inspect_report_before_retry': True, 'error_code': 'caption_worker_refused_or_interrupted'}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

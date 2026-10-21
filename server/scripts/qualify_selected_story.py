"""Run an explicitly requested, synthetic-only native selected-story rehearsal.

Importing this module is inert. Execution is Windows-only and uses nested Job
Objects: an outer Job owns this qualifier; the provider's Job owns its worker
and descendants. This is stage-one source qualification, not deployment or model
acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import sys
import time
import uuid

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / 'backend'))
sys.path.insert(0, str(SERVER / 'scripts'))

FEATURE_BASE_COMMIT = '31083f72b0d20e7c0c55f2faea5e4181eea1ff2e'
REPORT_NAME = 'selected-story-qualification.json'
MAX_REPORT_BYTES = 4096
FAILURE_NAME = 'selected-story-qualification-failure.json'
TOTAL_SECONDS = 120
MEMORY_LIMIT = 2 * 1024**3
PROCESS_LIMIT = 8
FREE_RAM_FLOOR = 8 * 1024**3
MODEL = 'synthetic-native-qualification'
CASES = (
    'providers_default_off_until_explicit_enable',
    'disabled_provider_prepare_is_inert',
    'real_provider_valid_generated_narrative',
    'real_provider_cancellation_and_job_cleanup',
    'real_provider_active_scope_expiry_and_job_cleanup',
    'real_provider_preflight_expired_scope_refusal',
    'real_provider_wrong_scope_refusal',
    'real_provider_lingering_descendant_cleanup',
    'private_exchange_acl_and_file_ipc',
)


def _refuse():
    raise ValueError('qualification_refused')


def _direct_directory(path):
    import stat
    info = path.lstat()
    if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & 0x400):
        _refuse()


def _validate_output(value):
    path = Path(value)
    if ('?' in str(path) or '#' in str(path) or not path.is_absolute()
            or '..' in path.parts or os.path.lexists(path)
            or path.parent.resolve(strict=True) != path.parent):
        _refuse()
    win = PureWindowsPath(str(path))
    if win.anchor.startswith(('\\\\', '//')):
        _refuse()
    for parent in (path.parent, *path.parent.parents):
        _direct_directory(parent)
    from app.access.private_storage import require_private_directory
    require_private_directory(path.parent)
    return path


def _interpreter_digest():
    digest = hashlib.sha256()
    with open(sys.executable, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _source_identity(expected_commit, *, package_root=None, script_path=None):
    if type(expected_commit) is not str or not re.fullmatch(r'[0-9a-f]{40}', expected_commit):
        _refuse()
    root = Path(package_root) if package_root is not None else SERVER
    script = Path(script_path) if script_path is not None else Path(__file__).resolve()
    try:
        manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
        if (type(manifest) is not dict or manifest.get('source_commit') != expected_commit
                or type(manifest.get('files')) is not dict):
            _refuse()
        digest = manifest['files'].get('scripts/qualify_selected_story.py')
        if (type(digest) is not str or not re.fullmatch(r'[0-9a-f]{64}', digest)
                or hashlib.sha256(script.read_bytes()).hexdigest() != digest):
            _refuse()
    except (OSError, UnicodeError, ValueError, TypeError):
        _refuse()
    return expected_commit


def _write_report(path, value):
    from app.access.private_storage import require_private_file
    raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode('ascii')
    if len(raw) > MAX_REPORT_BYTES:
        _refuse()
    with path.open('xb') as stream:
        os.chmod(path, 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require_private_file(path)


def _bundle(operation_id):
    return {
        'version': 3,
        'library_id': 'synthetic-library',
        'target': {'type': 'draft', 'id': operation_id, 'revision': 0},
        'selection_revision': 'a' * 64,
        'language': 'en',
        'title': 'A small garden story',
        'theme': 'planting together',
        'chapters': [{'id': 'chapter-1', 'title': 'Planting beans', 'narration': '',
                      'asset_ids': ['synthetic-asset'],
                      'evidence_ids': ['synthetic-note']}],
        'sources': [{'id': 'synthetic-note', 'kind': 'family',
                     'source_kind': 'family_note', 'text': 'We planted beans together.',
                     'asset_id': None, 'author': 'Synthetic relative'}],
        'recent_turns': [], 'instructions': 'Keep it brief.',
    }


def _worker_code():
    # One source line is required by NativeStoryLaunch's control-character rule.
    return ("import json,os,subprocess,sys,time; "
            "q=json.load(open(os.environ['PHOTOHOUSE_NATIVE_STORY_REQUEST'],encoding='utf-8')); "
            "assert q['operation_id']==os.environ['PHOTOHOUSE_NATIVE_STORY_OPERATION']; "
            "g=q['generation']; "
            "time.sleep(20) if g['model']=='synthetic-slow' else None; "
            "subprocess.Popen([sys.executable,'-I','-B','-c','import time;time.sleep(60)'], "
            "stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL, "
            "close_fds=True) if g['model']=='synthetic-descendant' else None; "
            "r={'version':1,'title':'A small garden story','chapters':[{'id':'chapter-1', "
            "'narration':'We planted beans together.','source_ids':['synthetic-note']}], "
            "'questions':[],'needs_review':True}; "
            "json.dump({'version':1,'operation_id':q['operation_id'],'model':g['model']," 
            "'result':r},open(os.environ['PHOTOHOUSE_NATIVE_STORY_RESPONSE'],'x',encoding='utf-8'), "
            "ensure_ascii=False,separators=(',',':'))")


async def _case_run(provider, operation_id, *, seconds=12, invalidation=None):
    import threading
    from app.access.selected_story_operations import PreparationScope
    event = invalidation or threading.Event()
    scope = PreparationScope(operation_id, time.monotonic() + seconds, event, time.monotonic)
    return await provider.prepare(_bundle(operation_id), scope), scope


def _run_native(target, source_commit):
    import asyncio
    import tempfile
    import threading
    from unittest.mock import patch
    from app.access.private_storage import require_private_directory
    from app.access.selected_story_native import NativeStoryLaunch, NativeStoryProcessOwner
    from app.access.selected_story_process import ProcessSelectedStoryError, ProcessSelectedStoryProvider
    from app.access.selected_story_operations import PreparationScope
    from bounded_windows_job import CheckRefused, WindowsAPI

    if sys.platform != 'win32' or os.name != 'nt':
        raise CheckRefused('windows_required')
    proof = WindowsAPI().consume_job_proof()
    required_job_flags = 0x2000 | 0x0200 | 0x0008
    if (proof['memory_limit'] != MEMORY_LIMIT or proof['process_limit'] != PROCESS_LIMIT
            or proof['flags'] & required_job_flags != required_job_flags):
        raise CheckRefused('outer_job_proof_mismatch')
    import inspect
    if (inspect.signature(ProcessSelectedStoryProvider).parameters['enabled'].default is not False
            or inspect.signature(NativeStoryProcessOwner).parameters['enabled'].default is not False):
        raise CheckRefused('default_off_contract_failed')
    target = Path(target)
    require_private_directory(target)
    started = time.monotonic()
    phase = ['native_setup']
    class RecordingWindowsAPI(WindowsAPI):
        def __init__(self):
            super().__init__()
            self.events = []
            self.resumed = threading.Event()
            self.job = None

        def create_job(self, memory, processes):
            self.job = super().create_job(memory, processes)
            return self.job

        def resume(self, thread):
            result = super().resume(thread)
            if result:
                self.resumed.set()
            return result

        def active_processes(self, job):
            count = super().active_processes(job)
            self.events.append(('active_processes', count))
            return count

        def wait_process(self, process, milliseconds):
            state = super().wait_process(process, milliseconds)
            self.events.append(('root_wait', state))
            return state

        def terminate_job(self, job):
            self.events.append(('terminate_job',))
            return super().terminate_job(job)

    native_apis = []
    def kernel_factory():
        api = RecordingWindowsAPI()
        native_apis.append(api)
        return api

    async def wait_resumed_api(before, case):
        deadline = time.monotonic() + 8
        while len(native_apis) <= before and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        if len(native_apis) <= before:
            raise CheckRefused(case + '_kernel_not_created')
        api = native_apis[before]
        if not await asyncio.to_thread(api.resumed.wait, max(0, deadline - time.monotonic())):
            raise CheckRefused(case + '_worker_not_resumed')
        return api

    system_root = os.environ.get('SystemRoot')
    if not system_root:
        raise CheckRefused('system_root_unavailable')
    executable = str(Path(sys.executable).resolve())
    launch = NativeStoryLaunch(
        executable, hashlib.sha256(Path(executable).read_bytes()).hexdigest(),
        (executable, '-I', '-B', '-c', _worker_code()), str(target),
        {'PATH': str(Path(executable).parent), 'SYSTEMROOT': system_root,
         'WINDIR': system_root, 'TEMP': str(target), 'TMP': str(target),
         'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'},
        memory_limit=MEMORY_LIMIT, process_limit=PROCESS_LIMIT,
        minimum_free_ram=FREE_RAM_FLOOR)

    created_exchange = []
    original_mkdtemp = tempfile.mkdtemp
    def checked_mkdtemp(*args, **kwargs):
        result = original_mkdtemp(*args, **kwargs)
        require_private_directory(result)
        created_exchange.append(result)
        return result

    async def run_cases():
        phase[0] = 'default_off'
        disabled = ProcessSelectedStoryProvider(launch, MODEL, kernel_factory=kernel_factory,
                                                enabled=False, timeout=10, cleanup_seconds=4)
        disabled_id = str(uuid.uuid4())
        disabled_scope = PreparationScope(disabled_id, time.monotonic() + 10,
                                          threading.Event(), time.monotonic)
        before_apis, before_exchanges = len(native_apis), len(created_exchange)
        try:
            await disabled.prepare(_bundle(disabled_id), disabled_scope)
        except ProcessSelectedStoryError as error:
            if error.category != 'disabled':
                raise CheckRefused('disabled_provider_case_failed') from None
        else:
            raise CheckRefused('disabled_provider_not_refused')
        if len(native_apis) != before_apis or len(created_exchange) != before_exchanges:
            raise CheckRefused('disabled_provider_had_side_effect')
        await disabled.close()

        phase[0] = 'valid_exchange'
        good = ProcessSelectedStoryProvider(launch, MODEL, kernel_factory=kernel_factory,
                                             enabled=True, timeout=25, cleanup_seconds=4)
        # Force the exchange into this explicitly private, ACL-checked directory.
        tempfile.tempdir = str(target)
        with patch('tempfile.mkdtemp', checked_mkdtemp):
            result, scope = await _case_run(good, str(uuid.uuid4()))
            if result['chapters'][0]['source_ids'] != ['synthetic-note']:
                raise CheckRefused('narrative_case_failed')
            if await good.stop_and_reconcile(scope) is not True:
                raise CheckRefused('valid_cleanup_failed')
            await good.close()

            # Invalidate a live worker only after native resume and real Job inventory.
            phase[0] = 'running_cancellation'
            cancelled = ProcessSelectedStoryProvider(launch, 'synthetic-slow',
                kernel_factory=kernel_factory, enabled=True, timeout=25, cleanup_seconds=4)
            event = threading.Event()
            op_id = str(uuid.uuid4())
            previous_api_count = len(native_apis)
            task = asyncio.create_task(_case_run(cancelled, op_id, seconds=25, invalidation=event))
            api = await wait_resumed_api(previous_api_count, 'cancel')
            if api.active_processes(api.job) < 1:
                raise CheckRefused('cancel_worker_not_in_job')
            other = PreparationScope(str(uuid.uuid4()), time.monotonic() + 10,
                                     threading.Event(), time.monotonic)
            if await cancelled.stop_and_reconcile(other) is not False:
                raise CheckRefused('wrong_scope_cleanup_not_refused')
            if api.active_processes(api.job) < 1:
                raise CheckRefused('wrong_scope_signalled_owned_job')
            event.set()
            try:
                await asyncio.wait_for(task, 8)
            except ProcessSelectedStoryError as error:
                if error.category != 'cancelled':
                    raise CheckRefused('cancel_case_failed') from None
            except asyncio.TimeoutError:
                raise CheckRefused('cancel_case_timeout') from None
            else:
                raise CheckRefused('cancel_not_observed')
            active = cancelled._active
            if active is None or await cancelled.stop_and_reconcile(active.scope) is not True:
                raise CheckRefused('cancel_cleanup_failed')
            if (('terminate_job',) not in api.events
                    or ('active_processes', 0) not in api.events):
                raise CheckRefused('cancel_job_not_drained')
            await cancelled.close()

            # A live operation deadline must also terminate its owned worker.
            phase[0] = 'running_expiry'
            expiring = ProcessSelectedStoryProvider(launch, 'synthetic-slow',
                kernel_factory=kernel_factory, enabled=True, timeout=25, cleanup_seconds=4)
            previous_api_count = len(native_apis)
            expiry_task = asyncio.create_task(_case_run(expiring, str(uuid.uuid4()), seconds=6))
            api = await wait_resumed_api(previous_api_count, 'expiry')
            try:
                await asyncio.wait_for(expiry_task, 15)
            except ProcessSelectedStoryError as error:
                if error.category != 'cancelled':
                    raise CheckRefused('expiry_case_failed') from None
            else:
                raise CheckRefused('expiry_not_observed')
            active = expiring._active
            if active is None or await expiring.stop_and_reconcile(active.scope) is not True:
                raise CheckRefused('expiry_cleanup_failed')
            if (('terminate_job',) not in api.events
                    or ('active_processes', 0) not in api.events):
                raise CheckRefused('expiry_job_not_drained')
            await expiring.close()

            phase[0] = 'preflight_expiry'
            expired_provider = ProcessSelectedStoryProvider(launch, MODEL,
                kernel_factory=kernel_factory, enabled=True, timeout=10, cleanup_seconds=4)
            expired_id = str(uuid.uuid4())
            expired_scope = PreparationScope(expired_id, time.monotonic() - 1,
                                               threading.Event(), time.monotonic)
            try:
                await expired_provider.prepare(_bundle(expired_id), expired_scope)
            except ProcessSelectedStoryError as error:
                if error.category != 'cancelled':
                    raise CheckRefused('expired_scope_case_failed') from None
            else:
                raise CheckRefused('expired_scope_not_refused')
            await expired_provider.close()

            phase[0] = 'wrong_scope'
            wrong_provider = ProcessSelectedStoryProvider(launch, MODEL,
                kernel_factory=kernel_factory, enabled=True, timeout=10, cleanup_seconds=4)
            wrong_id, bundle_id = str(uuid.uuid4()), str(uuid.uuid4())
            wrong_scope = PreparationScope(wrong_id, time.monotonic() + 10,
                                            threading.Event(), time.monotonic)
            try:
                await wrong_provider.prepare(_bundle(bundle_id), wrong_scope)
            except ProcessSelectedStoryError as error:
                if error.category != 'invalid_input':
                    raise CheckRefused('wrong_scope_case_failed') from None
            else:
                raise CheckRefused('wrong_scope_not_refused')
            await wrong_provider.close()

            phase[0] = 'lingering_descendant'
            descendant = ProcessSelectedStoryProvider(launch, 'synthetic-descendant',
                kernel_factory=kernel_factory, enabled=True, timeout=20, cleanup_seconds=4)
            result, scope = await _case_run(descendant, str(uuid.uuid4()), seconds=20)
            if result['chapters'][0]['source_ids'] != ['synthetic-note']:
                raise CheckRefused('descendant_case_failed')
            owner = descendant._active.owner if descendant._active else None
            api = native_apis[-1] if native_apis else None
            if (owner is None or api is None
                    or ('root_wait', 'exited') not in api.events
                    or not any(event[0] == 'active_processes' and event[1] > 0 for event in api.events)
                    or ('terminate_job',) not in api.events):
                raise CheckRefused('descendant_not_observed')
            if await descendant.stop_and_reconcile(scope) is not True:
                raise CheckRefused('descendant_cleanup_failed')
            await descendant.close()
        if not created_exchange or any(Path(path).exists() for path in created_exchange):
            raise CheckRefused('exchange_not_disposed')
        return True

    try:
        asyncio.run(run_cases())
    except Exception as error:
        reason = str(error) if isinstance(error, CheckRefused) and re.fullmatch(r'[a-z_]{1,80}', str(error)) else 'native_case_failed'
        _write_report(target / FAILURE_NAME, {'status': 'failed', 'synthetic_only': True,
            'source_commit': source_commit, 'phase': phase[0], 'reason': reason})
        raise
    finally:
        tempfile.tempdir = None
    if time.monotonic() - started > TOTAL_SECONDS - 15:
        raise CheckRefused('qualification_wall_limit')
    report = {
        'status': 'passed', 'synthetic_only': True, 'native_windows': True,
        'feature_base_commit': FEATURE_BASE_COMMIT, 'source_commit': source_commit,
        'interpreter_sha256': _interpreter_digest(),
        'cases_passed': list(CASES), 'outer_job_proof': True,
        'production_database_opened': False, 'family_media_opened': False,
        'production_model_or_provider_used': False, 'network_or_listener_used': False,
        'remaining_gates': ['API crash and service restart behavior',
            'production worker and model locality', 'GPU and performance qualification',
            'deployment, installed service, and family/device acceptance'],
    }
    _write_report(target / REPORT_NAME, report)
    return report


def _child(target, source_commit):
    from bounded_windows_job import CheckRefused, WindowsAPI, run_bounded
    system_root = os.environ.get('SystemRoot')
    if not system_root:
        raise CheckRefused('system_root_unavailable')
    executable = str(Path(sys.executable).resolve())
    env = {'PATH': str(Path(executable).parent), 'SYSTEMROOT': system_root,
           'WINDIR': system_root, 'TEMP': str(target.parent), 'TMP': str(target.parent),
           'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    program = (f"import runpy; runpy.run_path({str(Path(__file__).resolve())!r}, "
               f"run_name='photohouse_selected_story_qualification')['_run_native'](" 
               f"{str(target)!r},{source_commit!r})")
    code = run_bounded(WindowsAPI(), executable, [executable, '-I', '-B', '-c', program],
        env, str(target.parent), timeout_seconds=TOTAL_SECONDS - 15,
        memory_limit=MEMORY_LIMIT, process_limit=PROCESS_LIMIT,
        minimum_free_ram=FREE_RAM_FLOOR, require_child_job_proof=True,
        terminate_descendants_after_exit=True, descendant_grace_seconds=5)
    if code != 0:
        raise CheckRefused('qualification_child_failed')
    from app.access.private_storage import require_private_file
    report_path = target / REPORT_NAME
    require_private_file(report_path)
    with report_path.open('rb') as stream:
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if not 0 < len(raw) <= MAX_REPORT_BYTES:
        raise CheckRefused('report_unavailable')
    report = json.loads(raw)
    if (type(report) is not dict or report.get('status') != 'passed'
            or report.get('source_commit') != source_commit
            or report.get('feature_base_commit') != FEATURE_BASE_COMMIT
            or report.get('interpreter_sha256') != _interpreter_digest()
            or report.get('cases_passed') != list(CASES)):
        raise CheckRefused('report_unavailable')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true', help='explicitly execute the native rehearsal')
    parser.add_argument('--commit', required=True, help='full source commit from manifest.json')
    parser.add_argument('--out', required=True, help='new absolute private output directory')
    args = parser.parse_args(argv)
    if not args.execute:
        _refuse()
    target = _validate_output(args.out)
    if os.name != 'nt':
        _refuse()
    source_commit = _source_identity(args.commit)
    target.mkdir(mode=0o700)
    from app.access.private_storage import require_private_directory
    require_private_directory(target)
    try:
        result = _child(target, source_commit)
    except Exception:
        failure = {'status': 'failed', 'synthetic_only': True,
                   'feature_base_commit': FEATURE_BASE_COMMIT,
                   'source_commit': source_commit,
                   'interpreter_sha256': _interpreter_digest(),
                   'failure_class': 'qualification_failed'}
        try:
            if target.is_dir():
                _write_report(target / FAILURE_NAME, failure)
        except Exception:
            pass
        raise
    print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","synthetic_only":true}', file=sys.stderr)
        raise SystemExit(2) from None

#!/usr/bin/env python3
"""Explicit library-bound SigLIP2 text service; no-argument invocation is inert.

The operator owns the persistent supervisor, inherited bounded Windows Job,
private configuration, readiness check and stop/rollback. This child never
installs a task, enables Search, changes an index, or substitutes another model.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import uuid
import math

SERVER = Path(__file__).resolve().parents[1]
SOURCE_ROOT = SERVER.parent
SCHEMA = 'photohouse.library_text_provider.v1'
FIELDS = frozenset({'schema', 'model_directory', 'artifacts', 'package_versions',
    'binding', 'credential_file', 'port', 'preparation_source_sha256',
    'model_receipt_sha256'})
DIGEST = re.compile(r'[0-9a-f]{64}\Z', re.ASCII)
JOB_LIMITS = {'flags': 0x2208, 'memory_limit': 8 * 1024**3, 'process_limit': 4}
MINIMUM_FREE_RAM = 8 * 1024**3


class ProviderRefused(ValueError):
    def __init__(self):
        super().__init__('library_provider_unavailable')


class Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise ProviderRefused()


def request_budget(value):
    if (type(value) not in (int, float) or not math.isfinite(float(value))
            or not 0 < float(value) <= 30):
        raise ProviderRefused()
    return float(value)


def document_sha256(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')).hexdigest()


def _backend():
    # Explicit operations only. No backend, ML or native module imports on the
    # inert path. The reviewed package supplies this exact sibling backend.
    backend = str(SERVER / 'backend')
    if backend not in sys.path:
        sys.path.insert(0, backend)


def require_windows():
    if os.name != 'nt':
        raise ProviderRefused()


def native_admission():
    require_windows()
    scripts = str(SERVER / 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from bounded_windows_job import WindowsAPI
    api = WindowsAPI()
    proof = api.consume_job_proof()
    if (type(proof) is not dict or set(proof) != set(JOB_LIMITS)
            or any(type(proof[k]) is not int or proof[k] != v
                   for k, v in JOB_LIMITS.items())):
        raise ProviderRefused()
    free = api.free_ram()
    if type(free) is not int or free < MINIMUM_FREE_RAM:
        raise ProviderRefused()


def load_configuration(path, expected_sha256, *, serving=False):
    """Read one private, canonically pinned library-provider selection."""
    if (not isinstance(path, Path) or not path.is_absolute() or '..' in path.parts
            or type(expected_sha256) is not str or not DIGEST.fullmatch(expected_sha256)):
        raise ProviderRefused()
    _backend()
    from app.access.model_deployment import _load_private_document
    from app.access.semantic_encoder import JointSpaceBinding
    from app.access.visual_candidates import VectorSpaceIdentity
    import qualify_multilingual_scenes as qualification
    value = _load_private_document(path, source_root=SOURCE_ROOT)
    if (type(value) is not dict or set(value) != FIELDS or value.get('schema') != SCHEMA
            or document_sha256(value) != expected_sha256
            or value['artifacts'] != qualification.OFFICIAL_ARTIFACTS
            or value['package_versions'] != qualification.EXPECTED_PACKAGES
            or type(value['port']) is not int or not 1024 <= value['port'] <= 65535
            or any(type(value[k]) is not str or not DIGEST.fullmatch(value[k])
                   for k in ('preparation_source_sha256', 'model_receipt_sha256'))):
        raise ProviderRefused()
    model_directory = value['model_directory']
    if (type(model_directory) is not str or not Path(model_directory).is_absolute()
            or '..' in Path(model_directory).parts
            or Path(model_directory).is_relative_to(SOURCE_ROOT)):
        raise ProviderRefused()
    prep = SERVER / 'scripts/library_image_inputs.py'
    if hashlib.sha256(prep.read_bytes()).hexdigest() != value['preparation_source_sha256']:
        raise ProviderRefused()
    raw_binding = value['binding']
    if type(raw_binding) is not dict or set(raw_binding) != {
            'image_identity', 'text_identity', 'qualification_sha256'}:
        raise ProviderRefused()
    binding = JointSpaceBinding(VectorSpaceIdentity(**raw_binding['image_identity']),
        VectorSpaceIdentity(**raw_binding['text_identity']), raw_binding['qualification_sha256'])
    if binding.image_identity.dimension != 768 or binding.text_identity.dimension != 768:
        raise ProviderRefused()
    credential = value['credential_file']
    if credential is not None and (type(credential) is not str
            or not Path(credential).is_absolute() or '..' in Path(credential).parts
            or Path(credential).is_relative_to(SOURCE_ROOT)):
        raise ProviderRefused()
    token = None
    if serving:
        if credential is None:
            raise ProviderRefused()
        secret = _load_private_document(Path(credential), source_root=SOURCE_ROOT)
        if (type(secret) is not dict or set(secret) != {'token'}
                or type(secret['token']) is not str
                or re.fullmatch(r'[A-Za-z0-9_-]{32,128}', secret['token'], re.ASCII) is None):
            raise ProviderRefused()
        token = secret['token']
    return value, binding, token


def load_model(config):
    import torch
    torch.set_num_threads(2)
    torch.set_num_interop_threads(1)
    from library_siglip import LibrarySiglipModel
    # This is the same constructor used by R167, with its original library
    # image recipe and unchanged SigLIP2 text tower. No base-model fallback.
    return LibrarySiglipModel.load(model_directory=config['model_directory'],
        artifacts=config['artifacts'], package_versions=config['package_versions'],
        preparation_source_sha256=config['preparation_source_sha256'])


def checked_model(config, binding):
    model = load_model(config)
    model.verify()
    if (model.image_identity != binding.image_identity
            or model.text_identity != binding.text_identity
            or document_sha256(model.receipt()) != config['model_receipt_sha256']):
        raise ProviderRefused()
    model.bind(binding)
    model.verify()
    from semantic_siglip import query_policy_binding_for
    from app.access.search_policy_binding import verify_query_policy_binding
    policy = verify_query_policy_binding(query_policy_binding_for(model))
    return model, policy


def supervise(args, *, api=None, monotonic=time.monotonic, sleep=time.sleep):
    """Retain one fixed library-service Job until this scheduled-task exits.

    This is a production lifetime, not a qualification timeout extension. Root
    owns task installation, one-shot readiness, successful persistent handoff,
    and stopping this exact task on readiness/cutover failure. Closing this
    supervisor's Job handle kills only its assigned service descendants.
    """
    require_windows()
    seconds = request_budget(getattr(args, 'request_seconds', 2.0))
    if (str(uuid.UUID(args.service_id)) != args.service_id
            or any(type(x) is not str or not DIGEST.fullmatch(x)
                   for x in (args.entry_sha256, args.python_sha256, args.configuration_sha256))
            or not isinstance(args.ownership_record, Path)
            or not isinstance(args.cache_directory, Path)):
        raise ProviderRefused()
    scripts = str(SERVER / 'scripts')
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    from bounded_windows_job import WindowsAPI
    _backend()
    from app.access.private_storage import require_private_directory, require_private_file
    if api is None:
        api = WindowsAPI()
    free = api.free_ram()
    if type(free) is not int or free < MINIMUM_FREE_RAM:
        raise ProviderRefused()
    entry = Path(__file__).resolve(strict=True)
    executable = str(Path(sys.executable).resolve(strict=True))
    record = args.ownership_record
    if (not record.is_absolute() or '..' in record.parts
            or record.is_relative_to(SOURCE_ROOT)
            or record.parent.resolve(strict=True) != record.parent):
        raise ProviderRefused()
    require_private_directory(record.parent)
    cache = args.cache_directory
    if (not cache.is_absolute() or '..' in cache.parts
            or cache.is_relative_to(SOURCE_ROOT) or cache.resolve(strict=True) != cache):
        raise ProviderRefused()
    require_private_directory(cache)
    if record.exists() or record.is_symlink():
        raise ProviderRefused()
    def pins():
        if (hashlib.sha256(entry.read_bytes()).hexdigest() != args.entry_sha256
                or api.sha256_file(executable, deadline=monotonic()+30) != args.python_sha256):
            raise ProviderRefused()
    pins()
    # Fail malformed/changed private selections before creating a child. No
    # model is imported or constructed in the persistent supervisor.
    config, binding, token = load_configuration(args.configuration,
        args.configuration_sha256, serving=True)
    argv = [executable, '-I', '-B', str(entry), 'serve', '--configuration',
        str(args.configuration), '--configuration-sha256', args.configuration_sha256,
        '--request-seconds', str(seconds)]
    # Use a closed native environment, never a copied arbitrary PYTHONPATH,
    # Python user-site, HuggingFace token, proxy or provider override.
    system_root = os.environ.get('SystemRoot')
    if type(system_root) is not str or not Path(system_root).is_absolute():
        raise ProviderRefused()
    environment = {'SystemRoot': system_root, 'WINDIR': system_root,
        'PATH': str(Path(executable).parent)+os.pathsep+str(Path(system_root)/'System32'),
        'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
        'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
        'CUDA_VISIBLE_DEVICES': '', 'TEMP': str(cache), 'TMP': str(cache),
        'OMP_NUM_THREADS': '2', 'MKL_NUM_THREADS': '2'}
    job = process = thread = proof = None
    assigned = False
    def drain():
        deadline = monotonic()+5
        while True:
            count = api.active_processes(job)
            if type(count) is not int or count < 0:
                raise ProviderRefused()
            if count == 0:
                return
            if monotonic() >= deadline:
                raise ProviderRefused()
            sleep(0.05)
    try:
        job = api.create_job(JOB_LIMITS['memory_limit'], JOB_LIMITS['process_limit'])
        if not job:
            raise ProviderRefused()
        created = api.create_suspended_proven(executable, argv, environment, str(entry.parent), job)
        if type(created) is not tuple or len(created) != 4:
            raise ProviderRefused()
        process, thread, pid, proof = created
        if not process or not thread or not proof or type(pid) is not int or pid <= 0:
            raise ProviderRefused()
        if not api.assign(job, process):
            raise ProviderRefused()
        assigned = True
        pins()
        current, current_binding, current_token = load_configuration(args.configuration,
            args.configuration_sha256, serving=True)
        if (document_sha256(current) != document_sha256(config) or current_binding != binding
                or not hmac.compare_digest(current_token, token)):
            raise ProviderRefused()
        if not api.resume(thread):
            raise ProviderRefused()
        ownership = {'schema': 'photohouse.library_provider_owned_process.v1',
            'service_id': args.service_id, 'state': 'CHILD_STARTED_READINESS_NOT_ESTABLISHED',
            'supervisor_pid': os.getpid(),
            'supervisor_birthtime_100ns': api._process_creation_time(api.k32.GetCurrentProcess()),
            'child_pid': pid, 'child_birthtime_100ns': api._process_creation_time(process),
            'configuration_sha256': args.configuration_sha256,
            'entry_sha256': args.entry_sha256, 'python_sha256': args.python_sha256,
            'binding_sha256': binding.binding_sha256, 'limits': dict(JOB_LIMITS),
            'readiness_established': False, 'activation_performed': False}
        descriptor = os.open(record, os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os, 'O_BINARY', 0), 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write((json.dumps(ownership, sort_keys=True)+'\n').encode())
            stream.flush();os.fsync(stream.fileno())
        require_private_file(record);require_private_directory(record.parent)
        while True:
            outcome = api.wait_process(process, 1000)
            if outcome == 'exited':
                return api.exit_code(process)
            if outcome != 'timeout':
                raise ProviderRefused()
    finally:
        # A Root task stop may terminate the supervisor rather than deliver a
        # Python exception. The OS then enforces KILL_ON_JOB_CLOSE; actual Root
        # cleanup/readback is still required and is never inferred here.
        cleanup_ok = True
        try:
            if process:
                cleanup_ok = bool(api.terminate_job(job) if assigned else api.terminate_process(process))
                cleanup_ok = (api.wait_process(process, 5000) == 'exited') and cleanup_ok
            if assigned:
                drain()
        except BaseException:
            cleanup_ok = False
        for handle in (thread, process, proof, job):
            if handle:
                try:
                    api.close(handle)
                except BaseException:
                    cleanup_ok = False
        if not cleanup_ok:
            raise ProviderRefused() from None


def run(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if not arguments:
        print(json.dumps({'status': 'library_provider_plan', 'models_loaded': False,
            'private_files_read': False, 'listener_started': False,
            'activation_performed': False, 'service_management': False}, sort_keys=True))
        return 0
    previous = logging.root.manager.disable
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('operation', choices=('probe', 'serve', 'supervise'))
        parser.add_argument('--configuration', type=Path, required=True)
        parser.add_argument('--configuration-sha256', required=True)
        parser.add_argument('--entry-sha256')
        parser.add_argument('--python-sha256')
        parser.add_argument('--ownership-record', type=Path)
        parser.add_argument('--cache-directory', type=Path)
        parser.add_argument('--service-id')
        parser.add_argument('--request-seconds', type=float, default=2.0)
        args = parser.parse_args(arguments)
        seconds = request_budget(args.request_seconds)
        if args.operation == 'supervise':
            logging.disable(logging.CRITICAL)
            return supervise(args)
        if any(x is not None for x in (args.entry_sha256, args.python_sha256,
                args.ownership_record, args.cache_directory, args.service_id)):
            raise ProviderRefused()
        native_admission()  # actual inherited Job and RAM before private/model work
        logging.disable(logging.CRITICAL)
        from qualify_semantic_pair import quiet_dependencies
        with quiet_dependencies():
            config, binding, token = load_configuration(args.configuration,
                args.configuration_sha256, serving=args.operation == 'serve')
            model, policy = checked_model(config, binding)
            current, current_binding, current_token = load_configuration(args.configuration,
                args.configuration_sha256, serving=args.operation == 'serve')
            if (document_sha256(current) != document_sha256(config)
                    or current_binding != binding
                    or (token is not None and (current_token is None
                        or not hmac.compare_digest(current_token, token)))):
                raise ProviderRefused()
        if args.operation == 'probe':
            print(json.dumps({'status': 'library_provider_probed',
                'model_receipt_sha256': document_sha256(model.receipt()),
                'binding_sha256': binding.binding_sha256, 'query_policy_binding': policy,
                'models_loaded': True, 'listener_started': False,
                'activation_performed': False, 'service_management': False}, sort_keys=True))
            return 0
        from app.access.semantic_provider_transport import create_provider_app
        import uvicorn
        application = create_provider_app(model, bearer_token=token, port=config['port'],
            seconds=seconds)
        # The persistent supervisor retains its Job handle for the entire
        # service lifetime. Returning from serve is not deployment success.
        uvicorn.run(application, host='127.0.0.1', port=config['port'], workers=1,
            access_log=False, log_config=None, proxy_headers=False, forwarded_allow_ips='',
            timeout_keep_alive=1, limit_concurrency=8, backlog=8,
            h11_max_incomplete_event_size=8192)
        return 0
    except Exception:
        print('{"error":"library_provider_unavailable"}', file=sys.stderr)
        return 2
    finally:
        logging.disable(previous)


if __name__ == '__main__':
    raise SystemExit(run())

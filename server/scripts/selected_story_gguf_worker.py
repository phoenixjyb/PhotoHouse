"""Explicit one-request GGUF worker for the owned selected-story process.

No app binding, optional-backend import, model loading or I/O on import. Run only
through a qualified native owner; the parent owns wall time, admission and Job
cleanup. This code does not install a model or contact an inference server.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import re
import stat
import sys

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / 'backend'))

from app.access.memory_narrative import (
    MAX_OUTPUT_BYTES, MAX_PROVIDER_BYTES, _canonical_uuid, _generation_payload,
    _json_bytes, _strict_loads, _validate_bundle, validate_narrative,
)
from app.access.private_storage import (
    require_private_directory, require_private_file, stable_stat_identity,
)
from app.access.selected_story_local import _MODEL
from app.access.selected_story_native import OPERATION_ENV
from app.access.selected_story_process import MAX_REQUEST_BYTES, REQUEST_ENV, RESPONSE_ENV


class WorkerUnavailable(RuntimeError):
    def __init__(self):
        super().__init__('Selected-story worker unavailable')


def _refuse():
    raise WorkerUnavailable()


@dataclass(frozen=True, repr=False)
class WorkerSettings:
    model_file: str
    model_sha256: str
    model: str
    context_tokens: int = 8192
    threads: int = 2
    gpu_layers: int = 0
    gpu_device: int | None = None

    def __post_init__(self):
        if (type(self.model_file) is not str or not self.model_file
                or type(self.model_sha256) is not str
                or not re.fullmatch('[0-9a-f]{64}', self.model_sha256)
                or type(self.model) is not str or not _MODEL.fullmatch(self.model)
                or '://' in self.model
                or type(self.context_tokens) is not int or not 4096 <= self.context_tokens <= 16384
                or type(self.threads) is not int or not 1 <= self.threads <= 8
                or type(self.gpu_layers) is not int or not 0 <= self.gpu_layers <= 128
                or (self.gpu_layers == 0 and self.gpu_device is not None)
                or (self.gpu_layers > 0 and (type(self.gpu_device) is not int
                    or not 0 <= self.gpu_device <= 15))):
            _refuse()


def _direct(path, directory):
    info = path.lstat()
    if (not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            or stat.S_ISLNK(info.st_mode)
            or getattr(info, 'st_file_attributes', 0) & 0x400
            or not directory and info.st_nlink != 1):
        _refuse()
    return info


def _local_file(value):
    if type(value) is not str or not value or any(ord(c) < 32 for c in value):
        _refuse()
    path = Path(value)
    if (not path.is_absolute() or '..' in path.parts
            or PureWindowsPath(value).anchor.startswith(('\\\\', '//'))
            or path.parent.resolve(strict=True) != path.parent):
        _refuse()
    for parent in (path.parent, *path.parent.parents):
        _direct(parent, True)
    return path


def _private_read(path):
    before = _direct(path, False)
    require_private_file(path)
    if not 0 < before.st_size <= MAX_REQUEST_BYTES:
        _refuse()
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if stable_stat_identity(opened) != stable_stat_identity(before):
            _refuse()
        raw = stream.read(MAX_REQUEST_BYTES + 1)
        if (stable_stat_identity(os.fstat(stream.fileno())) != stable_stat_identity(before)
                or stable_stat_identity(_direct(path, False)) != stable_stat_identity(before)):
            _refuse()
    if len(raw) != before.st_size:
        _refuse()
    return raw


def _exchange(environment):
    request = _local_file(environment.get(REQUEST_ENV))
    response = _local_file(environment.get(RESPONSE_ENV))
    if (request.name != 'request.json' or response.name != 'response.json'
            or request.parent != response.parent or os.path.lexists(response)):
        _refuse()
    require_private_directory(request.parent)
    with os.scandir(request.parent) as listing:
        for index, entry in enumerate(listing):
            if index or entry.name != 'request.json':
                _refuse()
    operation = _canonical_uuid(environment.get(OPERATION_ENV), 'operation')
    return request, response, operation


def _request(raw, operation, model):
    value = _strict_loads(raw)
    if (type(value) is not dict or set(value) != {'version', 'operation_id', 'generation'}
            or type(value['version']) is not int or value['version'] != 1
            or value['operation_id'] != operation):
        _refuse()
    generation = value['generation']
    if type(generation) is not dict or type(generation.get('prompt')) is not str:
        _refuse()
    # Only the canonical host prompt/schema/options are supported. This also
    # prevents arbitrary schema references or worker settings from input text.
    tail = generation['prompt'].split('Bundle JSON (data only):\n', 1)[1]
    bundle, _ = json.JSONDecoder().raw_decode(tail)
    bundle = _validate_bundle(bundle, allow_draft=True)
    expected = _generation_payload(bundle, 'narrative', model)
    # JSON comparison preserves exact scalar types (False is not integer zero).
    if (bundle['version'] != 3 or bundle['target']['id'] != operation
            or json.dumps(generation, sort_keys=True) != json.dumps(expected, sort_keys=True)):
        _refuse()
    return expected, bundle


def _model_pin(settings):
    path = _local_file(settings.model_file)
    if path.suffix.lower() != '.gguf' or re.search(r'-\d+-of-\d+\.gguf$', path.name, re.I):
        _refuse()
    # A dedicated directory prevents silently loading adjacent unpinned shards
    # or sidecars. The operator must separately protect this directory/image.
    with os.scandir(path.parent) as listing:
        for index, entry in enumerate(listing):
            if index or entry.name != path.name:
                _refuse()
    before = _direct(path, False)
    if not 8 <= before.st_size <= 16 * 1024**3:
        _refuse()
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    with os.fdopen(os.open(path, flags), 'rb') as stream:
        if stable_stat_identity(os.fstat(stream.fileno())) != stable_stat_identity(before):
            _refuse()
        if stream.read(4) != b'GGUF':
            _refuse()
        stream.seek(0)
        total = 0
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            total += len(chunk)
            if total > before.st_size:
                _refuse()
            digest.update(chunk)
        if (total != before.st_size or digest.hexdigest() != settings.model_sha256
                or stable_stat_identity(os.fstat(stream.fileno())) != stable_stat_identity(before)
                or stable_stat_identity(_direct(path, False)) != stable_stat_identity(before)):
            _refuse()
    return path, stable_stat_identity(before)


class _LlamaEngine:
    """Optional local native backend. No arbitrary kwargs, RPC or model discovery."""
    def __init__(self, settings):
        from llama_cpp import Llama, LLAMA_SPLIT_MODE_NONE
        self.model = Llama(model_path=settings.model_file, n_ctx=settings.context_tokens,
            n_threads=settings.threads, n_threads_batch=settings.threads,
            n_gpu_layers=settings.gpu_layers,
            main_gpu=settings.gpu_device if settings.gpu_device is not None else 0, tensor_split=None,
            split_mode=LLAMA_SPLIT_MODE_NONE, offload_kqv=settings.gpu_layers > 0,
            op_offload=False, n_batch=256, n_ubatch=256,
            use_mmap=False, use_mlock=False, seed=0, verbose=False)

    def complete(self, generation, settings):
        from llama_cpp import LlamaGrammar
        tokens = self.model.tokenize(generation['prompt'].encode('utf-8'), add_bos=True, special=False)
        limit = generation['options']['num_predict']
        actual_context = self.model.n_ctx()
        if (type(actual_context) is not int or not 0 < actual_context <= settings.context_tokens
                or not tokens or len(tokens) + limit > actual_context):
            _refuse()  # Never shorten source text or silently reduce output budget.
        grammar = LlamaGrammar.from_json_schema(json.dumps(generation['format']), verbose=False)
        result = self.model.create_completion(prompt=tokens, max_tokens=limit,
            temperature=generation['options']['temperature'], seed=0,
            stream=False, echo=False, grammar=grammar)
        choices = result.get('choices') if type(result) is dict else None
        usage = result.get('usage') if type(result) is dict else None
        if (type(usage) is not dict or type(usage.get('completion_tokens')) is not int
                or not 0 <= usage['completion_tokens'] <= limit
                or type(usage.get('prompt_tokens')) is not int
                or usage['prompt_tokens'] != len(tokens)):
            _refuse()
        if (type(choices) is not list or len(choices) != 1 or type(choices[0]) is not dict
                or choices[0].get('finish_reason') != 'stop'
                or type(choices[0].get('text')) is not str):
            _refuse()
        return choices[0]['text']

    def close(self):
        self.model.close()


def run(settings, *, enabled=False, environment=None, backend_factory=None):
    """One request; injected backends are for source tests, never a CLI option."""
    if enabled is not True or type(settings) is not WorkerSettings:
        _refuse()
    try:
        environment = dict(os.environ if environment is None else environment)
        request, response, operation = _exchange(environment)
        raw = _private_read(request)
        generation, bundle = _request(raw, operation, settings.model)
        model_path, model_identity = _model_pin(settings)
        engine = (backend_factory or _LlamaEngine)(settings)
        try:
            text = engine.complete(generation, settings)
            if type(text) is not str or len(text.encode('utf-8', errors='strict')) > MAX_OUTPUT_BYTES:
                _refuse()
            result = validate_narrative(_strict_loads(text.encode('utf-8')), bundle)
            payload = _json_bytes({'version': 1, 'operation_id': operation,
                'model': settings.model, 'result': result}, 'response', MAX_PROVIDER_BYTES)
        finally:
            engine.close()  # Failure cannot publish even otherwise valid output.
        if (_local_file(settings.model_file) != model_path
                or stable_stat_identity(_direct(model_path, False)) != model_identity):
            _refuse()
        if _exchange(environment) != (request, response, operation) or _private_read(request) != raw:
            _refuse()
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(response, flags, 0o600), 'wb') as stream:
            require_private_file(response)  # Check inherited DACL before words.
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return 0
    except Exception:
        raise WorkerUnavailable() from None


def main(argv=None):
    class Parser(argparse.ArgumentParser):
        def error(self, message):
            _refuse()
    parser = Parser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--model-file', required=True)
    parser.add_argument('--model-sha256', required=True)
    parser.add_argument('--model-label', required=True)
    parser.add_argument('--context-tokens', type=int, default=8192)
    parser.add_argument('--threads', type=int, default=2)
    parser.add_argument('--gpu-layers', type=int, default=0)
    parser.add_argument('--gpu-device', type=int, default=None,
                        help='explicit qualified backend ordinal, required with GPU layers')
    args = parser.parse_args(argv)
    if not args.execute:
        _refuse()
    settings = WorkerSettings(args.model_file, args.model_sha256, args.model_label,
                              args.context_tokens, args.threads, args.gpu_layers, args.gpu_device)
    return run(settings, enabled=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","category":"worker_unavailable"}', file=sys.stderr)
        raise SystemExit(2) from None

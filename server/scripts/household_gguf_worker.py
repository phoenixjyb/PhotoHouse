"""Explicit pinned CPU worker for story packets and local agent decisions.

No tool execution, networking, service, installation or backend loading on
import. The unchanged native owner supplies the private file exchange and Job.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import json

sys.dont_write_bytecode = True
SERVER = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SERVER / 'backend'), str(SERVER / 'scripts')]

import selected_story_gguf_worker as story
_STORY_RUN = story.run
_STORY_FAILURE_RECORD = story._failure_record
from app.access.agent_decision import generation, validate_state, validate_decision
from app.access.memory_narrative import (
    _generation_payload, _validate_bundle, validate_generated_narrative,
)


SAVED_STORY_FAILURE_EXIT_CODES = {
    'request': 80,
    'model_pin': 81,
    'backend_load': 82,
    'generation': 83,
    'output_validation': 84,
    'unchanged_narration': 85,
    'model_close': 86,
    'tokenize': 87,
    'context': 88,
    'grammar': 89,
    'completion': 90,
    'narrative': 91,
    'source_recheck': 92,
    'response_write': 93,
}


class SavedStoryWorkerFailure(story.WorkerUnavailable):
    """Closed, content-free saved-story failure passed through the worker CLI."""

    def __init__(self, phase):
        self.phase = phase if type(phase) is str and phase in SAVED_STORY_FAILURE_EXIT_CODES else 'request'
        RuntimeError.__init__(self, 'Saved-story worker unavailable')


def _failure_record(error):
    if type(error) is not SavedStoryWorkerFailure:
        return _STORY_FAILURE_RECORD(error)
    record = {'status': 'failed', 'category': 'worker_unavailable', 'phase': error.phase}
    return SAVED_STORY_FAILURE_EXIT_CODES[error.phase], json.dumps(record, separators=(',', ':'))


def _saved_story_narrative(settings, environment, request, response, operation,
                           raw, value, backend_factory):
    phase = 'request'
    try:
        if (type(value) is not dict or
                set(value) != {'version', 'kind', 'operation_id', 'bundle'} or
                type(value.get('version')) is not int or value['version'] != 1 or
                value.get('kind') != 'saved_story_narrative_v1' or
                value.get('operation_id') != operation):
            story._refuse(phase)
        bundle = _validate_bundle(value['bundle'])
        if (bundle['version'] not in {1, 4} or bundle['target']['type'] != 'story' or
                bundle['target']['id'] == operation):
            story._refuse(phase)
        expected = _generation_payload(bundle, 'narrative', settings.model)
        phase = 'model_pin'
        model_path, model_identity = story._model_pin(settings)
        phase = 'backend_load'
        engine = (backend_factory or story._LlamaEngine)(settings)
        try:
            phase = 'generation'
            output = engine.complete(expected, settings)
            phase = 'output_validation'
            if type(output) is not str or len(output.encode('utf-8')) > story.MAX_OUTPUT_BYTES:
                story._refuse(phase)
            decoded = story._strict_loads(output.encode('utf-8'))
            phase = 'narrative'
            try:
                result = validate_generated_narrative(decoded, bundle)
            except ValueError as error:
                if str(error) == 'story refinement returned unchanged narration':
                    raise SavedStoryWorkerFailure('unchanged_narration') from None
                raise
            phase = 'output_validation'
            payload = story._json_bytes({'version': 1, 'operation_id': operation,
                'model': settings.model, 'result': result}, 'response', story.MAX_PROVIDER_BYTES)
        except SavedStoryWorkerFailure:
            raise
        except story.WorkerUnavailable as error:
            failed_phase = getattr(error, 'phase', None)
            if type(failed_phase) is not str or failed_phase not in SAVED_STORY_FAILURE_EXIT_CODES:
                failed_phase = phase
            raise SavedStoryWorkerFailure(failed_phase) from None
        except Exception:
            raise SavedStoryWorkerFailure(phase) from None
        finally:
            phase = 'model_close'
            try:
                engine.close()
            except Exception:
                raise SavedStoryWorkerFailure('model_close') from None
        phase = 'source_recheck'
        if (story._local_file(settings.model_file) != model_path
                or story.stable_stat_identity(story._direct(model_path, False)) != model_identity
                or story._exchange(environment) != (request, response, operation)
                or story._private_read(request) != raw):
            story._refuse(phase)
        phase = 'response_write'
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(response, flags, 0o600), 'wb') as stream:
            story.require_private_file(response)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        return 0
    except SavedStoryWorkerFailure:
        raise
    except story.WorkerUnavailable as error:
        failed_phase = getattr(error, 'phase', None)
        if type(failed_phase) is not str or failed_phase not in SAVED_STORY_FAILURE_EXIT_CODES:
            failed_phase = phase
        raise SavedStoryWorkerFailure(failed_phase) from None
    except Exception:
        raise SavedStoryWorkerFailure(phase) from None


def run(settings, *, enabled=False, environment=None, backend_factory=None):
    if enabled is not True or type(settings) is not story.WorkerSettings:
        story._refuse()
    environment = dict(os.environ if environment is None else environment)
    request, response, operation = story._exchange(environment)
    raw = story._private_read(request)
    value = story._strict_loads(raw)
    if type(value) is dict and 'kind' not in value:
        # Existing story request/response and validators remain byte-compatible.
        return _STORY_RUN(settings, enabled=True, environment=environment,
                         backend_factory=backend_factory)
    if type(value) is dict and value.get('kind') == 'saved_story_narrative_v1':
        return _saved_story_narrative(settings, environment, request, response,
                                      operation, raw, value, backend_factory)
    phase = 'request'
    try:
        if (type(value) is not dict or set(value) != {'version', 'kind', 'operation_id', 'state'}
                or type(value['version']) is not int or value['version'] != 1
                or value['kind'] != 'agent_decision_v1' or value['operation_id'] != operation
                or type(value['state']) is not dict or set(value['state']) != {'turn', 'observations'}):
            story._refuse(phase)
        state = validate_state(value['state']['turn'], value['state']['observations'])
        expected = generation(state, settings.model)
        phase = 'model_pin'
        model_path, model_identity = story._model_pin(settings)
        phase = 'backend_load'
        engine = (backend_factory or story._LlamaEngine)(settings)
        try:
            phase = 'generation'
            output = engine.complete(expected, settings)
            if type(output) is not str or len(output.encode('utf-8')) > 4096:
                story._refuse(phase)
            result = validate_decision(story._strict_loads(output.encode('utf-8')), state)
            payload = story._json_bytes({'version': 1, 'operation_id': operation,
                'model': settings.model, 'result': result}, 'agent response', 8192)
        finally:
            try:
                engine.close()
            except Exception:
                raise story.WorkerUnavailable('model_close') from None
        phase = 'source_recheck'
        if (story._local_file(settings.model_file) != model_path
                or story.stable_stat_identity(story._direct(model_path, False)) != model_identity
                or story._exchange(environment) != (request, response, operation)
                or story._private_read(request) != raw):
            story._refuse(phase)
        phase = 'response_write'
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(response, flags, 0o600), 'wb') as stream:
            story.require_private_file(response)
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        return 0
    except story.WorkerUnavailable:
        raise
    except Exception:
        raise story.WorkerUnavailable(phase) from None


def main(argv=None):
    # Reuse the exact approved CLI settings parser; only its closed dispatcher
    # is changed in this module's process. No model settings come from input.
    original = story.run
    story.run = run
    try:
        return story.main(argv)
    finally:
        story.run = original


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        code, record = _failure_record(error)
        print(record, file=sys.stderr)
        raise SystemExit(code) from None

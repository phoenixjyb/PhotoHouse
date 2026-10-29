"""Offline tests for the explicit library-bound text provider entrypoint."""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'scripts')]
import serve_library_semantic_text as subject  # noqa: E402
import qualify_multilingual_scenes as qualification  # noqa: E402
from app.access.semantic_encoder import (  # noqa: E402
    JointSpaceBinding, TextVector, _query_digest,
)
from app.access.search_policy_binding import capture_current_query_policy_binding  # noqa: E402
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum  # noqa: E402


class FakeLibraryModel:
    def __init__(self, binding, *, image_identity=None, text_identity=None, receipt=None):
        self.image_identity = image_identity or binding.image_identity
        self.text_identity = text_identity or binding.text_identity
        self._receipt = receipt if receipt is not None else {'schema': 'synthetic-library-model-receipt.v1'}
        self._binding = None
        self.query_policy_binding = capture_current_query_policy_binding()
        self.bind_calls = 0
        self.verify_calls = 0

    @property
    def binding(self):
        return self._binding

    def verify(self):
        self.verify_calls += 1

    def bind(self, binding):
        self.bind_calls += 1
        self._binding = binding
        return self

    def receipt(self):
        return self._receipt

    def encode(self, query, *, check=lambda: None):
        check()
        vector = (1.0,) + (0.0,) * 767
        return TextVector(self._binding.binding_sha256, _query_digest(query), vector,
                          canonical_vector_checksum(vector))


class FakeSupervisorAPI:
    def __init__(self, python_sha256, *, assigned=True, resumed=True, waits=None):
        self.python_sha256 = python_sha256
        self.assign_result = assigned
        self.resume_result = resumed
        self.wait_results = list(waits or ('timeout', 'exited'))
        self.events = []
        self.closed = []
        self.job = object()
        self.process = object()
        self.thread = object()
        self.proof = object()
        self.k32 = SimpleNamespace(GetCurrentProcess=Mock(return_value='supervisor-process'))

    def free_ram(self):
        return 8 * 1024**3

    def sha256_file(self, _path, *, deadline):
        self.events.append(('sha256_file', deadline))
        return self.python_sha256

    def create_job(self, memory_limit, process_limit):
        self.events.append(('create_job', memory_limit, process_limit))
        return self.job

    def create_suspended_proven(self, executable, argv, environment, cwd, job):
        self.events.append(('create_suspended', executable, tuple(argv), dict(environment), cwd, job))
        return self.process, self.thread, 23145, self.proof

    def assign(self, job, process):
        self.events.append(('assign', job, process))
        return self.assign_result

    def resume(self, thread):
        self.events.append(('resume', thread))
        return self.resume_result

    def _process_creation_time(self, _handle):
        return 123456789

    def wait_process(self, process, timeout):
        self.events.append(('wait', process, timeout))
        if timeout == 1000:
            result = self.wait_results.pop(0) if self.wait_results else 'exited'
            if result == 'timeout':
                self.assert_supervisor_still_owns_job()
            return result
        return 'exited'

    def assert_supervisor_still_owns_job(self):
        if self.job in self.closed:
            raise AssertionError('job handle closed while child remained alive')
        if not any(event[0] == 'assign' for event in self.events):
            raise AssertionError('child was not assigned before wait')
        if not any(event[0] == 'resume' for event in self.events):
            raise AssertionError('child was not resumed before wait')

    def exit_code(self, _process):
        return 0

    def terminate_job(self, job):
        self.events.append(('terminate_job', job))
        return True

    def terminate_process(self, process):
        self.events.append(('terminate_process', process))
        return True

    def active_processes(self, job):
        self.events.append(('active_processes', job))
        return 0

    def close(self, handle):
        self.events.append(('close', handle))
        self.closed.append(handle)


class ServeLibrarySemanticTextTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='library-provider-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.root.chmod(0o700)
        self.config_path = self.root / 'configuration.private.json'
        self.credential_path = self.root / 'credential.private.json'
        self.token = 'synthetic_token_' + 't' * 32
        self.credential_path.write_text(json.dumps({'token': self.token}), encoding='utf-8')
        self.credential_path.chmod(0o600)
        image = VectorSpaceIdentity('a' * 64, 'b' * 64, 'photohouse-library-image',
                                    'siglip2-library-v1', 768, 'unit_l2')
        text = VectorSpaceIdentity('c' * 64, 'd' * 64, 'photohouse-library-image',
                                   'siglip2-library-v1', 768, 'unit_l2')
        self.binding = JointSpaceBinding(image, text, 'e' * 64)
        prep = ROOT / 'scripts' / 'library_image_inputs.py'
        self.preparation_sha256 = hashlib.sha256(prep.read_bytes()).hexdigest()
        receipt = {'schema': 'synthetic-library-model-receipt.v1'}
        self.model = FakeLibraryModel(self.binding, receipt=receipt)
        self.document = {
            'schema': subject.SCHEMA,
            'model_directory': str(self.root / 'outside-model'),
            'artifacts': qualification.OFFICIAL_ARTIFACTS,
            'package_versions': qualification.EXPECTED_PACKAGES,
            'binding': asdict(self.binding),
            'credential_file': str(self.credential_path),
            'port': 48321,
            'preparation_source_sha256': self.preparation_sha256,
            'model_receipt_sha256': subject.document_sha256(receipt),
        }
        self.write_config()

    def write_config(self):
        self.config_path.write_text(json.dumps(self.document, sort_keys=True), encoding='utf-8')
        self.config_path.chmod(0o600)
        self.config_sha256 = subject.document_sha256(self.document)

    def run_capture(self, args):
        out, err = io.StringIO(), io.StringIO()
        with patch.object(subject, 'native_admission', return_value=None), \
             redirect_stdout(out), redirect_stderr(err):
            result = subject.run(args)
        return result, out.getvalue(), err.getvalue()

    def test_no_argument_entry_is_inert_and_does_not_import_provider_or_ml(self):
        code = '''import importlib.util, json, sys
p = sys.argv[1]
s = importlib.util.spec_from_file_location("inert_library_entry", p)
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
r = m.run([])
blocked = ("torch", "transformers", "library_siglip", "qualify_multilingual_scenes",
           "app.access.model_deployment", "bounded_windows_job")
print(json.dumps({"result": r, "loaded": [n for n in blocked if n in sys.modules]}))
'''
        result = subprocess.run([sys.executable, '-I', '-B', '-S', '-c', code,
                                 str(ROOT / 'scripts' / 'serve_library_semantic_text.py')],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 2)
        record = json.loads(lines[1])
        self.assertEqual(record, {'result': 0, 'loaded': []})
        # The run itself prints the inert receipt before the subprocess marker.
        receipt = json.loads(lines[0])
        self.assertEqual(receipt, {'status': 'library_provider_plan', 'models_loaded': False,
            'private_files_read': False, 'listener_started': False,
            'activation_performed': False, 'service_management': False})
        self.assertEqual(result.stderr, '')

    def test_native_admission_refuses_non_windows_and_checks_exact_job_proof(self):
        if os.name != 'nt':
            with self.assertRaises(subject.ProviderRefused):
                subject.native_admission()
        fake = ModuleType('bounded_windows_job')
        api = SimpleNamespace(consume_job_proof=Mock(return_value={
            'flags': 0x2208, 'memory_limit': 8 * 1024**3, 'process_limit': 4}),
            free_ram=Mock(return_value=8 * 1024**3))
        fake.WindowsAPI = Mock(return_value=api)
        with patch.object(subject.os, 'name', 'nt'), patch.dict(sys.modules, {'bounded_windows_job': fake}):
            subject.native_admission()
            api.consume_job_proof.assert_called_once_with()
            api.free_ram.assert_called_once_with()
            api.consume_job_proof.return_value = {'flags': True, 'memory_limit': 8 * 1024**3,
                                                  'process_limit': 4}
            with self.assertRaises(subject.ProviderRefused):
                subject.native_admission()
            api.consume_job_proof.return_value = {'flags': 0x2208, 'memory_limit': 8 * 1024**3,
                                                  'process_limit': 4}
            api.free_ram.return_value = 8 * 1024**3 - 1
            with self.assertRaises(subject.ProviderRefused):
                subject.native_admission()

    def test_native_admission_refusal_precedes_private_configuration_read(self):
        config_reader = Mock(side_effect=AssertionError('configuration read must follow Job proof'))
        out, err = io.StringIO(), io.StringIO()
        with patch.object(subject, 'native_admission', side_effect=subject.ProviderRefused), \
             patch.object(subject, 'load_configuration', config_reader), \
             redirect_stdout(out), redirect_stderr(err):
            result = subject.run(['probe', '--configuration', str(self.config_path),
                                  '--configuration-sha256', self.config_sha256])
        self.assertEqual(result, 2)
        self.assertEqual(err.getvalue(), '{"error":"library_provider_unavailable"}\n')
        config_reader.assert_not_called()

    def test_malformed_schema_and_preparation_pin_refuse_before_model_load(self):
        for change in ({'schema': 'photohouse.base_siglip_provider.v1'},
                       {'preparation_source_sha256': 'f' * 64}):
            with self.subTest(change=list(change)):
                self.document.update(change)
                self.write_config()
                model_load = Mock(side_effect=AssertionError('model load must not run'))
                out, err = io.StringIO(), io.StringIO()
                checked = Mock(side_effect=AssertionError('model check must not run'))
                with patch.object(subject, 'native_admission', return_value=None), \
                     patch.object(subject, 'load_model', model_load), \
                     patch.object(subject, 'checked_model', checked), \
                     redirect_stdout(out), redirect_stderr(err):
                    result = subject.run(['probe', '--configuration', str(self.config_path),
                                          '--configuration-sha256', self.config_sha256])
                self.assertEqual(result, 2)
                self.assertEqual(err.getvalue(), '{"error":"library_provider_unavailable"}\n')
                model_load.assert_not_called()
                checked.assert_not_called()
                self.document = {**self.document, **{k: v for k, v in change.items()}}
                self.document['schema'] = subject.SCHEMA
                self.document['preparation_source_sha256'] = self.preparation_sha256
        self.write_config()

    def test_binding_and_model_receipt_mismatch_refuse_before_listener(self):
        cases = (
            FakeLibraryModel(self.binding, image_identity=VectorSpaceIdentity(
                'f' * 64, 'b' * 64, 'photohouse-library-image', 'siglip2-library-v1', 768, 'unit_l2')),
            FakeLibraryModel(self.binding, receipt={'schema': 'different-receipt'}),
        )
        for model in cases:
            for operation in ('probe', 'serve'):
                with self.subTest(model_receipt=model.receipt(), operation=operation):
                    out, err = io.StringIO(), io.StringIO()
                    app_factory = Mock(side_effect=AssertionError('listener app must not be built'))
                    uvicorn = SimpleNamespace(run=Mock(side_effect=AssertionError('listener must not run')))
                    with patch.object(subject, 'native_admission', return_value=None), \
                         patch.object(subject, 'load_model', return_value=model), \
                         patch('app.access.semantic_provider_transport.create_provider_app', app_factory), \
                         patch.dict(sys.modules, {'uvicorn': uvicorn}), \
                         redirect_stdout(out), redirect_stderr(err):
                        result = subject.run([operation, '--configuration', str(self.config_path),
                                              '--configuration-sha256', self.config_sha256])
                    self.assertEqual(result, 2)
                    self.assertEqual(err.getvalue(), '{"error":"library_provider_unavailable"}\n')
                    self.assertNotIn(str(self.config_path), err.getvalue())
                    self.assertNotIn(self.token, err.getvalue())
                    app_factory.assert_not_called()
                    uvicorn.run.assert_not_called()

    def test_probe_does_not_read_credential_or_start_listener(self):
        self.credential_path.unlink()
        model = self.model
        app_factory = Mock(side_effect=AssertionError('probe must not build listener app'))
        uvicorn = SimpleNamespace(run=Mock(side_effect=AssertionError('probe must not serve')))
        with patch.object(subject, 'native_admission', return_value=None), \
             patch.object(subject, 'load_model', return_value=model), \
             patch('app.access.semantic_provider_transport.create_provider_app', app_factory), \
             patch.dict(sys.modules, {'uvicorn': uvicorn}):
            result, stdout, stderr = self.run_capture(['probe', '--configuration', str(self.config_path),
                                                        '--configuration-sha256', self.config_sha256])
        self.assertEqual(result, 0)
        receipt = json.loads(stdout)
        self.assertEqual(receipt['status'], 'library_provider_probed')
        self.assertFalse(receipt['listener_started'])
        self.assertFalse(receipt['activation_performed'])
        self.assertNotIn(str(self.config_path), stdout)
        self.assertNotIn(str(self.credential_path), stdout)
        self.assertNotIn(self.token, stdout)
        self.assertEqual(stderr, '')
        app_factory.assert_not_called()
        uvicorn.run.assert_not_called()

    def test_configuration_and_credential_are_rechecked_before_app_creation(self):
        original = dict(self.document)
        for changed in ('configuration', 'credential'):
            with self.subTest(changed=changed):
                def mutate_after_model(_config, _binding):
                    if changed == 'configuration':
                        self.document['port'] = 48322
                        self.write_config()
                    else:
                        self.credential_path.write_text(json.dumps({'token': 'changed_token_' + 'z' * 32}),
                                                        encoding='utf-8')
                        self.credential_path.chmod(0o600)
                    return self.model, {'policy': 'synthetic'}
                out, err = io.StringIO(), io.StringIO()
                app_factory = Mock(side_effect=AssertionError('changed inputs must not create app'))
                uvicorn = SimpleNamespace(run=Mock(side_effect=AssertionError('changed inputs must not serve')))
                with patch.object(subject, 'native_admission', return_value=None), \
                     patch.object(subject, 'checked_model', side_effect=mutate_after_model), \
                     patch('app.access.semantic_provider_transport.create_provider_app', app_factory), \
                     patch.dict(sys.modules, {'uvicorn': uvicorn}), \
                     redirect_stdout(out), redirect_stderr(err):
                    result = subject.run(['serve', '--configuration', str(self.config_path),
                                          '--configuration-sha256', self.config_sha256])
                self.assertEqual(result, 2)
                self.assertEqual(err.getvalue(), '{"error":"library_provider_unavailable"}\n')
                self.assertNotIn(str(self.config_path), err.getvalue())
                self.assertNotIn(self.token, err.getvalue())
                app_factory.assert_not_called()
                uvicorn.run.assert_not_called()
                self.document = dict(original)
                self.write_config()
                self.credential_path.write_text(json.dumps({'token': self.token}), encoding='utf-8')
                self.credential_path.chmod(0o600)

    def test_explicit_cpu_request_budget_reaches_transport(self):
        app_factory = Mock(return_value=object())
        uvicorn = SimpleNamespace(run=Mock())
        with patch.object(subject, 'native_admission', return_value=None), \
             patch.object(subject, 'load_model', return_value=self.model), \
             patch('app.access.semantic_provider_transport.create_provider_app', app_factory), \
             patch.dict(sys.modules, {'uvicorn': uvicorn}):
            result, stdout, stderr = self.run_capture(['serve', '--configuration', str(self.config_path),
                '--configuration-sha256', self.config_sha256, '--request-seconds', '15'])
        self.assertEqual((result, stdout, stderr), (0, '', ''))
        self.assertEqual(app_factory.call_args.kwargs['seconds'], 15.0)

    def test_invalid_request_budget_refuses_before_native_or_model_work(self):
        for value in ('0', '31', 'nan', 'inf'):
            with self.subTest(value=value), patch.object(subject, 'native_admission') as native:
                result, _, stderr = self.run_capture(['probe', '--configuration', str(self.config_path),
                    '--configuration-sha256', self.config_sha256, '--request-seconds', value])
                self.assertEqual(result, 2)
                self.assertEqual(stderr, '{"error":"library_provider_unavailable"}\n')
                native.assert_not_called()

    def test_supervisor_preserves_explicit_request_budget_for_child(self):
        record = self.root / 'budget-owner.private.json'
        cache = self.root / 'budget-cache'
        cache.mkdir(mode=0o700)
        api = FakeSupervisorAPI('9' * 64)
        fake_module = self.supervisor_api_module()
        fake_module.WindowsAPI = Mock()
        args = self.supervisor_args(record, cache)
        args.request_seconds = 15
        with patch.object(subject, 'require_windows'), \
             patch.dict(os.environ, {'SystemRoot': str(self.root)}), \
             patch.dict(sys.modules, {'bounded_windows_job': fake_module}):
            self.assertEqual(subject.supervise(args, api=api), 0)
        argv = next(event[2] for event in api.events if event[0] == 'create_suspended')
        self.assertEqual(argv[-2:], ('--request-seconds', '15.0'))

    def supervisor_args(self, record, cache, *, entry_sha=None, python_sha=None):
        entry = Path(subject.__file__).resolve(strict=True)
        return SimpleNamespace(service_id=str(uuid.uuid4()),
            entry_sha256=entry_sha or hashlib.sha256(entry.read_bytes()).hexdigest(),
            python_sha256=python_sha or '9' * 64,
            configuration=self.config_path,
            configuration_sha256=self.config_sha256,
            ownership_record=record, cache_directory=cache)

    def supervisor_api_module(self):
        return ModuleType('bounded_windows_job')

    def test_supervisor_retains_job_during_timeout_and_assigns_before_resume(self):
        record = self.root / 'owned-process.private.json'
        cache = self.root / 'cache'
        cache.mkdir(mode=0o700)
        api = FakeSupervisorAPI('9' * 64, waits=('timeout', 'exited'))
        fake_module = self.supervisor_api_module()
        fake_module.WindowsAPI = Mock()
        out, err = io.StringIO(), io.StringIO()
        with patch.object(subject, 'require_windows'), \
             patch.dict(os.environ, {'SystemRoot': str(self.root)}), \
             patch.dict(sys.modules, {'bounded_windows_job': fake_module}), \
             redirect_stdout(out), redirect_stderr(err):
            result = subject.supervise(self.supervisor_args(record, cache), api=api)
        event_names = [event[0] for event in api.events]
        self.assertEqual(result, 0)
        self.assertLess(event_names.index('assign'), event_names.index('resume'))
        self.assertEqual(event_names.count('wait'), 3)  # timeout, child exit, owned cleanup readback
        self.assertIn(('terminate_job', api.job), api.events)
        self.assertIn(('active_processes', api.job), api.events)
        self.assertEqual(set(api.closed), {api.thread, api.process, api.proof, api.job})
        ownership = json.loads(record.read_text(encoding='utf-8'))
        self.assertEqual(ownership['state'], 'CHILD_STARTED_READINESS_NOT_ESTABLISHED')
        self.assertFalse(ownership['readiness_established'])
        self.assertFalse(ownership['activation_performed'])
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(err.getvalue(), '')

    def test_supervisor_failure_cleans_exact_unassigned_or_assigned_child(self):
        for assign_ok, resume_ok, expected_cleanup in (
                (False, True, 'terminate_process'), (True, False, 'terminate_job')):
            with self.subTest(assign=assign_ok, resume=resume_ok):
                record = self.root / f'owned-{assign_ok}-{resume_ok}.private.json'
                cache = self.root / f'cache-{assign_ok}-{resume_ok}'
                cache.mkdir(mode=0o700)
                api = FakeSupervisorAPI('9' * 64, assigned=assign_ok, resumed=resume_ok)
                fake_module = self.supervisor_api_module()
                fake_module.WindowsAPI = Mock()
                with patch.object(subject, 'require_windows'), \
                     patch.dict(os.environ, {'SystemRoot': str(self.root)}), \
                     patch.dict(sys.modules, {'bounded_windows_job': fake_module}), \
                     self.assertRaises(subject.ProviderRefused):
                    subject.supervise(self.supervisor_args(record, cache), api=api)
                event_names = [event[0] for event in api.events]
                self.assertIn(expected_cleanup, event_names)
                self.assertIn(('wait', api.process, 5000), api.events)
                if assign_ok:
                    self.assertIn(('active_processes', api.job), api.events)
                else:
                    self.assertNotIn(('active_processes', api.job), api.events)
                    self.assertNotIn('resume', event_names)
                self.assertEqual(set(api.closed), {api.thread, api.process, api.proof, api.job})
                self.assertFalse(record.exists())

    def test_supervisor_refuses_existing_ownership_record_and_source_pin_before_child(self):
        for refusal in ('existing_record', 'entry_pin'):
            with self.subTest(refusal=refusal):
                record = self.root / f'owned-{refusal}.private.json'
                cache = self.root / f'cache-{refusal}'
                cache.mkdir(mode=0o700)
                if refusal == 'existing_record':
                    record.write_text('existing ownership', encoding='utf-8')
                    record.chmod(0o600)
                api = FakeSupervisorAPI('9' * 64)
                fake_module = self.supervisor_api_module()
                fake_module.WindowsAPI = Mock()
                args = self.supervisor_args(record, cache,
                    entry_sha=('0' * 64 if refusal == 'entry_pin' else None))
                with patch.object(subject, 'require_windows'), \
                     patch.dict(os.environ, {'SystemRoot': str(self.root)}), \
                     patch.dict(sys.modules, {'bounded_windows_job': fake_module}), \
                     self.assertRaises(subject.ProviderRefused):
                    subject.supervise(args, api=api)
                self.assertFalse(any(event[0] == 'create_suspended' for event in api.events))
                if refusal == 'existing_record':
                    self.assertEqual(record.read_text(encoding='utf-8'), 'existing ownership')
                self.assertFalse(any(event[0] == 'resume' for event in api.events))

    def test_keyboard_interrupt_propagates_without_private_diagnostics(self):
        with patch.object(subject, 'native_admission', side_effect=KeyboardInterrupt), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                subject.run(['probe', '--configuration', str(self.config_path),
                             '--configuration-sha256', self.config_sha256])

    def test_authenticated_synthetic_asgi_route_uses_library_bound_model(self):
        model = self.model
        application = {}
        def run_asgi(app, **kwargs):
            application['app'] = app
            application['kwargs'] = kwargs
            from fastapi.testclient import TestClient
            with TestClient(app, base_url=f"http://127.0.0.1:{self.document['port']}",
                           client=('127.0.0.1', 50000)) as client:
                denied = client.post('/v1/encode-text', json={
                    'version': 1, 'binding_sha256': self.binding.binding_sha256, 'query': 'family photo'},
                    headers={'Authorization': 'Bearer ' + 'wrong_' + 'x' * 32})
                accepted = client.post('/v1/encode-text', json={
                    'version': 1, 'binding_sha256': self.binding.binding_sha256, 'query': 'family photo'},
                    headers={'Authorization': 'Bearer ' + self.token})
            self.assertEqual(denied.status_code, 401)
            self.assertEqual(accepted.status_code, 200)
            body = accepted.json()
            self.assertEqual(body['binding_sha256'], self.binding.binding_sha256)
            self.assertEqual(body['query_sha256'], _query_digest('family photo'))
        uvicorn = SimpleNamespace(run=Mock(side_effect=run_asgi))
        out, err = io.StringIO(), io.StringIO()
        with patch.object(subject, 'native_admission', return_value=None), \
             patch.object(subject, 'load_model', return_value=model), \
             patch.dict(sys.modules, {'uvicorn': uvicorn}), \
             redirect_stdout(out), redirect_stderr(err):
            result = subject.run(['serve', '--configuration', str(self.config_path),
                                  '--configuration-sha256', self.config_sha256])
        self.assertEqual(result, 0)
        self.assertEqual(err.getvalue(), '')
        self.assertEqual(out.getvalue(), '')
        self.assertEqual(model.bind_calls, 1)
        self.assertEqual(uvicorn.run.call_args.kwargs['host'], '127.0.0.1')
        self.assertEqual(uvicorn.run.call_args.kwargs['workers'], 1)


if __name__ == '__main__':
    unittest.main()

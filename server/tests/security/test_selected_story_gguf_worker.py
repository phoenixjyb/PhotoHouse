"""Synthetic worker/optional-binding tests; no GGUF inference or native Job proof."""
import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import selected_story_gguf_worker as worker
from test_selected_story_local import MODEL, OPERATION_ID, bundle, narrative, make_scope


class SyntheticEngine:
    def __init__(self, settings):
        self.settings = settings
        self.calls = []
        self.closed = False
        self.text = json.dumps(narrative())
        self.fail_close = False

    def complete(self, generation, settings):
        self.calls.append((generation, settings))
        return self.text

    def close(self):
        self.closed = True
        if self.fail_close:
            raise RuntimeError('synthetic source words must not appear in errors')


class GGUFWorkerTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve()
        self.exchange = self.root / 'exchange'
        self.exchange.mkdir(mode=0o700)
        self.model_dir = self.root / 'model'
        self.model_dir.mkdir(mode=0o700)
        self.model = self.model_dir / 'synthetic.gguf'
        self.model.write_bytes(b'GGUFsynthetic fixture, never inference')
        self.settings = worker.WorkerSettings(str(self.model),
            hashlib.sha256(self.model.read_bytes()).hexdigest(), MODEL)
        self.request = self.exchange / 'request.json'
        self.response = self.exchange / 'response.json'
        self.env = {worker.REQUEST_ENV: str(self.request), worker.RESPONSE_ENV: str(self.response),
                    worker.OPERATION_ENV: OPERATION_ID}
        self.body = {'version': 1, 'operation_id': OPERATION_ID,
                     'generation': worker._generation_payload(bundle(), 'narrative', MODEL)}
        self.write_request()
        self.engine = SyntheticEngine(self.settings)
        self.factory = Mock(return_value=self.engine)

    def write_request(self):
        self.request.write_text(json.dumps(self.body, ensure_ascii=False), encoding='utf-8')
        os.chmod(self.request, 0o600)

    def run_worker(self, **kwargs):
        return worker.run(self.settings, enabled=True, environment=self.env,
                          backend_factory=self.factory, **kwargs)

    def test_disabled_is_inert_before_path_or_backend_access(self):
        with patch.object(worker, '_exchange') as exchange:
            with self.assertRaises(worker.WorkerUnavailable):
                worker.run(self.settings, environment=self.env, backend_factory=self.factory)
            exchange.assert_not_called()
            self.factory.assert_not_called()
        self.assertFalse(self.response.exists())

    def test_import_and_cli_refusal_do_not_import_optional_backend_or_echo_paths(self):
        program = (f'import sys;sys.path.insert(0,{str(SCRIPTS)!r});'
                   'import selected_story_gguf_worker;assert "llama_cpp" not in sys.modules')
        out = subprocess.run([sys.executable, '-I', '-B', '-c', program], capture_output=True,
                             text=True, timeout=10)
        self.assertEqual(0, out.returncode, out.stderr)
        out = subprocess.run([sys.executable, '-I', '-B', str(SCRIPTS / 'selected_story_gguf_worker.py'),
            '--model-file', 'private-synthetic-path', '--model-sha256', 'a'*64,
            '--model-label', MODEL], capture_output=True, text=True, timeout=10)
        self.assertEqual(2, out.returncode)
        self.assertEqual('', out.stdout)
        self.assertEqual('{"status":"failed","category":"worker_unavailable"}', out.stderr.strip())
        self.assertFalse(self.response.exists())

    def test_success_closes_before_private_response_and_keeps_request_unchanged(self):
        before = self.request.read_bytes()
        check = worker.require_private_file
        def privacy(path):
            if Path(path) == self.response:
                self.assertTrue(self.engine.closed)
                self.assertEqual(b'', self.response.read_bytes())
            return check(path)
        with patch.object(worker, 'require_private_file', side_effect=privacy):
            self.assertEqual(0, self.run_worker())
        result = json.loads(self.response.read_bytes())
        self.assertEqual({'version': 1, 'operation_id': OPERATION_ID, 'model': MODEL,
                          'result': narrative()}, result)
        self.assertEqual(before, self.request.read_bytes())
        self.assertEqual({'request.json', 'response.json'}, {p.name for p in self.exchange.iterdir()})

    def test_request_exact_types_schema_and_binding_refused_before_model_load(self):
        baseline = json.loads(json.dumps(self.body))
        mutations = [lambda b:b.update(version=True), lambda b:b.update(extra='source'),
            lambda b:b.update(operation_id='a'*36),
            lambda b:b['generation'].update(stream=0),
            lambda b:b['generation'].update(truncate=True),
            lambda b:b['generation'].update(model='other-model'),
            lambda b:b['generation'].update(format={'$ref':'https://untrusted.invalid/schema'}),
            lambda b:b['generation']['options'].update(num_predict=2048.0),
            lambda b:b['generation'].update(prompt=b['generation']['prompt']+' altered')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.body = json.loads(json.dumps(baseline));mutate(self.body);self.write_request()
                with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
                self.factory.assert_not_called()
                self.assertFalse(self.response.exists())

    def test_malformed_duplicate_nonfinite_utf8_and_oversized_requests(self):
        for raw in (b'{"version":1,"version":1}', b'{"version":NaN}', b'\xff',
                    b'x'*(worker.MAX_REQUEST_BYTES+1), b''):
            with self.subTest(length=len(raw)):
                self.request.write_bytes(raw)
                with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
                self.factory.assert_not_called()

    def test_unsafe_exchange_paths_and_existing_response_refused(self):
        original = dict(self.env)
        for change in ({worker.OPERATION_ENV:'wrong'}, {worker.REQUEST_ENV:'relative'},
            {worker.RESPONSE_ENV:str(self.root/'response.json')},
            {worker.REQUEST_ENV:str(self.exchange/'..'/'request.json')},
            {worker.RESPONSE_ENV:'//remote/share/response.json'}):
            with self.subTest(change=change):
                self.env = {**original, **change}
                with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
                self.factory.assert_not_called()
        self.env=original
        self.response.write_bytes(b'preserve existing')
        with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
        self.assertEqual(b'preserve existing',self.response.read_bytes())
        self.factory.assert_not_called()

    def test_hardlinked_request_and_unexpected_exchange_entries_refused(self):
        link=self.root/'extra';os.link(self.request,link)
        with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
        link.unlink()
        (self.exchange/'unfamiliar').write_bytes(b'keep')
        with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
        self.factory.assert_not_called()

    def test_bad_model_hash_magic_split_and_sidecar_refused_before_backend(self):
        original=self.settings
        self.settings=replace(original, model_sha256='0'*64)
        with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
        self.model.write_bytes(b'not a GGUF fixture')
        self.settings=replace(original, model_sha256=hashlib.sha256(self.model.read_bytes()).hexdigest())
        with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
        self.model.write_bytes(b'GGUFsynthetic fixture, never inference');self.settings=original
        extra=self.model_dir/'unverified.gguf';extra.write_bytes(b'GGUFextra')
        with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
        extra.unlink()
        split=self.model_dir/'model-00001-of-00002.gguf';self.model.rename(split)
        self.settings=replace(original,model_file=str(split))
        with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
        self.factory.assert_not_called()

    def test_invalid_or_oversized_result_and_close_failure_never_publish(self):
        variants=['not JSON',json.dumps({**narrative(),'needs_review':False}),
            json.dumps({**narrative(),'chapters':[{'id':'chapter-1','narration':'invented',
                                                  'source_ids':['foreign']}]}),
            'x'*(worker.MAX_OUTPUT_BYTES+1)]
        for text in variants:
            with self.subTest(text=text[:20]):
                self.engine.text=text
                with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
                self.assertTrue(self.engine.closed)
                self.assertFalse(self.response.exists())
        self.engine.text=json.dumps(narrative());self.engine.fail_close=True
        with self.assertRaises(worker.WorkerUnavailable) as caught:self.run_worker()
        self.assertNotIn('source words',str(caught.exception))
        self.assertFalse(self.response.exists())

    def test_request_or_model_mutation_during_inference_refuses_result(self):
        for path in (self.request,self.model):
            with self.subTest(path=path.name):
                before=path.read_bytes()
                def complete(*_):
                    path.write_bytes(before+b' ')
                    return json.dumps(narrative())
                with patch.object(self.engine,'complete',side_effect=complete):
                    with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
                self.assertFalse(self.response.exists());path.write_bytes(before)

    def test_late_response_collision_is_preserved_and_private_write_refuses_before_words(self):
        def complete(*_):
            self.response.write_bytes(b'preserve collision')
            return json.dumps(narrative())
        with patch.object(self.engine,'complete',side_effect=complete):
            with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
        self.assertEqual(b'preserve collision',self.response.read_bytes())
        self.response.unlink()
        check=worker.require_private_file
        def deny_response(path):
            if Path(path)==self.response:raise ValueError('not private')
            return check(path)
        with patch.object(worker,'require_private_file',side_effect=deny_response):
            with self.assertRaises(worker.WorkerUnavailable):self.run_worker()
        self.assertEqual(b'',self.response.read_bytes())

    def test_optional_binding_refuses_out_of_budget_or_invalid_usage(self):
        native=Mock();native.n_ctx.return_value=8192;native.tokenize.return_value=[1,2,3]
        binding=SimpleNamespace(Llama=Mock(return_value=native),LLAMA_SPLIT_MODE_NONE=0,
            LlamaGrammar=SimpleNamespace(from_json_schema=Mock()))
        with patch.dict(sys.modules,{'llama_cpp':binding}):
            engine=worker._LlamaEngine(self.settings)
            for usage in ({'prompt_tokens':3,'completion_tokens':2049},
                          {'prompt_tokens':True,'completion_tokens':1},
                          {'prompt_tokens':3,'completion_tokens':True},
                          {'prompt_tokens':4,'completion_tokens':1},None):
                with self.subTest(usage=usage):
                    native.create_completion.return_value={'choices':[{'text':'{}','finish_reason':'stop'}], 'usage':usage}
                    with self.assertRaises(worker.WorkerUnavailable):engine.complete(self.body['generation'],self.settings)
            engine.close()

    def test_config_resource_limits_reject_bool_and_unbounded_values(self):
        for change in ({'context_tokens':0},{'context_tokens':32768},{'threads':True},
                       {'threads':9},{'gpu_layers':-1},{'gpu_layers':129},
                       {'gpu_layers':1},{'gpu_device':0},
                       {'gpu_layers':1,'gpu_device':True},
                       {'gpu_layers':1,'gpu_device':16},
                       {'model':'https://remote.invalid/model'}):
            with self.subTest(change=change):
                with self.assertRaises(worker.WorkerUnavailable):replace(self.settings,**change)

    def test_optional_binding_uses_local_cpu_and_full_tokens_with_closed_schema(self):
        native=Mock();native.tokenize.return_value=[1,2,3];native.n_ctx.return_value=8192
        native.create_completion.return_value={'choices':[{'text':json.dumps(narrative()),'finish_reason':'stop'}], 'usage':{'prompt_tokens':3,'completion_tokens':100}}
        grammar=SimpleNamespace(from_json_schema=Mock(return_value='synthetic-grammar'))
        binding=SimpleNamespace(Llama=Mock(return_value=native),LlamaGrammar=grammar,LLAMA_SPLIT_MODE_NONE=0)
        generation=self.body['generation']
        with patch.dict(sys.modules,{'llama_cpp':binding}):
            engine=worker._LlamaEngine(self.settings)
            self.assertEqual(json.dumps(narrative()),engine.complete(generation,self.settings))
            engine.close()
        options=binding.Llama.call_args.kwargs
        self.assertEqual(str(self.model),options['model_path']);self.assertEqual(0,options['n_gpu_layers'])
        self.assertFalse(options['offload_kqv']);self.assertFalse(options['op_offload'])
        self.assertFalse(options['verbose']);self.assertFalse(options['use_mmap'])
        self.assertNotIn('rpc_servers',options)
        native.tokenize.assert_called_once_with(generation['prompt'].encode(),add_bos=True,special=False)
        completion=native.create_completion.call_args.kwargs
        self.assertEqual([1,2,3],completion['prompt']);self.assertEqual(2048,completion['max_tokens'])
        self.assertFalse(completion['stream']);self.assertFalse(completion['echo'])
        self.assertEqual(generation['format'],json.loads(grammar.from_json_schema.call_args.args[0]))
        native.close.assert_called_once()

    def test_gpu_offload_requires_explicit_backend_ordinal(self):
        binding=SimpleNamespace(Llama=Mock(),LLAMA_SPLIT_MODE_NONE=0)
        settings=replace(self.settings,gpu_layers=8,gpu_device=1)
        with patch.dict(sys.modules,{'llama_cpp':binding}):
            engine=worker._LlamaEngine(settings)
            engine.close()
        options=binding.Llama.call_args.kwargs
        self.assertEqual(1,options['main_gpu'])
        self.assertEqual(8,options['n_gpu_layers'])
        self.assertEqual(0,options['split_mode'])
        self.assertTrue(options['offload_kqv'])
        # An ordinal is configuration, not a claim about physical GPU identity.

    def test_worker_environment_keeps_windows_basics_and_excludes_provider_secrets(self):
        from test_selected_story_process_lifecycle import worker_environment
        with patch.dict(os.environ,{'SystemRoot':r'C:\Windows',
                'PHOTOHOUSE_PROVIDER_TOKEN':'synthetic-secret',
                'OLLAMA_HOST':'http://untrusted.invalid'},clear=True):
            env=worker_environment()
        self.assertEqual(r'C:\Windows',env['SYSTEMROOT'])
        self.assertEqual({'PATH','PHOTOHOUSE_NO_DOTENV','SYSTEMROOT'},set(env))

    def test_context_boundary_and_truncated_completion_refused(self):
        native=Mock();native.n_ctx.return_value=4096
        native.create_completion.return_value={'choices':[{'text':'{}','finish_reason':'stop'}], 'usage':{'prompt_tokens':2048,'completion_tokens':1}}
        binding=SimpleNamespace(Llama=Mock(return_value=native),
            LlamaGrammar=SimpleNamespace(from_json_schema=Mock()),LLAMA_SPLIT_MODE_NONE=0)
        with patch.dict(sys.modules,{'llama_cpp':binding}):
            engine=worker._LlamaEngine(self.settings)
            native.tokenize.return_value=[1]*2048
            self.assertEqual('{}',engine.complete(self.body['generation'],self.settings))
            native.create_completion.reset_mock();native.tokenize.return_value=[1]*2049
            with self.assertRaises(worker.WorkerUnavailable):engine.complete(self.body['generation'],self.settings)
            native.create_completion.assert_not_called()
            native.tokenize.return_value=[1]
            native.create_completion.return_value={'choices':[{'text':'{}','finish_reason':'length'}], 'usage':{'prompt_tokens':1,'completion_tokens':2048}}
            with self.assertRaises(worker.WorkerUnavailable):engine.complete(self.body['generation'],self.settings)
            engine.close()


class GGUFWorkerProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_worker_protocol_roundtrip_with_synthetic_engine(self):
        from test_selected_story_process_lifecycle import WorkerKernel, worker_environment
        from backend.app.access.selected_story_native import NativeStoryLaunch
        from backend.app.access.selected_story_process import ProcessSelectedStoryProvider
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();model_dir=root/'model';model_dir.mkdir(mode=0o700)
            model=model_dir/'synthetic.gguf';model.write_bytes(b'GGUFnot real weights')
            digest=hashlib.sha256(model.read_bytes()).hexdigest()
            code=('import sys,runpy,json;sys.stdin.buffer.read(1);'
                f"w=runpy.run_path({str(SCRIPTS/'selected_story_gguf_worker.py')!r},run_name='test_worker');"
                f"s=w['WorkerSettings']({str(model)!r},{digest!r},{MODEL!r});"
                f"E=type('SyntheticEngine',(),{{'__init__':lambda self,s:None,'complete':lambda self,g,s:{json.dumps(narrative())!r},'close':lambda self:None}});"
                "w['run'](s,enabled=True,backend_factory=E)")
            spec=NativeStoryLaunch(sys.executable,hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
                (sys.executable,'-I','-B','-c',code),str(root),worker_environment(),minimum_free_ram=0)
            kernel=WorkerKernel(helpers=0)
            self.addCleanup(kernel.finish)
            provider=ProcessSelectedStoryProvider(spec,MODEL,kernel_factory=lambda:kernel,enabled=True)
            self.addAsyncCleanup(provider.close)
            scope=make_scope(seconds=15)
            # macOS's default /var alias is deliberately refused by the worker.
            with patch('tempfile.tempdir',str(root)):
                self.assertEqual(narrative(),await provider.prepare(bundle(),scope))
                self.assertTrue(await provider.stop_and_reconcile(scope))
            self.assertTrue(all(not path.exists() for path in kernel.exchanges))
            self.assertTrue(all(p.poll()==0 for p in kernel.children))

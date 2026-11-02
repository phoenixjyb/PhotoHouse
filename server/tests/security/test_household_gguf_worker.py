"""Household dispatcher fixtures only; actual pinned model runs on Windows."""
import contextlib,ctypes,hashlib,io,json,os,runpy,subprocess,sys,types,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock,patch

SCRIPTS=Path(__file__).resolve().parents[2]/'scripts';sys.path.insert(0,str(SCRIPTS))
import household_gguf_worker as worker
import test_selected_story_gguf_worker as _worker_fixture
from test_selected_story_local import OPERATION_ID, bundle, narrative
from backend.app.access.memory_narrative import STORY_REFINEMENT_PROFILE, _generation_payload

STORY_ID='12345678-1234-4234-8234-123456789abc'

def saved_bundle():
    value=bundle();value['version']=1
    value['target']={'type':'story','id':STORY_ID,'revision':7}
    value.pop('selection_revision')
    for source in value['sources']:source.pop('source_kind')
    return value


def fake_native_log_api():
    callback_type=ctypes.CFUNCTYPE(None,ctypes.c_int,ctypes.c_char_p,ctypes.c_void_p)
    class FakeNative(types.ModuleType):
        def __init__(self):
            super().__init__('llama_cpp.llama_cpp')
            self.llama_log_callback=callback_type
            self.previous_callback=callback_type(lambda _level,_message,_userdata:None)
            self.previous_userdata=ctypes.c_void_p(0x1234)
            self.current_callback=self.previous_callback
            self.current_userdata=self.previous_userdata
            self.set_calls=[]
        def llama_log_get(self,callback_out,userdata_out):
            ctypes.cast(callback_out,ctypes.POINTER(callback_type))[0]=self.current_callback
            ctypes.cast(userdata_out,ctypes.POINTER(ctypes.c_void_p))[0]=self.current_userdata
        def llama_log_set(self,callback,userdata):
            self.set_calls.append((callback,userdata))
            self.current_callback=callback
            self.current_userdata=userdata
        def emit(self,level,message):
            self.current_callback(level,message,self.current_userdata)
    native=FakeNative()
    package=types.ModuleType('llama_cpp')
    package.__path__=[]
    package.llama_cpp=native
    return native,package

class HouseholdWorkerTests(unittest.TestCase):
    setUp= _worker_fixture.GGUFWorkerTests.setUp
    write_request= _worker_fixture.GGUFWorkerTests.write_request
    def test_existing_story_packet_delegates_to_unchanged_validator(self):
        self.assertEqual(worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory),0)
        self.assertTrue(self.engine.closed);self.assertTrue(self.response.exists())
    def test_agent_decision_requires_owned_kind_and_reconstructs_prompt(self):
        self.body={'version':1,'kind':'agent_decision_v1','operation_id':OPERATION_ID,'state':{'turn':{'version':1,'text':'Find photos','locale':'en'},'observations':[]}};self.write_request();self.engine.text=json.dumps({'tool':'search_media'})
        self.assertEqual(worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory),0)
        self.assertEqual(json.loads(self.response.read_bytes())['result'],{'tool':'search_media'});self.assertTrue(self.engine.closed)
        self.assertEqual(self.engine.calls[0][0]['options'],{'temperature':0,'num_predict':128})
    def test_saved_story_narrative_requires_closed_packet_and_reconstructs_canonical_generation(self):
        self.body={'version':1,'kind':'saved_story_narrative_v1','operation_id':OPERATION_ID,'bundle':saved_bundle()}
        self.write_request()
        self.engine.text=json.dumps(narrative(),ensure_ascii=False)
        self.assertEqual(worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory),0)
        response=json.loads(self.response.read_bytes())
        self.assertEqual(response['operation_id'],OPERATION_ID)
        self.assertEqual(response['result'],narrative())
        self.assertEqual(self.engine.calls[0][0],_generation_payload(saved_bundle(),'narrative',_worker_fixture.MODEL))
        self.assertTrue(self.engine.closed)

    def test_saved_story_echo_and_backend_phases_remain_distinguishable(self):
        value=saved_bundle()
        value['version']=4
        value['story_refinement']={'profile':STORY_REFINEMENT_PROFILE,'people':[]}
        narration='A family spent a long afternoon planting beans together, watering each row, and sharing what they hoped would grow. '
        narration *= 2
        value['chapters'][0]['narration']=narration
        self.body={'version':1,'kind':'saved_story_narrative_v1','operation_id':OPERATION_ID,'bundle':value}
        self.write_request()
        self.engine.responses=[json.dumps({'repairs':[]}),
            json.dumps({'repairs':[],'title':'A small garden story',
                'paragraphs':[narration], 'questions':[]},ensure_ascii=False)]
        with self.assertRaises(worker.SavedStoryWorkerFailure) as caught:
            worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory)
        self.assertEqual('unchanged_narration',caught.exception.phase)

        self.body={'version':1,'kind':'saved_story_narrative_v1','operation_id':OPERATION_ID,'bundle':saved_bundle()}
        self.write_request()
        self.engine.close()
        class TokenizerFailure:
            def __init__(self, _settings): pass
            def complete(self, _generation, _settings): raise worker.story.WorkerUnavailable('tokenize')
            def close(self): pass
        with patch.object(worker.story,'_LlamaEngine',TokenizerFailure):
            with self.assertRaises(worker.SavedStoryWorkerFailure) as backend_caught:
                worker.run(self.settings,enabled=True,environment=self.env)
        self.assertEqual('tokenize',backend_caught.exception.phase)
        code,record=worker._failure_record(backend_caught.exception)
        self.assertEqual(worker.SAVED_STORY_FAILURE_EXIT_CODES['tokenize'],code)
        self.assertEqual('tokenize',json.loads(record)['phase'])
    def test_v10_trust_filtered_editorial_profile_reaches_actual_worker_prompt(self):
        value = saved_bundle()
        value.update(version=4, story_refinement={'profile':STORY_REFINEMENT_PROFILE,
            'people':[{'name':'Test Canonical','aliases':['Test Alias']}]})
        value['title'] = 'Synthetic English story title label'
        value['chapters'][0]['title'] = 'Synthetic English chapter label'
        value['chapters'][0]['narration'] = (
            'A family gathered in the garden and talked beside the old tree, then recalled their walk home. ' * 2)
        value['chapters'][0]['evidence_ids'].extend(['transcript-note', 'ai-caption', 'metadata-hint'])
        value['sources'].extend([
            {'id':'transcript-note','kind':'transcript',
             'text':'We walked together after lunch and talked about the garden.',
             'asset_id':None,'author':'Synthetic Speaker'},
            {'id':'ai-caption','kind':'ai',
             'text':'An uncertain image guess: four jeweled lamps and an ornate blue clock.',
             'asset_id':'synthetic-asset','author':None},
            {'id':'metadata-hint','kind':'metadata',
             'text':'Unverified decoration note: four jeweled lamps and an ornate blue clock.',
             'asset_id':None,'author':None},
        ])
        original_value=deepcopy(value)
        self.body={'version':1,'kind':'saved_story_narrative_v1',
                   'operation_id':OPERATION_ID,'bundle':value}
        self.write_request()
        self.engine.responses=[json.dumps({'repairs':[{'before':'garden','after':'garden park'}]},ensure_ascii=False),
            json.dumps({'repairs':[],'title':'花园里的回忆',
                'paragraphs':['家人在花园里相聚，聊起往事，后来又一起走回家。'],
                'questions':[]},ensure_ascii=False)]
        self.assertEqual(worker.run(self.settings,enabled=True,environment=self.env,
                                    backend_factory=self.factory),0)
        first_prompt=self.engine.calls[0][0]['prompt']
        prompt=self.engine.calls[1][0]['prompt']
        self.assertIn('Task: saved_story_public_name_repairs_v10', first_prompt)
        self.assertNotIn('Test Canonical', first_prompt)
        self.assertNotIn('Test Alias', first_prompt)
        self.assertEqual({'temperature':0.2,'num_predict':256},self.engine.calls[0][0]['options'])
        self.assertEqual({'temperature':0.2,'num_predict':2048},self.engine.calls[1][0]['options'])
        self.assertIs(self.engine.calls[0][1],self.settings)
        self.assertIs(self.engine.calls[1][1],self.settings)
        self.assertIn('clear context and reliable common knowledge',prompt)
        self.assertIn('obvious ASR homophones in public people, places or proper names',prompt)
        self.assertIn('use only the canonical name',prompt)
        self.assertIn('never repeat aliases or “or”',prompt)
        self.assertIn('Preserve the full account',prompt)
        self.assertIn('do not summarize',prompt)
        self.assertIn('saved_story_editorial_v10',prompt)
        self.assertNotIn('Synthetic English story title label',prompt)
        self.assertNotIn('Synthetic English chapter label',prompt)
        self.assertNotIn('four jeweled lamps',prompt)
        self.assertNotIn('ornate blue clock',prompt)
        self.assertIn(value['sources'][0]['text'],prompt)
        self.assertIn('Test Canonical',prompt)
        self.assertIn('Test Alias',prompt)
        self.assertNotIn('ai-caption',prompt)
        self.assertNotIn('metadata-hint',prompt)
        self.assertNotIn('family-note-1',prompt)
        self.assertNotIn('source_ids',prompt)
        public_result=json.loads(self.response.read_bytes())['result']
        self.assertEqual({'version','title','chapters','questions','needs_review'},
                         set(public_result))
        self.assertTrue(public_result['needs_review'])
        self.assertEqual(value['chapters'][0]['id'], public_result['chapters'][0]['id'])
        self.assertEqual(['family-note-1', 'transcript-note'],
                         public_result['chapters'][0]['source_ids'])
        self.assertIn('public_name_suggestions', prompt)
        self.assertIn('garden park', prompt)
        self.assertEqual(2,len(self.engine.calls))
        self.factory.assert_called_once_with(self.settings)
        self.assertEqual(original_value,value)
        self.assertTrue(self.engine.closed)

    def test_v10_invalid_public_repair_plans_stop_before_prose_and_close_engine(self):
        value=saved_bundle()
        value.update(version=4,story_refinement={'profile':STORY_REFINEMENT_PROFILE,
            'people':[{'name':'Private Canonical','aliases':['Private Alias']}]})
        value['chapters'][0]['narration']='家人提到Private Alias，也在湖边散步。' * 2
        self.body={'version':1,'kind':'saved_story_narrative_v1','operation_id':OPERATION_ID,'bundle':value}
        invalid_plans=[
            {'repairs':[{'before':'invented phrase','after':'public spelling'}]},
            {'repairs':[{'before':'Private Alias','after':'public spelling'}]},
            {'repairs':[{'before':'湖边散步','after':'Private Canonical'}]},
        ]
        for plan in invalid_plans:
            with self.subTest(plan=plan):
                self.response.unlink(missing_ok=True)
                self.engine=_worker_fixture.SyntheticEngine(self.settings)
                self.factory=Mock(return_value=self.engine)
                self.engine.responses=[json.dumps(plan,ensure_ascii=False),json.dumps({})]
                self.write_request()
                with self.assertRaises(worker.SavedStoryWorkerFailure) as caught:
                    worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory)
                self.assertEqual('output_validation',caught.exception.phase)
                self.assertEqual(1,len(self.engine.calls))
                self.assertTrue(self.engine.closed)
                self.assertFalse(self.response.exists())

    def test_saved_story_failure_exit_codes_are_closed_and_content_free(self):
        expected = worker.SAVED_STORY_FAILURE_EXIT_CODES
        self.assertEqual(set(expected.values()), set(range(80, 97)))
        for phase, code in expected.items():
            with self.subTest(phase=phase):
                actual, record = worker._failure_record(worker.SavedStoryWorkerFailure(phase))
                self.assertEqual(code, actual)
                self.assertEqual({'status': 'failed', 'category': 'worker_unavailable',
                                  'phase': phase}, json.loads(record))
                self.assertNotIn('Traceback', record)
                self.assertNotIn('synthetic', record)
        original_code, original_record = worker._failure_record(worker.story.WorkerUnavailable('generation'))
        self.assertEqual(17, original_code)
        self.assertEqual('generation', json.loads(original_record)['phase'])

    def test_default_native_factory_is_selected_only_without_injected_factory(self):
        for kind in ('story', 'agent', 'saved'):
            with self.subTest(kind=kind):
                self.response.unlink(missing_ok=True)
                self.engine=_worker_fixture.SyntheticEngine(self.settings)
                if kind == 'agent':
                    self.body={'version':1,'kind':'agent_decision_v1','operation_id':OPERATION_ID,
                               'state':{'turn':{'version':1,'text':'Find photos','locale':'en'},
                                        'observations':[]}}
                    self.write_request();self.engine.text=json.dumps({'tool':'search_media'})
                elif kind == 'saved':
                    self.body={'version':1,'kind':'saved_story_narrative_v1','operation_id':OPERATION_ID,
                               'bundle':saved_bundle()}
                    self.write_request();self.engine.text=json.dumps(narrative(),ensure_ascii=False)
                else:
                    self.body={'version':1,'operation_id':OPERATION_ID,
                               'generation':worker.story._generation_payload(bundle(),'narrative',self.settings.model)}
                    self.write_request();self.engine.text=json.dumps(narrative(),ensure_ascii=False)
                default=Mock(return_value=self.engine)
                with patch.object(worker,'_default_backend_factory',default):
                    self.assertEqual(0,worker.run(self.settings,enabled=True,environment=self.env))
                default.assert_called_once_with(self.settings)
                self.assertTrue(self.engine.closed)
                self.assertTrue(self.response.exists())
                self.assertEqual(1,len(self.engine.calls))

    def test_injected_backend_factory_bypasses_optional_native_logger(self):
        with patch.object(worker,'_default_backend_factory') as default:
            self.assertEqual(0,worker.run(self.settings,enabled=True,environment=self.env,
                                          backend_factory=self.factory))
        default.assert_not_called();self.factory.assert_called_once_with(self.settings)

    def test_default_factory_classifies_bounded_error_logs_and_restores_exact_callback(self):
        native, package = fake_native_log_api()
        secret=b'PRIVATE-CANARY-PATH-and-model-details'
        def fail_constructor(settings):
            self.assertIs(settings,self.settings)
            native.emit(2,b'out of memory at non-error level')
            native.emit(3,b'GGML error: failed to allocate 8192 bytes '+secret)
            raise RuntimeError('private backend detail '+secret.decode())
        with patch.dict(sys.modules,{'llama_cpp':package,'llama_cpp.llama_cpp':native}), \
             patch.object(worker.story,'_LlamaEngine',side_effect=fail_constructor), \
             contextlib.redirect_stderr(io.StringIO()) as stderr:
            with self.assertRaises(worker.SavedStoryWorkerFailure) as caught:
                worker._default_backend_factory(self.settings)
        self.assertEqual('backend_memory',caught.exception.phase)
        self.assertEqual('',stderr.getvalue())
        self.assertNotIn(secret.decode(),str(caught.exception))
        self.assert_restored_callback(native)
        code,record=worker._failure_record(caught.exception)
        self.assertEqual(94,code)
        self.assertEqual({'status':'failed','category':'worker_unavailable','phase':'backend_memory'},
                         json.loads(record))
        self.assertNotIn(secret.decode(),record)

    def test_default_factory_classifies_architecture_and_preserves_unknown_backend_load(self):
        native, package = fake_native_log_api()
        def architecture_failure(_settings):
            native.emit(3,b'unknown model architecture: private-model-name')
            raise RuntimeError('native constructor failed')
        with patch.dict(sys.modules,{'llama_cpp':package,'llama_cpp.llama_cpp':native}), \
             patch.object(worker.story,'_LlamaEngine',side_effect=architecture_failure):
            with self.assertRaises(worker.SavedStoryWorkerFailure) as caught:
                worker._default_backend_factory(self.settings)
        self.assertEqual('backend_architecture',caught.exception.phase)
        self.assert_restored_callback(native)

        native, package = fake_native_log_api()
        with patch.dict(sys.modules,{'llama_cpp':package,'llama_cpp.llama_cpp':native}), \
             patch.object(worker.story,'_LlamaEngine',side_effect=RuntimeError('ordinary failure')):
            with self.assertRaisesRegex(RuntimeError,'ordinary failure'):
                worker._default_backend_factory(self.settings)
        self.assert_restored_callback(native)

    def test_default_factory_direct_memory_dependency_and_success_are_exact(self):
        for error, phase, code in ((MemoryError('private'), 'backend_memory', 94),
                                   (ImportError('private'), 'backend_dependency', 96)):
            native, package = fake_native_log_api()
            with self.subTest(phase=phase), \
                 patch.dict(sys.modules,{'llama_cpp':package,'llama_cpp.llama_cpp':native}), \
                 patch.object(worker.story,'_LlamaEngine',side_effect=error):
                with self.assertRaises(worker.SavedStoryWorkerFailure) as caught:
                    worker._default_backend_factory(self.settings)
                self.assertEqual(phase,caught.exception.phase)
                self.assertEqual(code,worker._failure_record(caught.exception)[0])
                self.assert_restored_callback(native)

        native, package = fake_native_log_api()
        returned=object();seen=[]
        def successful_constructor(settings):
            seen.append(settings)
            native.emit(3,b'unsupported architecture but constructor succeeded')
            return returned
        with patch.dict(sys.modules,{'llama_cpp':package,'llama_cpp.llama_cpp':native}), \
             patch.object(worker.story,'_LlamaEngine',side_effect=successful_constructor):
            self.assertIs(returned,worker._default_backend_factory(self.settings))
        self.assertEqual([self.settings],seen)
        self.assert_restored_callback(native)

    def assert_restored_callback(self,native):
        self.assertEqual(ctypes.cast(native.current_callback,ctypes.c_void_p).value,
                         ctypes.cast(native.previous_callback,ctypes.c_void_p).value)
        self.assertEqual(native.current_userdata.value,native.previous_userdata.value)

    def test_native_callback_is_error_only_bounded_and_restores_callback(self):
        native, package = fake_native_log_api()
        with patch.dict(sys.modules,{'llama_cpp':package,'llama_cpp.llama_cpp':native}):
            capture=worker._install_native_log_capture()
            self.assertIsNotNone(capture)
            native.emit(2,b'out of memory at non-error level')
            native.emit(3,b'x'*8192+b' out of memory beyond bounded slice')
            self.assertEqual({'memory':False,'architecture':False},capture.flags)
            native.emit(3,b'unsupported model architecture: private label')
            self.assertEqual({'memory':False,'architecture':True},capture.flags)
            self.assertTrue(all(type(value) is bool for value in capture.flags.values()))
            capture.restore()
        self.assert_restored_callback(native)

    def test_native_logger_setup_failure_still_calls_exact_constructor(self):
        native, package = fake_native_log_api()
        original_set=native.llama_log_set
        attempts=[]
        def fail_first_set(callback,userdata):
            attempts.append((callback,userdata))
            if len(attempts)==1:
                raise RuntimeError('synthetic logger setup failure')
            return original_set(callback,userdata)
        native.llama_log_set=fail_first_set
        returned=object();seen=[]
        def constructor(settings):
            seen.append(settings)
            return returned
        with patch.dict(sys.modules,{'llama_cpp':package,'llama_cpp.llama_cpp':native}), \
             patch.object(worker.story,'_LlamaEngine',side_effect=constructor):
            self.assertIs(returned,worker._default_backend_factory(self.settings))
        self.assertEqual([self.settings],seen)
        self.assertEqual(2,len(attempts))
        self.assert_restored_callback(native)

    def test_household_main_emits_saved_phase_from_real_cli_exception_path(self):
        self.body={'version':1,'kind':'saved_story_narrative_v1','operation_id':OPERATION_ID,'bundle':saved_bundle()}
        self.write_request()
        class FailedEngine:
            def __init__(self, _settings): pass
            def complete(self, _generation, _settings): raise RuntimeError('private engine detail')
            def close(self): pass
        argv=[str(SCRIPTS/'household_gguf_worker.py'),'--execute',
              '--model-file',self.settings.model_file,'--model-sha256',self.settings.model_sha256,
              '--model-label',self.settings.model]
        stderr=io.StringIO()
        with patch.object(worker.story,'_model_pin',return_value=(Path(self.settings.model_file),('fixture',))), \
             patch.object(worker.story,'_LlamaEngine',FailedEngine), \
             patch.dict(os.environ,self.env,clear=True), patch.object(sys,'argv',argv), \
             contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                runpy.run_path(str(SCRIPTS/'household_gguf_worker.py'),run_name='__main__')
        self.assertEqual(83,caught.exception.code)
        self.assertEqual({'status':'failed','category':'worker_unavailable','phase':'generation'},
                         json.loads(stderr.getvalue()))
        self.assertNotIn('private engine detail',stderr.getvalue())
        self.assertFalse(self.response.exists())

    def test_saved_story_packet_rejects_draft_wrong_target_or_extra_fields(self):
        for mutate in (
                lambda value:value.update(bundle=bundle()),
                lambda value:value['bundle']['target'].update(type='book'),
                lambda value:value.update(extra=True),
                lambda value:value['bundle']['target'].update(id=OPERATION_ID)):
            with self.subTest(mutate=mutate):
                self.body={'version':1,'kind':'saved_story_narrative_v1','operation_id':OPERATION_ID,'bundle':saved_bundle()}
                mutate(self.body);self.write_request()
                with self.assertRaises(worker.story.WorkerUnavailable):
                    worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory)
                self.assertFalse(self.response.exists())
    def test_foreign_operation_or_unknown_tool_never_publishes(self):
        self.body={'version':1,'kind':'agent_decision_v1','operation_id':OPERATION_ID,'state':{'turn':{'version':1,'text':'Find photos','locale':'en'},'observations':[]}};self.write_request();self.engine.text=json.dumps({'tool':'shell','command':'private data'})
        with self.assertRaises(worker.story.WorkerUnavailable):worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory)
        self.assertTrue(self.engine.closed);self.assertFalse(self.response.exists())
    def test_disabled_does_not_read_exchange_or_load_backend(self):
        with self.assertRaises(worker.story.WorkerUnavailable):worker.run(self.settings,environment=self.env,backend_factory=self.factory)
        self.factory.assert_not_called();self.assertFalse(self.response.exists())

class HouseholdIsolatedCLITests(unittest.TestCase):
    def test_real_isolated_cli_help_imports_without_model_or_runtime(self):
        # Production launch uses -I, which removes the script directory from
        # sys.path. Execute that actual cold entry rather than an imported fixture.
        value=subprocess.run([sys.executable,'-I','-B',str(SCRIPTS/'household_gguf_worker.py'),'--help'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(value.returncode,0,value.stderr.decode('utf-8','replace'))
        self.assertIn(b'--model-file',value.stdout)
        self.assertNotIn(b'Traceback',value.stderr)
        program = (f'import sys;sys.path.insert(0,{str(SCRIPTS)!r});'
                   'import household_gguf_worker;assert "llama_cpp" not in sys.modules')
        cold=subprocess.run([sys.executable,'-I','-B','-c',program],capture_output=True,
                            text=True,timeout=10)
        self.assertEqual(0,cold.returncode,cold.stderr)

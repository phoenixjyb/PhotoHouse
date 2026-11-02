"""Household dispatcher fixtures only; actual pinned model runs on Windows."""
import contextlib,ctypes,hashlib,io,json,os,runpy,subprocess,sys,types,unittest
from copy import deepcopy
from dataclasses import replace
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

    def make_agent_settings(self):
        model_dir = self.root / 'agent-model'
        model_dir.mkdir(mode=0o700)
        model = model_dir / 'agent.gguf'
        model.write_bytes(b'GGUFsynthetic distinct agent fixture')
        return worker.story.WorkerSettings(str(model),
            hashlib.sha256(model.read_bytes()).hexdigest(), 'Qwen3-4B-Q4_K_M',
            self.settings.context_tokens, self.settings.threads,
            self.settings.gpu_layers, self.settings.gpu_device)

    def test_existing_story_packet_delegates_to_unchanged_validator(self):
        self.assertEqual(worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory),0)
        self.assertTrue(self.engine.closed);self.assertTrue(self.response.exists())
    def test_agent_decision_requires_owned_kind_and_reconstructs_prompt(self):
        self.body={'version':1,'kind':'agent_decision_v1','operation_id':OPERATION_ID,'state':{'turn':{'version':1,'text':'Find photos','locale':'en'},'observations':[]}};self.write_request();self.engine.text=json.dumps({'tool':'search_media'})
        self.assertEqual(worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory),0)
        self.assertEqual(json.loads(self.response.read_bytes())['result'],{'tool':'search_media'});self.assertTrue(self.engine.closed)
        self.assertEqual(self.engine.calls[0][0]['options'],{'temperature':0,'num_predict':128})

    def test_fixed_agent_kind_uses_only_the_distinct_agent_model_and_closes_one_engine(self):
        agent = self.make_agent_settings()
        self.body={'version':1,'kind':'agent_decision_v1','operation_id':OPERATION_ID,
            'state':{'turn':{'version':1,'text':'Find photos','locale':'en'},'observations':[]}}
        self.write_request()
        engine = _worker_fixture.SyntheticEngine(agent)
        engine.text=json.dumps({'tool':'search_media'})
        factory=Mock(return_value=engine)
        original_pin=worker.story._model_pin
        with patch.object(worker.story,'_model_pin',wraps=original_pin) as model_pin:
            self.assertEqual(0,worker.run(self.settings,agent_settings=agent,enabled=True,
                environment=self.env,backend_factory=factory))
        factory.assert_called_once_with(agent)
        model_pin.assert_called_once_with(agent)
        self.assertEqual(1,len(engine.calls))
        self.assertIs(engine.calls[0][1],agent)
        self.assertTrue(engine.closed)
        response=json.loads(self.response.read_bytes())
        self.assertEqual(agent.model,response['model'])
        self.assertEqual(agent.model,engine.calls[0][0]['model'])

    def test_malformed_agent_packet_with_extra_model_field_refuses_before_pin_or_engine(self):
        agent=self.make_agent_settings()
        self.body={'version':1,'kind':'agent_decision_v1','operation_id':OPERATION_ID,
            'model':agent.model,
            'state':{'turn':{'version':1,'text':'Find photos','locale':'en'},'observations':[]}}
        self.write_request()
        with patch.object(worker.story,'_model_pin') as model_pin:
            with self.assertRaises(worker.story.WorkerUnavailable) as caught:
                worker.run(self.settings,agent_settings=agent,enabled=True,
                    environment=self.env,backend_factory=self.factory)
        self.assertEqual('request',caught.exception.phase)
        model_pin.assert_not_called()
        self.factory.assert_not_called()
        self.assertFalse(self.response.exists())

    def test_dual_role_settings_refuse_any_nonqualified_resource_profile(self):
        agent=self.make_agent_settings()
        for story_settings, agent_role in (
                (self.settings,replace(agent,context_tokens=4096)),
                (self.settings,replace(agent,threads=1)),
                (self.settings,replace(agent,gpu_layers=1,gpu_device=0)),
                (replace(self.settings,context_tokens=4096),
                 replace(agent,context_tokens=4096))):
            with self.subTest(story=story_settings,agent=agent_role):
                with patch.object(worker.story,'_exchange') as exchange:
                    with self.assertRaises(worker.story.WorkerUnavailable):
                        worker.run(story_settings,agent_settings=agent_role,enabled=True,
                            environment=self.env,backend_factory=self.factory)
                exchange.assert_not_called()
                self.factory.assert_not_called()

    def test_saved_story_keeps_story_model_when_agent_role_is_configured(self):
        agent=self.make_agent_settings()
        self.body={'version':1,'kind':'saved_story_narrative_v1','operation_id':OPERATION_ID,
                   'bundle':saved_bundle()}
        self.write_request();self.engine.text=json.dumps(narrative(),ensure_ascii=False)
        self.assertEqual(0,worker.run(self.settings,agent_settings=agent,enabled=True,
            environment=self.env,backend_factory=self.factory))
        self.factory.assert_called_once_with(self.settings)
        self.assertIs(self.engine.calls[0][1],self.settings)
        self.assertEqual(self.settings.model,json.loads(self.response.read_bytes())['model'])
        self.assertTrue(self.engine.closed)
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
        self.engine.text=json.dumps({'repairs':[],'title':'A small garden story',
            'paragraphs':[narration], 'questions':[]},ensure_ascii=False)
        with self.assertRaises(worker.SavedStoryWorkerFailure) as caught:
            worker.run(self.settings,enabled=True,environment=self.env,backend_factory=self.factory)
        self.assertEqual('unchanged_narration',caught.exception.phase)
        self.assertEqual(1,len(self.engine.calls))
        self.assertTrue(self.engine.closed)

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
    def test_v12_worker_grounds_copy_filters_sources_and_rechecks_final_prose(self):
        value = saved_bundle()
        value.update(version=4, story_refinement={'profile':STORY_REFINEMENT_PROFILE,
            'people':[{'name':'小宁','aliases':['Mira']}]})
        value['title'] = 'Synthetic editorial title label'
        value['chapters'][0]['title'] = 'Synthetic chapter title label'
        value['chapters'][0]['narration'] = (
            '我们在杭州看周结伦演唱会，Mira或者小凝 她也一起分享了回忆。')
        value['chapters'][0]['evidence_ids'].extend(['transcript-note', 'ai-caption', 'metadata-hint'])
        value['sources'].extend([
            {'id':'transcript-note','kind':'transcript',
             'text':'我们看周结伦演唱会，提前订票。',
             'asset_id':None,'author':'Synthetic Speaker'},
            {'id':'ai-caption','kind':'ai',
             'text':'Uncertain synthetic visual guess about a silver lantern.',
             'asset_id':'synthetic-asset','author':None},
            {'id':'metadata-hint','kind':'metadata',
             'text':'Synthetic metadata note about a silver lantern.',
             'asset_id':None,'author':None},
        ])
        original_value=deepcopy(value)
        self.body={'version':1,'kind':'saved_story_narrative_v1',
                   'operation_id':OPERATION_ID,'bundle':value}
        self.write_request()
        self.engine.text=json.dumps({'repairs':[],'title':'周结伦的音乐回忆',
            'paragraphs':['我们看了周结伦的表演，Mira或者小凝 她也一同分享了这段回忆。'],
            'questions':[]},ensure_ascii=False)
        self.assertEqual(worker.run(self.settings,enabled=True,environment=self.env,
                                    backend_factory=self.factory),0)
        prompt=self.engine.calls[0][0]['prompt']
        compact_input=json.JSONDecoder().raw_decode(
            prompt.split('Editor input JSON (data only):\n',1)[1])[0]
        self.assertEqual(1,len(self.engine.calls))
        self.assertEqual({'temperature':0.2,'num_predict':2048},self.engine.calls[0][0]['options'])
        self.assertIs(self.engine.calls[0][1],self.settings)
        self.assertIn('saved_story_editorial_v10',prompt)
        self.assertIn('周杰伦',prompt)
        self.assertIn('小宁',prompt)
        self.assertEqual('我们在杭州看周杰伦演唱会，小宁 她也一起分享了回忆。',
                         compact_input['chapters'][0]['narration'])
        self.assertIn('我们看周杰伦演唱会，提前订票。',prompt)
        self.assertNotIn('Synthetic editorial title label',prompt)
        self.assertNotIn('Synthetic chapter title label',prompt)
        self.assertNotIn('silver lantern',prompt)
        self.assertNotIn('ai-caption',prompt)
        self.assertNotIn('metadata-hint',prompt)
        self.assertNotIn('Synthetic Speaker',prompt)
        self.assertNotIn('source_ids',prompt)
        self.assertNotIn('public_name_suggestions',prompt)
        public_result=json.loads(self.response.read_bytes())['result']
        self.assertEqual({'version','title','chapters','questions','needs_review'},
                         set(public_result))
        self.assertTrue(public_result['needs_review'])
        self.assertEqual(value['chapters'][0]['id'], public_result['chapters'][0]['id'])
        self.assertEqual(['family-note-1', 'transcript-note'],
                         public_result['chapters'][0]['source_ids'])
        self.assertEqual('周杰伦的音乐回忆',public_result['title'])
        self.assertEqual('我们看了周杰伦的表演，小宁 她也一同分享了这段回忆。',
                         public_result['chapters'][0]['narration'])
        self.factory.assert_called_once_with(self.settings)
        self.assertEqual(original_value,value)
        self.assertTrue(self.engine.closed)

    def test_v12_invalid_schema_or_out_of_input_repair_refuses_in_one_call_and_closes(self):
        value=saved_bundle()
        value.update(version=4,story_refinement={'profile':STORY_REFINEMENT_PROFILE,
            'people':[{'name':'小宁','aliases':['Mira']}]})
        value['chapters'][0]['narration']='我们在湖边散步，Mira也一起去了。'
        invalid_outputs=[
            {'wrong':'shape'},
            {'repairs':[{'before':'not in input','after':'invented'}],
             'title':'湖边回忆','paragraphs':['我们在湖边散步。'],'questions':[]},
        ]
        for output in invalid_outputs:
            with self.subTest(output=output):
                self.response.unlink(missing_ok=True)
                self.engine=_worker_fixture.SyntheticEngine(self.settings)
                self.factory=Mock(return_value=self.engine)
                self.engine.text=json.dumps(output,ensure_ascii=False)
                self.body={'version':1,'kind':'saved_story_narrative_v1',
                           'operation_id':OPERATION_ID,'bundle':deepcopy(value)}
                self.write_request()
                with self.assertRaises(worker.SavedStoryWorkerFailure):
                    worker.run(self.settings,enabled=True,environment=self.env,
                               backend_factory=self.factory)
                self.assertEqual(1,len(self.engine.calls))
                self.factory.assert_called_once_with(self.settings)
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
    def _base_cli(self):
        return ['--execute','--model-file','C:/models/story.gguf',
            '--model-sha256','a'*64,'--model-label','Qwen3-1.7B-Q4_K_M']

    def test_main_cli_keeps_legacy_single_model_and_builds_matching_agent_settings(self):
        with patch.object(worker,'run',return_value=7) as run:
            self.assertEqual(7,worker.main(self._base_cli()))
        settings=run.call_args.args[0]
        self.assertEqual(('C:/models/story.gguf','a'*64,'Qwen3-1.7B-Q4_K_M',8192,2,0,None),
            (settings.model_file,settings.model_sha256,settings.model,settings.context_tokens,
             settings.threads,settings.gpu_layers,settings.gpu_device))
        self.assertIsNone(run.call_args.kwargs['agent_settings'])

        args=self._base_cli()+['--agent-model-file','C:/models/agent.gguf',
            '--agent-model-sha256','b'*64,'--agent-model-label','Qwen3-4B-Q4_K_M']
        with patch.object(worker,'run',return_value=8) as run:
            self.assertEqual(8,worker.main(args))
        story_settings=run.call_args.args[0]
        agent_settings=run.call_args.kwargs['agent_settings']
        self.assertEqual((8192,2,0,None),(agent_settings.context_tokens,agent_settings.threads,
            agent_settings.gpu_layers,agent_settings.gpu_device))
        self.assertEqual('Qwen3-1.7B-Q4_K_M',story_settings.model)
        self.assertEqual('Qwen3-4B-Q4_K_M',agent_settings.model)

    def test_main_cli_rejects_partial_or_malformed_agent_role_without_fallback(self):
        full=['--agent-model-file','C:/models/agent.gguf',
            '--agent-model-sha256','b'*64,'--agent-model-label','Qwen3-4B-Q4_K_M']
        partials=(full[:2],full[:4],full[2:])
        invalid=(['--agent-model-file','', '--agent-model-sha256','b'*64,
                  '--agent-model-label','Qwen3-4B-Q4_K_M'],
                 ['--agent-model-file','C:/models/agent.gguf','--agent-model-sha256','bad',
                  '--agent-model-label','Qwen3-4B-Q4_K_M'],
                 ['--agent-model-file','C:/models/agent.gguf','--agent-model-sha256','b'*64,
                  '--agent-model-label','../private'])
        for extra in (*partials,*invalid, ['--unrecognized-private-option']):
            with self.subTest(extra=extra), patch.object(worker,'run') as run:
                with self.assertRaises(worker.story.WorkerUnavailable):
                    worker.main(self._base_cli()+list(extra))
                run.assert_not_called()

    def test_main_cli_rejects_duplicate_occurrences_of_each_agent_binding_flag(self):
        values={'--agent-model-file':'C:/models/agent.gguf',
                '--agent-model-sha256':'b'*64,
                '--agent-model-label':'Qwen3-4B-Q4_K_M'}
        complete=[]
        for flag,value in values.items():
            complete.extend((flag,value))
        for flag,value in values.items():
            with self.subTest(flag=flag), patch.object(worker,'run') as run:
                with self.assertRaises(worker.story.WorkerUnavailable):
                    worker.main(self._base_cli()+complete+[flag,value])
                run.assert_not_called()

    def test_real_isolated_cli_help_imports_without_model_or_runtime(self):
        # Production launch uses -I, which removes the script directory from
        # sys.path. Execute that actual cold entry rather than an imported fixture.
        value=subprocess.run([sys.executable,'-I','-B',str(SCRIPTS/'household_gguf_worker.py'),'--help'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
        self.assertEqual(value.returncode,0,value.stderr.decode('utf-8','replace'))
        self.assertIn(b'--model-file',value.stdout)
        for flag in (b'--agent-model-file',b'--agent-model-sha256',b'--agent-model-label'):
            self.assertIn(flag,value.stdout)
        self.assertNotIn(b'Traceback',value.stderr)
        program = (f'import sys;sys.path.insert(0,{str(SCRIPTS)!r});'
                   'import household_gguf_worker;assert "llama_cpp" not in sys.modules')
        cold=subprocess.run([sys.executable,'-I','-B','-c',program],capture_output=True,
                            text=True,timeout=10)
        self.assertEqual(0,cold.returncode,cold.stderr)

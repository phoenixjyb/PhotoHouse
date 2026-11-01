"""Household dispatcher fixtures only; actual pinned model runs on Windows."""
import contextlib,hashlib,io,json,os,runpy,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch

SCRIPTS=Path(__file__).resolve().parents[2]/'scripts';sys.path.insert(0,str(SCRIPTS))
import household_gguf_worker as worker
import test_selected_story_gguf_worker as _worker_fixture
from test_selected_story_local import OPERATION_ID, bundle, narrative
from backend.app.access.memory_narrative import _generation_payload

STORY_ID='12345678-1234-4234-8234-123456789abc'

def saved_bundle():
    value=bundle();value['version']=1
    value['target']={'type':'story','id':STORY_ID,'revision':7}
    value.pop('selection_revision')
    for source in value['sources']:source.pop('source_kind')
    return value

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
        value['story_refinement']={'profile':'asr_editorial_v6','people':[]}
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
    def test_editorial_profile_reaches_the_actual_saved_story_worker_prompt(self):
        value = saved_bundle()
        value.update(version=4, story_refinement={'profile':'asr_editorial_v6',
            'people':[{'name':'林澄','aliases':['Lina']}]})
        value['chapters'][0]['narration'] = (
            'A family gathered in the garden and talked beside the old tree. ' * 2)
        self.body={'version':1,'kind':'saved_story_narrative_v1',
                   'operation_id':OPERATION_ID,'bundle':value}
        self.write_request()
        self.engine.text=json.dumps({'repairs':[],'title':'A family memory',
            'paragraphs':['The family met by the garden tree and shared memories.'],
            'questions':[]},ensure_ascii=False)
        self.assertEqual(worker.run(self.settings,enabled=True,environment=self.env,
                                    backend_factory=self.factory),0)
        prompt=self.engine.calls[0][0]['prompt']
        self.assertIn('ASR, homophone and proper-name repairs',prompt)
        self.assertIn('remove filler and repetition',prompt)
        self.assertIn('林澄',prompt)
        self.assertNotIn('family-note-1',prompt)
        self.assertNotIn('source_ids',prompt)
        public_result=json.loads(self.response.read_bytes())['result']
        self.assertEqual({'version','title','chapters','questions','needs_review'},
                         set(public_result))
        self.assertTrue(public_result['needs_review'])
        self.assertEqual(value['chapters'][0]['id'], public_result['chapters'][0]['id'])
        self.assertEqual(value['chapters'][0]['evidence_ids'],
                         public_result['chapters'][0]['source_ids'])
        self.assertEqual(1,len(self.engine.calls))
        self.assertTrue(self.engine.closed)

    def test_saved_story_failure_exit_codes_are_closed_and_content_free(self):
        expected = worker.SAVED_STORY_FAILURE_EXIT_CODES
        self.assertEqual(set(expected.values()), set(range(80, 94)))
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

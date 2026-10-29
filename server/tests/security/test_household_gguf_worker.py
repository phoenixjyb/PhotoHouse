"""Household dispatcher fixtures only; actual pinned model runs on Windows."""
import hashlib,json,os,subprocess,sys,unittest
from pathlib import Path
from unittest.mock import Mock

SCRIPTS=Path(__file__).resolve().parents[2]/'scripts';sys.path.insert(0,str(SCRIPTS))
import household_gguf_worker as worker
import test_selected_story_gguf_worker as _worker_fixture
from test_selected_story_local import OPERATION_ID

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

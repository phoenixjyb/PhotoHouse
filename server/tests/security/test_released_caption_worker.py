"""Generated-media worker journeys; all HTTP and process launches are synthetic."""
from contextlib import closing
from dataclasses import replace
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch
import uuid

import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'tests/security'))
import test_promotion as fixture
from app.access.promotion import promote_and_assign
from app.access.provisioning_apply import _identity
from app.access.runtime import ExistingDatabase
from app.access.original_deletions import OriginalDeletionJournal
from app.access.upload_processing import release_deferred_upload_starters
from app.approved_caption_http import LocalCaptionHTTP
spec=importlib.util.spec_from_file_location('released_caption_launcher', ROOT/'scripts/run_released_caption_worker.py')
worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
GOOD='EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子放在木桌上。'
MODEL='Qwen/Qwen3-VL-8B-Instruct'


class ReleasedCaptionWorkerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixture.PromotionTests.setUpClass()
    @classmethod
    def tearDownClass(cls): fixture.PromotionTests.tearDownClass()

    def setUp(self):
        self.f=fixture.PromotionTests();self.f.setUp();self.addCleanup(self.f.doCleanups)
        output=io.BytesIO()
        with Image.new('RGB',(48,32),'red') as image:image.save(output,format='PNG')
        self.raw=output.getvalue()
        self.asset=int(self.f.upload(self.raw)['asset_id'])
        envelope=self.f.planned('promote',library_id='family-a',operator_account_id=self.f.owner_id,asset_ids=[self.asset])
        promote_and_assign(envelope,review=self.f.review(envelope),clock=lambda:fixture.NOW,release_starters=False)
        expected=[dict(r) for r in self.f.rows('SELECT id,type,payload_json,state FROM tasks WHERE json_extract(payload_json,\'$.asset_id\')=? ORDER BY id',(self.asset,))]
        release=release_deferred_upload_starters(envelope,database_factory=ExistingDatabase(self.f.path.resolve()),
            database_identity=_identity(self.f.path.resolve()),operator_account_id=self.f.owner_id,library_id='family-a',
            asset_ids=[self.asset],expected_tasks=expected,authority_reference='synthetic-caption',clock=lambda:fixture.NOW)
        self.task=next(r['task_id'] for r in release['released_tasks'] if r['type']=='caption')
        journal=OriginalDeletionJournal.initialize(self.f.root/'journal.sqlite',str(uuid.uuid4()),format_version=3)
        with self.f.connection() as db:journal.bind(db)
        self.config=dict(database=str(self.f.path),originals_root=str(self.f.originals),
            original_deletion_journal_path=str(journal.path),original_deletion_namespace=journal.namespace,
            operator_account_id=self.f.owner_id,library_id='family-a',release_plan_id=release['plan_id'],
            task_ids=[self.task],caption_url='http://127.0.0.1:8102',expected_model_id=MODEL,
            stop_file=str(self.f.root/'stop.flag'),provider_timeout_seconds=60)
        self.config_path=self.f.root/'worker.json';self.write_config()
        self.report=self.f.root/'run.json';self.requests=[];self.launches=[]
        self.launch_env=None

    def write_config(self):
        self.config_path.write_text(json.dumps(self.config));self.config_path.chmod(0o600)

    def http(self,request):
        self.requests.append(request.url.path)
        if request.url.path=='/health':
            return httpx.Response(200,json={'status':'healthy','active_provider':'qwen3-vl','model_cache_ready':True})
        if request.url.path=='/caption':
            self.assertIn(b'Content-Type: image/png',request.read())
            return httpx.Response(200,json={'caption':GOOD,'provider':'qwen3-vl','model':MODEL})
        raise AssertionError('Unexpected endpoint')

    def provider(self,config):
        p=LocalCaptionHTTP(url=config['caption_url'],expected_model_id=MODEL,transport=httpx.MockTransport(self.http))
        p.preflight();return p

    def fake_launch(self,api,exe,argv,env,cwd,**limits):
        self.launches.append(limits);self.launch_env=env
        task=int(argv[argv.index('--bounded-task')+1])
        digest=argv[argv.index('--config-sha256')+1]
        result=Path(argv[argv.index('--result')+1])
        with patch.object(worker,'verify_child_budget'):
            worker.task_child(self.config_path,digest,task,result)
        return 0

    def execute(self,launch=None):
        class Native:
            def free_ram(inner):return worker.FREE_RAM_FLOOR+1
        with patch.object(worker.sys,'platform','win32'),patch.object(worker,'_provider',side_effect=self.provider):
            return worker.run(self.config_path,execute=True,report_path=self.report,
                api_factory=Native,launch=launch or self.fake_launch)

    def state(self):return tuple(self.f.rows('SELECT state,retry_count,last_error FROM tasks WHERE id=?',(self.task,))[0])

    def test_default_preflight_has_no_provider_or_process_or_file_effects(self):
        before=[tuple(r) for r in self.f.rows('SELECT * FROM tasks')]
        with patch.object(worker,'_provider',side_effect=AssertionError('No provider')):
            result=worker.run(self.config_path)
        self.assertFalse(result['activated']);self.assertFalse(result['provider_checked'])
        self.assertEqual(before,[tuple(r) for r in self.f.rows('SELECT * FROM tasks')])
        self.assertFalse(self.report.exists());self.assertEqual(self.requests,[])

    def test_generated_image_through_mock_http_to_bound_database(self):
        result=self.execute()
        self.assertEqual(result['state'],'attempts_finished');self.assertTrue(result['all_selected_finished'])
        self.assertEqual(self.state(),('finished',0,None))
        self.assertEqual(self.f.rows('SELECT text FROM captions WHERE asset_id=?',(self.asset,))[0][0],GOOD)
        self.assertEqual(self.requests.count('/caption'),1)
        self.assertEqual(len(self.launches),1)
        self.assertEqual(self.launches[0],{'timeout_seconds':300,'memory_limit':2*1024**3,
            'process_limit':8,'minimum_free_ram':8*1024**3,'require_child_job_proof':True})
        self.assertNotIn('HTTP_PROXY',self.launch_env)
        source=Path(self.f.rows('SELECT path FROM assets WHERE id=?',(self.asset,))[0][0])
        self.assertEqual(source.read_bytes(),self.raw)

    def test_explicit_stop_prevents_admission_and_claim(self):
        Path(self.config['stop_file']).touch()
        with self.assertRaisesRegex(worker.WorkerRefused,'stop_requested'):self.execute()
        self.assertEqual(self.requests,[]);self.assertEqual(self.state()[0],'pending')
        self.assertFalse(self.report.exists())

    def test_unavailable_provider_does_not_consume_attempt(self):
        with patch.object(worker.sys,'platform','win32'),patch.object(worker,'_provider',side_effect=RuntimeError('private error')):
            class Native:
                def free_ram(inner):return worker.FREE_RAM_FLOOR+1
            with self.assertRaises(RuntimeError):
                worker.run(self.config_path,execute=True,report_path=self.report,api_factory=Native)
        self.assertEqual(self.state(),('pending',0,None));self.assertFalse(self.report.exists())

    def test_low_memory_prevents_provider_and_task_claim(self):
        class LowMemory:
            def free_ram(inner):return worker.FREE_RAM_FLOOR-1
        with patch.object(worker.sys,'platform','win32'),patch.object(worker,'_provider',side_effect=AssertionError('No provider')):
            with self.assertRaisesRegex(worker.WorkerRefused,'free_ram_below_minimum'):
                worker.run(self.config_path,execute=True,report_path=self.report,api_factory=LowMemory)
        self.assertEqual(self.state(),('pending',0,None))

    def test_child_nonzero_stops_without_replaying_or_resetting(self):
        def interrupted(*args,**kwargs):
            self.f.mutate("UPDATE tasks SET state='running',last_error='owned-interruption' WHERE id=?",(self.task,))
            return 1
        with self.assertRaisesRegex(worker.WorkerRefused,'child_interrupted_inspect_owned_claim'):
            self.execute(interrupted)
        self.assertEqual(self.state(),('running',0,'owned-interruption'))
        self.assertEqual(json.loads(self.report.read_bytes())['state'],'stopped_requires_review')
        self.report.unlink() # Only the fixture's own report, for the second admission check.
        with self.assertRaisesRegex(worker.WorkerRefused,'running_claim_requires_review'):self.execute()

    def test_completed_selection_needs_no_provider_or_launch(self):
        self.execute()
        self.requests.clear()
        with patch.object(worker,'_provider',side_effect=AssertionError('No model')):
            result=worker.run(self.config_path,execute=True,report_path=self.f.root/'unused.json')
        self.assertEqual(result['state'],'no_due_tasks');self.assertTrue(result['all_selected_finished'])
        self.assertEqual(self.requests,[])

    def test_failed_selection_remains_failed_and_is_not_called_ready(self):
        self.f.mutate("UPDATE tasks SET state='failed',retry_count=3,last_error='retained' WHERE id=?",(self.task,))
        with patch.object(worker,'_provider',side_effect=AssertionError('No model')):
            result=worker.run(self.config_path,execute=True,report_path=self.report)
        self.assertEqual(result['state'],'no_due_tasks');self.assertFalse(result['all_selected_finished'])
        self.assertEqual(self.state(),('failed',3,'retained'))

    def test_duplicate_config_keys_and_remote_model_endpoint_are_refused(self):
        self.config_path.write_text('{"database":"a","database":"b"}')
        with self.assertRaises(worker.WorkerRefused):worker.read_config(self.config_path)
        self.config['caption_url']='http://example.test:8102';self.write_config()
        with self.assertRaises(worker.WorkerRefused):worker.read_config(self.config_path)

    def test_stop_and_report_cannot_target_originals_or_stores(self):
        self.config['stop_file']=str(self.f.originals/'bad.stop');self.write_config()
        with self.assertRaises(worker.WorkerRefused):worker.read_config(self.config_path)
        self.config['stop_file']=str(self.f.root/'stop.flag');self.write_config()
        self.report=Path(self.config['database'])
        with self.assertRaisesRegex(worker.WorkerRefused,'new_private_report_required'):self.execute()
        self.assertEqual(self.state()[0],'pending')

    def test_direct_child_is_rejected_before_database_or_provider(self):
        with patch.object(worker.sys,'platform','darwin'),patch.object(worker,'read_config',side_effect=AssertionError('No config')):
            with self.assertRaisesRegex(worker.WorkerRefused,'windows_required'):
                worker.task_child(self.config_path,'bad',self.task,self.f.root/'result.json')

    def test_explicit_job_proof_is_checked_instead_of_an_implicit_outer_job(self):
        flags = (worker.JOB_OBJECT_LIMIT_ACTIVE_PROCESS | worker.JOB_OBJECT_LIMIT_JOB_MEMORY
                 | worker.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
        class Proven:
            def consume_job_proof(inner):
                return {'flags': flags, 'memory_limit': worker.MEMORY_LIMIT,
                        'process_limit': worker.PROCESS_LIMIT}
            def free_ram(inner): return worker.FREE_RAM_FLOOR
        with patch.object(worker.sys, 'platform', 'win32'), patch.object(worker, 'WindowsAPI', Proven):
            worker.verify_child_budget()

    def test_explicit_job_proof_drift_or_low_memory_refuses_before_database(self):
        flags = (worker.JOB_OBJECT_LIMIT_ACTIVE_PROCESS | worker.JOB_OBJECT_LIMIT_JOB_MEMORY
                 | worker.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE)
        valid = {'flags': flags, 'memory_limit': worker.MEMORY_LIMIT, 'process_limit': worker.PROCESS_LIMIT}
        for changed in ({**valid, 'flags': 12288}, {**valid, 'memory_limit': 0},
                        {**valid, 'process_limit': 0}, {**valid, 'unexpected': True}):
            class Drifted:
                def consume_job_proof(inner): return changed
                def free_ram(inner): raise AssertionError('No RAM admission after bad proof')
            with self.subTest(changed=changed), patch.object(worker.sys, 'platform', 'win32'), \
                    patch.object(worker, 'WindowsAPI', Drifted):
                with self.assertRaisesRegex(worker.WorkerRefused, 'child_budget_unavailable'):
                    worker.verify_child_budget()
        class Low:
            def consume_job_proof(inner): return valid
            def free_ram(inner): return worker.FREE_RAM_FLOOR - 1
        with patch.object(worker.sys, 'platform', 'win32'), patch.object(worker, 'WindowsAPI', Low):
            with self.assertRaisesRegex(worker.WorkerRefused, 'free_ram_below_minimum'):
                worker.verify_child_budget()

    def test_child_refuses_existing_result_before_provider_or_claim(self):
        digest = hashlib.sha256(self.config_path.read_bytes()).hexdigest()
        with patch.object(worker, 'verify_child_budget'), patch.object(worker, '_provider',
                side_effect=AssertionError('No provider')):
            with self.assertRaisesRegex(worker.WorkerRefused, 'new_private_report_required'):
                worker.task_child(self.config_path, digest, self.task, self.config_path)
        self.assertEqual(self.state(), ('pending', 0, None))

    @unittest.skipIf(sys.platform == 'win32', 'POSIX mode regression; native DACL checks are separate')
    def test_world_readable_config_is_refused_before_database(self):
        self.config_path.chmod(0o644)
        with patch.object(worker, 'preflight', side_effect=AssertionError('No database')):
            with self.assertRaises(ValueError):
                worker.run(self.config_path)
        self.assertEqual(self.state(), ('pending', 0, None))

    def test_generation_policy_failure_is_reported_as_failure_not_ready(self):
        def bad(request):
            if request.url.path=='/health':return httpx.Response(200,json={'status':'healthy','active_provider':'qwen3-vl','model_cache_ready':True})
            return httpx.Response(200,json={'caption':'EN: A person is possibly outside.\n\nZH-CN: 一个人在外面。','provider':'qwen3-vl','model':MODEL})
        def provider(config):
            p=LocalCaptionHTTP(url=config['caption_url'],transport=httpx.MockTransport(bad));p.preflight();return p
        with patch.object(self,'provider',side_effect=provider):result=self.execute()
        self.assertFalse(result['all_selected_finished'])
        self.assertEqual(self.state(),('failed',1,'caption_policy_rejected'))
        self.assertEqual(len(self.f.rows('SELECT 1 FROM captions WHERE asset_id=?',(self.asset,))),0)

    def test_chinese_policy_correction_uses_shared_translation_contract(self):
        paths=[]
        def handle(request):
            paths.append(request.url.path)
            if request.url.path=='/health':return httpx.Response(200,json={'status':'healthy','active_provider':'qwen3-vl','model_cache_ready':True})
            if request.url.path=='/caption':return httpx.Response(200,json={'caption':'EN: A red cup rests on a wooden table.\n\nZH-CN: 一个红色杯子可能放在木桌上。','provider':'qwen3-vl','model':MODEL})
            payload=json.loads(request.read());self.assertGreater(len(payload['avoid_terms']),16)
            return httpx.Response(200,json={'translation':'一个红色杯子放在木桌上。','provider':'qwen3-vl','model':MODEL})
        def provider(config):
            p=LocalCaptionHTTP(url=config['caption_url'],transport=httpx.MockTransport(handle));p.preflight();return p
        with patch.object(self,'provider',side_effect=provider):result=self.execute()
        self.assertTrue(result['all_selected_finished']);self.assertEqual(paths.count('/caption'),1)
        self.assertEqual(paths.count('/translate'),1)
        self.assertEqual(self.f.rows('SELECT text FROM captions WHERE asset_id=?',(self.asset,))[0][0],GOOD)

    def test_model_swap_during_response_is_permanent_and_does_not_publish(self):
        def handle(request):
            if request.url.path=='/health':return httpx.Response(200,json={'status':'healthy','active_provider':'qwen3-vl','model_cache_ready':True})
            return httpx.Response(200,json={'caption':GOOD,'provider':'qwen3-vl','model':'unreviewed-other-model'})
        def provider(config):
            p=LocalCaptionHTTP(url=config['caption_url'],transport=httpx.MockTransport(handle));p.preflight();return p
        with patch.object(self,'provider',side_effect=provider):result=self.execute()
        self.assertFalse(result['all_selected_finished'])
        self.assertEqual(self.state(),('failed',1,'invalid_caption_result'))
        self.assertEqual(len(self.f.rows('SELECT 1 FROM captions WHERE asset_id=?',(self.asset,))),0)

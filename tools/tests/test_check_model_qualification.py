"""The qualification CLI reviews private records, with explicit file reads only."""
import builtins
from contextlib import redirect_stdout
from datetime import datetime
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def _module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class QualificationDoctorTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.private=Path(temp.name).resolve();self.private.chmod(0o700)
        helper=_module('qualification_fixture',ROOT/'server/tests/security/test_model_qualification.py')
        self.catalog,self.manifest,self.deployment,self.plan,self.inputs,self.doc=helper.synthetic_fixture(self.private)
        self.now=helper.NOW
        self.paths={}
        for name,value in [('manifest',self.manifest),('evidence',self.doc),('inputs',self.inputs)]:
            path=self.private/(name+'.json');path.write_text(json.dumps(value));path.chmod(0o600);self.paths[name]=path
        self.doctor=_module('qualification_doctor',ROOT/'tools/check_model_qualification.py')

    def call(self, *arguments):
        out=io.StringIO()
        class Clock:
            @staticmethod
            def now(_tz):return self.now
        with redirect_stdout(out),patch.object(self.doctor,'datetime',Clock):
            code=self.doctor.main(list(arguments))
        return code,json.loads(out.getvalue())

    def argv(self):
        return ['--manifest',str(self.paths['manifest']),'--evidence',str(self.paths['evidence']),
                '--audio-inputs',str(self.paths['inputs'])]

    def test_plan_binds_selected_roles_and_hashes_without_observations(self):
        code,report=self.call('--manifest',str(self.paths['manifest']))
        self.assertEqual(code,0);self.assertEqual(report['status'],'qualification_plan')
        self.assertEqual(set(report['selection_identities']),{'assistant_asr','assistant_tts','memory_asr','narrative'})
        self.assertFalse(report['observations_collected']);self.assertFalse(report['activation_performed'])
        with patch.object(self.doctor,'verify_identity_files') as verifier:
            code,report=self.call('--manifest',str(self.paths['manifest']),'--audio-inputs',str(self.paths['inputs']))
            verifier.assert_not_called()
        self.assertEqual(code,0);self.assertEqual(report['audio_plan_sha256'],self.doc['audio_plan_sha256'])

    def test_wsl_evidence_keeps_linux_execution_and_private_placement(self):
        self.manifest['schema'] = 2
        for runtime in self.manifest['runtimes']:
            runtime['placement'] = {'kind': 'native', 'host_platform': runtime['platform'], 'instance': None}
        provider = next(p for p in self.manifest['providers'] if p['role'] == 'assistant_asr')
        runtime = next(r for r in self.manifest['runtimes'] if r['id'] == provider['runtime'])
        runtime.update(platform='linux', execution_mode='loopback_http')
        runtime['placement'] = {'kind': 'wsl2', 'host_platform': 'windows', 'instance': 'Private-Synthetic-Distro'}
        from app.access.model_deployment import validate_deployment
        from app.access.model_qualification import selection_identity
        selected = validate_deployment(self.manifest, self.catalog)
        self.doc.update(platform='linux', scope_roles=['assistant_asr'], selection_sha256=selected.selection_sha256)
        record = next(r for r in self.doc['records'] if r['role'] == 'assistant_asr')
        self.doc['records'] = [record]
        record['selection_identity_sha256'] = selection_identity(selected, 'assistant_asr')
        record['observed_identity']['placement'] = runtime['placement']
        self.paths['manifest'].write_text(json.dumps(self.manifest))
        self.paths['evidence'].write_text(json.dumps(self.doc))
        code, report = self.call(*self.argv())
        self.assertEqual(code, 0)
        self.assertEqual(report['execution_platform'], 'linux')
        self.assertEqual(report['host_platforms'], {'assistant_asr': 'windows'})
        self.assertNotIn('Private-Synthetic-Distro', json.dumps(report))
        with patch.object(sys, 'platform', 'win32'):
            code, report = self.call(*self.argv(), '--verify-files')
        self.assertEqual(code, 1)
        self.assertEqual(report['reason'], 'identity_file_platform_mismatch')

    def test_record_review_never_reads_artifacts_until_requested(self):
        with patch.object(self.doctor,'verify_identity_files') as verifier:
            code,report=self.call(*self.argv());verifier.assert_not_called()
        self.assertEqual(code,0);self.assertFalse(report['files_verified'])
        code,report=self.call(*self.argv(),'--verify-files')
        self.assertEqual(code,0);self.assertTrue(report['files_verified'])
        self.assertFalse(report['runtime_environment_verified']);self.assertFalse(report['quality_independently_verified'])
        self.assertEqual(set(p.name for p in self.private.iterdir()),
                         {'artifact.synthetic','dependency_lock.synthetic','preprocessing.synthetic','synthetic-case.wav',
                          'manifest.json','evidence.json','inputs.json'})

    def test_incomplete_or_failed_or_stale_evidence_returns_nonzero(self):
        self.doc['records'][0]['resources']=None
        self.paths['evidence'].write_text(json.dumps(self.doc))
        code,report=self.call(*self.argv());self.assertEqual(code,2)
        self.assertEqual(report['status'],'scoped_evidence_incomplete')
        self.assertIn('resource_observations_missing',report['records']['assistant_asr']['gaps'])

    def test_private_values_and_argument_errors_are_redacted(self):
        code,report=self.call(*self.argv(),'--verify-files')
        for private in (str(self.private),'private-reviewer','synthetic-asr','19001','example.invalid'):
            self.assertNotIn(private,json.dumps(report))
        for arguments,reason in [(['--secret=private-secret'],'invalid_arguments'),
                                  (['--manifest',str(self.paths['manifest']),'--verify-files'],'evidence_required'),
                                  (['--manifest',str(self.paths['manifest']),'--hash-timeout-seconds','5'],'file_verification_required'),
                                  (['--manifest',str(self.paths['manifest']),'--evidence',str(self.private/'private-missing')],'private_evidence_unavailable')]:
            code,report=self.call(*arguments)
            self.assertEqual(code,1);self.assertEqual(report,{'status':'refused','reason':reason})

    def test_plan_case_hash_change_refuses_old_evidence(self):
        plan=json.loads(json.dumps(self.plan));plan['suites'][0]['cases'][0]['input_text']+='Changed synthetic phrase'
        original=self.doctor.model_catalog._load
        def load(root,path):return plan if path=='models/quality-cases.json' else original(root,path)
        with patch.object(self.doctor.model_catalog,'_load',side_effect=load):
            code,report=self.call(*self.argv())
        self.assertEqual(code,1);self.assertEqual(report['reason'],'evidence_case_plan_mismatch')

    def test_invalid_timeouts_platform_and_duplicate_private_json_are_refused(self):
        for value in ('nan','inf','-1','601'):
            code,report=self.call(*self.argv(),'--verify-files','--hash-timeout-seconds',value)
            self.assertEqual(code,1);self.assertEqual(report['reason'],'evidence_measurement')
        with patch.object(sys,'platform','unsupported'):
            code,report=self.call(*self.argv(),'--verify-files')
        self.assertEqual(code,1);self.assertEqual(report['reason'],'identity_file_platform_mismatch')
        self.paths['evidence'].write_text('{"schema":1,"schema":1}')
        code,report=self.call(*self.argv());self.assertEqual(code,1);self.assertEqual(report['reason'],'private_evidence_unavailable')
        self.paths['evidence'].write_text(json.dumps(self.doc))
        code,report=self.call(*self.argv(),'--selection','rollback')
        self.assertEqual(code,1);self.assertEqual(report['reason'],'evidence_selection_mismatch')
        code,report=self.call(*self.argv(),'--selection','current')
        self.assertEqual(code,0);self.assertEqual(report['selection'],'current')

    def test_source_verification_precedes_private_loading(self):
        with patch.object(self.doctor.model_catalog,'verify',side_effect=self.doctor.model_catalog.CatalogError('adapter_symbol_missing')):
            with patch.object(self.doctor,'load_private_deployment') as reader:
                code,report=self.call(*self.argv());reader.assert_not_called()
        self.assertEqual(code,1);self.assertEqual(report['reason'],'adapter_symbol_missing')

    def test_import_and_review_do_not_load_ml_network_or_provider_processes(self):
        original=builtins.__import__
        blocked={'torch','transformers','onnxruntime','requests','httpx','socket','subprocess'}
        def guarded(name,*args,**kwargs):
            if name.split('.')[0] in blocked or name in {'app.main','app.config'}:
                raise AssertionError('Forbidden inference/runtime import')
            return original(name,*args,**kwargs)
        with patch.object(builtins,'__import__',side_effect=guarded):
            self.doctor=_module('isolated_qualification_doctor',ROOT/'tools/check_model_qualification.py')
            code,report=self.call(*self.argv())
        self.assertEqual(code,0);self.assertFalse(report['provider_probed'])


if __name__=='__main__':
    unittest.main()

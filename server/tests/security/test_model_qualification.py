"""Synthetic evidence is never installation, GPU, semantic or family acceptance."""
import copy
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'server/backend'))
from app.access import model_deployment as deployment
from app.access import model_qualification as qualification

NOW = datetime(2026, 10, 9, 1, 3, tzinfo=timezone.utc)


def synthetic_fixture(directory):
    directory = Path(directory).resolve()
    catalog = json.loads((ROOT / 'models/catalog.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'models/deployment.synthetic.json').read_text(encoding='utf-8'))
    plan = json.loads((ROOT / 'models/quality-cases.json').read_text(encoding='utf-8'))
    data = {'artifact': b'synthetic checkpoint, not a model', 'dependency_lock': b'synthetic exact lock',
            'preprocessing': b'synthetic preprocessing'}
    files = {}
    digests = {}
    for kind, payload in data.items():
        path = directory / (kind + '.synthetic')
        path.write_bytes(payload)
        files[kind] = str(path)
        digests[kind] = hashlib.sha256(payload).hexdigest()
    platform = {'darwin': 'macos', 'linux': 'linux', 'win32': 'windows'}[sys.platform]
    for runtime in manifest['runtimes']:
        runtime.update(platform=platform, dependency_lock_sha256=digests['dependency_lock'])
    for artifact in manifest['artifacts']:
        artifact.update(identity_sha256=digests['artifact'], preprocessing_sha256=digests['preprocessing'])
    tts = copy.deepcopy(manifest['providers'][0])
    tts.update(id='synthetic-tts', role='assistant_tts', adapter='LocalAssistantTts',
               contract='assistant-reply-wav-v1', endpoint='http://127.0.0.1:19005/speech')
    manifest['providers'].append(tts)
    manifest['bindings'].append({'role': 'assistant_tts', 'provider': tts['id'], 'enabled': False})
    validated = deployment.validate_deployment(manifest, catalog)
    suites = qualification.validate_case_plan(plan)
    plan_digest = hashlib.sha256(qualification._canonical(plan)).hexdigest()
    audio = directory / 'synthetic-case.wav'
    # No intelligibility claim: the bytes merely exercise identity comparison.
    audio.write_bytes(b'RIFF synthetic test bytes, not playable speech')
    audio_digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    inputs = {'schema': 1, 'kind': 'photohouse-model-audio-inputs', 'case_plan_sha256': plan_digest,
              'inputs': [{'role': role, 'case_id': case['id'], 'file': str(audio), 'input_sha256': audio_digest}
                         for role in ('assistant_asr', 'memory_asr') for case in suites[role].values()]}
    records = []
    for role in sorted(qualification.ROLES):
        resolved = validated.resolve(role)
        runtime, artifact = resolved['runtime'], resolved['artifact']
        identity = {'runtime_version': runtime['runtime_version'], 'implementation': runtime['implementation'],
                    'dependency_lock_sha256': runtime['dependency_lock_sha256'], 'device': runtime['device'],
                    'artifact_sha256': artifact['identity_sha256'], 'preprocessing_sha256': artifact['preprocessing_sha256']}
        results = [{'case_id': case['id'], 'input_sha256': case['input_sha256'] or audio_digest,
                    'output_sha256': 'a' * 64, 'criteria': {c: 'passed' for c in case['criteria']},
                    'reviewed_by': 'private-reviewer', 'reviewed_at': '2026-10-09T01:02:00Z'}
                   for case in suites[role].values()]
        records.append({'role': role, 'selection_identity_sha256': qualification.selection_identity(validated, role),
                        'observed_identity': identity, 'runtime_capture_sha256': 'b' * 64, 'files': files.copy(),
                        'resources': {'method': 'owned_process_tree', 'capture_sha256': 'c' * 64,
                                      'sample_count': 3, 'window_seconds': 50, 'peak_ram_mib': 256,
                                      'minimum_free_ram_mib': 8192, 'minimum_free_vram_mib': 0,
                                      'peak_concurrency': 1, 'maximum_request_seconds': 10}, 'quality': results})
    document = {'schema': 1, 'kind': 'photohouse-model-qualification', 'selection_sha256': validated.selection_sha256,
                'selection': 'current', 'case_plan_sha256': plan_digest, 'scope_roles': sorted(qualification.ROLES),
                'audio_plan_sha256': hashlib.sha256(qualification._canonical(inputs)).hexdigest(),
                'platform': platform, 'started_at': '2026-10-09T01:00:00Z', 'ended_at': '2026-10-09T01:01:00Z',
                'records': records}
    return catalog, manifest, validated, plan, inputs, document


class ModelQualificationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.private = Path(temp.name).resolve()
        self.private.chmod(0o700)
        self.catalog, self.manifest, self.deployment, self.plan, self.inputs, self.doc = synthetic_fixture(self.private)

    def validate(self, *, now=NOW):
        return qualification.validate_qualification(self.doc, self.deployment, self.plan, now=now, audio_plan=self.inputs)

    def refused(self, reason, callback=None):
        with self.assertRaises(qualification.QualificationError) as caught:
            (callback or self.validate)()
        self.assertEqual(str(caught.exception), reason)

    def test_consistent_record_is_private_immutable_and_not_activation_or_quality_proof(self):
        value = self.validate()
        report = value.report()
        self.assertEqual(report['status'], 'scoped_evidence_consistent')
        self.assertIn('annotation_polish', report['other_declared_roles'])
        for flag in ('files_verified', 'provider_probed', 'device_verified', 'runtime_environment_verified',
                     'quality_independently_verified', 'resources_enforced', 'activation_performed',
                     'shared_memory_item_budget_verified', 'complete_deployment_qualification'):
            self.assertIs(report[flag], False)
        encoded = json.dumps(report) + repr(value)
        for private in ('private-reviewer', str(self.private), 'synthetic-asr', '19001', 'example.invalid', 'b' * 64):
            self.assertNotIn(private, encoded)
        self.doc['records'][0]['quality'].clear()
        report['records'].clear()
        self.assertEqual(value.report()['status'], 'scoped_evidence_consistent')
        with self.assertRaises(TypeError):
            qualification.QualificationEvidence()

    def test_declared_and_observed_device_and_lock_are_independent(self):
        observed = self.doc['records'][0]['observed_identity']
        for key, value in (('dependency_lock_sha256', None), ('runtime_version', 'unknown'),
                           ('device', {'kind': 'cpu', 'index': False, 'hardware_id': None}),
                           ('artifact_sha256', '0' * 64)):
            with self.subTest(key=key):
                old = observed[key]
                observed[key] = value
                report = self.validate().report()
                self.assertEqual(report['status'], 'scoped_evidence_incomplete')
                self.assertIn('observed_identity_mismatch', report['records'][self.doc['records'][0]['role']]['gaps'])
                observed[key] = old

    def test_scope_coverage_cannot_omit_missing_roles(self):
        omitted = self.doc['records'].pop()['role']
        self.assertEqual(self.validate().report()['records'][omitted]['gaps'], ['role_record_missing'])
        self.doc['scope_roles'].remove(omitted)
        report = self.validate().report()
        self.assertEqual(report['status'], 'scoped_evidence_consistent')
        self.assertIn(omitted, report['other_declared_roles'])
        self.doc['records'].clear()
        self.assertEqual(self.validate().report()['status'], 'scoped_evidence_incomplete')

    def test_manifest_provider_branch_and_case_plan_revisions_are_bound(self):
        pristine = copy.deepcopy(self.doc)
        for key, value, reason in [('selection_sha256', '0' * 64, 'evidence_manifest_mismatch'),
                                    ('case_plan_sha256', '0' * 64, 'evidence_case_plan_mismatch'),
                                    ('audio_plan_sha256', '0' * 64, 'evidence_audio_plan_mismatch'),
                                    ('selection', 'rollback', 'evidence_binding_missing')]:
            with self.subTest(key=key):
                self.doc = copy.deepcopy(pristine);self.doc[key] = value;self.refused(reason)
        self.doc = pristine
        self.doc['records'][0]['selection_identity_sha256'] = '0' * 64
        self.refused('evidence_provider_mismatch')

    def test_disabled_candidate_and_explicit_rollback_can_be_reviewed_without_enabling(self):
        previous = copy.deepcopy(self.manifest['providers'][0])
        previous.update(id='previous-asr', endpoint='http://127.0.0.1:19007/transcribe')
        self.manifest['providers'].append(previous)
        self.manifest['rollback_bindings'] = [{'role': 'assistant_asr', 'provider': previous['id'], 'enabled': True}]
        self.deployment = deployment.validate_deployment(self.manifest, self.catalog)
        record = next(r for r in self.doc['records'] if r['role'] == 'assistant_asr')
        self.doc.update(selection='rollback', selection_sha256=self.deployment.selection_sha256,
                        scope_roles=['assistant_asr'], records=[record])
        record['selection_identity_sha256'] = qualification.selection_identity(self.deployment, 'assistant_asr', selection='rollback')
        self.assertEqual(self.validate().report()['status'], 'scoped_evidence_consistent')
        self.assertNotEqual(record['selection_identity_sha256'], qualification.selection_identity(self.deployment, 'assistant_asr'))
        self.assertFalse(self.manifest['bindings'][0]['enabled'])

    def test_stale_future_invalid_window_and_explicit_clock(self):
        self.assertIn('evidence_stale', self.validate(now=NOW + timedelta(days=31)).report()['records']['assistant_asr']['gaps'])
        self.refused('evidence_clock_required', lambda: self.validate(now=NOW.replace(tzinfo=None)))
        self.refused('evidence_window', lambda: self.validate(now=NOW - timedelta(days=1)))
        self.doc['ended_at'] = self.doc['started_at'];self.refused('evidence_window')
        self.doc['ended_at'] = '2026-10-09T08:00:00Z';self.refused('evidence_window')
        self.doc['started_at'] = '2026-10-09 01:00:00';self.refused('evidence_timestamp')

    def test_measured_limits_are_not_enforced_and_device_observation_must_match(self):
        observation = self.doc['records'][0]['resources']
        pristine = copy.deepcopy(observation)
        cases = [('peak_ram_mib', 2049, 'ram_budget_exceeded'), ('minimum_free_ram_mib', 8191, 'ram_headroom_below_floor'),
                 ('peak_concurrency', 2, 'concurrency_budget_exceeded'), ('maximum_request_seconds', 46, 'request_budget_exceeded')]
        for field, value, reason in cases:
            with self.subTest(field=field):
                observation.update(pristine);observation[field] = value
                report = self.validate().report()['records'][self.doc['records'][0]['role']]
                self.assertIn(reason, report['gaps']);self.assertFalse(report['recorded_resources_within_budget'])
        observation.update(pristine);observation['minimum_free_vram_mib'] = 1
        self.refused('resource_observed_device')

    def test_invalid_numbers_and_capture_method_are_refused(self):
        observation = self.doc['records'][0]['resources']
        for field, value, reason in [('peak_ram_mib', True, 'evidence_measurement'),
                                    ('peak_ram_mib', 10 ** 512, 'evidence_measurement'),
                                    ('peak_ram_mib', float('nan'), 'evidence_measurement'),
                                    ('sample_count', 1, 'resource_sample_count'),
                                    ('peak_concurrency', True, 'resource_observed_concurrency'),
                                    ('window_seconds', 61, 'evidence_measurement'),
                                    ('method', 'unknown', 'resource_measurement_method')]:
            with self.subTest(field=field,value=value):
                old=observation[field];observation[field]=value;self.refused(reason);observation[field]=old

    def test_quality_requires_pinned_inputs_and_complete_human_review(self):
        record = next(r for r in self.doc['records'] if r['role'] == 'assistant_asr')
        record['quality'][0]['input_sha256'] = '0' * 64
        self.assertIn('quality_input_mismatch', self.validate().report()['records']['assistant_asr']['gaps'])
        self.inputs = None;self.doc['audio_plan_sha256'] = None
        self.assertIn('quality_audio_input_unpinned', self.validate().report()['records']['assistant_asr']['gaps'])
        record['quality'][0]['reviewed_by'] = None;record['quality'][0]['reviewed_at'] = None
        self.refused('quality_reviewer_required')
        record['quality'][0]['criteria'] = {c: 'unreviewed' for c in record['quality'][0]['criteria']}
        self.assertFalse(self.validate().report()['records']['assistant_asr']['recorded_quality_review_passed'])

    def test_failed_missing_duplicate_and_unexpected_quality_results(self):
        record=self.doc['records'][0]
        criterion=next(iter(record['quality'][0]['criteria']))
        record['quality'][0]['criteria'][criterion]='failed'
        self.assertIn('quality_review_failed',self.validate().report()['records'][record['role']]['gaps'])
        record['quality'].pop()
        self.assertIn('quality_cases_missing',self.validate().report()['records'][record['role']]['gaps'])
        record['quality'].append(copy.deepcopy(record['quality'][0]));self.refused('quality_case_identity')
        record['quality'].pop();record['quality'][0]['criteria']['extra_private']='passed';self.refused('quality_criteria_fields')

    def test_review_timestamp_cannot_precede_run_or_be_in_future(self):
        result=self.doc['records'][0]['quality'][0]
        for value in ('2026-10-08T01:00:00Z','2026-10-09T01:04:00Z'):
            result['reviewed_at']=value;self.refused('quality_review_time')

    def test_unknown_fields_and_malformed_scope_or_version_are_refused(self):
        pristine=copy.deepcopy(self.doc)
        for key,value,reason in [('schema',True,'evidence_version'),('scope_roles',['assistant_asr','assistant_asr'],'evidence_scope'),
                                ('platform',[], 'evidence_platform'),('token','private-token','evidence_fields')]:
            self.doc=copy.deepcopy(pristine);self.doc[key]=value;self.refused(reason)

    def test_snapshot_integrity_and_explicit_file_inspection(self):
        evidence=self.validate()
        report=qualification.verify_identity_files(evidence,self.deployment,source_root=ROOT)
        self.assertTrue(report['files_verified']);self.assertEqual(report['unique_files_hashed'],4)
        self.assertFalse(evidence.report()['files_verified'])
        object.__setattr__(evidence,'_payload',b'{}')
        self.refused('validated_evidence_required', evidence.report)
        self.refused('validated_evidence_required',lambda:qualification.verify_identity_files(evidence,self.deployment,source_root=ROOT))

    def test_file_mismatch_missing_empty_and_source_paths_are_refused_privately(self):
        path=Path(self.doc['records'][0]['files']['artifact'])
        path.write_bytes(b'wrong bytes')
        self.refused('identity_file_hash_mismatch',lambda:qualification.verify_identity_files(self.validate(),self.deployment,source_root=ROOT))
        path.write_bytes(b'');self.refused('identity_file_size_or_kind',lambda:qualification.verify_identity_files(self.validate(),self.deployment,source_root=ROOT))
        path.unlink();self.refused('identity_file_unavailable',lambda:qualification.verify_identity_files(self.validate(),self.deployment,source_root=ROOT))
        self.doc['records'][0]['files']['artifact']=str(ROOT/'models/catalog.json')
        self.refused('identity_file_location',lambda:qualification.verify_identity_files(self.validate(),self.deployment,source_root=ROOT))

    def test_leaf_and_parent_symlinks_and_reparse_points_are_refused(self):
        actual=Path(self.doc['records'][0]['files']['artifact'])
        link=self.private/'leaf-link';link.symlink_to(actual)
        self.doc['records'][0]['files']['artifact']=str(link)
        self.refused('identity_file_link',lambda:qualification.verify_identity_files(self.validate(),self.deployment,source_root=ROOT))
        link.unlink();link.symlink_to(self.private,target_is_directory=True)
        self.doc['records'][0]['files']['artifact']=str(link/actual.name)
        self.refused('identity_file_link',lambda:qualification.verify_identity_files(self.validate(),self.deployment,source_root=ROOT))

    def test_changes_after_hash_shared_cache_deadline_and_size_limits_are_refused(self):
        original=qualification._hash_file
        count=0
        def changing(path,**kwargs):
            nonlocal count
            value=original(path,**kwargs);count+=1
            if count==4:
                Path(self.doc['records'][0]['files']['artifact']).write_bytes(b'changed after cached hash')
            return value
        with patch.object(qualification,'_hash_file',side_effect=changing):
            self.refused('identity_file_changed',lambda:qualification.verify_identity_files(self.validate(),self.deployment,source_root=ROOT))
        with patch.object(qualification.time,'monotonic',side_effect=[0,2]):
            self.refused('identity_hash_deadline',lambda:qualification.verify_identity_files(self.validate(),self.deployment,source_root=ROOT,timeout_seconds=1))
        with patch.object(qualification,'MAX_FILE_BYTES',1):
            self.refused('identity_file_size_or_kind',lambda:qualification.verify_identity_files(self.validate(),self.deployment,source_root=ROOT))

    def test_private_evidence_and_audio_plan_readers_keep_strict_metadata_boundary(self):
        path=self.private/'evidence.json';inputs=self.private/'inputs.json'
        for target,value in [(path,self.doc),(inputs,self.inputs)]:
            target.write_text(json.dumps(value), encoding='utf-8');target.chmod(0o600)
        report=qualification.load_private_qualification(path,self.deployment,self.plan,source_root=ROOT,now=NOW,audio_plan_path=inputs).report()
        self.assertEqual(report['status'],'scoped_evidence_consistent')
        path.write_text('{"schema":1,"schema":1}', encoding='utf-8')
        self.refused('private_evidence_unavailable',lambda:qualification.load_private_qualification(path,self.deployment,self.plan,source_root=ROOT,now=NOW))

    def test_narrative_inputs_match_existing_generated_bundle_hashes(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('synthetic_memoir_plan',ROOT/'server/scripts/plan_memoir_quality_cases.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        hashes={c['case_id']:c['bundle_sha256'] for c in module.build_plan()['cases']}
        suite=qualification.validate_case_plan(self.plan)['narrative']
        self.assertEqual(hashes,{key:case['input_sha256'] for key,case in suite.items()})


if __name__=='__main__':
    unittest.main()

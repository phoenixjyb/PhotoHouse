"""Schema-2 placement and WSL loopback projection contract tests."""
import copy
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'server/backend'), str(ROOT / 'server/scripts')]
from app.access import model_deployment as deployment
from app.access import model_qualification as qualification
from app.access.model_binding import ModelBindingError, project_configuration
from app.access.runtime import RuntimeConfiguration
import staging_app
import run_memory_worker as worker


def _qualification_fixture(directory):
    """Reuse the established synthetic evidence builder from the qualification suite."""
    path = ROOT / 'server/tests/security/test_model_qualification.py'
    spec = importlib.util.spec_from_file_location('model_qualification_fixture', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.synthetic_fixture(directory)


class ModelTopologyTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / 'models/catalog.json').read_text())
        self.doc = json.loads((ROOT / 'models/deployment.synthetic.json').read_text())

    def native_schema2(self, *, platform='windows'):
        self.doc['schema'] = 2
        for runtime in self.doc['runtimes']:
            runtime['platform'] = platform
            runtime['placement'] = {'kind': 'native', 'host_platform': platform, 'instance': None}
        return self.doc

    def add_wsl_asr(self, *, enabled=False, rollback=False):
        self.native_schema2()
        runtime = next(r for r in self.doc['runtimes'] if r['id'] == 'asr-service')
        runtime.update(platform='linux', execution_mode='loopback_http', environment_id='ubuntu-asr')
        runtime['placement'] = {'kind': 'wsl2', 'host_platform': 'windows', 'instance': 'Ubuntu-22.04'}
        binding = next(b for b in self.doc['bindings'] if b['role'] == 'assistant_asr')
        binding['enabled'] = enabled
        if rollback:
            current = next(p for p in self.doc['providers'] if p['id'] == binding['provider'])
            old_runtime = copy.deepcopy(runtime)
            old_runtime.update(id='asr-previous-runtime', environment_id='ubuntu-asr-previous')
            old_runtime['placement'] = dict(old_runtime['placement'], instance='Ubuntu-20.04')
            self.doc['runtimes'].append(old_runtime)
            old_provider = copy.deepcopy(current)
            old_provider.update(id='asr-previous', runtime=old_runtime['id'],
                                endpoint='http://127.0.0.1:19003/transcribe')
            self.doc['providers'].append(old_provider)
            self.doc['rollback_bindings'] = [{'role': 'assistant_asr', 'provider': old_provider['id'],
                                              'enabled': True}]
        return deployment.validate_deployment(self.doc, self.catalog)

    def add_native_tts(self):
        spec = next(s for s in self.catalog['capabilities'] if s['id'] == 'assistant_tts')
        artifact = copy.deepcopy(self.doc['artifacts'][0])
        artifact.update(id='synthetic-system-voice', kind='system_voice', model_name='synthetic-system-voice')
        self.doc['artifacts'].append(artifact)
        runtime = copy.deepcopy(self.doc['runtimes'][0])
        runtime.update(id='windows-tts-runtime', environment_id='windows-tts')
        runtime['platform'] = 'windows'
        runtime['execution_mode'] = 'loopback_http'
        runtime['placement'] = {'kind': 'native', 'host_platform': 'windows', 'instance': None}
        self.doc['runtimes'].append(runtime)
        provider = {'id': 'synthetic-tts', 'role': 'assistant_tts', 'adapter': 'LocalAssistantTts',
            'contract': spec['contract'], 'runtime': runtime['id'], 'artifact': artifact['id'],
            'endpoint': 'http://127.0.0.1:19005/speech', 'credential_env': None}
        self.doc['providers'].append(provider)
        self.doc['bindings'].append({'role': 'assistant_tts', 'provider': provider['id'], 'enabled': True})
        previous = copy.deepcopy(provider)
        previous.update(id='synthetic-tts-previous', endpoint='http://127.0.0.1:19006/speech')
        self.doc['providers'].append(previous)
        self.doc.setdefault('rollback_bindings', []).append({'role': 'assistant_tts',
            'provider': previous['id'], 'enabled': True})

    def test_schema1_remains_native_and_schema2_requires_strict_placement_shape(self):
        legacy = deployment.validate_deployment(self.doc, self.catalog)
        self.assertEqual(legacy.resolve('assistant_asr')['runtime']['platform'], 'windows')
        self.assertEqual(legacy.report()['status'], 'configuration_valid')
        legacy_projection = project_configuration(legacy, target='assistant', platform='windows',
                                                  feature_enabled=True)
        self.assertEqual(legacy_projection.report()['host_platform'], 'windows')
        self.assertEqual(legacy_projection.report()['execution_platforms'], {})

        self.doc['runtimes'][0]['placement'] = {'kind': 'native', 'host_platform': 'windows', 'instance': None}
        with self.assertRaisesRegex(deployment.DeploymentError, 'runtime_fields'):
            deployment.validate_deployment(self.doc, self.catalog)
        del self.doc['runtimes'][0]['placement']

        self.native_schema2()
        deployment.validate_deployment(self.doc, self.catalog)
        runtime = self.doc['runtimes'][0]
        pristine = copy.deepcopy(runtime)
        cases = [
            ({k: v for k, v in pristine.items() if k != 'placement'}, 'runtime_fields'),
            (pristine | {'extra': True}, 'runtime_fields'),
            (pristine | {'placement': {'kind': 'native', 'host_platform': 'windows'}}, 'placement_fields'),
            (pristine | {'placement': pristine['placement'] | {'instance': []}}, 'native_placement_identity'),
            (pristine | {'placement': pristine['placement'] | {'host_platform': 'linux'}}, 'native_placement_identity'),
        ]
        for value, reason in cases:
            with self.subTest(reason=reason):
                self.doc['runtimes'][0] = value
                with self.assertRaisesRegex(deployment.DeploymentError, reason):
                    deployment.validate_deployment(self.doc, self.catalog)
                self.doc['runtimes'][0] = copy.deepcopy(pristine)

    def test_wsl2_placement_types_host_execution_mode_and_role_boundaries(self):
        self.add_wsl_asr()
        runtime = next(r for r in self.doc['runtimes'] if r['id'] == 'asr-service')
        pristine = copy.deepcopy(runtime)
        mutations = [
            (lambda r: r['placement'].update(instance=''), 'wsl_instance_identity'),
            (lambda r: r['placement'].update(instance='x' * 121), 'wsl_instance_identity'),
            (lambda r: r['placement'].update(host_platform='linux'), 'wsl_placement_contract'),
            (lambda r: r.update(platform='windows'), 'wsl_placement_contract'),
            (lambda r: r.update(execution_mode='http_service'), 'wsl_placement_contract'),
        ]
        for mutate, reason in mutations:
            with self.subTest(reason=reason):
                mutate(runtime)
                with self.assertRaisesRegex(deployment.DeploymentError, reason):
                    deployment.validate_deployment(self.doc, self.catalog)
                runtime.clear(); runtime.update(copy.deepcopy(pristine))

        spec = next(s for s in self.catalog['capabilities'] if s['id'] == 'vlm_caption')
        provider = self.doc['providers'][0]
        provider.update(role='vlm_caption', adapter='HTTPCaptionProvider', contract=spec['contract'])
        with self.assertRaisesRegex(deployment.DeploymentError, 'provider_execution_mode'):
            deployment.validate_deployment(self.doc, self.catalog)
        # Even a future catalog mode addition cannot silently widen WSL roles.
        spec['execution_modes'].append('loopback_http')
        with self.assertRaisesRegex(deployment.DeploymentError, 'wsl_role_not_supported'):
            deployment.validate_deployment(self.doc, self.catalog)

    def test_environment_identity_includes_wsl_distribution_instance(self):
        self.add_wsl_asr()
        other = copy.deepcopy(next(r for r in self.doc['runtimes'] if r['id'] == 'asr-service'))
        other.update(id='same-env-other-instance')
        other['placement']['instance'] = 'Ubuntu-24.04'
        self.doc['runtimes'].append(other)
        with self.assertRaisesRegex(deployment.DeploymentError, 'environment_identity_conflict'):
            deployment.validate_deployment(self.doc, self.catalog)

    def test_mixed_windows_host_projection_copies_flags_without_execution(self):
        self.add_wsl_asr(enabled=True, rollback=True)
        self.add_native_tts()
        selected_deployment = deployment.validate_deployment(self.doc, self.catalog)
        projection = project_configuration(selected_deployment, target='assistant', platform='windows',
                                           feature_enabled=True)
        self.assertEqual(projection.report()['host_platform'], 'windows')
        self.assertEqual(projection.report()['execution_platforms'],
                         {'assistant_asr': 'linux', 'assistant_tts': 'windows'})
        self.assertEqual(projection.report()['placement_kinds'],
                         {'assistant_asr': 'wsl2', 'assistant_tts': 'native'})
        self.assertNotIn('Ubuntu-22.04', json.dumps(projection.report()))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            staging_raw = {'format_version': 1, 'database': str(root / 'db.sqlite'),
                'web_origin': 'https://photohouse.test:8443', 'original_roots': [str(root / 'originals')],
                'derived_root': str(root / 'derived'), 'bind_host': '127.0.0.1', 'port': 8443,
                'tls_certificate': str(root / 'cert.pem'), 'tls_private_key': str(root / 'key.pem'),
                'assistant_enabled': True}
            staging = staging_app.parse_configuration(staging_raw)
            runtime = RuntimeConfiguration(root / 'db.sqlite', 'https://photohouse.test',
                (root / 'originals',), root / 'derived', assistant_enabled=True)
            with patch('httpx.Client', side_effect=AssertionError('provider call forbidden')), \
                 patch('sqlite3.connect', side_effect=AssertionError('storage call forbidden')), \
                 patch.object(staging.__class__, 'build_app', side_effect=AssertionError('app build forbidden')):
                selected_staging = staging.with_model_deployment(selected_deployment, platform='windows')
                selected_runtime = runtime.with_model_deployment(selected_deployment, platform='windows')
            for selected in (selected_staging, selected_runtime):
                self.assertEqual(selected.assistant_asr_url, 'http://127.0.0.1:19001/transcribe')
                self.assertEqual(selected.assistant_tts_url, 'http://127.0.0.1:19005/speech')
                self.assertTrue(selected.assistant_enabled)
                self.assertFalse(selected.memory_generation_enabled)
            self.assertIsNone(staging.assistant_asr_url)
            self.assertIsNone(runtime.assistant_asr_url)

        # The worker API uses the same host projection and returns a validated copy.
        self.doc = json.loads((ROOT / 'models/deployment.synthetic.json').read_text())
        self.native_schema2()
        self.add_wsl_memory_asr_and_native_polish()
        worker_deployment = deployment.validate_deployment(self.doc, self.catalog)
        config = {'database': '/private/synthetic.sqlite', 'mode': 'contributions',
            'asr_url': None, 'asr_model': None, 'asr_token': None, 'ollama_url': None,
            'ollama_model': None, 'original_deletion_journal_path': '/private/deletions.sqlite',
            'original_deletion_namespace': '00000000-0000-4000-8000-000000000001'}
        with patch('httpx.Client', side_effect=AssertionError('provider call forbidden')):
            selected_worker = worker.with_model_deployment(config, worker_deployment, platform='windows',
                                                           processing_enabled=True)
        self.assertEqual(selected_worker['asr_url'], 'http://127.0.0.1:19001/transcribe-memory')
        self.assertEqual(selected_worker['ollama_url'], 'http://127.0.0.1:19002/api/generate')
        self.assertIsNone(config['asr_url'])

    def add_wsl_memory_asr_and_native_polish(self):
        # Convert the synthetic current providers into a complete contribution target.
        for role in ('memory_asr', 'annotation_polish'):
            binding = next(b for b in self.doc['bindings'] if b['role'] == role)
            provider = next(p for p in self.doc['providers'] if p['id'] == binding['provider'])
            runtime = next(r for r in self.doc['runtimes'] if r['id'] == provider['runtime'])
            binding['enabled'] = True
            previous = copy.deepcopy(provider)
            previous.update(id=provider['id'] + '-previous',
                            endpoint=provider['endpoint'].replace(':19001', ':19003').replace(':19002', ':19004'))
            self.doc['providers'].append(previous)
            self.doc.setdefault('rollback_bindings', []).append({'role': role,
                'provider': previous['id'], 'enabled': True})
            if role == 'memory_asr':
                runtime.update(platform='linux', execution_mode='loopback_http', environment_id='ubuntu-memory-asr')
                runtime['placement'] = {'kind': 'wsl2', 'host_platform': 'windows', 'instance': 'Ubuntu-22.04'}

    def test_rollback_projection_refuses_provider_on_wrong_host(self):
        selected = self.add_wsl_asr(enabled=True, rollback=True)
        rollback_runtime = next(r for r in self.doc['runtimes'] if r['id'] == 'asr-previous-runtime')
        rollback_runtime.update(platform='linux')
        rollback_runtime['placement'] = {'kind': 'native', 'host_platform': 'linux', 'instance': None}
        selected_wrong_host = deployment.validate_deployment(self.doc, self.catalog)
        with self.assertRaisesRegex(ModelBindingError, 'runtime_platform_mismatch'):
            project_configuration(selected_wrong_host, target='assistant', platform='windows',
                                  feature_enabled=True, rollback=True)
        # A valid rollback on the Windows host remains projectable; selection is explicit.
        rollback_runtime.update(platform='linux')
        rollback_runtime['placement'] = {'kind': 'wsl2', 'host_platform': 'windows',
                                         'instance': 'Ubuntu-20.04'}
        selected = deployment.validate_deployment(self.doc, self.catalog)
        projection = project_configuration(selected, target='assistant', platform='windows',
                                            feature_enabled=True, rollback=True)
        self.assertEqual(projection.report()['selection'], 'rollback')

    def test_selection_and_projection_reports_redact_distribution_instance(self):
        selected = self.add_wsl_asr(enabled=True, rollback=True)
        report = selected.report()
        projection = project_configuration(selected, target='assistant', platform='windows',
            feature_enabled=True).report()
        encoded = json.dumps(report) + json.dumps(projection) + repr(selected)
        self.assertNotIn('Ubuntu-22.04', encoded)
        self.assertFalse(report['activation_performed'])
        self.assertFalse(projection['runtime_probed'])

    def test_qualification_records_execution_os_placement_and_requires_split_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp).resolve()
            directory.chmod(0o700)
            catalog, manifest, _old, plan, inputs, doc = _qualification_fixture(directory)
            manifest['schema'] = 2
            for runtime in manifest['runtimes']:
                runtime['placement'] = {'kind': 'native', 'host_platform': runtime['platform'], 'instance': None}
            asr_provider = next(p for p in manifest['providers'] if p['role'] == 'assistant_asr')
            asr_runtime = next(r for r in manifest['runtimes'] if r['id'] == asr_provider['runtime'])
            asr_runtime.update(platform='linux', execution_mode='loopback_http')
            asr_runtime['placement'] = {'kind': 'wsl2', 'host_platform': 'windows', 'instance': 'Ubuntu-22.04'}
            # Give TTS its own native Windows execution runtime for independent evidence.
            tts_provider = next(p for p in manifest['providers'] if p['role'] == 'assistant_tts')
            tts_runtime = copy.deepcopy(asr_runtime)
            tts_runtime.update(id='windows-tts', platform='windows', environment_id='windows-tts')
            tts_runtime['placement'] = {'kind': 'native', 'host_platform': 'windows', 'instance': None}
            manifest['runtimes'].append(tts_runtime)
            tts_provider['runtime'] = tts_runtime['id']
            selected = deployment.validate_deployment(manifest, catalog)

            # A Linux execution record binds the WSL placement and is valid for ASR alone.
            doc['selection_sha256'] = selected.selection_sha256
            doc['platform'] = 'linux'
            doc['scope_roles'] = ['assistant_asr']
            record = next(r for r in doc['records'] if r['role'] == 'assistant_asr')
            doc['records'] = [record]
            record['selection_identity_sha256'] = qualification.selection_identity(selected, 'assistant_asr')
            record['observed_identity']['placement'] = asr_runtime['placement']
            report = qualification.validate_qualification(doc, selected, plan, now=datetime(2026, 10, 9, 1, 3,
                tzinfo=timezone.utc), audio_plan=inputs).report()
            self.assertEqual(report['status'], 'scoped_evidence_consistent')
            self.assertEqual(report['execution_platform'], 'linux')
            self.assertEqual(report['host_platforms'], {'assistant_asr': 'windows'})

            record['observed_identity']['placement'] = dict(asr_runtime['placement'], instance='Ubuntu-other')
            mismatch = qualification.validate_qualification(doc, selected, plan,
                now=datetime(2026, 10, 9, 1, 3, tzinfo=timezone.utc), audio_plan=inputs).report()
            self.assertIn('observed_identity_mismatch', mismatch['records']['assistant_asr']['gaps'])

            # One evidence platform cannot cover WSL Linux ASR and native Windows TTS.
            doc['scope_roles'] = ['assistant_asr', 'assistant_tts']
            doc['records'] = [record, copy.deepcopy(next(r for r in _qualification_fixture(directory)[5]['records']
                                                          if r['role'] == 'assistant_tts'))]
            tts_record = doc['records'][1]
            tts_record['selection_identity_sha256'] = qualification.selection_identity(selected, 'assistant_tts')
            with self.assertRaisesRegex(qualification.QualificationError, 'evidence_platform_mismatch'):
                qualification.validate_qualification(doc, selected, plan,
                    now=datetime(2026, 10, 9, 1, 3, tzinfo=timezone.utc), audio_plan=inputs)

            doc['scope_roles'] = ['assistant_tts']
            doc['records'] = [tts_record]
            doc['platform'] = 'windows'
            tts_runtime['platform'] = 'windows'
            tts_expected = {'runtime_version': tts_runtime['runtime_version'],
                'implementation': tts_runtime['implementation'],
                'dependency_lock_sha256': tts_runtime['dependency_lock_sha256'], 'device': tts_runtime['device'],
                'artifact_sha256': selected.resolve('assistant_tts')['artifact']['identity_sha256'],
                'preprocessing_sha256': selected.resolve('assistant_tts')['artifact']['preprocessing_sha256'],
                'placement': tts_runtime['placement']}
            tts_record['observed_identity'] = tts_expected
            result = qualification.validate_qualification(doc, selected, plan,
                now=datetime(2026, 10, 9, 1, 3, tzinfo=timezone.utc), audio_plan=inputs).report()
            self.assertEqual(result['status'], 'scoped_evidence_consistent')
            self.assertEqual(result['host_platforms'], {'assistant_tts': 'windows'})

    def test_branch_hash_changes_when_wsl_distribution_instance_changes(self):
        first = self.add_wsl_asr(enabled=True, rollback=True)
        first_identity = qualification.selection_identity(first, 'assistant_asr')
        self.doc['runtimes'][0]['placement']['instance'] = 'Ubuntu-24.04'
        second = deployment.validate_deployment(self.doc, self.catalog)
        self.assertNotEqual(first_identity, qualification.selection_identity(second, 'assistant_asr'))


if __name__ == '__main__':
    unittest.main()

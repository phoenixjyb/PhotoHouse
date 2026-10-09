"""Offline synthetic selection, identity, rollback and private-file boundaries."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'server' / 'backend'))
from app.access import model_deployment as deployment


class ModelDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / 'models/catalog.json').read_text())
        self.doc = json.loads((ROOT / 'models/deployment.synthetic.json').read_text())

    def validate(self):
        return deployment.validate_deployment(self.doc, self.catalog)

    def refused(self, reason):
        with self.assertRaises(deployment.DeploymentError) as caught:
            self.validate()
        self.assertEqual(str(caught.exception), reason)

    def enable(self, role='assistant_asr'):
        binding = next(b for b in self.doc['bindings'] if b['role'] == role)
        provider = next(p for p in self.doc['providers'] if p['id'] == binding['provider'])
        old = copy.deepcopy(provider)
        old['id'] += '-previous'
        if old['endpoint']:
            old['endpoint'] = old['endpoint'].replace(':19001', ':19003').replace(':19002', ':19004')
        else:
            runtime = copy.deepcopy(next(r for r in self.doc['runtimes'] if r['id'] == old['runtime']))
            runtime['id'] += '-previous'
            runtime['runtime_version'] = 'synthetic-previous'
            old['runtime'] = runtime['id']
            if not any(r['id'] == runtime['id'] for r in self.doc['runtimes']):
                self.doc['runtimes'].append(runtime)
        self.doc['providers'].append(old)
        self.doc['rollback_bindings'].append({'role': role, 'provider': old['id'], 'enabled': True})
        binding['enabled'] = True
        return binding, old

    def test_disabled_example_is_immutable_and_report_has_no_private_values(self):
        value = self.validate()
        digest = value.selection_sha256
        selected = value.resolve('assistant_asr')
        selected['provider']['endpoint'] = 'private-mutated'
        self.doc['id'] = 'private-household'
        self.doc['artifacts'][0]['model_name'] = 'private-model'
        self.assertEqual(value.selection_sha256, digest)
        self.assertNotEqual(value.resolve('assistant_asr')['provider']['endpoint'], 'private-mutated')
        self.assertIsNone(value.resolve('assistant_tts'))
        report = value.report()
        self.assertEqual(report['requested_enabled_roles'], [])
        for key in ('runtime_probed', 'artifacts_verified', 'quality_evaluated', 'activation_performed'):
            self.assertFalse(report[key])
        text = repr(value) + json.dumps(report)
        for private in ('private-household', 'synthetic-asr', '19001', 'example.invalid'):
            self.assertNotIn(private, text)

    def test_enabled_selection_requires_distinct_compatible_rollback(self):
        self.doc['bindings'][0]['enabled'] = True
        self.refused('enabled_without_rollback')
        self.doc['bindings'][0]['enabled'] = False
        _, old = self.enable()
        self.assertEqual(self.validate().report()['requested_enabled_roles'], ['assistant_asr'])
        old['endpoint'] = self.doc['providers'][0]['endpoint']
        self.refused('rollback_not_distinct')
        old['endpoint'] = 'http://127.0.0.1:19003/transcribe'
        self.doc['rollback_bindings'][0]['enabled'] = False
        self.refused('rollback_binding')

    def test_rollback_cannot_cross_role_or_adapter_contract(self):
        self.enable()
        self.doc['rollback_bindings'][0]['provider'] = 'memory-asr-candidate'
        self.refused('binding_contract')

    def test_disabled_candidate_can_predeclare_rollback_without_requesting_activation(self):
        binding, _ = self.enable()
        binding['enabled'] = False
        report = self.validate().report()
        self.assertEqual(report['requested_enabled_roles'], [])
        self.assertEqual(report['rollback_declared_roles'], ['assistant_asr'])
        self.assertFalse(report['activation_performed'])

    def test_inline_secrets_unknown_fields_and_malformed_types_are_refused(self):
        pristine = copy.deepcopy(self.doc)
        mutations = [
            (lambda d: d['providers'][0].update(token='synthetic-secret'), 'provider_fields'),
            (lambda d: d['providers'][0].update(adapter=[]), 'provider_contract'),
            (lambda d: d['providers'][0].update(contract='different-contract'), 'provider_contract'),
            (lambda d: d['providers'][0].update(artifact='missing-artifact'), 'provider_reference'),
            (lambda d: d['providers'][0].update(runtime=[]), 'provider_reference'),
            (lambda d: d['providers'][0].update(credential_env='token=value'), 'credential_reference'),
            (lambda d: d['runtimes'][0].update(execution_mode=[]), 'runtime_mode'),
            (lambda d: d['runtimes'][0].update(execution_mode='in_process'), 'provider_execution_mode'),
            (lambda d: d['artifacts'][0].update(kind=[]), 'artifact_kind'),
            (lambda d: d['bindings'][0].update(enabled=1), 'binding_contract'),
            (lambda d: d['bindings'].append(copy.deepcopy(d['bindings'][0])), 'binding_role'),
            (lambda d: d['runtimes'].append(copy.deepcopy(d['runtimes'][0])), 'runtime_inventory'),
            (lambda d: d.update(schema=True), 'manifest_version'),
        ]
        for mutation, reason in mutations:
            with self.subTest(reason=reason):
                self.doc = copy.deepcopy(pristine)
                mutation(self.doc)
                self.refused(reason)

    def test_endpoint_restrictions_and_safe_credential_reference(self):
        provider = self.doc['providers'][0]
        for url in ('https://127.0.0.1:19001/transcribe', 'http://provider.invalid:19001/transcribe',
                    'http://127.0.0.1/transcribe', 'http://@127.0.0.1:19001/transcribe',
                    'http://user:secret@127.0.0.1:19001/transcribe',
                    'http://127.0.0.1:19001/transcribe?token=secret',
                    'http://127.0.0.1:19001/transcribe#secret', 'http://127.0.0.1:19001',
                    'http://127.0.0.1:99999/transcribe'):
            with self.subTest(url=url):
                provider['endpoint'] = url
                self.refused('invalid_local_endpoint')
        provider['endpoint'] = 'http://localhost:19001/transcribe'
        provider['credential_env'] = 'PHOTOHOUSE_ASR_TOKEN'
        with patch.dict(os.environ, {'PHOTOHOUSE_ASR_TOKEN': 'never-read-this-secret'}):
            self.assertNotIn('never-read-this-secret', json.dumps(self.validate().report()))
        self.doc['providers'][2]['endpoint'] = 'http://localhost:19002/chat'
        self.refused('invalid_local_endpoint')

    def test_resource_and_device_types_and_contract_timeout(self):
        budget = self.doc['runtimes'][0]['resources']
        for field, value, reason in (('max_concurrency', True, 'resource_concurrency'),
                                     ('ram_limit_mib', 0, 'resource_memory'),
                                     ('minimum_free_ram_mib', -1, 'resource_memory'),
                                     ('vram_floor_mib', 1, 'resource_device_mismatch'),
                                     ('timeout_seconds', 61, 'provider_timeout')):
            previous = budget[field]
            budget[field] = value
            self.refused(reason)
            budget[field] = previous
        runtime = self.doc['runtimes'][0]
        runtime['device'] = {'kind': 'cuda', 'index': 0, 'hardware_id': 'GPU-12345678-abcd'}
        self.refused('resource_device_mismatch')
        budget['vram_floor_mib'] = 1024
        self.validate()
        runtime['device']['index'] = True
        self.refused('cuda_device_index')

    def test_shared_environment_cannot_claim_conflicting_dependency_locks(self):
        candidate = copy.deepcopy(self.doc['runtimes'][0])
        candidate['id'] += '-other'
        candidate['dependency_lock_sha256'] = '4' * 64
        self.doc['runtimes'].append(candidate)
        self.refused('environment_identity_conflict')

    def test_model_version_and_vector_space_identity_cannot_be_reused(self):
        artifact = copy.deepcopy(self.doc['artifacts'][2])
        artifact['id'] += '-other'
        artifact['identity_sha256'] = '4' * 64
        self.doc['artifacts'].append(artifact)
        self.refused('model_version_reused')
        artifact['model_version'] = 'synthetic-v2'
        self.refused('vector_space_reused')
        artifact['vector_space']['id'] = 'synthetic-clip-space-v2'
        self.validate()

    def test_equal_dimensions_are_not_embedding_compatibility(self):
        self.enable('image_embedding')
        self.enable('video_embedding')
        self.validate()
        artifact = copy.deepcopy(self.doc['artifacts'][2])
        artifact.update(id='clip-v2', model_version='synthetic-v2', identity_sha256='4' * 64)
        artifact['vector_space']['id'] = 'synthetic-clip-space-v2'
        self.doc['artifacts'].append(artifact)
        next(p for p in self.doc['providers'] if p['role'] == 'video_embedding')['artifact'] = 'clip-v2'
        self.refused('image_video_space_mismatch')

    def test_current_approved_embedding_contracts_remain_explicit(self):
        provider = self.doc['providers'][-2]
        artifact = self.doc['artifacts'][2]
        artifact['vector_space']['normalization'] = 'none'
        self.refused('approved_image_normalization')
        artifact['vector_space']['normalization'] = 'unit_l2'
        artifact['model_name'] = 'another-model'
        self.refused('approved_image_model')
        artifact['model_name'] = 'clip-synthetic'
        provider['endpoint'] = 'http://127.0.0.1:19002/generate'
        self.refused('non_http_provider_endpoint')
        provider['endpoint'] = None
        provider['role'] = 'face_embedding'
        spec = next(s for s in self.catalog['capabilities'] if s['id'] == 'face_embedding')
        provider.update(adapter=spec['adapters'][0]['symbol'], contract=spec['contract'])
        artifact['vector_space']['dimension'] = 256
        self.refused('approved_face_dimension')

    def test_system_voice_is_a_windows_tts_artifact_only(self):
        self.doc['artifacts'][0]['kind'] = 'system_voice'
        self.refused('system_voice_runtime')
        spec = next(s for s in self.catalog['capabilities'] if s['id'] == 'assistant_tts')
        voice = copy.deepcopy(self.doc['artifacts'][0])
        voice.update(id='synthetic-voice', model_name='synthetic-system-voice')
        self.doc['artifacts'].append(voice)
        self.doc['artifacts'][0]['kind'] = 'checkpoint'
        provider = self.doc['providers'][0]
        provider.update(role='assistant_tts', adapter='LocalAssistantTts', contract=spec['contract'], artifact=voice['id'])
        self.doc['bindings'][0]['role'] = 'assistant_tts'
        self.validate()
        self.doc['runtimes'][0]['platform'] = 'linux'
        self.refused('system_voice_runtime')

    def test_license_implementation_digest_and_source_catalog_are_bounded(self):
        self.doc['artifacts'][0]['license_source'] = 'https://@example.invalid/license'
        self.refused('invalid_reference_url')
        self.doc['artifacts'][0]['license_source'] = 'https://example.invalid/license'
        self.doc['runtimes'][0]['implementation']['revision'] = 'main'
        self.refused('implementation_revision')
        self.doc['runtimes'][0]['implementation']['revision'] = 'a' * 40
        self.catalog['capabilities'][0] = None
        self.refused('source_catalog')

    def test_each_catalog_role_can_declare_its_current_adapter_without_activation(self):
        for spec in self.catalog['capabilities']:
            with self.subTest(role=spec['id']):
                doc = copy.deepcopy(self.doc)
                runtime = doc['runtimes'][0]
                runtime['execution_mode'] = spec['execution_modes'][0]
                artifact = doc['artifacts'][0]
                if spec['id'] in deployment.VECTOR_ROLES:
                    artifact.update(model_name='clip-synthetic', vector_space={
                        'id': 'synthetic-role-space', 'dimension': 512, 'normalization': 'unit_l2'})
                provider = doc['providers'][0]
                provider.update(role=spec['id'], adapter=spec['adapters'][0]['symbol'], contract=spec['contract'])
                if runtime['execution_mode'] not in {'http_service', 'loopback_http'}:
                    provider['endpoint'] = None
                elif spec['id'] in deployment.TEXT_ROLES:
                    provider['endpoint'] = 'http://127.0.0.1:19001/api/generate'
                doc.update(runtimes=[runtime], artifacts=[artifact], providers=[provider],
                           bindings=[{'role': spec['id'], 'provider': provider['id'], 'enabled': False}])
                result = deployment.validate_deployment(doc, self.catalog)
                self.assertEqual(result.report()['selected_roles'], [spec['id']])
                self.assertFalse(result.report()['activation_performed'])

    def test_inventory_implementation_is_not_an_http_request_adapter(self):
        spec = next(s for s in self.catalog['capabilities'] if s['id'] == 'vlm_caption')
        self.doc['providers'][0].update(role='vlm_caption', adapter='CaptionSubprocessProvider', contract=spec['contract'])
        self.refused('adapter_not_selectable')
        spec = next(s for s in self.catalog['capabilities'] if s['id'] == 'assistant_tts')
        self.doc['providers'][0].update(role='assistant_tts', adapter='WindowsSystemSpeech', contract=spec['contract'])
        self.refused('adapter_not_selectable')

    def test_strict_json_duplicate_nonfinite_invalid_utf8_and_depth(self):
        cases = [(b'{"id":1,"id":2}', 'duplicate_json_key'),
                 (b'{"id":NaN}', 'nonfinite_json'), (b'\xff', 'manifest_json'),
                 (b'[' * 2000 + b']' * 2000, 'manifest_json')]
        for payload, reason in cases:
            with self.subTest(reason=reason):
                with self.assertRaises(deployment.DeploymentError) as caught:
                    deployment._strict_json(payload)
                self.assertEqual(str(caught.exception), reason)

    def test_private_reader_only_reads_metadata_and_refuses_checkout_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            root.chmod(0o700)
            path = root / 'selection.json'
            path.write_text(json.dumps(self.doc)); path.chmod(0o600)
            result = deployment.load_private_deployment(path, self.catalog, source_root=ROOT)
            self.assertFalse(result.report()['activation_performed'])
            self.assertEqual(list(root.iterdir()), [path])
            with self.assertRaisesRegex(deployment.DeploymentError, 'manifest_location'):
                deployment.load_private_deployment(ROOT / 'models/deployment.synthetic.json', self.catalog, source_root=ROOT)
            with self.assertRaisesRegex(deployment.DeploymentError, 'manifest_location'):
                deployment.load_private_deployment('relative.json', self.catalog, source_root=ROOT)
            missing = root / 'private-missing.json'
            with self.assertRaisesRegex(deployment.DeploymentError, 'private_manifest_unavailable'):
                deployment.load_private_deployment(missing, self.catalog, source_root=ROOT)
            self.assertFalse(missing.exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX mode/alias checks; Windows DACL tests are separate')
    def test_permissions_symlinks_hardlinks_and_size_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); root.chmod(0o700)
            path = root / 'selection.json'
            path.write_text(json.dumps(self.doc)); path.chmod(0o644)
            def load():
                return deployment.load_private_deployment(path, self.catalog, source_root=ROOT)
            with self.assertRaisesRegex(deployment.DeploymentError, 'private_manifest_unavailable'): load()
            path.chmod(0o600); root.chmod(0o755)
            with self.assertRaisesRegex(deployment.DeploymentError, 'private_manifest_unavailable'): load()
            root.chmod(0o700)
            alias = root / 'alias'; alias.symlink_to(path)
            with self.assertRaisesRegex(deployment.DeploymentError, 'manifest_link'):
                deployment.load_private_deployment(alias, self.catalog, source_root=ROOT)
            alias.unlink(); os.link(path, alias)
            with self.assertRaisesRegex(deployment.DeploymentError, 'private_manifest_unavailable'): load()
            alias.unlink(); path.write_bytes(b'x' * (deployment.MAX_BYTES + 1))
            with self.assertRaisesRegex(deployment.DeploymentError, 'manifest_too_large'): load()

    def test_mid_read_replacement_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); root.chmod(0o700)
            path = root / 'selection.json'
            path.write_text(json.dumps(self.doc)); path.chmod(0o600)
            real_check = deployment.require_private_file
            calls = []
            def replace_after_read(selected):
                calls.append(selected)
                if len(calls) == 2:
                    replacement = root / 'replacement.json'
                    replacement.write_text(json.dumps(self.doc)); replacement.chmod(0o600)
                    os.replace(replacement, path)
                real_check(selected)
            with patch.object(deployment, 'require_private_file', side_effect=replace_after_read):
                with self.assertRaisesRegex(deployment.DeploymentError, 'manifest_changed'):
                    deployment.load_private_deployment(path, self.catalog, source_root=ROOT)

    def test_windows_creation_identity_allows_path_handle_ctime_difference_but_checks_handle_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve(); root.chmod(0o700)
            path = root / 'selection.json'
            path.write_text(json.dumps({'synthetic': True})); path.chmod(0o600)
            real_fstat = os.fstat

            class FakeStream:
                def __init__(self, fd):
                    self.fd = fd

                def __enter__(self):
                    return self

                def __exit__(self, *_args):
                    os.close(self.fd)

                def fileno(self):
                    return self.fd

                def read(self, _limit):
                    return json.dumps({'synthetic': True}).encode()

            def identity(info):
                # Windows stable identity is dev/inode/size/mtime/birthtime;
                # raw ctime remains separately comparable between fstat calls.
                return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, 123)

            for ctimes, expected_error in (((111, 111), None), ((111, 222), 'manifest_changed')):
                with self.subTest(ctimes=ctimes):
                    samples = iter(ctimes)

                    def fake_fstat(fd):
                        value = real_fstat(fd)
                        return SimpleNamespace(st_dev=value.st_dev, st_ino=value.st_ino,
                            st_size=value.st_size, st_mtime_ns=value.st_mtime_ns,
                            st_mode=value.st_mode, st_ctime_ns=next(samples))

                    with patch.object(deployment, 'stable_stat_identity', side_effect=identity), \
                            patch.object(deployment.os, 'fstat', side_effect=fake_fstat), \
                            patch.object(deployment.os, 'fdopen', side_effect=lambda fd, _mode: FakeStream(fd)):
                        if expected_error:
                            with self.assertRaisesRegex(deployment.DeploymentError, expected_error):
                                deployment._load_private_document(path, source_root=ROOT)
                        else:
                            self.assertEqual(deployment._load_private_document(path, source_root=ROOT),
                                             {'synthetic': True})


if __name__ == '__main__':
    unittest.main()

"""Explicit model projections exercise real config parsers without model/storage I/O."""
from contextlib import nullcontext
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'server/backend'), str(ROOT / 'server/scripts')]
from app.access.model_binding import ModelBindingError, project_configuration
from app.access.model_deployment import ValidatedDeployment, validate_deployment
from app.access.runtime import RuntimeConfiguration
import staging_app
import run_memory_worker as worker


class ModelBindingTests(unittest.TestCase):
    def setUp(self):
        self.doc = json.loads((ROOT / 'models/deployment.synthetic.json').read_text())
        self.catalog = json.loads((ROOT / 'models/catalog.json').read_text())
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.staging = {'format_version': 1, 'database': str(self.root / 'db' / 'metadata.sqlite'),
            'web_origin': 'https://photohouse.test:8443', 'original_roots': [str(self.root / 'originals')],
            'derived_root': str(self.root / 'derived'), 'bind_host': '127.0.0.1', 'port': 8443,
            'tls_certificate': str(self.root / 'tls' / 'certificate.pem'),
            'tls_private_key': str(self.root / 'tls' / 'key.pem')}
        self.memory = {'database': str(self.root / 'metadata.sqlite'), 'mode': 'contributions',
            'ollama_url': None, 'ollama_model': None, 'asr_url': None, 'asr_model': None, 'asr_token': None,
            'original_deletion_journal_path': str(self.root / 'deletions.sqlite'),
            'original_deletion_namespace': '00000000-0000-4000-8000-000000000001'}

    def enable(self, role, *, timeout=None, credential=None):
        provider = next(p for p in self.doc['providers'] if p['role'] == role)
        if timeout is not None:
            runtime = copy.deepcopy(next(r for r in self.doc['runtimes'] if r['id'] == provider['runtime']))
            runtime.update(id=role.replace('_', '-') + '-runtime')
            runtime['resources']['timeout_seconds'] = timeout
            self.doc['runtimes'].append(runtime)
            provider['runtime'] = runtime['id']
        provider['credential_env'] = credential
        previous = copy.deepcopy(provider)
        previous['id'] += '-old'
        previous['endpoint'] = previous['endpoint'].replace(':19001', ':19101').replace(':19002', ':19102')
        self.doc['providers'].append(previous)
        binding = next(b for b in self.doc['bindings'] if b['role'] == role)
        binding['enabled'] = True
        self.doc['rollback_bindings'].append({'role': role, 'provider': previous['id'], 'enabled': True})
        return provider

    def add_tts(self):
        spec = next(s for s in self.catalog['capabilities'] if s['id'] == 'assistant_tts')
        artifact = copy.deepcopy(self.doc['artifacts'][0])
        artifact.update(id='system-voice', kind='system_voice', model_name='synthetic-voice')
        self.doc['artifacts'].append(artifact)
        self.doc['providers'].append({'id': 'tts-candidate', 'role': 'assistant_tts',
            'adapter': 'LocalAssistantTts', 'contract': spec['contract'], 'runtime': 'asr-service',
            'artifact': artifact['id'], 'endpoint': 'http://127.0.0.1:19001/synthesize', 'credential_env': None})
        self.doc['bindings'].append({'role': 'assistant_tts', 'provider': 'tts-candidate', 'enabled': False})

    def deployment(self):
        return validate_deployment(self.doc, self.catalog)

    def project(self, target='assistant', enabled=True, rollback=False):
        return project_configuration(self.deployment(), target=target, platform='windows',
                                     feature_enabled=enabled, rollback=rollback)

    def contributions(self, *, timeout=45):
        self.enable('memory_asr', timeout=timeout)
        self.enable('annotation_polish', timeout=20)
        return worker.with_model_deployment(self.memory, self.deployment(), platform='windows',
                                            processing_enabled=True)

    def test_assistant_requires_independent_opt_in_and_keeps_all_other_flags(self):
        self.enable('assistant_asr', timeout=7)
        base = staging_app.parse_configuration(self.staging)
        with self.assertRaisesRegex(ModelBindingError, 'feature_opt_in_required'):
            base.with_model_deployment(self.deployment(), platform='windows')
        base = staging_app.parse_configuration(self.staging | {'assistant_enabled': True})
        with patch('sqlite3.connect', side_effect=AssertionError('storage forbidden')), \
             patch('httpx.Client', side_effect=AssertionError('network forbidden')), \
             patch.object(base.__class__, 'build_app', side_effect=AssertionError('build forbidden')):
            selected = base.with_model_deployment(self.deployment(), platform='windows')
        self.assertIsNone(base.assistant_asr_url)
        self.assertEqual(selected.assistant_asr_model, 'synthetic-asr')
        self.assertEqual(selected.assistant_asr_timeout_seconds, 7)
        self.assertTrue(selected.assistant_enabled)
        for name in ('annotation_intake_enabled', 'memory_collaboration_enabled', 'memory_originals_enabled',
                     'memory_generation_enabled', 'memory_editorial_enabled', 'memory_editions_enabled',
                     'upload_review_enabled'):
            self.assertFalse(getattr(selected, name))
        self.assertEqual(vars(base) | {'assistant_asr_url': selected.assistant_asr_url,
            'assistant_asr_model': selected.assistant_asr_model,
            'assistant_asr_timeout_seconds': 7}, vars(selected))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_partial_assistant_projection_preserves_unlisted_existing_tts(self):
        self.enable('assistant_asr')
        base = staging_app.parse_configuration(self.staging | {'assistant_enabled': True,
            'assistant_tts_url': 'http://localhost:19200/synthesize'})
        selected = base.with_model_deployment(self.deployment(), platform='windows')
        self.assertEqual(selected.assistant_tts_url, base.assistant_tts_url)
        self.assertEqual(selected.assistant_tts_timeout_seconds, 45)

    def test_disabled_binding_is_noop_only_for_unconfigured_provider(self):
        base = staging_app.parse_configuration(self.staging)
        self.assertEqual(vars(base.with_model_deployment(self.deployment(), platform='windows')), vars(base))
        active = staging_app.parse_configuration(self.staging | {'assistant_enabled': True,
            'assistant_asr_url': 'http://localhost:19200/transcribe', 'assistant_asr_model': 'existing'})
        with self.assertRaisesRegex(ModelBindingError, 'disabled_binding_configuration_conflict'):
            active.with_model_deployment(self.deployment(), platform='windows')

    def test_explicit_conflicting_provider_is_not_overwritten_and_matching_is_idempotent(self):
        self.enable('assistant_asr', timeout=7)
        base = staging_app.parse_configuration(self.staging | {'assistant_enabled': True})
        selected = base.with_model_deployment(self.deployment(), platform='windows')
        self.assertEqual(vars(selected.with_model_deployment(self.deployment(), platform='windows')), vars(selected))
        for change in ({'assistant_asr_model': 'other'}, {'assistant_asr_timeout_seconds': 8},
                       {'assistant_asr_token': 'private-old-token'}):
            from dataclasses import replace
            conflicting = replace(selected, **change)
            with self.assertRaisesRegex(ModelBindingError, 'provider_configuration_conflict'):
                conflicting.with_model_deployment(self.deployment(), platform='windows')

    def test_explicit_credentials_never_come_from_environment_or_projection_repr(self):
        self.enable('assistant_asr', credential='PHOTOHOUSE_TEST_ASR_TOKEN')
        with patch.dict(os.environ, {'PHOTOHOUSE_TEST_ASR_TOKEN': 'ambient-secret'}):
            projection = self.project()
            with self.assertRaisesRegex(ModelBindingError, 'credential_values_required'):
                projection.bind_fields({})
        for value in (None, '', 'bad\ntoken', '\ud800', 'x' * 4097):
            with self.subTest(value=type(value).__name__):
                with self.assertRaisesRegex(ModelBindingError, 'credential_value_invalid'):
                    projection.bind_fields({}, credential_values={'PHOTOHOUSE_TEST_ASR_TOKEN': value})
        fields = projection.bind_fields({}, credential_values={'PHOTOHOUSE_TEST_ASR_TOKEN': 'explicit-secret'})
        self.assertEqual(fields['assistant_asr_token'], 'explicit-secret')
        for value in ('explicit-secret', 'ambient-secret', 'PHOTOHOUSE_TEST_ASR_TOKEN', 'synthetic-asr', '19001'):
            self.assertNotIn(value, repr(projection) + json.dumps(projection.report()))

    def test_runtime_and_staging_copies_do_not_repr_tokens_and_staging_passes_timeouts(self):
        self.enable('assistant_asr', timeout=7, credential='PHOTOHOUSE_TEST_ASR_TOKEN')
        self.add_tts(); self.enable('assistant_tts', timeout=11)
        values = {'PHOTOHOUSE_TEST_ASR_TOKEN': 'explicit-secret'}
        base = staging_app.parse_configuration(self.staging | {'assistant_enabled': True})
        selected = base.with_model_deployment(self.deployment(), platform='windows', credential_values=values)
        runtime = RuntimeConfiguration(base.database, base.web_origin, base.original_roots, base.derived_root,
                                       assistant_enabled=True).with_model_deployment(
            self.deployment(), platform='windows', credential_values=values)
        self.assertNotIn('explicit-secret', repr(runtime) + repr(selected))
        self.assertEqual(runtime.assistant_tts_timeout_seconds, 11)
        with patch('app.access.runtime.RuntimeConfiguration') as constructor:
            selected.build_app()
        self.assertEqual(constructor.call_args.kwargs['assistant_asr_timeout_seconds'], 7)
        self.assertEqual(constructor.call_args.kwargs['assistant_tts_timeout_seconds'], 11)

    def test_actual_runtime_constructors_receive_projected_timeouts_without_http(self):
        self.enable('assistant_asr', timeout=7); self.add_tts(); self.enable('assistant_tts', timeout=11)
        settings = RuntimeConfiguration(self.root / 'db', 'https://photohouse.test',
            (self.root / 'originals',), self.root / 'derived', assistant_enabled=True)
        settings = settings.with_model_deployment(self.deployment(), platform='windows')
        with patch('app.main.create_app'), patch('httpx.Client', side_effect=AssertionError('network forbidden')), \
             patch('sqlite3.connect', side_effect=AssertionError('storage forbidden')), \
             patch('app.access.assistant_speech.LocalAssistantAsr') as asr, \
             patch('app.access.assistant_speech.LocalAssistantTts') as tts:
            settings.build_app()
        self.assertEqual(asr.call_args.kwargs['timeout'], 7)
        self.assertEqual(tts.call_args.kwargs['timeout'], 11)

    def test_target_platform_flags_and_credentials_without_runtime_destination_are_refused(self):
        self.enable('assistant_asr')
        for kwargs, reason in (({'platform': 'linux'}, 'runtime_platform_mismatch'),
                               ({'feature_enabled': 1}, 'explicit_projection_flags'),
                               ({'target': 'face_embedding'}, 'unsupported_projection_target')):
            arguments = dict(target='assistant', platform='windows', feature_enabled=True)
            arguments.update(kwargs)
            with self.assertRaisesRegex(ModelBindingError, reason):
                project_configuration(self.deployment(), **arguments)
        self.enable('narrative', credential='PHOTOHOUSE_LLM_TOKEN')
        with self.assertRaisesRegex(ModelBindingError, 'credential_not_supported_by_target'):
            self.project('memory-narrative')

    def test_story_title_projection_is_distinct_and_requires_its_own_opt_in(self):
        self.enable('annotation_polish')
        self.enable('narrative')
        with self.assertRaisesRegex(ModelBindingError, 'required_binding_not_enabled'):
            self.project('story-titles')

        self.enable('title_suggestions', timeout=60)
        with self.assertRaisesRegex(ModelBindingError, 'feature_opt_in_required'):
            self.project('story-titles', enabled=False)
        projection = self.project('story-titles')
        self.assertEqual(projection.report()['projected_roles'], ['title_suggestions'])
        self.assertEqual(projection.report()['request_timeouts_seconds'], {'title_suggestions': 30})
        fields = projection.bind_fields({})
        self.assertEqual(fields, {
            'story_title_url': 'http://127.0.0.1:19002/api/generate',
            'story_title_model': 'synthetic-language',
            'story_title_timeout_seconds': 30,
        })
        self.assertNotIn('ollama_url', fields)
        self.assertNotIn('ollama_model', fields)
        self.assertNotIn('title_suggestions', projection.report().get('disabled_roles', []))

    def test_story_title_projection_preserves_conflict_idempotence_and_redaction(self):
        provider = self.enable('title_suggestions', timeout=11)
        projection = self.project('story-titles')
        fields = projection.bind_fields({})
        self.assertEqual(projection.bind_fields(fields), fields)
        self.assertEqual(fields['story_title_timeout_seconds'], 11)
        for change in ({'story_title_url': 'http://localhost:19999/api/generate'},
                       {'story_title_model': 'another-model'},
                       {'story_title_timeout_seconds': 12}):
            with self.subTest(change=tuple(change)):
                with self.assertRaisesRegex(ModelBindingError, 'provider_configuration_conflict'):
                    projection.bind_fields(fields | change)
        for private in (provider['endpoint'], 'synthetic-language', '19002'):
            self.assertNotIn(private, repr(projection) + json.dumps(projection.report()))

    def test_story_title_projection_checks_platform_credentials_and_rollback_binding(self):
        self.enable('title_suggestions', timeout=60)
        with self.assertRaisesRegex(ModelBindingError, 'runtime_platform_mismatch'):
            project_configuration(self.deployment(), target='story-titles', platform='linux',
                                  feature_enabled=True)
        rollback = self.project('story-titles', rollback=True)
        self.assertEqual(rollback.report()['selection'], 'rollback')
        self.assertEqual(rollback.bind_fields({})['story_title_url'],
                         'http://127.0.0.1:19102/api/generate')
        provider = next(p for p in self.doc['providers'] if p['role'] == 'title_suggestions')
        provider['credential_env'] = 'PHOTOHOUSE_TEST_TITLE_TOKEN'
        with self.assertRaisesRegex(ModelBindingError, 'credential_not_supported_by_target'):
            self.project('story-titles')

    def test_story_title_staging_and_runtime_projection_are_explicit_and_pure(self):
        self.enable('title_suggestions', timeout=60)
        deployment = self.deployment()
        runtime_base = RuntimeConfiguration(self.root / 'db', 'https://photohouse.test',
            (self.root / 'originals',), self.root / 'derived', assistant_enabled=True)
        staging_base = staging_app.parse_configuration(self.staging | {'assistant_enabled': True})
        with patch('sqlite3.connect', side_effect=AssertionError('storage forbidden')), \
             patch('httpx.Client', side_effect=AssertionError('network forbidden')), \
             patch.object(RuntimeConfiguration, 'build_app', side_effect=AssertionError('runtime build forbidden')) as runtime_build, \
             patch.object(staging_app.StagingConfiguration, 'build_app', side_effect=AssertionError('staging build forbidden')) as staging_build:
            with self.assertRaisesRegex(ModelBindingError, 'feature_opt_in_required'):
                runtime_base.with_story_title_model_deployment(deployment, platform='windows')
            with self.assertRaisesRegex(ModelBindingError, 'feature_opt_in_required'):
                staging_base.with_story_title_model_deployment(deployment, platform='windows')

            runtime = replace(runtime_base, story_title_suggestions_enabled=True)
            staging = staging_app.parse_configuration(self.staging | {
                'assistant_enabled': True, 'story_title_suggestions_enabled': True})
            runtime_selected = runtime.with_story_title_model_deployment(deployment, platform='windows')
            staging_selected = staging.with_story_title_model_deployment(deployment, platform='windows')
            expected = {
                'story_title_url': 'http://127.0.0.1:19002/api/generate',
                'story_title_model': 'synthetic-language',
                'story_title_timeout_seconds': 30,
            }
            for selected in (runtime_selected, staging_selected):
                for key, value in expected.items():
                    self.assertEqual(getattr(selected, key), value)
                self.assertTrue(selected.story_title_suggestions_enabled)
                self.assertTrue(selected.assistant_enabled)

            runtime_rollback = runtime.with_story_title_model_deployment(
                deployment, platform='windows', rollback=True)
            staging_rollback = staging.with_story_title_model_deployment(
                deployment, platform='windows', rollback=True)
            for selected in (runtime_rollback, staging_rollback):
                self.assertEqual(selected.story_title_url, 'http://127.0.0.1:19102/api/generate')
                self.assertEqual(selected.story_title_timeout_seconds, 30)

            for selected, method in ((runtime_selected, 'with_story_title_model_deployment'),
                                     (staging_selected, 'with_story_title_model_deployment')):
                conflicting = replace(selected, story_title_model='different-model')
                with self.assertRaisesRegex(ModelBindingError, 'provider_configuration_conflict'):
                    getattr(conflicting, method)(deployment, platform='windows')
                with self.assertRaisesRegex(ModelBindingError, 'provider_configuration_conflict'):
                    getattr(selected, method)(deployment, platform='windows', rollback=True)

            runtime_build.assert_not_called()
            staging_build.assert_not_called()

    def test_unvalidated_constructed_or_changed_snapshots_cannot_be_projected(self):
        with self.assertRaises(TypeError):
            ValidatedDeployment('a' * 64, b'{"unvalidated":"payload"}')
        empty = object.__new__(ValidatedDeployment)
        with self.assertRaisesRegex(ModelBindingError, 'validated_deployment_required'):
            project_configuration(empty, target='assistant', platform='windows')
        selected = self.deployment()
        object.__setattr__(selected, '_payload', selected._payload.replace(b'synthetic-asr', b'changed-model'))
        with self.assertRaisesRegex(ModelBindingError, 'validated_deployment_required'):
            project_configuration(selected, target='assistant', platform='windows')

    def test_explicit_rollback_uses_the_declared_previous_provider(self):
        self.enable('assistant_asr')
        fields = self.project(rollback=True).bind_fields({})
        self.assertIn(':19101/', fields['assistant_asr_url'])
        self.assertEqual(self.project(rollback=True).report()['selection'], 'rollback')
        active = staging_app.parse_configuration(self.staging | {'assistant_enabled': True})
        current = active.with_model_deployment(self.deployment(), platform='windows')
        with self.assertRaisesRegex(ModelBindingError, 'provider_configuration_conflict'):
            current.with_model_deployment(self.deployment(), platform='windows', rollback=True)

    def test_contributions_require_both_roles_and_worker_processing_opt_in(self):
        self.enable('memory_asr')
        with self.assertRaisesRegex(ModelBindingError, 'required_binding_not_enabled'):
            self.project('memory-contributions')
        self.enable('annotation_polish')
        with self.assertRaisesRegex(ModelBindingError, 'feature_opt_in_required'):
            worker.with_model_deployment(self.memory, self.deployment(), platform='windows')
        with patch('sqlite3.connect', side_effect=AssertionError('storage forbidden')), \
             patch('httpx.Client', side_effect=AssertionError('network forbidden')):
            selected = worker.with_model_deployment(self.memory, self.deployment(), platform='windows', processing_enabled=True)
        self.assertEqual(selected['asr_model'], 'synthetic-asr')
        self.assertEqual(selected['ollama_model'], 'synthetic-language')
        self.assertIsNone(self.memory['asr_url'])
        self.assertEqual(selected['original_deletion_journal_path'], self.memory['original_deletion_journal_path'])
        self.assertNotIn('memory_editorial_enabled', selected)

    def test_worker_projection_passes_actual_parser_and_phase_timeout_caps(self):
        selected = self.contributions()
        path = self.root / 'worker.json'; path.write_text(json.dumps(selected))
        reread = worker.read_config(path)
        self.assertEqual(reread, selected)
        self.assertEqual(reread['asr_timeout_seconds'], 30)
        self.assertEqual(reread['ollama_timeout_seconds'], 20)
        with patch('httpx.Client', side_effect=AssertionError('network forbidden')):
            self.assertEqual(worker._adapters(reread, timeout=25, phase='transcribe').timeout, 25)
            self.assertEqual(worker._adapters(reread, timeout=25, phase='polish').timeout, 20)
            self.assertEqual(worker._adapters(reread, timeout=3, phase='polish').timeout, 3)

    def test_narrative_projection_preserves_null_asr_and_editorial_flag(self):
        self.memory.update(mode='narrative', memory_editorial_enabled=True)
        self.enable('narrative', timeout=12)
        selected = worker.with_model_deployment(self.memory, self.deployment(), platform='windows', processing_enabled=True)
        self.assertTrue(selected['memory_editorial_enabled'])
        for name in ('asr_url', 'asr_model', 'asr_token'):
            self.assertIsNone(selected[name])
        with patch('httpx.Client', side_effect=AssertionError('network forbidden')):
            self.assertEqual(worker._adapters(selected, timeout=30).timeout, 12)
        selected['mode'] = 'contributions'
        with self.assertRaises(worker.WorkerConfigurationError):
            worker.validate_config(selected)

    def test_timeout_extensions_reject_booleans_nonfinite_and_out_of_range(self):
        for value in (True, 0, -1, 61, float('nan'), float('inf'), '7'):
            with self.subTest(target='assistant', value=type(value).__name__):
                with self.assertRaises(staging_app.InvalidConfiguration):
                    staging_app.parse_configuration(self.staging | {'assistant_asr_timeout_seconds': value})
        selected = self.contributions()
        for value in (True, 0, -1, 31, float('nan'), float('inf'), '7'):
            with self.subTest(target='memory', value=type(value).__name__):
                with self.assertRaises(worker.WorkerConfigurationError):
                    worker.validate_config(selected | {'asr_timeout_seconds': value})

    def test_worker_shared_item_deadline_still_bounds_the_second_phase(self):
        selected = self.contributions(timeout=7)
        now, calls = [0], []
        def models(**kwargs):
            timeout = kwargs['timeout']
            def asr(*args):
                calls.append(('asr', timeout)); now[0] = 18; return 'synthetic'
            def polish(*args):
                calls.append(('polish', timeout)); return 'synthetic'
            return SimpleNamespace(transcribe=asr, polish=polish)
        def contribution(db, **kwargs):
            kwargs['transcribe'](b'fake', 'zh'); kwargs['polish']('fake', 'zh')
            return {'state': 'ready'}
        with patch.object(worker, '_database', return_value=lambda: nullcontext(object())), \
             patch.object(worker, '_check_schema', return_value=True), \
             patch.object(worker, 'LocalAnnotationModels', side_effect=models), \
             patch.object(worker, 'process_contribution', side_effect=contribution):
            worker._run(selected, maximum_items=1, maximum_seconds=25, once=True, clock=lambda: now[0])
        self.assertEqual(calls, [('asr', 7), ('polish', 7)])
        self.assertEqual((worker.PROVIDER_TIMEOUT, worker.MAX_ITEMS, worker.MAX_SECONDS), (30, 32, 1800))


if __name__ == '__main__':
    unittest.main()

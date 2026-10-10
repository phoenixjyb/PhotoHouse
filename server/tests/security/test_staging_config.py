"""Synthetic coverage for the staging configuration contract.

This is the only place a deployment's roots are declared, and it is deliberately strict: the
accepted field set is exact, every path must be absolute and canonical, and no two roots may
overlap. The incoming root is the one optional field, and it exists precisely so that a
configuration written before member upload existed keeps loading.
"""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'backend'))

import staging_app as s
import app.access.runtime  # noqa: F401 - mocked runtime target must be importable in isolation


def base():
    return {
        'format_version': 1,
        'database': '/synthetic/databases/metadata.sqlite',
        'web_origin': 'https://photohouse.test:8443',
        'original_roots': ['/synthetic/01_INCOMING'],
        'derived_root': '/synthetic/VLM_DATA/derived',
        'bind_host': '100.98.1.2',
        'port': 8443,
        'tls_certificate': '/synthetic/tls/server.crt',
        'tls_private_key': '/synthetic/tls/server.key',
    }


class StagingConfigurationTests(unittest.TestCase):
    def test_memory_groups_are_manual_default_off_and_forward_a_typed_vector_profile_only_when_complete(self):
        legacy = s.parse_configuration(base())
        self.assertFalse(legacy.memory_groups_enabled)
        self.assertIsNone(legacy.memory_group_vector_root)
        self.assertIsNone(legacy.memory_group_vector_identity)
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            legacy.build_app()
        self.assertIs(runtime.call_args.kwargs['memory_groups_enabled'], False)
        self.assertIsNone(runtime.call_args.kwargs['memory_group_vectors'])

        manual = s.parse_configuration(dict(base(), memory_groups_enabled=True))
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            manual.build_app()
        self.assertIs(runtime.call_args.kwargs['memory_groups_enabled'], True)
        self.assertIsNone(runtime.call_args.kwargs['memory_group_vectors'])

        identity_json = {
            'artifact_sha256': 'a' * 64,
            'preprocessing_sha256': 'b' * 64,
            'vector_space_id': 'family-photo-v1',
            'model_version': 'clip-v2',
            'dimension': 768,
            'normalization': 'unit_l2',
        }
        source = dict(base(), memory_groups_enabled=True,
            memory_group_vector_root='/synthetic/private/group-vectors',
            memory_group_vector_identity=identity_json)
        configuration = s.parse_configuration(source)
        identity_json['model_version'] = 'mutated-after-parse'
        self.assertEqual(configuration.memory_group_vector_identity[3], 'clip-v2')
        derived = s.parse_configuration(dict(source, memory_group_vector_root=base()['derived_root']))
        self.assertEqual(str(derived.memory_group_vector_root), base()['derived_root'])
        child = s.parse_configuration(dict(source, memory_group_vector_root=base()['derived_root']+'/qualified'))
        self.assertEqual(str(child.memory_group_vector_root), base()['derived_root']+'/qualified')
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            configuration.build_app()
        fields = runtime.call_args.kwargs
        self.assertIs(fields['memory_groups_enabled'], True)
        from app.access.memory_group_transport import GroupVectorConfiguration
        from app.access.visual_candidates import VectorSpaceIdentity
        profile = fields['memory_group_vectors']
        self.assertIs(type(profile), GroupVectorConfiguration)
        self.assertEqual(profile.vector_root, Path('/synthetic/private/group-vectors'))
        self.assertIs(type(profile.identity), VectorSpaceIdentity)
        self.assertEqual(profile.identity.artifact_sha256, 'a' * 64)
        self.assertEqual(profile.identity.preprocessing_sha256, 'b' * 64)
        self.assertEqual(profile.identity.vector_space_id, 'family-photo-v1')
        self.assertEqual(profile.identity.model_version, 'clip-v2')
        self.assertEqual(profile.identity.dimension, 768)
        self.assertEqual(profile.identity.normalization, 'unit_l2')

    def test_memory_group_vector_configuration_is_all_or_nothing_and_strictly_qualified(self):
        identity = {
            'artifact_sha256': 'a' * 64,
            'preprocessing_sha256': 'b' * 64,
            'vector_space_id': 'family-photo-v1',
            'model_version': 'clip-v2',
            'dimension': 768,
            'normalization': 'unit_l2',
        }
        invalid = [
            {'memory_groups_enabled': 'true'}, {'memory_groups_enabled': 1},
            {'memory_group_vector_root': '/synthetic/private/group-vectors'},
            {'memory_group_vector_identity': identity},
            {'memory_groups_enabled': False, 'memory_group_vector_root': '/synthetic/private/group-vectors',
             'memory_group_vector_identity': identity},
            {'memory_groups_enabled': True, 'memory_group_vector_root': 'relative/vectors',
             'memory_group_vector_identity': identity},
            {'memory_groups_enabled': True, 'memory_group_vector_root': '/synthetic/01_INCOMING/vectors',
             'memory_group_vector_identity': identity},
        ]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), **changes))

        for field, value in (
                ('artifact_sha256', 'A' * 64), ('preprocessing_sha256', 'x' * 64),
                ('vector_space_id', 'Uppercase'), ('model_version', ' model'),
                ('dimension', 0), ('dimension', 4097), ('dimension', True),
                ('normalization', 'l2')):
            bad = dict(identity, **{field: value})
            with self.subTest(field=field, value=value), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), memory_groups_enabled=True,
                    memory_group_vector_root='/synthetic/private/group-vectors',
                    memory_group_vector_identity=bad))
        for bad in ({**identity, 'extra': 'unexpected'},
                    {key: value for key, value in identity.items() if key != 'model_version'},
                    None, ['not', 'a', 'mapping']):
            with self.subTest(identity=bad), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), memory_groups_enabled=True,
                    memory_group_vector_root='/synthetic/private/group-vectors',
                    memory_group_vector_identity=bad))

    def test_title_configuration_is_independent_optional_and_passed_to_runtime(self):
        default = s.parse_configuration(base())
        self.assertFalse(default.story_title_suggestions_enabled)
        self.assertIsNone(default.story_title_url)
        enabled = s.parse_configuration(dict(base(), story_title_suggestions_enabled=True,
            story_title_url='http://127.0.0.1:19002', story_title_model='synthetic-titles',
            story_title_timeout_seconds=7))
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            enabled.build_app()
        fields = runtime.call_args.kwargs
        self.assertTrue(fields['story_title_suggestions_enabled'])
        self.assertEqual(fields['story_title_url'], 'http://127.0.0.1:19002')
        self.assertEqual(fields['story_title_model'], 'synthetic-titles')
        self.assertEqual(fields['story_title_timeout_seconds'], 7)
        for name in ('assistant_enabled', 'annotation_intake_enabled', 'memory_generation_enabled'):
            self.assertFalse(fields[name])
        # Opt-in alone is allowed for explicit later model projection; it exposes no provider.
        self.assertIsNone(s.parse_configuration(dict(base(), story_title_suggestions_enabled=True)).story_title_url)

    def test_title_configuration_refuses_partial_disabled_or_unbounded_settings(self):
        valid = dict(story_title_suggestions_enabled=True,
                     story_title_url='http://localhost:19002/api/generate', story_title_model='synthetic')
        invalid = [dict(story_title_suggestions_enabled=False),
                   dict(story_title_suggestions_enabled=1), dict(story_title_url=None),
                   dict(story_title_model=None), dict(story_title_model=' '),
                   dict(story_title_model=' synthetic'), dict(story_title_model='bad\nname')]
        invalid += [dict(story_title_timeout_seconds=t) for t in (0, True, 31, float('nan'), float('inf'), '30')]
        invalid += [dict(story_title_url=u) for u in ('https://localhost:19002',
            'http://192.0.2.1:19002', 'http://localhost:19002/other',
            'http://name:secret@localhost:19002', 'http://localhost:19002?token=secret',
            'http://localhost:19002#fragment', 5)]
        invalid.append(dict(story_title_token='secret'))
        for change in invalid:
            with self.subTest(change=change), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), **(valid | change)))

    def test_reviewed_editions_are_default_off_and_require_collaboration_and_journal(self):
        self.assertFalse(s.parse_configuration(base()).memory_editions_enabled)
        for flag in ('true', 1, None):
            with self.subTest(flag=flag), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), memory_editions_enabled=flag))
        with self.assertRaises(s.InvalidConfiguration):
            s.parse_configuration(dict(base(), memory_editions_enabled=True))
        with self.assertRaises(s.InvalidConfiguration):
            s.parse_configuration(dict(base(), memory_editions_enabled=True,
                                       memory_collaboration_enabled=True))
        selected = s.parse_configuration(dict(base(), memory_editions_enabled=True,
            memory_collaboration_enabled=True,
            original_deletion_journal_path='/synthetic/private/deletions.sqlite',
            original_deletion_namespace='00000000-0000-4000-8000-000000000001'))
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            selected.build_app()
        self.assertTrue(runtime.call_args.kwargs['memory_editions_enabled'])
        self.assertFalse(runtime.call_args.kwargs['memory_generation_enabled'])

    def test_family_note_erasure_false_key_remains_compatible_and_true_is_default_off(self):
        self.assertFalse(s.parse_configuration(base()).family_note_erasure_enabled)
        disabled = s.parse_configuration(dict(base(), family_note_erasure_enabled=False))
        self.assertFalse(disabled.family_note_erasure_enabled)
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            disabled.build_app()
        self.assertIs(runtime.call_args.kwargs['family_note_erasure_enabled'], False)
        for invalid in ('false', 0, None):
            with self.subTest(value=invalid), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), family_note_erasure_enabled=invalid))
        with self.assertRaises(s.InvalidConfiguration):
            s.parse_configuration(dict(base(), family_note_erasure_enabled=True))
        enabled = s.parse_configuration(dict(base(), family_note_erasure_enabled=True,
            original_deletion_journal_path='/synthetic/private/deletions.sqlite',
            original_deletion_namespace='00000000-0000-4000-8000-000000000001'))
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            enabled.build_app()
        self.assertIs(runtime.call_args.kwargs['family_note_erasure_enabled'], True)

    def test_assistant_journal_is_explicit_separate_and_passed_to_runtime(self):
        self.assertIsNone(s.parse_configuration(base()).assistant_journal_path)
        for path in ('relative.sqlite','/synthetic/01_INCOMING/log.sqlite',
                     '/synthetic/VLM_DATA/derived/log.sqlite','/synthetic/databases/metadata.sqlite',
                     '/synthetic/tls/server.key','/synthetic/updates/log.sqlite'):
            with self.subTest(path=path), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(),assistant_enabled=True,
                    assistant_journal_path=path,update_root='/synthetic/updates'))
        with self.assertRaises(s.InvalidConfiguration):
            s.parse_configuration(dict(base(),assistant_journal_path='/synthetic/private/journal.sqlite'))
        selected=s.parse_configuration(dict(base(),assistant_enabled=True,
            assistant_journal_path='/synthetic/private/journal.sqlite'))
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            selected.build_app()
        self.assertEqual(runtime.call_args.kwargs['assistant_journal_path'],Path('/synthetic/private/journal.sqlite'))

    def test_a_configuration_written_before_upload_still_loads(self):
        configuration = s.parse_configuration(base())
        self.assertIsNone(configuration.incoming_root)
        self.assertEqual(configuration.discovery_indexes, ())
        self.assertFalse(configuration.annotation_intake_enabled)
        self.assertEqual(configuration.original_roots, (Path('/synthetic/01_INCOMING'),))

    def test_discovery_paths_reach_runtime_only_when_explicitly_configured(self):
        path = Path('/synthetic/indexes/family.json')
        configuration = s.parse_configuration(dict(base(), discovery_indexes=[str(path)]))
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            app = configuration.build_app()
        self.assertEqual(runtime.call_args.kwargs['discovery_indexes'], (path,))
        self.assertIs(app, runtime.return_value.build_app.return_value)

    def test_discovery_artifacts_cannot_overlap_served_or_private_state(self):
        invalid = (None, 'file.json', ['/synthetic/index.json'] * 2,
                   [f'/synthetic/index-{n}.json' for n in range(9)],
                   ['relative.json'], ['/synthetic/01_INCOMING/index.json'],
                   ['/synthetic/VLM_DATA/derived/index.json'],
                   ['/synthetic/databases/metadata.sqlite'], ['/synthetic/tls/server.key'],
                   ['/synthetic/00_MEMBER_UPLOADS/index.json'])
        for indexes in invalid:
            with self.subTest(indexes=indexes), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), discovery_indexes=indexes,
                                           incoming_root='/synthetic/00_MEMBER_UPLOADS'))

    def test_the_incoming_root_is_optional_and_accepted_when_present(self):
        configuration = s.parse_configuration(dict(base(), incoming_root='/synthetic/00_MEMBER_UPLOADS'))
        self.assertEqual(configuration.incoming_root, Path('/synthetic/00_MEMBER_UPLOADS'))

    def test_an_incoming_root_overlapping_anything_the_service_owns_is_refused(self):
        """Overlapping a media root would put unaccepted bytes where the media routes serve."""
        for bad in ('/synthetic/01_INCOMING',
                    '/synthetic/01_INCOMING/_member_uploads',
                    '/synthetic/VLM_DATA/derived/incoming',
                    '/synthetic',
                    '/synthetic/databases/metadata.sqlite',
                    'relative/path',
                    '/synthetic/00_MEMBER_UPLOADS/'):
            with self.subTest(incoming_root=bad):
                with self.assertRaises(s.InvalidConfiguration):
                    s.parse_configuration(dict(base(), incoming_root=bad))

    def test_the_optional_field_does_not_loosen_the_accepted_set(self):
        for extra in ('surprise', 'incoming', 'upload_root'):
            with self.subTest(extra=extra):
                with self.assertRaises(s.InvalidConfiguration):
                    s.parse_configuration(dict(base(), **{extra: '/synthetic/x'}))

    def test_upload_review_opt_in_requires_an_incoming_root_and_one_original_root(self):
        invalid = (
            'true', 1, None,
        )
        for value in invalid:
            with self.subTest(upload_review_enabled=value), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), upload_review_enabled=value))
        with self.assertRaises(s.InvalidConfiguration):
            s.parse_configuration(dict(base(), upload_review_enabled=True,
                                       incoming_root=None))
        with self.assertRaises(s.InvalidConfiguration):
            s.parse_configuration(dict(base(), upload_review_enabled=True,
                                       incoming_root='/synthetic/00_MEMBER_UPLOADS',
                                       original_roots=['/synthetic/01_INCOMING',
                                                       '/synthetic/02_INCOMING']))

    def test_upload_review_defaults_false_and_is_preserved_when_disabled(self):
        self.assertFalse(s.parse_configuration(base()).upload_review_enabled)
        configuration = s.parse_configuration(dict(
            base(), incoming_root='/synthetic/00_MEMBER_UPLOADS', upload_review_enabled=False))
        self.assertFalse(configuration.upload_review_enabled)

    def test_annotation_intake_requires_explicit_boolean_opt_in(self):
        for value in ('true', 1, None):
            with self.subTest(value=value), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), annotation_intake_enabled=value))
        with self.assertRaises(s.InvalidConfiguration):
            s.parse_configuration(dict(base(), annotation_intake_enabled=True))
        enabled = s.parse_configuration(dict(base(), annotation_intake_enabled=True,
            original_deletion_journal_path='/synthetic/deletions.sqlite',
            original_deletion_namespace='00000000-0000-4000-8000-000000000001'))
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            enabled.build_app()
        self.assertIs(runtime.call_args.kwargs['annotation_intake_enabled'], True)

    def test_assistant_and_loopback_asr_require_separate_opt_in(self):
        self.assertFalse(s.parse_configuration(base()).assistant_enabled)
        for value in ('true', 1, None):
            with self.subTest(value=value), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), assistant_enabled=value))
        for changes in (
                {'assistant_asr_url': 'https://outside.test/transcribe', 'assistant_asr_model': 'x'},
                {'assistant_asr_url': 'http://127.0.0.1:8001/transcribe', 'assistant_asr_model': 'x'},
                {'assistant_enabled': True, 'assistant_asr_url': 'http://example.test/transcribe', 'assistant_asr_model': 'x'},
                {'assistant_enabled': True, 'assistant_asr_url': 'http://127.0.0.1:8001/transcribe'},
                {'assistant_enabled': True, 'assistant_asr_token': 'orphan'},
                {'assistant_tts_url': 'http://127.0.0.1:8001/tts'},
                {'assistant_enabled': True, 'assistant_tts_url': 'https://outside.test/tts'},
                {'assistant_enabled': True, 'assistant_tts_token': 'orphan'}):
            with self.subTest(changes=changes), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), **changes))
        enabled = s.parse_configuration(dict(base(), assistant_enabled=True,
            assistant_asr_url='http://127.0.0.1:8001/transcribe', assistant_asr_model='local-whisper',
            assistant_tts_url='http://127.0.0.1:8001/api/tts/synthesize'))
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            enabled.build_app()
        self.assertTrue(runtime.call_args.kwargs['assistant_enabled'])
        self.assertEqual(runtime.call_args.kwargs['assistant_asr_model'], 'local-whisper')
        self.assertEqual(runtime.call_args.kwargs['assistant_tts_url'], 'http://127.0.0.1:8001/api/tts/synthesize')

    def test_update_root_is_explicit_and_separate_from_protected_storage(self):
        self.assertIsNone(s.parse_configuration(base()).update_root)
        path = Path('/synthetic/updates')
        configuration = s.parse_configuration(dict(base(), update_root=str(path)))
        with patch('app.access.runtime.RuntimeConfiguration') as runtime:
            configuration.build_app()
        self.assertEqual(runtime.call_args.kwargs['update_root'], path)
        for invalid in ('relative', '/synthetic/01_INCOMING/updates',
                        '/synthetic/VLM_DATA/derived/updates', '/synthetic/databases',
                        '/synthetic/tls/server.key', '/synthetic/00_MEMBER_UPLOADS/updates'):
            with self.subTest(path=invalid), self.assertRaises(s.InvalidConfiguration):
                s.parse_configuration(dict(base(), incoming_root='/synthetic/00_MEMBER_UPLOADS',
                                           update_root=invalid))

    def test_the_required_fields_are_still_required(self):
        for missing in sorted(s.FIELDS):
            with self.subTest(missing=missing):
                value = base()
                value.pop(missing)
                with self.assertRaises(s.InvalidConfiguration):
                    s.parse_configuration(value)

    def test_the_pre_existing_overlap_rules_are_unchanged(self):
        for key, bad in (('derived_root', '/synthetic/01_INCOMING/derived'),
                         ('database', '/synthetic/01_INCOMING/metadata.sqlite'),
                         ('original_roots', ['/synthetic/VLM_DATA/derived'])):
            with self.subTest(key=key):
                with self.assertRaises(s.InvalidConfiguration):
                    s.parse_configuration(dict(base(), **{key: bad}))

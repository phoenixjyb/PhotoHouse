"""Private semantic runtime configuration stays explicit and fail closed."""
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'backend'), str(ROOT / 'tests/security')]

from app.access.semantic_configuration import (SemanticConfigurationError,
    _require_semantic_paths_disjoint, load_semantic_runtime)
from app.access.semantic_encoder import JointSpaceBinding, LocalSemanticEncoder
from app.access.discovery_transport import DiscoveryRuntime
from app.access.semantic_search import SemanticSearchRuntime
from app.access.visual_candidates import VectorSpaceIdentity
import test_visual_vector_loader as vector_fixtures


class SemanticConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='semantic-config-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.config_path = self.root / 'semantic.json'
        self.credential_path = self.root / 'credential.json'
        self.vector_root = self.root / 'vectors'
        self.vector_root.mkdir(mode=0o700)
        identity = vector_fixtures.IDENTITY
        text_identity = VectorSpaceIdentity('c' * 64, 'd' * 64, identity.vector_space_id,
                                             'text-v1', identity.dimension, 'unit_l2')
        self.binding = JointSpaceBinding(identity, text_identity, 'e' * 64)
        self.document = {
            'format_version': 1,
            'vector_root': str(self.vector_root),
            'encoder_url': 'http://127.0.0.1:43210/v1/encode-text',
            'encoder_timeout_seconds': 1.5,
            'credential_file': str(self.credential_path),
            'binding': {'image_identity': asdict(identity), 'text_identity': asdict(text_identity),
                        'qualification_sha256': 'e' * 64},
            'binding_sha256': self.binding.binding_sha256,
            'operator_reviewed': True,
        }

    def write(self, document=None):
        self.config_path.write_text(json.dumps(self.document if document is None else document), encoding='utf-8')
        self.config_path.chmod(0o600)
        return self.config_path

    def write_credential(self, token='a' * 40, document=None):
        selected = {'token': token} if document is None else document
        self.credential_path.write_text(json.dumps(selected), encoding='utf-8')
        self.credential_path.chmod(0o600)
        return self.credential_path

    def test_loader_requires_operator_review_pin_and_private_credential_reference(self):
        self.write()
        self.write_credential()
        discovery = DiscoveryRuntime.__new__(DiscoveryRuntime)
        runtime = load_semantic_runtime(self.config_path, discovery=discovery,
            source_root=ROOT.parent)
        self.assertIs(type(runtime), SemanticSearchRuntime)
        self.assertIs(runtime.discovery, discovery)
        self.assertEqual(runtime.encoder.binding.binding_sha256, self.binding.binding_sha256)
        self.assertEqual(runtime.encoder._bearer_token, 'a' * 40)

    def test_loader_refuses_missing_secret_malformed_pin_and_unreviewed_binding(self):
        self.write()
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)
        self.write_credential()
        for change in (
            {'binding_sha256': '0' * 64},
            {'operator_reviewed': False},
            {'unexpected': 'field'},
        ):
            doc = dict(self.document)
            doc.update(change)
            self.write(doc)
            with self.assertRaises(SemanticConfigurationError):
                load_semantic_runtime(self.config_path, discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)
        incomplete = dict(self.document)
        incomplete.pop('credential_file')
        self.write(incomplete)
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)

    def test_v2_requires_a_safe_owner_and_v1_cannot_configure_768_dimensions(self):
        self.write_credential()
        discovery = DiscoveryRuntime.__new__(DiscoveryRuntime)
        for bad_owner in (None, '', 'account/other', 'x' * 129, 7):
            document = self.document | {'format_version': 2, 'pilot_owner_account_id': bad_owner}
            self.write(document)
            with self.assertRaises(SemanticConfigurationError):
                load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)

        image_identity = replace(vector_fixtures.IDENTITY, dimension=768)
        text_identity = replace(self.binding.text_identity, dimension=768)
        binding = JointSpaceBinding(image_identity, text_identity, 'e' * 64)
        document = self.document | {'binding': {
            'image_identity': asdict(image_identity), 'text_identity': asdict(text_identity),
            'qualification_sha256': 'e' * 64}, 'binding_sha256': binding.binding_sha256}
        self.write(document)
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)

        document.update(format_version=2, pilot_owner_account_id='pilot-owner')
        self.write(document)
        runtime = load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)
        self.assertEqual(runtime.pilot_owner_account_id, 'pilot-owner')

    def test_v3_large_cohort_requires_closed_explicit_limits_and_retains_admission_pool(self):
        from app.access.discovery import ReadBudget
        self.write_credential()
        discovery = DiscoveryRuntime.__new__(DiscoveryRuntime)
        object.__setattr__(discovery, 'budget', ReadBudget(rows=100, seconds=1, concurrency=1))
        limits = {'candidate_limit': 30000, 'source_rows': 500000,
                  'source_bytes': 128 * 1024**2, 'search_seconds': 60}
        document = self.document | {'format_version': 3,
            'pilot_owner_account_id': 'pilot-owner', 'serving_limits': limits}
        self.write(document)
        runtime = load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)
        self.assertEqual(runtime.serving_limits.candidate_limit, 30000)
        self.assertIs(runtime.budget.slots, discovery.budget.slots)
        self.assertEqual(runtime.budget.rows, 500000)
        self.assertEqual(runtime.budget.search_source_bytes, 128 * 1024**2)
        self.assertEqual(runtime.budget.search_seconds, 60)
        self.assertEqual(discovery.budget.rows, 100)
        self.assertEqual(discovery.budget.seconds, 1)
        self.assertEqual(runtime.budget.response_bytes, discovery.budget.response_bytes)
        for invalid in (None, {}, {**limits, 'candidate_limit': True},
                        {**limits, 'candidate_limit': 100001},
                        {**limits, 'candidate_limit': 512},
                        {**limits, 'source_rows': 1000001},
                        {**limits, 'source_bytes': 256 * 1024**2 + 1},
                        {**limits, 'search_seconds': float('inf')},
                        {**limits, 'search_seconds': 121},
                        {**limits, 'search_seconds': True}, {**limits, 'unexpected': 1}):
            self.write({**document, 'serving_limits': invalid})
            with self.assertRaises(SemanticConfigurationError):
                load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)
        # Earlier versions cannot silently opt into a larger scope.
        self.write({**document, 'format_version': 2})
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)

    def test_direct_768_runtime_requires_owner_and_validates_owner_identifier(self):
        image_identity = replace(vector_fixtures.IDENTITY, dimension=768)
        text_identity = replace(self.binding.text_identity, dimension=768)
        binding = JointSpaceBinding(image_identity, text_identity, 'e' * 64)
        encoder = LocalSemanticEncoder(binding, 'http://127.0.0.1:43210/v1/encode-text')
        discovery = DiscoveryRuntime.__new__(DiscoveryRuntime)
        with self.assertRaises(ValueError):
            SemanticSearchRuntime(discovery, self.vector_root, encoder)
        for invalid in ('', 'pilot/owner', 'x' * 129):
            with self.assertRaises(ValueError):
                SemanticSearchRuntime(discovery, self.vector_root, encoder, invalid)
        runtime = SemanticSearchRuntime(discovery, self.vector_root, encoder, 'pilot.owner-1')
        self.assertEqual(runtime.pilot_owner_account_id, 'pilot.owner-1')

    def test_v5_eligibility_is_explicit_pinned_disjoint_and_not_read_before_authorization(self):
        from app.access.semantic_eligibility import SemanticEligibilityStore
        self.write_credential()
        discovery = DiscoveryRuntime.__new__(DiscoveryRuntime)
        policy_path = self.root / 'eligibility.json'
        document = self.document | {'format_version': 5, 'pilot_owner_account_id': 'pilot-owner',
            'serving_limits': {'candidate_limit': 30000, 'source_rows': 500000,
                              'source_bytes': 128 * 1024**2, 'search_seconds': 60},
            'bulk_vectors': {'path': str(self.root / 'bulk.phbv'), 'file_sha256': 'a' * 64,
                             'library_id': 'family-a'},
            'eligibility': {'path': str(policy_path), 'file_sha256': 'b' * 64}}
        self.write(document)
        with patch.object(SemanticEligibilityStore, 'read_and_validate',
                          side_effect=AssertionError('policy must be read only after owner authorization')):
            runtime = load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)
        self.assertEqual(runtime.eligibility.path, policy_path)
        self.assertEqual(runtime.eligibility.bulk_sha256, runtime.bulk_vectors.file_sha256)
        self.assertEqual(runtime.eligibility.binding_sha256, runtime.encoder.binding.binding_sha256)
        for invalid in (None, {}, {'path': str(policy_path), 'file_sha256': 'invalid'},
                        {'path': str(self.vector_root / 'policy.json'), 'file_sha256': 'b' * 64},
                        {'path': str(self.credential_path), 'file_sha256': 'b' * 64},
                        {'path': str(self.root / 'bulk.phbv'), 'file_sha256': 'b' * 64},
                        {'path': str(policy_path), 'file_sha256': 'b' * 64, 'unknown': True}):
            with self.subTest(invalid=invalid):
                self.write(document | {'eligibility': invalid})
                with self.assertRaises(SemanticConfigurationError):
                    load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)
        self.write(document)
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent,
                                 protected_paths=(policy_path,))
        for version in (1, 2, 3, 4):
            self.write(document | {'format_version': version})
            with self.assertRaises(SemanticConfigurationError):
                load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)

    def test_loader_refuses_bad_endpoint_token_and_partial_credential_document(self):
        self.write_credential(token='a' * 40)
        for change in ({'encoder_url': 'https://encoder.example.test/v1/encode-text'},):
            self.write(self.document | change)
            with self.assertRaises(SemanticConfigurationError):
                load_semantic_runtime(self.config_path, discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)
        self.write()
        self.write_credential(token='contains spaces')
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)
        self.write_credential(document={'token': 'a' * 40, 'extra': 'field'})
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)
        self.write_credential(document={'other': 'value'})
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)

    def test_vector_root_requires_private_existing_real_directory_outside_source(self):
        self.write()
        self.write_credential()
        discovery = DiscoveryRuntime.__new__(DiscoveryRuntime)
        self.vector_root.chmod(0o755)
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)

        self.vector_root.chmod(0o700)
        link = self.root / 'vector-link'
        link.symlink_to(self.vector_root, target_is_directory=True)
        self.write(self.document | {'vector_root': str(link)})
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)
        self.write(self.document | {'vector_root': str(ROOT.parent)})
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)
        self.write(self.document | {'vector_root': str(self.root / 'missing')})
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path, discovery=discovery, source_root=ROOT.parent)

    def test_overlap_checks_only_compare_semantic_paths_to_protected_paths(self):
        unrelated_existing_paths = (self.root / 'shared', self.root / 'shared' / 'nested')
        _require_semantic_paths_disjoint((self.config_path, self.credential_path, self.vector_root),
                                         unrelated_existing_paths)
        with self.assertRaises(SemanticConfigurationError):
            _require_semantic_paths_disjoint((self.vector_root,), (self.vector_root / 'nested',))

    def test_default_factory_does_not_load_or_read_semantic_configuration(self):
        from app.access.runtime import RuntimeConfiguration
        database = self.root / 'unused.sqlite'
        with patch('app.access.semantic_configuration._load_private_document',
                   side_effect=AssertionError('disabled semantic config must not load')):
            runtime = RuntimeConfiguration(database, 'https://photohouse.test',
                (self.root / 'originals',), self.root / 'derived').build_app()
        self.assertIsNone(runtime.state.semantic_search_runtime)
        self.assertFalse(runtime.state.assistant_semantic_search_enabled)

    def test_factory_refuses_partial_semantic_opt_in_before_private_reads(self):
        from app.access.runtime import RuntimeConfiguration
        base = RuntimeConfiguration(self.root / 'unused.sqlite', 'https://photohouse.test',
            (self.root / 'originals',), self.root / 'derived')
        for configured in (
            {'assistant_semantic_search_enabled': True},
            {'semantic_configuration_path': self.config_path},
            {'assistant_semantic_search_enabled': True, 'semantic_configuration_path': self.config_path},
        ):
            with self.subTest(configured=configured), \
                 patch('app.access.semantic_configuration._load_private_document',
                       side_effect=AssertionError('partial config must refuse before private reads')):
                with self.assertRaises(ValueError):
                    replace(base, **configured).build_app()

    def test_factory_uses_the_same_authenticated_discovery_runtime(self):
        from app.access.runtime import RuntimeConfiguration
        access, discovery = object(), object()
        semantic = SimpleNamespace(vector_root=self.vector_root)
        settings = RuntimeConfiguration(database=self.root / 'db.sqlite',
            web_origin='https://photohouse.test', original_roots=(self.root / 'originals',),
            derived_root=self.root / 'derived', discovery_indexes=(self.root / 'index',),
            assistant_enabled=True, assistant_workspace_path=self.root / 'workspace.sqlite',
            semantic_configuration_path=self.config_path,
            assistant_semantic_search_enabled=True)
        with patch('app.access.runtime.ExistingDatabase', return_value=object()), \
             patch('app.access.runtime.AccessRuntime', return_value=access), \
             patch('app.access.runtime.MediaRuntime', return_value=object()), \
             patch('app.access.discovery_index.runtime', return_value=discovery), \
             patch('app.access.assistant_workspace_store.AssistantWorkspaceStore', return_value=object()), \
             patch('app.access.semantic_configuration.load_semantic_runtime', return_value=semantic) as loader, \
             patch('app.main.create_app', return_value='app') as create_app:
            self.assertEqual(settings.build_app(), 'app')
        loader.assert_called_once()
        self.assertIs(loader.call_args.kwargs['discovery'], discovery)
        self.assertIn(settings.database, loader.call_args.kwargs['protected_paths'])
        self.assertIs(create_app.call_args.kwargs['discovery_runtime'], discovery)
        self.assertIs(create_app.call_args.kwargs['semantic_search_runtime'], semantic)
        self.assertTrue(create_app.call_args.kwargs['assistant_semantic_search_enabled'])

    def test_bulk_version_four_is_explicit_pinned_and_does_not_load_vectors(self):
        from app.access.semantic_bulk_vectors import BulkVectorStore
        self.write_credential()
        parent = self.root / 'bulk-serving'
        parent.mkdir(mode=0o700)
        bulk_path = parent / 'verified.phbv'
        document = self.document | {
            'format_version': 4, 'pilot_owner_account_id': 'pilot.owner-1',
            'serving_limits': {'candidate_limit': 100000, 'source_rows': 1000000,
                'source_bytes': 256 * 1024**2, 'search_seconds': 120.0},
            'bulk_vectors': {'path': str(bulk_path), 'file_sha256': 'f' * 64,
                             'library_id': 'family-test'}}
        self.write(document)
        with patch.object(BulkVectorStore, 'snapshot', side_effect=AssertionError('config must not load vectors')):
            runtime = load_semantic_runtime(self.config_path,
                discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)
        self.assertIs(type(runtime.bulk_vectors), BulkVectorStore)
        self.assertEqual(runtime.bulk_vectors.path, bulk_path)
        self.assertFalse(bulk_path.exists())
        self.assertEqual(runtime.bulk_vectors.identity, self.binding.image_identity)
        for field in ({'file_sha256': 'f' * 63}, {'library_id': '../other'},
                      {'path': str(self.vector_root / 'overlap.phbv')}, {'extra': True}):
            with self.subTest(field=field):
                self.write(document | {'bulk_vectors': document['bulk_vectors'] | field})
                with self.assertRaises(SemanticConfigurationError):
                    load_semantic_runtime(self.config_path,
                        discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)
        self.write(document | {'format_version': 3})
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path,
                discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent)
        self.write(document)
        with self.assertRaises(SemanticConfigurationError):
            load_semantic_runtime(self.config_path,
                discovery=DiscoveryRuntime.__new__(DiscoveryRuntime), source_root=ROOT.parent,
                protected_paths=(parent,))


if __name__ == '__main__':
    unittest.main()

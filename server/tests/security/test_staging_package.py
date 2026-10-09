"""Fixed source-selection and deterministic archive tests; no Git/network needed."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import build_staging_package as package


class StagingPackageTests(unittest.TestCase):
    def test_curated_runtime_dependency_and_contract_closure_is_allowlisted(self):
        required = {
            'backend/app/access/assistant_journal.py',
            'backend/app/access/captions.py',
            'backend/app/access/duplicates.py',
            'backend/app/access/family_note_deletions.py',
            'backend/app/access/family_note_identity.py',
            'backend/app/access/family_note_identity_schema.py',
            'backend/app/access/library_organization.py',
            'backend/app/access/memory_book_edition_contract.py',
            'backend/app/access/memory_book_edition_deletions.py',
            'backend/app/access/memory_book_edition_provenance.py',
            'backend/app/access/memory_book_edition_schema.py',
            'backend/app/access/memory_book_edition_sources.py',
            'backend/app/access/memory_book_edition_transport.py',
            'backend/app/access/memory_book_editions.py',
            'backend/app/access/memory_book_editorial.py',
            'backend/app/access/memory_book_editorial_contract.py',
            'backend/app/access/memory_book_editorial_deletions.py',
            'backend/app/access/memory_book_editorial_schema.py',
            'backend/app/access/memory_book_planning.py',
            'backend/app/access/memory_editorial_context.py',
            'backend/app/access/memory_processing.py',
            'backend/app/access/memory_schema.py',
            'backend/app/access/memory_source_refs.py',
            'backend/app/access/memory_stories.py',
            'backend/app/access/memory_transport.py',
            'backend/app/access/original_deletions.py',
            'backend/app/access/prepared_video.py',
            'backend/app/access/private_storage.py',
            'backend/app/access/model_deployment.py',
            'backend/app/access/model_binding.py',
            'backend/app/access/model_qualification.py',
            'backend/app/access/promotion.py',
            'backend/app/access/story_outline.py',
            'backend/app/access/story_titles.py',
            'backend/app/access/story_workspace.py',
            'backend/app/access/task_recovery.py',
            'backend/app/access/upload.py',
            'backend/app/access/upload_schema.py',
            'backend/app/access/upload_transport.py',
            'backend/app/access/windows_tts.py',
            'backend/app/home_catalog.py',
            'backend/app/ui/access/memory-community.js',
            'backend/app/ui/access/story-workspace.js',
            'backend/migrations/versions/a0c9d2e4f817_saved_story_contribution_refs.py',
            'backend/migrations/versions/b1d7e4a9c230_memory_book_editorial.py',
            'backend/migrations/versions/c2e6b8a1d490_reviewed_memoir_editions.py',
            'backend/migrations/versions/d1f6a8c3e920_family_note_identities.py',
            'backend/migrations/versions/c3f7a91d5e20_upload_auto_approval_policy.py',
            'backend/migrations/versions/d4a7e3c9b821_family_annotations.py',
            'backend/migrations/versions/e6b2f8a1c903_memory_stories.py',
            'backend/migrations/versions/f2a6d8b4c915_protected_upload.py',
            'backend/migrations/versions/f7c3a9d2e614_memory_collaboration.py',
            'docs/security/MEMOIR_EDITORIAL_SCHEMA_APPLICATION.md',
            'docs/security/REVIEWED_MEMOIR_EDITIONS_V1.md',
            'docs/security/FAMILY_NOTE_IDENTITIES_V1.md',
            'docs/security/FAMILY_NOTE_ERASURE_V2.md',
            'docs/security/ORIGINAL_JOURNAL_UPGRADE_V2.md',
            'scripts/apply_memory_collaboration_schema.py',
            'scripts/apply_memory_editorial_schema.py',
            'scripts/apply_memory_sources_schema.py',
            'scripts/home_memory_envelope.py',
            'scripts/initialize_original_deletions.py',
            'scripts/prepare_access_discovery_index.py',
            'scripts/replay_original_deletions.py',
            'scripts/upgrade_original_deletion_journal.py',
            'scripts/run_memory_worker.py',
            'scripts/serve_windows_tts.py',
            'backend/app/main.py',
            'backend/app/db.py',
            'backend/app/ui/photohouse-icon.svg',
            'backend/requirements-access.in',
            'backend/requirements-access.lock',
            'backend/requirements-access-test.in',
            'backend/requirements-access-test.lock',
            'backend/migrations/env.py',
            'backend/alembic.ini',
            'scripts/staging_app.py',
        }
        self.assertTrue(required <= set(package.FILES), required - set(package.FILES))

    def test_extracted_actual_api_imports_without_checkout_fallback(self):
        commit = package.git('rev-parse', 'HEAD').decode().strip()
        files = package.source_files(commit)
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected).resolve()
            with zipfile.ZipFile(io.BytesIO(package.package_bytes(commit, files))) as archive:
                archive.extractall(root)
            program = (
                'import sys\nfrom pathlib import Path\n'
                f'root=Path({str(root)!r})\n'
                "sys.path[:0]=[str(root/'scripts'),str(root/'backend')]\n"
                'from staging_app import load_configuration\n'
                'from app.access.runtime import RuntimeConfiguration\n'
                'from app.access.model_binding import project_configuration\n'
                'from app.access.model_deployment import validate_deployment\n'
                'from app.access.model_qualification import validate_qualification\n'
                'from app.main import create_app\n'
                'from app.access.story_titles import validate_bundle, validate_suggestions\n'
                'app=create_app()\nassert app.state.access_runtime is None\n'
                "for name,module in tuple(sys.modules.items()):\n"
                " if name=='app' or name.startswith('app.') or name=='staging_app':\n"
                "  origin=getattr(module,'__file__',None)\n"
                "  if origin: assert Path(origin).resolve().is_relative_to(root),(name,origin)\n"
                "  else:\n"
                "   paths=tuple(module.__path__);assert paths\n"
                "   assert all(Path(p).resolve().is_relative_to(root) for p in paths),(name,paths)\n"
                "print('isolated_extracted_api_import_passed')\n"
            )
            result = subprocess.run([sys.executable, '-I', '-B', '-c', program],
                                    cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), 'isolated_extracted_api_import_passed')

    def test_extracted_api_prepares_and_serves_synthetic_a0_without_migration_to_package_head(self):
        commit = package.git('rev-parse', 'HEAD').decode().strip()
        files = package.source_files(commit)
        with tempfile.TemporaryDirectory() as selected:
            root = Path(selected).resolve()
            with zipfile.ZipFile(io.BytesIO(package.package_bytes(commit, files))) as archive:
                archive.extractall(root)
            fixture = Path(__file__).resolve().with_name('package_smoke.py')
            result = subprocess.run([sys.executable, '-I', '-B', str(fixture), str(root)],
                                    cwd=root, capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['package_smoke'], 'pass')
            self.assertEqual(report['synthetic_migration_revision'], 'a0c9d2e4f817')
            self.assertFalse(report['application_listeners_opened'])
            self.assertFalse(report['live_data_accessed'])
            self.assertEqual(report['database_preparation_commands'], 9)
            self.assertEqual(report['saved_story_checks'], 7)

    def test_archive_is_deterministic_complete_and_contains_no_private_discovery(self):
        files={name:('synthetic source '+name).encode() for name in package.FILES}
        first=package.package_bytes('a'*40,files)
        self.assertEqual(first,package.package_bytes('a'*40,dict(reversed(list(files.items())))))
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertEqual(set(archive.namelist()),set(package.FILES)|{'manifest.json'})
            manifest=json.loads(archive.read('manifest.json'))
            self.assertFalse(manifest['dependencies_included'] or manifest['private_configuration_included'])
            for name in package.FILES:
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),manifest['files'][name])
            self.assertIn('backend/app/ui/photohouse-icon.svg',archive.namelist())
            self.assertEqual(manifest['migration_revision'], 'd1f6a8c3e920')
            self.assertIn('backend/migrations/versions/c3f7a91d5e20_upload_auto_approval_policy.py',
                          archive.namelist())
            for name in ('backend/app/tasks.py', 'backend/app/gps_utils.py',
                         'backend/app/ingest.py'):
                self.assertIn(name, archive.namelist())
            for name in ('backend/app/access/stories.py', 'backend/app/access/story_schema.py',
                         'backend/migrations/versions/c7f4a9e2b610_family_stories.py'):
                self.assertIn(name, archive.namelist())
            self.assertNotIn('backend/app/config.py',archive.namelist())
            self.assertNotIn('backend/app/legacy_main.py',archive.namelist())
            self.assertFalse(any(name.endswith(('.sqlite','.pem','.env','.pt')) for name in archive.namelist()))

    def test_extra_missing_or_traversal_files_are_refused(self):
        files={name:b'synthetic' for name in package.FILES}
        for changed in (files|{'../private.env':b'secret'}, files|{'.env':b'secret'}, {}):
            with self.assertRaises(ValueError): package.package_bytes('a'*40,changed)

    def test_moving_refs_missing_source_and_symlink_git_objects_are_refused(self):
        with patch.object(package,'git') as git:
            with self.assertRaises(ValueError): package.source_files('HEAD')
            git.assert_not_called()
        with patch.object(package,'git',side_effect=[b'commit\n',b'']):
            with self.assertRaises(ValueError): package.source_files('a'*40)
        with patch.object(package,'git',side_effect=[b'commit\n',
                b'120000 blob '+b'b'*40+b'\tserver/backend/app/main.py\0']):
            with self.assertRaises(ValueError): package.source_files('a'*40)


if __name__=='__main__': unittest.main()

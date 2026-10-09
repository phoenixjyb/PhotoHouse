#!/usr/bin/env python3
"""Build a source-only staging ZIP from an explicit immutable local Git commit.

Fixed file allowlist; no working-tree/config/data/venv discovery, dependency install,
network, extraction or deployment. The output hash must be reviewed separately.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
GIT_PREFIX = 'server/'
FILES = (
    'backend/alembic.ini',
    'backend/app/__init__.py',
    'backend/app/access/__init__.py',
    'backend/app/access/admission.py',
    'backend/app/access/albums.py',
    'backend/app/access/annotation_local.py',
    'backend/app/access/annotation_processing.py',
    'backend/app/access/annotation_schema.py',
    'backend/app/access/annotations.py',
    'backend/app/access/assistant.py',
    'backend/app/access/assistant_journal.py',
    'backend/app/access/assistant_speech.py',
    'backend/app/access/bootstrap.py',
    'backend/app/access/boundary.py',
    'backend/app/access/captions.py',
    'backend/app/access/credentials.py',
    'backend/app/access/date_hints.py',
    'backend/app/access/discovery.py',
    'backend/app/access/discovery_index.py',
    'backend/app/access/discovery_provider.py',
    'backend/app/access/discovery_transport.py',
    'backend/app/access/duplicates.py',
    'backend/app/access/face_jobs.py',
    'backend/app/access/library.py',
    'backend/app/access/library_organization.py',
    'backend/app/access/management_import.py',
    'backend/app/access/management_schema.py',
    'backend/app/access/media.py',
    'backend/app/access/members.py',
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
    'backend/app/access/memory_books.py',
    'backend/app/access/memory_collaboration_schema.py',
    'backend/app/access/memory_contributions.py',
    'backend/app/access/memory_editorial_context.py',
    'backend/app/access/memory_jobs.py',
    'backend/app/access/memory_narrative.py',
    'backend/app/access/memory_processing.py',
    'backend/app/access/memory_schema.py',
    'backend/app/access/memory_source_refs.py',
    'backend/app/access/memory_stories.py',
    'backend/app/access/memory_transport.py',
    'backend/app/access/metadata.py',
    'backend/app/access/original_deletions.py',
    'backend/app/access/owner_recovery.py',
    'backend/app/access/ownership_repair.py',
    'backend/app/access/people.py',
    'backend/app/access/prepared_video.py',
    'backend/app/access/private_storage.py',
    'backend/app/access/model_deployment.py',
    'backend/app/access/model_binding.py',
    'backend/app/access/promotion.py',
    'backend/app/access/provisioning.py',
    'backend/app/access/provisioning_apply.py',
    'backend/app/access/recovery.py',
    'backend/app/access/resumable.py',
    'backend/app/access/resumable_schema.py',
    'backend/app/access/runtime.py',
    'backend/app/access/schema.py',
    'backend/app/access/service.py',
    'backend/app/access/stories.py',
    'backend/app/access/story_outline.py',
    'backend/app/access/story_schema.py',
    'backend/app/access/story_titles.py',
    'backend/app/access/story_workspace.py',
    'backend/app/access/tags.py',
    'backend/app/access/task_recovery.py',
    'backend/app/access/transport.py',
    'backend/app/access/upload.py',
    'backend/app/access/upload_review.py',
    'backend/app/access/upload_schema.py',
    'backend/app/access/upload_transport.py',
    'backend/app/access/windows_tts.py',
    'backend/app/db.py',
    'backend/app/gps_utils.py',
    'backend/app/home_catalog.py',
    'backend/app/home_feed.py',
    'backend/app/ingest.py',
    'backend/app/main.py',
    'backend/app/photo_delivery.py',
    'backend/app/routers/ui.py',
    'backend/app/scoped_face_worker.py',
    'backend/app/tasks.py',
    'backend/app/ui/access/app.js',
    'backend/app/ui/access/index.html',
    'backend/app/ui/access/memory-community.js',
    'backend/app/ui/access/story-workspace.js',
    'backend/app/ui/access/styles.css',
    'backend/app/ui/photohouse-icon.svg',
    'backend/app/updates.py',
    'backend/migrations/env.py',
    'backend/migrations/versions/0001_initial.py',
    'backend/migrations/versions/402a07259e4a_sqlalchemy2_typing_refactor.py',
    'backend/migrations/versions/5b6b4d1c2a3f_task_progress_cancel.py',
    'backend/migrations/versions/6f2a8c1d9b7e_embedding_metadata.py',
    'backend/migrations/versions/7c1c2d4e5f6a_task_timing_columns.py',
    'backend/migrations/versions/8a2f1c3d4b5e_captions_multi_variants.py',
    'backend/migrations/versions/9b1e7d2a5c6f_caption_status_and_variant_meta.py',
    'backend/migrations/versions/a0c9d2e4f817_saved_story_contribution_refs.py',
    'backend/migrations/versions/a1c9d4e5f8b2_face_assignment_events.py',
    'backend/migrations/versions/a5d2e8f4b610_legacy_read_schema.py',
    'backend/migrations/versions/a8d4c2e6f901_resumable_uploads.py',
    'backend/migrations/versions/b1d7e4a9c230_memory_book_editorial.py',
    'backend/migrations/versions/b6e3f9a5c721_offline_receipts.py',
    'backend/migrations/versions/c2e6b8a1d490_reviewed_memoir_editions.py',
    'backend/migrations/versions/c3f7a91d5e20_upload_auto_approval_policy.py',
    'backend/migrations/versions/c4e7a2d9f1b3_versioned_face_embeddings.py',
    'backend/migrations/versions/c7f4a9e2b610_family_stories.py',
    'backend/migrations/versions/d2b7e4f6a901_album_drafts.py',
    'backend/migrations/versions/d4a7e3c9b821_family_annotations.py',
    'backend/migrations/versions/d8e5b2f7a904_library_management.py',
    'backend/migrations/versions/e3a9b1c7d402_access_foundation.py',
    'backend/migrations/versions/e6b2f8a1c903_memory_stories.py',
    'backend/migrations/versions/f2a6d8b4c915_protected_upload.py',
    'backend/migrations/versions/f4c1a8d2e703_access_admission.py',
    'backend/migrations/versions/f7c3a9d2e614_memory_collaboration.py',
    'backend/requirements-access-test.in',
    'backend/requirements-access-test.lock',
    'backend/requirements-access.in',
    'backend/requirements-access.lock',
    'backend/requirements-home-preparation.lock',
    'docs/security/MEMOIR_EDITORIAL_SCHEMA_APPLICATION.md',
    'docs/security/MEMORY_COMMUNITY_V1.md',
    'docs/security/REVIEWED_MEMOIR_EDITIONS_V1.md',
    'scripts/apply_access_schema.py',
    'scripts/apply_memory_collaboration_schema.py',
    'scripts/apply_memory_editorial_schema.py',
    'scripts/apply_memory_sources_schema.py',
    'scripts/home_media_worker.py',
    'scripts/home_memory_envelope.py',
    'scripts/home_preparation_resources.py',
    'scripts/initialize_original_deletions.py',
    'scripts/prepare_access_database.py',
    'scripts/prepare_access_discovery_index.py',
    'scripts/provision_access.py',
    'scripts/publish_android_update.py',
    'scripts/rehearse_fullsize_database.py',
    'scripts/replay_original_deletions.py',
    'scripts/run_memory_worker.py',
    'scripts/serve_windows_tts.py',
    'scripts/staging_app.py',
)


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,stderr=subprocess.DEVNULL)


def source_files(commit):
    if not re.fullmatch('[0-9a-f]{40}',commit) or git('cat-file','-t',commit).strip() != b'commit':
        raise ValueError('Explicit full commit required')
    records = git('ls-tree','-r','-z','--full-tree',commit,'--',*(GIT_PREFIX+name for name in FILES)).split(b'\0')
    entries = {}
    for record in filter(None,records):
        identity,name = record.split(b'\t',1)
        mode,kind,oid = identity.decode('ascii').split()
        if mode not in ('100644','100755') or kind != 'blob':
            raise ValueError('Only regular source blobs are allowed')
        path = name.decode('utf-8')
        if not path.startswith(GIT_PREFIX):
            raise ValueError('Selected source path escaped monorepo prefix')
        entries[path[len(GIT_PREFIX):]] = oid
    if set(entries) != set(FILES):
        raise ValueError('Selected commit lacks required source files')
    sizes = {name:int(git('cat-file','-s',oid)) for name,oid in entries.items()}
    if any(size > 2_000_000 for size in sizes.values()) or sum(sizes.values()) > 16_000_000:
        raise ValueError('Source package size exceeded')
    return {name:git('cat-file','blob',entries[name]) for name in FILES}


def package_bytes(commit, files):
    if set(files) != set(FILES):
        raise ValueError('Exact source allowlist required')
    manifest = {'format_version':1,'source_commit':commit,'artifact_kind':'source_only_not_deployed',
        'migration_revision':'c2e6b8a1d490','dependencies_included':False,'private_configuration_included':False,
        'files':{name:hashlib.sha256(files[name]).hexdigest() for name in FILES}}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_STORED) as archive:
        for name,data in [*sorted(files.items()),('manifest.json',(json.dumps(manifest,indent=2)+'\n').encode())]:
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.create_system=3; info.external_attr=0o100644 << 16
            archive.writestr(info,data)
    return output.getvalue()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit',required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:
        if (not args.out.is_absolute() or '..' in args.out.parts
                or args.out.parent.resolve(strict=True) != args.out.parent):
            raise ValueError('Explicit direct output required')
        data=package_bytes(args.commit,source_files(args.commit))
        flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)
        with os.fdopen(os.open(args.out,flags,0o600),'wb') as stream:
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
        print(json.dumps({'source_commit':args.commit,'source_files':len(FILES),
            'zip_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'deployed':False}))
        return 0
    except (ValueError,OSError,subprocess.CalledProcessError):
        print('Source packaging refused; no existing output was overwritten.')
        return 2


if __name__=='__main__':
    raise SystemExit(main())

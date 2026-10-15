#!/usr/bin/env python3
"""Run explicit API, memoir, Windows CPU, optional Web or Android checks."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

if __package__:
    from . import check_receipt
else:
    import check_receipt

ROOT = Path(__file__).resolve().parents[1]
API_TESTS = (
    "test_search_readiness.py", "test_search_evaluation.py", "test_private_search_cli.py",
    "test_assistant_query_plan.py", "test_search_text.py", "test_search_turn_projection.py",
    "test_kinship.py", "test_assistant_kinship.py",
    "test_closed_application.py", "test_access_foundation.py", "test_access_transport.py", "test_library_reads.py",
    "test_library_albums.py", "test_library_organization.py", "test_android_updates.py",
    "test_upload.py", "test_upload_annotations.py", "test_upload_auto_approval.py",
    "test_upload_history.py", "test_upload_retry.py", "test_upload_review.py",
    "test_original_deletions.py", "test_original_deletion_integration.py",
    "test_asset_tombstones.py",
    "test_family_note_identity.py", "test_family_note_identity_migration.py",
    "test_family_note_deletions.py", "test_family_note_deletion_boundaries.py",
    "test_family_note_erasure_api.py", "test_upgrade_original_deletion_journal.py",
    "test_private_storage.py", "test_model_deployment.py", "test_model_binding.py", "test_model_qualification.py", "test_model_topology.py", "test_apply_memory_editorial_schema.py",
    "test_oral_history_intake.py", "test_oral_history_withdrawal.py", "test_qualify_oral_history.py", "test_memory_contributions.py", "test_memory_contribution_refs.py", "test_memory_books.py",
    "test_memoir_quality_cases.py", "test_memoir_quality_canary.py",
    "test_memory_book_editorial_service.py", "test_memory_book_editorial_http.py",
    "test_memory_book_editorial_migration.py", "test_model_diagnostics.py",
    "test_memory_book_edition_contract.py", "test_memory_book_edition_schema.py",
    "test_memory_book_edition_provenance.py", "test_memory_book_editions.py",
    "test_memory_book_edition_deletions.py", "test_memory_book_edition_erasure.py",
    "test_memory_book_edition_http.py", "test_memory_book_edition_migration.py",
    "test_memory_book_edition_sources.py", "test_memory_book_edition_sources_http.py",
    "test_orm_migrations.py", "test_memory_groups_qualification.py",
    "test_apply_memory_group_schema.py", "test_memory_group_workers_qualification.py", "test_runtime_adapter.py", "test_windows_tts.py",
    "test_memory_worker_launcher.py",
    "test_memory_book_editorial_contract.py", "test_memory_book_editorial_schema.py", "test_memory_book_editorial_deletions.py", "test_memory_book_editorial_erasure.py",
    "test_memory_jobs.py", "test_memory_narrative.py", "test_story_workspace.py", "test_story_outline.py", "test_shared_memory_evidence.py", "test_chapter_source_policy.py", "test_story_related_media.py", "test_visual_candidates.py", "test_visual_vector_artifacts.py", "test_visual_vector_loader.py", "test_memory_grouping.py", "test_memory_groups.py", "test_memory_group_routes.py", "test_story_titles.py", "test_story_title_routes.py", "test_memory_processing.py",
    "test_memory_editorial_context.py", "test_memory_book_planning.py",
    "test_assistant_http.py", "test_assistant_conversational_search.py", "test_assistant_joint_search.py", "test_assistant_memory_discovery.py", "test_assistant_memory_intent.py", "test_assistant_memory_followup.py", "test_assistant_memory_reading_speech.py", "test_assistant_memory_segment_speech.py", "test_assistant_saved_memory_tool.py", "test_assistant_saved_memory_http.py", "test_assistant_saved_memory_reader.py", "test_assistant_workspace_http.py", "test_assistant_workspace_turn_http.py",
    "test_assistant_workspace_reply_speech.py", "test_assistant_memory_actions.py", "test_qualify_private_assistant.py",
    "test_assistant_journal.py", "test_assistant_asr_errors.py", "test_assistant_asset_number.py",
    "test_assistant_playback_receipts.py", "test_assistant_result_overview.py", "test_assistant_workspace_store.py", "test_assistant_workspace_turn_store.py",
    "test_prepare_assistant_workspace.py", "test_memory_transport.py",
    "test_approved_face_queue.py", "test_approved_worker_package.py",
    "test_approved_worker_failure_reports.py",
    "test_image_worker_claims.py", "test_visual_vector_publication.py", "test_visual_vector_cleanup.py",
    "test_visual_vector_erasure.py",
    "test_visual_vector_erasure_catalog.py", "test_vector_erasure_qualification.py",
    "test_image_embedding_receipts.py", "test_image_preprocessing_receipts.py",
    "test_visual_vector_worker.py", "test_immutable_image_worker.py",
    "test_approved_workers_c2_compatibility.py", "test_approved_workers_d1_compatibility.py", "test_approved_workers_e7_compatibility.py",
    "test_initialize_original_deletions.py",
    "test_staging_config.py", "test_staging_package.py",
    "test_database_preparation.py", "test_fullsize_preparation.py",
    "test_bad_video_recovery.py",
    "test_editorial_rehearsal_database_guard.py",
)
MEMORY_TESTS = (
    "test_private_storage.py", "test_oral_history_intake.py", "test_oral_history_withdrawal.py", "test_qualify_oral_history.py", "test_memory_contributions.py", "test_memory_contribution_refs.py",
    "test_memory_books.py", "test_memory_book_editorial_service.py", "test_memory_book_editorial_http.py",
    "test_family_note_identity.py", "test_family_note_identity_migration.py",
    "test_family_note_deletions.py", "test_family_note_deletion_boundaries.py",
    "test_family_note_erasure_api.py",
    "test_memory_book_editorial_deletions.py", "test_memory_book_editorial_erasure.py",
    "test_memory_book_edition_contract.py", "test_memory_book_edition_schema.py",
    "test_memory_book_edition_provenance.py", "test_memory_book_editions.py",
    "test_memory_book_edition_deletions.py", "test_memory_book_edition_erasure.py",
    "test_memory_book_edition_http.py", "test_memory_book_edition_migration.py",
    "test_memory_book_edition_sources.py", "test_memory_book_edition_sources_http.py",
    "test_memory_editorial_context.py", "test_memory_book_planning.py",
    "test_memory_jobs.py", "test_shared_memory_evidence.py", "test_chapter_source_policy.py", "test_memory_narrative.py", "test_memory_processing.py", "test_memory_transport.py",
)
WINDOWS_CPU_TESTS = (
    "test_database_preparation.py", "test_fullsize_preparation.py",
    "test_runtime_adapter.py", "test_staging_package.py",
    "test_approved_worker_package.py", "test_memory_groups_qualification.py",
    "test_apply_memory_group_schema.py", "test_memory_group_workers_qualification.py",
)
ANDROID_TASKS = (
    ":core:test", ":protocol:test", ":live-core:test", ":home-core:test",
    ":playback-core:test", ":story-fixture-core:test",
    ":connected:testDebugUnitTest", ":tv:testDebugUnitTest",
    ":connected:lintDebug", ":tv:lintDebug", ":connected:assembleDebug", ":tv:assembleDebug",
)
WEB_TESTS = (
    "server/tests/ui/voice-turn-timing.test.mjs",
    "server/tests/ui/assistant-private-workspace.test.mjs",
    "server/tests/security/test_assistant_workspace_browser.cjs",
    "server/tests/security/test_assistant_search_browser.cjs",
    "server/tests/security/test_assistant_saved_memory_browser.cjs",
    "server/tests/security/test_annotation_web_wav.cjs",
    "server/tests/security/test_assistant_pending_recovery_browser.cjs",
    "server/tests/security/test_assistant_turn_trail_browser.cjs",
    "server/tests/security/test_assistant_transcript_browser.cjs",
    "server/tests/security/test_assistant_capture_scope_browser.cjs",
    "server/tests/security/test_assistant_voice_session_browser.cjs",
    "server/tests/security/test_memory_book_editorial_browser.cjs",
    "server/tests/security/test_memory_book_editorial_reader_browser.cjs",
    "server/tests/security/test_memory_book_edition_browser.cjs",
    "server/tests/security/test_memory_book_edition_shelf_browser.cjs",
    "server/tests/security/test_memory_book_edition_sources_browser.cjs",
    "server/tests/security/test_memory_community_browser.cjs",
    "server/tests/security/test_memory_conversation_navigation_browser.cjs",
    "server/tests/security/test_story_titles_browser.cjs",
    "server/tests/security/test_story_related_media_browser.cjs",
    "server/tests/security/test_memory_groups_dom.cjs",
    "server/tests/security/test_memory_groups_browser.cjs",
    "server/tests/security/test_story_reader_frames_browser.cjs",
    "server/tests/security/test_upload_history_browser.cjs",
    "server/tests/security/test_story_workspace_browser.cjs",
    "server/tests/security/test_story_first_guide_browser.cjs",
    "server/tests/security/test_story_draft_store.cjs",
    "server/tests/security/test_story_draft_resume_browser.cjs",
)


def run(args, cwd=ROOT, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True)


def cpu_environment():
    """Give generated CPU checks platform basics, not live provider settings."""
    allowed = {
        "PATH", "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT",
        "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA",
        "USER", "USERNAME", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TZ",
    }
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(PHOTOHOUSE_NO_DOTENV="1", PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
               PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    return env


def api_tests(names, include_runtime_paths=False):
    paths = [ROOT / "server" / "tests" / "security" / name for name in names]
    if include_runtime_paths:
        paths.append(ROOT / "server" / "backend" / "tests" / "test_runtime_paths.py")
    if any(not path.is_file() for path in paths):
        raise SystemExit("The supported source export is incomplete")
    run([sys.executable, "-m", "pytest", "--noconftest", "-c", str(ROOT / "config" / "pytest.ini"),
        "-q", *map(str, paths)], cwd=ROOT / "server", env=cpu_environment())


def api():
    api_tests(API_TESTS, include_runtime_paths=True)
    run([sys.executable, "examples/generated-demo/check_demo.py"], env=cpu_environment())


def windows_cpu():
    """Generated database/runtime/package contracts, without installed services."""
    api_tests(WINDOWS_CPU_TESTS)


def memory():
    api_tests(MEMORY_TESTS)


def android_command(project, platform):
    """Build the platform wrapper command without starting Gradle."""
    if platform == "win32":
        wrapper = "gradlew.bat"
        command = ["cmd.exe", "/d", "/c", wrapper]
    else:
        wrapper = "gradlew"
        command = ["sh", wrapper]
    if not (project / wrapper).is_file():
        raise SystemExit(f"The Android source export is missing {wrapper}")
    return [*command, "--no-daemon", "--console=plain", *ANDROID_TASKS]


def android():
    project = ROOT / "clients" / "android" / "android"
    # No origin, device, release signer or deployment settings are supplied.
    run(android_command(project, sys.platform), cwd=project)


def web():
    paths = [ROOT / relative for relative in WEB_TESTS]
    missing = [relative for relative, path in zip(WEB_TESTS, paths) if not path.is_file()]
    if missing:
        raise SystemExit("Web profile unavailable; missing generated-data suite(s): " + ", ".join(missing))

    node = shutil.which("node")
    if not node:
        raise SystemExit("Web profile requires an existing Node.js executable; no install attempted")

    # Browser bridges use the same generated CPU boundary. Preserve only the
    # caller's explicit existing toolchain and artifact locations, not provider,
    # database, Python plugin or Node preload settings from an operator shell.
    env = cpu_environment()
    for key in ("PLAYWRIGHT_MODULE", "PLAYWRIGHT_MODULE_PATH", "PLAYWRIGHT_BROWSERS_PATH",
                "PH_BROWSER_PYTHON", "PH_BROWSER_EXECUTABLE", "PH_BROWSER_ARTIFACTS", "NODE_PATH"):
        if key in os.environ:
            env[key] = os.environ[key]
    module = env.get("PLAYWRIGHT_MODULE")
    module_path = env.get("PLAYWRIGHT_MODULE_PATH")
    if module and module_path and module != module_path:
        raise SystemExit("Web profile refused conflicting PLAYWRIGHT_MODULE and PLAYWRIGHT_MODULE_PATH")
    module = module or module_path
    if module:
        # The generated suites share both conventions; pass the caller's
        # existing module choice to each without installing or resolving one.
        env["PLAYWRIGHT_MODULE"] = module
        env["PLAYWRIGHT_MODULE_PATH"] = module
    env["PH_BROWSER_PYTHON"] = env.get("PH_BROWSER_PYTHON") or sys.executable

    for path in paths:
        suite_env = env.copy()
        if env.get("PH_BROWSER_ARTIFACTS"):
            # Suites use common result filenames. Give each its own directory
            # so a later journey cannot replace an earlier acceptance record.
            suite_env["PH_BROWSER_ARTIFACTS"] = str(
                Path(env["PH_BROWSER_ARTIFACTS"]) / path.stem
            )
        run([node, str(path)], env=suite_env)


def dispatch(profile):
    if profile in ("api", "all"):
        api()
    if profile == "memory":
        memory()
    if profile in ("android", "all"):
        android()
    if profile == "web":
        web()
    if profile == "windows-cpu":
        windows_cpu()


def _exit_code(error):
    if isinstance(error, subprocess.CalledProcessError):
        return int(error.returncode)
    if isinstance(error, KeyboardInterrupt):
        return 130
    if isinstance(error, SystemExit):
        return error.code if type(error.code) is int else (0 if error.code is None else 1)
    return 1


def _with_receipt(profile, output):
    try:
        destination = check_receipt.preflight_destination(output, ROOT)
    except check_receipt.ReceiptError as error:
        print(f"check receipt refused: {error}", file=sys.stderr)
        return 2
    profiles = check_receipt.expanded_profiles(profile)
    started = check_receipt.utc_now()
    start_identity = check_receipt.source_identity(ROOT, profiles, destination)
    failure = None
    try:
        dispatch(profile)
    except BaseException as error:
        failure = error
        if isinstance(error, SystemExit) and isinstance(error.code, str):
            print(error.code, file=sys.stderr)
    end_identity = check_receipt.source_identity(ROOT, profiles, destination)
    receipt = check_receipt.make_receipt(profile, profiles, started, check_receipt.utc_now(),
                                         start_identity, end_identity,
                                         _exit_code(failure) if failure is not None else 0)
    try:
        check_receipt.write_receipt(destination, receipt)
    except check_receipt.ReceiptError as error:
        print(f"check receipt write failed: {error}", file=sys.stderr)
        if isinstance(failure, (subprocess.CalledProcessError, SystemExit, KeyboardInterrupt)):
            return _exit_code(failure)
        if failure is not None:
            raise failure
        return 2
    if failure is not None and not isinstance(failure, (subprocess.CalledProcessError, SystemExit, KeyboardInterrupt)):
        raise failure
    return _exit_code(failure) if failure is not None else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("api", "memory", "windows-cpu", "android", "web", "all"))
    parser.add_argument("--receipt", type=Path,
                        help="write a private local check-invocation receipt to a new JSON file")
    args = parser.parse_args(argv)
    if args.receipt is not None:
        return _with_receipt(args.profile, args.receipt)
    dispatch(args.profile)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

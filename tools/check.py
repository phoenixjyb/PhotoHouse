#!/usr/bin/env python3
"""Run explicit API, memoir, optional Web browser, or Android development checks."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
API_TESTS = (
    "test_closed_application.py", "test_access_foundation.py", "test_access_transport.py", "test_library_reads.py",
    "test_library_albums.py", "test_library_organization.py", "test_android_updates.py",
    "test_upload.py", "test_upload_annotations.py", "test_upload_auto_approval.py",
    "test_upload_history.py", "test_upload_retry.py", "test_upload_review.py",
    "test_original_deletions.py", "test_original_deletion_integration.py",
    "test_private_storage.py", "test_apply_memory_editorial_schema.py",
    "test_memory_contributions.py", "test_memory_contribution_refs.py", "test_memory_books.py",
    "test_memoir_quality_cases.py",
    "test_memory_book_editorial_service.py", "test_memory_book_editorial_http.py",
    "test_memory_book_editorial_migration.py", "test_model_diagnostics.py",
    "test_memory_book_edition_contract.py", "test_memory_book_edition_schema.py",
    "test_memory_book_edition_provenance.py", "test_memory_book_editions.py",
    "test_memory_book_edition_deletions.py", "test_memory_book_edition_erasure.py",
    "test_memory_book_edition_http.py", "test_memory_book_edition_migration.py",
    "test_memory_book_edition_sources.py", "test_memory_book_edition_sources_http.py",
    "test_orm_migrations.py", "test_runtime_adapter.py", "test_windows_tts.py",
    "test_memory_worker_launcher.py",
    "test_memory_book_editorial_contract.py", "test_memory_book_editorial_schema.py", "test_memory_book_editorial_deletions.py", "test_memory_book_editorial_erasure.py",
    "test_memory_jobs.py", "test_memory_narrative.py", "test_story_workspace.py", "test_story_related_media.py", "test_story_titles.py", "test_story_title_routes.py", "test_memory_processing.py",
    "test_memory_editorial_context.py", "test_memory_book_planning.py",
    "test_assistant_http.py", "test_assistant_journal.py", "test_memory_transport.py",
    "test_approved_face_queue.py", "test_approved_worker_package.py",
    "test_approved_workers_c2_compatibility.py", "test_initialize_original_deletions.py",
    "test_staging_config.py", "test_staging_package.py",
    "test_editorial_rehearsal_database_guard.py",
)
MEMORY_TESTS = (
    "test_private_storage.py", "test_memory_contributions.py", "test_memory_contribution_refs.py",
    "test_memory_books.py", "test_memory_book_editorial_service.py", "test_memory_book_editorial_http.py",
    "test_memory_book_editorial_deletions.py", "test_memory_book_editorial_erasure.py",
    "test_memory_book_edition_contract.py", "test_memory_book_edition_schema.py",
    "test_memory_book_edition_provenance.py", "test_memory_book_editions.py",
    "test_memory_book_edition_deletions.py", "test_memory_book_edition_erasure.py",
    "test_memory_book_edition_http.py", "test_memory_book_edition_migration.py",
    "test_memory_book_edition_sources.py", "test_memory_book_edition_sources_http.py",
    "test_memory_editorial_context.py", "test_memory_book_planning.py",
    "test_memory_jobs.py", "test_memory_narrative.py", "test_memory_processing.py", "test_memory_transport.py",
)
ANDROID_TASKS = (
    ":core:test", ":protocol:test", ":live-core:test", ":home-core:test",
    ":playback-core:test", ":story-fixture-core:test",
    ":connected:testDebugUnitTest", ":tv:testDebugUnitTest",
    ":connected:lintDebug", ":tv:lintDebug", ":connected:assembleDebug", ":tv:assembleDebug",
)
WEB_TESTS = (
    "server/tests/security/test_assistant_pending_recovery_browser.cjs",
    "server/tests/security/test_memory_book_editorial_browser.cjs",
    "server/tests/security/test_memory_book_editorial_reader_browser.cjs",
    "server/tests/security/test_memory_book_edition_browser.cjs",
    "server/tests/security/test_memory_book_edition_shelf_browser.cjs",
    "server/tests/security/test_memory_book_edition_sources_browser.cjs",
    "server/tests/security/test_memory_community_browser.cjs",
    "server/tests/security/test_story_titles_browser.cjs",
    "server/tests/security/test_story_related_media_browser.cjs",
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

    env = os.environ.copy()
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
        run([node, str(path)], env=env)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("api", "memory", "android", "web", "all"))
    choice = parser.parse_args().profile
    if choice in ("api", "all"):
        api()
    if choice == "memory":
        memory()
    if choice in ("android", "all"):
        android()
    if choice == "web":
        web()

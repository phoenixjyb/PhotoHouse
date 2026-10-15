from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest import mock

from tools import check, check_receipt


class CheckReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self._write("tools/check.py", b"check script\n")
        self._write("tools/check_receipt.py", b"receipt helper\n")
        self._write("server/backend/app.py", b"backend source v1\n")
        self._write("server/tests/security/test_example.py", b"test source\n")
        self._write("server/tests/security/browser-tooling/package-lock.json", b"{\"lockfileVersion\": 3}\n")
        self._write("config/pytest.ini", b"[pytest]\n")
        self._write("examples/generated-demo/check_demo.py", b"demo\n")
        self._write("clients/android/android/settings.gradle", b"rootProject.name = 'fixture'\n")
        self._write("clients/android/contracts/v1/manifest.json", b"{\"version\": 1}\n")
        self._write("docs/ROADMAP.md", b"fixture roadmap\n")
        self._git("init", "-q")
        self._git("add", "--all")
        self._git("-c", "user.name=Receipt Test", "-c", "user.email=receipt@example.invalid",
                  "commit", "-q", "-m", "initial")

    def tearDown(self):
        self.temporary.cleanup()

    def _write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout.decode().strip()

    def _main(self, argv):
        with mock.patch.object(check, "ROOT", self.root):
            return check.main(argv)

    def test_optional_stable_receipt_is_private_and_contains_no_execution_output(self):
        destination = self.root / "local-check.json"
        output = io.StringIO()
        with mock.patch.object(check, "api", side_effect=lambda: print("private raw test output")), \
                redirect_stdout(output):
            status = self._main(["api", "--receipt", str(destination)])
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue(), "private raw test output\n")
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(receipt["profile"], "api")
        self.assertEqual(receipt["expanded_profiles"], ["api"])
        self.assertEqual(receipt["head_start"], receipt["head_end"])
        self.assertEqual(receipt["source_sha256_start"], receipt["source_sha256_end"])
        self.assertEqual(receipt["source_identity"], "available")
        self.assertTrue(receipt["source_unchanged"])
        self.assertEqual(receipt["exit_code"], 0)
        self.assertNotIn("private raw test output", destination.read_text(encoding="utf-8"))
        self.assertNotIn("DATABASE_URL", destination.read_text(encoding="utf-8"))
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

    def test_tracked_and_untracked_source_changes_during_run_unbind_receipt(self):
        destination = self.root / "local-check.json"

        def mutate_sources():
            self._write("server/backend/app.py", b"backend source changed\n")
            self._write("server/tests/security/new_case.py", b"new untracked test\n")

        with mock.patch.object(check, "memory", side_effect=mutate_sources):
            status = self._main(["memory", "--receipt", str(destination)])
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertNotEqual(receipt["source_sha256_start"], receipt["source_sha256_end"])
        self.assertFalse(receipt["source_unchanged"])

    def test_deleted_profile_source_makes_end_identity_unavailable(self):
        destination = self.root / "deleted-source.json"

        def delete_source():
            (self.root / "server/backend/app.py").unlink()

        with mock.patch.object(check, "memory", side_effect=delete_source):
            status = self._main(["memory", "--receipt", str(destination)])
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertEqual(receipt["source_identity"], "unavailable")
        self.assertIsNone(receipt["source_sha256_end"])
        self.assertEqual(receipt["source_identity_reason_end"], "source_unreadable")
        self.assertFalse(receipt["source_unchanged"])

    def test_profile_file_mode_change_unbinds_receipt(self):
        destination = self.root / "mode-change.json"
        source = self.root / "server/backend/app.py"
        initial_mode = stat.S_IMODE(source.stat().st_mode)
        source.chmod(initial_mode ^ stat.S_IXUSR)
        mode_change_supported = stat.S_IMODE(source.stat().st_mode) != initial_mode
        source.chmod(initial_mode)
        if not mode_change_supported:
            self.skipTest("filesystem does not preserve executable mode changes")

        def change_mode():
            before = stat.S_IMODE(source.stat().st_mode)
            source.chmod(before ^ stat.S_IXUSR)

        with mock.patch.object(check, "memory", side_effect=change_mode):
            status = self._main(["memory", "--receipt", str(destination)])
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertNotEqual(receipt["source_sha256_start"], receipt["source_sha256_end"])
        self.assertFalse(receipt["source_unchanged"])

    def test_out_of_profile_android_mutation_does_not_change_memory_identity(self):
        destination = self.root / "unrelated-profile.json"

        def add_android_source():
            self._write("clients/android/android/settings.gradle", b"settings changed\n")

        with mock.patch.object(check, "memory", side_effect=add_android_source):
            status = self._main(["memory", "--receipt", str(destination)])
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertEqual(receipt["source_sha256_start"], receipt["source_sha256_end"])
        self.assertTrue(receipt["source_unchanged"])

    def test_web_profile_covers_browser_dependency_lockfile(self):
        destination = self.root / "web-lock.json"
        lockfile = self.root / "server/tests/security/browser-tooling/package-lock.json"

        def update_lockfile():
            lockfile.write_bytes(b"{\"lockfileVersion\": 3, \"packages\": {}}\n")

        with mock.patch.object(check, "web", side_effect=update_lockfile):
            status = self._main(["web", "--receipt", str(destination)])
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertNotEqual(receipt["source_sha256_start"], receipt["source_sha256_end"])
        self.assertFalse(receipt["source_unchanged"])

    def test_android_profile_covers_shared_contract_resources(self):
        destination = self.root / "android-contract.json"
        contract = self.root / "clients/android/contracts/v1/manifest.json"

        def update_contract():
            contract.write_bytes(b"{\"version\": 1, \"fixture\": \"changed\"}\n")

        with mock.patch.object(check, "android", side_effect=update_contract):
            status = self._main(["android", "--receipt", str(destination)])
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertNotEqual(receipt["source_sha256_start"], receipt["source_sha256_end"])
        self.assertFalse(receipt["source_unchanged"])

    def test_android_profile_excludes_unrelated_documentation(self):
        destination = self.root / "android-docs.json"

        def update_unrelated_docs():
            (self.root / "docs/ROADMAP.md").write_bytes(b"unrelated documentation changed\n")

        with mock.patch.object(check, "android", side_effect=update_unrelated_docs):
            status = self._main(["android", "--receipt", str(destination)])
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertEqual(receipt["source_sha256_start"], receipt["source_sha256_end"])
        self.assertTrue(receipt["source_unchanged"])

    def test_head_change_during_run_is_detected_even_if_profile_is_recorded(self):
        destination = self.root / "head-change.json"

        def commit_source_change():
            self._write("server/backend/app.py", b"committed source change\n")
            self._git("add", "server/backend/app.py")
            self._git("-c", "user.name=Receipt Test", "-c", "user.email=receipt@example.invalid",
                      "commit", "-q", "-m", "changed")

        with mock.patch.object(check, "android", side_effect=commit_source_change):
            status = self._main(["android", "--receipt", str(destination)])
        receipt = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(status, 0)
        self.assertNotEqual(receipt["head_start"], receipt["head_end"])
        self.assertFalse(receipt["source_unchanged"])

    def test_all_receipt_records_current_cli_expansion(self):
        destination = self.root / "all.json"
        with mock.patch.object(check, "api"), mock.patch.object(check, "android"):
            status = self._main(["all", "--receipt", str(destination)])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(destination.read_text())["expanded_profiles"], ["api", "android"])

    def test_command_failure_exit_is_recorded_and_preserved(self):
        destination = self.root / "failed.json"
        output = io.StringIO()
        with mock.patch.object(check, "windows_cpu", side_effect=subprocess.CalledProcessError(17, "pytest")), \
                redirect_stdout(output):
            status = self._main(["windows-cpu", "--receipt", str(destination)])
        self.assertEqual(status, 17)
        self.assertEqual(output.getvalue(), "")
        receipt = json.loads(destination.read_text())
        self.assertEqual(receipt["exit_code"], 17)
        self.assertTrue(receipt["source_unchanged"])

    def test_existing_receipt_path_is_refused_before_running_profile(self):
        destination = self.root / "already-there.json"
        destination.write_text("keep", encoding="utf-8")
        errors = io.StringIO()
        with mock.patch.object(check, "api") as api, redirect_stderr(errors):
            status = self._main(["api", "--receipt", str(destination)])
        self.assertEqual(status, 2)
        api.assert_not_called()
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep")
        self.assertIn("destination_exists", errors.getvalue())

    def test_deleted_tracked_source_cannot_be_reused_as_receipt_destination(self):
        source = self.root / "server/backend/app.py"
        source.unlink()
        with self.assertRaisesRegex(check_receipt.ReceiptError, "destination_tracks_source"):
            check_receipt.preflight_destination(source, self.root)

    def test_receipt_write_failure_is_reported_without_masking_check_failure(self):
        destination = self.root / "failed-receipt.json"
        errors = io.StringIO()
        with mock.patch.object(check, "memory", side_effect=subprocess.CalledProcessError(17, "pytest")), \
                mock.patch.object(check_receipt, "write_receipt",
                                  side_effect=check_receipt.ReceiptError("receipt_write_failed")), \
                redirect_stderr(errors):
            status = self._main(["memory", "--receipt", str(destination)])
        self.assertEqual(status, 17)
        self.assertIn("check receipt write failed: receipt_write_failed", errors.getvalue())
        self.assertFalse(destination.exists())

    def test_receipt_publication_falls_back_when_platform_lacks_posix_flags(self):
        destination = self.root / "portable-receipt.json"
        real_link = os.link
        calls = 0

        def portable_link(source, target, **kwargs):
            nonlocal calls
            calls += 1
            if kwargs:
                raise TypeError("follow_symlinks is unsupported")
            return real_link(source, target)

        with mock.patch.object(check_receipt.os, "fchmod", side_effect=NotImplementedError), \
                mock.patch.object(check_receipt.os, "link", side_effect=portable_link):
            check_receipt.write_receipt(destination, {"schema": 1})
        self.assertEqual(calls, 2)
        self.assertEqual(json.loads(destination.read_text(encoding="utf-8")), {"schema": 1})

    def test_identity_unavailable_never_claims_unchanged(self):
        not_git = self.root.parent / (self.root.name + "-not-git")
        not_git.mkdir()
        try:
            identity = check_receipt.source_identity(not_git, ("memory",))
            receipt = check_receipt.make_receipt("memory", ("memory",), "start", "end", identity,
                                                 identity, 0)
            self.assertIsNone(identity["head"])
            self.assertIsNone(identity["source_sha256"])
            self.assertFalse(receipt["source_unchanged"])
            self.assertEqual(receipt["source_identity"], "unavailable")
        finally:
            not_git.rmdir()

    def test_profile_input_symlink_makes_identity_unavailable(self):
        target = self.root / "server/backend/linked.py"
        outside = self.root / "outside.py"
        outside.write_text("outside", encoding="utf-8")
        target.symlink_to(outside)
        identity = check_receipt.source_identity(self.root, ("memory",))
        self.assertIsNone(identity["source_sha256"])
        self.assertEqual(identity["reason"], "source_symlink_refused")

    def test_legacy_invocation_without_receipt_keeps_dispatch_only(self):
        with mock.patch.object(check, "api") as api:
            self.assertEqual(self._main(["api"]), 0)
        api.assert_called_once_with()
        self.assertFalse(list(self.root.glob("*.json")))


if __name__ == "__main__":
    unittest.main()

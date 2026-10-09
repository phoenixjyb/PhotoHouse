"""Fixture-only tests for the clean tracked-source ZIP packager."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import stat
import tempfile
import warnings
import unittest
import zipfile
from unittest import mock

from tools import package_source


class PackageSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        self._git("init", "-q")
        self._git("config", "user.email", "fixture@example.invalid")
        self._git("config", "user.name", "Fixture")
        (self.root / "README.md").write_text("tracked source\n", encoding="utf-8")
        self._commit()
        self.output = self.base / "packages" / "candidate"
        self.output.parent.mkdir()
        self.verify_calls = []

    def tearDown(self):
        self.temp.cleanup()

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout

    def _commit(self):
        self._git("add", "--all")
        self._git("commit", "-qm", "fixture")

    def _verify(self, root):
        self.verify_calls.append(root)
        return {"status": "verified", "current_files_verified": 1}

    def _package(self):
        return package_source.package_source(self.root, self.output, _verifier=self._verify)

    def test_clean_tree_produces_exact_tracked_archive_and_receipt(self):
        report = self._package()
        self.assertEqual(self.verify_calls, [self.root.resolve()])
        self.assertEqual(report["status"], "verified")
        self.assertEqual(report["head"], self._git("rev-parse", "HEAD").decode().strip())
        self.assertEqual(report["tracked_file_count"], 1)
        self.assertTrue((self.output / "source.zip").is_file())
        receipt = json.loads((self.output / "verification.json").read_text(encoding="utf-8"))
        self.assertEqual(receipt["archive_sha256"], report["archive_sha256"])
        with zipfile.ZipFile(self.output / "source.zip") as archive:
            self.assertEqual(archive.namelist(), ["README.md"])
            self.assertEqual(archive.read("README.md"), b"tracked source\n")
            self.assertIsNone(archive.testzip())

    def test_executable_git_mode_is_preserved_in_zip(self):
        script = self.root / "run.sh"
        script.write_bytes(b"#!/bin/sh\nexit 0\n")
        script.chmod(0o755)
        self._commit()
        self._package()
        with zipfile.ZipFile(self.output / "source.zip") as archive:
            mode = archive.getinfo("run.sh").external_attr >> 16
        self.assertEqual(stat.S_IFMT(mode), stat.S_IFREG)
        self.assertEqual(stat.S_IMODE(mode), 0o755)

    def test_dirty_tree_is_refused_without_output(self):
        (self.root / "README.md").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(package_source.PackageError, "dirty_worktree"):
            self._package()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.verify_calls, [])

    def test_output_inside_repository_is_refused(self):
        (self.root / "packages").mkdir()
        output = self.root / "packages" / "out"
        with self.assertRaisesRegex(package_source.PackageError, "output_inside_repository"):
            package_source.package_source(self.root, output, _verifier=self._verify)
        self.assertFalse(output.exists())

    def test_existing_output_directory_is_refused_unchanged(self):
        self.output.mkdir()
        marker = self.output / "owner.txt"
        marker.write_text("pre-existing\n", encoding="utf-8")
        with self.assertRaisesRegex(package_source.PackageError, "output_must_be_absent"):
            self._package()
        self.assertEqual(marker.read_text(encoding="utf-8"), "pre-existing\n")
        self.assertFalse((self.output / "source.zip").exists())

    def test_output_created_at_publication_race_is_preserved(self):
        publish = package_source._publish_output

        def race(source_archive, target, report):
            target.mkdir()
            marker = target / "created-by-other-actor.txt"
            marker.write_text("keep\n", encoding="utf-8")
            return publish(source_archive, target, report)

        with mock.patch.object(package_source, "_publish_output", side_effect=race):
            with self.assertRaisesRegex(package_source.PackageError, "output_must_be_absent"):
                self._package()
        self.assertEqual((self.output / "created-by-other-actor.txt").read_text(encoding="utf-8"), "keep\n")
        self.assertFalse((self.output / "source.zip").exists())
        self.assertFalse((self.output / "verification.json").exists())

    def test_empty_output_created_at_publication_race_keeps_identity(self):
        publish = package_source._publish_output
        claimed = []
        def race(source_archive, target, report):
            target.mkdir()
            item = target.stat()
            claimed.append((item.st_dev, item.st_ino))
            return publish(source_archive, target, report)
        with mock.patch.object(package_source, "_publish_output", side_effect=race):
            with self.assertRaisesRegex(package_source.PackageError, "output_must_be_absent"):
                self._package()
        item = self.output.stat()
        self.assertEqual((item.st_dev, item.st_ino), claimed[0])
        self.assertEqual(list(self.output.iterdir()), [])

    def test_tracked_symlink_is_refused(self):
        (self.root / "linked").symlink_to("README.md")
        self._commit()
        with self.assertRaises(package_source.PackageError) as context:
            self._package()
        self.assertIn(context.exception.reason, {"tracked_file_type_refused", "symlink_refused"})
        self.assertFalse(self.output.exists())

    def test_declared_gradlew_crlf_is_only_allowed_normalization(self):
        path = self.root / "clients/android/android"
        path.mkdir(parents=True)
        (path / ".gitattributes").write_text("*.bat text eol=crlf\n", encoding="utf-8")
        batch = path / "gradlew.bat"
        batch.write_bytes(b"@echo off\necho fixture\n")
        self._commit()
        batch.unlink()
        self._git("checkout", "--", "clients/android/android/gradlew.bat")
        self.assertEqual(batch.read_bytes(), b"@echo off\r\necho fixture\r\n")
        report = self._package()
        self.assertEqual(report["eol_serializations"], [{
            "path": "clients/android/android/gradlew.bat", "git_blob_eol": "LF",
            "zip_eol": "CRLF", "declared_attribute": "text eol=crlf"}])
        with zipfile.ZipFile(self.output / "source.zip") as archive:
            self.assertEqual(archive.read("clients/android/android/gradlew.bat"),
                             b"@echo off\r\necho fixture\r\n")

    def test_undeclared_eol_change_is_refused(self):
        (self.root / "README.md").write_bytes(b"tracked source\r\n")
        with self.assertRaisesRegex(package_source.PackageError, "dirty_worktree"):
            self._package()
        self.assertFalse(self.output.exists())

    def test_unexpected_archive_path_is_refused_and_staging_is_removed(self):
        def bad_archive(_root, _head, destination):
            with zipfile.ZipFile(destination, "w") as archive:
                archive.writestr("README.md", b"tracked source\n")
                archive.writestr("../escape", b"unsafe")
        with mock.patch.object(package_source, "_git_archive", side_effect=bad_archive):
            with self.assertRaisesRegex(package_source.PackageError, "unsafe_archive_path"):
                self._package()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.glob(".candidate.package-*")), [])

    def test_duplicate_archive_members_are_refused(self):
        def bad_archive(_root, _head, destination):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(destination, "w") as archive:
                    archive.writestr("README.md", b"tracked source\n")
                    archive.writestr("README.md", b"duplicate")
        with mock.patch.object(package_source, "_git_archive", side_effect=bad_archive):
            with self.assertRaisesRegex(package_source.PackageError, "duplicate_archive_member"):
                self._package()
        self.assertFalse(self.output.exists())

    def test_source_verifier_failure_never_exposes_package(self):
        def refusal(_root):
            raise package_source.VerificationError("content_digest_mismatch", "README.md")
        with self.assertRaisesRegex(package_source.PackageError, "source_verification_failed"):
            package_source.package_source(self.root, self.output, _verifier=refusal)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()

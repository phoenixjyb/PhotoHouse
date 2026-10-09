from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from tools.verify_current_source import (
    MAX_LEDGER_BYTES,
    VerificationError,
    _load_ledger,
    verify_current_source,
)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write(root: Path, relative: str, value: bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def baseline_record(repo: str, source_path: str, content: bytes) -> dict:
    return {"repo": repo, "source_path": source_path, "sha256": sha(content)}


def ledgers(root: Path):
    original = b"base source\n"
    client_original = b"client source\n"
    after_brand = b"brand transformed\n"
    added = b"brand new file\n"
    after_docs = b"documentation transformed\n"
    latest = b"feature overlay two\n"
    latest_added = b"feature add then replace\n"
    write(root, "server/app.py", latest)
    write(root, "clients/android/Main.kt", after_docs)
    write(root, "server/icon.svg", added)
    write(root, "server/new.py", latest_added)

    baseline = {"schema": 1, "historical_git_imported": False,
                "exported_files": [baseline_record("server", "app.py", original),
                                   baseline_record("android", "Main.kt", client_original)]}
    brand = {"schema": 1, "transformations": [
        {"path": "server/app.py", "operation": "replace",
         "before_sha256": sha(original), "after_sha256": sha(after_brand)},
        {"path": "server/icon.svg", "operation": "add", "sha256": sha(added)},
    ]}
    documentation = {"schema": 1, "transformations": [
        {"path": "clients/android/Main.kt", "operation": "replace",
         "before_sha256": sha(client_original), "after_sha256": sha(after_docs)},
    ]}
    features = {"schema": 1, "changes": [
        {"feature": "overlay-one", "files": [
            {"path": "server/app.py", "before_sha256": sha(after_brand),
             "source_sha256": sha(b"private source provenance is not the output"),
             "sha256": sha(b"stale noncandidate output"),
             "candidate_sha256": sha(b"feature overlay one")},
            {"path": "server/new.py", "before_sha256": None,
             "sha256": sha(b"first feature file")},
        ]},
        {"feature": "overlay-two", "files": [
            {"path": "server/app.py", "before_sha256": sha(b"feature overlay one"),
             "sha256": sha(latest)},
            {"path": "server/new.py", "before_sha256": sha(b"first feature file"),
             "sha256": sha(latest_added)},
        ]},
    ]}
    # Latest overlay hashes are the expected current files.
    write(root, "server/app.py", latest)
    return baseline, brand, documentation, features


class VerifyCurrentSourceTests(unittest.TestCase):
    def test_ledger_reader_refuses_symlinks_oversize_and_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            external = Path(outside) / "ledger.json"
            external.write_text('{"safe":true}', encoding="utf-8")
            (root / "ledger.json").symlink_to(external)
            with self.assertRaises(VerificationError) as caught:
                _load_ledger(root, "ledger.json")
            self.assertEqual((caught.exception.reason, caught.exception.path),
                             ("symlink_refused", "ledger.json"))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ledger.json").write_bytes(b" " * (MAX_LEDGER_BYTES + 1))
            with self.assertRaises(VerificationError) as caught:
                _load_ledger(root, "ledger.json")
            self.assertEqual((caught.exception.reason, caught.exception.path),
                             ("ledger_too_large", "ledger.json"))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "ledger.json").write_text('{"sha256":"safe","sha256":"masked"}',
                                              encoding="utf-8")
            with self.assertRaises(VerificationError) as caught:
                _load_ledger(root, "ledger.json")
            self.assertEqual((caught.exception.reason, caught.exception.path),
                             ("duplicate_json_key", "ledger.json"))
            self.assertNotIn("masked", str(caught.exception))

    def test_baseline_transforms_and_ordered_overlays_verify_latest_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = ledgers(root)
            result = verify_current_source(root, *args)
        self.assertEqual(result, {
            "status": "verified", "baseline_files": 2,
            "public_transform_records": 3, "feature_overlays": 2,
            "feature_file_records": 4, "current_files_verified": 4,
            "historical_git_imported": False,
        })

    def test_stale_current_content_fails_with_only_known_relative_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = ledgers(root)
            write(root, "server/app.py", b"changed after ledger\n")
            with self.assertRaises(VerificationError) as caught:
                verify_current_source(root, *args)
        self.assertEqual(caught.exception.reason, "content_digest_mismatch")
        self.assertEqual(caught.exception.path, "server/app.py")
        self.assertNotIn("changed after ledger", str(caught.exception))

    def test_invalid_before_chain_is_rejected_before_file_hashing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            baseline, brand, documentation, features = ledgers(root)
            features["changes"][1]["files"][0]["before_sha256"] = sha(b"unrelated")
            with self.assertRaises(VerificationError) as caught:
                verify_current_source(root, baseline, brand, documentation, features)
        self.assertEqual((caught.exception.reason, caught.exception.path),
                         ("before_digest_mismatch", "server/app.py"))

    def test_rejects_unsafe_and_duplicate_paths_and_malformed_transform(self):
        cases = (
            (lambda b, g, d, f: g["transformations"].append(
                {"path": "../escape", "operation": "add", "sha256": sha(b"x")}),
             "unsafe_path"),
            (lambda b, g, d, f: b["exported_files"].append(dict(b["exported_files"][0])),
             "duplicate_baseline_path"),
            (lambda b, g, d, f: g["transformations"].append(dict(g["transformations"][0])),
             "duplicate_transform_path"),
            (lambda b, g, d, f: g["transformations"].append(
                {"path": "clients/android/Main.kt", "operation": "add", "sha256": sha(b"x")}),
             "add_target_exists"),
            (lambda b, g, d, f: g["transformations"][0].update(operation="delete"),
             "transform_operation_invalid"),
            (lambda b, g, d, f: f["changes"][0]["files"].append(
                dict(f["changes"][0]["files"][0])), "duplicate_overlay_path"),
            (lambda b, g, d, f: f["changes"].append(
                {"feature": "invalid-null-add", "files": [
                    {"path": "server/app.py", "before_sha256": None,
                     "sha256": sha(b"x")}]}), "overlay_add_target_exists"),
        )
        for mutate, expected_reason in cases:
            with self.subTest(reason=expected_reason), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                args = ledgers(root)
                mutate(*args)
                with self.assertRaises(VerificationError) as caught:
                    verify_current_source(root, *args)
                self.assertEqual(caught.exception.reason, expected_reason)

    def test_rejects_unknown_repo_invalid_digest_and_historical_import(self):
        for mutation, expected in (
            (lambda b: b["exported_files"][0].update(repo="personal"), "unknown_repository"),
            (lambda b: b["exported_files"][0].update(sha256=7), "invalid_digest"),
            (lambda b: b.update(historical_git_imported=True), "historical_git_imported"),
        ):
            with self.subTest(reason=expected), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                args = list(ledgers(root))
                mutation(args[0])
                with self.assertRaises(VerificationError) as caught:
                    verify_current_source(root, *args)
                self.assertEqual(caught.exception.reason, expected)

    def test_rejects_symlink_and_nonregular_files(self):
        with tempfile.TemporaryDirectory() as temporary, tempfile.TemporaryDirectory() as outside:
            root = Path(temporary)
            args = ledgers(root)
            target = root / "server/app.py"
            target.unlink()
            target.symlink_to(Path(outside) / "private.txt")
            (Path(outside) / "private.txt").write_bytes(b"outside")
            with self.assertRaises(VerificationError) as caught:
                verify_current_source(root, *args)
            self.assertEqual((caught.exception.reason, caught.exception.path),
                             ("symlink_refused", "server/app.py"))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = ledgers(root)
            target = root / "server/app.py"
            target.unlink()
            target.mkdir()
            with self.assertRaises(VerificationError) as caught:
                verify_current_source(root, *args)
            self.assertEqual((caught.exception.reason, caught.exception.path),
                             ("not_regular_file", "server/app.py"))


if __name__ == "__main__":
    unittest.main()

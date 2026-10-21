"""Synthetic authorization and bounded-file checks for the vector reader."""
from pathlib import Path
import hashlib
import os
import sqlite3
import sys
import struct
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_access_foundation import (MEMBER, NOW, OWNER, OTHER_OWNER, PASSWORD, database)
from app.access.bootstrap import bootstrap_owner
from app.access.service import AccessDenied, AccessService
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256
from app.access.visual_vector_loader import VisualVectorReads, _artifact_from_row, _validated_rows
from app.access.visual_vector_schema import create_visual_vector_schema, sqlite_visual_vector_contract


ARTIFACT_SHA = "a" * 64
PREPROCESS_SHA = "b" * 64
IDENTITY = VectorSpaceIdentity(ARTIFACT_SHA, PREPROCESS_SHA, "synthetic-space", "v1", 2, "unit_l2")
SOURCE_A = "1" * 64
SOURCE_B = "2" * 64


def npy_bytes(vector):
    header = repr({"descr": "<f4", "fortran_order": False,
                   "shape": (len(vector),)}).encode("ascii")
    padding = (-(10 + len(header) + 1)) % 16
    header += b" " * padding + b"\n"
    return (b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header
            + struct.pack(f"<{len(vector)}f", *vector))


class VisualVectorLoaderTests(unittest.TestCase):
    def setUp(self):
        self.db = database()
        self.db.execute("ALTER TABLE assets ADD COLUMN mime TEXT")
        self.db.execute("ALTER TABLE assets ADD COLUMN hash_sha256 TEXT")
        self.db.execute("UPDATE assets SET mime='image/jpeg',hash_sha256=? WHERE id=101", (SOURCE_A,))
        self.db.execute("UPDATE assets SET mime='image/jpeg',hash_sha256=? WHERE id=102", (SOURCE_B,))
        self.db.execute("UPDATE assets SET mime='image/jpeg',hash_sha256=? WHERE id=201", ("3" * 64,))
        self.db.execute("UPDATE assets SET status='active' WHERE id=102")
        self.db.commit()
        bootstrap_owner(self.db, phone=OWNER, password=PASSWORD, library_id="family-a")
        bootstrap_owner(self.db, phone=OTHER_OWNER, password=PASSWORD, library_id="family-b")
        self.service = AccessService(self.db, clock=lambda: NOW)
        self.owner_token = self.service.login(OWNER, PASSWORD)
        self.other_token = self.service.login(OTHER_OWNER, PASSWORD)
        self.member_token = self.service.register(MEMBER, PASSWORD,
            self.service.invite(self.owner_token, "family-a", MEMBER), "Synthetic Member")
        self.member_id = self.service.profile(self.member_token)["account_id"]
        self.db.execute("INSERT INTO access_asset_libraries VALUES (101,'family-a')")
        self.db.execute("INSERT INTO access_asset_libraries VALUES (102,'family-a')")
        self.db.execute("INSERT INTO access_asset_libraries VALUES (201,'family-b')")
        create_visual_vector_schema(self.db)
        self.db.commit()
        directory = tempfile.TemporaryDirectory(prefix="visual-vectors-")
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve(strict=True)
        self.reader = VisualVectorReads(self.service, self.root, IDENTITY)

    def tearDown(self):
        self.db.close()

    def add_vector(self, asset_id, vector, *, source_hash=None, raw=None, identity=IDENTITY,
                   component_hash=None):
        source_hash = source_hash or {"101": SOURCE_A, "102": SOURCE_B, "201": "3" * 64}.get(str(asset_id), "4" * 64)
        raw = raw if raw is not None else npy_bytes(vector)
        digest = identity_sha256(identity)
        record_id = hashlib.sha256(f"record-{asset_id}-{source_hash}-{digest}".encode()).hexdigest()
        relative = f"image-vectors/{digest}/{record_id}.npy"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        component_hash = component_hash or canonical_vector_checksum(vector)
        record = ImmutableVectorArtifact(
            record_id, str(asset_id), source_hash, "synthetic-model", identity.artifact_sha256,
            identity.preprocessing_sha256, identity.vector_space_id, identity.model_version,
            identity.dimension, identity.normalization, digest, relative,
            hashlib.sha256(raw).hexdigest(), component_hash, 1, "ready",
        )
        self.db.execute("""INSERT INTO image_vector_artifacts(
            record_id,asset_id,source_sha256,model_name,artifact_sha256,preprocessing_sha256,
            vector_space_id,model_version,dimension,normalization,identity_sha256,relative_path,
            file_sha256,component_sha256,created_at,status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", tuple(record.__dict__.values()) if hasattr(record, "__dict__") else (
                record.record_id, record.asset_id, record.source_sha256, record.model_name,
                record.artifact_sha256, record.preprocessing_sha256, record.vector_space_id,
                record.model_version, record.dimension, record.normalization, record.identity_sha256,
                record.relative_path, record.file_sha256, record.component_sha256,
                record.created_at, record.status))
        self.db.commit()
        return path, record

    @staticmethod
    def artifact_row(record):
        values = [record.record_id, int(record.asset_id), record.source_sha256,
                  record.model_name, record.artifact_sha256, record.preprocessing_sha256,
                  record.vector_space_id, record.model_version, record.dimension,
                  record.normalization, record.identity_sha256, record.relative_path,
                  record.file_sha256, record.component_sha256, record.created_at,
                  record.status]
        return tuple(values)

    def test_validated_rows_checks_identity_once_and_still_rejects_bad_rows(self):
        _path, record = self.add_vector(101, (1.0, 0.0))
        row = self.artifact_row(record)
        from app.access import visual_vector_loader as loader
        with patch.object(loader, "validate_artifact", wraps=loader.validate_artifact) as validate:
            result = _validated_rows((row,), IDENTITY)
        self.assertEqual(result, {record.asset_id: record})
        validate.assert_called_once_with(record, IDENTITY)

        # The private constructor's default remains self-validating for callers
        # that do not have an expected identity.
        with patch.object(loader, "validate_artifact", wraps=loader.validate_artifact) as validate:
            self.assertEqual(_artifact_from_row(row), record)
        validate.assert_called_once_with(record, None)

        wrong_identity = VectorSpaceIdentity(ARTIFACT_SHA, PREPROCESS_SHA,
                                             "synthetic-space", "v2", 2, "unit_l2")
        with patch.object(loader, "validate_artifact", wraps=loader.validate_artifact) as validate:
            self.assertEqual(_validated_rows((row,), wrong_identity), {})
        validate.assert_called_once_with(record, wrong_identity)

        malformed = list(row)
        malformed[2] = "not-a-sha256"
        with patch.object(loader, "validate_artifact", wraps=loader.validate_artifact) as validate:
            self.assertEqual(_validated_rows((tuple(malformed),), IDENTITY), {})
        self.assertEqual(validate.call_count, 1)

        with patch.object(loader, "validate_artifact", wraps=loader.validate_artifact) as validate:
            self.assertEqual(_validated_rows((row, row), IDENTITY), {})
        self.assertEqual(validate.call_count, 2)

    def clear_artifacts(self):
        delete_trigger = next(ddl for kind, name, ddl in sqlite_visual_vector_contract()
                              if kind == "trigger" and name == "trg_image_vector_artifacts_immutable_delete")
        self.db.execute("DROP TRIGGER trg_image_vector_artifacts_immutable_delete")
        self.db.execute("DELETE FROM image_vector_artifacts")
        self.db.execute(delete_trigger)
        self.db.commit()

    def test_loads_only_same_library_cohort_and_does_not_write_database(self):
        self.add_vector(101, (1.0, 0.0))
        self.add_vector(102, (0.99503719, 0.09950372))
        foreign_path, _ = self.add_vector(201, (0.0, 1.0))
        baseline = self.db.total_changes
        with patch("app.access.visual_vector_loader._read_vector", wraps=__import__(
                "app.access.visual_vector_loader", fromlist=["_read_vector"])._read_vector) as read:
            result = self.reader.candidates(self.member_token, "family-a", ["101"])
        self.assertEqual(result.status, "ready")
        self.assertEqual([item.asset_id for item in result.candidates], ["102"])
        self.assertEqual(self.db.total_changes, baseline)
        self.assertEqual(read.call_count, 2)
        self.assertNotIn(foreign_path, [call.args[0] / call.args[1].relative_path for call in read.call_args_list])

    def test_foreign_inactive_unmapped_and_revoked_seeds_are_denied_before_filesystem(self):
        with patch("app.access.visual_vector_loader._checked_root", side_effect=AssertionError("path touched")):
            for token, library, seed in ((self.member_token, "family-a", "201"),
                                         (self.member_token, "family-a", "999")):
                with self.assertRaises(AccessDenied):
                    self.reader.candidates(token, library, [seed])
            self.db.execute("UPDATE assets SET status='deleted' WHERE id=102")
            self.db.commit()
            with self.assertRaises(AccessDenied):
                self.reader.candidates(self.member_token, "family-a", ["102"])
            self.db.execute("UPDATE access_memberships SET status='revoked' WHERE library_id='family-a' AND account_id=?",
                            (self.member_id,))
            self.db.commit()
            with self.assertRaises(AccessDenied):
                self.reader.candidates(self.member_token, "family-a", ["102"])

    def test_missing_optional_schema_is_unavailable_without_vector_reads(self):
        self.db.execute("DROP TABLE image_vector_artifacts")
        self.db.commit()
        with patch("app.access.visual_vector_loader._checked_root", side_effect=AssertionError("path touched")):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_candidate_over_cap_refuses_before_any_file_io(self):
        # A synthetic DB can hold the full capped cohort without creating bytes.
        for asset_id in range(1000, 1000 + 513):
            self.db.execute("INSERT INTO assets(id,path,status,mime,hash_sha256) VALUES (?,?,'active','image/jpeg',?)",
                            (asset_id, f"synthetic/{asset_id}.jpg", f"{asset_id:064x}"))
            self.db.execute("INSERT INTO access_asset_libraries VALUES (?, 'family-a')", (asset_id,))
            digest = identity_sha256(IDENTITY)
            record_id = hashlib.sha256(f"cap-{asset_id}".encode()).hexdigest()
            relative = f"image-vectors/{digest}/{record_id}.npy"
            self.db.execute("""INSERT INTO image_vector_artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (record_id, asset_id, f"{asset_id:064x}", "synthetic-model", ARTIFACT_SHA,
                 PREPROCESS_SHA, "synthetic-space", "v1", 2, "unit_l2", digest, relative,
                 "5" * 64, "6" * 64, 1, "ready"))
        self.db.commit()
        with patch("app.access.visual_vector_loader._checked_root", side_effect=AssertionError("path touched")):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_bad_source_metadata_refuses_before_filesystem(self):
        _path, record = self.add_vector(101, (1.0, 0.0), source_hash="9" * 64)
        # Seed asset bytes changed after the record was written.
        with patch("app.access.visual_vector_loader._checked_root", side_effect=AssertionError("path touched")):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_old_vector_identity_is_never_mixed_and_wrong_identity_rows_refuse(self):
        old_identity = VectorSpaceIdentity(ARTIFACT_SHA, PREPROCESS_SHA,
                                           "synthetic-space", "v2", 2, "unit_l2")
        self.add_vector(101, (1.0, 0.0), identity=old_identity)
        with patch("app.access.visual_vector_loader._checked_root", side_effect=AssertionError("path touched")):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_oversized_file_refuses_before_decode(self):
        raw = npy_bytes((1.0, 0.0)) + b"x" * (64 * 1024)
        self.add_vector(101, (1.0, 0.0), raw=raw)
        with patch("app.access.visual_vector_loader._decode_npy",
                   side_effect=AssertionError("decode must not run")):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_huge_npy_shape_header_refuses_without_ranker_or_shape_allocation(self):
        header = repr({"descr": "<f4", "fortran_order": False,
                       "shape": (2**60,)}).encode("ascii")
        header += b" " * (-(10 + len(header) + 1) % 16) + b"\n"
        raw = b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header + b"\0" * 8
        self.add_vector(101, (1.0, 0.0), raw=raw)
        with patch("app.access.visual_vector_loader.rank_visual_candidates",
                   side_effect=AssertionError("must not score malformed input")):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_file_checksum_and_symlink_are_refused(self):
        path, record = self.add_vector(101, (1.0, 0.0))
        path.write_bytes(path.read_bytes() + b"x")
        self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                         "unavailable")
        path.unlink()
        elsewhere = self.root / "outside.npy"
        elsewhere.write_bytes(npy_bytes((1.0, 0.0)))
        path.symlink_to(elsewhere)
        self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                         "unavailable")

    def test_trailing_payload_wrong_component_nonunit_and_nonfinite_vectors_refuse(self):
        raw = npy_bytes((1.0, 0.0)) + b"tail"
        self.add_vector(101, (1.0, 0.0), raw=raw)
        self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                         "unavailable")
        self.clear_artifacts()
        self.add_vector(101, (1.0, 0.0), component_hash="a" * 64)
        self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                         "unavailable")
        self.clear_artifacts()
        self.add_vector(101, (0.8, 0.0))
        self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                         "unavailable")
        self.clear_artifacts()
        nonfinite = npy_bytes((float("nan"), 0.0))
        self.add_vector(101, (1.0, 0.0), raw=nonfinite, component_hash="a" * 64)
        self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                         "unavailable")

    def test_malformed_schema_root_symlink_and_reparse_are_refused(self):
        self.add_vector(101, (1.0, 0.0))
        alias = self.root.parent / (self.root.name + "-alias")
        alias.symlink_to(self.root, target_is_directory=True)
        symlink_reader = VisualVectorReads(self.service, alias, IDENTITY)
        self.assertEqual(symlink_reader.candidates(self.member_token, "family-a", ["101"]).status,
                         "unavailable")
        with patch("app.access.visual_vector_loader._is_reparse", return_value=True):
            self.assertIsNone(__import__("app.access.visual_vector_loader",
                fromlist=["_checked_root"])._checked_root(self.root))
        self.db.execute("DROP INDEX uq_image_vector_relative_path")
        self.db.commit()
        with patch("app.access.visual_vector_loader._checked_root", side_effect=AssertionError("path touched")):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_descriptor_replacement_or_truncation_is_refused(self):
        self.add_vector(101, (1.0, 0.0))
        original_read = os.read
        changed = False
        def read_then_truncate(descriptor, count):
            nonlocal changed
            chunk = original_read(descriptor, count)
            if chunk and not changed:
                changed = True
                for path in self.root.glob("image-vectors/*/*.npy"):
                    path.write_bytes(b"short")
            return chunk
        with patch("app.access.visual_vector_loader.os.read", side_effect=read_then_truncate):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_root_ancestor_identity_change_during_read_is_refused(self):
        self.add_vector(101, (1.0, 0.0))
        import app.access.visual_vector_loader as loader
        vector_parent = self.root / "image-vectors" / identity_sha256(IDENTITY)
        snapshot = loader._root_snapshot(vector_parent)
        with patch("app.access.visual_vector_loader._root_snapshot", side_effect=[snapshot, None]):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_direct_file_reader_refuses_aliased_or_nondirectory_ancestors(self):
        import app.access.visual_vector_loader as loader
        path, artifact = self.add_vector(101, (1.0, 0.0))
        parent = path.parent
        moved = parent.with_name('preserved-vector-parent')
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        self.assertIsNone(loader._read_vector(self.root, artifact))
        parent.unlink()
        parent.write_bytes(b'not a directory')
        self.assertIsNone(loader._read_vector(self.root, artifact))

    def test_direct_file_reader_refuses_reparse_parent_before_payload_io(self):
        import app.access.visual_vector_loader as loader
        path, artifact = self.add_vector(101, (1.0, 0.0))
        parent_inode = path.parent.stat().st_ino
        with patch('app.access.visual_vector_loader._is_reparse',
                   side_effect=lambda info: info.st_ino == parent_inode), patch(
                       'app.access.visual_vector_loader.os.open',
                       side_effect=AssertionError('payload opened through reparse parent')):
            self.assertIsNone(loader._read_vector(self.root, artifact))

    def test_nonimage_seed_and_invalid_seed_count_are_unavailable_without_schema_probe(self):
        self.db.execute("UPDATE assets SET mime='video/mp4' WHERE id=101")
        self.db.commit()
        with patch("app.access.visual_vector_loader.verify_visual_vector_schema",
                   side_effect=AssertionError("schema read before media validation")):
            self.assertEqual(self.reader.candidates(self.member_token, "family-a", ["101"]).status,
                             "unavailable")

    def test_v2_container_and_hostile_headers_are_bounded(self):
        from app.access.visual_vector_loader import _decode_npy
        v1 = npy_bytes((1.0, 0.0))
        header_size = struct.unpack_from("<H", v1, 8)[0]
        v2 = b"\x93NUMPY\x02\x00" + struct.pack("<I", header_size) + v1[10:]
        self.assertEqual(_decode_npy(v2, 2), (1.0, 0.0))
        hostile_headers = (
            b"[" * 300 + b"]" * 300 + b"\n",
            b"{'descr':'<f4','fortran_order':False,'shape':(2.0,)}\n",
            b"{'descr':'<f4','fortran_order':False,'shape':(2,), 'extra':1}\n",
            b" " * 4096 + b"\n",
        )
        for header in hostile_headers:
            with self.subTest(header_size=len(header)):
                raw = b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header + b"\0" * 8
                self.assertIsNone(_decode_npy(raw, 2))


if __name__ == "__main__":
    unittest.main()

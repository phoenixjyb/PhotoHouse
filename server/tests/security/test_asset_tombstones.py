"""Synthetic restore contracts for durable image asset tombstones."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.access.asset_tombstones import (
    apply_asset_tombstone,
    plan_durable_asset_vector_cleanup,
    prepare_asset_tombstone,
)
from app.access.original_deletions import OriginalDeletionError, OriginalDeletionJournal
from app.access.visual_candidates import canonical_vector_checksum
from app.access.visual_vector_artifacts import identity_sha256
from app.access.visual_vector_schema import create_visual_vector_schema
from app.access.visual_candidates import VectorSpaceIdentity


NOW = 2_000_000_000
LIBRARY = "family-a"
OTHER_LIBRARY = "family-b"
SOURCE = b"synthetic original image bytes"
SOURCE_SHA = hashlib.sha256(SOURCE).hexdigest()
IDENTITY = VectorSpaceIdentity("a" * 64, "b" * 64, "synthetic-space", "v1", 2, "unit_l2")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _npy(vector):
    header = repr({"descr": "<f4", "fortran_order": False,
                   "shape": (len(vector),)}).encode("ascii")
    padding = (-(10 + len(header) + 1)) % 16
    header += b" " * padding + b"\n"
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header + struct.pack(
        f"<{len(vector)}f", *vector
    )


class AssetTombstoneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="photohouse-asset-tombstones-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.primary_path = self.root / "primary.sqlite"
        self.journal_path = self.root / "deletions.sqlite"
        self.namespace = str(uuid.uuid4())
        self.db = self._connect(self.primary_path)
        self.addCleanup(self.db.close)
        self._schema(self.db)
        self.vector_root = self.root / "vectors"
        self.vector_root.mkdir()
        self.source_path = self.root / "original.jpg"
        self.source_path.write_bytes(SOURCE)
        self._add_asset(self.db, 101)
        create_visual_vector_schema(self.db)
        self._add_vector(self.db, 101)
        self.db.commit()
        self.journal = OriginalDeletionJournal.initialize(
            self.journal_path, self.namespace, format_version=3
        )
        self.journal.bind(self.db)

    @staticmethod
    def _connect(path):
        db = sqlite3.connect(path)
        db.execute("PRAGMA foreign_keys=ON")
        return db

    @staticmethod
    def _schema(db):
        db.executescript("""
            CREATE TABLE assets (
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL,
                status TEXT,
                hash_sha256 TEXT NOT NULL,
                file_size INTEGER NOT NULL,
                mime TEXT NOT NULL
            );
            CREATE TABLE access_libraries (id TEXT PRIMARY KEY, state TEXT NOT NULL);
            INSERT INTO access_libraries VALUES ('family-a','active'),('family-b','active');
            CREATE TABLE access_asset_libraries (
                asset_id INTEGER PRIMARY KEY REFERENCES assets(id),
                library_id TEXT NOT NULL REFERENCES access_libraries(id)
            );
            CREATE TABLE access_upload_annotations (id TEXT PRIMARY KEY);
            CREATE TABLE access_memory_contributions (id TEXT PRIMARY KEY);
            CREATE TABLE access_uploads (
                asset_id INTEGER NOT NULL, state TEXT NOT NULL,
                sha256 TEXT NOT NULL, bytes INTEGER NOT NULL
            );
            CREATE TABLE access_original_deletion_state (
                id INTEGER PRIMARY KEY, namespace TEXT NOT NULL,
                applied_seq INTEGER NOT NULL, applied_digest TEXT NOT NULL
            );
        """)

    def _add_asset(self, db, asset_id, *, library=LIBRARY, path=None):
        source_path = path or str(self.source_path)
        db.execute("INSERT INTO assets(id,path,status,hash_sha256,file_size,mime) "
                   "VALUES (?,?, 'active',?,?,?)",
                   (asset_id, source_path, SOURCE_SHA, len(SOURCE), "image/jpeg"))
        db.execute("INSERT INTO access_asset_libraries(asset_id,library_id) VALUES (?,?)",
                   (asset_id, library))
        db.execute("INSERT INTO access_uploads(asset_id,state,sha256,bytes) VALUES (?,'assigned',?,?)",
                   (asset_id, SOURCE_SHA, len(SOURCE)))

    def _add_vector(self, db, asset_id):
        vector = (1.0, 0.0)
        raw = _npy(vector)
        identity_digest = identity_sha256(IDENTITY)
        record_id = _sha(f"asset-{asset_id}".encode())
        relative = f"image-vectors/{identity_digest}/{record_id}.npy"
        target = self.vector_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        db.execute("""INSERT INTO image_vector_artifacts(
            record_id,asset_id,source_sha256,model_name,artifact_sha256,preprocessing_sha256,
            vector_space_id,model_version,dimension,normalization,identity_sha256,relative_path,
            file_sha256,component_sha256,created_at,status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record_id, asset_id, SOURCE_SHA, "synthetic-model", IDENTITY.artifact_sha256,
             IDENTITY.preprocessing_sha256, IDENTITY.vector_space_id, IDENTITY.model_version,
             IDENTITY.dimension, IDENTITY.normalization, identity_digest, relative, _sha(raw),
             canonical_vector_checksum(vector), NOW, "ready"))

    def _snapshot(self, target):
        with closing(sqlite3.connect(target)) as copy:
            self.db.backup(copy)

    def _restore(self, source, *, name="restore.sqlite"):
        target = self.root / name
        shutil.copyfile(source, target)
        db = self._connect(target)
        return target, db

    def _request(self, db, asset_id=101, library=LIBRARY):
        binding = prepare_asset_tombstone(db, asset_id, library, NOW)['asset_binding_json']
        return {'id': asset_id, 'library_id': library, 'asset_binding_json': binding}

    def _append_and_apply(self, db, asset_id=101, library=LIBRARY):
        db.execute("PRAGMA secure_delete=ON")
        db.execute("BEGIN IMMEDIATE")
        candidate = prepare_asset_tombstone(db, asset_id, library, NOW)
        entry = self.journal.append(db, "asset", self._request(db, asset_id, library), NOW)
        apply_asset_tombstone(db, candidate)
        return entry

    def test_sidecar_append_primary_rollback_replays_older_backup_and_retains_assets(self):
        backup = self.root / "before-delete.sqlite"
        self._snapshot(backup)
        source_bytes = self.source_path.read_bytes()
        vector_bytes = next(self.vector_root.rglob("*.npy")).read_bytes()
        artifact_before = tuple(self.db.execute(
            "SELECT * FROM image_vector_artifacts WHERE asset_id=101").fetchone())

        entry = self._append_and_apply(self.db)
        self.assertNotIn(str(self.source_path), repr(entry))
        self.db.rollback()  # External append survives the simulated primary crash.
        self.assertEqual(self.journal.head()[1], 1)
        self.assertEqual(self.db.execute(
            "SELECT status FROM assets WHERE id=101").fetchone()[0], "active")

        _path, restored = self._restore(backup)
        with closing(restored):
            review = self.journal.review(restored)
            self.assertEqual(review["pending_count"], 1)
            result = self.journal.replay(restored)
            self.assertEqual(result[3], 1)
            self.assertEqual(restored.execute(
                "SELECT status FROM assets WHERE id=101").fetchone()[0], "deleted")
            self.assertEqual(restored.execute(
                "SELECT library_id FROM access_asset_libraries WHERE asset_id=101").fetchone()[0], LIBRARY)
            self.assertEqual(tuple(restored.execute(
                "SELECT * FROM image_vector_artifacts WHERE asset_id=101").fetchone()), artifact_before)
            self.assertEqual(self.journal.replay(restored)[3], 0)

        self.assertEqual(self.source_path.read_bytes(), source_bytes)
        self.assertEqual(next(self.vector_root.rglob("*.npy")).read_bytes(), vector_bytes)

    def test_prepared_binding_is_content_free_and_hashes_original_path(self):
        self.db.execute("BEGIN")
        candidate = prepare_asset_tombstone(self.db, 101, LIBRARY, NOW)
        self.db.rollback()
        binding = json.loads(candidate["asset_binding_json"])
        self.assertEqual(set(binding), {
            "version", "asset_id", "source_sha256", "file_size", "mime",
            "path_sha256", "library_id", "mapping_sha256",
        })
        self.assertEqual(binding["path_sha256"], _sha(str(self.source_path).encode("utf-8")))
        self.assertNotIn(str(self.source_path), candidate["asset_binding_json"])
        self.assertNotIn(SOURCE.decode(), candidate["asset_binding_json"])

    def test_process_death_after_external_append_replays_older_primary(self):
        backup = self.root / 'process-death-backup.sqlite'
        self._snapshot(backup)
        code = '''import os,sqlite3,sys
sys.path.insert(0,sys.argv[1])
from app.access.original_deletions import OriginalDeletionJournal
from app.access.asset_tombstones import prepare_asset_tombstone
db=sqlite3.connect(sys.argv[2]);db.execute('PRAGMA foreign_keys=ON')
db.execute('PRAGMA secure_delete=ON');db.execute('BEGIN IMMEDIATE')
journal=OriginalDeletionJournal(sys.argv[3],sys.argv[4])
candidate=prepare_asset_tombstone(db,101,'family-a',2000000000)
journal.append(db,'asset',{'id':101,'library_id':'family-a',
    'asset_binding_json':candidate['asset_binding_json']},2000000000)
os._exit(47)
'''
        child = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(ROOT / 'backend'),
                                str(self.primary_path), str(self.journal_path), self.namespace],
                               capture_output=True, timeout=30)
        self.assertEqual(child.returncode, 47, child.stderr.decode(errors='replace'))
        _, restored = self._restore(backup, name='process-death-restored.sqlite')
        with closing(restored):
            self.assertEqual(self.journal.review(restored)['pending_count'], 1)
            self.assertEqual(self.journal.replay(restored)[3], 1)
            self.assertEqual(restored.execute('SELECT status FROM assets WHERE id=101').fetchone(), ('deleted',))
            self.assertEqual(restored.execute('SELECT count(*) FROM image_vector_artifacts').fetchone(), (1,))
        self.assertEqual(self.source_path.read_bytes(), SOURCE)

    def test_missing_or_stale_prepared_binding_cannot_append_a_new_tombstone(self):
        head = self.journal.head()
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.execute('BEGIN IMMEDIATE')
        request = self._request(self.db)
        with self.assertRaises(OriginalDeletionError):
            self.journal.append(self.db, 'asset', {'id': 101, 'library_id': LIBRARY}, NOW)
        self.db.execute("UPDATE assets SET path=path||'.changed' WHERE id=101")
        with self.assertRaises(OriginalDeletionError):
            self.journal.append(self.db, 'asset', request, NOW)
        self.db.rollback()
        self.assertEqual(self.journal.head(), head)

    def test_invalid_asset_identifiers_refuse_without_journal_changes(self):
        head = self.journal.head()
        self.db.execute('BEGIN IMMEDIATE')
        for asset_id in (True, 0, -1, '101', 2**63):
            with self.subTest(asset_id=asset_id), self.assertRaises(OriginalDeletionError):
                prepare_asset_tombstone(self.db, asset_id, LIBRARY, NOW)
        self.db.rollback()
        self.assertEqual(self.journal.head(), head)

    def test_exact_retry_succeeds_but_changed_binding_is_refused(self):
        entry = self._append_and_apply(self.db)
        self.db.rollback()
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("BEGIN IMMEDIATE")
        retry_candidate = prepare_asset_tombstone(self.db, 101, LIBRARY, NOW)
        retried = self.journal.append(self.db, "asset", self._request(self.db), NOW)
        self.assertEqual(retried["digest"], entry["digest"])
        apply_asset_tombstone(self.db, retry_candidate)
        self.db.rollback()

        self.db.execute("UPDATE assets SET file_size=file_size+1 WHERE id=101")
        self.db.commit()
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("BEGIN IMMEDIATE")
        with self.assertRaises(OriginalDeletionError):
            self.journal.append(self.db, "asset", self._request(self.db), NOW)
        self.db.rollback()
        self.assertEqual(self.journal.head()[1], 1)

    def test_asset_append_is_refused_by_v1_and_v2_without_advancing_head(self):
        for version in (1, 2):
            with self.subTest(version=version):
                path = self.root / f"v{version}.sqlite"
                journal = OriginalDeletionJournal.initialize(path, str(uuid.uuid4()),
                                                             format_version=version)
                # Bind requires the marker namespace and an empty originals inventory.
                prior_namespace = self.journal.namespace
                # Use an independent empty primary for each journal namespace.
                primary = self._connect(self.root / f"v{version}-primary.sqlite")
                self._schema(primary)
                self._add_asset(primary, 101)
                primary.commit()
                journal.bind(primary)
                head = journal.head()
                primary.execute("PRAGMA secure_delete=ON")
                primary.execute("BEGIN IMMEDIATE")
                with self.assertRaises(OriginalDeletionError):
                    journal.append(primary, "asset", self._request(primary), NOW)
                primary.rollback()
                self.assertEqual(journal.head(), head)
                primary.close()
                self.assertEqual(prior_namespace, self.journal.namespace)

    def test_v1_and_v2_upload_history_upgrade_preserves_old_record_and_marker_digests(self):
        from app.access import original_deletions as journal_module

        for version in (1, 2):
            with self.subTest(version=version):
                namespace = str(uuid.uuid4())
                journal_path = self.root / f"upgrade-v{version}.sqlite"
                primary_path = self.root / f"upgrade-v{version}-primary.sqlite"
                journal = OriginalDeletionJournal.initialize(
                    journal_path, namespace, format_version=version
                )
                primary = self._connect(primary_path)
                self._schema(primary)
                primary.commit()
                journal.bind(primary)
                record = {
                    "seq": 1,
                    "collection": "upload",
                    "library_id": LIBRARY,
                    "object_id": str(uuid.uuid4()),
                    "original_kind": "text",
                    "original_sha256": "a" * 64,
                    "batch": "b" * 32,
                    "asset_id": None,
                    "story_id": None,
                    "occurred_at": NOW,
                    "prev_digest": journal_module._genesis(namespace),
                }
                record["digest"] = journal_module._record_digest(record["prev_digest"], record)
                ledger = journal._connect()
                try:
                    ledger.execute("BEGIN IMMEDIATE")
                    names = list(journal_module._RECORD_COLUMNS)
                    if version == 2:
                        names.append("family_binding_json")
                        record["family_binding_json"] = None
                    ledger.execute(
                        "INSERT INTO deletions (" + ",".join(names) + ") VALUES (" +
                        ",".join("?" for _ in names) + ")",
                        tuple(record.get(name) for name in names),
                    )
                    ledger.execute("UPDATE journal_meta SET head_seq=1,head_digest=? WHERE id=1",
                                   (record["digest"],))
                    ledger.commit()
                finally:
                    ledger.close()
                primary.execute("BEGIN IMMEDIATE")
                primary.execute("UPDATE access_original_deletion_state "
                                "SET applied_seq=1,applied_digest=? WHERE id=1",
                                (record["digest"],))
                before = journal.head()
                upgraded = journal.upgrade_asset_format(primary, expected_head=before)
                primary.commit()
                self.assertEqual(upgraded, before)
                self.assertEqual(journal.head(), before)
                self.assertEqual(tuple(primary.execute(
                    "SELECT applied_seq,applied_digest FROM access_original_deletion_state WHERE id=1"
                ).fetchone()), (before[1], before[2]))
                ledger = journal._connect()
                try:
                    stored = ledger.execute("SELECT * FROM deletions WHERE seq=1").fetchone()
                    self.assertEqual(stored["prev_digest"], record["prev_digest"])
                    self.assertEqual(stored["digest"], record["digest"])
                finally:
                    ledger.close()
                primary.close()

    def test_v2_family_note_history_keeps_its_digest_rule_when_upgraded_to_v3(self):
        from app.access import original_deletions as journal_module

        namespace = str(uuid.uuid4())
        journal = OriginalDeletionJournal.initialize(
            self.root / "upgrade-v2-family.sqlite", namespace, format_version=2
        )
        primary = self._connect(self.root / "upgrade-v2-family-primary.sqlite")
        self._schema(primary)
        primary.commit()
        journal.bind(primary)
        binding = json.dumps({
            "version": 2,
            "identity_id": str(uuid.uuid4()),
            "registry_sha256": "a" * 64,
            "expected_revision": 1,
            "revision_sha256": "b" * 64,
            "scope_digests": ["c" * 64],
        }, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        record = {
            "seq": 1,
            "collection": "family_note",
            "library_id": LIBRARY,
            "object_id": str(uuid.uuid4()),
            "original_kind": "text",
            "original_sha256": "d" * 64,
            "batch": None,
            "asset_id": 101,
            "story_id": None,
            "occurred_at": NOW,
            "prev_digest": journal_module._genesis(namespace),
            "family_binding_json": binding,
        }
        record["digest"] = journal_module._record_digest(record["prev_digest"], record)
        ledger = journal._connect()
        try:
            ledger.execute("BEGIN IMMEDIATE")
            names = [*journal_module._RECORD_COLUMNS, "family_binding_json"]
            ledger.execute(
                "INSERT INTO deletions (" + ",".join(names) + ") VALUES (" +
                ",".join("?" for _ in names) + ")",
                tuple(record.get(name) for name in names),
            )
            ledger.execute("UPDATE journal_meta SET head_seq=1,head_digest=? WHERE id=1",
                           (record["digest"],))
            ledger.commit()
        finally:
            ledger.close()
        primary.execute("BEGIN IMMEDIATE")
        primary.execute("UPDATE access_original_deletion_state "
                        "SET applied_seq=1,applied_digest=? WHERE id=1", (record["digest"],))
        before = journal.head()
        before_history_digest = journal.history_digest(1)
        self.assertEqual(before_history_digest, record["digest"])
        journal.upgrade_asset_format(primary, expected_head=before)
        primary.commit()
        self.assertEqual(journal.head(), before)
        self.assertEqual(journal.history_digest(1), before_history_digest)
        self.assertEqual(tuple(primary.execute(
            "SELECT applied_seq,applied_digest FROM access_original_deletion_state WHERE id=1"
        ).fetchone()), (before[1], before[2]))
        primary.close()

    def test_replay_refuses_source_or_mapping_drift_atomically(self):
        for asset_id in range(101, 106):
            if asset_id != 101:
                self._add_asset(self.db, asset_id)
        self.db.commit()
        backup = self.root / "drift-backup.sqlite"
        self._snapshot(backup)
        for asset_id in range(101, 106):
            self._append_and_apply(self.db, asset_id)
            self.db.commit()

        changes = {
            "hash": "UPDATE assets SET hash_sha256=? WHERE id=105",
            "size": "UPDATE assets SET file_size=file_size+1 WHERE id=105",
            "mime": "UPDATE assets SET mime='image/png' WHERE id=105",
            "path": "UPDATE assets SET path=path||'.moved' WHERE id=105",
            "receipt": "UPDATE access_uploads SET bytes=bytes+1 WHERE asset_id=105",
            "mapping": "UPDATE access_asset_libraries SET library_id=? WHERE asset_id=105",
            "missing_parent": "DELETE FROM assets WHERE id=105",
        }
        for name, sql in changes.items():
            with self.subTest(change=name):
                _path, restored = self._restore(backup, name=f"drift-{name}.sqlite")
                with closing(restored):
                    args = ("family-b",) if name == "mapping" else (
                        ("f" * 64,) if name == "hash" else ())
                    if name == "missing_parent":
                        restored.execute("DELETE FROM access_asset_libraries WHERE asset_id=105")
                    restored.execute(sql, args)
                    restored.commit()
                    with self.assertRaises(OriginalDeletionError):
                        self.journal.replay(restored)
                    self.assertEqual(restored.execute(
                        "SELECT status FROM assets WHERE id=101").fetchone()[0], "active")
                    self.assertEqual(restored.execute(
                        "SELECT applied_seq FROM access_original_deletion_state WHERE id=1").fetchone()[0], 0)

    def test_cleanup_plan_requires_matching_committed_receipt(self):
        self.db.execute("BEGIN")
        with self.assertRaises(OriginalDeletionError):
            plan_durable_asset_vector_cleanup(self.db, self.vector_root, self.journal, 101)
        self.db.rollback()

        self._append_and_apply(self.db)
        self.db.commit()
        self.db.execute("BEGIN")
        plan = plan_durable_asset_vector_cleanup(self.db, self.vector_root, self.journal, 101)
        self.db.rollback()
        self.assertEqual(len(plan.items), 1)
        self.assertFalse(plan.items[0].missing)

    def test_uncommitted_primary_marker_and_status_do_not_authorize_cleanup_plan(self):
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("BEGIN IMMEDIATE")
        candidate = prepare_asset_tombstone(self.db, 101, LIBRARY, NOW)
        self.journal.append(self.db, "asset", self._request(self.db), NOW)
        apply_asset_tombstone(self.db, candidate)
        with self.assertRaises(OriginalDeletionError):
            plan_durable_asset_vector_cleanup(self.db, self.vector_root, self.journal, 101)
        self.db.rollback()

        self.journal.replay(self.db)
        self.db.execute("BEGIN")
        plan = plan_durable_asset_vector_cleanup(self.db, self.vector_root, self.journal, 101)
        self.db.rollback()
        self.assertEqual(len(plan.items), 1)
        self.assertFalse(plan.items[0].missing)

    def test_asset_id_cannot_be_reused_under_another_library(self):
        self._append_and_apply(self.db)
        self.db.commit()
        self.db.execute("UPDATE assets SET status='active' WHERE id=101")
        self.db.execute("UPDATE access_asset_libraries SET library_id=? WHERE asset_id=101",
                        (OTHER_LIBRARY,))
        self.db.commit()
        self.db.execute("PRAGMA secure_delete=ON")
        self.db.execute("BEGIN IMMEDIATE")
        with self.assertRaises(OriginalDeletionError):
            self.journal.append(self.db, "asset", self._request(self.db, library=OTHER_LIBRARY), NOW)
        self.db.rollback()

    def test_applied_marker_cannot_hide_a_revived_asset_during_offline_restore(self):
        self._append_and_apply(self.db)
        self.db.commit()
        self.db.execute("UPDATE assets SET status='active' WHERE id=101")
        self.db.commit()
        before = self.journal.head()
        with self.assertRaises(OriginalDeletionError):
            self.journal.review(self.db)
        with self.assertRaises(OriginalDeletionError):
            self.journal.replay(self.db)
        self.assertEqual(self.journal.head(), before)
        self.assertEqual(self.db.execute('SELECT status FROM assets WHERE id=101').fetchone(), ('active',))


if __name__ == "__main__":
    unittest.main()

"""CPU-only regression checks for exact image-worker claim ownership."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import run_approved_image_embed_worker as worker


class ImageWorkerClaimTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "claims.sqlite"
        self.db = sqlite3.connect(self.path)
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE tasks(id INTEGER PRIMARY KEY,type TEXT,state TEXT,payload_json TEXT,
                retry_count INTEGER,cancel_requested INTEGER,scheduled_at TEXT,started_at TEXT,
                finished_at TEXT,last_error TEXT,priority INTEGER);
            INSERT INTO tasks VALUES(1,'embed','pending','{"asset_id":101,"modality":"image"}',
                0,0,NULL,NULL,NULL,NULL,80);
        """)
        self.db.commit()
        self.candidate = {'task_id': 1, 'asset_id': 101, 'retry_count': 0,
                          'payload_json': '{"asset_id":101,"modality":"image"}'}

    def claim(self):
        with patch.object(worker, "validate_schema"), patch.object(
                worker, "matching_candidates", return_value=[self.candidate.copy()]):
            return worker._claim_one(self.path)

    def test_claim_captures_exact_raw_payload_start_and_retry(self):
        claim = self.claim()
        row = self.db.execute("SELECT payload_json,started_at,retry_count,state FROM tasks WHERE id=1").fetchone()
        self.assertEqual((claim['claimed_payload_json'], claim['claim_started_at'], claim['claim_retry_count']),
                         row[:3])
        self.assertEqual(row[3], 'running')
        self.assertIsNotNone(claim['claim_started_at'])

    def test_stale_failure_never_mutates_current_task(self):
        claim = self.claim()
        changes = (
            ('payload_json', json.dumps({'asset_id': 101, 'modality': 'image'})),
            ('retry_count', 2), ('started_at', 'new-claim'), ('cancel_requested', 1),
            ('type', 'other-task'), ('state', 'finished'),
        )
        original = self.db.execute("SELECT * FROM tasks").fetchone()
        for column, value in changes:
            with self.subTest(column=column):
                self.db.execute("UPDATE tasks SET type=?,state=?,payload_json=?,retry_count=?,cancel_requested=?,"
                                "scheduled_at=?,started_at=?,finished_at=?,last_error=?,priority=? WHERE id=1",
                                original[1:])
                self.db.execute(f"UPDATE tasks SET {column}=? WHERE id=1", (value,))
                self.db.commit()
                before = self.db.execute("SELECT * FROM tasks").fetchone()
                self.assertEqual(worker.record_failure(self.path, claim, RuntimeError('synthetic')), 0)
                self.assertEqual(self.db.execute("SELECT * FROM tasks").fetchone(), before)

    def test_exact_claim_failure_keeps_bounded_retry_behavior(self):
        claim = self.claim()
        self.assertEqual(worker.record_failure(self.path, claim, RuntimeError('synthetic')), 1)
        row = self.db.execute("SELECT state,retry_count,started_at,last_error FROM tasks").fetchone()
        self.assertEqual(row[:3], ('pending', 1, None))
        self.assertEqual(row[3], 'provider_or_worker_failure')


if __name__ == '__main__':
    unittest.main()

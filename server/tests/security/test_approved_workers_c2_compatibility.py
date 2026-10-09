"""Memory-worker schema admission against the real additive C2 SQLite migration."""
import sqlite3
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))

import run_memory_worker as memory_worker
import test_memory_book_edition_migration as edition_migration


class C2MemoryWorkerCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.fixture = edition_migration.MemoryBookEditionMigrationTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture._upgrade_to_b1_with_existing_editorial()
        self.fixture._upgrade()
        self.db = sqlite3.connect(self.fixture.migration.path)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.addCleanup(self.db.close)

    def test_actual_c2_accepts_existing_jobs_and_editorial_context_without_schema_writes(self):
        before = self.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall()
        self.assertTrue(memory_worker._check_schema(self.db))
        self.assertTrue(memory_worker._check_schema(self.db, editorial_enabled=True))
        self.assertEqual(self.db.execute('SELECT type,name,sql FROM sqlite_master ORDER BY name').fetchall(), before)
        self.assertFalse(self.db.in_transaction)

    def test_missing_editorial_or_citation_tables_and_unknown_revision_fail_closed(self):
        self.db.execute('DROP TABLE access_memory_book_editorial_refs')
        self.assertFalse(memory_worker._check_schema(self.db, editorial_enabled=True))
        self.assertTrue(memory_worker._check_schema(self.db))
        self.db.execute('DROP TABLE access_memory_contribution_refs')
        self.assertFalse(memory_worker._check_schema(self.db))
        self.db.execute("UPDATE alembic_version SET version_num='synthetic-unknown'")
        self.assertFalse(memory_worker._check_schema(self.db))

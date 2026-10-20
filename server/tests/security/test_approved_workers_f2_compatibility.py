"""Read-only admission of every approved worker after the actual f2 migration."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))

import test_approved_workers_e7_compatibility as previous
from app.access.photo_stack_schema import TABLES


class ApprovedWorkersF2CompatibilityTests(previous.ApprovedWorkersE7CompatibilityTests):
    schema_revision='f2a8c5d1e640'

    def test_new_presentation_storage_starts_empty_without_worker_activation(self):
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.worker_fixture.database)) as db:
            for name in TABLES:
                self.assertEqual(db.execute('SELECT count(*) FROM '+name).fetchone()[0],0)

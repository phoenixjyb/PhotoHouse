"""Library-driven caption reads retain rows, bytes and closed snapshot admission."""
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path[:0] = [str(Path(__file__).resolve().parents[2] / 'backend'), str(Path(__file__).parent)]
from app.access import discovery as d
from app.access.semantic_request_snapshot import _known_query
from phone_discovery_fixture import create

PRIOR = ('SELECT x.id,x.asset_id,CASE WHEN length(CAST(x.text AS BLOB))<=4096 THEN x.text END,'
         'length(CAST(x.text AS BLOB)),length(CAST(x.text AS BLOB)),x.user_edited,x.superseded '
         'FROM captions x' + d.SCOPE + ' AND x.superseded=0 ORDER BY x.id')


class AssistantCaptionScopeTests(unittest.TestCase):
    def setUp(self):
        self.db = create(sqlite3.connect(':memory:'))
        self.addCleanup(self.db.close)
        # This index is part of the supported caption migration; no production
        # index or migration is created by the application query change.
        self.db.execute('CREATE INDEX ix_captions_asset_id ON captions(asset_id)')

    def rows(self, sql, library='family-a'):
        return self.db.execute(sql, (library,)).fetchall()

    def test_current_and_prior_queries_have_exact_rows_order_and_byte_accounting(self):
        self.db.executemany('INSERT INTO captions VALUES(?,?,?,?,?)', [
            (11, 101, '中文🙂', 1, 0), (12, 101, 'superseded', 0, 1),
            (13, 101, 'unknown state', 0, None), (14, 102, '', 0, 0),
            (15, 102, None, 0, 0), (16, 102, '海' * 1400, 0, 0),
            (17, 201, 'foreign', 1, 0), (18, 103, 'inactive', 0, 0),
            (19, 9999, 'orphan', 0, 0)])
        self.db.execute("UPDATE assets SET status='inactive' WHERE id=103")
        for library in ('family-a', 'family-b', 'missing'):
            with self.subTest(library=library):
                expected = self.rows(PRIOR, library)
                actual = self.rows(d.SCOPED_TEXT_CAPTIONS_SQL, library)
                self.assertEqual(actual, expected)
                self.assertEqual(d.packed(actual), d.packed(expected))

    def test_foreign_caption_volume_does_not_force_a_global_caption_scan(self):
        self.db.executemany('INSERT INTO captions VALUES(?,?,?,0,0)',
                           ((1000 + value, 201, 'Foreign fixture caption') for value in range(20000)))
        self.db.commit()
        expected = self.rows(PRIOR)
        steps = [0]

        def progress():
            steps[0] += 1
            return int(steps[0] > 100)

        self.db.set_progress_handler(progress, 100)
        try:
            actual = self.rows(d.SCOPED_TEXT_CAPTIONS_SQL)
        finally:
            self.db.set_progress_handler(None, 0)
        self.assertEqual(actual, expected)
        self.assertLessEqual(steps[0], 100, 'scoped lookup exceeded 10,000 VM steps')

    def test_snapshot_allows_only_the_exact_reviewed_query_shape(self):
        self.assertTrue(_known_query(d.SCOPED_TEXT_CAPTIONS_SQL))
        self.assertTrue(_known_query(PRIOR))
        self.assertFalse(_known_query(d.SCOPED_TEXT_CAPTIONS_SQL.replace('m.library_id=? AND ', '')))
        self.assertFalse(_known_query(d.SCOPED_TEXT_CAPTIONS_SQL.replace('x.superseded=0', '1=1')))

    def test_budgeted_read_returns_the_same_rows_and_releases_its_slot(self):
        expected = self.rows(PRIOR)
        self.db.commit()
        byte_count = sum(len(d.packed(row)) for row in expected)
        budget = d.ReadBudget(rows=len(expected), source_bytes=byte_count, seconds=30, concurrency=1)
        with budget.attempt(self.db, lambda: False) as (_, read):
            self.assertEqual(read(d.SCOPED_TEXT_CAPTIONS_SQL, ('family-a',)), expected)
        with budget.attempt(self.db, lambda: False) as (_, read):
            self.assertEqual(read(d.SCOPED_TEXT_CAPTIONS_SQL, ('family-a',)), expected)
        limited = d.ReadBudget(rows=len(expected), source_bytes=byte_count - 1, seconds=30)
        with limited.attempt(self.db, lambda: False) as (_, read):
            with self.assertRaises(d.DiscoveryUnavailable):
                read(d.SCOPED_TEXT_CAPTIONS_SQL, ('family-a',))


if __name__ == '__main__':
    unittest.main()

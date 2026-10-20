"""Real protected-session policy for the unwired draft owner; no KDF/model I/O."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.access.credentials import DUMMY_HASH, session_digest
from app.access.schema import apply_schema
from app.access.selected_story_operations import DraftPrincipal, SelectedStorySources
from app.access.service import AccessDenied


class DraftOperationAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.addCleanup(self.db.close)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE assets(id INTEGER PRIMARY KEY)')
        apply_schema(self.db.execute)
        self.token = 'A' * 43
        self.now = 2_000_000_000
        self.db.execute('INSERT INTO access_accounts(id,phone_login,password_hash) VALUES (?,?,?)',
                        ('synthetic-owner', '+12025550100', DUMMY_HASH))
        self.db.execute('INSERT INTO access_libraries(id,bootstrap_operator) VALUES (?,?)',
                        ('synthetic-library', 'synthetic-owner'))
        self.db.execute('''INSERT INTO access_memberships
            (account_id,library_id,status,role,revision,approved_by)
            VALUES ('synthetic-owner','synthetic-library','approved','owner',1,'synthetic-owner')''')
        self.db.execute('INSERT INTO access_sessions(digest,account_id,expires_at) VALUES (?,?,?)',
                        (session_digest(self.token), 'synthetic-owner', self.now + 100))
        self.db.commit()
        @contextmanager
        def connection():
            yield self.db
        self.sources = SelectedStorySources(SimpleNamespace(connection_factory=connection,
            clock=lambda: self.now, memory_groups_enabled=False))

    def test_authorizes_current_writer_and_returns_only_actor_and_session_hash(self):
        trace = []
        self.db.set_trace_callback(trace.append)
        principal = self.sources.authenticate(self.token, 'synthetic-library')
        self.assertEqual(principal, DraftPrincipal('synthetic-owner', session_digest(self.token)))
        self.assertNotIn(self.token, repr(principal))
        self.assertFalse(self.db.in_transaction)
        self.assertFalse(any(sql.lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE', 'REPLACE'))
                             for sql in trace))

    def test_denies_revoked_expired_viewer_and_foreign_scope(self):
        mutations = (
            ("UPDATE access_sessions SET revoked=1", "UPDATE access_sessions SET revoked=0"),
            ("UPDATE access_accounts SET state='disabled'", "UPDATE access_accounts SET state='active'"),
            ("UPDATE access_memberships SET role='viewer'", "UPDATE access_memberships SET role='owner'"),
            ("UPDATE access_memberships SET status='revoked'", "UPDATE access_memberships SET status='approved'"),
        )
        for mutation, restore in mutations:
            with self.subTest(mutation=mutation):
                self.db.execute(mutation); self.db.commit()
                with self.assertRaises(AccessDenied):
                    self.sources.authenticate(self.token, 'synthetic-library')
                self.db.execute(restore); self.db.commit()
        with self.assertRaises(AccessDenied):
            self.sources.authenticate(self.token, 'other-library')
        self.now += 101
        with self.assertRaises(AccessDenied):
            self.sources.authenticate(self.token, 'synthetic-library')

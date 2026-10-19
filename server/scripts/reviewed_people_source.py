"""Read-only source boundary for reviewed-people preparation tools."""
from contextlib import contextmanager
import sqlite3

from app.access.provisioning_apply import (
    PlanRejected,
    assert_deletion_history,
    capture_deletion_history,
)


def _require_unbound_primary(db):
    row = db.execute("SELECT type FROM sqlite_master WHERE name='access_original_deletion_state'").fetchone()
    if row is None:
        return
    if row[0] != 'table' or db.execute(
            'SELECT 1 FROM access_original_deletion_state LIMIT 1').fetchone() is not None:
        raise PlanRejected('Bound primary requires deletion history review')


def _enable_deletion_guard_reads(producer, db):
    """Keep the producer authorizer, allowing only the guard's identity PRAGMAs."""
    original = producer.authorize

    def authorize(action, first, second, *rest):
        if (action == sqlite3.SQLITE_PRAGMA and
                ((first == 'database_list' and second is None) or
                 (first == 'table_info' and second == 'access_original_deletion_state'))):
            return sqlite3.SQLITE_OK
        return original(action, first, second, *rest)
    db.set_authorizer(authorize)


@contextmanager
def open_reviewed_people_source(producer, database, start, *, deletion_journal=None,
                                deletion_namespace=None):
    """Yield a producer-configured read-only DB under a stable deletion head.

    The caller retains its producer's SQLite authorizer and progress handler.
    A private external journal is only read; it is never initialized, replayed,
    or bound by this source boundary.
    """
    if (deletion_journal is None) != (deletion_namespace is None):
        raise PlanRejected('Both deletion history options are required')
    history = capture_deletion_history(deletion_journal, deletion_namespace)
    db = producer.open_read_only(database, start)
    completed = False
    try:
        if history is not None:
            _enable_deletion_guard_reads(producer, db)
        if history is None:
            _require_unbound_primary(db)
        else:
            assert_deletion_history(history, db)
        yield db
        if history is None:
            _require_unbound_primary(db)
        else:
            assert_deletion_history(history, db)
        completed = True
    finally:
        db.close()
    # Recheck after closing the primary, before returning control to the CLI
    # to serialize and write its output.
    if completed and history is not None:
        assert_deletion_history(history)

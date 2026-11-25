"""Opt-in, numeric-only profiling of semantic qualification setup and audits.

Importing this module performs no IO, model loading or patching. The explicit
context restores every patched alias on exit. Timings are inclusive and may
overlap; operation counts are not counts of distinct assets or bytes.
"""
from contextlib import ExitStack, contextmanager, nullcontext
from functools import wraps
import importlib
import threading
import time
from unittest.mock import patch


_LOCK = threading.Lock()
_OPERATIONS = (
    ("library_semantic_index", "_load_json", "audit_json"),
    ("library_semantic_index", "_load_json_inspector", "audit_json"),
    ("library_semantic_index", "_stat_source", "audit_source_stat"),
    ("library_semantic_index", "_read_vector", "audit_vector_read"),
    ("library_semantic_index", "inspect_checkpoint", "audit_checkpoint_verify"),
    ("app.access.semantic_bulk_vectors", "_cohort_digest", "bulk_cohort"),
    ("app.access.semantic_bulk_vectors", "_read_vector", "bulk_vector_read"),
    ("app.access.semantic_bulk_vectors", "_canonical_components", "bulk_components"),
    ("app.access.semantic_bulk_vectors", "_write_all", "bulk_write"),
    ("app.access.semantic_bulk_vectors", "_hash_published", "bulk_published_hash"),
    ("qualify_multilingual_pilot", "_fixture", "fixture_build"),
    ("app.access.discovery", "scoped_source", "scoped_source"),
    ("app.access.discovery", "digest", "source_digest"),
    ("semantic_coverage_qualification", "_validate_inputs", "coverage_inputs"),
    ("semantic_coverage_qualification", "validate_omission_review", "coverage_review"),
    ("semantic_coverage_qualification", "runtime_policy", "coverage_policy"),
    ("qualify_library_semantic", "_record_digest", "file_hash"),
)


class SetupObserver:
    def __init__(self, journal=None):
        self.journal = journal
        self._lock = threading.Lock()
        self._totals = {name: {"calls": 0, "errors": 0,
            "inclusive_ms": 0.0, "max_ms": 0.0} for _, _, name in _OPERATIONS}

    def wrap(self, name, function):
        @wraps(function)
        def observed(*args, **kwargs):
            started = time.perf_counter_ns()
            error = True
            try:
                result = function(*args, **kwargs)
                error = False
                return result
            finally:
                elapsed = max(0, time.perf_counter_ns() - started) / 1_000_000
                with self._lock:
                    total = self._totals[name]
                    total["calls"] += 1
                    total["errors"] += int(error)
                    total["inclusive_ms"] += elapsed
                    total["max_ms"] = max(total["max_ms"], elapsed)
                if self.journal is not None:
                    # The underlying exception takes priority if persistence
                    # also fails. A successful call must not hide lost evidence.
                    try:
                        self.journal.record_operation(name, elapsed, error=error)
                    except BaseException:
                        if not error:
                            raise
        return observed

    def phase(self, name):
        return self.journal.phase(name) if self.journal is not None else nullcontext()

    def snapshot(self):
        with self._lock:
            return {"schema": "photohouse.semantic_setup_profile.v1",
                "diagnostic_only": True, "qualification_passed": False,
                "timings_are_nested": True, "observer_overhead_included": True,
                "counts_are_operation_calls": True,
                "operations": {name: dict(value) for name, value in self._totals.items()}}


@contextmanager
def instrument_setup(journal=None):
    """Instrument one explicitly invoked harness; refuse overlapping scopes.

    Optional journal heartbeats occur after completed operations, without a
    background worker. A stalled native call retains its durable phase start;
    it does not fabricate completed work or infer acceptance from an output.
    """
    if not _LOCK.acquire(blocking=False):
        raise ValueError("semantic_setup_profile_already_active")
    try:
        observer = SetupObserver(journal)
        with ExitStack() as patches:
            for module_name, attribute, name in _OPERATIONS:
                module = importlib.import_module(module_name)
                patches.enter_context(patch.object(module, attribute,
                    observer.wrap(name, getattr(module, attribute))))
            yield observer
    finally:
        _LOCK.release()

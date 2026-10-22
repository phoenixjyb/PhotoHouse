"""Security and durability checks for semantic qualification progress."""
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

import semantic_qualification_journal as subject


class Clock:
    def __init__(self):
        self.value = 10.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def test_journal_writes_private_fixed_records_and_detached_snapshot(tmp_path):
    clock = Clock()
    output = tmp_path / "journal"
    journal = subject.QualificationJournal(output, clock=clock)
    with journal.phase("initial_audit"):
        clock.advance(1.25)
        journal.record_operation("audit_json", 12.8)
        snapshot = journal.snapshot()
        snapshot["phases"]["initial_audit"]["calls"] = 999
        snapshot["operations"]["audit_json"]["calls"] = 999
        assert journal.snapshot()["phases"]["initial_audit"]["calls"] == 1
        assert journal.snapshot()["operations"]["audit_json"]["calls"] == 1
    journal.close(success=False)

    records = subject.read_checkpoints(output)
    assert [item["event"] for item in records] == [
        "phase_started", "phase_completed", "closed"]
    assert all(item["diagnostic_only"] is True for item in records)
    assert all(item["qualification_passed"] is False for item in records)
    assert records[-1]["status"] == "failed"
    assert records[-1]["operations"]["audit_json"] == {
        "calls": 1, "errors": 0, "inclusive_ms": 12.8, "max_ms": 12.8}
    assert (output / "checkpoint-000001.json").stat().st_mode & 0o777 == 0o600
    assert output.stat().st_mode & 0o777 == 0o700


def test_interrupted_process_leaves_durable_started_phase(tmp_path):
    output = tmp_path / "interrupted-journal"
    code = """import os, sys
sys.path.insert(0, sys.argv[1])
from semantic_qualification_journal import QualificationJournal
journal = QualificationJournal(sys.argv[2])
with journal.phase('initial_audit'):
    os._exit(0)
"""
    completed = subprocess.run([sys.executable, "-c", code,
        str(ROOT / "scripts"), str(output)], cwd=ROOT, check=False)
    assert completed.returncode == 0
    records = subject.read_checkpoints(output)
    assert len(records) == 1
    assert records[0]["event"] == "phase_started"
    assert records[0]["phase"] == "initial_audit"
    assert records[0]["qualification_passed"] is False


def test_interruption_immediately_after_windows_publication_leaves_one_readable_link(tmp_path):
    output = tmp_path / 'interrupted-publication'
    code = """import os,sys
sys.path.insert(0,sys.argv[1])
import semantic_qualification_journal as journal_module
journal_module._WINDOWS_PUBLICATION=True
rename=os.rename
def interrupted_rename(source,destination):
    # Exercise the Windows branch on POSIX without claiming native acceptance.
    assert not os.path.lexists(destination)
    rename(source,destination)
    os._exit(0)
journal_module.os.rename=interrupted_rename
journal=journal_module.QualificationJournal(sys.argv[2])
with journal.phase('initial_audit'):pass
"""
    process = subprocess.run([sys.executable, '-c', code,
        str(ROOT / 'scripts'), str(output)], cwd=ROOT, check=False)
    assert process.returncode == 0
    records = subject.read_checkpoints(output)
    assert len(records) == 1 and records[0]['event'] == 'phase_started'
    assert (output / 'checkpoint-000001.json').stat().st_nlink == 1
    assert len(list(output.iterdir())) == 1


def test_report_completion_is_still_diagnostic_and_pulses_are_throttled(tmp_path):
    output = tmp_path / "complete-report"
    clock = Clock()
    journal = subject.QualificationJournal(output, clock=clock)
    with journal.phase("canary"):
        clock.advance(6)
        journal.record_operation("file_hash", 2.0)
    with journal.phase("report"):
        pass
    journal.close(success=True)
    records = subject.read_checkpoints(output)
    assert any(item["event"] == "progress" and item["completed_units"] == 1
        for item in records)
    assert records[-1]["status"] == "completed"
    assert records[-1]["qualification_passed"] is False
    assert journal.snapshot()["qualification_passed"] is False


def test_failed_phase_remains_latched_after_report_and_successful_close(tmp_path):
    output = tmp_path / "failure-latched"
    journal = subject.QualificationJournal(output)
    with pytest.raises(RuntimeError):
        with journal.phase("fixture"):
            raise RuntimeError("private-failure")
    with journal.phase("report"):
        pass
    journal.close(success=True)
    records = subject.read_checkpoints(output)
    assert records[-1]["status"] == "failed"
    assert records[-1]["qualification_passed"] is False
    assert journal.snapshot()["status"] == "failed"


def test_storage_failure_preserves_prior_checkpoints_and_cleans_temp(tmp_path, monkeypatch):
    output = tmp_path / "storage-failure"
    journal = subject.QualificationJournal(output)
    with journal.phase("initial_audit"):
        pass

    def refuse_link(*_args, **_kwargs):
        raise OSError("sensitive injected detail")

    monkeypatch.setattr(subject.os, "link", refuse_link)
    with pytest.raises(subject.QualificationJournalError):
        with journal.phase("fixture"):
            pass
    assert [item["event"] for item in subject.read_checkpoints(output)] == [
        "phase_started", "phase_completed"]
    assert not list(output.glob("*.tmp"))
    assert not list(output.glob(".*.tmp"))


def test_publication_closes_temporary_descriptor_before_windows_delete(tmp_path, monkeypatch):
    journal = subject.QualificationJournal(tmp_path / 'windows-compatible-publication')
    opened = []
    real_open, real_link = os.open, os.link
    def observe_open(path, flags, *args, **kwargs):
        descriptor = real_open(path, flags, *args, **kwargs)
        if flags & os.O_WRONLY:
            opened.append(descriptor)
        return descriptor
    def windows_link(source, destination, **kwargs):
        assert opened
        # Simulate Windows refusing temporary-name deletion with an open CRT
        # handle. This must hold before either publication filesystem mutation.
        with pytest.raises(OSError):
            os.fstat(opened[-1])
        return real_link(source, destination, **kwargs)
    monkeypatch.setattr(subject.os, 'open', observe_open)
    monkeypatch.setattr(subject.os, 'link', windows_link)
    with journal.phase('initial_audit'):
        pass
    journal.close(success=False)
    assert len(opened) == 3
    assert len(subject.read_checkpoints(journal.directory)) == 3


def test_failed_phase_never_persists_exception_or_caller_text(tmp_path):
    output = tmp_path / "private-fields"
    journal = subject.QualificationJournal(output)
    with pytest.raises(RuntimeError, match="secret-exception-text"):
        with journal.phase("fixture"):
            raise RuntimeError("secret-exception-text")
    journal.close(success=False)
    raw = b"".join(path.read_bytes() for path in sorted(output.glob("checkpoint-*.json")))
    assert b"secret-exception-text" not in raw
    assert b"/Users/" not in raw
    records = subject.read_checkpoints(output)
    assert records[-2]["event"] == "phase_failed"
    assert records[-2]["status"] == "failed"


@pytest.mark.parametrize("bad_phase", ["", "canary ", "secret-phase", None])
def test_phase_names_are_fixed_and_invalid_units_or_operations_refuse(tmp_path, bad_phase):
    journal = subject.QualificationJournal(tmp_path / "invalid-inputs")
    with pytest.raises(subject.QualificationJournalError):
        with journal.phase(bad_phase):
            pass
    with journal.phase("canary"):
        for units in (0, -1, True, 1.5):
            with pytest.raises(subject.QualificationJournalError):
                journal.pulse(units)
        for args in (("private-name", 1), ("file_hash", -1), ("file_hash", float("nan")),
                     ("file_hash", 1, 1)):
            with pytest.raises(subject.QualificationJournalError):
                journal.record_operation(*args)
    journal.close(success=False)


def test_final_record_slot_is_reserved_when_regular_checkpoint_cap_is_reached(
        tmp_path, monkeypatch):
    monkeypatch.setattr(subject, "_MAX_RECORDS", 3)
    output = tmp_path / "reserved-final"
    clock = Clock()
    journal = subject.QualificationJournal(output, clock=clock)
    with journal.phase("initial_audit"):
        pass
    with journal.phase("fixture"):
        pass
    journal.close(success=False)
    records = subject.read_checkpoints(output)
    assert len(records) == 3
    assert records[-1]["event"] == "closed"
    assert [item["sequence"] for item in records] == [1, 2, 3]
    assert journal.snapshot()["dropped_records"] >= 1


def test_rejects_existing_path_symlink_and_non_private_published_file(tmp_path):
    output = tmp_path / "existing"
    output.mkdir(mode=0o700)
    with pytest.raises(subject.QualificationJournalError):
        subject.QualificationJournal(output)

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks unavailable")
    with pytest.raises(subject.QualificationJournalError):
        subject.QualificationJournal(alias / "journal")

    journal_dir = tmp_path / "journal"
    journal = subject.QualificationJournal(journal_dir)
    journal.close(success=False)
    (journal_dir / "checkpoint-000001.json").chmod(0o644)
    with pytest.raises(subject.QualificationJournalError):
        subject.read_checkpoints(journal_dir)


def test_refuses_overwrite_and_malformed_published_checkpoint(tmp_path):
    output = tmp_path / "one-shot"
    journal = subject.QualificationJournal(output)
    journal.close(success=False)
    before = subject.read_checkpoints(output)
    with pytest.raises(subject.QualificationJournalError):
        subject.QualificationJournal(output)
    assert subject.read_checkpoints(output) == before

    path = output / "checkpoint-000001.json"
    value = json.loads(path.read_text())
    value["phase"] = "private-caller-phase"
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    with pytest.raises(subject.QualificationJournalError):
        subject.read_checkpoints(output)


def test_reader_ignores_only_bounded_private_temp_remnants(tmp_path):
    output = tmp_path / "temp-remnant"
    journal = subject.QualificationJournal(output)
    journal.close(success=False)
    orphan = output / (".checkpoint-000002.json." + "a" * 32 + ".tmp")
    descriptor = os.open(orphan, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(b"incomplete")
    assert len(subject.read_checkpoints(output)) == 1
    orphan.unlink()
    assert len(subject.read_checkpoints(output)) == 1


def test_module_import_has_no_journal_io_or_model_imports(tmp_path):
    code = """import sys
sys.path.insert(0, sys.argv[1])
before = set(sys.modules)
import semantic_qualification_journal
assert 'serve_semantic_text' not in set(sys.modules) - before
assert 'semantic_openclip' not in set(sys.modules) - before
"""
    completed = subprocess.run([sys.executable, "-c", code,
        str(ROOT / "scripts")], cwd=tmp_path, check=False)
    assert completed.returncode == 0
    assert list(tmp_path.iterdir()) == []


def test_operation_callbacks_and_snapshots_are_thread_safe(tmp_path):
    journal = subject.QualificationJournal(tmp_path / "threaded")
    failures = []
    with journal.phase("source_projection"):
        def observe():
            try:
                for _ in range(40):
                    journal.record_operation("scoped_source", 0.75)
                    journal.snapshot()
            except BaseException as error:
                failures.append(error)

        workers = [threading.Thread(target=observe) for _ in range(5)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
    assert not failures
    journal.close(success=False)
    final = subject.read_checkpoints(tmp_path / "threaded")[-1]
    assert final["operations"]["scoped_source"] == {
        "calls": 200, "errors": 0, "inclusive_ms": 150.0, "max_ms": 0.75}
    assert final["completed_units"] == 200


def test_many_submillisecond_operations_preserve_persisted_total(tmp_path):
    output = tmp_path / "submillisecond"
    journal = subject.QualificationJournal(output)
    with journal.phase("artifact_validation"):
        for _ in range(1000):
            journal.record_operation("audit_vector_read", 0.01)
    journal.close(success=False)
    saved = subject.read_checkpoints(output)[-1]["operations"]["audit_vector_read"]
    assert saved["calls"] == 1000
    assert saved["inclusive_ms"] > 0
    assert math.isclose(saved["inclusive_ms"], 10.0, rel_tol=0, abs_tol=1e-9)
    assert saved["max_ms"] == 0.01


def test_reader_rejects_nonfinite_or_inconsistent_operation_totals(tmp_path):
    output = tmp_path / "bad-operation-total"
    journal = subject.QualificationJournal(output)
    journal.close(success=False)
    checkpoint = output / "checkpoint-000001.json"
    value = json.loads(checkpoint.read_text())
    value["operations"]["file_hash"] = {
        "calls": 1, "errors": 0, "inclusive_ms": 0.5, "max_ms": 0.6}
    checkpoint.write_text(json.dumps(value))
    checkpoint.chmod(0o600)
    with pytest.raises(subject.QualificationJournalError):
        subject.read_checkpoints(output)

    value["operations"]["file_hash"]["inclusive_ms"] = float("inf")
    value["operations"]["file_hash"]["max_ms"] = 0.5
    checkpoint.write_text(json.dumps(value))
    checkpoint.chmod(0o600)
    with pytest.raises(subject.QualificationJournalError):
        subject.read_checkpoints(output)

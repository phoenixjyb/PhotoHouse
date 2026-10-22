"""Result-neutral, private setup observation over generated calls only."""
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

import semantic_setup_profile as subject
import library_semantic_index as index


def test_scoped_alias_restored_and_sensitive_arguments_never_retained(monkeypatch):
    secret = "private-family-path-query-and-identity"
    sentinel = object()
    calls = []
    def load(*args, **kwargs):
        calls.append((args, kwargs))
        return sentinel
    monkeypatch.setattr(index, "_load_json", load)
    with subject.instrument_setup() as observer:
        assert index._load_json(secret, 42) is sentinel
        assert calls == [((secret, 42), {})]
        report = observer.snapshot()
        assert report['operations']['audit_json']['calls'] == 1
        assert report['operations']['audit_json']['errors'] == 0
        assert secret not in json.dumps(report)
        report['operations']['audit_json']['calls'] = 999
        assert observer.snapshot()['operations']['audit_json']['calls'] == 1
        with pytest.raises(ValueError, match='already_active'):
            with subject.instrument_setup():
                pytest.fail('overlapping patches entered')
    assert index._load_json is load


def test_failure_counted_original_exception_and_restoration(monkeypatch):
    failure = RuntimeError('sensitive exception text')
    def refuse(*args, **kwargs):
        raise failure
    monkeypatch.setattr(index, '_load_json', refuse)
    with pytest.raises(RuntimeError) as error:
        with subject.instrument_setup() as observer:
            index._load_json('sensitive path', 1)
    assert error.value is failure
    assert index._load_json is refuse
    report = observer.snapshot()
    assert report['operations']['audit_json']['errors'] == 1
    assert 'sensitive' not in json.dumps(report)


def test_heartbeat_storage_failure_cannot_replace_operation_failure():
    class BrokenJournal:
        def record_operation(self, *args, **kwargs):
            raise OSError('checkpoint write refused')
    observer = subject.SetupObserver(BrokenJournal())
    underlying = RuntimeError('original failure')
    def refuse():
        raise underlying
    with pytest.raises(RuntimeError) as error:
        observer.wrap('audit_json', refuse)()
    assert error.value is underlying
    with pytest.raises(OSError, match='checkpoint write refused'):
        observer.wrap('audit_json', lambda: 123)()


def test_partial_instrumentation_failure_restores_earlier_aliases(monkeypatch):
    original = index._load_json
    monkeypatch.setattr(subject, '_OPERATIONS', (
        ('library_semantic_index', '_load_json', 'audit_json'),
        ('library_semantic_index', 'missing_fixture_attribute', 'file_hash')))
    with pytest.raises(AttributeError):
        with subject.instrument_setup():
            pytest.fail('incomplete instrumentation entered')
    assert index._load_json is original
    # The lock was also released after setup failed.
    monkeypatch.setattr(subject, '_OPERATIONS', ())
    with subject.instrument_setup():
        pass

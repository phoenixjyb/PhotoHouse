"""Synthetic parity and cancellation contracts for the opt-in native kernel."""
from pathlib import Path
import importlib.util
import json
import random
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
from app.access import photo_stack_index as builder
from app.access.photo_stack_reference import group_items

NATIVE = importlib.util.find_spec('photohouse_photo_stack') is not None


def row(i, hash='0000000000000000', time='2026-10-22T08:00:00Z', account=None, batch=None):
    return (i, 'image/jpeg', 'generated', 1, 1, time, hash, account, batch)


def test_characterization_reference_records_success_and_budget_refusal():
    payload = json.dumps({'items': [['ffffffffffffffff', '-1', True, None, None, None, False]] * 2,
                          'maximum_comparisons': 1})
    assert json.loads(group_items(payload)) == [[[0, 1], 'near_capture']]
    with pytest.raises(ValueError, match='pair comparison budget exceeded'):
        group_items(payload.replace('"maximum_comparisons": 1', '"maximum_comparisons": 0'))
    for invalid in ('', '{}', 'null'):
        with pytest.raises(ValueError, match='invalid photo-stack kernel input'):
            group_items(invalid)


def test_selected_missing_native_engine_is_actionable(monkeypatch):
    from app.access import photo_stack_acceleration as acceleration
    monkeypatch.setenv('PHOTOHOUSE_PHOTO_STACK_ENGINE', 'rust')
    def missing(_name):
        raise ImportError('synthetic unavailable extension')
    monkeypatch.setattr(acceleration.importlib, 'import_module', missing)
    with pytest.raises(RuntimeError, match='selected but unavailable'):
        builder.build_library_photo_stacks([row(1)])


def test_incompatible_native_policy_is_rejected_before_grouping(monkeypatch):
    from app.access import photo_stack_acceleration as acceleration
    from types import SimpleNamespace
    monkeypatch.setenv('PHOTOHOUSE_PHOTO_STACK_ENGINE', 'rust')
    monkeypatch.setattr(acceleration.importlib, 'import_module', lambda _name: SimpleNamespace(
        KERNEL_VERSION=1, POLICY_FINGERPRINT='different-policy'))
    with pytest.raises(RuntimeError, match='Incompatible Rust photo-stack engine'):
        builder.build_library_photo_stacks([row(1)])


@pytest.mark.skipif(not NATIVE, reason='build the optional native extension for native parity')
def test_native_matches_reference_on_deterministic_mixed_fixtures(monkeypatch):
    rng = random.Random(20261120)
    times = [None, '2026-10-22', '2026-10-23', '1969-12-31T23:59:59.999999Z',
             '2026-10-22T08:00:00Z', '2026-10-22T10:05:00+02:00',
             '2026-10-22T08:05:00.000001Z', '2026-10-22 08:00:00',
             '0001-01-01T00:00:00+01:00', '9999-12-31T23:59:59-01:00']
    fixtures = [[row(2**63 - 1), row(2**63 - 2)]]
    fixtures += [[row(i, time=None, account='家人😀', batch='batch') for i in range(1, 80)]]
    fixtures += [[row(1, time=None, account='\ud800', batch='a'),
                  row(2, time=None, account='\ud800', batch='a')]]
    for _ in range(100):
        fixtures.append([row(i, f'{rng.getrandbits(rng.choice([0, 8, 64])):016x}',
                             rng.choice(times), rng.choice([None, 'a', 'b', ' 家人😀 ']),
                             rng.choice([None, 'x', 'y'])) for i in range(1, rng.randrange(2, 100))])
    for rows in fixtures:
        monkeypatch.setenv('PHOTOHOUSE_PHOTO_STACK_ENGINE', 'python')
        expected = builder.build_library_photo_stacks(rows)
        monkeypatch.setenv('PHOTOHOUSE_PHOTO_STACK_ENGINE', 'rust')
        assert builder.build_library_photo_stacks(rows) == expected


@pytest.mark.skipif(not NATIVE, reason='build the optional native extension for native parity')
def test_native_preserves_budget_cancellation_and_callback_exception(monkeypatch):
    monkeypatch.setenv('PHOTOHOUSE_PHOTO_STACK_ENGINE', 'rust')
    rows = [row(i) for i in range(1, 101)]
    with pytest.raises(ValueError, match='pair comparison budget exceeded'):
        builder.build_library_photo_stacks(rows, maximum_comparisons=0)
    calls = 0
    def stopped():
        nonlocal calls
        calls += 1
        return calls > 120
    with pytest.raises(builder.PhotoStackCancelled, match='photo_stack_refresh_cancelled'):
        builder.build_library_photo_stacks(rows, stopped=stopped)
    assert calls == 121
    calls = 0
    def broken():
        nonlocal calls
        calls += 1
        if calls > 105:
            raise LookupError('exact callback error')
        return False
    with pytest.raises(LookupError, match='exact callback error'):
        builder.build_library_photo_stacks(rows, stopped=broken)


@pytest.mark.skipif(not NATIVE, reason='build the optional native extension for native parity')
def test_native_honors_changed_live_policy_via_reference(monkeypatch):
    from app.access import photo_stacks
    monkeypatch.setenv('PHOTOHOUSE_PHOTO_STACK_ENGINE', 'rust')
    monkeypatch.setattr(photo_stacks, 'GROUP_LIMIT', 2)
    assert [g['count'] for g in builder.build_library_photo_stacks([row(i) for i in range(1, 7)])] == [2, 2, 2]


@pytest.mark.skipif(not NATIVE, reason='build the optional native extension for native parity')
def test_20k_native_fixture_preserves_exact_comparison_budget(monkeypatch):
    monkeypatch.setenv('PHOTOHOUSE_PHOTO_STACK_ENGINE', 'rust')
    rng = random.Random(20261022)
    rows = [row(i, f'{rng.getrandbits(64):016x}') for i in range(1, 20001)]
    assert builder.build_library_photo_stacks(rows, maximum_comparisons=1993226) == []
    with pytest.raises(ValueError, match='pair comparison budget exceeded'):
        builder.build_library_photo_stacks(rows, maximum_comparisons=1993225)

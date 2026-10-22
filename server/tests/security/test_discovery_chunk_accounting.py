"""Exact, bounded accounting for SQLite discovery row chunks."""
import math
import random
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.access import discovery as d


def test_generated_safe_chunks_equal_the_sum_of_individually_packed_rows():
    rng = random.Random(481516)
    alphabet = ("a", "\"", "\\", "\x00", "\x1f", "\x7f", "é", "中", "𝄞", "\ud800")
    strings = ["".join(rng.choice(alphabet) for _ in range(rng.randrange(9))) for _ in range(160)]
    values = [None, -(2**63), 2**63 - 1, -1, 0, 1,
              0.0, -0.0, sys.float_info.max, -sys.float_info.max,
              math.ulp(0.0), -math.ulp(0.0), *strings]
    rows = [
        (),
        ("", '"\\', "\x00\x1f\x7f", "é", "中", "𝄞", "\ud800"),
        (-(2**63), 2**63 - 1, sys.float_info.max, -sys.float_info.max,
         math.ulp(0.0), -math.ulp(0.0), None),
    ]
    for index in range(257):
        count = index % 8
        rows.append(tuple(values[(index * 17 + cell * 23) % len(values)]
                          for cell in range(count)))

    for start in range(0, len(rows), 128):
        chunk = rows[start:start + 128]
        expected = sum(len(d.packed(row)) for row in chunk)
        assert d._packed_chunk_size(chunk, d._ACCOUNTING_CHUNK_BYTES) == expected

    assert d._packed_chunk_size([], d._ACCOUNTING_CHUNK_BYTES) is None
    assert d._packed_chunk_size([()], d._ACCOUNTING_CHUNK_BYTES) == len(d.packed(()))


@pytest.mark.parametrize("chunk", [
    [(True,)],
    [(b"binary",)],
    [([1, 2],)],
    [(2**63,)],
    [(-(2**63) - 1,)],
    [(float("inf"),)],
    [(float("nan"),)],
    [("ok",) * 33],
    [tuple("x" for _ in range(33))],
])
def test_unsafe_cell_types_values_and_wide_rows_use_fallback(chunk):
    assert d._packed_chunk_size(chunk, d._ACCOUNTING_CHUNK_BYTES) is None


def test_oversized_chunk_is_rejected_before_json_serialization():
    chunk = [("x" * 180_000,)]
    with patch.object(d, "packed", wraps=d.packed) as pack:
        assert d._packed_chunk_size(chunk, 1024 * 1024) is None
        pack.assert_not_called()


def test_chunk_remaining_budget_gate_uses_conservative_encoded_bound():
    chunk = [(None,), (None,)]
    encoded_bound = sum(len(d.packed(row)) for row in chunk) + len(chunk) + 1
    assert d._packed_chunk_size(chunk, encoded_bound) == sum(len(d.packed(row)) for row in chunk)
    assert d._packed_chunk_size(chunk, encoded_bound - 1) is None
    assert d._packed_chunk_size(chunk, d._ACCOUNTING_CHUNK_BYTES + 1) == sum(
        len(d.packed(row)) for row in chunk)


def test_read_budget_exact_byte_limit_and_one_byte_less_use_real_sqlite_rows():
    rows = [(None,), ("x",), (-2**63,), (2**63 - 1,)]
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE items (value)")
    db.executemany("INSERT INTO items(value) VALUES (?)", rows)
    expected = sum(len(d.packed(row)) for row in rows)

    exact = d.ReadBudget(rows=len(rows), source_bytes=expected, seconds=30)
    with exact.attempt(db, lambda: False) as (_check, read):
        assert read("SELECT value FROM items ORDER BY rowid", ()) == rows

    short = d.ReadBudget(rows=len(rows), source_bytes=expected - 1, seconds=30)
    with short.attempt(db, lambda: False) as (_check, read):
        with pytest.raises(d.DiscoveryUnavailable):
            read("SELECT value FROM items ORDER BY rowid", ())
    db.close()


def test_read_budget_uses_bounded_chunk_path_and_preserves_row_limit_and_cancel_checks():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE items (value)")
    db.executemany("INSERT INTO items(value) VALUES (?)", ((index,) for index in range(128)))
    budget = d.ReadBudget(rows=128, source_bytes=64 * 1024, seconds=30, concurrency=1)
    assert budget.search_view().slots is budget.slots
    with budget.attempt(db, lambda: False) as (_check, read):
        with patch.object(d, "packed", wraps=d.packed) as pack:
            assert len(read("SELECT value FROM items ORDER BY rowid", ())) == 128
            assert pack.call_count == 1

    limited = d.ReadBudget(rows=127, source_bytes=64 * 1024, seconds=30)
    with limited.attempt(db, lambda: False) as (_check, read):
        with patch.object(d, "packed", wraps=d.packed) as pack:
            with pytest.raises(d.DiscoveryUnavailable):
                read("SELECT value FROM items ORDER BY rowid", ())
            pack.assert_not_called()

    checks = 0

    def cancel_after_fetch():
        nonlocal checks
        checks += 1
        return checks == 2

    with budget.attempt(db, cancel_after_fetch) as (_check, read):
        with patch.object(d, "packed", wraps=d.packed) as pack:
            with pytest.raises(d.DiscoveryCancelled):
                read("SELECT value FROM items ORDER BY rowid", ())
            pack.assert_not_called()
    assert checks == 2
    # Cancellation still releases the same single admission slot.
    with budget.attempt(db, lambda: False) as (_check, read):
        assert read("SELECT value FROM items LIMIT 1", ()) == [(0,)]
    db.close()


def test_unsupported_sqlite_values_keep_original_discovery_invalid_behavior():
    db = sqlite3.connect(":memory:")
    budget = d.ReadBudget(rows=4, source_bytes=4096, seconds=30)
    for query in ("SELECT X'00'", "SELECT 1e999"):
        with budget.attempt(db, lambda: False) as (_check, read):
            with pytest.raises(d.DiscoveryInvalid):
                read(query, ())
    db.close()


def test_large_but_supported_sqlite_text_falls_back_and_is_counted_exactly():
    text = "x" * 180_000
    db = sqlite3.connect(":memory:")
    budget = d.ReadBudget(rows=1, source_bytes=256 * 1024, seconds=30)
    with budget.attempt(db, lambda: False) as (_check, read):
        assert read("SELECT ?", (text,)) == [(text,)]
    db.close()

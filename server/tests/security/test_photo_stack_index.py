import random

import pytest

from app.access.photo_stack_index import _CandidateIndex, build_library_photo_stacks
from app.access.photo_stacks import build_photo_stacks


def row(asset_id, phash='0000000000000000', captured='2026-01-01 12:00:00',
        account=None, batch=None, mime='image/jpeg'):
    return (asset_id, mime, 'name.jpg', 1, 1, captured, phash, account, batch)


def test_cross_page_library_groups_preserve_gallery_order_and_split_at_24():
    rows = [row(i, captured='2026-01-01T12:00:00Z') for i in range(130, 10, -1)]

    groups = build_library_photo_stacks(rows)

    assert [group['count'] for group in groups] == [24] * 5
    assert groups[0] == {
        'id': '107', 'cover_asset_id': '130',
        'asset_ids': [str(i) for i in range(130, 106, -1)],
        'count': 24, 'reason': 'near_capture',
    }
    assert all(group['count'] <= 24 for group in groups)


def test_complete_link_prevents_transitive_bridging():
    rows = [
        row(1, '0000000000000000'),
        row(2, '000000000000003f'),  # distance 6 from first
        row(3, '0000000000000fff'),  # within 6 of second, farther from first
    ]

    groups = build_library_photo_stacks(rows)

    assert groups == [{
        'id': '1', 'cover_asset_id': '1', 'asset_ids': ['1', '2'],
        'count': 2, 'reason': 'near_capture',
    }]


def test_near_capture_normalizes_aware_offsets_and_keeps_naive_domain_separate():
    groups = build_library_photo_stacks([
        row(1, captured='2026-01-01T12:00:00+02:00'),
        row(2, captured='2026-01-01T10:05:00Z'),
        row(3, captured='2026-01-01 10:05:00'),
    ])

    assert [group['asset_ids'] for group in groups] == [['1', '2']]


def test_same_upload_fallback_uses_hash_and_date_veto():
    groups = build_library_photo_stacks([
        row(1, '0000000000000000', '2026-01-01', 'acct', 'batch'),
        row(2, '0000000000000003', '2026-01-01', 'acct', 'batch'),
        row(3, '0000000000000000', '2026-01-02', 'acct', 'batch'),
        row(4, '0000000000000000', None, 'acct', 'batch'),
    ])

    assert groups == [{
        'id': '1', 'cover_asset_id': '1', 'asset_ids': ['1', '2', '4'],
        'count': 3, 'reason': 'same_upload',
    }]


def test_dense_repeated_hashes_remove_full_groups_from_candidate_index():
    rows = [row(i, captured='2026-04-05T08:00:00Z') for i in range(1, 2001)]

    groups = build_library_photo_stacks(rows, maximum_comparisons=50000)

    assert sum(group['count'] for group in groups) == 2000
    assert len(groups) == (2000 + 23) // 24
    assert max(group['count'] for group in groups) == 24


def test_unknown_day_uses_upload_prefix_index_not_global_mapping_scan(monkeypatch):
    class IterationCountingDict(dict):
        items_calls = 0

        def items(self):
            type(self).items_calls += 1
            return super().items()

    original_init = _CandidateIndex.__init__

    def instrumented_init(index):
        original_init(index)
        index.upload = IterationCountingDict()

    monkeypatch.setattr(_CandidateIndex, '__init__', instrumented_init)
    rows = [row(i, captured=None, account=f'acct-{i}', batch=f'batch-{i}')
            for i in range(1, 501)]

    assert build_library_photo_stacks(rows) == []
    assert IterationCountingDict.items_calls == 0


def test_index_matches_page_local_builder_on_deterministic_small_fixtures():
    rng = random.Random(9173)
    rows = []
    asset_id = 1
    for block in range(7):
        base = rng.getrandbits(64)
        for _ in range(8):
            phash = base
            for bit in rng.sample(range(64), rng.randrange(0, 4)):
                phash ^= 1 << bit
            captured = f'2026-06-01T{block:02d}:00:00Z'
            rows.append(row(asset_id, f'{phash:016x}', captured))
            asset_id += 1
    for batch_no in range(4):
        for _ in range(5):
            rows.append(row(asset_id, f'{rng.getrandbits(64):016x}', None,
                            f'acct-{batch_no}', f'batch-{batch_no}'))
            asset_id += 1

    assert len(rows) <= 100
    assert build_library_photo_stacks(rows) == build_photo_stacks(rows)['groups']


def test_invalid_assets_are_ignored_but_duplicate_ids_and_asset_cap_refuse_build():
    assert build_library_photo_stacks([
        row(1, mime='video/mp4'), row(2, phash='bad'),
    ]) == []
    with pytest.raises(ValueError, match='duplicate asset ID'):
        build_library_photo_stacks([row(1), row(1, mime='video/mp4')])
    with pytest.raises(ValueError, match='asset limit'):
        build_library_photo_stacks([row(1), row(2)], maximum_assets=1)


def test_comparison_budget_exhaustion_refuses_whole_build():
    with pytest.raises(ValueError, match='comparison budget'):
        build_library_photo_stacks([row(1), row(2)], maximum_comparisons=0)


def test_unrepresentable_aware_capture_time_stays_unmatched_without_aborting():
    groups = build_library_photo_stacks([
        row(1, captured='0001-01-01T00:00:00+14:00'),
        row(2, captured='2026-01-01T12:00:00Z'),
        row(3, captured='2026-01-01T12:00:00Z'),
    ])

    assert [group['asset_ids'] for group in groups] == [['2', '3']]

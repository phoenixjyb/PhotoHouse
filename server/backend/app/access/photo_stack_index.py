"""Bounded pure whole-library photo stack suggestions.

The caller supplies one already-authorized library snapshot in gallery order.
This module deliberately has no database, filesystem, or model access.
"""
from datetime import datetime, timezone

from . import photo_stacks as _policy
from .photo_stack_reference.algorithm import (
    _bands, _band_variants, _CandidateIndex, _build_prepared,
)


_MAX_ID = 2**63 - 1
_EPOCH_NAIVE = datetime(1970, 1, 1)
_EPOCH_UTC = datetime(1970, 1, 1, tzinfo=timezone.utc)


def grouping_policy_fingerprint():
    """Return the exact pure grouping policy that affects index contents."""
    return {
        'algorithm_version': _policy.GROUPING_ALGORITHM_VERSION,
        'near_capture_hash_max_distance': _policy.NEAR_CAPTURE_HASH_MAX_DISTANCE,
        'same_upload_hash_max_distance': _policy.SAME_UPLOAD_HASH_MAX_DISTANCE,
        'capture_window_seconds': _policy.CAPTURE_WINDOW_SECONDS,
        'group_limit': _policy.GROUP_LIMIT,
    }


class PhotoStackCancelled(RuntimeError):
    """An explicitly stopped build must not publish a partial index."""


def check_stopped(stopped):
    if stopped is not None and stopped():
        raise PhotoStackCancelled('photo_stack_refresh_cancelled')


def _time_bucket(value):
    """Return (domain, five-minute bucket), normalizing aware times to UTC."""
    if value.utcoffset() is None:
        delta = value - _EPOCH_NAIVE
        micros = ((delta.days * 86400 + delta.seconds) * 1_000_000
                  + delta.microseconds)
        return 'naive', micros // 300_000_000
    try:
        normalized = value.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError('capture time cannot be normalized safely') from exc
    delta = normalized - _EPOCH_UTC
    micros = ((delta.days * 86400 + delta.seconds) * 1_000_000
              + delta.microseconds)
    return 'aware', micros // 300_000_000


def build_library_photo_stacks(rows, *, maximum_assets=100000,
                               maximum_comparisons=10000000, stopped=None):
    """Build deterministic complete-link stacks across one authorized library.

    Candidate discovery stores ``floor(r / 2) + 1`` exact pHash bands for an
    inclusive distance threshold ``r`` and probes exact plus one-bit variants.
    If every band differed by more than one bit, at least ``2 * bands`` bits
    would differ overall, which exceeds ``r``; therefore every eligible pair
    shares a probed key. Every tested pair consumes the comparison budget;
    exceeding it rejects the whole build with ``ValueError``.
    """
    if stopped is not None and not callable(stopped):
        raise ValueError('stopped must be callable')
    check_stopped(stopped)
    if type(maximum_assets) is not int or maximum_assets < 0:
        raise ValueError('maximum_assets must be a nonnegative integer')
    if type(maximum_comparisons) is not int or maximum_comparisons < 0:
        raise ValueError('maximum_comparisons must be a nonnegative integer')
    if type(rows) not in (list, tuple):
        raise ValueError('rows must be a list or tuple')
    if len(rows) > maximum_assets:
        raise ValueError('library asset limit exceeded')

    prepared = []
    seen_ids = set()
    for row in rows:
        check_stopped(stopped)
        if not isinstance(row, (list, tuple)):
            continue
        if row and type(row[0]) is int and 1 <= row[0] <= _MAX_ID:
            if row[0] in seen_ids:
                raise ValueError('duplicate asset ID')
            seen_ids.add(row[0])
        if len(row) < 9:
            continue
        asset_id, mime = row[0], row[1]
        phash = _policy._hash(row[6])
        if (type(asset_id) is not int or not 1 <= asset_id <= _MAX_ID
                or type(mime) is not str or not mime.startswith('image/')
                or phash is None):
            continue
        capture_time = _policy._capture_time(row[5])
        account, batch = row[7:9]
        item = {
            'id': asset_id,
            'capture_time': capture_time,
            'capture_day': _policy._capture_day(row[5]),
            'phash': phash,
            'upload_account': account if type(account) is str and account.strip() else None,
            'upload_batch': batch if type(batch) is str and batch.strip() else None,
        }
        try:
            item['time_bucket'] = _time_bucket(capture_time) if capture_time is not None else None
        except ValueError:
            # The page-local helper treats unnormalizable datetimes as
            # unmatchable; keep the asset but do not index it for grouping.
            item['time_bucket'] = None
            item['unmatchable_time'] = True
        prepared.append(item)

    from .photo_stack_acceleration import build_accelerated
    accelerated = build_accelerated(prepared, maximum_comparisons, stopped)
    if accelerated is not None:
        return accelerated
    return _build_prepared(prepared, maximum_comparisons, stopped)

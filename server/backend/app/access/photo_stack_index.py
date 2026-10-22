"""Bounded pure whole-library photo stack suggestions.

The caller supplies one already-authorized library snapshot in gallery order.
This module deliberately has no database, filesystem, or model access.
"""
from datetime import datetime, timezone

from . import photo_stacks as _policy


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


def _bands(value, count):
    """Return disjoint bit bands for lossless bounded-distance lookup."""
    width, extra = divmod(64, count)
    result = []
    offset = 0
    for i in range(count):
        size = width + (1 if i < extra else 0)
        result.append((i, (value >> offset) & ((1 << size) - 1)))
        offset += size
    return tuple(result)


def _band_variants(part, band, count):
    """Return an exact band value and each value one bit away from it."""
    width, extra = divmod(64, count)
    size = width + (1 if band < extra else 0)
    return (part, *(part ^ (1 << bit) for bit in range(size)))


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


class _CandidateIndex:
    def __init__(self):
        self.near = {}
        self.upload = {}
        self.upload_any_day = {}

    @staticmethod
    def _add(mapping, key, cluster_id):
        mapping.setdefault(key, set()).add(cluster_id)

    def keys_for(self, item):
        keys = []
        hash_near = _bands(item['phash'],
                           _policy.NEAR_CAPTURE_HASH_MAX_DISTANCE // 2 + 1)
        if item['capture_time'] is not None:
            domain, bucket = item['time_bucket']
            for band, part in hash_near:
                keys.append(('n', domain, bucket, band, part))
        # _pair_reason only consults upload metadata when both times are absent.
        if (item['capture_time'] is None and item['upload_account']
                and item['upload_batch']):
            for band, part in _bands(
                    item['phash'], _policy.SAME_UPLOAD_HASH_MAX_DISTANCE // 2 + 1):
                keys.append(('u', item['upload_account'], item['upload_batch'],
                             band, part, item['capture_day']))
        return tuple(keys)

    def add(self, item, cluster_id):
        keys = self.keys_for(item)
        for key in keys:
            mapping = self.near if key[0] == 'n' else self.upload
            self._add(mapping, key, cluster_id)
            if key[0] == 'u':
                self._add(self.upload_any_day, key[:-1], cluster_id)
        return keys

    def candidates(self, item):
        ids = set()
        if item['capture_time'] is not None:
            domain, bucket = item['time_bucket']
            bucket_span = (_policy.CAPTURE_WINDOW_SECONDS + 299) // 300
            for band, part in _bands(
                    item['phash'], _policy.NEAR_CAPTURE_HASH_MAX_DISTANCE // 2 + 1):
                for variant in _band_variants(
                        part, band, _policy.NEAR_CAPTURE_HASH_MAX_DISTANCE // 2 + 1):
                    for neighbor in range(bucket - bucket_span,
                                          bucket + bucket_span + 1):
                        ids.update(self.near.get(
                            ('n', domain, neighbor, band, variant), ()))
        elif item['upload_account'] and item['upload_batch']:
            count = _policy.SAME_UPLOAD_HASH_MAX_DISTANCE // 2 + 1
            for band, part in _bands(item['phash'], count):
                for variant in _band_variants(part, band, count):
                    prefix = ('u', item['upload_account'], item['upload_batch'],
                              band, variant)
                    if item['capture_day'] is None:
                        # Unknown day may pair with every recorded day. Keep
                        # an account/batch/band index so this lookup is
                        # independent of unrelated upload metadata elsewhere.
                        ids.update(self.upload_any_day.get(prefix, ()))
                    else:
                        ids.update(self.upload.get(prefix + (item['capture_day'],), ()))
                        ids.update(self.upload.get(prefix + (None,), ()))
        return ids

    def remove_cluster(self, cluster_id, keys):
        for key in keys:
            mapping = self.near if key[0] == 'n' else self.upload
            found = mapping.get(key)
            if found is not None:
                found.discard(cluster_id)
                if not found:
                    del mapping[key]
            if key[0] == 'u':
                any_day = self.upload_any_day.get(key[:-1])
                if any_day is not None:
                    any_day.discard(cluster_id)
                    if not any_day:
                        del self.upload_any_day[key[:-1]]


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

    clusters = []
    indexed_keys = []
    index = _CandidateIndex()
    comparisons = 0
    for item in prepared:
        check_stopped(stopped)
        if item.get('unmatchable_time'):
            clusters.append({'members': [item], 'reason': None})
            indexed_keys.append([])
            continue
        selected = None
        for cluster_id in sorted(index.candidates(item)):
            check_stopped(stopped)
            cluster = clusters[cluster_id]
            if len(cluster['members']) >= _policy.GROUP_LIMIT:
                continue
            relation = None
            eligible = True
            for member in cluster['members']:
                comparisons += 1
                if comparisons > maximum_comparisons:
                    raise ValueError('pair comparison budget exceeded')
                pair_relation = _policy._pair_reason(item, member)
                if pair_relation is None or (relation is not None and pair_relation != relation):
                    eligible = False
                    break
                relation = pair_relation
            if (eligible and relation is not None
                    and (cluster['reason'] is None or cluster['reason'] == relation)):
                selected = cluster_id
                cluster['reason'] = relation
                cluster['members'].append(item)
                indexed_keys[selected].extend(index.add(item, selected))
                if len(cluster['members']) == _policy.GROUP_LIMIT:
                    index.remove_cluster(selected, indexed_keys[selected])
                break
        if selected is None:
            cluster_id = len(clusters)
            clusters.append({'members': [item], 'reason': None})
            indexed_keys.append(list(index.add(item, cluster_id)))

    groups = []
    for cluster in clusters:
        check_stopped(stopped)
        members = cluster['members']
        if len(members) < 2:
            continue
        asset_ids = [str(member['id']) for member in members]
        groups.append({
            'id': str(min(member['id'] for member in members)),
            'cover_asset_id': asset_ids[0],
            'asset_ids': asset_ids,
            'count': len(asset_ids),
            'reason': cluster['reason'],
        })
    return groups

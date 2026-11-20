"""Unchanged Python candidate-index and complete-link reference algorithm."""
from .. import photo_stacks as _policy


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



def _build_prepared(prepared, maximum_comparisons, stopped=None):
    """Python reference after validation; also used by native parity recording."""
    from ..photo_stack_index import check_stopped
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

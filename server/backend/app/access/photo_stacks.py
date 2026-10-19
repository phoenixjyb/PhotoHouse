"""Pure, conservative page-local photo stack suggestions.

No database, filesystem, model, or mutation access belongs in this module. The
caller supplies already authorized gallery rows from one database snapshot.
"""
from datetime import datetime, timezone
import re


_FULL_CAPTURE_TIME = re.compile(
    r'\A[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}'
    r'(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})?\Z', re.ASCII)
_RECORDED_DAY = re.compile(r'\A([0-9]{4}-[0-9]{2}-[0-9]{2})(?:[ T].*)?\Z', re.ASCII)
_PHASH = re.compile(r'\A[0-9a-fA-F]{16}\Z', re.ASCII)


def _capture_time(value):
    """Parse only a full recorded datetime; date-only values are unknown."""
    if type(value) is not str or not _FULL_CAPTURE_TIME.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + '+00:00' if value.endswith('Z') else value)
    except ValueError:
        return None
    return parsed


def _capture_day(value):
    """Retain a valid recorded calendar date even when time precision is absent."""
    if type(value) is not str:
        return None
    match = _RECORDED_DAY.fullmatch(value)
    if match is None:
        return None
    try:
        return datetime.fromisoformat(match.group(1)).date()
    except ValueError:
        return None


def _hash(value):
    if type(value) is not str or not _PHASH.fullmatch(value):
        return None
    return int(value, 16)


def _pair_reason(left, right):
    """Return the one relation supported by both items, or no relation."""
    left_time, right_time = left['capture_time'], right['capture_time']
    if left_time is not None and right_time is not None:
        if (left['phash'] ^ right['phash']).bit_count() > 6:
            return None
        left_aware = left_time.utcoffset() is not None
        right_aware = right_time.utcoffset() is not None
        if left_aware != right_aware:
            return None
        if left_aware:
            try:
                left_time = left_time.astimezone(timezone.utc)
                right_time = right_time.astimezone(timezone.utc)
            except (OverflowError, ValueError):
                return None
        return 'near_capture' if abs((left_time - right_time).total_seconds()) <= 300 else None
    if left_time is not None or right_time is not None:
        return None
    left_day, right_day = left['capture_day'], right['capture_day']
    if left_day is not None and right_day is not None and left_day != right_day:
        return None
    if (left['upload_account'] and left['upload_batch']
            and left['upload_account'] == right['upload_account']
            and left['upload_batch'] == right['upload_batch']
            and (left['phash'] ^ right['phash']).bit_count() <= 2):
        return 'same_upload'
    return None


def build_photo_stacks(rows, *, hints=False):
    """Build deterministic complete-link stacks from a page of authorized rows.

    The gallery order chooses each cover and member order. Invalid/missing
    metadata only prevents grouping; it never removes a gallery item.
    """
    base_fields = 8 if hints else 6
    if type(rows) not in (list, tuple) or len(rows) > 100:
        return {'version': 1, 'scope': 'page', 'groups': []}
    prepared = []
    for row in rows:
        if len(row) < base_fields + 3:
            continue
        asset_id, mime = row[0], row[1]
        phash = _hash(row[base_fields])
        if (type(asset_id) is not int or not 1 <= asset_id <= 2**63 - 1
                or type(mime) is not str or not mime.startswith('image/')
                or phash is None):
            continue
        account, batch = row[base_fields + 1:base_fields + 3]
        prepared.append({
            'id': asset_id,
            'capture_time': _capture_time(row[5]),
            'capture_day': _capture_day(row[5]),
            'phash': phash,
            'upload_account': account if type(account) is str and account.strip() else None,
            'upload_batch': batch if type(batch) is str and batch.strip() else None,
        })

    clusters = []
    for item in prepared:
        for cluster in clusters:
            relations = [_pair_reason(item, member) for member in cluster['members']]
            if (all(relations) and len(set(relations)) == 1
                    and (cluster['reason'] is None or cluster['reason'] == relations[0])):
                cluster['members'].append(item)
                cluster['reason'] = relations[0]
                break
        else:
            clusters.append({'members': [item], 'reason': None})

    groups = []
    for cluster in clusters:
        members = cluster['members']
        if len(members) < 2:
            continue
        ids = [str(member['id']) for member in members]
        groups.append({
            'id': str(min(member['id'] for member in members)),
            'cover_asset_id': ids[0],
            'asset_ids': ids,
            'count': len(ids),
            'reason': cluster['reason'],
        })
    return {'version': 1, 'scope': 'page', 'groups': groups}

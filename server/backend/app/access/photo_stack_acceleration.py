"""Opt-in native grouping; Python remains the portable reference backend."""
from datetime import datetime, timezone
import importlib
import json
import os


def kernel_payload(prepared, maximum_comparisons):
    records = []
    for item in prepared:
        captured = item['capture_time']
        aware = captured is not None and captured.utcoffset() is not None
        micros = None
        if captured is not None and not item.get('unmatchable_time'):
            epoch = datetime(1970, 1, 1, tzinfo=timezone.utc if aware else None)
            delta = (captured.astimezone(timezone.utc) if aware else captured) - epoch
            micros = str((delta.days * 86400 + delta.seconds) * 1000000 + delta.microseconds)
        records.append([f"{item['phash']:016x}", micros, aware,
                        item['capture_day'].toordinal() if item['capture_day'] else None,
                        item['upload_account'], item['upload_batch'],
                        bool(item.get('unmatchable_time'))])
    return json.dumps({'items': records, 'maximum_comparisons': min(maximum_comparisons, 2**63 - 1)},
                      separators=(',', ':'), ensure_ascii=True)


def build_accelerated(prepared, maximum_comparisons, stopped):
    mode = os.environ.get('PHOTOHOUSE_PHOTO_STACK_ENGINE', 'python')
    if mode == 'python':
        return None
    if mode != 'rust':
        raise ValueError('PHOTOHOUSE_PHOTO_STACK_ENGINE must be python or rust')
    from .photo_stack_index import check_stopped, grouping_policy_fingerprint
    if grouping_policy_fingerprint() != {
        'algorithm_version': 'complete-link-v1', 'near_capture_hash_max_distance': 8,
        'same_upload_hash_max_distance': 4, 'capture_window_seconds': 300, 'group_limit': 24,
    }:
        # A changed live policy is always evaluated by its Python implementation.
        return None
    if len(prepared) > 100000 or any(
            any(0xD800 <= ord(char) <= 0xDFFF for char in (item[key] or ''))
            for item in prepared for key in ('upload_account', 'upload_batch')):
        return None
    try:
        native = importlib.import_module('photohouse_photo_stack')
    except ImportError as error:
        raise RuntimeError('Rust photo-stack engine is selected but unavailable; build a compatible extension') from error
    if (getattr(native, 'KERNEL_VERSION', None) != 1
            or getattr(native, 'POLICY_FINGERPRINT', None) != 'complete-link-v1:8:4:300:24'):
        raise RuntimeError('Incompatible Rust photo-stack engine; rebuild the extension')
    callback = (lambda: check_stopped(stopped)) if stopped is not None else None
    groups = json.loads(native.group(kernel_payload(prepared, maximum_comparisons), callback))
    result = []
    for indices, reason in groups:
        ids = [prepared[index]['id'] for index in indices]
        asset_ids = [str(asset_id) for asset_id in ids]
        result.append({'id': str(min(ids)), 'cover_asset_id': asset_ids[0],
                       'asset_ids': asset_ids, 'count': len(ids), 'reason': reason})
    return result

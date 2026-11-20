"""Data-only characterization seam for the optional Rust grouping kernel.

The public builder retains validation and date parsing. This private wire format
uses hexadecimal hashes and decimal microseconds to preserve integer precision.
"""
from datetime import datetime, timedelta, timezone, date
import json


def group_items(payload: str) -> str:
    """Reference for rust-anything recording; no database, provider or network."""
    from app.access.photo_stack_index import _build_prepared, _time_bucket
    try:
        value = json.loads(payload)
        if type(value) is not dict or set(value) != {'items', 'maximum_comparisons'}:
            raise ValueError
        records, budget = value['items'], value['maximum_comparisons']
        if (type(records) is not list or len(records) > 100000
                or type(budget) is not int or not 0 <= budget <= 2**63 - 1):
            raise ValueError
        prepared = []
        for index, record in enumerate(records):
            if type(record) is not list or len(record) != 7:
                raise ValueError
            phash, micros, aware, day, account, batch, unmatchable = record
            if (type(phash) is not str or len(phash) != 16
                    or any(c not in '0123456789abcdef' for c in phash)
                    or type(aware) is not bool or type(unmatchable) is not bool
                    or (day is not None and (type(day) is not int or not 1 <= day <= 3652059))
                    or any(v is not None and (type(v) is not str or any(
                        0xD800 <= ord(c) <= 0xDFFF for c in v)) for v in (account, batch))):
                raise ValueError
            captured = None
            if micros is not None:
                if type(micros) is not str or str(int(micros)) != micros:
                    raise ValueError
                epoch = datetime(1970, 1, 1, tzinfo=timezone.utc if aware else None)
                captured = epoch + timedelta(microseconds=int(micros))
            prepared.append({
                'id': index + 1, 'phash': int(phash, 16), 'capture_time': captured,
                'capture_day': date.fromordinal(day) if day is not None else None,
                'upload_account': account, 'upload_batch': batch,
                'unmatchable_time': unmatchable,
                'time_bucket': _time_bucket(captured) if captured is not None else None,
            })
    except (ValueError, TypeError, OverflowError, KeyError):
        raise ValueError('invalid photo-stack kernel input') from None
    groups = _build_prepared(prepared, budget)
    return json.dumps([[ [int(i) - 1 for i in group['asset_ids']], group['reason']]
                       for group in groups], separators=(',', ':'))

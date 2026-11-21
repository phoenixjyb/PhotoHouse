"""Generated grouping workloads; no household media or database input."""
from datetime import datetime, timedelta, timezone
import random


def workloads():
    """Return deterministic burst and mixed-metadata libraries in gallery order."""
    rng = random.Random(20261121)
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    result = {}
    for name in ('bursts', 'mixed'):
        rows = []
        for cluster in range(400):
            base = rng.getrandbits(64)
            # Separate capture windows make expected membership independent of
            # accidental collisions between unrelated random base hashes.
            captured = origin + timedelta(minutes=15 * cluster)
            for member in range(32 if name == 'bursts' else 16):
                ident = len(rows) + 1
                stamp = (captured + timedelta(seconds=member)).isoformat()
                account = batch = None
                if name == 'mixed':
                    kind = cluster % 4
                    if kind == 1:
                        stamp = (captured + timedelta(seconds=member)).replace(tzinfo=None).isoformat()
                    elif kind == 2:
                        stamp = captured.date().isoformat() if member % 3 else None
                        account, batch = 'generated-family-家人', f'upload-{cluster}'
                    elif kind == 3:
                        stamp = (captured + timedelta(seconds=member)).astimezone(
                            timezone(timedelta(hours=8))).isoformat()
                phash = base ^ (1 << (member % 64))
                rows.append((ident, 'image/jpeg', f'generated-{ident}.jpg', 1920, 1080,
                             stamp, f'{phash:016x}', account, batch))
        # Gallery order affects covers and must survive the native bridge.
        rows.reverse()
        result[name] = {
            'rows': rows,
            'expected_groups': 800 if name == 'bursts' else 400,
            'expected_sizes': {24: 400, 8: 400} if name == 'bursts' else {16: 400},
        }
    return result

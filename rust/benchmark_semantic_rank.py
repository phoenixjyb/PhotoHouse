"""Generated complete non-bulk semantic rank calls, existing Rust bridge included.

Never builds, downloads, reads household data or activates a live engine.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import struct
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--case', choices=('small', 'streaming'), required=True)
    args = parser.parse_args()
    output, native_dir = args.output.absolute(), args.native_dir.resolve(strict=True)
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        parser.error('a new output in an existing parent is required')
    if os.name == 'nt' and any(p.drive.upper() != 'D:' for p in (ROOT, native_dir, output)):
        parser.error('Windows source, native input and output must be on D:')
    sys.path[:0] = [str(native_dir), str(ROOT / 'server/backend')]
    from app.access.semantic_encoder import JointSpaceBinding, TextVector, rank_semantic
    from app.access.semantic_streaming import rank_semantic_batches
    from app.access.visual_candidates import VectorSpaceIdentity, VectorRecord, canonical_vector_checksum
    import photohouse_vector_kernel as native
    rng = random.Random(20261123)
    dimension = 768
    count = 512 if args.case == 'small' else 4096
    pool = []
    for _ in range(32):
        values = [rng.uniform(-1, 1) for _ in range(dimension)]
        norm = math.sqrt(math.fsum(x*x for x in values))
        pool.append(tuple(struct.unpack('>768f', struct.pack('>768f', *(x/norm for x in values)))))
    identity = VectorSpaceIdentity('a'*64, 'b'*64, 'generated-v1', 'generated-v1', dimension, 'unit_l2')
    binding = JointSpaceBinding(identity, identity, 'c'*64)
    sums = [canonical_vector_checksum(v) for v in pool]
    query = TextVector(binding.binding_sha256, 'd'*64, pool[0], sums[0])
    rows = tuple(VectorRecord(str(i+1), identity, pool[i % 32], sums[i % 32]) for i in range(count))
    expected = None
    results = []
    for engine in ('python', 'rust'):
        checks = [0]
        def check():
            checks[0] += 1
        def call():
            checks[0] = 0
            if args.case == 'small':
                return rank_semantic(query, binding, rows, check=check)
            return rank_semantic_batches(query, binding,
                (rows[start:start+128] for start in range(0, count, 128)),
                expected_count=count, candidate_limit=count, check=check)
        with patch.dict(os.environ, PHOTOHOUSE_VECTOR_ENGINE=engine):
            value = call()
            current = (value, checks[0])
            if expected is None:
                expected = current
            if current != expected:
                raise AssertionError('exact_rank_or_cancellation_parity_failed')
            wall, cpu = [], []
            for _ in range(7):
                start, process = time.perf_counter(), time.process_time()
                value = call()
                cpu.append(time.process_time()-process)
                wall.append(time.perf_counter()-start)
                if (value, checks[0]) != expected:
                    raise AssertionError('exact_rank_or_cancellation_parity_failed')
        results.append({'engine': engine, 'wall_seconds': wall, 'cpu_seconds': cpu,
            'median': statistics.median(wall), 'callbacks': checks[0]})
    report = {'case': args.case, 'rows': count, 'dimension': dimension, 'warmups': 1, 'repeats': 7,
        'results': results, 'speedup': results[0]['median']/results[1]['median'],
        'result_sha256': hashlib.sha256(repr(expected).encode()).hexdigest(),
        'native_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        'native_builds': 0, 'python': platform.python_version(), 'system': platform.system(),
        'machine': platform.machine(), 'source_sha256': {
            name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in (
                'server/backend/app/access/semantic_encoder.py',
                'server/backend/app/access/semantic_streaming.py',
                'server/backend/app/access/visual_candidates.py',
                'server/backend/app/access/vector_acceleration.py',
                'rust/benchmark_semantic_rank.py')},
        'scope': 'Generated full canonicalization/scoring/ranking component only; excludes DB/file/HTTP/provider/network and household relevance; no activation'}
    with output.open('x') as stream:
        json.dump(report, stream, indent=2)
        stream.write('\n')
    output.chmod(0o600)
    print(json.dumps({key: report[key] for key in ('case', 'rows', 'speedup', 'result_sha256', 'native_builds')}))


if __name__ == '__main__':
    main()

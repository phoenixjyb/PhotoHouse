"""Generated vector benchmark; exact byte/rank parity, bridge and callbacks included.

Use --case for one fresh-process measurement. No providers, databases or network.
"""
import argparse
from contextlib import ExitStack
import ctypes
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
CASES = ('cold_python', 'cold_rust', 'warm_scalar', 'warm_numpy', 'warm_rust',
         'cold_and_rank_python', 'cold_and_rank_rust')


def process_memory():
    """Fresh-process peak, including the common fixture/reference setup."""
    if os.name == 'nt':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        values = Counters(); values.cb = ctypes.sizeof(values)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(values), values.cb):
            raise OSError('process memory query failed')
        return {'peak_working_set_bytes': values.PeakWorkingSetSize,
                'peak_commit_bytes': values.PeakPagefileUsage}
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'peak_working_set_bytes': value if sys.platform == 'darwin' else value * 1024}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--native-dir', type=Path)
    parser.add_argument('--dependency-root', type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / '.runtime/vector-kernel/benchmark.json'
    native_dir = args.native_dir or ROOT / 'rust/vector-python/target/python'
    if os.name == 'nt':
        for path in (ROOT, output, native_dir):
            if path.drive.upper() != 'D:':
                parser.error('Windows source, output and native scratch must be on D:')
    sys.path[:0] = [str(native_dir), str(ROOT / 'server/backend')]
    if args.dependency_root:
        sys.path.append(str(args.dependency_root.resolve(strict=True)))
    from app.access import semantic_bulk_vectors as bulk
    from app.access.visual_candidates import (VectorSpaceIdentity, canonical_vector_checksum,
                                               _canonical_components, VectorRecord)
    from app.access.visual_vector_artifacts import ImmutableVectorArtifact, identity_sha256
    dimension = 768; count = 4096; rng = random.Random(20261120); vectors = []
    for _ in range(64):
        values = [rng.uniform(-1, 1) for _ in range(dimension)]
        norm = math.sqrt(math.fsum(x * x for x in values))
        vectors.append(tuple(struct.unpack(f'>{dimension}f', struct.pack(
            f'>{dimension}f', *(x / norm for x in values)))))
    identity = VectorSpaceIdentity('a' * 64, 'b' * 64, 'synthetic-vector-v1',
                                   'synthetic-v1', dimension, 'unit_l2')
    digest = identity_sha256(identity)
    checksums = [canonical_vector_checksum(v) for v in vectors]
    artifacts = tuple(ImmutableVectorArtifact(f'{i:064x}', str(i), f'{i:064x}', 'synthetic',
        identity.artifact_sha256, identity.preprocessing_sha256, identity.vector_space_id,
        identity.model_version, dimension, 'unit_l2', digest,
        f'image-vectors/{digest}/{i:064x}.npy', 'f' * 64, checksums[i % 64], 1, 'ready')
        for i in range(1, count + 1))
    payload = memoryview(b''.join(struct.pack(f'>{dimension}f', *vectors[i % 64])
                                 for i in range(1, count + 1)))
    query = _canonical_components(VectorRecord('1', identity, vectors[0], checksums[0]), identity)
    ids = tuple(a.asset_id for a in artifacts)
    with patch.dict(os.environ, PHOTOHOUSE_VECTOR_ENGINE='python'):
        reference = bulk._canonical_matrix(payload, artifacts, identity, lambda: None)
        snapshot = bulk.BulkVectorSnapshot(artifacts, identity, reference)
        expected = snapshot.rank(query, ids)
    numpy = bulk._rank_numpy_backend()
    assert numpy is not None, 'NumPy baseline required; do not substitute scalar timings'
    import photohouse_vector_kernel as native
    records = []
    for name in ((args.case,) if args.case else CASES):
        engine = 'rust' if name.endswith('_rust') else 'python'
        checks = [0]
        def check():
            checks[0] += 1
        def cold():
            return bulk._canonical_matrix(payload, artifacts, identity, check)
        def call():
            if name.startswith('cold_and_rank_'):
                return bulk.BulkVectorSnapshot(artifacts, identity, cold()).rank(query, ids, check=check)
            if name.startswith('cold_'):
                return cold()
            return snapshot.rank(query, ids, check=check)
        wanted = reference if name in ('cold_python', 'cold_rust') else expected
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, PHOTOHOUSE_VECTOR_ENGINE=engine))
            if name == 'warm_scalar':
                stack.enter_context(patch.object(bulk, '_rank_numpy_backend', return_value=None))
            checks[0] = 0; assert call() == wanted; callbacks = checks[0]
            wall = []; cpu = []
            for _ in range(5):
                checks[0] = 0; start = time.perf_counter(); c = time.process_time()
                value = call(); cpu.append(time.process_time() - c)
                wall.append(time.perf_counter() - start)
                assert value == wanted and checks[0] == callbacks
            expected_callbacks = (count + 1) * (2 if name.startswith('cold_and_rank_') else 1)
            assert callbacks == expected_callbacks
        records.append({'name': name, 'engine': engine, 'warmups': 1, 'repeats': 5,
            'wall_seconds': wall, 'wall_median': statistics.median(wall),
            'wall_min': min(wall), 'wall_max': max(wall), 'cpu_seconds': cpu,
            'cpu_median': statistics.median(cpu), 'callbacks_per_call': callbacks})
    result = {'schema': 'photohouse-vector-kernel-benchmark@2', 'python': platform.python_version(),
        'machine': platform.machine(), 'system': platform.system(), 'numpy': numpy.__version__,
        'rows': count, 'dimensions': dimension, 'unique_generated_patterns': 64,
        'payload_sha256': hashlib.sha256(payload).hexdigest(),
        'matrix_sha256': hashlib.sha256(b''.join(reference[0])).hexdigest(),
        'rank_sha256': hashlib.sha256(json.dumps(expected, separators=(',', ':')).encode()).hexdigest(),
        'scope': 'Generated CPU components; excludes file admission/DB/HTTP/model/network and household data',
        'exact_matrix_bytes_and_ranked_scores': True, 'fresh_process_case': args.case,
        'pid': os.getpid(), 'memory': process_memory(), 'results': records,
        'native_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
        'source_sha256': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in (
            'server/backend/app/access/semantic_bulk_vectors.py',
            'server/backend/app/access/vector_acceleration.py', 'rust/vector-core/src/port.rs',
            'rust/vector-core/src/lib.rs', 'rust/vector-core/Cargo.toml', 'rust/vector-core/Cargo.lock',
            'rust/vector-python/src/lib.rs', 'rust/vector-python/Cargo.toml',
            'rust/vector-python/Cargo.lock', 'rust/benchmark_vector_kernel.py')}}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(json.dumps({'status': 'PASS', 'cases': len(records),
                      'medians': {r['name']: r['wall_median'] for r in records}}))


if __name__ == '__main__':
    main()

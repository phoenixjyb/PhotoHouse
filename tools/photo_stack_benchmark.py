"""Measure one generated grouping workload in a fresh, explicitly selected process.

Run each engine/callback/workload combination in its own process for comparable
process peak memory. This tool never launches a service or reads a database.
"""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from photo_stack_workloads import workloads


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()


def process_peak_memory():
    """Process-lifetime high-water mark, including input and warm-up allocations."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize',
                'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage',
                'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return {'peak_working_set_bytes': counters.PeakWorkingSetSize,
                'peak_commit_bytes': counters.PeakPagefileUsage}
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {'peak_resident_bytes': peak if sys.platform == 'darwin' else peak * 1024}


def run(fixture, engine, native_dir, runs, cancellable):
    sys.path.insert(0, str(ROOT / 'server/backend'))
    if native_dir is not None:
        sys.path.insert(0, str(native_dir.resolve(strict=True)))
    os.environ['PHOTOHOUSE_PHOTO_STACK_ENGINE'] = engine
    from app.access.photo_stack_index import build_library_photo_stacks, PhotoStackCancelled
    native = None
    if engine == 'rust':
        import photohouse_photo_stack as native
        if native_dir is None or Path(native.__file__).resolve().parent != native_dir.resolve():
            raise ValueError('explicit_native_import_directory_required')
    case = workloads()[fixture]; rows = case['rows']
    calls = [0]
    def stopped():
        calls[0] += 1
        return False
    options = {'stopped': stopped} if cancellable else {}
    expected = build_library_photo_stacks(rows, **options)
    assert len(expected) == case['expected_groups']
    assert Counter(g['count'] for g in expected) == case['expected_sizes']
    assert sum(g['count'] for g in expected) == len(rows)
    assert len({i for g in expected for i in g['asset_ids']}) == len(rows)
    expected_digest = digest(expected)
    warmup_calls = calls[0]
    timings = []
    for _ in range(runs):
        calls[0] = 0
        cpu, wall = time.process_time_ns(), time.perf_counter_ns()
        groups = build_library_photo_stacks(rows, **options)
        elapsed, used = time.perf_counter_ns() - wall, time.process_time_ns() - cpu
        assert digest(groups) == expected_digest and calls[0] == warmup_calls
        timings.append({'wall_seconds': elapsed / 1e9, 'process_cpu_seconds': used / 1e9})
    peak = process_peak_memory()
    # Stop after preparation, while grouping is active. No partial output may
    # escape, and the exact check count must agree across backends.
    calls[0] = 0
    requested = [None]
    def cancel():
        calls[0] += 1
        if calls[0] > len(rows) + 120:
            requested[0] = time.perf_counter_ns()
            return True
        return False
    start = time.perf_counter_ns()
    try:
        build_library_photo_stacks(rows, stopped=cancel)
    except PhotoStackCancelled as error:
        returned = time.perf_counter_ns()
        assert str(error) == 'photo_stack_refresh_cancelled'
    else:
        raise AssertionError('cancellation returned partial groups')
    assert calls[0] == len(rows) + 121
    return {'fixture': fixture, 'engine': engine, 'cancellable': cancellable,
            'rows': len(rows), 'groups': len(expected), 'group_sizes': case['expected_sizes'],
            'rows_sha256': digest(rows), 'groups_sha256': expected_digest,
            'warmups': 1, 'runs': timings, 'callback_checks_per_call': warmup_calls,
            'wall_median': statistics.median(r['wall_seconds'] for r in timings),
            'wall_min': min(r['wall_seconds'] for r in timings),
            'wall_max': max(r['wall_seconds'] for r in timings),
            'cpu_median': statistics.median(r['process_cpu_seconds'] for r in timings),
            'memory': peak, 'memory_scope': 'fresh process lifetime through warmup and all timing calls',
            'cancellation': {'status': 'PASS', 'checks': calls[0],
                             'total_call_seconds': (returned - start) / 1e9,
                             'after_stop_request_seconds': (returned - requested[0]) / 1e9},
            'python': sys.version, 'platform': platform.platform(),
            'native_sha256': hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest() if native else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', choices=('bursts', 'mixed'), required=True)
    parser.add_argument('--engine', choices=('python', 'rust'), required=True)
    parser.add_argument('--native-dir', type=Path)
    parser.add_argument('--cancellable', action='store_true')
    parser.add_argument('--runs', type=int, choices=range(1, 10), default=9)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('new output required')
    if os.name == 'nt' and (args.output.absolute().drive.upper() != 'D:' or ROOT.drive.upper() != 'D:'):
        parser.error('Windows source and output must be on D:')
    report = run(args.fixture, args.engine, args.native_dir, args.runs, args.cancellable)
    with args.output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, indent=2, sort_keys=True); stream.write('\n')
    print(json.dumps({k: report[k] for k in ('fixture', 'engine', 'cancellable', 'wall_median', 'groups')}))


if __name__ == '__main__':
    main()

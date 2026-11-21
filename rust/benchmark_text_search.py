"""Generated literal-search scan; no files, database or model in the timed call."""
import argparse
import cProfile
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def fixture(case, count):
    records = []
    for index in range(1, count + 1):
        contents = (f'海边合影 family picnic sunset 旅行记录 {index}。',
                    f'周末海边合影，是一次轻松的旅行。 family picnic {index}')
        if case == 'mostly_miss' and index % 5:
            contents = (f'city garden album {index}', f'周末城市公园 {index}')
        records.append((str(index), [
            {'source': source, 'source_id': str(index), 'revision': 1, 'content': content}
            for source, content in zip(('edited_caption', 'photo_memory'), contents)]))
    return records, 'family picnic' if case == 'ascii' else '海边合影'


def scan(module, records, phrase, prepare):
    filters = module.normalize_filters({'text': phrase})
    prepared = module.TextQueryCache() if prepare else None
    checks = 0

    def check():
        nonlocal checks
        checks += 1

    found = []
    qualities = {}
    for asset_id, sources in records:
        normalized = module.normalize_sources(sources, check)
        kwargs = {'query_cache': prepared} if prepare else {}
        matched, reasons, quality = module.match_text(
            {'text_sources': normalized}, filters, check, **kwargs)
        if matched:
            found.append({'id': asset_id, 'match_reasons': reasons})
            qualities[asset_id] = quality
    return module.rank_results(found, qualities, check), qualities, checks


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path)
    parser.add_argument('--case', choices=['cjk', 'ascii', 'mostly_miss'], required=True)
    parser.add_argument('--rows', type=int, default=10000)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--profile', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.rows <= 10000:
        parser.error('rows must be 1..10000')
    if os.name == 'nt' and any(p.drive.upper() != 'D:' for p in [ROOT, args.output]):
        parser.error('Windows source/output must be on D:')
    if args.output.exists():
        parser.error('output must be new')
    sys.path.insert(0, str(ROOT / 'server/backend'))
    if args.reference:
        spec = importlib.util.spec_from_file_location('reference_search_text', args.reference)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
    else:
        from app.access import search_text as module
    records, phrase = fixture(args.case, args.rows)
    call = lambda: scan(module, records, phrase, args.prepare)
    expected = call()
    expected_count = args.rows // 5 if args.case == 'mostly_miss' else args.rows
    assert len(expected[0]) == expected_count
    samples = []
    cpu = []
    for _ in range(5):
        start = time.perf_counter()
        process_start = time.process_time()
        actual = call()
        cpu.append(time.process_time() - process_start)
        samples.append(time.perf_counter() - start)
        assert actual == expected
    result = {'status': 'PASS', 'case': args.case, 'rows': args.rows,
              'sources_per_row': 2, 'result_count': len(expected[0]), 'checks': expected[2],
              'prepared_query': args.prepare, 'warmups': 1, 'repeats': 5,
              'wall_seconds': samples, 'wall_median': statistics.median(samples),
              'cpu_seconds': cpu, 'exact_result_sha256': digest(expected),
              'source_sha256': hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest(),
              'tool_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'python': platform.python_version(), 'system': platform.system(),
              'machine': platform.machine(),
              'scope': 'Generated full literal-source normalization/matching/ranking; excludes DB/file admission/HTTP/model/network'}
    if args.profile:
        profile = cProfile.Profile()
        profile.enable()
        actual = call()
        profile.disable()
        assert actual == expected
        result['profile'] = profile_rows(profile)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps({k: result[k] for k in ['status', 'case', 'rows', 'result_count', 'wall_median', 'prepared_query']}))


def profile_rows(profile):
    import pstats
    return sorted([
        {'file': Path(file).name, 'line': line, 'function': function, 'calls': nc,
         'self_seconds': tt, 'cumulative_seconds': ct}
        for (file, line, function), (cc, nc, tt, ct, callers) in pstats.Stats(profile).stats.items()
    ], key=lambda row: row['self_seconds'], reverse=True)


if __name__ == '__main__':
    main()

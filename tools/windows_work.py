#!/usr/bin/env python3
"""Native development storage entrypoint. No service/task or archive execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server' / 'backend'))
from app import work_storage as storage
from app.access.private_storage import require_private_directory, require_private_file

PRODUCERS = {
    'snapshot': 'server/scripts/rehearse_fullsize_database.py',
    'rehearse': 'server/scripts/rehearse_fullsize_database.py',
    'package-source': 'tools/package_source.py',
    'api-package': 'server/scripts/build_staging_package.py',
    'editorial-package': 'server/scripts/build_editorial_rehearsal_package.py',
    'editorial-group': 'server/scripts/run_editorial_rehearsal_group.py',
}
POLICY_FILES = tuple(sorted(set(PRODUCERS.values()) | {
    'tools/windows_work.py', 'server/backend/app/work_storage.py',
    'server/backend/app/access/private_storage.py', 'server/scripts/prepare_access_database.py',
}))


def install():
    if os.name != 'nt':
        raise storage.StorageRefused('native_windows_required')
    pins = {str(ROOT / name): hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in POLICY_FILES}
    python = ROOT / '.venv' / 'Scripts' / 'python.exe'
    pins[str(python)] = hashlib.sha256(python.read_bytes()).hexdigest()
    identity = hashlib.sha256(json.dumps(pins, sort_keys=True).encode()).hexdigest()
    tools = storage.work_root() / 'tools'
    if not tools.exists():
        storage.private_mkdir(tools)
    require_private_directory(tools)
    destination = tools / ('storage-policy-' + identity[:16])
    with storage.operation([destination], [(destination, 'pinned development launcher', 65536)]):
        storage.private_mkdir(destination)
        manifest = {'version': 1, 'source_linked': True, 'python': str(python),
                    'checkout': str(ROOT), 'entry': str(ROOT / 'tools/windows_work.py'), 'sha256': pins}
        (destination / 'installation.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
        (destination / 'PhotoHouse-Work.ps1').write_text(
            "$ErrorActionPreference = 'Stop'\n"
            "$manifest = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'installation.json') | ConvertFrom-Json\n"
            "foreach ($pin in $manifest.sha256.PSObject.Properties) {\n"
            "    $stream = [IO.File]::OpenRead($pin.Name)\n"
            "    $algorithm = [Security.Cryptography.SHA256]::Create()\n"
            "    try { $digest = [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-', '').ToLowerInvariant() }\n"
            "    finally { $stream.Dispose(); $algorithm.Dispose() }\n"
            "    if ($digest -ne $pin.Value) {\n"
            "        throw 'Source or policy changed. Review and install a new launcher.'\n"
            "    }\n"
            "}\n"
            "& $manifest.python -B $manifest.entry @args\n"
            "exit $LASTEXITCODE\n", encoding='utf-8')
        for child in destination.iterdir():
            require_private_file(child)
    return {'status': 'installed', 'launcher': str(destination / 'PhotoHouse-Work.ps1'),
            'source_linked': True, 'installation_id': identity}


def report():
    # Report metadata only. Failure/age is never authority to move/delete data.
    mount = storage.volume(storage.work_root())[1]
    admission = storage.direct(mount / 'PhotoHouseWork' / 'admission')
    if not admission.exists():
        return {'operations': 0, 'states': {}, 'archival_enabled': False}
    require_private_directory(admission)
    states, count, recorded = {}, 0, 0
    for child in admission.iterdir():
        child = storage.direct(child)
        if not child.is_dir():
            continue
        require_private_directory(child)
        receipt = storage.direct(child / 'receipt.json')
        require_private_file(receipt)
        if receipt.stat().st_size > 65536 or count >= 10000:
            raise storage.StorageRefused('report_bound_exceeded')
        item = json.loads(receipt.read_text(encoding='utf-8'))
        state = item['state']
        if state not in ('running', 'closed', 'failed_uncertain'):
            raise storage.StorageRefused('unknown_lifecycle_state')
        states[state] = states.get(state, 0) + 1
        count += 1
        recorded += item['actual_bytes'] or 0
    return {'operations': count, 'states': states, 'recorded_actual_bytes': recorded,
            'archival_enabled': False, 'scope': 'policy receipts; not a current disk inventory'}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in PRODUCERS:
        command = argv.pop(0)
        script = ROOT / PRODUCERS[command]
        sys.path.insert(0, str(script.parent))
        sys.argv = [str(script), *([command] if command in ('snapshot', 'rehearse') else []), *argv]
        runpy.run_path(str(script), run_name='__main__')
        return 0
    parser = argparse.ArgumentParser(description=__doc__, epilog='Producers: ' + ', '.join(PRODUCERS))
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('install', help='install a private source/hash-bound PowerShell launcher on D:')
    commands.add_parser('report', help='report lifecycle receipts; never archive or delete')
    plan = commands.add_parser('plan', help='read-only volume/peak-space preflight')
    plan.add_argument('--output', type=Path, required=True)
    plan.add_argument('--component', action='append', required=True, metavar='PURPOSE=BYTES')
    args = parser.parse_args(argv)
    try:
        if args.command == 'install':
            result = install()
        elif args.command == 'report':
            result = report()
        else:
            output = storage.target(args.output)
            components = []
            for component in args.component:
                name, size = component.rsplit('=', 1)
                components.append((output, name, int(size)))
            storage.check_space(components)
            result = {'status': 'admissible_now', 'planned_bytes': sum(size for _, _, size in components),
                      'reserve_bytes': storage.RESERVE, 'allocated_bytes': 0}
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError):
        print(json.dumps({'status': 'refused', 'allocated_payload_bytes': 0}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Native development storage entrypoint. No service/task or archive execution."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile

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


def setup_dependencies(profile):
    if os.name != 'nt':
        raise storage.StorageRefused('native_windows_required')
    python_profile = profile == 'python'
    if sys.version_info[:3] < (3, 12, 4):
        raise storage.StorageRefused('python_3_12_4_or_newer_required')
    if python_profile and sys.version_info[:2] != (3, 12):
        raise storage.StorageRefused('development_dependencies_require_python_3_12')

    project = ROOT if python_profile else ROOT / 'server/tests/security/browser-tooling'
    install_root = storage.direct(project / ('.venv' if python_profile else 'node_modules'))
    lock = storage.direct(project / ('config/requirements-dev.lock' if python_profile else 'package-lock.json'))
    if not lock.is_file():
        raise storage.StorageRefused('dependency_lock_unavailable')
    storage.volume(install_root)

    work_root = storage.work_root()
    cache = work_root / 'package-cache' / ('pip' if python_profile else 'npm')
    # Reserve space for both installation and cached/downloaded working files.
    budget = 1024**3 if python_profile else 128 * 1024**2
    components = [(install_root, 'dependency installation', budget),
                  (cache, 'package cache and temporary files', budget)]
    volumes = storage.check_space(components)
    with ExitStack() as stack:
        for identity in sorted(volumes):
            stack.enter_context(storage._volume_lock(volumes[identity][0]))
        storage.check_space(components)
        storage.direct(install_root)
        if python_profile:
            python = storage.direct(install_root / 'Scripts/python.exe')
            create_venv = not install_root.exists()
            if not create_venv and (
                not python.is_file() or not storage.direct(install_root / 'pyvenv.cfg').is_file()
            ):
                raise storage.StorageRefused('development_venv_incomplete')

        cache_parent = storage._private_child(work_root, 'package-cache')
        cache = storage._private_child(cache_parent, cache.name)
        with tempfile.TemporaryDirectory(prefix='install-', dir=cache) as name:
            temporary = storage.direct(Path(name))
            require_private_directory(temporary)
            # The checked-in locks select the packages. Package-manager
            # settings in the shell must not redirect installation or caches.
            env = {key: value for key, value in os.environ.items()
                   if not key.upper().startswith(('PIP_', 'NPM_CONFIG_'))}
            env.update({key: str(temporary) for key in ('TEMP', 'TMP', 'TMPDIR')})
            if python_profile:
                env.update(PIP_CONFIG_FILE=os.devnull, PIP_CACHE_DIR=str(cache))
                if create_venv:
                    subprocess.run([sys.executable, '-I', '-m', 'venv', str(install_root)],
                                   cwd=project, env=env, check=True)
                storage.direct(python)
                command = [str(python), '-I', '-m', 'pip', '--require-virtualenv',
                           'install', '--require-hashes', '-r', str(lock)]
            else:
                npm_logs = storage.direct(cache / '_logs')
                env.update(NPM_CONFIG_CACHE=str(cache), NPM_CONFIG_LOGS_DIR=str(npm_logs),
                           NPM_CONFIG_PREFIX=str(project))
                command = ['cmd.exe', '/d', '/c', 'npm.cmd', 'ci', '--ignore-scripts',
                           '--no-audit', '--no-fund', '--global=false']
            subprocess.run(command, cwd=project, env=env, check=True)


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
    dependencies = commands.add_parser(
        'dependencies', help='install locked development dependencies with managed caches',
    )
    dependencies.add_argument('profile', choices=('python', 'web'))
    plan = commands.add_parser('plan', help='read-only volume/peak-space preflight')
    plan.add_argument('--output', type=Path, required=True)
    plan.add_argument('--component', action='append', required=True, metavar='PURPOSE=BYTES')
    args = parser.parse_args(argv)
    try:
        if args.command == 'install':
            result = install()
        elif args.command == 'report':
            result = report()
        elif args.command == 'dependencies':
            setup_dependencies(args.profile)
            return 0
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
    except subprocess.CalledProcessError as error:
        return error.returncode
    except (OSError, ValueError, KeyError) as error:
        result = {'status': 'refused', 'allocated_payload_bytes': 0}
        if args.command == 'dependencies' and isinstance(error, storage.StorageRefused):
            result = {'status': 'refused', 'reason': str(error)}
        print(json.dumps(result))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())

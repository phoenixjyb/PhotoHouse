#!/usr/bin/env python3
"""Export a pinned backend and run opt-in Android HTTPS interoperability tests.

No cloning, dependency installation, real endpoint, database or credential input.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def export_backend(repo, target, manifest):
    commit = manifest['backend_commit']
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid pinned backend identity')
    observed = subprocess.check_output(['git', '-C', str(repo), 'rev-parse', commit + '^{commit}'], text=True).strip()
    if observed != commit:
        raise ValueError('Pinned backend is unavailable')
    selected = ['backend/app/__init__.py', 'backend/app/main.py', 'backend/app/db.py',
                'backend/app/access', 'backend/app/routers/ui.py', 'backend/app/ui/access',
                'backend/migrations', 'tests/security/test_library_reads.py',
                'tests/security/test_orm_migrations.py', 'tests/security/test_access_foundation.py']
    archive = subprocess.check_output(['git', '-C', str(repo), 'archive', '--format=tar', commit, *selected])
    with tarfile.open(fileobj=io.BytesIO(archive)) as bundle:
        # Extract only ordinary source files/directories; refuse links and paths
        # escaping this newly-created test export on older Python versions too.
        for item in bundle:
            path = target / item.name
            if not path.resolve().is_relative_to(target.resolve()) or not (item.isfile() or item.isdir()):
                raise ValueError('Unsafe archive member')
            if item.isdir():
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(bundle.extractfile(item).read())
    for name, digest in manifest['backend_sources'].items():
        if hashlib.sha256((target / name).read_bytes()).hexdigest() != digest:
            raise ValueError('Pinned backend source checksum mismatch: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-repo', type=Path, required=True)
    parser.add_argument('--python', type=Path, required=True, help='Existing backend root test interpreter')
    parser.add_argument('--evidence-dir', type=Path, default=Path('docs/evidence/android/integration'))
    args = parser.parse_args()
    evidence_dir = (ROOT / args.evidence_dir).resolve()
    if not evidence_dir.is_relative_to((ROOT / 'docs/evidence/android').resolve()):
        raise ValueError('Evidence must stay under Android evidence ownership')
    interpreter = args.python.absolute()  # Preserve venv identity; do not resolve its executable symlink.
    if not interpreter.is_file():
        raise ValueError('An existing Python test interpreter is required')
    manifest = json.loads((ROOT / 'contracts/v1/manifest.json').read_text())
    subprocess.run(['python3', str(ROOT / 'scripts/verify-contracts.py')], cwd=ROOT, check=True)
    build = ROOT / 'android/build/backend-integration'
    build.mkdir(parents=True, exist_ok=True)
    # A small allowlist prevents application configuration and credentials from
    # reaching the backend process or influencing its selected synthetic database.
    environment = {k: v for k, v in os.environ.items() if k in {
        'HOME', 'PATH', 'TMPDIR', 'JAVA_HOME', 'ANDROID_HOME', 'ANDROID_SDK_ROOT',
        'GRADLE_USER_HOME', 'LANG', 'LC_ALL', 'SYSTEMROOT',
    }}
    result = None
    with tempfile.TemporaryDirectory(prefix='source-', dir=build) as temporary:
        source = Path(temporary)
        export_backend(args.backend_repo, source, manifest)
        print('PASS pinned backend identity and 10 source checksums', flush=True)
        environment.update(PHOTOHOUSE_TEST_BACKEND=str(source), PHOTOHOUSE_TEST_PYTHON=str(interpreter),
                           PHOTOHOUSE_TEST_SERVER=str(ROOT / 'android/integration/backend_server.py'))
        with (build / 'gradle.log').open('w') as log:
            result = subprocess.run([str(ROOT / 'android/gradlew'), '-p', str(ROOT / 'android'),
                ':live-core:backendIntegrationTest', '--console=plain'], cwd=ROOT, env=environment,
                stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            print('FAIL backend integration; inspect ignored android/build/backend-integration/gradle.log')
            return result.returncode
        report = ROOT / 'android/live-core/build/test-results/backendIntegrationTest/TEST-dev.photohouse.connected.core.BackendIntegrationTest.xml'
        suite = ET.parse(report).getroot()
        assert suite.attrib['tests'] == '7' and all(suite.attrib[k] == '0' for k in ('failures', 'errors', 'skipped'))
        suite.attrib.pop('hostname', None)
        for tag in ('system-out', 'system-err'):
            for element in suite.findall(tag):
                suite.remove(element)
        output = evidence_dir
        output.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(suite).write(output / 'backend-integration-tests.xml', encoding='utf-8', xml_declaration=True)
        versions = subprocess.check_output([str(interpreter), '-I', '-B', '-c',
            'import sys,importlib.metadata,json;print(json.dumps({"python":sys.version.split()[0],**{n:importlib.metadata.version(n) for n in ("uvicorn","fastapi","starlette","sqlalchemy","alembic","httpx","Pillow")}}))'], env=environment, text=True)
        evidence = {'backend_commit': manifest['backend_commit'], 'contract_version': manifest['contract_version'],
                    'backend_source_checksums': len(manifest['backend_sources']), 'versions': json.loads(versions),
                    'tests': 7, 'failures': 0, 'errors': 0, 'skipped': 0,
                    'transport': 'real loopback TLS to pinned ASGI and temporary migrated SQLite',
                    'real_backend_deployment_accessed': False, 'backend_checkout_modified': False}
    assert not source.exists(), 'Temporary source export was not removed'
    evidence['source_export_removed'] = True
    (output / 'result.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('PASS 7 actual-backend Android TLS integration tests; temporary source export removed')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Package a checksum-selected qualified Windows literal DLL without rebuilding.

This produces an unpublished deterministic wheel, not a deployment or a new
qualification. Provenance is a public projection of a checksum-bound receipt.
"""
import argparse
import base64
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tomllib
import zipfile

from package_vector_kernel import pe_x64

ROOT = Path(__file__).resolve().parents[1]
DIST = 'photohouse_literal_kernel-0.1.0.dist-info'
WHEEL_NAME = 'photohouse_literal_kernel-0.1.0-cp312-abi3-win_amd64.whl'


def _need(value, code):
    if not value:
        raise ValueError(code)


def _canonical(path, *, directory=False):
    path = Path(path)
    _need(path.is_absolute() and path.resolve(strict=True) == path
          and not path.is_symlink(), 'canonical_packaging_path_required')
    _need(path.is_dir() if directory else path.is_file(), 'regular_packaging_input_required')
    if os.name == 'nt':
        _need(path.drive.upper() == 'D:', 'packaging_requires_D_scratch')
    return path


def _qualification(path, expected):
    _need(type(expected) is str and re.fullmatch('[0-9a-f]{64}', expected),
          'complete_packaging_provenance_required')
    path = _canonical(path)
    _need(0 < path.stat().st_size <= 65536, 'qualification_receipt_size_cap')
    raw = path.read_bytes()
    _need(hashlib.sha256(raw).hexdigest() == expected, 'qualification_receipt_hash_mismatch')
    try:
        value = json.loads(raw.decode('utf-8'))
        _need(type(value) is dict and value['status'] ==
              'WINDOWS_QUALIFIED_NOT_ACTIVATED_EXACT_SCOPE_RELEASED'
              and value['production_activated'] is False
              and type(value['kernel_cases']) is int and value['kernel_cases'] == 832
              and type(value['total_tests']) is int and value['total_tests'] == 69
              and value['tests_and_benchmarks_source_verified'] is True
              and value['PE_AMD64_verified'] is True, 'qualified_receipt_refused')
        native_sha256 = value['native_artifact_ref']['sha256']
        _need(value['qualified_native_sha256'] == native_sha256
              and type(value['native_artifact_ref']['bytes']) is int,
              'qualified_receipt_refused')
        return (native_sha256, value['native_artifact_ref']['bytes'],
                value['native_build_source_commit'], value['source_commit'])
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError):
        raise ValueError('qualified_receipt_refused') from None


def package(native, vendor, output, *, qualification, qualification_sha256):
    native_sha256, native_bytes, native_source_commit, qualified_source_commit = \
        _qualification(qualification, qualification_sha256)
    for value, width in ((native_sha256, 64), (native_source_commit, 40),
                         (qualified_source_commit, 40)):
        _need(type(value) is str and re.fullmatch('[0-9a-f]{' + str(width) + '}', value),
              'complete_packaging_provenance_required')
    output = Path(output)
    _need(not output.exists() and not output.is_symlink(), 'new_output_required')
    _canonical(output.parent, directory=True)
    native, vendor = _canonical(native), _canonical(vendor, directory=True)
    _need(native.stat().st_size <= 2 * 1024**2, 'native_size_cap')
    binary = native.read_bytes()
    _need(len(binary) == native_bytes and hashlib.sha256(binary).hexdigest() == native_sha256,
          'qualified_native_hash_mismatch')
    pe_x64(binary)
    files = {
        'photohouse_literal_kernel.pyd': binary,
        f'{DIST}/METADATA': (b'Metadata-Version: 2.4\nName: photohouse-literal-kernel\n'
            b'Version: 0.1.0\nSummary: Optional exact PhotoHouse literal quality kernel\n'
            b'License-Expression: Apache-2.0 AND MIT\nRequires-Python: >=3.12\n\n'),
        f'{DIST}/WHEEL': (b'Wheel-Version: 1.0\nGenerator: PhotoHouse local native packager\n'
            b'Root-Is-Purelib: false\nTag: cp312-abi3-win_amd64\n'),
        f'{DIST}/licenses/PhotoHouse-LICENSE': (ROOT / 'LICENSE').read_bytes(),
        f'{DIST}/licenses/rust-anything-MIT.txt':
            (ROOT / 'third_party/licenses/rust-anything-MIT.txt').read_bytes(),
    }
    lock_path = ROOT / 'rust/literal-python/Cargo.lock'
    lock = tomllib.loads(lock_path.read_text(encoding='utf-8'))
    dependencies = []
    for entry in lock['package']:
        if 'source' not in entry:
            continue
        _need(entry['source'].startswith('registry+')
              and re.fullmatch('[A-Za-z0-9_-]+', entry['name'])
              and re.fullmatch('[A-Za-z0-9.+-]+', entry['version'])
              and re.fullmatch('[0-9a-f]{64}', entry['checksum']), 'locked_registry_dependency_required')
        directory = _canonical(vendor / (entry['name'] + '-' + entry['version']), directory=True)
        manifest = directory / 'Cargo.toml'
        checksums = json.loads(_canonical(directory / '.cargo-checksum.json').read_text(encoding='utf-8'))
        metadata = tomllib.loads(_canonical(manifest).read_text(encoding='utf-8'))['package']
        _need(metadata['name'] == entry['name'] and metadata['version'] == entry['version']
              and checksums['package'] == entry['checksum']
              and hashlib.sha256(manifest.read_bytes()).hexdigest() == checksums['files'].get('Cargo.toml'),
              'vendored_dependency_lock_mismatch')
        notices = []
        for path in sorted(directory.iterdir()):
            if not path.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT')):
                continue
            _need(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', path.name)
                  and not path.name.endswith('.'), 'canonical_notice_name_required')
            raw = _canonical(path).read_bytes()
            _need(hashlib.sha256(raw).hexdigest() == checksums['files'].get(path.name),
                  'dependency_notice_hash_mismatch')
            name = f'{DIST}/licenses/{entry["name"]}-{entry["version"]}/{path.name}'
            files[name] = raw
            notices.append(name)
        _need(notices, 'dependency_notices_required')
        dependencies.append({'name': entry['name'], 'version': entry['version'],
                             'license': metadata.get('license'), 'notices': notices})
    provenance = {'native_source_commit': native_source_commit,
        'qualified_source_commit': qualified_source_commit, 'qualification_sha256': qualification_sha256,
        'native_sha256': native_sha256, 'target': 'x86_64-pc-windows-msvc',
        'cargo_lock_sha256': hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        'literal_policy_version': 1, 'minimum_python': '3.12', 'dependencies': dependencies,
        'scope': 'Packaging only; no rebuild, install, activation or new qualification'}
    files[f'{DIST}/build.json'] = (json.dumps(provenance, indent=2, sort_keys=True) + '\n').encode()
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, raw in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
        writer.writerow((name, 'sha256=' + digest, len(raw)))
    writer.writerow((f'{DIST}/RECORD', '', ''))
    files[f'{DIST}/RECORD'] = record.getvalue().encode()
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    output.chmod(0o600)
    return {'wheel': output.name, 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'native_sha256': native_sha256, 'dependency_notice_sets': len(dependencies)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('native', 'vendor', 'output-dir', 'qualification'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--qualification-sha256', required=True)
    args = parser.parse_args()
    result = package(args.native.absolute(), args.vendor.absolute(), args.output_dir.absolute() / WHEEL_NAME,
        qualification=args.qualification.absolute(), qualification_sha256=args.qualification_sha256)
    print(json.dumps(result))


if __name__ == '__main__':
    main()

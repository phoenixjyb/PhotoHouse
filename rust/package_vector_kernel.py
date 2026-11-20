"""Package an explicitly built MSVC x64 extension as an unpublished ABI3 wheel.

No build, download or installation occurs. Locked vendored crates supply their
license notices. The caller must separately qualify native imports and workers.
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
import struct
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIST = 'photohouse_vector_kernel-0.1.0.dist-info'
WHEEL_NAME = 'photohouse_vector_kernel-0.1.0-cp39-abi3-win_amd64.whl'


def pe_x64(data):
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('PE image required')
    offset = struct.unpack_from('<I', data, 60)[0]
    if offset + 26 > len(data) or data[offset:offset + 4] != b'PE\0\0':
        raise ValueError('valid PE header required')
    machine, = struct.unpack_from('<H', data, offset + 4)
    flags, = struct.unpack_from('<H', data, offset + 22)
    magic, = struct.unpack_from('<H', data, offset + 24)
    if machine != 0x8664 or not flags & 0x2000 or magic != 0x20B:
        raise ValueError('AMD64 PE32+ DLL required')


def package(native, vendor, output, source_commit):
    if re.fullmatch('[0-9a-f]{40}', source_commit) is None:
        raise ValueError('full source commit required')
    if output.exists():
        raise ValueError('new output required')
    for path in (native, vendor, output.parent):
        if not path.is_absolute() or path.resolve(strict=True) != path or path.is_symlink():
            raise ValueError('canonical absolute paths required')
        if os.name == 'nt' and path.drive.upper() != 'D:':
            raise ValueError('Windows packaging inputs and output must be on D:')
    binary = native.read_bytes(); pe_x64(binary)
    files = {'photohouse_vector_kernel.pyd': binary,
             f'{DIST}/METADATA': b'Metadata-Version: 2.4\nName: photohouse-vector-kernel\nVersion: 0.1.0\nSummary: Optional PhotoHouse exact vector engine\nLicense-Expression: Apache-2.0 AND PSF-2.0\nRequires-Python: >=3.9\n\n',
             f'{DIST}/WHEEL': b'Wheel-Version: 1.0\nGenerator: PhotoHouse local native packager\nRoot-Is-Purelib: false\nTag: cp39-abi3-win_amd64\n',
             f'{DIST}/licenses/PhotoHouse-LICENSE': (ROOT / 'LICENSE').read_bytes(),
             f'{DIST}/licenses/rust-anything-MIT.txt': (ROOT / 'third_party/licenses/rust-anything-MIT.txt').read_bytes(),
             f'{DIST}/licenses/Python-PSF.txt': (ROOT / 'third_party/python/LICENSE.txt').read_bytes(),
             f'{DIST}/licenses/Python-NOTICE.md': (ROOT / 'third_party/python/NOTICE.md').read_bytes()}
    dependencies = []
    lock = tomllib.loads((ROOT / 'rust/vector-python/Cargo.lock').read_text())
    for entry in lock['package']:
        if 'source' not in entry:
            continue
        if not entry['source'].startswith('registry+'):
            raise ValueError('registry dependencies required')
        directory = vendor / entry['name']
        if directory.is_symlink() or directory.resolve(strict=True).parent != vendor:
            raise ValueError('canonical vendored crate required')
        metadata = tomllib.loads((directory / 'Cargo.toml').read_text(encoding='utf-8'))['package']
        checksums = json.loads((directory / '.cargo-checksum.json').read_text(encoding='utf-8'))
        if (metadata['name'] != entry['name'] or metadata['version'] != entry['version']
                or checksums['package'] != entry['checksum']):
            raise ValueError('vendored crate lock mismatch')
        notices = []
        for path in sorted(directory.iterdir()):
            if not path.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE', 'COPYRIGHT')):
                continue
            if path.is_symlink() or not path.is_file():
                raise ValueError('regular license file required')
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != checksums['files'].get(path.name):
                raise ValueError('license checksum mismatch')
            member = f'{DIST}/licenses/{entry["name"]}-{entry["version"]}/{path.name}'
            files[member] = raw; notices.append(member)
        if not notices:
            raise ValueError('dependency license notices required')
        dependencies.append({'name': entry['name'], 'version': entry['version'],
                             'license': metadata.get('license'), 'notices': notices})
    provenance = {'source_commit': source_commit, 'target': 'x86_64-pc-windows-msvc',
                  'native_sha256': hashlib.sha256(binary).hexdigest(),
                  'cargo_lock_sha256': hashlib.sha256((ROOT / 'rust/vector-python/Cargo.lock').read_bytes()).hexdigest(),
                  'dependencies': dependencies,
                  'qualification': 'packaging only; separate native import, exact parity and Search integration checks required'}
    files[f'{DIST}/build.json'] = (json.dumps(provenance, indent=2, sort_keys=True) + '\n').encode()
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, raw in sorted(files.items()):
        checksum = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode('ascii')
        writer.writerow((name, 'sha256=' + checksum, len(raw)))
    writer.writerow((f'{DIST}/RECORD', '', ''))
    files[f'{DIST}/RECORD'] = record.getvalue().encode()
    with zipfile.ZipFile(output, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED; info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return {'wheel': output.name, 'bytes': output.stat().st_size,
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'native_sha256': provenance['native_sha256'], 'dependency_notice_sets': len(dependencies)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--vendor', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--source-commit', required=True)
    args = parser.parse_args()
    print(json.dumps(package(args.native.resolve(strict=True), args.vendor.resolve(strict=True),
                             args.output_dir.resolve(strict=True) / WHEEL_NAME, args.source_commit)))


if __name__ == '__main__':
    main()

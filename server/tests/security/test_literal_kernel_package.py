"""Deterministic wheel/RECORD and admission refusals using a tiny generated PE."""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'rust'))
import package_literal_kernel as package


class LiteralKernelPackageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.vendor = self.root / 'vendor'; self.vendor.mkdir()
        self.source = self.root / 'source'
        (self.source / 'rust/literal-python').mkdir(parents=True)
        (self.source / 'third_party/licenses').mkdir(parents=True)
        (self.source / 'LICENSE').write_text('generated project license')
        (self.source / 'third_party/licenses/rust-anything-MIT.txt').write_text('generated MIT notice')
        (self.source / 'rust/literal-python/Cargo.lock').write_text('''version = 4
[[package]]
name = "fixture-dependency"
version = "1.0.0"
source = "registry+https://example.test/index"
checksum = "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
''')
        self.crate = self.vendor / 'fixture-dependency-1.0.0'; self.crate.mkdir()
        (self.crate / 'Cargo.toml').write_text('[package]\nname="fixture-dependency"\nversion="1.0.0"\nlicense="MIT"\n')
        (self.crate / 'LICENSE-MIT').write_text('generated dependency notice')
        self.checksums = {'package': 'd' * 64, 'files': {
            name: hashlib.sha256((self.crate / name).read_bytes()).hexdigest()
            for name in ('Cargo.toml', 'LICENSE-MIT')}}
        (self.crate / '.cargo-checksum.json').write_text(json.dumps(self.checksums))
        binary = bytearray(128); binary[:2] = b'MZ'
        struct.pack_into('<I', binary, 60, 64); binary[64:68] = b'PE\0\0'
        struct.pack_into('<H', binary, 68, 0x8664)
        struct.pack_into('<H', binary, 86, 0x2000)
        struct.pack_into('<H', binary, 88, 0x20B)
        self.native = self.root / 'fixture.pyd'; self.native.write_bytes(binary)
        self.pin = hashlib.sha256(binary).hexdigest()
        self.qualification = self.root / 'qualification.json'
        self.qualified = dict(status='WINDOWS_QUALIFIED_NOT_ACTIVATED_EXACT_SCOPE_RELEASED',
            production_activated=False, kernel_cases=832, total_tests=69,
            tests_and_benchmarks_source_verified=True, PE_AMD64_verified=True,
            native_artifact_ref={'sha256': self.pin, 'bytes': len(binary)},
            qualified_native_sha256=self.pin, native_build_source_commit='a' * 40, source_commit='b' * 40)
        self.save_qualification()

    def save_qualification(self):
        self.qualification.write_text(json.dumps(self.qualified))

    def build(self, output, **kwargs):
        values = dict(qualification=self.qualification,
            qualification_sha256=hashlib.sha256(self.qualification.read_bytes()).hexdigest())
        values.update(kwargs)
        with patch.object(package, 'ROOT', self.source):
            return package.package(self.native, self.vendor, output, **values)

    def test_wheel_preserves_binary_provenance_notices_and_complete_record(self):
        output = self.root / package.WHEEL_NAME
        result = self.build(output)
        self.assertEqual(result['dependency_notice_sets'], 1)
        with zipfile.ZipFile(output) as archive:
            names = archive.namelist(); self.assertEqual(len(names), len(set(names)))
            self.assertEqual(archive.read('photohouse_literal_kernel.pyd'), self.native.read_bytes())
            record = list(csv.reader(io.StringIO(archive.read(package.DIST + '/RECORD').decode())))
            self.assertEqual({r[0] for r in record}, set(names))
            for name, digest, size in record[:-1]:
                raw = archive.read(name)
                self.assertEqual(len(raw), int(size))
                self.assertEqual(digest, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode())
            self.assertEqual(record[-1], [package.DIST + '/RECORD', '', ''])
            metadata = archive.read(package.DIST + '/METADATA').decode()
            self.assertIn('Requires-Python: >=3.12', metadata)
            self.assertIn('cp312-abi3-win_amd64', archive.read(package.DIST + '/WHEEL').decode())
            build = json.loads(archive.read(package.DIST + '/build.json'))
            self.assertEqual(build['native_sha256'], self.pin)
            self.assertEqual(build['native_source_commit'], 'a' * 40)
            self.assertEqual(build['qualified_source_commit'], 'b' * 40)
            self.assertNotIn(str(self.root), json.dumps(build))
        second = self.root / 'second.whl'; self.build(second)
        self.assertEqual(output.read_bytes(), second.read_bytes())

    def test_tampered_binary_wrong_pe_and_existing_output_refuse(self):
        output = self.root / package.WHEEL_NAME
        self.native.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'qualified_native_hash_mismatch'):
            self.build(output)
        self.native.write_bytes(b'not a PE')
        self.qualified['native_artifact_ref'] = dict(sha256=hashlib.sha256(self.native.read_bytes()).hexdigest(), bytes=self.native.stat().st_size)
        self.qualified['qualified_native_sha256'] = self.qualified['native_artifact_ref']['sha256']
        self.save_qualification()
        with self.assertRaisesRegex(ValueError, 'PE image required'):
            self.build(output)
        output.write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'new_output_required'):
            self.build(output)
        self.assertEqual(output.read_bytes(), b'keep')

    def test_missing_notice_tampering_and_lock_mismatch_refuse(self):
        output = self.root / package.WHEEL_NAME
        (self.crate / 'LICENSE-MIT').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'dependency_notice_hash_mismatch'):
            self.build(output)
        (self.crate / 'LICENSE-MIT').unlink()
        with self.assertRaisesRegex(ValueError, 'dependency_notices_required'):
            self.build(output)
        (self.crate / 'Cargo.toml').write_text('[package]\nname="other"\nversion="1.0.0"\n')
        with self.assertRaisesRegex(ValueError, 'vendored_dependency_lock_mismatch'):
            self.build(output)

    def test_incomplete_provenance_refuses_before_writing(self):
        output = self.root / package.WHEEL_NAME
        with self.assertRaisesRegex(ValueError, 'qualification_receipt_hash_mismatch'):
            self.build(output, qualification_sha256='0' * 64)
        self.qualified['source_commit'] = 'short'; self.save_qualification()
        with self.assertRaisesRegex(ValueError, 'complete_packaging_provenance_required'):
            self.build(output)
        self.assertFalse(output.exists())

    def test_failed_or_unverified_receipt_is_not_packaged(self):
        for change in ({'status': 'FAILED'}, {'total_tests': 68}, {'production_activated': True},
                       {'tests_and_benchmarks_source_verified': False}, {'PE_AMD64_verified': False}):
            original = dict(self.qualified); self.qualified.update(change); self.save_qualification()
            with self.assertRaisesRegex(ValueError, '^qualified_receipt_refused$'):
                self.build(self.root / package.WHEEL_NAME)
            self.qualified = original

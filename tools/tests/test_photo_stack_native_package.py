"""Native wheel structure, RECORD, licenses and corrupt-input refusal."""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import package_photo_stack_native as package


class NativePackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / 'rust/photo-stack-python').mkdir(parents=True)
        (self.root / 'third_party/licenses').mkdir(parents=True)
        (self.root / 'LICENSE').write_bytes(b'project license')
        (self.root / 'third_party/licenses/rust-anything-MIT.txt').write_bytes(b'scaffold notice')
        crate = self.root / 'vendor/sample'; crate.mkdir(parents=True)
        notice = b'required dependency notice'
        (crate / 'LICENSE-MIT').write_bytes(notice)
        (crate / 'Cargo.toml').write_text('[package]\nname="sample"\nversion="1.0.0"\nlicense="MIT"\n')
        (crate / '.cargo-checksum.json').write_text(json.dumps({
            'package': 'a' * 64, 'files': {'LICENSE-MIT': hashlib.sha256(notice).hexdigest()}}))
        (self.root / 'rust/photo-stack-python/Cargo.lock').write_text(
            'version=4\n[[package]]\nname="sample"\nversion="1.0.0"\n'
            'source="registry+https://github.com/rust-lang/crates.io-index"\nchecksum="' + 'a'*64 + '"\n')
        binary = bytearray(128); binary[:2] = b'MZ'
        struct.pack_into('<I', binary, 60, 64); binary[64:68] = b'PE\0\0'
        struct.pack_into('<H', binary, 68, 0x8664)
        struct.pack_into('<H', binary, 86, 0x2000)
        struct.pack_into('<H', binary, 88, 0x20B)
        self.native = self.root / 'native.dll'; self.native.write_bytes(binary)
        self.output = self.root / package.WHEEL_NAME

    def build(self):
        with patch.object(package, 'ROOT', self.root):
            return package.package(self.native, self.root / 'vendor', self.output, 'b' * 40)

    def test_complete_record_and_dependency_notice_and_repeatability(self):
        first = self.build(); self.assertEqual(first['dependency_notice_sets'], 1)
        with zipfile.ZipFile(self.output) as archive:
            self.assertIn('Tag: cp39-abi3-win_amd64', archive.read(package.DIST + '/WHEEL').decode())
            records = list(csv.reader(io.StringIO(archive.read(package.DIST + '/RECORD').decode())))
            self.assertEqual(set(r[0] for r in records), set(archive.namelist()))
            for name, checksum, size in records[:-1]:
                raw = archive.read(name)
                actual = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b'=').decode()
                self.assertEqual(checksum, 'sha256=' + actual)
                self.assertEqual(int(size), len(raw))
            self.assertEqual(archive.read(package.DIST + '/licenses/sample-1.0.0/LICENSE-MIT'),
                             b'required dependency notice')
        raw = self.output.read_bytes(); self.output.unlink(); self.build()
        self.assertEqual(raw, self.output.read_bytes())

    def test_refuses_wrong_machine_and_truncated_PE(self):
        for raw in (b'', b'MZ', bytes(128), self.native.read_bytes()[:80]):
            self.native.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.build()
            self.assertFalse(self.output.exists())
        raw = bytearray(128); raw[:2] = b'MZ'; struct.pack_into('<I', raw, 60, 64)
        raw[64:68] = b'PE\0\0'; struct.pack_into('<H', raw, 68, 0xAA64)
        self.native.write_bytes(raw)
        with self.assertRaises(ValueError):
            self.build()

    def test_refuses_changed_notice_and_lock_mismatch_before_output(self):
        notice = self.root / 'vendor/sample/LICENSE-MIT'; notice.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'license checksum mismatch'):
            self.build()
        self.assertFalse(self.output.exists())
        (self.root / 'vendor/sample/Cargo.toml').write_text('[package]\nname="sample"\nversion="2.0.0"\n')
        with self.assertRaisesRegex(ValueError, 'lock mismatch'):
            self.build()

    def test_existing_output_and_bad_source_identity_refused(self):
        self.output.write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError, 'new output'):
            self.build()
        self.assertEqual(self.output.read_bytes(), b'preserve')
        self.output.unlink()
        with patch.object(package, 'ROOT', self.root), self.assertRaisesRegex(ValueError, 'full source'):
            package.package(self.native, self.root / 'vendor', self.output, 'short')


if __name__ == '__main__':
    unittest.main()

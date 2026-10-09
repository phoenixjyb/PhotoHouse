#!/usr/bin/env python3
"""Verify independent discovery/v2 pin and exact synthetic producer examples."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--backend-root', type=Path)
args = parser.parse_args()
pack = ROOT / 'android/discovery-delivery-contract'
manifest = json.loads((pack / 'manifest.json').read_text())
assert manifest['contract'] == 'photohouse-discovery-delivery-2'
assert manifest['backend_commit'] == '590cc52ceeb7cdef1d2cae0bbc6aa36c16d75cd6'
assert set(manifest['files']) == {'CONTRACT.md', 'examples-v2.json'}
for name, digest in manifest['files'].items():
    assert hashlib.sha256((pack / name).read_bytes()).hexdigest() == digest, name
example = (pack / 'examples-v2.json').read_bytes()
assert example == (ROOT / 'android/home-core/src/test/resources/discovery-delivery-v2.json').read_bytes()
value = json.loads(example)
assert value['search_response']['version'] == 2
assert value['search_response']['total'] == 4
photo = ROOT / 'android/home-core/src/test/resources/discovery-delivery-photo.jpg'
assert hashlib.sha256(photo.read_bytes()).hexdigest() == manifest['backend_sources']['tests/security/fixtures/home-8x8.jpg']
for name, digest in manifest['backend_sources'].items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    if args.backend_root:
        blob = subprocess.check_output(['git', 'show', manifest['backend_commit'] + ':' + name], cwd=args.backend_root)
        assert hashlib.sha256(blob).hexdigest() == digest, name
        assert (args.backend_root / name).read_bytes() == blob, 'Producer working-tree drift: ' + name
print(f"PASS discovery/v2 independent pin, {len(manifest['backend_sources'])} producer inputs and exact synthetic replay resources")

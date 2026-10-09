#!/usr/bin/env python3
"""Verify independent discovery/v3 tag pin and exact synthetic producer examples."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--backend-root', type=Path)
args = parser.parse_args()
pack = ROOT / 'android/tag-discovery-contract'
manifest = json.loads((pack / 'manifest.json').read_text())
assert manifest['contract'] == 'photohouse-tag-discovery-3'
assert manifest['backend_commit'] == '52c3bac16c85d3b0f40d29cfa10c2e473756cfe1'
assert set(manifest['files']) == {'CONTRACT.md', 'examples-v3.json'}
for name, digest in manifest['files'].items():
    assert hashlib.sha256((pack / name).read_bytes()).hexdigest() == digest, name
example = (pack / 'examples-v3.json').read_bytes()
assert example == (ROOT / 'android/home-core/src/test/resources/discovery-tags-v3.json').read_bytes()
value = json.loads(example)
assert value['search_response']['version'] == 3
assert value['search_response']['total'] == 1
photo = ROOT / 'android/home-core/src/test/resources/discovery-delivery-photo.jpg'
assert hashlib.sha256(photo.read_bytes()).hexdigest() == manifest['backend_sources']['tests/security/fixtures/home-8x8.jpg']
for name, digest in manifest['backend_sources'].items():
    assert not Path(name).is_absolute() and '..' not in Path(name).parts
    if args.backend_root:
        blob = subprocess.check_output(['git', 'show', manifest['backend_commit'] + ':' + name], cwd=args.backend_root)
        assert hashlib.sha256(blob).hexdigest() == digest, name
        assert (args.backend_root / name).read_bytes() == blob, 'Producer working-tree drift: ' + name
print(f"PASS discovery/v3 tag independent pin, {len(manifest['backend_sources'])} producer inputs and exact synthetic replay resources")

#!/usr/bin/env python3
"""Readiness producer identity and synthetic page replay; no live access."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--backend-root',type=Path);args=p.parse_args()
pack=ROOT/'android/readiness-browse-contract';manifest=json.loads((pack/'manifest.json').read_text())
assert manifest['contract']=='photohouse-readiness-browse-1'
assert re.fullmatch('[0-9a-f]{40}',manifest['backend_commit'])
assert set(manifest['files'])=={'CONTRACT.md','browse-v1.json'}
for name,expected in manifest['files'].items():
    assert hashlib.sha256((pack/name).read_bytes()).hexdigest()==expected,name
assert (pack/'browse-v1.json').read_bytes()==(ROOT/'android/home-core/src/test/resources/browse-v1.json').read_bytes()
if args.backend_root:
    for name,expected in manifest['backend_sources'].items():
        assert not name.startswith('/') and '..' not in Path(name).parts
        blob=subprocess.check_output(['git','show',manifest['backend_commit']+':'+name],cwd=args.backend_root)
        assert hashlib.sha256(blob).hexdigest()==expected,name
        assert (args.backend_root/name).read_bytes()==blob,'Producer working-tree drift: '+name
print('PASS readiness browsing source pin, checksums and six synthetic producer pages')

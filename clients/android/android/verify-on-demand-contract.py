#!/usr/bin/env python3
"""Verify the independent on-demand producer pin and exact synthetic example."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--backend-root',type=Path);args=p.parse_args()
pack=ROOT/'android/on-demand-contract';manifest=json.loads((pack/'manifest.json').read_text())
assert manifest['contract']=='photohouse-on-demand-1'
assert re.fullmatch('[0-9a-f]{40}',manifest['backend_commit'])
for name,expected in manifest['files'].items():
    assert name in ('CONTRACT.md','catalog-v3.json')
    assert hashlib.sha256((pack/name).read_bytes()).hexdigest()==expected,name
example=(pack/'catalog-v3.json').read_bytes()
assert example==(ROOT/'android/home-core/src/test/resources/catalog-v3.json').read_bytes()
value=json.loads(example);assert value['version']==3 and value['total']==2
assert value['items'][0]['video']['state']=='direct'
assert value['items'][1]['previews']['display']['state']=='on_demand'
if args.backend_root:
    for name,expected in manifest['backend_sources'].items():
        assert not name.startswith('/') and '..' not in Path(name).parts
        blob=subprocess.check_output(['git','show',manifest['backend_commit']+':'+name],cwd=args.backend_root)
        assert hashlib.sha256(blob).hexdigest()==expected,name
        assert (args.backend_root/name).read_bytes()==blob,'Producer working-tree drift: '+name
print('PASS on-demand producer pin, strict v3 synthetic example and independent phone display contract')

#!/usr/bin/env python3
"""Replay pinned home-feed ASGI checks in disposable synthetic files, without listeners."""
import argparse, hashlib, json, subprocess, tempfile
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--backend', type=Path, required=True)
p.add_argument('--python', type=Path, required=True)
a = p.parse_args()
here = Path(__file__).resolve().parent
inputs = json.loads((here.parent/'contract/source-inputs.json').read_text())
bundle = json.loads((here/'bundle-inputs.json').read_text())
pin = inputs['implementation_commit']
assert bundle['source_commit'] == pin

def blob(path):
    return subprocess.check_output(['git','show',f'{pin}:{path}'], cwd=a.backend)
for path, digest in inputs['files'].items():
    assert hashlib.sha256(blob(path)).hexdigest() == digest, path
for name in ['home-feed-contract-v1.json','home-feed-manifest.example.json']:
    assert (here.parent/'contract'/name).read_bytes() == blob('docs/security/'+name)
for name in ['home-8x8.jpg','home-3840x2160.jpg']:
    assert (here.parent/'src/test/resources'/name).read_bytes() == blob('tests/security/fixtures/'+name)
fixture_paths = {'fixture/selection.json':'docs/security/home-feed-manifest.example.json',
    'fixture/prepared/grid/101.jpg':'tests/security/fixtures/home-8x8.jpg',
    'fixture/prepared/display/101.jpg':'tests/security/fixtures/home-3840x2160.jpg'}
with tempfile.TemporaryDirectory(prefix='photohouse-home-asgi-') as temporary:
    root = Path(temporary).resolve()
    for path, digest in bundle['files'].items():
        source = path.removeprefix('source/') if path.startswith('source/') else fixture_paths[path]
        data = blob(source)
        assert hashlib.sha256(data).hexdigest() == digest, path
        target = root/path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
    result = subprocess.check_output([str(a.python), '-I', '-B', str(here/'package_smoke.py'), str(root)], text=True)
    receipt = json.loads(result)
    receipt.update(implementation_commit=pin, source_hashes_verified=len(inputs['files']),
                   contract_sha256=inputs['files']['docs/security/home-feed-contract-v1.json'],
                   evidence_tier='in-process actual backend; separate from Kotlin mock TLS and device tests')
    print(json.dumps(receipt, indent=2))

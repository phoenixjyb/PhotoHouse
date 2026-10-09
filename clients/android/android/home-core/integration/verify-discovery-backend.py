#!/usr/bin/env python3
"""Extract verified Git blobs and replay synthetic discovery ASGI without a listener."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--backend', type=Path, required=True)
parser.add_argument('--python', type=Path, required=True)
args = parser.parse_args()
here = Path(__file__).resolve().parent
contract = here.parent / 'discovery-contract'
subprocess.run(['python3', str(here.parents[1] / 'verify-discovery-contract.py')], check=True)
pin = (contract / 'backend-pin.txt').read_text().strip()
inputs = json.loads((contract / 'source-inputs.json').read_text())['files']
with tempfile.TemporaryDirectory(prefix='photohouse-discovery-asgi-') as temporary:
    root = Path(temporary).resolve()
    for item in inputs:
        data = subprocess.check_output(['git', 'show', pin + ':' + item['path']], cwd=args.backend)
        assert len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'], item['path']
        target = root / item['path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    for name in ['home-discovery-contract-v1.json', 'home-discovery-schema-v1.json', 'home-discovery-examples-v1.json']:
        assert (contract / name).read_bytes() == (root / 'docs/security' / name).read_bytes()
    replay = root / 'docs/security/evidence/home-discovery-v1/replay.py'
    raw = subprocess.check_output([str(args.python), '-I', '-B', str(replay), '--source-root', str(root)], text=True)
    receipt = json.loads(raw)
    assert receipt['check_count'] == 11 and receipt['status'] == 'PASS_SYNTHETIC_ASGI_ONLY'
    receipt.update(implementation_commit=pin, source_hashes_verified=len(inputs),
                   evidence_tier='actual in-process backend; separate from Kotlin mock TLS and physical device')
    print(json.dumps(receipt, indent=2))

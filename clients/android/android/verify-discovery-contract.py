#!/usr/bin/env python3
"""Verify the independently frozen discovery contract; no network or real metadata."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
contract = root / 'home-core/discovery-contract'
pin = '54f68427058c45f6bcc5a863cc6d708f5b325e45'
assert (contract / 'backend-pin.txt').read_text().strip() == pin
expected = {
    'home-discovery-contract-v1.json': '754c9edcb7d8dec250d900d942f8a7a6318a1e54680d06d3a1743ff27e05d9cd',
    'home-discovery-schema-v1.json': 'bc15d646ef83a6c5ee91199b3ba212ceaec068cb769541e7373cd2303cf8b92d',
    'home-discovery-examples-v1.json': 'bebb456c9acb4e386400b13888c0c407681c19dbd63903fd9edf39e935c4cdff',
    'source-inputs.json': 'bf4afdfe74e2c45e0b8bd129637a314f50da1e582e9635d8cf7bd8a201c76ccf',
}
for name, sha in expected.items():
    assert hashlib.sha256((contract / name).read_bytes()).hexdigest() == sha, name
manifest = json.loads((contract / 'source-inputs.json').read_text())
assert manifest['implementation_commit'] == pin and len(manifest['files']) == 19
paths = [item['path'] for item in manifest['files']]
assert len(set(paths)) == 19
assert all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in paths)
assert (root / 'home-core/contract-v2/backend-pin.txt').read_text().strip() == 'a5d0f595d7cd26379ed2845a944ec1d58d7885cc'
assert not (root / 'tv/src/main/assets').exists()
print('PASS independent discovery pin, contract/schema/examples and 19-input manifest; v2 pin unchanged')

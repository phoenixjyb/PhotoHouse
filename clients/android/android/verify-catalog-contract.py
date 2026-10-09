#!/usr/bin/env python3
"""Check the independent frozen v2 inputs and test-only media; no service access."""
from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent
contract=root/'home-core/contract-v2'
assert (contract/'backend-pin.txt').read_text().strip() == 'a5d0f595d7cd26379ed2845a944ec1d58d7885cc'
expected={'home-catalog-contract-v2.json':'13cf10892dc4e91631ad71b5ee4bed21baa44697f1e779851c19026dbe606120',
'home-catalog-response-v2.example.json':'2cde48dd6de163e9fb0f78baf6de14e4da5bcdf12ce9d3830681d91dc4f109f9',
'source-inputs.json':'77586ebb028751d9600b0f04356c2e943f89f432253b3bb647916acec9bf0cb0'}
for name,digest in expected.items(): assert hashlib.sha256((contract/name).read_bytes()).hexdigest() == digest,name
inputs=json.loads((contract/'source-inputs.json').read_text())['files']
assert len(inputs)==16
for folder in ['home-core/src/test/resources','tv/src/androidTest/assets']:
 assert (root/folder/'catalog-v2.json').read_bytes() == (contract/'home-catalog-response-v2.example.json').read_bytes()
 assert hashlib.sha256((root/folder/'catalog-video.mp4').read_bytes()).hexdigest() == '5ab7d5d27cc6b3f557068ce21cc07e332939ae92f8240233b5eb087c1012afe8'
assert not (root/'tv/src/main/assets').exists()
assert 'photohouseTvCatalogVersion' in (root/'tv/build.gradle.kts').read_text()
print('PASS v2 pin, 16-input manifest, contract/example and test-only video; explicit version selection')

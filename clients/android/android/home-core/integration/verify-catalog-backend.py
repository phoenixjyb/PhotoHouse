#!/usr/bin/env python3
"""Replay exact v2 backend Git blobs in disposable synthetic files, never a listener."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--backend',type=Path,required=True);p.add_argument('--python',type=Path,required=True)
a=p.parse_args();here=Path(__file__).resolve().parent;contract=here.parent/'contract-v2'
subprocess.run(['python3',str(here.parents[1]/'verify-catalog-contract.py')],check=True)
pin=(contract/'backend-pin.txt').read_text().strip();inputs=json.loads((contract/'source-inputs.json').read_text())['files']
assert hashlib.sha256((here/'catalog-smoke.py').read_bytes()).hexdigest()=='8bbb08443c8072d76814a54ec85196b2f9bf68ffdc34957a4e66394f363d616e'
with tempfile.TemporaryDirectory(prefix='photohouse-catalog-asgi-') as temporary:
 root=Path(temporary).resolve()
 for item in inputs:
  data=subprocess.check_output(['git','show',pin+':'+item['path']],cwd=a.backend)
  assert len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],item['path']
  target=root/item['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 for name in ['home-catalog-contract-v2.json','home-catalog-response-v2.example.json']:
  assert (contract/name).read_bytes()==(root/'docs/security'/name).read_bytes()
 result=subprocess.check_output([str(a.python),'-I','-B',str(here/'catalog-smoke.py'),'--source-root',str(root)],text=True)
 receipt=json.loads(result);receipt.update(implementation_commit=pin,source_hashes_verified=len(inputs),evidence_tier='actual in-process backend; separate from Kotlin mock TLS and physical device')
 print(json.dumps(receipt,indent=2))

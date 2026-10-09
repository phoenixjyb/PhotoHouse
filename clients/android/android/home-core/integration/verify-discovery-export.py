#!/usr/bin/env python3
"""Replay pinned synthetic exporter plus frozen serving code; compare JVM fixture bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--backend', type=Path, required=True)
parser.add_argument('--python', type=Path, required=True)
parser.add_argument('--update-fixture', action='store_true', help='Explicitly regenerate the test-only fixture after reviewing the exporter pin')
args = parser.parse_args()
here = Path(__file__).resolve().parent
pin = json.loads((here/'discovery-export-pin.json').read_text())
contract = here.parent/'discovery-contract'
assert pin['serving_commit'] == (contract/'backend-pin.txt').read_text().strip()
serving = json.loads((contract/'source-inputs.json').read_text())['files']
fixture = here.parent/'src/test/resources/discovery-export-generated.json'
with tempfile.TemporaryDirectory(prefix='android-export-source-') as temporary:
    root = Path(temporary).resolve()
    for commit, files in ((pin['serving_commit'], serving), (pin['exporter_commit'], pin['files'])):
        for item in files:
            path = Path(item['path'])
            assert not path.is_absolute() and '..' not in path.parts
            raw = subprocess.check_output(['git', 'show', commit+':'+item['path']], cwd=args.backend)
            assert len(raw) == item['bytes'] and hashlib.sha256(raw).hexdigest() == item['sha256'], item['path']
            target = root/path
            assert not target.exists()
            target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
    raw = subprocess.check_output([str(args.python), '-I', '-B', str(here/'probe-discovery-export.py'), '--source-root', str(root)])
    result = json.loads(raw)
    assert result['synthetic_only'] and result['input_unchanged'] and not result['final_enabled']
    if args.update_fixture:
        fixture.write_bytes(raw)
    assert raw == fixture.read_bytes(), 'Exporter responses differ from the reviewed JVM fixture'
    print(json.dumps({'status': 'PASS_SYNTHETIC_EXPORT_TO_ANDROID_FIXTURE', 'exporter_commit': pin['exporter_commit'],
        'serving_commit': pin['serving_commit'], 'source_hashes_verified': len(serving)+len(pin['files']),
        'fixture_sha256': hashlib.sha256(raw).hexdigest(), 'response_count': len(result['responses']),
        'final_enabled': False, 'real_data_accessed': False}, indent=2))

#!/usr/bin/env python3
"""Verify the separate opt-in phone contract, optionally replay its exact Git inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parent / "phone-discovery-contract"
manifest = json.loads((root / "manifest.json").read_text())
expected = "af8e0c8cf749f6e963dd8b196dce9aa842240387"
assert manifest["backend_commit"] == expected
assert manifest["status"] == "REVIEWED_FOR_OPT_IN_SYNTHETIC_ANDROID_INTEGRATION"
assert set(manifest["files"]) == {"schema.json", "examples.json", "CONTRACT.md", "backend-inputs.json"}
for name, digest in manifest["files"].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
inputs = json.loads((root / "backend-inputs.json").read_text())
assert inputs["source_commit"] == expected and len(inputs["files"]) == 33
paths = [entry["path"] for entry in inputs["files"]]
assert len(set(paths)) == len(paths)
for name, source in {
    "schema.json": "docs/security/phone-discovery-http-candidate-schema.json",
    "examples.json": "docs/security/phone-discovery-http-candidate-examples.json",
    "CONTRACT.md": "docs/security/PHONE_DISCOVERY_HTTP_CANDIDATE.md",
}.items():
    entry = next(e for e in inputs["files"] if e["path"] == source)
    assert entry["sha256"] == manifest["files"][name]
    assert entry["bytes"] == (root / name).stat().st_size
examples = json.loads((root / "examples.json").read_text())
assert examples["synthetic_only"] is True and len(examples["examples"]) == 14
assert sum(e["status"] == 200 for e in examples["examples"]) == 7
parser = argparse.ArgumentParser()
parser.add_argument("--backend-root", type=Path)
args = parser.parse_args()
if args.backend_root:
    for entry in inputs["files"]:
        path = Path(entry["path"])
        assert not path.is_absolute() and ".." not in path.parts
        content = subprocess.check_output(["git", "show", f"{expected}:{entry['path']}"], cwd=args.backend_root)
        assert len(content) == entry["bytes"] and hashlib.sha256(content).hexdigest() == entry["sha256"], entry["path"]
print("PASS separate opt-in phone discovery pin: 4 files, 14 producer examples" + (", 33 exact backend Git inputs" if args.backend_root else ""))

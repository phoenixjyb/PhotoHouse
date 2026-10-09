#!/usr/bin/env python3
"""Verify the Android snapshot and, optionally, the pinned backend pack."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ANDROID = Path(__file__).resolve().parent
SNAPSHOT = ANDROID / "protected-native-contract"
MANIFEST_SHA256 = "a38f6fdcee38c857bcb7e3364d971c9f3acb807cecda4789dc67b5691eaf8b71"
BACKEND_PACK = Path("docs/contracts/protected-native-v2")
BACKEND_COMMIT = "f09be487e38102c1718533d95783554aad26a741"
SOURCE_COMMIT = "808abfe134273d4fa208c14199422dd81ea45d38"
SNAPSHOT_PAYLOADS = {
    "CONTRACT.md": "d5e5d1445cae0e7c82dbffc2a9614d6820f00ddc430448e001687a6ede3fc993",
    "UPLOAD_NEXT.md": "2ea8ce05cd9c2336c725793812eac10f5b7a2315bdf72c155959adf7b9a9d1bd",
    "VALIDATION.md": "dcd25c36c86cfe3a5feac79384ae01f59fe47531141c96274954f7219bf6102c",
    "cases.json": "13f4c6a9af089cfb461409bfb97333cdc8a760b71c5afa5c9509bbfec3af33cd"
}

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_snapshot() -> dict:
    manifest_path = SNAPSHOT / "manifest.json"
    if digest(manifest_path) != MANIFEST_SHA256:
        raise ValueError("snapshot manifest digest mismatch")
    manifest = json.loads(manifest_path.read_text())
    if manifest["backend_source_commit"] != SOURCE_COMMIT:
        raise ValueError("unexpected backend source commit")
    if manifest["case_count"] != 89:
        raise ValueError("unexpected case metadata")
    if manifest["client_profile_defaults"] != {
        "protected_native_v2": False,
        "protected_photo_display": False,
        "protected_story_read": False,
    }:
        raise ValueError("profile defaults are not explicitly off")
    for name, expected in SNAPSHOT_PAYLOADS.items():
        actual = digest(SNAPSHOT / name)
        if actual != expected or manifest["payload_sha256"].get(str(BACKEND_PACK / name)) != expected:
            raise ValueError(f"snapshot payload mismatch: {name}")
    if digest(SNAPSHOT / "PREPARED_MEDIA.md") != manifest["source_sha256"]["docs/security/PROTECTED_PREPARED_MEDIA.md"]:
        raise ValueError("prepared playback contract reference changed")
    cases = json.loads((SNAPSHOT / "cases.json").read_text())
    if cases["contract_version"] != manifest["contract_version"] or cases["synthetic_only"] is not True:
        raise ValueError("case metadata mismatch")
    if len(cases["cases"]) != manifest["case_count"]:
        raise ValueError("case count mismatch")
    return manifest


def verify_backend(root: Path, snapshot_manifest: dict) -> None:
    root = root.resolve()
    if subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip() != BACKEND_COMMIT:
        raise ValueError("backend checkout is not the pinned pack commit")
    manifest_path = root / BACKEND_PACK / "manifest.json"
    if digest(manifest_path) != MANIFEST_SHA256:
        raise ValueError("backend manifest digest mismatch")
    backend = json.loads(manifest_path.read_text())
    if backend != snapshot_manifest:
        raise ValueError("backend manifest differs from Android snapshot")
    for group in ("source_sha256", "payload_sha256"):
        for name, expected in backend[group].items():
            path = root / name
            if not path.is_file() or digest(path) != expected:
                raise ValueError(f"backend {group} mismatch: {name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend-root", type=Path)
    args = parser.parse_args()
    manifest = verify_snapshot()
    if args.backend_root:
        verify_backend(args.backend_root, manifest)
    print(f"PASS {manifest['contract_version']}: {manifest['case_count']} cases; snapshot verified")


if __name__ == "__main__":
    main()

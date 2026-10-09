#!/usr/bin/env python3
"""Verify the initial curated export against its recorded source and transforms.

This is an import acceptance check. Normal feature development does not need to
rewrite or satisfy the historical baseline manifest after changing source files.
"""
from pathlib import Path, PurePosixPath
import hashlib
import json
import stat

ROOT = Path(__file__).resolve().parents[1]


def checked_path(relative):
    value = PurePosixPath(relative)
    if value.is_absolute() or ".." in value.parts or "\\" in relative:
        raise ValueError("unsafe manifest path")
    path = ROOT.joinpath(*value.parts)
    for ancestor in (path, *path.parents):
        if ancestor == ROOT.parent:
            break
        if ancestor.is_symlink():
            raise ValueError("symlink in source baseline")
    if not stat.S_ISREG(path.stat().st_mode):
        raise ValueError("source baseline is not a regular file")
    return path


def digest(relative):
    return hashlib.sha256(checked_path(relative).read_bytes()).hexdigest()


def verify():
    manifest = json.loads((ROOT / "docs/source-export-manifest.json").read_text())
    changes = []
    for ledger in ("generic-brand-transform.json", "documentation-transform.json"):
        changes.extend(json.loads((ROOT / "docs" / ledger).read_text())["transformations"])
    transforms = {item["path"]: item for item in changes}
    if len(transforms) != len(changes):
        raise ValueError("duplicate transform")
    prefixes = {"server": "server", "android": "clients/android"}
    baseline = {}
    for item in manifest["exported_files"]:
        path = prefixes[item["repo"]] + "/" + item["source_path"]
        if path in baseline:
            raise ValueError("duplicate source file")
        baseline[path] = item
        change = transforms.get(path)
        if change:
            if change["operation"] != "replace" or change["before_sha256"] != item["sha256"]:
                raise ValueError("transform source mismatch")
            expected = change["after_sha256"]
        else:
            expected = item["sha256"]
        if digest(path) != expected:
            raise ValueError("source baseline content differs: " + path)
    for path, change in transforms.items():
        if change["operation"] == "add":
            if path in baseline or digest(path) != change["sha256"]:
                raise ValueError("added asset mismatch")
        elif path not in baseline:
            raise ValueError("transform missing source")
    if manifest["historical_git_imported"]:
        raise ValueError("unexpected historical Git import")
    return {"source_files": len(baseline), "deliberate_transforms": len(changes),
            "historical_git_imported": False, "baseline_verified": True}


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))

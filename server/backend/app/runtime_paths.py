"""Portable default locations for local PhotoHouse runtime data.

These helpers only compute paths; callers remain responsible for creating them.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


def data_root(environ: Mapping[str, str] | None = None, cwd: Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get("VLM_DATA_ROOT")
    if configured:
        return Path(configured)
    return (Path.cwd() if cwd is None else Path(cwd)) / ".runtime" / "photohouse"


def originals_path(environ: Mapping[str, str] | None = None, cwd: Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get("ORIGINALS_PATH")
    return Path(configured) if configured else data_root(env, cwd) / "originals"


def derived_path(environ: Mapping[str, str] | None = None, cwd: Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get("DERIVED_PATH")
    return Path(configured) if configured else data_root(env, cwd) / "derived"


def temporary_path(environ: Mapping[str, str] | None = None, cwd: Path | None = None) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get("VLM_TMP_DIR")
    return Path(configured) if configured else data_root(env, cwd) / "tmp"

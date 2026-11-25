"""Shared target-path selection and native Windows storage checks."""
from __future__ import annotations

import os
from pathlib import Path


def selected_target(crate: Path, argument: str | Path | None = None,
                    environ: dict[str, str] | None = None) -> Path:
    """Choose CLI target, then CARGO_TARGET_DIR, then the legacy crate target."""
    values = os.environ if environ is None else environ
    chosen = argument if argument is not None else values.get("CARGO_TARGET_DIR")
    if chosen is None or str(chosen) == "":
        return crate / "target"
    path = Path(chosen).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path


def _storage_helpers(root: Path):
    backend = root / "server" / "backend"
    if str(backend) not in os.sys.path:
        os.sys.path.insert(0, str(backend))
    from app import work_storage
    from app.access import private_storage
    return work_storage, private_storage


def validate_windows_paths(root: Path, target: Path,
                           environ: dict[str, str] | None = None) -> None:
    """Require all build storage on D: and inspect existing paths before use."""
    if os.name != "nt":
        return
    values = os.environ if environ is None else environ
    storage, privacy = _storage_helpers(root)
    paths = {
        "source": root,
        "target": target,
        "Cargo cache": Path(values.get("CARGO_HOME", "C:/")),
        "TEMP": Path(values.get("TEMP", "C:/")),
        "TMP": Path(values.get("TMP", "C:/")),
    }
    for name, path in paths.items():
        if path.drive.upper() != "D:":
            raise SystemExit(f"{name} must be explicitly located on D:")
        try:
            storage.direct(path)
            # A D: spelling alone does not prove a fixed, non-system volume.
            storage.volume(path)
            existing = path
            while not existing.exists():
                if existing == existing.parent:
                    raise ValueError
                existing = existing.parent
            if name != "source":
                privacy.require_private_directory(existing)
        except (OSError, ValueError):
            raise SystemExit(f"{name} path is not direct private D: storage") from None

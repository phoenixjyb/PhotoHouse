from pathlib import Path

import pytest

from app import caption_service, caption_subprocess, image_tag_service
from app.config import (
    _default_data_root,
    _default_derived_path,
    _default_originals_path,
    get_settings,
)
from app.runtime_paths import data_root, derived_path, originals_path, temporary_path


def test_defaults_are_local_and_consistent_without_environment(monkeypatch, tmp_path):
    for name in ("VLM_DATA_ROOT", "ORIGINALS_PATH", "DERIVED_PATH", "VLM_TMP_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)

    expected_root = tmp_path / ".runtime" / "photohouse"
    assert data_root() == expected_root
    assert originals_path() == expected_root / "originals"
    assert derived_path() == expected_root / "derived"
    assert temporary_path() == expected_root / "tmp"
    assert Path(_default_data_root()) == expected_root
    assert Path(_default_originals_path()) == expected_root / "originals"
    assert Path(_default_derived_path()) == expected_root / "derived"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_settings.cache_clear()
    settings = get_settings()
    assert Path(settings.originals_path) == expected_root / "originals"
    assert Path(settings.derived_path) == expected_root / "derived"
    assert ".runtime/photohouse/databases/metadata.sqlite" in settings.database_url
    get_settings.cache_clear()
    assert not expected_root.exists()


@pytest.mark.parametrize("name,expected", [
    ("VLM_DATA_ROOT", "data"),
    ("ORIGINALS_PATH", "originals-in"),
    ("DERIVED_PATH", "derived-out"),
    ("VLM_TMP_DIR", "scratch"),
])
def test_each_explicit_path_override_is_preserved(monkeypatch, tmp_path, name, expected):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VLM_DATA_ROOT", raising=False)
    monkeypatch.delenv("ORIGINALS_PATH", raising=False)
    monkeypatch.delenv("DERIVED_PATH", raising=False)
    monkeypatch.delenv("VLM_TMP_DIR", raising=False)
    monkeypatch.setenv(name, expected)

    paths = {
        "VLM_DATA_ROOT": data_root(),
        "ORIGINALS_PATH": originals_path(),
        "DERIVED_PATH": derived_path(),
        "VLM_TMP_DIR": temporary_path(),
    }
    assert paths[name] == Path(expected)
    if name == "VLM_DATA_ROOT":
        assert Path(_default_data_root()) == Path(expected)
        assert Path(_default_originals_path()) == Path(expected) / "originals"
        assert Path(_default_derived_path()) == Path(expected) / "derived"
    elif name == "ORIGINALS_PATH":
        assert Path(_default_originals_path()) == Path(expected)
    elif name == "DERIVED_PATH":
        assert Path(_default_derived_path()) == Path(expected)


def test_temp_artifact_callers_share_configured_directory(monkeypatch, tmp_path):
    target = tmp_path / "configured-temp"
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("VLM_DATA_ROOT", raising=False)
    monkeypatch.setenv("VLM_TMP_DIR", str(target))

    assert Path(caption_service._caption_tmp_dir()) == target
    assert Path(caption_subprocess._caption_tmp_dir()) == target
    assert Path(image_tag_service._tmp_dir()) == target
    assert target.is_dir()


def test_temp_artifact_callers_fall_back_when_directory_cannot_be_created(monkeypatch, tmp_path):
    fallback = tmp_path / "system-temp"
    monkeypatch.setattr(caption_service, "temporary_path", lambda: tmp_path / "blocked")
    monkeypatch.setattr(caption_subprocess, "temporary_path", lambda: tmp_path / "blocked")
    monkeypatch.setattr(image_tag_service, "temporary_path", lambda: tmp_path / "blocked")
    monkeypatch.setattr(caption_service.tempfile, "gettempdir", lambda: str(fallback))
    monkeypatch.setattr(caption_subprocess.tempfile, "gettempdir", lambda: str(fallback))
    monkeypatch.setattr(image_tag_service.tempfile, "gettempdir", lambda: str(fallback))

    def denied(*args, **kwargs):
        raise PermissionError("test denied")

    monkeypatch.setattr(Path, "mkdir", denied)
    assert caption_service._caption_tmp_dir() == str(fallback)
    assert caption_subprocess._caption_tmp_dir() == str(fallback)
    assert image_tag_service._tmp_dir() == str(fallback)

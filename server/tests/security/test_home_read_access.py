import hashlib
import json
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import qualify_home_read_access as qualifier


class FakeAdapter:
    def __init__(self, pid, sid, *, allow=True, alive=True, fail=False):
        assert pid == 123
        assert sid == "S-1-5-80-123"
        self.allow, self.is_alive, self.fail = allow, alive, fail
        self.checked = []
        self.closed = False

    def alive(self):
        return self.is_alive

    def read_allowed(self, path):
        self.checked.append(path)
        if self.fail:
            raise RuntimeError("private native detail")
        return self.allow

    def close(self):
        self.closed = True


def make_index(tmp_path):
    root = tmp_path / "originals"
    root.mkdir(parents=True)
    source = root / "photo.jpg"
    source.write_bytes(b"fixture bytes")
    st = source.stat()
    identity = [st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns]
    doc = {"version": 1, "catalog_sha256": "a" * 64, "assets": [{
        "id": 9, "path": str(source), "identity": identity, "kind": "photo",
        "mime": "image/jpeg", "width": 1, "height": 1,
        "duration_ms": None, "audio_codec": None,
    }]}
    index = tmp_path / "sources.json"
    raw = json.dumps(doc, separators=(",", ":")).encode()
    index.write_bytes(raw)
    return index, hashlib.sha256(raw).hexdigest(), root, source


def run(index, pin, root, adapter):
    return qualifier.qualify(index, pin, 123, "S-1-5-80-123", (root,), 5,
                              adapter_factory=adapter)


def test_pinned_selected_source_is_checked_without_mutation(tmp_path):
    index, pin, root, source = make_index(tmp_path)
    before = (source.stat().st_mode, source.stat().st_mtime_ns, source.read_bytes())
    made = []

    def factory(*args):
        value = FakeAdapter(*args)
        made.append(value)
        return value

    result = run(index, pin, root, factory)
    assert result["result"] == "pass"
    assert result["allowed"] == 1 and result["failed_asset_ids"] == []
    assert made[0].checked == [source] and made[0].closed
    assert (source.stat().st_mode, source.stat().st_mtime_ns, source.read_bytes()) == before


@pytest.mark.parametrize("kwargs,expected", [
    ({"allow": False}, (1, 0)),
    ({"alive": False}, (0, 1)),
    ({"fail": True}, (0, 1)),
])
def test_denied_dead_or_native_failure_fails_closed(tmp_path, kwargs, expected):
    index, pin, root, _ = make_index(tmp_path)
    made = []

    def factory(*args):
        value = FakeAdapter(*args, **kwargs)
        made.append(value)
        return value

    result = run(index, pin, root, factory)
    assert result["result"] == "failed"
    assert (result["denied"], result["unverifiable"]) == expected
    assert result["failed_asset_ids"] == [9]
    assert made[0].closed


def test_wrong_sid_fails_before_file_check(tmp_path):
    index, pin, root, _ = make_index(tmp_path)

    def wrong_sid(pid, sid):
        raise RuntimeError("sid_mismatch")

    with pytest.raises(RuntimeError, match="sid_mismatch"):
        run(index, pin, root, wrong_sid)


def test_stale_identity_and_reparse_source_fail_before_adapter(tmp_path):
    index, pin, root, source = make_index(tmp_path)
    source.write_bytes(b"changed source size")
    with pytest.raises(ValueError, match="stale_identity"):
        run(index, pin, root, lambda *_: pytest.fail("adapter must not open"))

    index, pin, root, source = make_index(tmp_path / "second")
    link = root / "link.jpg"
    try:
        link.symlink_to(source)
    except OSError:
        pytest.skip("symlink creation unavailable")
    doc = json.loads(index.read_text())
    doc["assets"][0]["path"] = str(link)
    doc["assets"][0]["identity"] = [link.lstat().st_dev, link.lstat().st_ino, link.lstat().st_size, link.lstat().st_mtime_ns]
    raw = json.dumps(doc, separators=(",", ":")).encode()
    index.write_bytes(raw)
    with pytest.raises(ValueError, match="reparse_point"):
        run(index, hashlib.sha256(raw).hexdigest(), root, lambda *_: pytest.fail("adapter must not open"))


def test_pin_mismatch_and_duplicate_ids_are_rejected(tmp_path):
    index, pin, root, _ = make_index(tmp_path)
    with pytest.raises(ValueError, match="index_pin_failed"):
        run(index, "0" * 64, root, lambda *_: pytest.fail("adapter must not open"))
    doc = json.loads(index.read_text())
    doc["assets"].append(dict(doc["assets"][0]))
    raw = json.dumps(doc, separators=(",", ":")).encode()
    index.write_bytes(raw)
    with pytest.raises(ValueError, match="duplicate_or_invalid_id"):
        run(index, hashlib.sha256(raw).hexdigest(), root, lambda *_: pytest.fail("adapter must not open"))


def test_index_reparse_and_parent_components_are_rejected(tmp_path):
    index, pin, root, _ = make_index(tmp_path)
    link = tmp_path / "index-link.json"
    try:
        link.symlink_to(index)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError, match="index_not_regular"):
        run(link, pin, root, lambda *_: pytest.fail("adapter must not open"))
    with pytest.raises(ValueError, match="parent_component_refused"):
        run(index, pin, root / ".." / "originals", lambda *_: pytest.fail("adapter must not open"))


def test_duplicate_paths_use_normalized_windows_case(monkeypatch, tmp_path):
    index, pin, root, source = make_index(tmp_path)
    doc = json.loads(index.read_text())
    second = dict(doc["assets"][0], id=10, path=str(source.parent / "." / source.name))
    doc["assets"].append(second)
    raw = json.dumps(doc, separators=(",", ":")).encode()
    index.write_bytes(raw)
    monkeypatch.setattr(qualifier, "_path_key", lambda path: str(path).replace("\\", "/").lower().replace("/./", "/"))
    with pytest.raises(ValueError, match="duplicate_or_invalid_path"):
        run(index, hashlib.sha256(raw).hexdigest(), root, lambda *_: pytest.fail("adapter must not open"))


def test_native_close_accepts_integer_process_handle_and_handle_objects():
    adapter = object.__new__(qualifier.WindowsAccessAdapter)
    adapter.w = wintypes
    seen = []

    class Kernel:
        @staticmethod
        def CloseHandle(handle):
            seen.append(handle.value)
            return 1

    adapter.k = Kernel()
    adapter.check_token = wintypes.HANDLE(323)
    adapter.token = wintypes.HANDLE(322)
    adapter.process = 321  # ctypes HANDLE restype may expose this as a native int
    adapter.close()
    assert seen == [323, 322, 321]
    assert adapter.process is None and adapter.token is None and adapter.check_token is None


def test_native_token_requests_query_and_duplicate(monkeypatch):
    # Exercise the constructor with fake Win32 libraries: no Windows API is called.
    import ctypes
    calls = []

    class Proc:
        def __init__(self, fn): self.fn = fn
        def __call__(self, *args): return self.fn(*args)

    class Library:
        def __init__(self, name):
            self.OpenProcess = Proc(lambda *_: 321)
            self.CloseHandle = Proc(lambda handle: calls.append(handle.value) or 1)
            self.OpenProcessToken = Proc(lambda proc, access, out: calls.append(("token_access", access)) or 0)
            self.DuplicateToken = Proc(lambda *_: 0)
            for name in ("QueryFullProcessImageNameW", "GetProcessTimes", "GetTokenInformation",
                         "ConvertSidToStringSidW", "GetFileSecurityW", "AccessCheck", "WaitForSingleObject", "LocalFree"):
                setattr(self, name, Proc(lambda *_: 0))

    monkeypatch.setattr(qualifier.os, "name", "nt")
    monkeypatch.setattr(ctypes, "WinDLL", lambda name, use_last_error=True: Library(name), raising=False)
    with pytest.raises(RuntimeError, match="token_open_failed"):
        qualifier.WindowsAccessAdapter(123, "S-1-5-80-123")
    assert ("token_access", 0x000A) in calls
    assert 321 in calls  # partial-construction cleanup closed process handle


def test_deadline_covers_index_entry_walk(monkeypatch, tmp_path):
    index, pin, root, _ = make_index(tmp_path)
    ticks = iter([0.0, 2.0, 2.0])
    monkeypatch.setattr(qualifier.time, "monotonic", lambda: next(ticks, 2.0))
    with pytest.raises(ValueError, match="timeout"):
        qualifier.qualify(index, pin, 123, "S-1-5-80-123", (root,), 1,
                          adapter_factory=lambda *_: pytest.fail("adapter must not open"))


def empty_index(index):
    doc = json.loads(index.read_text())
    doc["assets"] = []
    raw = json.dumps(doc, separators=(",", ":")).encode()
    index.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_empty_selection_fails_if_process_dies_at_final_gate(tmp_path):
    index, _, root, _ = make_index(tmp_path)
    pin = empty_index(index)

    class DiesAtEnd(FakeAdapter):
        def __init__(self, *args):
            super().__init__(*args)
            self.calls = 0

        def alive(self):
            self.calls += 1
            return self.calls == 1

    adapter = DiesAtEnd(123, "S-1-5-80-123")
    result = run(index, pin, root, lambda *_: adapter)
    assert result["selected"] == 0 and result["failed_asset_ids"] == []
    assert result["result"] == "failed"
    assert result["failed_reason"] == "process_unavailable"


def test_empty_selection_fails_if_qualification_deadline_expires(monkeypatch, tmp_path):
    index, _, root, _ = make_index(tmp_path)
    pin = empty_index(index)
    ticks = iter([0.0, 0.0, 0.0, 2.0])
    monkeypatch.setattr(qualifier.time, "monotonic", lambda: next(ticks, 2.0))
    result = qualifier.qualify(index, pin, 123, "S-1-5-80-123", (root,), 1,
        adapter_factory=lambda *args: FakeAdapter(*args))
    assert result["selected"] == 0 and result["failed_asset_ids"] == []
    assert result["result"] == "failed" and result["failed_reason"] == "timeout"

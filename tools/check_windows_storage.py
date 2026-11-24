"""Bounded, generated Windows source checks for the PhotoHouse workstation."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import uuid

if __package__:
    from . import check_receipt
else:
    import check_receipt


CHECKOUT = Path(__file__).resolve().parents[1]
WORK = Path("D:/PhotoHouseWork")
TESTS = WORK / "tests"
RUNS = TESTS / "check-runs-v1"
META = TESTS / "check-receipts-v1"
BOOTSTRAP = META / "bootstrap"
PROFILES = ("api", "memory", "windows-cpu", "web")
DB_BYTES = 256 * 1024**2
RUN_BYTES = 1024**3
HOT_BYTES = 4 * RUN_BYTES
MAX_RUNS = 16
KEEP_SUCCESSES = 3
MEMORY_BYTES = 4 * 1024**3
PROCESS_LIMIT = 16
JOB_FLAGS = 0x2208  # active process count, total Job memory, kill on close
MAX_ENTRIES = 60_000
RECORD_LIMIT = 64 * 1024
SCHEMA = "photohouse.generated-check.v1"


def enabled():
    if os.name != "nt":
        return False
    if os.path.lexists(WORK) or os.environ.get("PHOTOHOUSE_REQUIRE_D_TEST_STORAGE") == "1":
        return True
    return (os.environ.get("GITHUB_ACTIONS") != "true"
            and os.environ.get("PHOTOHOUSE_PORTABLE_WINDOWS_CHECKS") != "1")


def _components():
    for directory in (CHECKOUT, CHECKOUT / "server" / "backend"):
        if str(directory) not in sys.path:
            sys.path.insert(0, str(directory))
    from app import work_storage
    from app.access import private_storage
    from server.scripts import bounded_windows_job

    return work_storage, private_storage, bounded_windows_job


def require_d_receipt(path, expected=None):
    path = Path(path)
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        storage, privacy, _ = _components()
        storage.direct(path)
        if path.drive.upper() != "D:":
            raise ValueError
        storage.volume(path)
        privacy.require_private_directory(path.parent)
        identity = _identity(_entry(path.parent))
        if expected is not None and expected != identity:
            raise ValueError
        return identity
    except (OSError, ValueError):
        raise check_receipt.ReceiptError("workstation_receipt_requires_direct_d") from None


def _layout(storage, privacy):
    if os.name != "nt":
        raise ValueError("Windows lean checks require native storage admission")
    storage.direct(WORK)
    if storage.volume(WORK)[1] != Path("D:/"):
        raise ValueError("workstation lean checks require the local D volume")
    privacy.require_private_directory(WORK)
    for path in (TESTS, RUNS, META, BOOTSTRAP):
        storage.direct(path)
        if not path.exists():
            try:
                storage.private_mkdir(path)
            except FileExistsError:
                pass
        privacy.require_private_directory(path)


@contextlib.contextmanager
def _lock(storage, privacy):
    import msvcrt

    path = storage.direct(META / "launcher.lock")
    with path.open("a+b") as stream:
        privacy.require_private_file(path)
        if stream.seek(0, 2) == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise ValueError("another generated Windows check owns the launcher") from None
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _read(path, storage, privacy):
    storage.direct(path)
    privacy.require_private_file(path)
    with path.open("rb") as stream:
        data = stream.read(RECORD_LIMIT + 1)
    if len(data) > RECORD_LIMIT:
        raise ValueError("test record exceeds its bound")
    record = json.loads(data)
    if type(record) is not dict:
        raise ValueError("invalid test record")
    return record


def _write(path, record, storage, privacy):
    if len(_json_bytes(record)) + 1 > RECORD_LIMIT:
        raise ValueError("test record exceeds its bound")
    storage.direct(path)
    check_receipt.write_receipt(path, record)
    if _read(path, storage, privacy) != record:
        raise ValueError("test record readback mismatch")


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_birthtime_ns)


def _entry(path):
    info = path.lstat()
    if (info.st_file_attributes & 0x400 or not info.st_ino
            or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode))):
        raise ValueError("non-direct object in test storage")
    return info


def _measure(root, *, payload=False, moving=False, inventory=False):
    """Bound a direct tree walk; only successful cleanup needs a file manifest."""
    if not os.path.lexists(root) and moving:
        return 0, {}
    device = _entry(root).st_dev
    directories = [root]
    rows = {}
    sizes = {}
    total = entries = 0
    while directories:
        directory = directories.pop()
        try:
            info = _entry(directory)
            if info.st_dev != device or not stat.S_ISDIR(info.st_mode):
                raise ValueError("test directory changed")
            with os.scandir(directory) as children:
                for child in children:
                    entries += 1
                    if entries > MAX_ENTRIES:
                        raise ValueError("test storage inventory bound reached")
                    path = Path(child.path)
                    try:
                        if moving and path.lstat().st_file_attributes & 0x400:
                            continue  # Some generated checks create transient alias fixtures.
                        info = _entry(path)
                    except FileNotFoundError:
                        if moving:
                            continue
                        raise
                    if info.st_dev != device:
                        raise ValueError("test storage crossed its volume")
                    is_dir = stat.S_ISDIR(info.st_mode)
                    if inventory:
                        rows[path.relative_to(root).as_posix()] = (
                            "dir" if is_dir else "file", _identity(info), info.st_size,
                            info.st_mtime_ns,
                        )
                    if is_dir:
                        directories.append(path)
                        continue
                    if payload and not moving and info.st_nlink != 1:
                        raise ValueError("linked file in owned test payload")
                    total += info.st_size
                    if payload:
                        base = str(path)
                        for suffix in ("-journal", "-wal", "-shm"):
                            if base.casefold().endswith(suffix):
                                base = base[:-len(suffix)]
                                break
                        key = base.casefold()
                        sizes[key] = sizes.get(key, 0) + info.st_size
                        if sizes[key] > DB_BYTES or total > RUN_BYTES:
                            raise ValueError("generated check exceeded its storage budget")
        except FileNotFoundError:
            if not moving:
                raise
    return total, rows


def _environment(base, root):
    env = {name.upper(): value for name, value in base.items()}
    for key in ("TEMP", "TMP", "TMPDIR", "SQLITE_TMPDIR", "HOME", "USERPROFILE"):
        env[key] = str(root)
    for key, leaf in {
        "APPDATA": "roaming", "LOCALAPPDATA": "local", "XDG_CACHE_HOME": "xdg",
        "PIP_CACHE_DIR": "pip", "UV_CACHE_DIR": "uv", "HF_HOME": "hf",
        "TORCH_HOME": "torch", "MPLCONFIGDIR": "mpl", "NUMBA_CACHE_DIR": "numba",
    }.items():
        env[key] = str(root / leaf)
    env.update(PHOTOHOUSE_NO_DOTENV="1", PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", PIP_NO_INDEX="1", UV_OFFLINE="1",
               PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1")
    return env


def _started(run_id, profile):
    return {"schema": SCHEMA, "id": run_id, "profile": profile, "mode": "generated",
            "started_ns": time.time_ns()}


def _run_id(name):
    try:
        return type(name) is str and str(uuid.UUID(name)) == name
    except ValueError:
        return False


def _closed_success(run_id, storage, privacy):
    start = _read(META / (run_id + ".started.json"), storage, privacy)
    if (start.get("schema") != SCHEMA or start.get("id") != run_id or start.get("mode") != "generated"
            or start.get("profile") not in PROFILES or type(start.get("started_ns")) is not int):
        raise ValueError("invalid check registration")
    path = META / (run_id + ".closed.json")
    if not os.path.lexists(path):
        return None
    row = _read(path, storage, privacy)
    if (row.get("start") != start or type(row.get("exit_code")) is not int or row["exit_code"] != 0
            or row.get("native_job_closed") is not True or row.get("admission_closed") is not True
            or type(row.get("finished_ns")) is not int
            or type(row.get("payload_identity")) is not list
            or type(row.get("payload_bytes")) is not int or not 0 < row["payload_bytes"] <= RUN_BYTES
            or type(row.get("inventory_sha256")) is not str or not _run_id(row.get("admission"))
            or type(row.get("retention_eligible")) is not bool):
        raise ValueError("invalid successful check closure")
    return row if row["retention_eligible"] else None


def _nested_admissions(run, storage, privacy):
    root = storage.direct(run / "admitted-temporary")
    privacy.require_private_directory(root)
    records = {}
    preserved_residue = False
    for temporary in root.iterdir():
        if not _run_id(temporary.name) or len(records) >= MAX_ENTRIES:
            raise ValueError("unregistered admitted test temporary directory")
        privacy.require_private_directory(storage.direct(temporary))
        lease = _read(WORK / "admission" / temporary.name / "receipt.json", storage, privacy)
        state = lease.get("state")
        outputs = lease.get("outputs")
        if (lease.get("operation_id") != temporary.name or state not in ("closed", "failed_uncertain")
                or not isinstance(outputs, list) or not outputs
                or any(not Path(path).is_relative_to(run) for path in outputs)):
            raise ValueError("nested test admission does not match the owned run")
        if state == "failed_uncertain" and any(temporary.iterdir()):
            preserved_residue = True
        records[temporary.name] = lease
    return hashlib.sha256(_json_bytes(records)).hexdigest(), preserved_residue


def _retire(run, success, storage, privacy):
    """Revalidate ownership and the exact closed inventory before any unlink."""
    storage.direct(run)
    privacy.require_private_directory(run)
    run_identity = _identity(_entry(run))
    used, rows = _measure(run, payload=True, inventory=True)
    lease = _read(WORK / "admission" / success["admission"] / "receipt.json", storage, privacy)
    nested_sha, residue = _nested_admissions(run, storage, privacy)
    if (list(run_identity) != success["payload_identity"] or used != success["payload_bytes"]
            or hashlib.sha256(_json_bytes(rows)).hexdigest() != success["inventory_sha256"]
            or hashlib.sha256(_json_bytes(lease)).hexdigest() != success["admission_sha256"]
            or residue or nested_sha != success["nested_admissions_sha256"]):
        raise ValueError("closed test payload changed; preserve it")
    started = META / (run.name + ".retire-intent.json")
    _write(started, {"id": run.name, "success": success, "entries": len(rows)}, storage, privacy)
    for rel in sorted(rows, key=lambda p: (-p.count("/"), p)):
        path = storage.direct(run / rel)
        if not path.is_relative_to(run) or _identity(_entry(run)) != run_identity:
            raise ValueError("test payload scope changed during retirement")
        kind, identity, size, mtime = rows[rel]
        info = _entry(path)
        if _identity(info) != identity:
            raise ValueError("test payload object changed during retirement")
        if kind == "file":
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_size != size or info.st_mtime_ns != mtime):
                raise ValueError("test payload file changed during retirement")
            path.unlink()
        else:
            path.rmdir()
    if _identity(_entry(run)) != run_identity:
        raise ValueError("test payload root changed during retirement")
    run.rmdir()
    _write(META / (run.name + ".retired.json"),
           {"id": run.name, "inventory_sha256": success["inventory_sha256"],
            "retired_ns": time.time_ns()}, storage, privacy)


def _prune(storage, privacy):
    successes = []
    runs = list(RUNS.iterdir())
    if len(runs) > MAX_RUNS:
        raise ValueError("registered test run count exceeds its bound")
    for run in runs:
        if not _run_id(run.name):
            raise ValueError("unregistered object in owned test run root")
        storage.direct(run)
        privacy.require_private_directory(run)
        if os.path.lexists(META / (run.name + ".retire-intent.json")):
            continue  # Preserve any residue after uncertain retirement.
        success = _closed_success(run.name, storage, privacy)
        if success is not None:
            successes.append((success["finished_ns"], run, success))
    successes.sort(reverse=True)
    for _, run, success in successes[KEEP_SUCCESSES:]:
        _retire(run, success, storage, privacy)


def _native_run(native, executable, argv, environment, run, profile):
    class BudgetedAPI(native.WindowsAPI):
        def wait_process(self, process, milliseconds):
            if milliseconds <= 5000:
                return super().wait_process(process, milliseconds)
            deadline = time.monotonic() + milliseconds / 1000
            while True:
                remaining = int((deadline - time.monotonic()) * 1000)
                if remaining <= 0:
                    return "timeout"
                result = super().wait_process(process, min(5000, remaining))
                if result != "timeout":
                    return result
                _measure(run, payload=True, moving=True)

    return native.run_bounded(BudgetedAPI(), executable, argv, environment, str(CHECKOUT),
                              timeout_seconds=600 if profile == "windows-cpu" else 900,
                              memory_limit=MEMORY_BYTES,
                              process_limit=PROCESS_LIMIT, require_child_job_proof=True)


def run_profile(profile, base_environment):
    """Start the fixed profile; success needs a drained Job and a closed lease."""
    storage, privacy, native = _components()
    try:
        if profile not in PROFILES:
            raise ValueError("unknown generated check profile")
        _layout(storage, privacy)
        with _lock(storage, privacy):
            _prune(storage, privacy)
            hot, _ = _measure(TESTS)
            count = 0
            for path in META.glob("*.started.json"):
                run_name = path.name.removesuffix(".started.json")
                if not os.path.lexists(META / (run_name + ".retired.json")):
                    count += 1
            if count >= MAX_RUNS or hot + RUN_BYTES > HOT_BYTES:
                raise ValueError("D test storage budget exhausted")
            run_id = str(uuid.uuid4())
            run = RUNS / run_id
            start = _started(run_id, profile)
            _write(META / (run_id + ".started.json"), start, storage, privacy)
            exe = sys.executable
            code = _native_run(native, exe, [exe, "-B", "-m", "tools.check_windows_storage", run_id],
                               _environment(base_environment, BOOTSTRAP), run, profile)
            if code:
                raise subprocess.CalledProcessError(code, [f"generated check {profile}; evidence in {run}"])
            outcome = _read(run / "result.json", storage, privacy)
            lease_id = outcome["admission"]
            if not _run_id(lease_id):
                raise ValueError("invalid generated check admission identity")
            lease = _read(WORK / "admission" / lease_id / "receipt.json", storage, privacy)
            job = {"flags": JOB_FLAGS, "memory_limit": MEMORY_BYTES, "process_limit": PROCESS_LIMIT}
            if (outcome != {"start": start, "admission": lease_id, "job": job}
                    or lease.get("operation_id") != lease_id or lease.get("state") != "closed"
                    or lease.get("outputs") != [str(run)] or lease.get("planned_bytes") != RUN_BYTES
                    or type(lease.get("actual_bytes")) is not int or not 0 < lease["actual_bytes"] <= RUN_BYTES):
                raise ValueError("generated check closure did not match its admission")
            used, rows = _measure(run, payload=True, inventory=True)
            outer_temp = storage.direct(WORK / "admission" / lease_id / "temporary")
            privacy.require_private_directory(outer_temp)
            if used != lease["actual_bytes"] or any(outer_temp.iterdir()):
                raise ValueError("test payload grew after storage admission closed")
            nested_sha, residue = _nested_admissions(run, storage, privacy)
            success = {"start": start, "exit_code": 0, "admission": lease_id, "admission_closed": True,
                       "admission_sha256": hashlib.sha256(_json_bytes(lease)).hexdigest(),
                       "nested_admissions_sha256": nested_sha, "retention_eligible": not residue,
                       "native_job_closed": True, "finished_ns": time.time_ns(),
                       "payload_identity": list(_identity(_entry(run))), "payload_bytes": used,
                       "inventory_sha256": hashlib.sha256(_json_bytes(rows)).hexdigest()}
            _write(META / (run_id + ".closed.json"), success, storage, privacy)
            _prune(storage, privacy)
            print(f"{profile} passed under Windows D test storage. Scratch and log at {run}")
    except (OSError, ValueError, native.CheckRefused) as error:
        raise SystemExit(f"Windows D test storage refused: {error}") from None


def _worker(run_id):
    from tools import check

    storage, privacy, native = _components()
    if not _run_id(run_id):
        raise ValueError("invalid generated test run identity")
    job = native.WindowsAPI().consume_job_proof()
    if job != {"flags": JOB_FLAGS, "memory_limit": MEMORY_BYTES, "process_limit": PROCESS_LIMIT}:
        raise ValueError("unexpected native test job limits")
    _layout(storage, privacy)
    start = _read(META / (run_id + ".started.json"), storage, privacy)
    profile = start["profile"]
    if (type(start.get("started_ns")) is not int
            or start != {**_started(run_id, profile), "started_ns": start["started_ns"]}
            or profile not in PROFILES):
        raise ValueError("invalid generated test registration")
    run = RUNS / run_id
    inherited = dict(os.environ)
    try:
        with storage.operation([run], [(run, "generated source check", RUN_BYTES)]) as admission_temp:
            storage.private_mkdir(run)
            scratch = storage.private_mkdir(run / "temporary")
            nested_scratch = storage.private_mkdir(run / "admitted-temporary")
            os.environ.clear()
            os.environ.update(_environment(inherited, scratch))
            os.environ["PHOTOHOUSE_WORK_ROOT"] = str(run)
            if profile == "web":
                os.environ["PH_BROWSER_ARTIFACTS"] = str(storage.private_mkdir(run / "artifacts"))
            tempfile.tempdir = str(scratch)
            with (run / "check.log").open("x", encoding="utf-8") as log:
                def launch(args, cwd, env):
                    child_env = {**env, **_environment({}, scratch), "PHOTOHOUSE_WORK_ROOT": str(run)}
                    if args[:3] != [sys.executable, "-m", "pytest"]:
                        subprocess.run(args, cwd=cwd, env=child_env, stdout=log,
                                       stderr=subprocess.STDOUT, check=True)
                        return
                    # This process owns the volume lease. Preparation tests
                    # reuse it through app.work_storage on the same thread.
                    previous = Path.cwd()
                    previous_imports = sys.path[:]
                    os.chdir(cwd)
                    sys.path.insert(0, str(cwd))
                    try:
                        import pytest

                        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                            result = int(pytest.main([*args[3:], "--basetemp", str(run / "pytest")]))
                    finally:
                        sys.path[:] = previous_imports
                        os.chdir(previous)
                    if result:
                        raise subprocess.CalledProcessError(result, args)

                check._lean_run = launch
                try:
                    with storage.operation_temporaries_under(nested_scratch):
                        check.generated_profile(profile)()
                except BaseException:
                    traceback.print_exc(file=log)
                    raise
                finally:
                    check._lean_run = None
            _write(run / "result.json", {"start": start, "job": job,
                                        "admission": admission_temp.parent.name}, storage, privacy)
    except subprocess.CalledProcessError as error:
        return error.returncode
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("A registered generated test run is required.")
    raise SystemExit(_worker(sys.argv[1]))

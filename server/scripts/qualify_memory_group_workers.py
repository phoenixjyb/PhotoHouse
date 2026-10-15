"""Run approved CPU and video preparation workers against a generated E7 fixture.

The only inputs are an absent private output directory and explicit local
ffmpeg/ffprobe executables. The fixture is migrated from the real D1 schema to
E7; no database, service, model, GPU, or family media is accepted or opened.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import sqlite3
import subprocess
import sys

from PIL import Image

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / "backend"))
sys.path.insert(0, str(SERVER / "scripts"))

import qualify_memory_groups as memory_qualification
from app.access.private_storage import require_private_directory, require_private_file

FROM = "d1f6a8c3e920"
TO = "e7c1a9d5b304"
WORKER_TASKS = ("thumb", "phash", "video_probe", "video_keyframes")
WORKER_ASSET_IDS = {"thumb": 101, "phash": 101, "video_probe": 102, "video_keyframes": 102}
REPORT_NAME = "qualification-report.json"
FAILURE_NAME = "qualification-failure.json"
MAX_JPEG = 2 * 1024**2


def _path(value: str | Path, *, executable: bool = False) -> Path:
    path = Path(value)
    if (not path.is_absolute() or ".." in path.parts or path.anchor.startswith(("//", "\\\\"))
            or path.parent.resolve(strict=True) != path.parent or path.is_symlink()
            or not path.is_file() or path.resolve(strict=True) != path):
        raise ValueError("explicit_direct_local_file_required")
    if executable and not os.access(path, os.X_OK):
        raise ValueError("media_executable_not_runnable")
    return path


def _check_windows_paths(target: Path, *, windows: bool | None = None) -> None:
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return
    root = PureWindowsPath(target)
    names = ("primary.sqlite", "originals", "derived", "synthetic.png", "synthetic.mp4",
             REPORT_NAME, FAILURE_NAME)
    paths = [root / name for name in names]
    paths += [root / "schema-guard" / name
              for name in ("primary.sqlite", "a0-backup.sqlite")]
    paths += [PureWindowsPath(str(path) + suffix)
              for path in tuple(paths) if path.suffix == ".sqlite"
              for suffix in ("-journal", "-wal", "-shm")]
    paths += [root / "derived" / "thumbnails" / edge / "101.jpg" for edge in ("256", "1024")]
    paths += [root / "derived" / "video_frames" / "102" / "frame_00001.jpg"]
    units = lambda value: len(str(value).encode("utf-16le")) // 2
    if any(units(path) > 259 for path in paths) or any(units(p) > 247 for p in (root, *root.parents)):
        raise ValueError("windows_fixture_path_too_long")
    if any(units(value) > 259 for value in (sys.executable, Path(__file__).resolve())):
        raise ValueError("windows_launch_path_too_long")


def _validate_output(target: Path) -> None:
    if (not target.is_absolute() or ".." in target.parts or os.path.lexists(target)
            or target.parent.resolve(strict=True) != target.parent):
        raise ValueError("new_absolute_output_required")
    require_private_directory(target.parent)
    _check_windows_paths(target)


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _create_fixture(target: Path, ffmpeg: Path, ffprobe: Path) -> tuple[Path, Path, Path, str, str]:
    originals, derived = target / "originals", target / "derived"
    originals.mkdir(mode=0o700); derived.mkdir(mode=0o700)
    require_private_directory(originals); require_private_directory(derived)
    image = originals / "synthetic.png"
    Image.new("RGB", (96, 64), (30, 120, 170)).save(image, format="PNG")
    image.chmod(0o600); require_private_file(image)
    movie = originals / "synthetic.mp4"
    env = _child_environment(target)
    try:
        subprocess.run([str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                        "-f", "lavfi", "-i", "testsrc2=size=128x72:rate=5", "-t", "2",
                        "-threads", "1", "-c:v", "mpeg4", "-q:v", "5", str(movie)],
                       check=True, timeout=60, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("synthetic_video_generation_failed") from error
    movie.chmod(0o600)
    require_private_file(movie)
    database = target / "primary.sqlite"
    memory_qualification._seed(database)
    image_hash, movie_hash = _hash(image), _hash(movie)
    with closing(memory_qualification._db(database)) as db:
        db.execute("UPDATE assets SET path=?,hash_sha256=?,file_size=?,mime='image/png',status='active' WHERE id=101",
                   (str(image), image_hash, image.stat().st_size))
        db.execute("UPDATE access_uploads SET sha256=?,bytes=?,state='assigned',destination_library_id=?,approval_mode='manual' WHERE asset_id=101",
                   (image_hash, image.stat().st_size, memory_qualification.LIBRARY))
        db.execute("UPDATE assets SET path=?,hash_sha256=?,file_size=?,mime='video/mp4',status='active' WHERE id=102",
                   (str(movie), movie_hash, movie.stat().st_size))
        db.execute("INSERT INTO access_uploads(id,asset_id,account_id,incoming_label,batch,original_name,sha256,bytes,state,created_at,destination_library_id,approval_mode) VALUES(?,?,?,?,?,?,?,?,?,1,?,?)",
                   (102, 102, memory_qualification.OWNER, "synthetic-owner", "e" * 32,
                    movie.name, movie_hash, movie.stat().st_size, "assigned",
                    memory_qualification.LIBRARY, "manual"))
        db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('thumb','pending',60,'{\"asset_id\":101}')")
        db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('phash','pending',80,'{\"asset_id\":101}')")
        db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('video_probe','pending',40,'{\"asset_id\":102}')")
        db.commit()
    if not ffprobe.is_file():
        raise ValueError("explicit_ffprobe_unavailable")
    return database, originals, derived, image_hash, movie_hash


def _child_environment(target: Path) -> dict[str, str]:
    env = {"PATH": str(Path(sys.executable).resolve().parent),
           "TEMP": str(target), "TMP": str(target),
           "PHOTOHOUSE_NO_DOTENV": "1", "PYTHONNOUSERSITE": "1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    if os.name == "nt":
        system_root = os.environ.get("SystemRoot")
        if not system_root:
            raise RuntimeError("system_root_unavailable")
        env.update(SYSTEMROOT=system_root, WINDIR=system_root)
    else:
        env["PATH"] = os.environ.get("PATH", env["PATH"])
    return env


def _worker_once(script: str, args: list[str], target: Path, timeout: int) -> None:
    command = [sys.executable, "-I", "-B", str(SERVER / "scripts" / script), *args,
               "--execute", "--once"]
    try:
        result = subprocess.run(command, timeout=timeout, stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                env=_child_environment(target), cwd=target)
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError(f"{script}:launch_failed") from error
    if result.returncode:
        raise RuntimeError(f"{script}:exit_{result.returncode}")


def _decoded_jpeg(path: Path, edge: int) -> tuple[int, int]:
    try:
        if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= MAX_JPEG:
            raise ValueError("output_shape")
        with Image.open(path) as image:
            if image.format != "JPEG" or not (0 < image.width <= edge and 0 < image.height <= edge):
                raise ValueError("output_dimensions")
            image.load()
            return image.width, image.height
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise RuntimeError("synthetic_jpeg_decode_failed") from error


def _group_source_snapshot(database: Path) -> tuple:
    with closing(sqlite3.connect(database)) as db:
        names = ("access_memory_groups", "access_memory_group_revisions", "access_stories", "captions")
        return tuple((name, db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall()) for name in names)


def _remove_seed_caption_task(database: Path) -> None:
    """Remove the image caption queued by the shared D1 seed helper."""
    with closing(memory_qualification._db(database)) as db:
        rows = db.execute("SELECT id,payload_json FROM tasks WHERE type='caption'").fetchall()
        matching = []
        for task_id, payload_raw in rows:
            try:
                payload = json.loads(payload_raw or "{}")
            except (TypeError, ValueError):
                continue
            if payload == {"asset_id": 101}:
                matching.append(task_id)
        if len(matching) != 1:
            raise RuntimeError("synthetic_seed_caption_task_unexpected")
        db.execute("DELETE FROM tasks WHERE id=?", (matching[0],))
        db.commit()


def _verify_tasks(database: Path) -> None:
    with closing(sqlite3.connect(database)) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchall()
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
        worker_rows = db.execute(
            "SELECT type,state,payload_json FROM tasks WHERE type IN ('thumb','phash','video_probe','video_keyframes') ORDER BY id").fetchall()
        chained_rows = db.execute(
            "SELECT type,state,payload_json FROM tasks WHERE type IN ('caption','video_embed') ORDER BY id").fetchall()
    if integrity != [("ok",)] or foreign_keys:
        raise RuntimeError("synthetic_database_integrity_failed")
    if len(worker_rows) != len(WORKER_TASKS):
        raise RuntimeError("synthetic_worker_task_count_invalid")
    observed = {}
    for kind, state, payload_raw in worker_rows:
        if kind in observed:
            raise RuntimeError("synthetic_worker_task_duplicate")
        try:
            payload = json.loads(payload_raw or "{}")
        except (TypeError, ValueError) as error:
            raise RuntimeError("synthetic_worker_task_payload_invalid") from error
        if state != "finished" or payload != {"asset_id": WORKER_ASSET_IDS.get(kind)}:
            raise RuntimeError("synthetic_worker_task_state_invalid")
        observed[kind] = payload["asset_id"]
    if observed != WORKER_ASSET_IDS:
        raise RuntimeError("synthetic_worker_tasks_incomplete")
    expected_chained = {"caption": {"state": "pending", "payload": {"asset_id": 102}},
                        "video_embed": {"state": "pending", "payload": {"asset_id": 102}}}
    if len(chained_rows) != len(expected_chained):
        raise RuntimeError("synthetic_chained_task_count_invalid")
    chained = {}
    for kind, state, payload_raw in chained_rows:
        if kind in chained:
            raise RuntimeError("synthetic_chained_task_duplicate")
        try:
            payload = json.loads(payload_raw or "{}")
        except (TypeError, ValueError) as error:
            raise RuntimeError("synthetic_chained_task_payload_invalid") from error
        chained[kind] = {"state": state, "payload": payload}
    if chained != expected_chained:
        raise RuntimeError("synthetic_chained_task_invalid")


def _fixture_report() -> dict:
    return {"status": "passed", "synthetic_only": True, "native_windows": os.name == "nt",
            "source_revision": FROM, "target_revision": TO,
            "guarded_a0_upgrade": {"source_revision": "a0c9d2e4f817", "revision": TO,
                "new_tables_created": 9, "new_rows_created": 0,
                "interruption_rollback_verified": True, "backup_unchanged": True,
                "existing_rows_preserved": True},
            "workers_executed": list(WORKER_TASKS), "decoded_thumbnails": [256, 1024],
            "decoded_keyframes": True, "originals_hashes_unchanged": True,
            "approved_receipts_and_scope_preserved": True,
            "memory_group_and_source_rows_preserved": True,
            "caption_and_video_embed_remain_pending": True,
            "production_database_opened": False, "family_media_opened": False,
            "models_loaded": False, "gpu_used": False, "services_changed": False}


def run(output: str | Path, ffmpeg: str | Path, ffprobe: str | Path) -> dict:
    target = Path(output)
    _validate_output(target)
    ffmpeg_path, ffprobe_path = _path(ffmpeg, executable=True), _path(ffprobe, executable=True)
    target.mkdir(mode=0o700)
    require_private_directory(target)
    phase = "schema_guard"
    try:
        import apply_memory_group_schema
        guard_report = apply_memory_group_schema.qualify_generated(target / "schema-guard")
        if guard_report != _fixture_report()["guarded_a0_upgrade"]:
            raise RuntimeError("synthetic_schema_guard_unexpected")
        phase = "fixture"
        database, originals, derived, image_hash, movie_hash = _create_fixture(target, ffmpeg_path, ffprobe_path)
        # Apply the actual additive migration after D1 rows and approved scopes exist.
        phase = "migration"
        memory_qualification._migrate(database, TO)
        if memory_qualification._revision(database) != [(TO,)]:
            raise RuntimeError("synthetic_e7_revision_missing")
        # _seed already wrote an authored source story and D1 caption; add the
        # reviewed ID-only group using that source through the same domain API.
        with closing(memory_qualification._db(database)) as db:
            source = db.execute("SELECT id,title,text,language,byline FROM access_stories ORDER BY id LIMIT 1").fetchone()
        if source is None:
            raise RuntimeError("synthetic_source_story_missing")
        story = {"id": source[0]}
        phase = "groups"
        memory_qualification._groups(database, story)
        _remove_seed_caption_task(database)
        group_source_before = _group_source_snapshot(database)
        receipt_before = _receipt_scope_snapshot(database)
        phase = "workers"
        cpu_args = ["--database", str(database), "--originals-root", str(originals),
                    "--derived-root", str(derived), "--stop-file", str(target / "stop.flag")]
        for _ in range(2):
            _worker_once("run_approved_cpu_worker.py", cpu_args, target, 150)
        video_args = ["--database", str(database), "--derived-root", str(derived),
                      "--media-root", str(originals), "--ffprobe", str(ffprobe_path),
                      "--ffmpeg", str(ffmpeg_path)]
        for _ in range(2):
            _worker_once("run_approved_video_worker.py", video_args, target, 400)
        phase = "verify"
        _verify_tasks(database)
        with closing(sqlite3.connect(database)) as db:
            phash = db.execute("SELECT perceptual_hash FROM assets WHERE id=101").fetchone()[0]
            video_meta = db.execute("SELECT duration_sec,width,height,fps FROM assets WHERE id=102").fetchone()
            approved = db.execute("""SELECT a.id,a.path,a.hash_sha256,a.file_size,u.state,u.sha256,u.bytes,
                m.library_id,l.state FROM assets a JOIN access_uploads u ON u.asset_id=a.id
                JOIN access_asset_libraries m ON m.asset_id=a.id JOIN access_libraries l ON l.id=m.library_id
                WHERE a.id IN (101,102) ORDER BY a.id""").fetchall()
        if not isinstance(phash, str) or not re.fullmatch(r"[0-9a-fA-F]{16}", phash):
            raise RuntimeError("synthetic_phash_missing")
        duration, width, height, fps = video_meta
        if (width != 128 or height != 72 or isinstance(duration, bool) or isinstance(fps, bool)
                or not isinstance(duration, (int, float)) or not isinstance(fps, (int, float))
                or not math.isfinite(duration) or not math.isfinite(fps)
                or abs(duration - 2.0) > 0.25 or abs(fps - 5.0) > 0.01):
            raise RuntimeError("synthetic_video_metadata_failed")
        thumbs = [_decoded_jpeg(derived / "thumbnails" / str(edge) / "101.jpg", edge) for edge in (256, 1024)]
        frames = sorted((derived / "video_frames" / "102").glob("frame_*.jpg"))
        if not 1 <= len(frames) <= 32:
            raise RuntimeError("synthetic_keyframe_count_failed")
        for frame in frames:
            _decoded_jpeg(frame, 1024)
        if _group_source_snapshot(database) != group_source_before:
            raise RuntimeError("synthetic_group_source_rows_changed")
        if _receipt_scope_snapshot(database) != receipt_before:
            raise RuntimeError("synthetic_approved_receipt_scope_changed")
        if (hashlib.sha256((originals / "synthetic.png").read_bytes()).hexdigest() != image_hash
                or hashlib.sha256((originals / "synthetic.mp4").read_bytes()).hexdigest() != movie_hash):
            raise RuntimeError("synthetic_original_changed")
        if any(row[4] != "assigned" or row[5] != row[2] or row[6] != row[3]
               or row[7] != memory_qualification.LIBRARY or row[8] != "active" for row in approved):
            raise RuntimeError("synthetic_approval_scope_invalid")
        report = _fixture_report()
        report.update(guarded_a0_upgrade=guard_report,
                      decoded_thumbnails=[{"width": w, "height": h} for w, h in thumbs],
                      decoded_keyframes=len(frames))
        memory_qualification._write_json(target / REPORT_NAME, report)
        return report
    except Exception as error:
        code = getattr(error, "winerror", None)
        if type(code) is not int or not 0 <= code <= 65535:
            code = None
        try:
            memory_qualification._write_json(target / FAILURE_NAME,
                {"status": "failed", "synthetic_only": True, "phase": phase,
                 "exception_class": type(error).__name__ if type(error).__name__ in
                 {"OSError", "ValueError", "RuntimeError", "OperationalError", "IntegrityError"} else "Exception",
                 "winerror": code})
        except Exception:
            pass
        raise


def _receipt_scope_snapshot(database: Path) -> tuple:
    with closing(sqlite3.connect(database)) as db:
        return (tuple(db.execute("SELECT id,path,hash_sha256,file_size,mime,status FROM assets WHERE id IN (101,102) ORDER BY id")),
                tuple(db.execute("SELECT asset_id,account_id,incoming_label,batch,original_name,sha256,bytes,state,destination_library_id,approval_mode FROM access_uploads WHERE asset_id IN (101,102) ORDER BY asset_id")),
                tuple(db.execute("SELECT asset_id,library_id FROM access_asset_libraries WHERE asset_id IN (101,102) ORDER BY asset_id")))


def _bounded_report(target: Path, ffmpeg: Path, ffprobe: Path) -> dict:
    _validate_output(target)
    ffmpeg, ffprobe = _path(ffmpeg, executable=True), _path(ffprobe, executable=True)
    from bounded_windows_job import CheckRefused, WindowsAPI, run_bounded
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise CheckRefused("system_root_unavailable")
    executable = str(Path(sys.executable).resolve())
    environment = {"PATH": str(Path(executable).parent), "SYSTEMROOT": system_root,
                   "WINDIR": system_root, "TEMP": str(target), "TMP": str(target),
                   "PHOTOHOUSE_NO_DOTENV": "1", "PYTHONNOUSERSITE": "1",
                   "PYTHONDONTWRITEBYTECODE": "1"}
    program = ("import runpy\n" +
               f"runpy.run_path({str(Path(__file__).resolve())!r},run_name='photohouse_generated_worker_qualification')['run']({str(target)!r},{str(ffmpeg)!r},{str(ffprobe)!r})\n")
    code = run_bounded(WindowsAPI(), executable, [executable, "-I", "-B", "-c", program],
                       environment, str(target.parent), timeout_seconds=900,
                       memory_limit=2 * 1024**3, process_limit=8,
                       minimum_free_ram=8 * 1024**3)
    if code != 0:
        raise CheckRefused("qualification_child_failed")
    path = target / REPORT_NAME
    require_private_file(path)
    raw = path.read_bytes()
    expected = _fixture_report()
    if not 0 < len(raw) <= 8192:
        raise CheckRefused("qualification_report_unavailable")
    value = json.loads(raw)
    # Per-output dimensions and frame count are bounded fixture evidence.
    if (type(value) is not dict or any(value.get(key) != expected_value for key, expected_value in expected.items()
                                       if key not in {"decoded_thumbnails", "decoded_keyframes"})
            or type(value.get("decoded_keyframes")) is not int
            or not 1 <= value["decoded_keyframes"] <= 32
            or value.get("decoded_thumbnails") != [{"width": 96, "height": 64}, {"width": 96, "height": 64}]):
        raise CheckRefused("qualification_report_unavailable")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="absent absolute directory beneath a private parent")
    parser.add_argument("--ffmpeg", required=True, help="existing direct local ffmpeg executable")
    parser.add_argument("--ffprobe", required=True, help="existing direct local ffprobe executable")
    args = parser.parse_args(argv)
    output = Path(args.out)
    report = (_bounded_report(output, Path(args.ffmpeg), Path(args.ffprobe)) if os.name == "nt"
              else run(output, args.ffmpeg, args.ffprobe))
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","synthetic_only":true}', file=sys.stderr)
        raise SystemExit(2) from None

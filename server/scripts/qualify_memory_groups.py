"""Generated e7 upgrade, interrupted DDL and backup-restore qualification.

There is deliberately no database, media, provider or service argument. Only an
absent output directory under an existing private parent is accepted. Windows
CLI execution is supervised by a bounded Job; portable runs are source evidence.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import sqlite3
import sys
import uuid

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / "backend"))
sys.path.insert(0, str(SERVER / "scripts"))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL

from app.access.credentials import session_digest
from app.access.memory_group_schema import TABLE, REVISION_TABLE, verify_memory_group_schema
from app.access.memory_groups import MemoryGroups
from app.access.private_storage import require_private_directory, require_private_file
from app.access.service import AccessDenied, AccessService
from app.access.stories import Stories

FROM = "d1f6a8c3e920"
TO = "e7c1a9d5b304"
NOW = 2_000_000_000
LIBRARY = "synthetic-group-library"
OWNER, VIEWER = "synthetic-owner", "synthetic-viewer"
TOKEN, VIEWER_TOKEN = "a" * 43, "b" * 43
CASES = ("interrupted_upgrade_rollback", "additive_upgrade_preserves_existing_rows",
         "reviewed_group_original_attribution_and_retry", "backup_restore_before_and_after_groups",
         "nonempty_downgrade_refused")
PHASES = ("seed", "interruption", "upgrade", "groups", "restore", "downgrade", "report")
FILE_NAMES = ("primary.sqlite", "d1-backup.sqlite", "d1-restored.sqlite",
              "e7-backup.sqlite", "e7-restored.sqlite", "history-only.sqlite",
              "qualification-report.json", "qualification-failure.json")


def _check_windows_paths(target, *, windows=None):
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return
    root = PureWindowsPath(target)
    paths = [root / name for name in FILE_NAMES]
    paths += [PureWindowsPath(str(path) + suffix) for path in tuple(paths)
              if path.suffix == ".sqlite" for suffix in ("-journal", "-wal", "-shm")]
    units = lambda p: len(str(p).encode("utf-16le")) // 2
    if (any(units(p) > 259 for p in paths)
            or any(units(p) > 247 for p in (root, *root.parents))):
        raise ValueError("windows_fixture_path_too_long")
    if any(units(p) > 259 for p in (sys.executable, Path(__file__).resolve())):
        raise ValueError("windows_launch_path_too_long")


def _validate_output(target):
    if (not target.is_absolute() or ".." in target.parts
            or os.path.lexists(target) or target.parent.resolve(strict=True) != target.parent):
        raise ValueError("new_absolute_output_required")
    require_private_directory(target.parent)
    _check_windows_paths(target)


def _create_file(path):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    os.close(fd)
    require_private_file(path)


def _db(path):
    require_private_file(path)
    db = sqlite3.connect(path, timeout=5)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=FULL")
    return db


def _migrate(path, revision, *, down=False, interrupt=False):
    require_private_file(path)
    engine = create_engine(URL.create("sqlite", database=str(path)))
    def fail(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().startswith("CREATE TABLE " + REVISION_TABLE):
            raise RuntimeError("synthetic_ddl_interruption")
    if interrupt:
        event.listen(engine, "before_cursor_execute", fail)
    try:
        with engine.begin() as connection:
            config = Config()
            config.set_main_option("script_location", str(SERVER / "backend" / "migrations"))
            config.attributes["connection"] = connection
            (command.downgrade if down else command.upgrade)(config, revision)
    finally:
        engine.dispose()


def _snapshot(path, *, exclude_groups=False):
    with closing(_db(path)) as db:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("synthetic_database_integrity_failed")
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        skip = {"alembic_version"} | ({TABLE, REVISION_TABLE} if exclude_groups else set())
        quoted = lambda name: '"' + name.replace('"', '""') + '"'
        rows = {name: sorted(db.execute("SELECT * FROM " + quoted(name)).fetchall(), key=repr)
                for name in tables if name not in skip}
        objects = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND name!='alembic_version' ORDER BY type,name").fetchall()
        if exclude_groups:
            objects = [row for row in objects if row[2] not in {TABLE, REVISION_TABLE}]
        return objects, rows


def _revision(path):
    with closing(_db(path)) as db:
        return db.execute("SELECT version_num FROM alembic_version").fetchall()


def _backup(source, target):
    # Both are our generated files; the source has no open writer at this point.
    _create_file(target)
    with closing(_db(source)) as src, closing(_db(target)) as dst:
        src.backup(dst)
    if _snapshot(source) != _snapshot(target) or _revision(source) != _revision(target):
        raise RuntimeError("synthetic_backup_mismatch")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _seed(path):
    _create_file(path)
    _migrate(path, FROM)
    with closing(_db(path)) as db:
        for actor, phone, token, role in ((OWNER, "+12025550177", TOKEN, "owner"),
                                         (VIEWER, "+12025550178", VIEWER_TOKEN, "viewer")):
            db.execute("INSERT INTO access_accounts(id,phone_login,password_hash,display_name) VALUES(?,?,?,?)",
                       (actor, phone, "synthetic-nonlogin-hash", "Synthetic narrator"))
            db.execute("INSERT INTO access_sessions(digest,account_id,expires_at) VALUES(?,?,?)",
                       (session_digest(token), actor, NOW + 1000))
        db.execute("INSERT INTO access_libraries(id,bootstrap_operator) VALUES(?,?)", (LIBRARY, OWNER))
        for actor, role in ((OWNER, "owner"), (VIEWER, "viewer")):
            db.execute("INSERT INTO access_memberships(account_id,library_id,status,role,revision,approved_by) VALUES(?,?,'approved',?,1,?)",
                       (actor, LIBRARY, role, OWNER))
        for ident, mime in ((101, "image/png"), (102, "video/mp4")):
            db.execute("INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at) VALUES(?,?,?,'active',?,'2026-01-01 10:00:00')",
                       (ident, f"synthetic-{ident}", "c" * 64, mime))
            db.execute("INSERT INTO access_asset_libraries VALUES(?,?)", (ident, LIBRARY))
        db.execute("INSERT INTO captions(asset_id,text,model,user_edited,superseded) VALUES(101,'Synthetic legacy caption','synthetic-model',1,0)")
        db.execute("INSERT INTO access_uploads(asset_id,account_id,incoming_label,batch,original_name,sha256,bytes,state,created_at) VALUES(101,?,'synthetic',?,'synthetic.png',?,100,'assigned',?)",
                   (OWNER, "d" * 32, "c" * 64, NOW))
        db.execute("INSERT INTO tasks(type,state,priority,payload_json) VALUES('caption','pending',0,'{\"asset_id\":101}')")
        db.commit()
        note = Stories(AccessService(db, clock=lambda: NOW)).save(TOKEN, LIBRARY, {
            "title": "湖边的一天", "text": "我们一起看夕阳。", "language": "zh",
            "byline": "Synthetic narrator", "mutation_id": str(uuid.uuid4())}, asset_id=101)
        return note


def _body(note, revision="0"):
    return {"asset_ids": "101,102", "excluded_asset_ids": "103", "source_story_ids": note["id"],
            "theme": "everyday", "revision": revision, "mutation_id": str(uuid.uuid4())}


def _groups(path, note):
    with closing(_db(path)) as db:
        access = AccessService(db, clock=lambda: NOW)
        domain = MemoryGroups(access)
        body = _body(note)
        group = domain.save(TOKEN, LIBRARY, body)
        if group != domain.save(TOKEN, LIBRARY, body):
            raise RuntimeError("synthetic_idempotency_failed")
        try:
            domain.save(VIEWER_TOKEN, LIBRARY, _body(note))
        except AccessDenied:
            pass
        else:
            raise RuntimeError("synthetic_viewer_write_allowed")
        edited = Stories(access).save(TOKEN, LIBRARY, {"revision": "1", "title": "湖边的一天",
            "text": "我们沿着湖边散步，一起看夕阳。", "language": "zh", "byline": "Synthetic narrator",
            "mutation_id": str(uuid.uuid4())}, story_id=note["id"])
        read = domain.get(VIEWER_TOKEN, LIBRARY, group["id"])
        if read["sources"][0]["text"] != edited["text"] or read["sources"][0]["author_id"] != OWNER:
            raise RuntimeError("synthetic_source_attribution_failed")
        update = _body(note, "1")
        update.update(asset_ids="101", excluded_asset_ids="102,103")
        current = domain.save(TOKEN, LIBRARY, update, group["id"])
        if (current["revision"] != "2" or current["asset_ids"] != ["101"]
                or domain.save(TOKEN, LIBRARY, body)["revision"] != "2"):
            raise RuntimeError("synthetic_later_retry_failed")
        db.execute("UPDATE access_memberships SET status='revoked',revision=2 WHERE account_id=?", (VIEWER,))
        db.commit()
        try:
            domain.get(VIEWER_TOKEN, LIBRARY, group["id"])
        except AccessDenied:
            pass
        else:
            raise RuntimeError("synthetic_revoked_read_allowed")
        if not verify_memory_group_schema(db):
            raise RuntimeError("synthetic_group_schema_failed")
        # Original prose and authors remain solely in original note storage.
        columns = {row[1] for name in (TABLE, REVISION_TABLE) for row in db.execute(f"PRAGMA table_info({name})")}
        if columns & {"text", "original_text", "original_audio", "byline", "title"}:
            raise RuntimeError("synthetic_group_copied_source_columns")
        return group["id"]


def _refuse_downgrade(path):
    before = _snapshot(path)
    try:
        _migrate(path, FROM, down=True)
    except RuntimeError as error:
        if str(error) != "Memory group records require reviewed offline backup restoration":
            raise
    else:
        raise RuntimeError("synthetic_nonempty_downgrade_allowed")
    if _snapshot(path) != before or _revision(path) != [(TO,)]:
        raise RuntimeError("synthetic_failed_downgrade_mutated")


def _write_json(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="ascii", newline="\n") as stream:
        require_private_file(path)
        json.dump(value, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _report(native):
    return {"status": "passed", "synthetic_only": True, "native_windows": native,
            "source_revision": FROM, "target_revision": TO, "cases_passed": list(CASES),
            "production_database_opened": False, "family_media_opened": False,
            "models_loaded": False, "services_changed": False, "workers_executed": False,
            "power_loss_qualified": False}


def run(output):
    target = Path(output)
    _validate_output(target)
    target.mkdir(mode=0o700)
    require_private_directory(target)
    phase = "seed"
    try:
        primary = target / "primary.sqlite"
        note = _seed(primary)
        original = _snapshot(primary)
        backup = target / "d1-backup.sqlite"
        backup_hash = _backup(primary, backup)
        phase = "interruption"
        try:
            _migrate(primary, TO, interrupt=True)
        except RuntimeError as error:
            if str(error) != "synthetic_ddl_interruption":
                raise
        else:
            raise RuntimeError("synthetic_interruption_not_reached")
        if _snapshot(primary) != original or _revision(primary) != [(FROM,)]:
            raise RuntimeError("synthetic_ddl_rollback_failed")
        phase = "upgrade"
        _migrate(primary, TO)
        if _snapshot(primary, exclude_groups=True) != original or _revision(primary) != [(TO,)]:
            raise RuntimeError("synthetic_additive_preservation_failed")
        phase = "groups"
        _groups(primary, note)
        phase = "restore"
        _backup(backup, target / "d1-restored.sqlite")
        if _snapshot(target / "d1-restored.sqlite") != original:
            raise RuntimeError("synthetic_old_restore_failed")
        e7_backup = target / "e7-backup.sqlite"
        e7_hash = _backup(primary, e7_backup)
        _backup(e7_backup, target / "e7-restored.sqlite")
        phase = "downgrade"
        _refuse_downgrade(target / "e7-restored.sqlite")
        # Independently check audit-only refusal after an interrupted/invalid
        # current-row removal. Deliberate fixture damage does not touch backups.
        history = target / "history-only.sqlite"
        _backup(e7_backup, history)
        with closing(_db(history)) as db:
            db.execute("PRAGMA foreign_keys=OFF")
            db.execute(f"DELETE FROM {TABLE}")
            db.commit()
            db.execute("PRAGMA foreign_keys=ON")
        # The deliberately orphaned history cannot pass a normal FK snapshot.
        # Compare its complete schema/rows separately without masking FK damage.
        with closing(_db(history)) as db:
            history_rows = db.execute(f"SELECT * FROM {REVISION_TABLE} ORDER BY revision").fetchall()
            history_objects = db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        try:
            _migrate(history, FROM, down=True)
        except RuntimeError as error:
            if str(error) != "Memory group records require reviewed offline backup restoration":
                raise
        else:
            raise RuntimeError("synthetic_history_downgrade_allowed")
        with closing(_db(history)) as db:
            if (_revision(history) != [(TO,)] or db.execute(f"SELECT count(*) FROM {TABLE}").fetchone() != (0,)
                    or db.execute(f"SELECT * FROM {REVISION_TABLE} ORDER BY revision").fetchall() != history_rows
                    or db.execute("SELECT type,name,sql FROM sqlite_master ORDER BY type,name").fetchall() != history_objects):
                raise RuntimeError("synthetic_history_refusal_mutated")
        if hashlib.sha256(backup.read_bytes()).hexdigest() != backup_hash or hashlib.sha256(e7_backup.read_bytes()).hexdigest() != e7_hash:
            raise RuntimeError("synthetic_backup_changed")
        phase = "report"
        report = _report(os.name == "nt")
        _write_json(target / "qualification-report.json", report)
        return report
    except Exception as error:
        code = getattr(error, "winerror", None)
        if type(code) is not int or not 0 <= code <= 65535:
            code = None
        try:
            _write_json(target / "qualification-failure.json", {"status": "failed", "synthetic_only": True,
                "phase": phase, "exception_class": type(error).__name__ if type(error).__name__ in
                {"OSError", "ValueError", "RuntimeError", "OperationalError", "IntegrityError"} else "Exception", "winerror": code})
        except Exception:
            pass
        raise


def _bounded_report(target):
    _validate_output(target)
    from bounded_windows_job import CheckRefused, WindowsAPI, run_bounded
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise CheckRefused("system_root_unavailable")
    executable = str(Path(sys.executable).resolve())
    environment = {"PATH": str(Path(executable).parent), "SYSTEMROOT": system_root, "WINDIR": system_root,
                   "TEMP": str(target.parent), "TMP": str(target.parent), "PHOTOHOUSE_NO_DOTENV": "1",
                   "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    # The ordinary CLI always supervises on Windows. Its child calls only this
    # pinned generated-fixture function; there is no caller-set CLI bypass flag.
    program = ("import runpy\n"
               f"runpy.run_path({str(Path(__file__).resolve())!r},run_name='photohouse_generated_qualification')['run']({str(target)!r})\n")
    code = run_bounded(WindowsAPI(), executable,
        [executable, "-I", "-B", "-c", program],
        environment, str(target.parent), timeout_seconds=900, memory_limit=2 * 1024**3,
        process_limit=4, minimum_free_ram=8 * 1024**3)
    if code != 0:
        raise CheckRefused("qualification_child_failed")
    path = target / "qualification-report.json"
    require_private_file(path)
    with path.open("rb") as stream:
        raw = stream.read(8193)
    if not 0 < len(raw) <= 8192:
        raise CheckRefused("qualification_report_unavailable")
    value = json.loads(raw)
    expected = _report(True)
    if type(value) is not dict or value != expected or any(type(value.get(k)) is not bool for k, v in expected.items() if type(v) is bool):
        raise CheckRefused("qualification_report_unavailable")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="absent absolute directory beneath a private parent")
    args = parser.parse_args(argv)
    report = _bounded_report(Path(args.out)) if os.name == "nt" else run(args.out)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        print('{"status":"failed","synthetic_only":true}', file=sys.stderr)
        raise SystemExit(2) from None

"""Generated a0-to-f2 migration, paired backup and photo-stack lifecycle rehearsal.

Only a new private output directory is accepted. No runtime database, library,
media, model, provider or service can be selected. Windows CLI execution always
uses a bounded Job. Portable execution is source evidence, not Windows acceptance.
"""
from __future__ import annotations

import argparse
from contextlib import closing, contextmanager
import hashlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import sqlite3
import sys
import uuid
import wave

SERVER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER / "backend"))
sys.path.insert(0, str(SERVER / "scripts"))

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL

import apply_memory_group_schema as group_upgrade
import apply_library_photo_stack_schema as stack_upgrade
import run_photo_stack_worker as worker_host
import qualify_memory_groups as fixture
import rehearse_fullsize_database as full
import upgrade_original_deletion_journal as journal_upgrade
from app.access.annotations import Annotations
from app.access.library_photo_stacks import LibraryPhotoStacks, rebuild_photo_stack_index
from app.access.original_deletions import OriginalDeletionError, OriginalDeletionJournal
from app.access.photo_stack_schema import REVISION, TABLES
from app.access.private_storage import require_private_directory, require_private_file
from app.access.runtime import AccessConnection
from app.access.service import AccessDenied, AccessService
from app.access.transport import TransportError

FROM = "a0c9d2e4f817"
PARENT = "e7c1a9d5b304"
CASES = (
    "interrupted_a0_to_f2_rollback", "a0_to_f2_originals_preserved",
    "e7_to_f2_additive_upgrade", "paired_journal_upgrade_and_restores",
    "complete_cross_page_groups", "private_cover_separation_reset_and_conflicts",
    "new_asset_refresh_waits_for_hash_and_retains_failures",
    "stale_sources_and_revoked_access", "missing_and_stale_deletion_history_refused",
    "nonempty_downgrade_refused", "guarded_schema_application", "one_sweep_host_lifecycle",
)
FILE_NAMES = (
    "primary.sqlite", "journal.sqlite", "a0-backup.sqlite", "v1-backup.sqlite",
    "a0-restored.sqlite", "v1-restored.sqlite", "f2-before-journal.sqlite",
    "f2-backup.sqlite", "v2-backup.sqlite", "f2-restored.sqlite", "v2-restored.sqlite",
    "stale-restored.sqlite", "e7-edge.sqlite", "qualification-report.json",
    "qualification-failure.json", "primary.sqlite.photo-stack-refresh.lock",
)


def _check_windows_paths(target, *, windows=None):
    if windows is None:
        windows = os.name == "nt"
    if not windows:
        return
    root = PureWindowsPath(target)
    paths = [root / name for name in FILE_NAMES]
    paths += [PureWindowsPath(str(p) + suffix) for p in tuple(paths)
              if p.suffix == ".sqlite" for suffix in ("-journal", "-wal", "-shm")]
    units = lambda p: len(str(p).encode("utf-16le")) // 2
    if any(units(p) > 259 for p in paths) or any(units(p) > 247 for p in (root, *root.parents)):
        raise ValueError("windows_fixture_path_too_long")
    if any(units(p) > 259 for p in (sys.executable, Path(__file__).resolve())):
        raise ValueError("windows_launch_path_too_long")


def _validate_output(target):
    if (not target.is_absolute() or ".." in target.parts or os.path.lexists(target)
            or target.parent.resolve(strict=True) != target.parent):
        raise ValueError("new_absolute_output_required")
    require_private_directory(target.parent)
    _check_windows_paths(target)


def _require(value, code):
    if not value:
        raise RuntimeError("synthetic_" + code)


def _migrate(path, revision, *, interrupt=False, down=False):
    require_private_file(path)
    engine = create_engine(URL.create("sqlite", database=str(path)))
    def stop(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().startswith("CREATE TABLE " + TABLES[2]):
            raise RuntimeError("synthetic_f2_interruption")
    if interrupt:
        event.listen(engine, "before_cursor_execute", stop)
    try:
        with engine.begin() as connection:
            config = Config()
            config.set_main_option("script_location", str(SERVER / "backend" / "migrations"))
            config.attributes["connection"] = connection
            (command.downgrade if down else command.upgrade)(config, revision)
    finally:
        engine.dispose()


def _preserved(before, after):
    objects, rows = before
    current_objects, current_rows = after
    return (all(row in current_objects for row in objects)
            and all(current_rows.get(name) == values for name, values in rows.items()))


@contextmanager
def _connection(path, journal=None):
    require_private_file(path)
    with closing(sqlite3.connect(path, timeout=5, factory=AccessConnection)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        db.original_deletions = journal
        yield db


def _seed_originals(primary, journal):
    # Bind before introducing any original annotation. The earlier fixture's
    # authored legacy story is deliberately retained through the full chain.
    with _connection(primary) as db:
        journal.bind(db)
        raw_text = "合成回忆：我们在湖边看夕阳。"
        audio = io.BytesIO()
        with wave.open(audio, "wb") as stream:
            stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
            stream.writeframes(b"\0\0" * 8000)
        identifiers = []
        for kind, raw in (("text", raw_text.encode()), ("audio", audio.getvalue()),
                          ("text", b"Disposable generated original for retained history")):
            ident = str(uuid.uuid4()); identifiers.append((ident, hashlib.sha256(raw).hexdigest()))
            db.execute('''INSERT INTO access_upload_annotations
                (id,author_id,library_id,batch,asset_id,kind,original_text,original_audio,
                 mime,duration_ms,sha256,language,consent,mutation_id,request_digest,created_at)
                VALUES(?,?,?,?,101,?,?,?,?,?,?,'zh',1,?,?,?)''',
                (ident, fixture.OWNER, fixture.LIBRARY, "d"*32, kind,
                 raw.decode() if kind == "text" else None, raw if kind == "audio" else None,
                 "audio/wav" if kind == "audio" else None, 500 if kind == "audio" else None,
                 identifiers[-1][1], str(uuid.uuid4()), "e"*64, fixture.NOW))
        db.execute("UPDATE access_uploads SET destination_library_id=? WHERE asset_id=101", (fixture.LIBRARY,))
        db.commit()
    # Retain a nonempty, valid V1 deletion history before migrating. This is
    # a generated original erased through the ordinary owner-authorized API.
    with _connection(primary, journal) as db:
        Annotations(AccessService(db, clock=lambda: fixture.NOW)).delete_original(
            fixture.TOKEN, fixture.LIBRARY, 101, *identifiers[-1])
    _require(journal.head()[1] == 1, "seed_history_missing")
    return identifiers[:2]


def _backup(source, target):
    # Journals intentionally have no Alembic version table. Compare their whole
    # logical contents as well as primary revision rows when present.
    fixture._create_file(target)
    with closing(fixture._db(source)) as src, closing(fixture._db(target)) as dst:
        src.backup(dst)
        has_version = src.execute("SELECT 1 FROM sqlite_master WHERE name='alembic_version'").fetchone()
        versions_equal = not has_version or src.execute("SELECT * FROM alembic_version").fetchall() == dst.execute("SELECT * FROM alembic_version").fetchall()
    if not has_version:
        # The journal upgrade controller deliberately demands an exact byte
        # copy, not only SQLite backup equivalence (backup changes its header).
        with target.open("wb") as stream:
            stream.write(source.read_bytes()); stream.flush(); os.fsync(stream.fileno())
    _require(versions_equal and fixture._snapshot(source) == fixture._snapshot(target), "backup_mismatch")
    return hashlib.sha256(target.read_bytes()).hexdigest()


def _paired_restore(primary, journal_path, target_primary, target_journal, namespace):
    _backup(primary, target_primary)
    _backup(journal_path, target_journal)
    restored = OriginalDeletionJournal(target_journal, namespace)
    with _connection(target_primary, restored) as db:
        restored.assert_current(db)


def _seed_gallery(primary):
    with _connection(primary) as db:
        db.execute("UPDATE assets SET perceptual_hash=? WHERE id=101", ("0"*16,))
        for ident in (103, *range(200, 213)):
            db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at,perceptual_hash)
                VALUES(?,?,?,'active','image/jpeg',?,?)''',
                (ident, f"generated-not-a-media-file-{ident}", hashlib.sha256(str(ident).encode()).hexdigest(),
                 "2026-01-01 10:00:30" if ident == 103 else "2026-02-01 12:00:00",
                 "0"*16 if ident == 103 else None))
            db.execute("INSERT INTO access_asset_libraries VALUES(?,?)", (ident, fixture.LIBRARY))
        db.commit()


def _gallery_lifecycle(primary, journal):
    def connect():
        return _connection(primary, journal)
    def domain(db):
        return LibraryPhotoStacks(AccessService(db, clock=lambda: fixture.NOW))
    def page(token=fixture.TOKEN, number=2):
        with connect() as db:
            return domain(db).gallery(token, fixture.LIBRARY, page=number)
    def group(token=fixture.TOKEN):
        return page(token)["photo_stacks"]["groups"][0]
    def choose(**choice):
        envelope = page()["photo_stacks"]
        body = {"index_revision": envelope["index_revision"], "revision": str(envelope["preference_revision"]),
                "group_id": "101", "cover_asset_id": "", "separate_asset_id": "", "reset": "0", **choice}
        with connect() as db:
            domain(db).update(fixture.TOKEN, fixture.LIBRARY, body)
        return body
    def refresh():
        report = worker_host.execute_once(primary, journal.path, journal.namespace,
            (fixture.LIBRARY,), primary.parent/'refresh.stop')
        _require(report['status'] == 'completed', 'host_sweep_not_completed')
        return report['results']
    _require(refresh()[0]["status"] == "updated", "initial_index_failed")
    pages = [page(number=1), page()]
    ids = [a["id"] for p in pages for a in p["items"]]
    _require(all(p["total"] == 15 for p in pages) and len(ids) == len(set(ids)) == 16
             and not pages[0]["photo_stacks"]["groups"] and group()["count"] == 2, "cross_page_failed")
    stale = choose(cover_asset_id="101")
    _require(group()["cover_asset_id"] == "101" and group(fixture.VIEWER_TOKEN)["cover_asset_id"] == "103",
             "private_cover_failed")
    with connect() as db:
        try:
            domain(db).update(fixture.TOKEN, fixture.LIBRARY, stale)
        except TransportError as error:
            _require(error.status == 409, "wrong_preference_conflict")
        else:
            raise RuntimeError("synthetic_stale_preference_accepted")
    _require(refresh()[0]["status"] == "unchanged", "noop_changed_index")
    with connect() as db:
        db.execute('''INSERT INTO assets(id,path,hash_sha256,status,mime,taken_at,perceptual_hash)
            VALUES(104,'generated-not-a-media-file-104',?,'active','image/jpeg','2026-01-01 10:00:45',?)''', ("f"*64, "0"*16))
        db.execute("INSERT INTO access_asset_libraries VALUES(104,?)", (fixture.LIBRARY,))
        task = db.execute("INSERT INTO tasks(type,state,payload_json) VALUES('phash','pending','{\"asset_id\":104}')").lastrowid
        db.commit()
    _require(page()["total"] == 16 and group()["count"] == 2, "new_unindexed_asset_hidden")
    _require(refresh()[0]["status"] == "waiting", "runnable_hash_not_waited")
    with connect() as db:
        db.execute("UPDATE tasks SET state='failed',retry_count=2,last_error='synthetic retained failure' WHERE id=?", (task,))
        db.commit()
    _require(refresh()[0]["status"] == "updated" and group()["count"] == 3
             and group()["cover_asset_id"] == "101", "refresh_lost_choice")
    choose(separate_asset_id="101")
    _require(group()["id"] == "101" and set(group()["asset_ids"]) == {"103", "104"}
             and group(fixture.VIEWER_TOKEN)["count"] == 3, "private_separation_failed")
    choose(group_id="", reset="1")
    _require(group()["count"] == 3, "reset_failed")
    with connect() as db:
        db.execute("UPDATE assets SET perceptual_hash=? WHERE id=101", ("f"*16,)); db.commit()
    _require(page()["photo_stacks"]["groups"] == [] and page()["total"] == 17, "stale_group_hid_originals")
    with connect() as db:
        db.execute("UPDATE assets SET perceptual_hash=? WHERE id=101", ("0"*16,))
        db.execute("UPDATE access_memberships SET status='revoked',revision=revision+1 WHERE account_id=?", (fixture.VIEWER,))
        db.commit()
    try:
        page(fixture.VIEWER_TOKEN)
    except AccessDenied:
        pass
    else:
        raise RuntimeError("synthetic_revoked_read_allowed")
    with connect() as db:
        _require(db.execute("SELECT state,retry_count,last_error FROM tasks WHERE id=?", (task,)).fetchone()
                 == ("failed", 2, "synthetic retained failure"), "failure_history_changed")


def _report(native):
    return {"status": "passed", "synthetic_only": True, "source_revision": FROM,
            "revision": REVISION, "cases": list(CASES), "native_windows": native,
            "production_database_opened": False, "family_media_opened": False,
            "models_loaded": False, "production_services_changed": False, "production_tasks_changed": False,
            "production_worker_started": False, "synthetic_worker_exercised": True,
            "deletion_records_before_upgrade": 1, "paired_restore_replay_exercised": False,
            "power_loss_qualified": False}


def run(output):
    target = Path(output)
    _validate_output(target)
    target.mkdir(mode=0o700)
    require_private_directory(target)
    phase = "seed"
    try:
        primary, journal_path = target/"primary.sqlite", target/"journal.sqlite"
        fixture._seed(primary, revision=FROM)
        namespace = str(uuid.uuid4())
        journal = OriginalDeletionJournal.initialize(journal_path, namespace)
        originals = _seed_originals(primary, journal)
        before = fixture._snapshot(primary)
        backup_hashes = {}
        for source, name in ((primary, "a0-backup.sqlite"), (journal_path, "v1-backup.sqlite")):
            backup_hashes[name] = _backup(source, target/name)
        head, journal_bytes = journal.head(), journal_path.read_bytes()
        phase = "migration"
        try:
            _migrate(primary, REVISION, interrupt=True)
        except RuntimeError as error:
            if str(error) != "synthetic_f2_interruption":
                raise
        else:
            raise RuntimeError("synthetic_interruption_not_reached")
        _require(fixture._snapshot(primary) == before and fixture._revision(primary) == [(FROM,)], "migration_rollback_failed")
        budget = full.Budget(128*1024**2, 120)
        with full.read_source(primary, budget, offline=True) as source:
            digest = full.fingerprint(source, full.schema(source), budget)[0]
        applied = stack_upgrade.apply(primary, target/'a0-backup.sqlite', journal_path,
            target/'v1-backup.sqlite', digest, *head, hashlib.sha256(journal_bytes).hexdigest(),
            budget, execute=True, all_writers_stopped=True, from_revision=FROM)
        _require(applied['applied'] and applied['new_tables_created'] == 13
                 and not applied['journal_format_upgrade_required'] and not applied['journal_upgrade_performed'],
                 'guarded_schema_application_failed')
        after = fixture._snapshot(primary)
        _require(set(after[1]) - set(before[1]) == set(group_upgrade._additions(FROM)) | set(TABLES), "unexpected_migration_tables")
        _require(_preserved(before, after) and fixture._revision(primary) == [(REVISION,)]
                 and journal.head() == head and journal_path.read_bytes() == journal_bytes, "migration_preservation_failed")
        edge = target/"e7-edge.sqlite"
        fixture._seed(edge, revision=PARENT)
        edge_before = fixture._snapshot(edge)
        _migrate(edge, REVISION)
        objects, rows = fixture._snapshot(edge)
        _require(([x for x in objects if x[2] not in TABLES], {k:v for k,v in rows.items() if k not in TABLES}) == edge_before
                 and all(rows[name] == [] for name in TABLES), "e7_additive_edge_failed")
        phase = "journal_and_restore"
        _backup(primary, target/"f2-before-journal.sqlite")
        result = journal_upgrade.qualify(primary, target/"f2-before-journal.sqlite", journal_path,
            target/"v1-backup.sqlite", *head, full.Budget(64*1024**2, 60), execute=True, all_writers_stopped=True)
        _require(result["status"] == "upgraded" and result["primary_unchanged"] and journal.head() == head, "journal_upgrade_failed")
        _paired_restore(target/"a0-backup.sqlite", target/"v1-backup.sqlite",
                        target/"a0-restored.sqlite", target/"v1-restored.sqlite", namespace)
        phase = "gallery"
        _seed_gallery(primary)
        _gallery_lifecycle(primary, journal)
        for source, name in ((primary, "f2-backup.sqlite"), (journal_path, "v2-backup.sqlite")):
            backup_hashes[name] = _backup(source, target/name)
        _paired_restore(target/"f2-backup.sqlite", target/"v2-backup.sqlite",
                        target/"f2-restored.sqlite", target/"v2-restored.sqlite", namespace)
        phase = "history_fences"
        with _connection(primary) as db:
            try:
                rebuild_photo_stack_index(db, fixture.LIBRARY, expected_generation=None)
            except ValueError as error:
                _require(str(error) == "deletion_history_guard_required", "wrong_missing_guard_refusal")
            else:
                raise RuntimeError("synthetic_missing_history_accepted")
        # Advance actual generated history using the production erasure path.
        # The earlier backup must then be refused with the newer journal.
        _backup(primary, target/"stale-restored.sqlite")
        with _connection(primary, journal) as db:
            Annotations(AccessService(db, clock=lambda: fixture.NOW)).delete_original(
                fixture.TOKEN, fixture.LIBRARY, 101, *originals[0])
        stale_before = fixture._snapshot(target/"stale-restored.sqlite")
        with _connection(target/"stale-restored.sqlite", journal) as db:
            generation = db.execute("SELECT generation FROM access_photo_stack_indexes").fetchone()[0]
            try:
                rebuild_photo_stack_index(db, fixture.LIBRARY, expected_generation=generation)
            except OriginalDeletionError:
                pass
            else:
                raise RuntimeError("synthetic_stale_history_accepted")
        _require(fixture._snapshot(target/"stale-restored.sqlite") == stale_before, "stale_refusal_mutated")
        phase = "downgrade"
        restored = target/"f2-restored.sqlite"
        saved = fixture._snapshot(restored)
        try:
            _migrate(restored, PARENT, down=True)
        except RuntimeError as error:
            _require(str(error) == "Photo stack records require reviewed offline backup restoration", "wrong_downgrade_refusal")
        else:
            raise RuntimeError("synthetic_populated_downgrade_accepted")
        _require(fixture._snapshot(restored) == saved and fixture._revision(restored) == [(REVISION,)], "downgrade_refusal_mutated")
        _require(all(hashlib.sha256((target/name).read_bytes()).hexdigest() == digest
                     for name, digest in backup_hashes.items()), "backup_bytes_changed")
        phase = "report"
        report = _report(os.name == "nt")
        fixture._write_json(target/"qualification-report.json", report)
        return report
    except Exception as error:
        try:
            fixture._write_json(target/"qualification-failure.json", {"status": "failed", "synthetic_only": True,
                "phase": phase, "exception_class": type(error).__name__ if type(error).__name__ in
                {"OSError", "ValueError", "RuntimeError", "OperationalError", "IntegrityError"} else "Exception"})
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
    program = ("import runpy\n" + f"runpy.run_path({str(Path(__file__).resolve())!r},run_name='generated_stack_rehearsal')['run']({str(target)!r})\n")
    code = run_bounded(WindowsAPI(), executable, [executable, "-I", "-B", "-c", program],
        environment, str(target.parent), timeout_seconds=240, memory_limit=2*1024**3,
        process_limit=8, minimum_free_ram=8*1024**3)
    if code != 0:
        raise CheckRefused("qualification_child_failed")
    path = target/"qualification-report.json"
    require_private_file(path)
    with path.open("rb") as stream:
        raw = stream.read(8193)
    if not 0 < len(raw) <= 8192:
        raise CheckRefused("qualification_report_unavailable")
    value = json.loads(raw)
    expected = _report(True)
    if type(value) is not dict or value != expected or any(type(value.get(k)) is not type(v) for k,v in expected.items()):
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

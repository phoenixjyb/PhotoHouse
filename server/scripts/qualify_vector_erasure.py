"""Source-only synthetic qualification for durable vector erasure."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import struct
import subprocess
import sys
import uuid
import zlib

SERVER = Path(__file__).resolve().parents[1]
BACKEND = SERVER / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
if str(SERVER / "scripts") not in sys.path:
    sys.path.insert(0, str(SERVER / "scripts"))

from app.access.asset_tombstones import apply_asset_tombstone, prepare_asset_tombstone
from app.access.original_deletions import OriginalDeletionJournal
from app.access.private_storage import require_private_directory, require_private_file
from app.access.visual_candidates import VectorSpaceIdentity, canonical_vector_checksum
from app.access.visual_vector_artifacts import identity_sha256
from app.access.visual_vector_erasure import (VectorErasureCatalog, VectorErasureRefused,
    VectorErasureStore, create_visual_erasure_schema)
from app.access.visual_vector_publication import create_visual_publication_schema
from app.access.visual_vector_schema import create_visual_vector_schema

NOW = 2_000_000_000
LIBRARY = "qualification-library"


def _png_chunk(kind, payload):
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xffffffff)


SOURCE = (b"\x89PNG\r\n\x1a\n" +
          _png_chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 6, 0, 0, 0)) +
          _png_chunk(b"IDAT", zlib.compress(b"\x00\x20\x40\x60\xff")) +
          _png_chunk(b"IEND", b""))
SOURCE_SHA = hashlib.sha256(SOURCE).hexdigest()
IDENTITY = VectorSpaceIdentity("a" * 64, "b" * 64, "qualification-space", "v1", 2, "unit_l2")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _npy():
    header = repr({"descr": "<f4", "fortran_order": False, "shape": (2,)}).encode("ascii")
    header += b" " * (-(10 + len(header) + 1) % 16) + b"\n"
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header + struct.pack("<2f", 1.0, 0.0)


def _private_dir(path):
    path.mkdir(mode=0o700)
    if os.name != "nt":
        path.chmod(0o700)
    require_private_directory(path)


def _primary_schema(db):
    db.executescript("""
        CREATE TABLE assets(id INTEGER PRIMARY KEY,path TEXT NOT NULL,status TEXT,hash_sha256 TEXT NOT NULL,file_size INTEGER NOT NULL,mime TEXT NOT NULL);
        CREATE TABLE access_libraries(id TEXT PRIMARY KEY,state TEXT NOT NULL);
        INSERT INTO access_libraries VALUES('qualification-library','active');
        CREATE TABLE access_asset_libraries(asset_id INTEGER PRIMARY KEY REFERENCES assets(id),library_id TEXT NOT NULL REFERENCES access_libraries(id));
        CREATE TABLE access_upload_annotations(id TEXT PRIMARY KEY);
        CREATE TABLE access_memory_contributions(id TEXT PRIMARY KEY);
        CREATE TABLE access_uploads(asset_id INTEGER NOT NULL,state TEXT NOT NULL,sha256 TEXT NOT NULL,bytes INTEGER NOT NULL);
        CREATE TABLE access_original_deletion_state(id INTEGER PRIMARY KEY,namespace TEXT NOT NULL,applied_seq INTEGER NOT NULL,applied_digest TEXT NOT NULL);
    """)


def _record(asset_id):
    raw = _npy()
    ident = identity_sha256(IDENTITY)
    record_id = _sha(f"qualification-asset-{asset_id}".encode("ascii"))
    return ({"record_id": record_id, "asset_id": str(asset_id), "source_sha256": SOURCE_SHA,
        "model_name": "synthetic-model", "artifact_sha256": IDENTITY.artifact_sha256,
        "preprocessing_sha256": IDENTITY.preprocessing_sha256, "vector_space_id": IDENTITY.vector_space_id,
        "model_version": IDENTITY.model_version, "dimension": IDENTITY.dimension,
        "normalization": IDENTITY.normalization, "identity_sha256": ident,
        "relative_path": f"image-vectors/{ident}/{record_id}.npy", "file_sha256": _sha(raw),
        "component_sha256": canonical_vector_checksum((1.0, 0.0)), "created_at": NOW, "status": "ready"}, raw)


class _Fixture:
    def __init__(self, directory, metadata=True):
        self.directory = directory
        _private_dir(directory)
        self.primary_path, self.journal_path = directory / "primary.sqlite", directory / "deletions.sqlite"
        self.source_path, self.vector_root = directory / "synthetic-original.png", directory / "vectors"
        _private_dir(self.vector_root)
        self.source_path.write_bytes(SOURCE)
        self.namespace = str(uuid.uuid4())
        self.db = sqlite3.connect(self.primary_path)
        for pragma in ("PRAGMA foreign_keys=ON", "PRAGMA secure_delete=ON", "PRAGMA synchronous=FULL"):
            self.db.execute(pragma)
        _primary_schema(self.db)
        create_visual_vector_schema(self.db)
        create_visual_publication_schema(self.db)
        create_visual_erasure_schema(self.db)
        self.db.execute("INSERT INTO assets VALUES(201,?,'active',?,?,?)", (str(self.source_path), SOURCE_SHA, len(SOURCE), "image/png"))
        self.db.execute("INSERT INTO access_asset_libraries VALUES(201,?)", (LIBRARY,))
        self.db.execute("INSERT INTO access_uploads VALUES(201,'assigned',?,?)", (SOURCE_SHA, len(SOURCE)))
        if metadata:
            self.add_metadata()
        self.db.commit()
        self.journal = OriginalDeletionJournal.initialize(self.journal_path, self.namespace, format_version=3)
        self.journal.bind(self.db)
        self.catalog_path = directory / "catalog"
        _private_dir(self.catalog_path)
        self.catalog = VectorErasureCatalog(private_directory=self.catalog_path)

    def add_metadata(self):
        record, raw = _record(201)
        self.final = self.vector_root / record["relative_path"]
        self.final.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.final.parent.chmod(0o700)
        self.final.write_bytes(raw)
        self.db.execute("INSERT INTO image_vector_artifacts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
            record["record_id"], 201, record["source_sha256"], record["model_name"], record["artifact_sha256"],
            record["preprocessing_sha256"], record["vector_space_id"], record["model_version"], record["dimension"],
            record["normalization"], record["identity_sha256"], record["relative_path"], record["file_sha256"],
            record["component_sha256"], record["created_at"], record["status"]))
        intent = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        self.db.execute("INSERT INTO image_vector_publications VALUES(?,?,?,?,?,?)", (
            record["record_id"], 201, _sha(record["record_id"].encode()), intent, "committed", NOW))
        self.stage = self.vector_root / "image-vectors" / ".staging" / f"{record['record_id']}.npy"
        self.stage.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            self.stage.parent.chmod(0o700)
        os.link(self.final, self.stage)

    def snapshot(self, path):
        with sqlite3.connect(path) as target:
            self.db.backup(target)

    def withdraw(self):
        self.db.execute("BEGIN IMMEDIATE")
        candidate = prepare_asset_tombstone(self.db, 201, LIBRARY, NOW)
        self.journal.append(self.db, "asset", {"id": 201, "library_id": LIBRARY,
            "asset_binding_json": candidate["asset_binding_json"]}, NOW)
        apply_asset_tombstone(self.db, candidate)
        self.db.commit()

    def store(self, db=None):
        return VectorErasureStore(self.db if db is None else db, self.vector_root, self.journal, catalog=self.catalog)


def _finish(store, job):
    for _ in range(258):
        if store.step(job):
            return
    raise RuntimeError("Synthetic erasure did not complete")


def _case_crash(root):
    f = _Fixture(root / "complete-and-crash")
    f.withdraw()
    job = f.store().prepare(201)
    archived = f.catalog.read(job)
    if len(archived["paths"]) != 2 or archived["paths"][0][1] != archived["paths"][1][1]:
        raise RuntimeError("Catalog did not preserve the complete hardlink pair")
    quarantine = f.vector_root / "image-vectors" / ".erasing" / job / "000.npy"
    code = ("import os,sqlite3,sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
        "import app.access.visual_vector_erasure as e;from app.access.original_deletions import OriginalDeletionJournal;"
        "from app.access.visual_vector_erasure import VectorErasureCatalog;"
        "d=sqlite3.connect(sys.argv[2]);d.execute('PRAGMA foreign_keys=ON');d.execute('PRAGMA synchronous=FULL');"
        "j=OriginalDeletionJournal(sys.argv[3],sys.argv[4]);c=VectorErasureCatalog(private_directory=Path(sys.argv[6]));"
        "l=e.os.link;e.os.link=lambda *a,**k:(l(*a,**k),os._exit(47));"
        "e.VectorErasureStore(d,Path(sys.argv[5]),j,catalog=c).step(sys.argv[7])")
    proc = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(BACKEND), str(f.primary_path),
        str(f.journal_path), f.namespace, str(f.vector_root), str(f.catalog_path), job], capture_output=True, timeout=30)
    if proc.returncode != 47 or not f.final.exists() or not quarantine.exists() or not os.path.samefile(f.final, quarantine):
        raise RuntimeError("Synthetic process interruption did not preserve the quarantine link")
    _finish(f.store(), job)
    if f.final.exists() or f.stage.exists() or quarantine.exists():
        raise RuntimeError("Resumed synthetic cleanup left a vector path")
    if f.db.execute("SELECT count(*) FROM image_vector_erasures WHERE job_id=?", (job,)).fetchone() != (1,):
        raise RuntimeError("Synthetic cleanup job was not retained")
    if f.source_path.read_bytes() != SOURCE:
        raise RuntimeError("Synthetic original changed")
    f.db.close()


def _case_restore(root):
    f = _Fixture(root / "catalog-restore", metadata=False)
    backup = f.directory / "older-primary.sqlite"
    f.snapshot(backup)
    f.add_metadata()
    f.db.commit()
    f.withdraw()
    job = f.store().prepare(201)
    if f.catalog.read(job)["asset_id"] != 201:
        raise RuntimeError("Catalog did not archive the synthetic restore closure")
    _finish(f.store(), job)
    f.db.close()
    restored_path = f.directory / "restored-primary.sqlite"
    shutil.copyfile(backup, restored_path)
    db = sqlite3.connect(restored_path)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA synchronous=FULL")
    if f.journal.review(db)["pending_count"] != 1:
        raise RuntimeError("Older synthetic primary lacks expected pending withdrawal")
    f.journal.replay(db)
    if db.execute("SELECT status FROM assets WHERE id=201").fetchone() != ("deleted",):
        raise RuntimeError("Synthetic journal replay failed")
    f.store(db).restore(job)
    queries = [
        ("SELECT count(*) FROM image_vector_artifacts WHERE asset_id=201", (), (1,)),
        ("SELECT count(*) FROM image_vector_publications WHERE asset_id=201", (), (1,)),
        ("SELECT count(*) FROM image_vector_erasures WHERE job_id=?", (job,), (1,)),
    ]
    if any(db.execute(sql, args).fetchone() != expected for sql, args, expected in queries):
        raise RuntimeError("Catalog did not restore the complete synthetic metadata closure")
    _finish(f.store(db), job)
    db.close()
    if f.final.exists() or f.stage.exists():
        raise RuntimeError("Restored synthetic cleanup did not resume")
    if f.source_path.read_bytes() != SOURCE:
        raise RuntimeError("Synthetic original changed")


def _case_corrupt_refusal(root):
    f = _Fixture(root / "corrupt-quarantine")
    f.withdraw()
    store = f.store()
    job = store.prepare(201)
    image_dir = f.vector_root / "image-vectors"
    image_dir.mkdir(exist_ok=True)
    erasing_dir = image_dir / ".erasing"
    erasing_dir.mkdir(mode=0o700)
    qdir = erasing_dir / job
    qdir.mkdir(mode=0o700)
    if os.name != "nt":
        erasing_dir.chmod(0o700)
        qdir.chmod(0o700)
    require_private_directory(erasing_dir)
    require_private_directory(qdir)
    (qdir / "000.npy").write_bytes(b"synthetic-corrupt-quarantine")
    try:
        store.step(job)
    except VectorErasureRefused:
        pass
    else:
        raise RuntimeError("Corrupt synthetic quarantine was accepted")
    if (f.final.read_bytes() != _npy() or f.source_path.read_bytes() != SOURCE
            or (qdir / "000.npy").read_bytes() != b"synthetic-corrupt-quarantine"
            or f.db.execute("SELECT next_file FROM image_vector_erasures WHERE job_id=?", (job,)).fetchone() != (0,)):
        raise RuntimeError("Corrupt quarantine changed synthetic cleanup state")
    f.db.close()


def run(output: Path | str) -> dict:
    target = Path(output)
    if not target.is_absolute() or ".." in target.parts or target.exists() or os.path.lexists(target):
        raise ValueError("Output must be an absent absolute directory")
    require_private_directory(target.parent)
    _private_dir(target)
    _case_crash(target)
    _case_restore(target)
    _case_corrupt_refusal(target)
    report = {"source_only": True, "models_loaded": False, "services_changed": False,
        "native_windows": os.name == "nt", "power_loss_qualified": False,
        "cases_passed": ["complete_manifest_catalog_and_quarantine_link_process_recovery",
            "restore_older_primary_from_archived_closure_and_resume", "corrupt_quarantine_refused"]}
    report_path = target / "qualification-report.json"
    descriptor = os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="ascii", newline="\n") as stream:
        json.dump(report, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return report


def _bounded_report(target: Path):
    """Supervise a generated child; split out for portable controller checks."""
    if not target.is_absolute() or ".." in target.parts or target.exists() or os.path.lexists(target):
        raise ValueError("Output must be an absent absolute directory")
    require_private_directory(target.parent)
    from bounded_windows_job import CheckRefused, WindowsAPI, run_bounded
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise CheckRefused("system_root_unavailable")
    executable = str(Path(sys.executable).resolve())
    environment = {
        "PATH": str(Path(executable).parent), "SYSTEMROOT": system_root,
        "WINDIR": system_root, "TEMP": str(target.parent), "TMP": str(target.parent),
        "PHOTOHOUSE_NO_DOTENV": "1", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
        "PHOTOHOUSE_GENERATED_QUALIFICATION_CHILD": "1",
    }
    code = run_bounded(WindowsAPI(), executable,
        [executable, "-I", "-B", str(Path(__file__).resolve()), "--out", str(target), "--bounded-child"],
        environment, str(target.parent), timeout_seconds=900, memory_limit=2 * 1024**3,
        process_limit=4, minimum_free_ram=8 * 1024**3)
    if code != 0:
        raise CheckRefused("qualification_child_failed")
    report_path = target / "qualification-report.json"
    require_private_file(report_path)
    if not 0 < report_path.stat().st_size <= 8192:
        raise CheckRefused("qualification_report_unavailable")
    report = json.loads(report_path.read_text(encoding="ascii"))
    expected = {"source_only": True, "models_loaded": False, "services_changed": False,
                "native_windows": True, "power_loss_qualified": False,
                "cases_passed": ["complete_manifest_catalog_and_quarantine_link_process_recovery",
                    "restore_older_primary_from_archived_closure_and_resume", "corrupt_quarantine_refused"]}
    if (type(report) is not dict or report != expected
            or any(type(report.get(key)) is not bool for key in expected if key != "cases_passed")):
        raise CheckRefused("qualification_report_unavailable")
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="new absolute directory beneath an existing private parent")
    parser.add_argument("--bounded-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if os.name == "nt" and not args.bounded_child:
        report = _bounded_report(Path(args.out))
    else:
        if args.bounded_child and os.environ.get("PHOTOHOUSE_GENERATED_QUALIFICATION_CHILD") != "1":
            raise ValueError("Generated child marker unavailable")
        report = run(args.out)
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

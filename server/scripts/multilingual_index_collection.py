#!/usr/bin/env python3
"""Assemble immutable references to complete bounded multilingual image batches.

The default command is a no-I/O plan. Explicit assembly and inspection read
strict private inputs outside the source tree; they never load a model or write
database/provider state. The collection manifest is written last.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any

import multilingual_library_coverage as coverage


COLLECTION_SCHEMA = "photohouse.multilingual_image_index_collection.v1"
MAX_COLLECTION_ASSETS = coverage.MAX_SNAPSHOT_ASSETS
# The byte budget may split a library into many small cohorts, including the
# current household's 276 batches. Bound references by the source roster size.
MAX_BATCHES = MAX_COLLECTION_ASSETS
MAX_PRIVATE_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = MAX_PRIVATE_DOCUMENT_BYTES
MAX_STAGE_MANIFEST_BYTES = 128 * 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


class CollectionRefused(ValueError):
    """Raised when a whole collection cannot be verified safely."""


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError):
        raise CollectionRefused("collection_unavailable") from None


def _sha(value: object) -> bool:
    return type(value) is str and _SHA.fullmatch(value) is not None


def validate_roster(snapshot: object) -> dict[str, Any]:
    """Validate and canonically order the complete expected source roster.

    This is pure metadata validation; it does not open source image paths.
    """
    try:
        return coverage.validate_snapshot(snapshot)
    except Exception:
        raise CollectionRefused("collection_unavailable") from None


def roster_sha256(snapshot: object) -> str:
    return hashlib.sha256(_canonical(validate_roster(snapshot))).hexdigest()


def _eligible_sources(snapshot: dict[str, Any]) -> dict[int, dict[str, Any]]:
    plan = coverage.plan_snapshot(snapshot)
    eligible = set(plan["candidate_asset_ids"])
    return {row["asset_id"]: row for row in snapshot["assets"]
            if row["asset_id"] in eligible}


def _expected_batches(snapshot: dict[str, Any]) -> list[list[int]]:
    return [list(batch["asset_ids"]) for batch in coverage.plan_snapshot(snapshot)["batches"]]


def _strict_path(raw: object, *, filename: str | None = None) -> Path:
    if type(raw) is not str or not raw or "\x00" in raw:
        raise CollectionRefused("collection_unavailable")
    path = Path(raw)
    if not path.is_absolute() or ".." in path.parts or (filename and path.name != filename):
        raise CollectionRefused("collection_unavailable")
    source_root = Path(__file__).resolve().parents[2]
    if path.is_relative_to(source_root):
        raise CollectionRefused("collection_unavailable")
    try:
        if path.resolve(strict=True) != path:
            raise CollectionRefused("collection_unavailable")
        for parent in (*reversed(path.parents), path):
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise CollectionRefused("collection_unavailable")
        if not stat.S_ISREG(path.lstat().st_mode):
            raise CollectionRefused("collection_unavailable")
    except (OSError, ValueError):
        raise CollectionRefused("collection_unavailable") from None
    return path


def _load_private_document(path: Path) -> tuple[dict[str, Any], str]:
    """Read one stable owner-private JSON input and return its raw-file digest."""
    path = _strict_path(str(path))
    backend = str(Path(__file__).resolve().parents[1] / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from app.access.private_storage import require_private_directory, require_private_file, stable_stat_identity
    try:
        require_private_directory(path.parent)
        require_private_file(path)
        before = path.stat()
        if not 1 <= before.st_size <= MAX_PRIVATE_DOCUMENT_BYTES:
            raise CollectionRefused("collection_unavailable")
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            opened = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise CollectionRefused("collection_unavailable")
            raw = stream.read(MAX_PRIVATE_DOCUMENT_BYTES + 1)
            after = os.fstat(stream.fileno())
        require_private_file(path)
        for parent in path.parents:
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                raise CollectionRefused("collection_unavailable")
        final = path.stat()
        if (len(raw) > MAX_PRIVATE_DOCUMENT_BYTES or stable_stat_identity(before) != stable_stat_identity(opened)
                or stable_stat_identity(opened) != stable_stat_identity(after)
                or stable_stat_identity(after) != stable_stat_identity(final)
                or opened.st_ctime_ns != after.st_ctime_ns):
            raise CollectionRefused("collection_unavailable")
        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise CollectionRefused("collection_unavailable")
                result[key] = value
            return result
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                           parse_constant=lambda _x: (_ for _ in ()).throw(CollectionRefused()))
        if type(value) is not dict:
            raise CollectionRefused("collection_unavailable")
        return value, hashlib.sha256(raw).hexdigest()
    except CollectionRefused:
        raise
    except Exception:
        raise CollectionRefused("collection_unavailable") from None


def _indexer():
    # The heavyweight/application-facing verifier is loaded only for explicit
    # inspection, keeping import and plan mode free of model or file activity.
    scripts = str(Path(__file__).resolve().parent)
    backend = str(Path(__file__).resolve().parents[1] / "backend")
    for entry in (scripts, backend):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    import build_multilingual_image_index as indexer
    return indexer


def _read_batch(reference: object, *, library_id: str, source_rows: dict[int, dict[str, Any]],
                ) -> dict[str, Any]:
    if type(reference) is not dict or set(reference) != {"cohort_path", "index_path"}:
        raise CollectionRefused("collection_unavailable")
    cohort_path = _strict_path(reference["cohort_path"])
    index_path = _strict_path(reference["index_path"], filename="index.json")
    cohort, cohort_file_sha = _load_private_document(cohort_path)
    if (type(cohort) is not dict or set(cohort) != {"schema", "library_id", "reviewed", "assets"}
            or cohort["schema"] != "photohouse.multilingual_image_cohort.v1"
            or cohort["library_id"] != library_id or cohort["reviewed"] is not True
            or type(cohort["assets"]) is not list or not 1 <= len(cohort["assets"]) <= coverage.MAX_BATCH_IMAGES):
        raise CollectionRefused("collection_unavailable")
    expected_ids: list[int] = []
    seen: set[int] = set()
    for asset in cohort["assets"]:
        if (type(asset) is not dict or set(asset) != {"asset_id", "path", "sha256"}
                or type(asset["asset_id"]) is not str or not re.fullmatch(r"[1-9][0-9]{0,18}", asset["asset_id"])
                or type(asset["path"]) is not str or not _sha(asset["sha256"])):
            raise CollectionRefused("collection_unavailable")
        asset_id = int(asset["asset_id"])
        source = source_rows.get(asset_id)
        if (asset_id > coverage.MAX_SQLITE_ID or asset_id in seen or source is None
                or source["db_source_sha256"] != asset["sha256"]):
            raise CollectionRefused("collection_unavailable")
        seen.add(asset_id)
        expected_ids.append(asset_id)
    expected_cohort_digest = hashlib.sha256(_canonical({
        **cohort, "assets": [{"asset_id": item["asset_id"], "sha256": item["sha256"]}
                              for item in cohort["assets"]]})).hexdigest()
    index, index_file_sha = _load_private_document(index_path)
    try:
        inspected, records, identities = _indexer().inspect_index(
            index_path, expected_library=library_id, expected_cohort=cohort)
    except Exception:
        raise CollectionRefused("collection_unavailable") from None
    if inspected != index or index.get("cohort_sha256") != expected_cohort_digest:
        raise CollectionRefused("collection_unavailable")
    cohort_after, cohort_sha_after = _load_private_document(cohort_path)
    index_after, index_sha_after = _load_private_document(index_path)
    if (cohort_after != cohort or cohort_sha_after != cohort_file_sha
            or index_after != index or index_sha_after != index_file_sha):
        raise CollectionRefused("collection_unavailable")
    try:
        record_ids = [int(record.asset_id) for record in records]
    except (TypeError, ValueError, OverflowError):
        raise CollectionRefused("collection_unavailable") from None
    if len(record_ids) != len(expected_ids) or set(record_ids) != set(expected_ids):
        raise CollectionRefused("collection_unavailable")
    return {
        "cohort_path": str(cohort_path), "cohort_file_sha256": cohort_file_sha,
        "cohort_sha256": expected_cohort_digest, "index_path": str(index_path),
        "index_file_sha256": index_file_sha, "asset_ids": sorted(expected_ids),
        "image_identity": {key: getattr(identities["image"], key)
                           for key in identities["image"].__dataclass_fields__},
        "text_identity": {key: getattr(identities["text"], key)
                          for key in identities["text"].__dataclass_fields__},
    }


def _validate_batches(snapshot: dict[str, Any], references: object) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    if type(references) is not list or not 1 <= len(references) <= MAX_BATCHES:
        raise CollectionRefused("collection_unavailable")
    source_rows = _eligible_sources(snapshot)
    expected = _expected_batches(snapshot)
    batches = [_read_batch(ref, library_id=snapshot["library_id"], source_rows=source_rows)
               for ref in references]
    combined: list[int] = []
    seen: set[int] = set()
    image_identity = text_identity = None
    for batch in batches:
        ids = batch["asset_ids"]
        if any(asset_id in seen for asset_id in ids):
            raise CollectionRefused("collection_unavailable")
        seen.update(ids)
        combined.extend(ids)
        if image_identity is None:
            image_identity, text_identity = batch["image_identity"], batch["text_identity"]
        elif batch["image_identity"] != image_identity or batch["text_identity"] != text_identity:
            raise CollectionRefused("collection_unavailable")
    if sorted(combined) != sorted(source_rows) or sorted(map(sorted, [b["asset_ids"] for b in batches])) != sorted(map(sorted, expected)):
        raise CollectionRefused("collection_unavailable")
    return batches, image_identity, text_identity


def _collection_body(snapshot: dict[str, Any], batches: list[dict[str, Any]],
                     image_identity: dict[str, Any], text_identity: dict[str, Any]) -> dict[str, Any]:
    eligible_ids = set(_eligible_sources(snapshot))
    blocker_count = len(snapshot["assets"]) - len(eligible_ids)
    return {
        "schema": COLLECTION_SCHEMA,
        "library_id": snapshot["library_id"],
        "roster": snapshot,
        "roster_sha256": hashlib.sha256(_canonical(snapshot)).hexdigest(),
        "roster_count": len(snapshot["assets"]),
        "indexed_asset_count": sum(len(batch["asset_ids"]) for batch in batches),
        "blocked_asset_ids": [row["asset_id"] for row in snapshot["assets"]
                              if row["asset_id"] not in eligible_ids],
        "blocker_count": blocker_count,
        "candidate_coverage": True,
        "whole_library_coverage": blocker_count == 0,
        "batches": batches,
        "image_identity": image_identity,
        "text_identity": text_identity,
        "complete": True,
        "production_published": False,
        "activation_performed": False,
    }


def assemble_collection(snapshot: object, batch_references: object, output_directory: str | Path,
                        ) -> dict[str, Any]:
    """Verify all referenced batches and write one final immutable collection manifest."""
    roster = validate_roster(snapshot)
    batches, image_identity, text_identity = _validate_batches(roster, batch_references)
    from qualify_semantic_pair import output_target, write_record
    target = output_target(output_directory)
    target.mkdir(mode=0o700)
    body = _collection_body(roster, batches, image_identity, text_identity)
    if len(_canonical(body)) + 1 > MAX_MANIFEST_BYTES:
        raise CollectionRefused("collection_unavailable")
    write_record(target, "collection.json", body)
    # Re-open and verify the completed object before returning success. Keep
    # any failure artifact in place for later diagnosis.
    manifest_path = target / "collection.json"
    inspect_collection(manifest_path)
    return {"status": "private_multilingual_collection_prepared",
            "roster_count": body["roster_count"], "indexed_asset_count": body["indexed_asset_count"],
            "batch_count": len(batches), "roster_sha256": body["roster_sha256"],
            "collection_sha256": hashlib.sha256(_canonical(body) + b"\n").hexdigest(),
            "blocker_count": body["blocker_count"],
            "candidate_coverage": body["candidate_coverage"],
            "whole_library_coverage": body["whole_library_coverage"],
            "production_published": False, "activation_performed": False}


def inspect_collection(path: str | Path) -> dict[str, Any]:
    """Revalidate the complete embedded roster and every pinned existing batch."""
    path = _strict_path(str(path), filename="collection.json")
    value, _digest = _load_private_document(path)
    required = {"schema", "library_id", "roster", "roster_sha256", "roster_count",
                "indexed_asset_count", "blocked_asset_ids", "blocker_count", "candidate_coverage",
                "whole_library_coverage", "batches", "image_identity", "text_identity", "complete",
                "production_published", "activation_performed"}
    if (set(value) != required or value["schema"] != COLLECTION_SCHEMA
            or value["complete"] is not True or value["production_published"] is not False
            or value["activation_performed"] is not False):
        raise CollectionRefused("collection_unavailable")
    roster = validate_roster(value["roster"])
    if (roster["library_id"] != value["library_id"] or value["roster_count"] != len(roster["assets"])
            or value["roster_sha256"] != hashlib.sha256(_canonical(roster)).hexdigest()):
        raise CollectionRefused("collection_unavailable")
    references = [{"cohort_path": item.get("cohort_path"), "index_path": item.get("index_path")}
                  for item in value["batches"]] if type(value["batches"]) is list else None
    batches, image_identity, text_identity = _validate_batches(roster, references)
    expected = _collection_body(roster, batches, image_identity, text_identity)
    if expected != value:
        raise CollectionRefused("collection_unavailable")
    return value


def _copy_verified_vector(source: Path, destination: Path, expected_sha256: str) -> None:
    """Copy one pinned vector into a new private root, checking its bytes as copied."""
    from image_embedding_receipts import inspect_checkpoint, verify_checkpoint, _open_pinned
    from app.access.private_storage import require_private_file
    pin = inspect_checkpoint(source, expected_sha256)
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                         getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0), 0o600)
    digest = hashlib.sha256()
    try:
        with os.fdopen(descriptor, "wb") as outgoing:
            with _open_pinned(pin.path, pin.stat_identity) as incoming:
                while True:
                    chunk = incoming.read(1024 * 1024)
                    if not chunk:
                        break
                    outgoing.write(chunk)
                    digest.update(chunk)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        require_private_file(destination)
        verify_checkpoint(pin)
        if digest.hexdigest() != expected_sha256:
            raise CollectionRefused("collection_unavailable")
    except BaseException:
        # Retain partial files in this private candidate root as failure evidence.
        raise


def stage_collection_vectors(collection_path: str | Path, output_directory: str | Path,
                             ) -> dict[str, Any]:
    """Copy verified derived vectors into a new private root and emit future DB rows.

    Original images and database state are never opened. The final staging
    manifest is written only after every vector and metadata row is complete.
    """
    collection_path = _strict_path(str(collection_path), filename="collection.json")
    collection_value, initial_collection_sha = _load_private_document(collection_path)
    inspected_collection = inspect_collection(collection_path)
    if collection_value != inspected_collection:
        raise CollectionRefused("collection_unavailable")
    from dataclasses import asdict
    from qualify_semantic_pair import output_target, write_record
    from app.access.private_storage import require_private_directory

    target = output_target(output_directory)
    target.mkdir(mode=0o700)
    require_private_directory(target)
    indexer = _indexer()
    records_out: list[dict[str, Any]] = []
    copied_records: list[tuple[Any, Any]] = []
    seen: set[int] = set()
    for batch in collection_value["batches"]:
        cohort, cohort_sha = _load_private_document(Path(batch["cohort_path"]))
        index_path = _strict_path(batch["index_path"], filename="index.json")
        pinned_index, index_sha = _load_private_document(index_path)
        if cohort_sha != batch['cohort_file_sha256'] or index_sha != batch['index_file_sha256']:
            raise CollectionRefused('collection_unavailable')
        _manifest, records, identities = indexer.inspect_index(
            index_path, expected_library=collection_value["library_id"], expected_cohort=cohort)
        if _manifest != pinned_index:
            raise CollectionRefused('collection_unavailable')
        image_identity = {key: getattr(identities["image"], key)
                          for key in identities["image"].__dataclass_fields__}
        text_identity = {key: getattr(identities["text"], key)
                         for key in identities["text"].__dataclass_fields__}
        if (image_identity != collection_value["image_identity"]
                or text_identity != collection_value["text_identity"]):
            raise CollectionRefused("collection_unavailable")
        batch_root = index_path.parent
        for record in records:
            asset_id = int(record.asset_id)
            if asset_id in seen:
                raise CollectionRefused("collection_unavailable")
            seen.add(asset_id)
            destination = target / record.relative_path
            _copy_verified_vector(batch_root / record.relative_path, destination, record.file_sha256)
            row = asdict(record)
            metadata_path = destination.with_suffix(".json")
            write_record(metadata_path.parent, metadata_path.name, row)
            metadata_readback, metadata_sha = _load_private_document(metadata_path)
            if metadata_readback != row:
                raise CollectionRefused("collection_unavailable")
            records_out.append({"record": row, "metadata_sha256": metadata_sha})
            copied_records.append((record, identities["image"]))
    expected_ids = {asset_id for batch in collection_value["batches"] for asset_id in batch["asset_ids"]}
    if seen != expected_ids or len(records_out) != collection_value["indexed_asset_count"]:
        raise CollectionRefused("collection_unavailable")
    # Verify the copied bytes parse as the pinned records and remain in the
    # same canonical vector space before emitting the final staging manifest.
    from app.access.visual_candidates import VectorRecord, _canonical_components
    from app.access.visual_vector_loader import _read_vector
    for record, image_identity in copied_records:
        if not indexer.validate_artifact(record, image_identity):
            raise CollectionRefused("collection_unavailable")
        vector = _read_vector(target, record)
        if vector is None:
            raise CollectionRefused("collection_unavailable")
        _canonical_components(VectorRecord(record.asset_id, image_identity, vector,
                                           record.component_sha256), image_identity)
    # The exact original collection must still be present after every batch
    # copy and vector readback; do not rebind the staging rows to a new roster.
    final_inspection = inspect_collection(collection_path)
    pinned_collection, source_pin = _load_private_document(collection_path)
    if (final_inspection != collection_value or pinned_collection != collection_value
            or source_pin != initial_collection_sha):
        raise CollectionRefused("collection_unavailable")
    stage = {
        "schema": "photohouse.multilingual_image_index_collection_stage.v1",
        "library_id": collection_value["library_id"],
        "collection_file_sha256": source_pin,
        "roster_sha256": collection_value["roster_sha256"],
        "image_identity": collection_value["image_identity"],
        "text_identity": collection_value["text_identity"],
        "record_count": len(records_out),
        "records": records_out,
        "blocker_count": collection_value["blocker_count"],
        "candidate_coverage": collection_value["candidate_coverage"],
        "whole_library_coverage": collection_value["whole_library_coverage"],
        "complete": True,
        "production_published": False,
        "activation_performed": False,
    }
    if len(_canonical(stage)) + 1 > MAX_STAGE_MANIFEST_BYTES:
        raise CollectionRefused("collection_unavailable")
    write_record(target, "collection-stage.json", stage)
    return {"status": "private_multilingual_collection_vectors_staged",
            "record_count": len(records_out), "collection_file_sha256": source_pin,
            "staging_manifest_sha256": hashlib.sha256(_canonical(stage) + b"\n").hexdigest(),
            "blocker_count": stage["blocker_count"],
            "candidate_coverage": stage["candidate_coverage"],
            "whole_library_coverage": stage["whole_library_coverage"],
            "vector_root": str(target), "database_rows_written": False,
            "production_published": False, "activation_performed": False}


def plan() -> dict[str, Any]:
    return {"status": "multilingual_index_collection_plan", "max_roster_assets": MAX_COLLECTION_ASSETS,
            "max_batch_images": coverage.MAX_BATCH_IMAGES, "max_batches": MAX_BATCHES,
            "private_files_read": False, "models_loaded": False,
            "production_published": False, "activation_performed": False}


def run(argv=None) -> int:
    class Parser(argparse.ArgumentParser):
        def error(self, _message):
            raise CollectionRefused("collection_unavailable")
    try:
        parser = Parser(description=__doc__)
        parser.add_argument('operation', nargs='?', choices=('assemble', 'inspect', 'stage'))
        parser.add_argument('--snapshot', type=Path)
        parser.add_argument('--batch-references', type=Path)
        parser.add_argument('--collection', type=Path)
        parser.add_argument('--output-directory', type=Path)
        args = parser.parse_args(argv)
        if args.operation is None:
            if any((args.snapshot, args.batch_references, args.collection, args.output_directory)):
                raise CollectionRefused('collection_unavailable')
            result = plan()
        elif args.operation == 'assemble':
            if not args.snapshot or not args.batch_references or not args.output_directory or args.collection:
                raise CollectionRefused('collection_unavailable')
            snapshot, _snapshot_sha = _load_private_document(args.snapshot)
            references, _references_sha = _load_private_document(args.batch_references)
            if set(references) != {'batches'}:
                raise CollectionRefused('collection_unavailable')
            result = assemble_collection(snapshot, references['batches'], args.output_directory)
        else:
            if not args.collection or args.snapshot or args.batch_references:
                raise CollectionRefused('collection_unavailable')
            if args.operation == 'inspect':
                if args.output_directory:
                    raise CollectionRefused('collection_unavailable')
                value = inspect_collection(args.collection)
                result = {key: value[key] for key in ('roster_count', 'indexed_asset_count',
                    'blocker_count', 'candidate_coverage', 'whole_library_coverage',
                    'production_published', 'activation_performed')}
                result['status'] = 'private_multilingual_collection_verified'
            else:
                if not args.output_directory:
                    raise CollectionRefused('collection_unavailable')
                result = stage_collection_vectors(args.collection, args.output_directory)
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception:
        print('{"error":"multilingual_collection_unavailable"}', file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(run())

"""Optional SQLite schema contract for completed image-vector artifacts.

The contract is descriptive and has no import-time database effects. The
creation helper is intended only for isolated synthetic tests; it is not a
migration or runtime activation path.
"""
from __future__ import annotations

import re
import sqlite3


ARTIFACT_TABLE = "image_vector_artifacts"


def sqlite_visual_vector_contract() -> tuple[tuple[str, str, str], ...]:
    """Return deterministic required table, index, and trigger definitions."""
    table = f'''CREATE TABLE IF NOT EXISTS {ARTIFACT_TABLE} (
    record_id TEXT NOT NULL PRIMARY KEY
        CHECK(length(record_id)=64 AND record_id NOT GLOB '*[^0-9a-f]*'),
    asset_id INTEGER NOT NULL REFERENCES assets(id) ON DELETE RESTRICT
        CHECK(asset_id > 0),
    source_sha256 TEXT NOT NULL
        CHECK(length(source_sha256)=64 AND source_sha256 NOT GLOB '*[^0-9a-f]*'),
    model_name TEXT NOT NULL
        CHECK(length(model_name) BETWEEN 1 AND 64 AND model_name GLOB '[a-z0-9]*'
              AND model_name NOT GLOB '*[^a-z0-9._-]*'),
    artifact_sha256 TEXT NOT NULL
        CHECK(length(artifact_sha256)=64 AND artifact_sha256 NOT GLOB '*[^0-9a-f]*'),
    preprocessing_sha256 TEXT NOT NULL
        CHECK(length(preprocessing_sha256)=64 AND preprocessing_sha256 NOT GLOB '*[^0-9a-f]*'),
    vector_space_id TEXT NOT NULL
        CHECK(length(vector_space_id) BETWEEN 1 AND 64 AND vector_space_id GLOB '[a-z0-9]*'
              AND vector_space_id NOT GLOB '*[^a-z0-9._-]*'),
    model_version TEXT NOT NULL
        CHECK(length(model_version) BETWEEN 1 AND 64 AND model_version GLOB '[a-z0-9]*'
              AND model_version NOT GLOB '*[^a-z0-9._-]*'),
    dimension INTEGER NOT NULL CHECK(dimension BETWEEN 1 AND 4096),
    normalization TEXT NOT NULL CHECK(normalization='unit_l2'),
    identity_sha256 TEXT NOT NULL
        CHECK(length(identity_sha256)=64 AND identity_sha256 NOT GLOB '*[^0-9a-f]*'),
    relative_path TEXT NOT NULL
        CHECK(relative_path='image-vectors/'||identity_sha256||'/'||record_id||'.npy'),
    file_sha256 TEXT NOT NULL
        CHECK(length(file_sha256)=64 AND file_sha256 NOT GLOB '*[^0-9a-f]*'),
    component_sha256 TEXT NOT NULL
        CHECK(length(component_sha256)=64 AND component_sha256 NOT GLOB '*[^0-9a-f]*'),
    created_at INTEGER NOT NULL CHECK(created_at >= 0),
    status TEXT NOT NULL CHECK(status='ready')
)'''
    return tuple(sorted((
        ("table", ARTIFACT_TABLE, table),
        ("index", "uq_image_vector_asset_source_identity",
         f"CREATE UNIQUE INDEX IF NOT EXISTS uq_image_vector_asset_source_identity "
         f"ON {ARTIFACT_TABLE}(asset_id, source_sha256, identity_sha256)"),
        ("index", "uq_image_vector_relative_path",
         f"CREATE UNIQUE INDEX IF NOT EXISTS uq_image_vector_relative_path "
         f"ON {ARTIFACT_TABLE}(relative_path)"),
        ("trigger", "trg_image_vector_artifacts_immutable_update",
         f"CREATE TRIGGER IF NOT EXISTS trg_image_vector_artifacts_immutable_update "
         f"BEFORE UPDATE ON {ARTIFACT_TABLE} BEGIN "
         "SELECT RAISE(ABORT, 'Image vector artifact is immutable'); END"),
        ("trigger", "trg_image_vector_artifacts_immutable_delete",
         f"CREATE TRIGGER IF NOT EXISTS trg_image_vector_artifacts_immutable_delete "
         f"BEFORE DELETE ON {ARTIFACT_TABLE} BEGIN "
         "SELECT RAISE(ABORT, 'Image vector artifact is immutable'); END"),
    )))


def create_visual_vector_schema(db) -> None:
    """Create the optional contract on an explicitly supplied synthetic DB."""
    order = {"table": 0, "index": 1, "trigger": 2}
    for _kind, _name, ddl in sorted(sqlite_visual_vector_contract(), key=lambda row: order[row[0]]):
        db.execute(ddl)


def _normalized(sql: object) -> str | None:
    if type(sql) is not str:
        return None
    pieces = []
    quote = None
    pending_space = False
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote is not None:
            pieces.append(char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    pieces.append(sql[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"', "`"):
            if pending_space and pieces:
                pieces.append(" ")
            pending_space = False
            pieces.append(char)
            quote = char
        elif char.isspace():
            pending_space = True
        else:
            if pending_space and pieces:
                pieces.append(" ")
            pending_space = False
            pieces.append(char)
        index += 1
    normalized = "".join(pieces).rstrip("; ")
    return re.sub(r"^(CREATE(?: UNIQUE)? (?:TABLE|INDEX|TRIGGER)) IF NOT EXISTS ",
                  r"\1 ", normalized)


def verify_visual_vector_schema(db) -> bool:
    """Compare required SQLite objects without creating or changing any data."""
    try:
        contract = sqlite_visual_vector_contract()
        for kind, name, ddl in contract:
            row = db.execute("SELECT type, sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
            if row is None or row[0] != kind or _normalized(row[1]) != _normalized(ddl):
                return False
        expected_indexes = {name for kind, name, _ddl in contract if kind == "index"}
        actual_indexes = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
            (ARTIFACT_TABLE,),
        )}
        if actual_indexes != expected_indexes:
            return False
        expected_triggers = {name for kind, name, _ddl in contract if kind == "trigger"}
        actual_triggers = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?",
            (ARTIFACT_TABLE,),
        )}
        if actual_triggers != expected_triggers:
            return False
        return True
    except (AttributeError, sqlite3.Error, TypeError, ValueError):
        return False

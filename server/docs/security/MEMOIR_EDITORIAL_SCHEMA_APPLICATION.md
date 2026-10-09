# Offline memoir editorial schema application

The `a0c9d2e4f817` to `b1d7e4a9c230` migration adds two empty tables for
revision-bound memoir editorial snapshots and source references. It does not
backfill existing books, stories, or contributions, and it does not activate an
application feature.

The operator in `scripts/apply_memory_editorial_schema.py` reviews a direct,
offline SQLite database by default. Review requires a separate reviewed backup,
an exact 64-character logical fingerprint supplied by the operator, the exact
a0 source revision, and the expected collaboration and source-reference schema.
It compares the complete source and backup table/schema-object sets and their
logical fingerprints. SQLite sidecars are refused.

Execution also requires an independent `--all-writers-stopped` assertion. It
opens the existing database in read-write creator mode, starts an exclusive
transaction, rechecks source and backup identity and content, runs Alembic, and
verifies that the exclusive transaction remains active. It checks the two empty
tables, their model-derived indexes, foreign keys and immutable triggers, the
preserved historical data and schema objects, and SQLite integrity. Any failed
check rolls back the migration.

## Review

Provide direct local paths, explicit resource bounds, and the fingerprint
previously reviewed against the separate backup:

```sh
python scripts/apply_memory_editorial_schema.py \
  --database /direct/path/catalog.sqlite \
  --backup /direct/path/reviewed-backup.sqlite \
  --reviewed-backup-digest <64-lowercase-hex-digest> \
  --max-bytes 134217728 \
  --timeout-seconds 120
```

Review is read-only. A successful review reports `applied: false` and
`operational_quiescence_verified: false`.

## Apply

Only after the database owner has independently stopped all writers and reviewed
the backup, repeat the same command with both execution assertions:

```sh
python scripts/apply_memory_editorial_schema.py \
  --database /direct/path/catalog.sqlite \
  --backup /direct/path/reviewed-backup.sqlite \
  --reviewed-backup-digest <64-lowercase-hex-digest> \
  --max-bytes 134217728 \
  --timeout-seconds 120 \
  --execute \
  --all-writers-stopped
```

The assertion records operator-provided quiescence; the script does not inspect,
stop, or restart services or scheduled tasks. It does not create a backup,
checkpoint a journal, alter configuration, enable flags, or activate an API.
After interruption or lost output, inspect the actual revision and schema before
retrying. Do not restore or rerun based only on the process result.

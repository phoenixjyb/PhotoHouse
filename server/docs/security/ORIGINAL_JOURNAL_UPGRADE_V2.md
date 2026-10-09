# Offline original-deletion journal upgrade to version 2

Local operator controller, October 8, 2026. This is source and synthetic
qualification; native Windows execution remains a separate gate. See the
[family-note erasure contract](FAMILY_NOTE_ERASURE_V2.md) and
[replay contract](ORIGINAL_DELETION_RECOVERY.md).

## Inputs and review

The controller requires four existing, separate, direct private regular files:

1. A D1 primary database, already migrated and checked offline.
2. Its separate logically identical primary backup.
3. Its bound version 1 original-deletion journal.
4. A separate byte-identical private backup of that journal.

All inputs must have no SQLite sidecars or symbolic links. Use the paired
backup namespace, sequence and digest from the reviewed journal; do not infer
these from a primary restored without its ledger. The primary marker must match
the full journal head exactly, with no pending records. Populated original
sources are permitted; upgrading a capability does not adopt or erase them.

Run read-only review with private operator paths, for example:

```sh
python scripts/upgrade_original_deletion_journal.py \
  --database /private/primary.sqlite --backup /private/primary-backup.sqlite \
  --journal /private/deletions.sqlite --journal-backup /private/deletions-backup.sqlite \
  --namespace "$JOURNAL_NAMESPACE" --expected-sequence "$JOURNAL_SEQUENCE" \
  --expected-digest "$JOURNAL_DIGEST" --max-bytes 1073741824 --timeout-seconds 300
```

The paths are placeholders, not a Windows deployment command. The operator must
set explicit budgets suitable for the actual files. Output contains status,
counts and hashes, never source text, paths, account IDs or note IDs. A refusal
is deliberately generic; inspect storage privately without weakening checks.

## Explicit execution

Before execution, stop every writer under operation-specific authority and take
fresh matched primary and journal backups. Reuse the exact reviewed inputs and
head, adding `--execute --all-writers-stopped`. The tool does not stop services,
create backups, migrate a primary, backfill identities, alter feature flags or
publish anything. The attestation is an operator responsibility, not a process
inventory performed by the tool.

The primary is held under `BEGIN EXCLUSIVE`. File identities, private storage,
backup hashes, exact schema, integrity, foreign keys, logical fingerprint and
marker are rechecked. The final guard runs while the journal holds
`BEGIN IMMEDIATE`, before its schema change. Version 1 entries are copied into
the version 2 table without changing their digest projection, genesis, head or
primary marker. Only the external journal commits a schema change. The primary
and both backups must remain unchanged on readback.

A successful output is `upgraded`. A failure after the independent durable
journal commit is `upgraded_verification_incomplete`: keep all writers stopped,
inspect the journal and matched backups privately, and qualify the result before
starting anything. The tool never overwrites or restores files. A version 2 input
refuses rather than silently retrying or downgrading; use the ordinary read-only
journal/replay review to inspect it. Old binaries that reject D1/version 2 cannot
be used as an implicit rollback.

## Remaining qualification

Synthetic checks exercise success, refusal and failure boundaries. Native Windows
private ACLs, stopped-writer evidence, real size budgets, paired backup/restore,
compatible workers and staged binary readback remain required before live use.
The family-note erasure API and memoir editions remain default-off. Other original
source kinds and legacy unbound notes need separate provenance/erasure contracts.

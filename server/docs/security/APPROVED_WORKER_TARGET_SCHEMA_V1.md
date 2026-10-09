# Approved worker package target schema

The source-only worker package builder accepts an explicit intended qualification target:

```sh
python scripts/build_approved_worker_package.py \
  --commit <immutable-40-character-commit> \
  --schema-revision b1d7e4a9c230 \
  --out /absolute/path/to/new-workers.zip
```

The supported packaging targets are `a0c9d2e4f817` and `b1d7e4a9c230`. Omitting the option preserves the existing a0 archive metadata and byte format. The option changes only `manifest.json`'s `schema_revision`; the same fixed 21 Git blobs, source hashes and inactive/source-only flags remain in the archive. Unknown targets are rejected before archive creation. The CLI receipt reports the selected target along with the actual ZIP hash.

This metadata is the intended qualification target, not a runtime compatibility probe. It neither installs nor migrates a database, starts a worker, includes dependencies or qualifies native execution. Each worker's actual schema admission and native checks still apply. An explicit b1 synthetic canary also needs its own `--schema-revision b1d7e4a9c230`; packaging a b1 manifest does not select that canary option automatically.

Existing immutable packages and their approvals remain unchanged. In particular, the previously frozen `7427db9` worker ZIP has a0 metadata and b1-compatible source; this tooling update does not rewrite that ZIP or extend its operational authority. A future newly packaged archive requires its own fixed identity and review.

## Local verification

Focused package and canary contract tests passed **13 tests and 19 subtests** under the disposable Mac CPython3.12 test profile. These use synthetic worker bytes, temporary ZIPs, a synthetic database and mocked native processes. They verify default compatibility, explicit b1 selection, unchanged source members, deterministic archives, unknown-target refusal, CLI receipt/ZIP binding and the separate synthetic canary selector. No Windows source staging, native worker, model, real database, task or service was changed.

See [the worker canary contract](APPROVED_WORKER_CANARY_OUTPUTS_V1.md) and [the development guide](../../../docs/DEVELOPMENT.md) for source and runtime boundaries.

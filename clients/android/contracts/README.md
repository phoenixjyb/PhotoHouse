# Shared mobile contract

**Fixture wire format:** `1.0.0-fixture.1`, consuming reviewed backend commit
`87a60b475b37b1d6873cd977bcb6e7254472da7e` from `codex/backend-android-readiness`.
This is a native browsing subset of locally implemented behavior, not a deployed
service, complete backend API export or promise of production compatibility.

The coordinated backend repin adds the complete 512 KiB encoded caption-response
budget. Fields, operations and synthetic fixture bytes are unchanged; the original
`photohouse-mobile-fixture-v1` Git tag remains at its historical commit. The manifest
and its checksums identify this updated source snapshot within the same wire format.
See review and replay evidence (historical document excluded from this public export).

Start with [the behavioral contract](v1/CONTRACT.md), [OpenAPI snapshot](v1/openapi.json),
[synthetic responses](v1/fixtures.json), [client scenarios](v1/client-scenarios.json)
and [checksums/source identity](v1/manifest.json). Run:

```sh
python3 scripts/verify-contracts.py
```

The default verifier uses only Python's standard library. It checks the exact file
set/checksums, source identity, operation references and response fixtures against
the JSON Schema subset used by this snapshot. It is not a general OpenAPI validator.

The coordinator additionally replays the cases with the backend root `.venv` Python:

```sh
python scripts/verify-contracts.py --backend-root /absolute/path/to/pinned/backend-worktree
```

That optional check requires the backend's existing test dependencies. It verifies
HEAD and source checksums, imports only the synthetic security fixture harness,
creates temporary migrated SQLite/generated media, and makes in-process ASGI calls.
Network sockets, external processes, models, live settings and real data are not
used. `--record` is coordinator-only fixture maintenance; platform sessions must not
regenerate fixtures or change shared contracts to make their tests pass.

The full backend route inventory remains authoritative for all other surfaces.
Native clients implement the twelve frozen operations only; initial fixture apps
perform **zero real HTTP requests**. Missing search, albums, voice, upload, refresh,
password-reset and account-deletion operations must not be invented or routed to
legacy endpoints. A missing optional feature does not block the fixture browsing shell.

# Backend and Web

`server/` owns the protected API, browser client, primary database contracts,
portable workers and synthetic tests. It is maintained in the PhotoHouse monorepo.

## Source map

| Path | Responsibility |
| --- | --- |
| `backend/app/main.py` | Closed application factory and explicit protected composition |
| `backend/app/access/` | Authentication/membership, uploads, stories/memoirs, assistant, journals and feature/schema admission |
| `backend/app/ui/access/` | Web UI and domain/assistant controllers |
| `backend/migrations/` | Versioned primary SQLite schema; not automatically applied by startup |
| `scripts/staging_app.py` | Validated explicit runtime configuration and server composition |
| `scripts/run_approved_*` | Separate queue-scoped media workers |
| `scripts/build_staging_package.py` | Immutable source-only API packaging |
| `tests/security/`, `tests/ui/` | Generated API/contracts, Node and browser checks |

An imported module, default app or generated demo does not discover household
storage or start model services. A production installation explicitly selects
existing databases, storage, journals, provider adapters and feature flags.
See [Architecture](../docs/ARCHITECTURE.md), [Operations](../docs/OPERATIONS.md)
and [configuration examples](../config/examples/README.md).

## Local checks

From the **repository root**, after the [CPU setup](../docs/DEVELOPMENT.md#cpu-quick-start):

```sh
.venv/bin/python tools/check.py api
.venv/bin/python tools/check.py memory
.venv/bin/python tools/check.py windows-cpu
```

These are separate profiles; `api` includes the generated no-listener demo.
They use synthetic fixtures and need no family database, GPU or model weights.
Do not substitute an unrestricted historical `pytest tests/` run for the supported
profile. See the [test entry](tests/README.md) for focused examples.

Web sources live here, with optional Node/Playwright checks described in
[Web development](../docs/WEB_DEVELOPMENT.md). They are source checks, not a live
owner/member or device review. Phone/TV share the protected/domain contracts
through the [Android subtree](../clients/android/README.md).

[Project Status](../docs/PROJECT_STATUS.md) records the deployed v58 revision and
feature gates. The repository checkout, deployed API source and installed client
versions are different identities; preserve compatibility with older clients.

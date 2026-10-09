# Maintaining PhotoHouse

## Make a bounded change

1. Read `AGENTS.md`, [architecture](ARCHITECTURE.md) and the relevant module
   contract. Check the actual revision and preserve existing changes.
2. Pick a user journey or one shared contract. Use one writer per artifact;
   coordinate changes across server, Web and Android when their contract changes.
3. Keep household configuration, accounts, media, databases, model weights,
   recordings and signing keys out of Git. Use generated fixtures.
4. Run the narrow meaningful check, then the required affected development
   profile. Inspect rendered UI when visuals change. Record exact source and
   artifact hashes alongside limitations and the next delivery gate.

## Development checks

Follow [development setup](DEVELOPMENT.md). The ordinary API profile uses
Python 3.12, temporary SQLite and generated media; no model or household server.
Android uses the existing JDK 17 and SDK. The optional Web profile requires an
already installed browser toolchain and synthetic authenticated fixtures.

```sh
python tools/check.py api
python tools/check.py web
python tools/check.py android
python tools/android_test_report.py
python tools/verify_current_source.py
```

Select affected profiles rather than running model/inference tests as an
incidental side effect. Hosted CI, native provider checks and installed devices
are separate from these source checks.

## Change a schema

Keep migrations additive and preserve authored data and original-source history.
A migration operator defaults to review. Before execution, independently stop
all writers, review a fresh separate backup, verify source/target schema and
resource bounds, and authorize the concrete operation. The
[a0-to-b1 operator](../server/docs/security/MEMOIR_EDITORIAL_SCHEMA_APPLICATION.md)
checks identities, matching logical fingerprints and schema objects, uses an
exclusive transaction and verifies preserved rows, empty target tables,
foreign keys, immutable triggers and integrity before commit.

Stopping writers, creating/verifying the backup, service control and deployment
remain the operator's explicit responsibilities. An assertion flag is not proof
that the services stopped. Preserve the original-deletion journal and review
its replay contract when restoring a backup. Do not drop populated editorial
records as a rollback shortcut.

## Release an installed application

Pin source, dependencies, configuration and artifact identity. Verify server and
client compatibility, preserve the previous task action/configuration and define
rollback before requesting the specific deployment approval. Signing and OTA
publication have separate authorization and certificate-continuity checks.
Do not infer installed behavior from a copied APK or a successful HTTP response.

Assistant input records follow their retention policy; assistant recordings
remain transient. Story contributions preserve their originals until authorized
deletion. A source citation is a relationship, not ownership transfer.

## Maintain the public-source candidate

This curated monorepo records source imports and deliberate transformations.
When importing an accepted portable change, append its exact provenance and
before/after hashes to `docs/feature-source-changes.json`, then run
`tools/verify_current_source.py`. Include import dependencies and the affected
public test profile. Public-source packaging excludes Git history and private
operations receipts. The selected destination is
[phoenixjyb/PhotoHouse](https://github.com/phoenixjyb/PhotoHouse); submit reviewed
candidate changes through its pull request route. Use the private vulnerability
reporting channel in [SECURITY.md](../SECURITY.md). A local archive is not a
public publication; review the complete package contents before sharing.

Existing Gradle reports may come from an earlier or filtered run. The report
inventory counts files only; keep the executed build command, source pin and
artifact metadata with any acceptance claim. It never replaces a build result.

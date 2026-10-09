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

## Check a running installation

Keep a dated, private deployment record outside Git. Record the exact source
manifest and relevant file hashes, task action and process identity, listener,
enabled feature flags, and published client version/hash. Do not export raw
arguments, environment values, credentials, database rows or family catalogs
while collecting an inventory.

Probe the configured user-facing origin with normal certificate validation.
Match served static-file hashes to the deployed candidate. A separate tunnel
can target another service; its response does not describe the configured
WebUI or OTA feed. A task marked running and an HTTP success establish only
those observations. Authentication, authorized user journeys, provider quality,
installed client versions and actual device playback need their own checks.

Compare that record with the current source and roadmap before preparing a
release. Downloaded model weights are an installed artifact, not an enabled
provider; a successful OTA manifest read is publication evidence, not proof
that a device installed that APK. An audit does not authorize restarts,
scheduled-task changes, publication or model inference.

For idle or failed media workers, follow the
[terminal diagnostics contract](../server/docs/security/APPROVED_WORKER_DIAGNOSTICS_V1.md).
Keep scheduler exit codes separate from current preflight results. Inspect the
installed default mode before running it: embedding preflight can execute a
model child. Capture schema metadata using the selected existing file and a
proper SQLite read-only URI; do not create a database to diagnose one.

The API staging package's `migration_revision` records its included migration
head. Runtime admission uses the selected database's actual revision and
revision-specific table guards; it does not apply migrations. A metadata-only
story picker can run at a supported older schema with generation, editorial and
edition features off. Qualify that exact source/database combination before a
switch; do not migrate only to match a package label. A phone OTA also requires
a version code above the currently published code and the established signer.

## Maintain public source

New product changes belong in this monorepo. Follow the
[repository transition](REPOSITORY_TRANSITION.md) for remaining legacy imports
and preservation gates; do not develop duplicate features in both repositories.

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

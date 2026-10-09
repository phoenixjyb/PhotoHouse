# One development repository

PhotoHouse development now belongs in
[phoenixjyb/PhotoHouse](https://github.com/phoenixjyb/PhotoHouse).
The reviewed initial import merged through
[PR #1](https://github.com/phoenixjyb/PhotoHouse/pull/1) at
`3140f1729872f689a276dcf8ecbfc0b9777c456f`.
Its source checks passed 674 API tests and 352 subtests, 54 tooling tests,
the generated-data demo, and 773 Android JVM tests with lint and unconfigured
phone/TV debug builds. This records source qualification, not an installed
application or model-quality result.

## Where changes belong

| Work | Development home |
|---|---|
| API, Web, database contracts and portable workers | `server/` |
| Android phone, TV and shared Kotlin modules | `clients/android/android/` |
| Shared Android contracts and client documentation | `clients/android/contracts/` and `clients/android/docs/` |
| Contributor tooling, architecture and roadmap | `tools/` and `docs/` |
| Household configuration, credentials, signing keys and operation receipts | Private operator storage outside this repository |
| Optional inference implementations and model installations | Separate provider repositories and the runtime host |

Use one feature branch and pull request for changes spanning server and clients.
Run the affected profiles in [DEVELOPMENT.md](DEVELOPMENT.md), append reviewed
file provenance to `docs/feature-source-changes.json`, and preserve compatibility
with installed clients. Public CI checks source; it does not authorize or perform
household deployment, signing, publication or database changes.

## Previous application repositories

The former `vlmPhotoHouse` backend/Web repository and
`mobileAppForPhotoHouse` client repository are retained legacy references.
Their histories contain earlier source and acceptance records, and the curated
import deliberately excludes private operations and some unsupported source.
An import is therefore not evidence that every old file is redundant.

New product work starts here. A remaining portable change from a legacy
repository is reviewed and imported as a bounded diff with its source revision,
dependencies, privacy/license checks, provenance record and meaningful tests.
Do not merge the old Git histories into the public repository or make parallel
feature changes in both repositories. Keep household-specific configuration
private, and pin deployments to an explicit monorepo revision and artifact.

## Retirement gates

The October 9 source comparison identified these concrete preservation items:

- The legacy backend contains D1 original family-note identity, permanent
  erasure, deletion-journal upgrade and schema application code. The public
  baseline has ordinary story soft removal and separate memoir-contribution
  deletion contracts; those do not provide the D1 family-note erasure route.
  Import and qualify its dependency/schema/recovery closure as a separate slice.
- The legacy Android checkout contains a process-memory conversation-navigation
  helper and test absent from the public baseline. Review the behavior and its
  dependent store before importing or explicitly superseding it.
- Windows launchers, supervisors, worker packages and data-dependent repair
  utilities need individual disposition and an operator owner. Preserve the
  private originals while reviewing portable replacements.
- Neither application baseline contains tracked Swift/Xcode/iOS source. Any
  future iOS development needs an identified source owner and separate import
  decision; the Android import does not establish iOS coverage.

1. Record the retained legacy branch/commit and any local-only work.
2. Classify unmatched source as imported, intentionally excluded, separately
   maintained, or still awaiting review. Preserve unsupported client work.
3. Keep release/signing continuity, rollback artifacts, private operations
   records and original-deletion recovery evidence accessible outside public Git.
4. Qualify the monorepo release/package path before retiring a legacy release
   path. Source CI alone does not establish Windows or device acceptance.
5. Only then archive an old remote or remove a clean, inactive checkout with
   the owner's authority and a fresh preservation check.

No old repository, remote, original media or runtime data is removed by this
transition. Provider repositories such as `vlmCaptionModels` and `LVFace` keep
their separate installation and licensing lifecycles.

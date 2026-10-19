# Receipt-selected captions: native offline qualification

## Qualified source

Windows qualification passed on **October 18, 2026 (Asia/Shanghai)** for source
`d615583a2a2c98be3daf47e82dfab68fa3186b77`; implementation commit `2838b9c`.
The immutable source-only archive contains **247 files / 4,394,387 bytes**, SHA-256
`c3416940fe5d3343b0064f3fad11eaa580c0c4f1bd5941a0c78b9fa32aa4405d`.
Dependencies, private configuration, models and family media are not in it.

The earlier source candidate staged successfully but refused before creating its
synthetic database because an implicit Job query observed a different Job. Its
candidate files, one-shot claims and failure evidence were retained. It was not
replayed. The revised package was staged into a new private candidate directory,
and all archive/source hashes and private-file access checks passed.

## Native checks

Two process trees ran serially. Both used a **2 GiB Job memory limit**, **eight
processes** and an **8 GiB available-RAM admission floor**:

| Step | Maximum time | Outcome |
| --- | --- | --- |
| Job proof canary; no database/media access | 10 seconds | Passed: actual membership, flags `0x2208`, 2 GiB, eight processes |
| Generated-image / database / mock-HTTP qualification | 5 minutes | Passed: all ten cases |

The supervisor retained its non-inheritable query-only Job handle. The child
validated the supervisor's PID/creation identity, obtained a temporary query-only
duplicate, checked actual Job membership and limits, and closed temporary handles
before database work. No query handle was inherited during Python startup.

The ten fixture cases verified:

1. Metadata inspection did not claim work.
2. A generated PNG caption, finished task and completion receipt committed together.
3. A concurrent family description was preserved.
4. Uploader revocation discarded the generated result.
5. A provider failure retained a fixed error code and bounded retry backoff.
6. Invalid bilingual policy output did not publish.
7. Model identity drift did not publish.
8. An unrelated failed thumbnail task remained unchanged.
9. Normal processing preserved the bound deletion journal.
10. A journal advance followed by primary rollback made the stale store unavailable.

The fixture used six generated PNGs and an in-process mock HTTP transport.
Original fixture bytes and completion receipts were independently checked. The
final stale-journal case intentionally leaves only its disposable fixture stale.

## Source and service acceptance

The matching [source CI run](https://github.com/phoenixjyb/PhotoHouse/actions/runs/39080458709)
passed all five jobs: API, Windows CPU, Windows private readers, Web browser and
Android. Its API suite reported **2,324 passed, one skipped and 1,967 subtests**.
The scoped local cohort separately passed **132 tests / 30 subtests**. Five
private-controller fixture tests, native PowerShell parsing and a fresh extracted
package's ten portable cases also passed.

Independent pre/postflight readback matched the protected API task/action,
entry/configuration hashes and both OTA feed pointers. This operation opened no
production database or family media, loaded no model, sent no provider inference
request and changed no service, scheduled task or OTA publication.

This qualifies the scoped worker's native offline path. It does not recover the
caption model service, replace an installed worker, process real released tasks,
merge the source, or establish caption quality for the family. Those remain
separate delivery and acceptance steps; keep the legacy broad worker stopped.

See the [worker contract](../server/docs/security/RELEASED_CAPTION_WORKER.md) and
[upload journal context](UPLOAD_REVIEW_JOURNAL_CONTEXT.md).

A later, separately authorized [provider and live-batch operation](CAPTION_PROVIDER_RECOVERY_2026-10-18.md)
passed the actual model canary and completed all 17 selected captions. That record
contains its distinct resource, original/preview and completion-receipt evidence.

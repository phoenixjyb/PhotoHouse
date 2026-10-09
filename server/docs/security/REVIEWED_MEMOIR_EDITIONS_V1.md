# Reviewed memoir editions v1

## Delivery state

This is a default-off source feature after the b1 editorial foundation. Its
additive Alembic revision is `c2e6b8a1d490`, following `b1d7e4a9c230`. Migration
tests use disposable SQLite files; they do not qualify a Windows migration or
the existing live database. No provider runs during review or adoption.

`memory_editions_enabled` is a separate exact boolean, false when omitted from
the application or staging configuration. Enabling it requires collaboration
and a healthy, separately configured original-deletion journal. Generation may
stay disabled: an existing, still-current ready proposal can be adopted without
starting a model. Ordinary book reading and the existing capability DTO retain
their contracts.

## Protected routes

All routes require the authenticated current library and authorization to every
child story and media item. Cookie requests retain same-origin and CSRF checks.

| Method | Path below `/memory-community/v1/books/{book_id}` | Result |
| --- | --- | --- |
| GET | `/edition-capabilities` | Exact v1 `enabled` and `can_save` booleans; no manuscript |
| GET | `/editions/proposals/{job_id}` | Current editor's private, ready narrative job and source bindings |
| POST | `/editions` | Explicitly reviewed, atomic manuscript save; content-free receipt |
| GET | `/editions?page=1` | Eight current-authorized metadata receipts; no manuscript |
| GET | `/editions/{edition_id}` | Freshly authorized manuscript or a null-content invalidation state |

The proposal envelope binds the book revision, ordered child revisions, job ID,
result digest, neutral source fingerprint and context profile. Saving accepts
exact fields: `version`, `revision`, `mutation_id`, `job_id`,
`job_result_sha256`, `source_fingerprint`, `children`, `manuscript`, `reviewed`.
`reviewed` must independently be true. The manuscript keeps version 1, title,
ordered chapters, questions and `needs_review=true`. The job's context profile
comes from authorized storage, not an untrusted save field.

Request bodies are bounded to 128 KiB UTF-8 JSON, require
`Content-Type: application/json`, reject content encoding, duplicate fields and
noncanonical lengths, and have a ten-second intake deadline. Manuscripts and
model context retain their existing chapter, source and 64 KiB limits. A larger
memoir needs an explicitly smaller scope.

## Persistence and deletion

The migration creates only `access_memory_book_editions` and
`access_memory_book_edition_sources`; it does not backfill or alter originals,
manual story/book revisions, editorial snapshots or job retention. Immutable
triggers allow only one-way invalidation with manuscript content nulled. An
empty downgrade drops these two tables; any edition or source row, including
an invalidated edition, refuses downgrade and requires reviewed backup recovery.

Saving verifies the actor-owned ready job and every current dependency, then
stores the edited manuscript and the complete prompt provenance atomically.
Uncited prompt inputs remain dependencies. Private job fingerprints remain
unchanged; saved editions use a separate principal-neutral source fingerprint.

The same actor and identical mutation request receive the original receipt even
after the job expires or an edition is invalidated. Changed content with that
mutation ID conflicts. Receipt replay cannot restore erased prose. Reading is a
separate fresh authorization and source check; `source_changed` and
`source_invalidated` contain `manuscript: null`.

Memory-contribution owner deletion and journal restore replay scrub the complete
manuscript of every linked historical edition, including editions that did not
cite the contribution. A new deletion-journal bootstrap at C2 requires exact
edition table/index/trigger DDL and empty edition/source tables before binding;
an existing populated installation needs its already-bound journal.

**Activation limitation:** physical purge is currently integrated only for linked
memory contributions. Asset, caption, AI-observation, manual asset-family-story
evidence and upload-annotation deletion pointers are not all journal-bound edition
dependencies. Source-fingerprint withholding alone does not physically erase old
prose. Keep edition activation off until the relevant deletion types and paired
backup/replay workflow are qualified. This source feature grants no deployment,
worker restart, model execution or TV publication authority.

## Qualification boundaries

Source checks cover the real additive migration, exact installed schema,
authorization, private proposal access, reviewed save, identical retries,
changed sources, retention independence and contribution erasure. Source worker
allowlists include C2 separately from Windows worker acceptance. Package builders
include the new import closure and revision marker; an older b1 artifact retains
its original identity and evidence.

Remaining delivery work includes the bounded C2 operator/rehearsal, compatible
Windows worker canaries, native restore evidence, supported-source purge coverage,
client reader/editor completion and family/device acceptance. No synthetic pass
is a live-service or physical-device result.

## Evidence boundary

The source revision and its focused checks are recorded as source-repository evidence. They do not qualify this curated candidate until its checks are run against the candidate tree. Emulator or browser fixture results remain test evidence; they do not establish live-service, signed-package, physical-device or family acceptance. No live database migration, model/provider run, service deployment, package signing or publication is authorized by this source note.

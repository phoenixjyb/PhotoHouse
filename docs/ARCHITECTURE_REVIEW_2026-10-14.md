# Architecture review — October 14, 2026

Reviewed local source `86a154e`, maintained contracts, v58 delivery receipts and
read-only runtime flags/tasks. This review changes documentation, not runtime,
models, schema, original media or public GitHub state. Remote CI could not be
refreshed. [Project Status](PROJECT_STATUS.md) contains the scoped observations.

## Architecture to keep

The protected application is the central authority for membership, library/source
binding, revision, idempotence and reviewed effects. Clients own presentation,
foreground capture/playback and cancellation. Queue workers and model services
remain separate processes with their own resource and identity contracts. This
supports a modular product server with replaceable compute boundaries.

Original contributions, transcripts, polish/tags, proposals and adopted stories
have distinct provenance. The primary database, deletion journal, troubleshooting
journal and private conversation store are separate state domains. Explicit
configuration/admission, fail-closed paths and post-provider revalidation are
useful existing boundaries; preserve them while improving UX.

## Findings and concrete next work

| Finding | Evidence / impact | Action |
| --- | --- | --- |
| Current status mixed with chronological notes | README/Features retained pre-v58 claims; Roadmap and Development accumulated many release-specific “next” statements | Maintained Project Status/Features/Roadmap, document map and collapsed history; dated evidence stays intact |
| Source defaults confused with activated installation | Workspace/reply speech docs described default-off source as not deployed despite v58 configuration | Explicit source/default/runtime/device columns and one dated flag snapshot |
| Multiple stores need one recovery inventory | `runtime.py` separates journal/workspace/deletion paths; primary rollback is insufficient for all effects | Operations recovery table and future synthetic paired-store restore rehearsal |
| Operator release path is not fully portable | Working signing/cutover/recovery controllers and host/task receipts remain private | Extract generic manifest-bound controllers; preserve ACLs, budgets, one-use claims, ownership and guarded rollback |
| Provider catalog is broader than typed deployment wiring | Thirteen source capability rows; four target groups projected; face/embedding/caption paths use other settings | Clarify coverage now; extend one qualified role at a time with versioned space/preprocessing identity |
| Many optional schemas/flags increase admission complexity | `RuntimeConfiguration`, compatibility tables and feature probes span primary and auxiliary stores | Document supported capability profiles and their exact schema/provider/recovery prerequisites before reducing duplication in code |
| Long client/domain controllers complicate changes | Existing Web modules and Kotlin coordinators already split lifecycle/domain concerns | Continue bounded extraction at tested seams; keep one capture/player owner and cross-scope cancellation tests |
| Product quality still needs real observations | Synthetic/source/native publication checks do not cover family storytelling, Mandarin listening, projector or perceived latency | Prioritize device/family acceptance and a grounded quality corpus before broad feature/provider activation |
| Home TV depends on an interactive desktop | Enabled task was Ready with Interactive logon | Qualify a separate startup/service identity plan with unchanged publication boundary |
| Migrated docs contain missing links and old commands | Android legacy plan, note-erasure references and server test README | Repair to maintained contracts; label unavailable legacy material and dated plans |

## Family memory product direction

The owner added a [family memory hub direction](FAMILY_MEMORY_HUB.md): long
oral histories about relatives, separately attributed contributions and reviewed
chapters/books. The introduction website uses fictional examples and original
cartoon illustrations. This adds a planned intake/domain slice, not activation
of story generation or an unlimited recording mode. Keep it separate from the
assistant's transient microphone and 30-day private conversation retention.

## Reflection on scope

The next iteration should improve reading/conversation continuity and observable
quality, then activate one grounded story/grouping capability with evidence.
Large provider swaps, automatic story propagation and a wholesale service/UI
rewrite would each need their own design and acceptance plan. The current
architecture already has useful authority and process seams to build upon.

Operational readiness should be a matrix, not one “done” label: source support,
format/schema admission, provider installation/native inference, live activation,
artifact publication and family/device acceptance answer different questions.
Neither a source catalog nor a running task makes an AI capability ready.

## Documentation maintenance decision

[Architecture](ARCHITECTURE.md) is the maintained source map;
[Project Status](PROJECT_STATUS.md) is a dated installation/acceptance snapshot;
[Features](FEATURES.md) is the capability matrix; [Roadmap](ROADMAP.md) is active
priorities; [Development](DEVELOPMENT.md) retains qualification history and stable
commands. Dated architecture/release/shortlist records preserve their historical
scope. New work updates the relevant contract plus these summaries, links and
source provenance without copying private receipts into Git.

## Review checks

The documentation pass checked 190 Markdown files, 761 local links and 33
Markdown fragment links with no missing targets. The source model inventory
verified 13 adapter sources without contacting providers or loading weights.
The new architecture map rendered with the existing Mermaid/Chromium tooling.
The introduction website passed desktop, 390 px and 320 px layout checks,
keyboard skip navigation, reduced-motion behavior and page-error checks;
rendered desktop/mobile artwork and the fictional story example were inspected.
Application builds, hosted CI, new model inference and family/device acceptance
were not rerun for these documentation/static-site changes.

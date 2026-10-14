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

## October 15 source follow-up

Later source separates client timing into pure monotonic trackers and saved
narration segmentation into a small server-owned module. Clients negotiate the
new [section-reading contract](ASSISTANT_SEGMENT_READING.md) independently of
opening speech; they supply an ordinal and current parent/revision, never prose.
One playback owner and exact request-entry identity protect cancellation and
replacement. Complete source revalidation also catches edits outside the current
segment. [Release-profile preparation](ANDROID_RELEASE_PREPARATION.md) now has a
portable read-only checker; signing/cutover controllers remain a later extraction.

The internal oral-history withdrawal/V4 writer-fence primitive remains separate
from live admission, transport and erasure. These source changes do not alter
the October 14 installation snapshot. Maintain the source/package/runtime/device
gates as features become available, rather than relabeling prototypes as deployed.

### October 15 compact controls, qualification and delivery boundary

Phone and Web followup controls now display compact Summary, Chapters and All
memories labels, with localized phone/Web text. Accessibility descriptions keep
the full scoped question, and activation still places the unchanged prior
request wording in the editable draft. Explicit saved-memory reader actions
retain minimum 48 dp phone and 48 px Web targets; continuing remains a user
action for one segment at a time.

The Web capability-probe race now adds missing followup controls only to the
exact current rendered result after capability readiness. Its deterministic
held-response Edge journey passed 27 checkpoints, including no focus movement,
auto-submission or duplicate controls; the turn-trail journey also passed.
A subsequent owned restore gate closes premature voice startup while session
restoration can still invalidate ASR; current source shows checking access with
the microphone off. Focused held-restore voice/recovery journeys pass. Phone
composer text is hoisted only within the live assistant host so My conversations
round trips preserve it without persistent storage or automatic submission.
Complete integrated profiles and delivery remain separate gates.
The generated oral-history qualification now covers five content-free groups
and twelve cases with `experimental_fixture_schema=true`, guarded V3/V4 journal
replay, withdrawal, populated legacy history, interrupted paired commits and
retained source bytes. The frozen v59 package remains four groups / ten cases.
This does not qualify production
admission, transport or erasure.

The API source-package plan is now 201 files. Earlier dated records that say
200 files remain historical counts; this follow-up did not rebuild or qualify a
package. There is no deployment or runtime change here: the October 14 v58
phone / TV v30 snapshot remains the recorded runtime state. No new native,
family/device or model-quality acceptance is claimed.

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

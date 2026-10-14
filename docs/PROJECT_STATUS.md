# Current project status

Reviewed **2026-10-14**, against source `86a154e`, the v58 delivery receipts and a
read-only Windows snapshot at **19:44 Beijing (11:44 UTC)**. Documentation edits
are separate from the immutable deployed artifacts. This page is a dated status
snapshot; refresh runtime evidence before the next operation.

## Delivery and acceptance

| Area | Latest verified evidence | Still open |
| --- | --- | --- |
| API/Web | Source `8bc60e816e321c5a6ea4e8ca7b1ecf797b236138`, 195-file archive; service running; served-byte/anonymous-denial checks passed at deployment | Real owner/member voice and UX acceptance |
| Primary database | `a0c9d2e4f817` verified by the deployment; no migration | Optional later schema/feature activation and paired recovery qualification |
| Phone | v58 / `0.58-contextual-memory-actions`, signed and published to Windows HTTPS OTA | v58 physical installation and family listening acceptance |
| TV | v30 / `0.30-library-recovery` OTA manifest verified unchanged | Physical projector/library/playback check; Home TV task awaits interactive desktop session |
| Introduction website | Private preview deployed, then public audience verified; cartoons/fictional examples only | Broader family/design feedback; [delivery record](../website/RELEASE_2026-10-14.md) |
| Public source | Monorepo is the development home; this review checks local source and retained receipts | Remote branch/CI freshness was not verified: GitHub CLI authentication returned HTTP 401 and the anonymous API check was unavailable |

[Phone/API delivery](../clients/android/docs/PHONE_V58_RELEASE_2026-10-14.md)
records exact artifact hashes and source provenance. Native Windows verification
matched the complete signed APK over HTTPS. The independent Mac first/last range
checks passed; its additional complete transfer timed out. Neither publication
nor a running process is a physical-device or narrative-quality pass.

## Runtime configuration observed

The public defaults remain closed or opt-in. The following describes this
inspected installation, not the default configuration of a new checkout.

| Capability/configuration | Observed state | Meaning |
| --- | --- | --- |
| Upload review | Enabled | Per-library owner/member policy and destination checks still apply; a receipt alone is not gallery or TV publication |
| Assistant, saved-memory cards, private reply speech | Enabled | Authenticated read-only voice/chat and fresh saved-story actions; no general administrative tool agent |
| Private workspace, assistant receipt journal, original-deletion journal | Configured files present | Distinct stores; previous native admission/format checks remain delivery evidence, this snapshot did not open databases |
| Memory collaboration and original contributions | Enabled | Family contributions remain separate from assistant troubleshooting history |
| Upload annotation intake | Off | Separate from original story/memoir contribution paths |
| Story generation and title suggestions | Off | Implemented adapters/contracts are not a live writing/title service |
| Memory groups and memoir editorial/editions | Off | Source and synthetic qualification exist; activation still requires compatible schema, backup/recovery, provider and UI gates |
| Permanent family-note erasure | Off | Imported D1/journal contracts do not imply live migration or erasure activation |

Runtime source and flag checks emitted no private configuration values, tokens,
accounts, original media or model identities. No model inference, database open,
service change or publication was performed by this documentation audit.

## Service/task snapshot

API, approved CPU, face, image embedding, video embedding and video preparation
workers, ASR, and TTS tasks were enabled and running. The API retains its enabled
30-second startup trigger. Home TV was enabled but Ready, with an interactive
logon dependency. Do not infer a listener, warm model, GPU placement, successful
queue completion or audible quality from scheduled-task state alone.

Video conversion/backlog and unrecoverable-source counts were not recounted in
this audit. Retain failure rows and resume unfinished items; use the
[recovery planner](VIDEO_SOURCE_RECOVERY.md) before any separately authorized
repair. No source file or failed record was replaced or reset here.

## Current source qualification

- Full API profile at the v58 qualification revision: 1,426 tests and 862
  subchecks, plus the generated no-listener demo.
- Exact source ZIP: eleven synthetic qualification groups passed on Mac and
  native Windows under the reviewed resource limits.
- Android and Web feature tests, large-text emulator/browser checks and release
  assembly/lint are recorded in the [candidate](../clients/android/docs/PHONE_V58_RELEASE_CANDIDATE_2026-10-14.md).
- Phone delivery: 16 local operation checks, five generated native script parses,
  original-certificate signing and native/HTTPS publication checks passed.

These scopes overlap and are not summed. No new full application build or hosted
CI run is implied by documentation/link checks. [Development](DEVELOPMENT.md)
retains dated qualification history; [Features](FEATURES.md) is the capability
matrix and [Roadmap](ROADMAP.md) is the active priority list.

## Next decision

Complete the [v58 family test](../clients/android/docs/PHONE_V58_TEST_GUIDE_ZH.md),
then implement bounded assistant chapter continuation/progress. In parallel,
prepare a small grounded story/grouping quality pilot and portable release/recovery
tooling. New models, schema changes, service controls and public publication keep
separate qualification and operation authority.

## Later source increment: oral-history intake

The [internal recording-section foundation](ORAL_HISTORY_INTAKE_FOUNDATION.md)
was developed after the installation snapshot above. It has source tests only,
no HTTP/client surface, migration or runtime configuration. Windows services,
model/worker activity, family data and v58/TV OTA feeds were not changed. Do not
interpret its source quota or generated-fixture installer as live admission.

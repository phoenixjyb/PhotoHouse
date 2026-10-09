# Feature and acceptance matrix

This matrix records the source migration baseline. Live installations and physical devices have their own acceptance records.

| Area | Implemented baseline | Remaining gate or next improvement |
|---|---|---|
| Library access | Protected membership, owner review, per-member auto-approval | Member-account and revoked-access device walkthrough |
| Upload UX | Folded progress/history, date hints and intake states | New-upload end-to-end receipt/probe/preview validation |
| Original memories | Text/audio contributions, consent, original playback; separate default-off D1 identity-bound family-note erasure and offline journal upgrade | Exact D1 migration/version 2 journal and native recovery qualification; multi-member family acceptance and retention/deletion walkthrough |
| Stories | Revisioned chapters, original-memory links, source inspection; manual memoir editing and reading in Web source; protected selected-media grouped creation with reviewed title suggestions; offline synthetic memoir/title quality cases and independent title-role capture | Human review and separate local-model quality qualification remain open; title provider stays disabled by default; plan-only fixtures are not model results; Web memoir flag and live migration remain off/unqualified |
| Phone | Reviewed voice memory, chapter source linking, family-memory home card, draft guards, v40 assistant recovery, OTA client, manual memoir arrangement, first-message previews, scoped conversation restoration, original-source inspection, explicit chapter/reply narration pause-resume, grouped-story creation, profile-derived optional bylines and explicit same-day media candidates | [Candidate picker evidence](../clients/android/docs/ANDROID_RELATED_MOMENTS_2026-10-09.md) records local checks separately from release package, live service and family acceptance; server/client delivery and enabled b1 service remain separate gates |
| Web | Chinese default, session recovery, story workspace, pending assistant recovery, manual memoir editor/reader, opt-in first-message previews, scoped conversation restoration, explicit narration controls and original/derived source inspection; the current ten-suite generated-data Web profile passes | Conversation navigation has 23 checkpoint groups; the full community journey has its own result. Earlier 16/17/20/22 counts remain historical. These and the source-inspection/narration journeys are synthetic browser evidence; b1 service defaults off, with no household migration or live owner/member acceptance |
| TV | Named libraries, OTA, paced viewing | Latest installed projector navigation and playback |
| Voice assistant | ASR input, explicit submission, receipts/context, pending-turn recovery, optional TTS, scoped story/memoir conversation navigation and current-reply clarification cues in Web and phone | Served Web and signed phone delivery; provider and family conversation quality qualification |
| Approved face queue | Stdlib SQLite approval and claim helper; bounded detection and shadow-embedding pipeline source; portable Windows Job Object helper is included | Eight additional fake-child pipeline checks use generated data; native Windows Job Object, CUDA/model/device and live-service qualification remain separate gates |
| Video preparation | Checkpointed conversion, bounded resources, source-error methods | Native closure and playback publication on the household server have separate receipts; device playback still needs acceptance |
| Approved worker package | Fixed 21-file source-only package, immutable monorepo/standalone Git lookup and a synthetic canary selector that defaults to a0 and permits explicit b1 testing | Eight current packager tests cover both actual Git layouts and preservation; earlier package/schema cohorts have their own source snapshots; Windows-native execution, GPU/provider readiness and family processing remain separate gates |
| Worker terminal diagnostics | CPU, image/video embedding and face pipeline emit fixed failure identifiers while preserving terminal exit codes and approval/processing rules | 38 generated CPU-profile cases cover CLI reports, private-text refusal, SQLite/resource failures and child routing; installed failures and service recovery still need native operation evidence |
| Maintainability | Unified curated source, portable API/Android checks, synthetic demo, dependency/asset inventory, default-read-only b1 application tool and CI template | Complete archive review and hosted CI |

## Next product slices

The phone search assistant now reviews recognition before explicit insertion,
preserves typed words and links the ASR receipt only after Add. Unicode overflow
keeps both inputs available. See [the phone qualification](../clients/android/docs/ANDROID_ASSISTANT_TRANSCRIPT_REVIEW_2026-10-10.md);
signed delivery and a live voice turn remain separate gates.

1. Close the delivery gates for already implemented features.
2. Improve a complete voice turn with visible context, natural clarification, and server-supported idempotent recovery that cannot duplicate an action.
3. Extend memoir access to Android chapter and audio editing, with revision, source-change and offline recovery.
4. Add an album-level outline with ordered media and owner review before any prose work.
5. Improve long memoir playback, chapter navigation and source citation review.
6. Qualify local narrative processing with synthetic multi-chapter cases before enabling it for family material.
7. Publish the qualified source candidate through reviewed changes to the selected repository; run hosted CI.

## Longer memoirs: manual editorial source

The additive b1 sidecar stores ordered child revision snapshots, introduction
citations and source-linked prose between adjacent stories. The legacy memoir
DTO stays unchanged. The optional service and routes are source-tested for
authorization, revision conflicts, same-payload retry, save/reopen, original
deletion/replay and interrupted migration rollback. No historical source links
are inferred. Child or original-source changes yield an honest `source_changed`
state rather than displaying stale editorial text.

Phone story and memoir selectors also show bounded previews of the first retained
user message. The public monorepo passed separate filtered JVM runs totaling 168
tests across its HTTPS adapter (6), wire decoder (8), repository (11), connected
store (97) and memory community store (46). The pinned Android source workspace
separately records 11 repository tests, 46 community-store tests and two API 36
emulator journeys at 150% text with reviewed renders; those emulator results are
not from this public candidate. See the [phone preview evidence](../clients/android/docs/ANDROID_CONVERSATION_PREVIEWS_2026-10-05.md).

The service and Web client source are covered by generated-data browser journeys
for editing and reading. The `memory_editorial_enabled` flag remains disabled by
default, and the optional Web profile is not a live service or household migration
acceptance. Android source now includes owner citation selection, adjacent transitions,
revision review, scoped access clearing and frozen save retries. Its 213 focused /
adjacent core tests and four emulator journeys use synthetic adapters; no release
APK or live b1 service is included in those checks. See the
[Android evidence and commands](../clients/android/docs/MEMOIR_EDITORIAL_UI_2026-10-04.md).
The sidecar supports human authored editorial text; local-model generation remains a separate, unqualified
feature. See [story experience](STORY_EXPERIENCE.md) and
[optional Web browser checks](WEB_DEVELOPMENT.md).

The Web pending-turn recovery keeps an uncertain submission visible and checks
its receipt without resending it. After a tab reload, a bounded request/account/
library pointer offers an explicit receipt check; question text, recordings,
reply and conversation context are not stored in that pointer. Its eleven
browser checkpoints are synthetic source qualification. They do not establish provider availability or a live
account. See [Web browser test setup](WEB_DEVELOPMENT.md) and the
[story experience boundaries](STORY_EXPERIENCE.md).

The imported phone overlay adds explicit pause/resume controls for chapter and
assistant-reply narration and a bounded source inspector that keeps original
contributions separate from transcripts and polished text. The public candidate
has filtered JVM evidence for these changes but no new emulator, release-package
or physical-phone result. See the [Android memoir inspection note](../clients/android/docs/ANDROID_MEMOIR_SOURCE_INSPECTION_2026-10-05.md)
and [narration note](../clients/android/docs/ANDROID_REPLY_NARRATION_CONTINUITY_2026-10-05.md).

## October 5 source qualification

The optional manual memoir editor is included in the unsigned phone v41 release
candidate; its release unit tests, lint and assembly passed in the phone source
workspace. This is a separate artifact result, not signing, publication or a
physical-phone acceptance claim for the public monorepo.

The unified CPU profile passed 498 tests and 197 subtests plus the generated-data
demo, including seven plan-only memoir quality checks and the latest URI-guard
and conversation-preview checks. The preceding 485-test profile predates those
latest checks. The new offline b1 operator adds 14 refusal,
preservation and rollback cases;
the private-storage suite adds five checks for conservative Windows owner/DACL
policy and POSIX paths. See [development](DEVELOPMENT.md),
[maintenance](MAINTAINING.md), and [the roadmap](ROADMAP.md).

The approved-face queue contributes 14 CPU-profile checks. Its eight synthetic
pipeline checks share generated fixtures and fake child results (22 combined)
and are optional because they need NumPy and Pillow. They do not call the strict
CUDA child, load local model weights, or establish native GPU or household
service readiness. The newly imported face pipeline and Windows Job Object
helper still need native qualification before any runtime claim; the helper's
Windows integration tests are skipped on macOS.

The rehearsal URI guard is now included in the public CPU profile. Its twelve
focused checks (30 subtests) passed in this tree and reject outside-candidate,
remote-authority and unsupported auxiliary-file URIs. This repairs the generated
Windows journal fixture admission; it does not permit a live database operation
or qualify the 151-case successor on Windows.

## October 6 source additions

The optional memoir model context imports application and worker source from
`a56861b`. An explicit `editorial_context=1` request can include current saved
opening citations and adjacent transitions; legacy requests retain their exact
context and fingerprint. The selected profile is frozen in each job. References,
consent and revisions are checked before provider use and before accepting its
result. Generation and the editorial feature remain disabled by default.

The final public application run passed **96 tests and 73 subtests** across ten
context, job, HTTP, narrative, planning, worker and deletion suites. The earlier
backend-only operator allowlist was excluded from that import because it named
files absent from the curated tree. A later candidate adaptation keeps an
explicit existing-file runtime/migration/dependency closure, qualifies the
extracted API import, and packages server paths from the monorepo revision.
Windows worker and full operator qualification remains separate. At the
`a56861b` import snapshot, current-source verification covered
**844 files**, with 312 feature-file records and 74 ordered overlays. The earlier
100-test exploratory run included the private packaging slice and is not the
final public scope.

Phone source also resets reading position when selecting another story chapter
and shows original audio length without null/raw millisecond labels. Its source
workspace records the narrow synthetic emulator checks; this public import has
no separate emulator, APK, native service or family result. Client context-choice
controls are a subsequent source slice. No new ZIP or public release was made.


The phone now offers an explicit choice to include saved opening citations and
chapter transitions in memoir chat. A read-only plan check selects the option;
failed checks retain the draft and require rechecking or an explicit return to
the existing context. Retries preserve the exact text, mutation and choice.
The imported `e5ea3de` slice passed **85 focused JVM tests** in this unified
layout. Its source workspace separately passed two Chinese/English 150% emulator
journeys and lint; those are not emulator acceptance for the public candidate.
At the `e5ea3de` phone context-choice import snapshot, current-source verification
covered **849 files and 75 source overlays**. This is an import-stage count, not
the current candidate total; run `python3 tools/verify_current_source.py` from
the repository root for the current result. No phone release or service
activation is included. See the [phone context choice](../clients/android/docs/ANDROID_MEMOIR_EDITORIAL_CONTEXT_CHOICE_2026-10-06.md).


The Web memoir chat and drafting forms now offer the same explicit saved-context
choice. The exact `4b0b2bd` import passed its contract harness and **17 synthetic
browser checkpoints** in this unified tree, with no page errors or external
origins. The phone `2a8cf8e` import adds a read-only whole-book plan followed by
an explicit draft request and separate chapter-by-chapter review. It passed
**67 focused JVM tests** here; suggestions do not replace saved stories.

For maintainers, `tools/check.py memory` runs a focused CPU profile (**127 tests
and 76 subtests**), and the full API profile includes the new context/planning
suites (**522 tests and 211 subtests**, plus the generated demo). Live model
quality, enabled b1 service, signed APK, physical phone/TV and public release
remain separate delivery gates. The current Downloads ZIP was not replaced.

## Reviewed voice instructions and storytelling forms — October 6

The imported phone `a8bacd1`/`e2f0824` source adds a separate voice-instruction
review flow for memoir drafting, followed by explicit insertion and submission.
Temporary audio is separate from retained original family recordings; transcript
records follow the existing thirty-day assistant policy. Optional faithful
chronicle, reflective essay and connected memoir directions append to the one
existing request field only when the user submits. The default request is exact;
combined UTF-8 limits, immutable retries and scope changes preserve the full draft.

This public layout passed **78 focused JVM cases** (dictation helper 7, narrative
store 12, community 53 and editorial integration 6). The source workspace's
separate final bilingual 150% emulator checks and lint are recorded in the imported
contracts; they are not public-layout emulator or family acceptance. No signed
package, provider activation or deployed service is included.

Web `c346e6e` adds reviewed voice drafting instructions and keeps the stop/ASR
interval busy. The public browser suite passed 17 generated-fixture journeys
with no page errors or external origins, alongside its UI harness. Common model
prompt `13a050c` forbids invented quotations and distinguishes authored words
from derived transcripts; 24 public adapter/context checks passed. A prompt rule
is not a semantic factuality guarantee.

Web memoir form selection from `b5dc212` is also imported. A separate run in
this unified layout passed **18 synthetic browser checkpoints** with no page
errors or external requests. It verifies all four choices at 390 pixels and
150% text, language rerender preservation and reachable submission. The contract
harness passed as well, including exact default instructions, frozen uncertain
retries, later draft preservation, 409/422 handling and voice overflow retention.
The integration owner inspected final English form and submission displays.
These checks do not establish live deployment or model adherence.

The offline [development doctor](DEVELOPMENT_ENVIRONMENT.md) reports the API,
memory, Android and optional Web prerequisites as available, missing or
unverified. Thirteen scoped tool tests passed. It does not run application
tests, install packages or admit a deployment. Exact lock mismatches are shown
separately from a locally usable environment's previous test results.

Web plan-to-story reading from `e10409d` passed a separate 19-check synthetic
browser run and its UI harness in the unified layout, with zero page errors or
external requests. Source Android `230acb9` supplies the collapsed 24-chapter
proposal directory and separates original navigation from proposal navigation;
its bilingual emulator/lint evidence belongs to the source workspace.

The latest complete API run passed 523 tests and 215 independently reported
subtests, followed by the generated no-listener demo. A fresh hash-installed
Python 3.12.12 environment matches all 27 applicable locked packages, including
pytest 9.0.3. The previous pytest 8.4.1 run remains a separate historical record.
Earlier profile counts are preserved in the acceptance record, with native,
provider, hosted CI and deployed service qualification remaining separate.

Per-story memoir plan reading from Android `694fd08` is imported. The unified
layout passed 78 focused core JVM tests, debug compilation and debug lint.
The source workspace's separate final Chinese/English 150% emulator checks
verify whole-book over-capacity, a readable inspect-only story, exact fresh
parent/child reads, retained instructions/form and directory collapse. No
public-layout emulator or signed package is inferred from these checks.

The source workspace also prepared phone v43 from `13b01ab` with ten release
unit tests, release lint/assembly and unsigned APK continuity checks. That
private configured artifact is not a public-candidate APK or an OTA publication.
All 40 standalone public tool tests passed, including the 13 doctor checks
and four checks of the CPU child environment. Supported CPU checks no longer
inherit live database/provider settings or Python plugin overrides.

## Memoir draft navigation qualification

Web source `766e327` adds a default-collapsed, local 24-chapter directory with
current chapter announcement and exact account/library/book/rendered-job fences.
The unified layout passed 20 synthetic browser checkpoints and six UI harness
behavior groups; Chinese/English 390px and 150 percent text were inspected,
including the final chapter beneath the sticky reader header. Jumps stop prior
read-aloud without fetching or saving. The source worktree also produced an
unsigned phone v43 candidate from `13b01ab`; this is separate from the public
Android compilation/lint and 78-test JVM qualification. Neither these source
checks nor the unsigned artifact establish a live b1 service, publication,
physical device acceptance or narrative model quality.

Web source `672cfd5` adds explicitly controlled local audio for each reviewable
story or memoir draft chapter. The unified layout passed the 20-checkpoint
protected browser journey and both narration/community harnesses. Exact prose,
local voices, recording priority, pause/resume/stop, directory cancellation and
render-owned disposal retain the review boundary. Native browser voices and
family listening quality are separate acceptance checks.

The memoir companion now names the current whole-book scope, and each proposal
chapter displays a compact position such as 24/24. Source `4328770` passed
20 synthetic browser checkpoints and the community harness in this unified
layout. The final English 390px/150 percent display was visually reviewed.
Titles remain text, and the label does not change the generation target.

## Latest complete source qualification

The current Android imports passed 684 JVM tests, phone/TV debug lint and both
unconfigured debug builds. The earlier 592-test profile and targeted/emulator
runs retain their own source pins. These builds were not installed or published.
The current four-suite Web profile passed; its 22-checkpoint community journey
covers current-chapter questions, whole-book thread continuity and shared
draft/IME/voice insertion guards. Full API 523/215 qualification remains tied
to its exact-lock CPU run; fifty standalone tooling tests passed separately.

The Android report inventory reads existing XML without running tests or
binding results to a revision. It reports missing modules and failure/skip
counts, rejects unsafe/invalid files and prints no raw test output. The prepared
CI template calls it after the Android build. No hosted run is claimed.

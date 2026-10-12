# Feature and acceptance matrix

As of October 10, PRs #13–#15 are merged. The latest hosted source run passed
API, Android, Windows private-reader, Windows CPU and seventeen generated Web
suites. Historical counts below retain their revision-specific meaning;
household deployment and family acceptance remain separate gates.

The latest October 12 local source run passed the complete 19-suite Web profile
and the complete backend profile (1,210 tests and 692 subtests) with unchanged
profile source snapshots at `a1c6e94`. Earlier results retain their own pins.
The phone/TV source profile subsequently passed JVM tests, lint and
debug builds; newer chapter/reader/session checks are detailed in
[the development record](DEVELOPMENT.md#october-12-story-composition-and-reading).
These later local
checks do not update the hosted or household release records above.

This matrix records the source migration baseline. Live installations and physical devices have their own acceptance records.

Phone v50 is delivered on HTTPS OTA with the original artwork and clearer update
messages. Native verification and an independent complete download passed; phone
installation remains a separate gate. See the [delivery record](../clients/android/docs/PHONE_V50_RELEASE_CANDIDATE_2026-10-12.md).

| Area | Implemented baseline | Remaining gate or next improvement |
|---|---|---|
| Library access | Protected membership, owner review, per-member auto-approval | Member-account and revoked-access device walkthrough |
| Upload UX | Folded progress/history, date hints and intake states | New-upload end-to-end receipt/probe/preview validation |
| Original memories | Text/audio contributions, consent, original playback; separate default-off D1 identity-bound family-note erasure and offline journal upgrade | Exact D1 migration/version 2 journal and native recovery qualification; multi-member family acceptance and retention/deletion walkthrough |
| Stories | Revisioned chapters, original-memory links, source inspection; manual memoir editing and reading in Web source; protected selected-media grouped creation with reviewed title suggestions; offline synthetic memoir/title quality cases and independent title-role capture | Human review and separate local-model quality qualification remain open; title provider stays disabled by default; plan-only fixtures are not model results; Web memoir flag and live migration remain off/unqualified |
| Phone | Reviewed voice memory, chapter source linking, family-memory home card, draft guards, v40 assistant recovery, OTA client, manual memoir arrangement, first-message previews, scoped conversation restoration, original-source inspection, explicit chapter/reply narration pause-resume, grouped-story creation, profile-derived optional bylines and explicit same-day media candidates | [Candidate picker evidence](../clients/android/docs/ANDROID_RELATED_MOMENTS_2026-10-09.md) records local checks separately from release package, live service and family acceptance; server/client delivery and enabled b1 service remain separate gates |
| Web | Chinese default, session recovery, story workspace, pending assistant recovery, explicit transcript review, bounded current-page assistant turn trail, manual memoir editor/reader, opt-in first-message previews, scoped conversation restoration, explicit narration controls and original/derived source inspection; generated-data Web profiles have revision-specific results below | Conversation navigation has 23 checkpoint groups; the full community journey has its own result. Earlier 16/17/20/22 counts remain historical. These and the source-inspection/narration journeys are synthetic browser evidence; b1 service defaults off, with no household migration or live owner/member acceptance |
| TV | Named libraries, OTA, paced viewing | Latest installed projector navigation and playback |
| Voice assistant | ASR input, explicit submission, receipts/context, pending-turn recovery, optional TTS, scoped story/memoir conversation navigation and current-reply clarification cues in Web and phone | Served Web and signed phone delivery; provider and family conversation quality qualification |
| Conversation reading | Bounded Web and phone exchange lists preserve older reading positions and offer a localized jump to the latest activity | [Trail contract](ASSISTANT_TURN_TRAIL.md); generated phone scroll/keyboard journeys pass; exact installed delivery remains separate |
| Story/memoir chat history | Phone direct latest-page action and scope/lifetime guards on all history controls preserve unsent text | [Navigation contract](PHONE_MEMORY_CHAT_NAVIGATION.md); four bilingual 150% simulator journeys pass at `7d7b1ef`; signed delivery remains separate |
| Full conversation continuation | Backend distinguishes the 128-turn cap; Web and phone keep old history and transfer retained words into a reviewed new conversation using one retry identity | [Continuation contract](MEMORY_CHAT_CONTINUATION.md); generated browser and bilingual 150% simulator checks pass; served Web, signed phone and family conversation acceptance remain separate |
| Phone memoir composition | Collect readable saved stories, review their order and optional introduction, save with exact retry, and explicitly open the fresh book | [Composer contract](PHONE_MEMOIR_COMPOSITION.md); source `e157679` passed 161 focused core cases and four bilingual enlarged-text composer journeys, including reviewed voice introduction; six shared dictation journeys also passed; no APK publication or live activation |
| Saved phone memoir editing | Edit an authorized existing book, add/remove/reorder readable stories, revise book fields and reviewed spoken opening; preserve conflicts and replay uncertain saves exactly | [Edit contract](PHONE_MEMOIR_COMPOSITION.md); 822 core and 17 phone JVM checks, builds/lint and six bilingual enlarged-text generated journeys pass; source only, outside published v47 |
| Visual phone memoir shelf | Protected cover thumbnails or themed fallback, opening excerpts, honest media-entry totals and explicit reading actions | Source `61847c7`: 125 scoped core cases, two bilingual 150% shelf journeys and nine affected reader/composer journeys passed; release delivery remains separate |
| Reviewed memoir introduction voice | Phone composer and Web editor preserve the latest typed opening, review dictation before insertion and block save during unresolved voice input | [Introduction contract](MEMOIR_INTRODUCTION_DICTATION.md); phone accepted locally; Web source `bd8f6b6` passed Node contract checks; the completed-recording correction is `cd87ab2`; final complete-profile evidence is in Development; served/signed and family voice quality remain separate |
| Assistant result compatibility | Phone accepts protected seven-field result assets and optional validated hints; result cards label filename/received dates | [Response contract](ASSISTANT_RESULT_COMPATIBILITY.md); parser, protected transport and bilingual emulator checks pass at `c566ded`; served/device evidence remains separate |
| Memoir editing | Citation choices refresh independently of the title, opening note and story-order form; stale revisions and detached editors reject delayed results | Generated browser focus/composition checks; served UI and family editing acceptance remain separate |
| Approved face queue | Stdlib SQLite approval and claim helper; bounded detection and shadow-embedding pipeline source; portable Windows Job Object helper is included | Eight additional fake-child pipeline checks use generated data; native Windows Job Object, CUDA/model/device and live-service qualification remain separate gates |
| Video preparation | Checkpointed conversion, bounded resources and a supported path-free [source recovery planner](VIDEO_SOURCE_RECOVERY.md) | Native closure and playback publication on the household server have separate receipts; device playback still needs acceptance |
| Approved worker package | Fixed 33-file source-only closure, immutable monorepo/standalone Git lookup and a synthetic canary selector that defaults to a0 with explicit b1/c2/d1/e7 targets | Eight packager tests cover source identity, both Git layouts and schema selection; the generated native full-chain/CPU/video result at `18eb1cc` has its own receipt. New source pins, GPU/provider readiness and family processing remain separate gates |
| Worker terminal diagnostics | CPU, image/video embedding and face pipeline emit fixed failure identifiers while preserving terminal exit codes and approval/processing rules | 38 generated CPU-profile cases cover CLI reports, private-text refusal, SQLite/resource failures and child routing; installed failures and service recovery still need native operation evidence |
| Shared memory groups | Default-off protected group editor and time/similarity proposals, ID-only membership and sticky exclusions; current original notes feed story/memoir evidence with canonical origin, byline and deduplication | Manual groups require e7 activation; automatic proposals separately require qualified immutable vector identity/coverage; phone release and family calibration remain gates. No anonymous TV source projection or model activation |
| Chapter source choices | Explicit `chapter_sources_v1` policy selects up to 12 current picture-linked sources per chapter, including none; narrative, chat and title context honor the policy and preserve legacy stories; Web/phone controls pass focused browser/emulator checks | [Contract and local evidence](CHAPTER_SOURCE_CHOICES.md); final source qualification, live service and signed phone delivery remain separate |
| Spoken chapter writing | Phone and Web controls fence transient ASR to one editable chapter, preserve typed words and retain a rejected transcript for review | [Design and local evidence](STORY_CHAPTER_DICTATION.md); served Web, signed phone and family voice acceptance remain separate. No original audio is persisted by this writing shortcut |
| Saved phone story editing | Fresh same-revision family links, retained chapter arrangement, reviewed prose/source edits and chapter dictation; immutable uncertain retry and failed-reload draft preservation | [Editor contract and checks](PHONE_SAVED_STORY_EDITING.md); signed phone delivery and a family edit/reopen journey remain separate |
| Story reader navigation | Protected Web thumbnail filmstrip and current-frame labels; phone selection bound to current scope, chapter revision and eligible media; explicit chapter/media actions | [Reader contract](STORY_READER_NAVIGATION.md); generated browser/emulator checks remain separate from served Web files, signing, OTA and family acceptance |
| Phone reading continuity | Exact revision/account/library location offers after fresh authorization, explicit Continue/Start over and bounded Keystore-encrypted metadata | [Contract](PHONE_STORY_READING_CONTINUITY.md); generated encryption and bilingual 150% emulator checks passed; signed phone and family acceptance remain separate |
| Phone memoir continuity | Exact book/ordered-child/story/chapter/media location, fresh metadata-only offer and explicit Continue/Start over; separate encrypted memoir domain | [Contract](PHONE_MEMOIR_READING_CONTINUITY.md); source `c3e2706`, real-Keystore and bilingual simulator checks passed; signed delivery remains separate |
| Memoir opening narration | Explicit local Read, Pause, Resume and Stop for the saved opening; book language and reader scope retained | [Contract](MEMOIR_INTRODUCTION_NARRATION.md); Web `a8e8b47` passed 30 generated browser groups; phone `6f140f8` passed nine generated opening/reader cases; final phase/foreground correction `466ada2` passed the 28-case narration cohort and complete Android profile at `0548d8c`; served Web, signed phone and family listening remain separate |
| Memoir narration continuation | Explicit next-chapter speech inside one story, single consumed start attempt, no automatic replay after a recording conflict | [Contract](MEMOIR_NARRATION_CONTINUATION.md); phone `92b1285` and Web `ce2467c` have generated checks and inspected large-text renders; voice quality and delivery remain separate |
| Original memoir navigation | Collapsed phone contents, selected numbered cards, exact rendered-state guards and scalable Web media captions | [Reader contract](STORY_READER_NAVIGATION.md); phone `a0fdbca` and Web `210222b` passed generated checks and bilingual large-text review; signed and served delivery remain separate |
| New chapter arrangement | Reviewed new drafts can split or merge adjacent media without reordering, dropping prose or copying originals; actual title/save layouts and immutable retries | [Contract](STORY_CHAPTER_ARRANGEMENT.md); local browser/JVM/emulator checks passed; served/signed delivery remains separate |
| Web source-conflict recovery | Explicit refresh preserves a new story's words, manual groups, focus and composition; stale choices are removed and fresh choices require review before another save | [Contract](WEB_STORY_SOURCE_REFRESH.md); 29 generated browser checkpoint groups passed at `acb9036`; served Web and family editing acceptance remain separate |
| Phone album-to-story selection | Reauthorize an existing album, confirm selection replacement and seed its ordered moments/theme; complete larger albums remain browsable | [Contract](PHONE_ALBUM_TO_STORY.md); complete Android source profile and bilingual emulator flows passed at `b3ddd57`; signed delivery remains separate |
| TV library recovery | Disabled stale library choices, explicit localized retry preserving page/filters, and remote focus restoration | [Recovery contract](TV_LIBRARY_RECOVERY.md); the generated large-text remote journey passes; TV v30 signing/publication and physical TV acceptance remain separate gates |
| Windows CPU portability | Explicit generated database/runtime/source-package profile and a separate hosted Windows job | Repaired cohort passes 65 tests and 25 subtests on macOS and hosted Windows at `12c10e9`; the installed household runtime retains its own gate |
| Maintainability | Unified curated source, portable API/Android checks, synthetic demo, dependency/asset inventory, default-read-only b1 application tool and five hosted source jobs | Exact release archive review; installed-runtime and device evidence remain separate |

## October 12 delivery and source follow-up

The API/Web source `c6b1401` is served and phone v47 is published to HTTPS OTA,
with native and independent full readbacks. The live schema stayed at a0; five
upload workers were observed running after restoration. TV OTA stayed v30.
These receipts do not establish physical-device or family acceptance, and did
not activate AI generation, editions, title suggestions or grouping.

The subsequent local Android slice adds saved memoir editing through the
existing protected save contract: parent-specific edit permission, add/remove/
reorder saved stories, revised book fields, reviewed opening dictation, conflict
preservation and exact uncertain-save replay. See
[the edit contract](PHONE_MEMOIR_COMPOSITION.md). This feature is not in the
published v47 APK; a new signed release remains its delivery gate.

## Next product slices

The Web and phone search assistants now review recognition before explicit insertion,
preserve typed words and link the ASR receipt only after Add. Unicode overflow
keeps both inputs available. See [Web review](ASSISTANT_TRANSCRIPT_REVIEW.md) and
[the phone qualification](../clients/android/docs/ANDROID_ASSISTANT_TRANSCRIPT_REVIEW_2026-10-10.md);
signed delivery and a live voice turn remain separate gates.

1. Close the delivery gates for already implemented features.
2. Improve a complete voice turn with visible context, natural clarification, and server-supported idempotent recovery that cannot duplicate an action.
3. Extend memoir access to Android chapter and audio editing, with revision, source-change and offline recovery.
4. Extend the implemented album-to-story outline into reviewed multi-story memoir planning, preserving ordered media and provenance.
5. Complete delivery and family review of long memoir continuity, explicit narration and chapter navigation; then refine source citation review from that feedback.
6. Qualify local narrative processing with synthetic multi-chapter cases before enabling it for family material.
7. Keep reviewed source delivery and hosted checks current as the monorepo evolves; preserve exact release profiles and operation receipts.

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


## Central personal assistant (approved development)

The approved [拾光助手 design](PERSONAL_ASSISTANT.md) brings typed chat and an
opt-in foreground voice session into one phone/Web workspace. The initial slice
reuses protected photo/video retrieval, visual results and result-count speech;
Pause/End, context changes and uncertain-request recovery are explicit. Durable
private conversations/preferences and the grounded story/album/memoir agent are
separate qualification/delivery layers. Source controls and synthetic journeys do
not establish live provider quality or family-device acceptance. Phone v49 is published with the workspace/voice foundation; the Web workspace is also served and independently verified. The private history/preferences API is a separate
default-off source slice: owned list/create/read/delete, revisioned preferences
and reset, strict request limits and 30-day retention. Saved references are
non-actionable placeholders. Server-owned turns, applied preferences and client
continuation are not yet enabled in the served Windows backend.

The [private turn layer](PRIVATE_ASSISTANT_TURNS_V1.md) now implements an isolated
schema-v2 request ledger and server-owned continuation in local source. Identical
request retries recover existing state; stored results are revalidated and
readback cannot replay an open action. Web adds private conversation selection,
recent text history, reply-language preferences and explicit deletion. Phone
adds a strict protected SDK, lifecycle-scoped coordinator and private text/history
panel. [Explicit text/voice continuation](PRIVATE_ASSISTANT_VOICE_V1.md) now
activates the same owned thread in the central assistant: typing starts no
microphone, while the voice button starts foreground listen/reply/listen.
Synchronous request correlation, GET-only recovery, confirmed abandonment,
capability-loss stopping and access-denial cache erasure are implemented locally.
Recovered replies pause before speech, navigation or another capture. The
unselected ordinary route remains v1.
All private workspace storage remains explicitly admitted and default-off.

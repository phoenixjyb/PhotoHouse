# Feature and acceptance matrix

Maintained summary, reviewed **2026-10-14**. [Project Status](PROJECT_STATUS.md)
binds the exact release/runtime observations; [Roadmap](ROADMAP.md) owns active
next work. “Implemented” describes source, “enabled” describes an inspected
installation, and family acceptance requires physical use.

## Current capabilities

| Capability | Source / delivery state | Remaining gate |
| --- | --- | --- |
| Accounts, library membership, owner review and selected-member auto approval | Protected contracts and per-library policy; upload review enabled | Owner/member/device trial; existing uploads still need review |
| Photo/video browsing, named libraries/albums, dates and prepared playback | Phone/Web protected readers; Web failed thumbnails show a localized in-card fallback while preserving the label and explicit open action; Home TV uses its separate published catalog; filename/receipt hints remain distinct from capture time | Home TV desktop/listener and physical projector check; original-source failures need independent recovery |
| Upload queue/history folding and retry/status | Client source and delivered app; approval, preparation and visibility remain distinct | Family queue/recovery UX trial |
| Chinese-first UI and visible voice phases | Phone v58 / Web deployed; source/browser/emulator and large-text checks recorded | Device microphone/audio-focus and user perception |
| Text/audio original family contributions | Revisioned, attributed original and derivation contracts; collaboration/originals enabled | Family quality/recovery checks; not the assistant's transient audio path |
| Upload/folder annotation intake and automatic polish/tags | Source adapters/contracts present | Separate annotation intake off; provider/queue activation and source-quality review |
| Story/memoir composition, reviewed chapter sources, albums and reading continuity | Source supports protected composition/readers; separate manual chapter narration exists | Larger real-family story/album reading and contribution acceptance |
| Automatic story/title proposals, memoir editorial and reviewed editions | Source and generated qualification; source/derivation/consent and CAS guards | Generation/title/editorial/edition flags off; schema, model quality, paired backup and native delivery |
| Adjustable activity/shared-memory grouping | Manual group and time/similarity candidate contracts; source/version revalidation | Groups off; compatible schema/vector identity, withdrawal replay, native recovery and family adjustment trial |
| Private assistant threads/history and reply-language preference | Separate owned schema-v2 store, 30-day retention, idempotent requests and GET recovery; configured in v58 installation | Family/private account continuation checks; response length and voice pace are not applied |
| Foreground continuous voice | Explicit Start authorizes read-only listen → reply → listen; Pause/End and lifecycle fences | Real ASR/TTS/echo/latency trial; half duplex remains |
| Voice-turn timing | October 15 Web source shows four ephemeral client-observed stages after confirmed playback and next capture; default-collapsed, English/Chinese, no added request or transcript/audio retention | Real latency remains unmeasured; phone timing label follow-up and physical audio/family acceptance remain separate |
| Saved-story search, followups, current-card opening and opening speech | Deployed Web/API and signed phone v58; full-cohort/parent/source validation; typed actions explicit | Physical v58 trial; opening limited to 240 code points / 600 UTF-8 bytes |
| Assistant full-chapter continuation/progress and interruption | Design/next slice; manual reader speech is a separate implementation | Bounded segments, resume identity, cancellation/echo/quality qualification |
| Manual chapter narration segment progress | October 15 phone source shows current segment while preparing, speaking or paused; session-local | Signed delivery and physical audio acceptance; no persistent resume or assistant full-chapter speech |
| Memoir source-check status and retry | October 15 Web source shows status outside collapsed originals and explicit read-only retry | Served delivery and family trial; linked-source checking is not fact verification |
| Long oral-history withdrawal and replay | Internal default-off V4 journal/source prototype; author-only withdrawal retains raw sections and blocks revived source access | No HTTP/client/migration; journal upgrade, production admission and permanent erasure remain open |
| Model replacement and topology | Thirteen catalogued source capabilities; explicit typed projection for four target groups | Per-provider installation/licensing/resources/native quality; face/embedding projection and orchestration remain separate |
| OTA and recovery | Phone v58, TV v30; original signature/icon preserved; API startup trigger and five-worker restore verified | Installed-device acceptance; portable public operator controllers and paired recovery rehearsal |

## Acceptance rules

- A receipt is not upload approval, derived readiness, gallery visibility or TV publication.
- A catalog/manifest is not a loaded model, GPU placement or model-quality pass.
- A local test/debug build is not hosted CI, signing, live activation or physical acceptance.
- A source reference grants no new permission; account/library/revision changes fence late actions.
- Original contributions, transcripts, polished proposals and adopted story text remain distinct.
- The foreground voice session cannot save, share, erase or change access automatically.

See [Architecture](ARCHITECTURE.md), [Operations](OPERATIONS.md),
[Provider architecture](MODEL_PROVIDER_ARCHITECTURE.md) and the
[v58 test guide](../clients/android/docs/PHONE_V58_TEST_GUIDE_ZH.md).

## Oral-history intake source foundation

[Ordered local recording sections](ORAL_HISTORY_INTAKE_FOUNDATION.md) now have an
internal opt-in store with exact receipts, private author scope, manifest checks
and bounded quotas. Generated restart/retry/concurrency/refusal checks are source
evidence. This is not a deployed recording interface: withdrawal/replay, admitted
schema, transport, Web/phone capture and worker/native qualification remain open.

## Family memory hub direction

[Long oral histories and multiple-relative stories](FAMILY_MEMORY_HUB.md) are
planned: person/event relationships, resumable recording sections, reviewed
multi-speaker chapters and immersive books with source audio. Existing short
contributions and story/memoir editors are their foundation; automatic stitching
and long-session intake are not available yet. The [introduction website](../website/README.md)
uses fictional examples and original illustrations.

## Historical implementation and delivery notes

Earlier notes below preserve their original source/qualification context. Their
“pending”, “next” and release numbers are historical and are superseded by the
maintained matrix and dated Project Status. They are not the active backlog.

<details>
<summary>Expand earlier feature qualification notes</summary>

## Next local slice: conversational story actions

The [fluid assistant design](ASSISTANT_FLUID_EXPERIENCE.md) connects voice, chat,
current numbered story cards and protected readers. Local work adds negotiated
“读第二个故事” and “打开第一个故事” actions, ambiguity that retains the displayed
list, and cancellation guards. Delivered v57 stays the live baseline; this slice
is not yet qualified on Windows, signed, deployed or physically accepted.

Following priorities are chapter progress/continuation, measured latency and
qualified speaking interruption, then grounded storytelling and family quality
review. New providers and live editorial/grouping activation remain separate
qualification and operation gates.

## October 14 delivered: saved-memory opening speech and followups

API/Web source 4b69844 is served and phone **v57** is signed and published on
Windows HTTPS OTA. It includes v56 followups and explicit **朗读开篇** with
preparation/playback/Stop, fresh-source guards, microphone interruption and
enlarged-text layout fixes. Original icon/certificate and TV v30 are preserved.
Native qualification, stopped-writer backup, guarded recovery, eight running
tasks and independent complete HTTPS APK verification passed. See the
[delivery record](../clients/android/docs/PHONE_V57_RELEASE_2026-10-14.md).

Next priorities: family phone/member voice acceptance, an explicit voice intent
for reading the selected opening, then bounded full-chapter/multi-chapter
listening with progress, citations and cancellation. Evaluate grounded story
quality separately from release and service health.

## Opening-speech source and prior qualification

[Read opening](ASSISTANT_SAVED_MEMORY_READING.md) is an explicit action on fresh
assistant story/memoir cards. It reads the saved first-chapter narration or memoir
introduction with local TTS, rechecks all sources after synthesis, and exposes
preparing/playback/Stop in Web and phone. It ends voice and capture first; late,
recovered and old-scope output cannot start playback. Phone v57 is [delivered](../clients/android/docs/PHONE_V57_RELEASE_2026-10-14.md).
Local tests and enlarged renders pass; delivery is recorded above.

## Fixed v56 candidate: saved-memory conversational followups

[Followups](ASSISTANT_SAVED_MEMORY_FOLLOWUPS.md) let current saved-memory results
answer “介绍这些回忆”, “第二段回忆讲了什么” and “有哪些章节”. Web and phone
show ordered source cards and draft-only suggestions. Typed and foreground voice
requests bind the same current completed result; old history stays inert.
Source wording is transient, generic replies retain the existing private policy,
and no model or schema change is introduced. Phone v56 is [built and qualified on Windows](../clients/android/docs/PHONE_V56_RELEASE_CANDIDATE_2026-10-13.md).

This fixed candidate followed v55 and is now included in v57. Family voice/reader
acceptance remains open. Later work: richer grounded conversational
narration and evidence-backed story quality, with separately qualified providers.

## October 13 saved-memory reader delivery

API/Web source `c65528a` was served and phone v55 was published on Windows HTTPS
OTA with the original icon and certificate. Fresh search cards explicitly open
protected story/memoir readers after stopping voice and revalidating sources.
Native qualification, backup, eight running tasks, preserved ASR/TTS/OCR and
complete APK verification passed. TV remains v30. See the
[delivery record](../clients/android/docs/PHONE_V55_RELEASE_2026-10-13.md).
Physical owner/member and phone voice acceptance remain open.

## October 13 voice presence delivery

API/Web source `52c4c81` is served and phone v54 is published on Windows HTTPS
OTA. The [voice presence UI](ASSISTANT_VOICE_PRESENCE.md) now makes idle readiness,
confirmed listening, recognition, search, speech preparation, playback and pause
visible. Native qualification, stopped-writer backup, worker restoration and
complete APK verification passed. ASR/TTS/OCR are preserved; TV remains v30.
Original certificate and icon are unchanged. Physical phone and family voice
acceptance remain pending. See the [v54 delivery record](../clients/android/docs/PHONE_V54_RELEASE_2026-10-13.md).

## Earlier October 13 grounded voice delivery

API/Web source `5f92b94` was served and phone v53 was published on Windows HTTPS
OTA with the original certificate and icon. Stopped-writer backup, four database
integrity checks, served resource hashes and worker restoration passed; ASR/TTS
remain running and TV remains v30. Native complete APK readback and independent
Mac complete range readback match the signed file. Two Mac single-connection
downloads timed out; phone installation and actual listening remain unverified.
See the [v53 delivery record](../clients/android/docs/PHONE_V53_RELEASE_2026-10-13.md).

## Earlier source qualification records

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

The October 12 phone v50 delivery record documents HTTPS OTA publication, native
verification and an independent complete download; phone installation was a
separate gate at that time. A read-only native snapshot at 2026-10-13 13:00
Beijing later verified phone OTA v51 and API source `7daf740`. The existing phone
v52 source candidate is pinned to `7f8d92b` and pending publication. The new
grounded narration implementation is outside that immutable candidate, with
local qualification and delivery gates recorded below. These dated receipts
do not establish its live delivery. See the [v50 delivery record](../clients/android/docs/PHONE_V50_RELEASE_CANDIDATE_2026-10-12.md).

| Area | Implemented baseline | Remaining gate or next improvement |
|---|---|---|
| Library access | Protected membership, owner review, per-member auto-approval | Member-account and revoked-access device walkthrough |
| Upload UX | Folded progress/history, date hints and intake states | New-upload end-to-end receipt/probe/preview validation |
| Original memories | Text/audio contributions, consent, original playback; separate default-off D1 identity-bound family-note erasure and offline journal upgrade | Exact D1 migration/version 2 journal and native recovery qualification; multi-member family acceptance and retention/deletion walkthrough |
| Stories | Revisioned chapters, original-memory links, source inspection; manual memoir editing and reading in Web source; protected selected-media grouped creation with reviewed title suggestions; offline synthetic memoir/title quality cases and independent title-role capture | Human review and separate local-model quality qualification remain open; title provider stays disabled by default; plan-only fixtures are not model results; Web memoir flag and live migration remain off/unqualified |
| Phone | Reviewed voice memory, chapter source linking, family-memory home card, draft guards, v40 assistant recovery, OTA client, manual memoir arrangement, first-message previews, scoped conversation restoration, original-source inspection, explicit chapter/reply narration pause-resume, grouped-story creation, profile-derived optional bylines and explicit same-day media candidates | [Candidate picker evidence](../clients/android/docs/ANDROID_RELATED_MOMENTS_2026-10-09.md) records local checks separately from release package, live service and family acceptance; server/client delivery and enabled b1 service remain separate gates |
| Web | Chinese default, session recovery, story workspace, pending assistant recovery, explicit transcript review, bounded current-page assistant turn trail, manual memoir editor/reader, opt-in first-message previews, scoped conversation restoration, explicit narration controls and original/derived source inspection; generated-data Web profiles have revision-specific results below | Conversation navigation has 23 checkpoint groups; the full community journey has its own result. Earlier 16/17/20/22 counts remain historical. These and the source-inspection/narration journeys are synthetic browser evidence; b1 service defaults off, with no household migration or live owner/member acceptance |
| TV | Named libraries, OTA, paced viewing | Latest installed projector navigation and playback |
| Voice assistant | ASR input, explicit submission, receipts/context, pending-turn recovery, optional TTS, scoped story/memoir conversation navigation and current-reply clarification cues in Web and phone | [Grounded result narration](ASSISTANT_VOICE_RELIABILITY.md#grounded-result-narration) is limited to three current ordered cards, card kind and valid recorded `taken_at` date, with unknown dates explicit; preserve the v1 envelope/context and validate again after TTS. Source implementation, provider quality and family/device delivery remain separate gates |
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

The [voice reliability contract](ASSISTANT_VOICE_RELIABILITY.md) adds exact
asset-number lookup/open inside the current library, distinct safe ASR errors,
and negotiated completion/failure/cancellation events for both manual and
continuous reply playback. Navigation-free recovery and older v1 receipt
compatibility remain enforced. This next source candidate is separate from
the installed phone and active server release.

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

The phone now presents the selected conversation in a compact summary and folds
management controls behind an accessible local toggle. History, editing and
explicit continuation remain visible; the panel keeps recovery controls open
when state is unresolved. Its 19-case simulator cohort passed at Chinese 150%
text, followed by a focused composer-helper/byte-limit rerun. These UI changes
are not in the pinned v51 candidate at `3a56870`; they did not create a signed
APK. See the [current source qualification](DEVELOPMENT.md#october-13-compact-phone-conversation-controls).


[Private history navigation](PRIVATE_ASSISTANT_HISTORY_V1.md) adds ephemeral
first-question labels and explicit older pages, preserving complete saved text
and a fixed thread snapshot. A concurrent revision requires explicit reload.
Phone/Web history remains readable when discovery is unavailable, with no
automatic result hydration, speech or microphone capture. This is locally
qualified source; Windows storage/activation and a signed phone release remain
separate delivery gates.

[Saved-memory discovery](ASSISTANT_SAVED_MEMORY_CARDS_V1.md) now has a default-off
backend negotiated endpoint and optional capability probe, in addition to
literal kind-filtered search, revision-bound reader references and transient
typed projections. Base capabilities remain unchanged; opt-in is accepted only
for a fresh request, while same-ID replay returns stored status before fresh
negotiation. History keeps the legacy 30-day summary and non-actionable typed
reference counts. Web renders immutable plain-text cards after the separate
probe, with legacy fallback and scope/capability fences. Nine focused HTTP
checks, 45 controller checks and six generated browser checkpoints passed.
Saved-memory reply TTS now revalidates typed sources before and after synthesis,
behind a separate optional probe; no source prose is passed to TTS. The final
controller and browser follow-up passed 49 checks and eight checkpoints.
Capability loss stops active playback and revokes transient audio. Phone cards
and reader opening remain outstanding;
no live flag or API was activated.


[Protected private reply speech](PRIVATE_ASSISTANT_REPLY_SPEECH_V1.md) is the next
local candidate: it reads the completed reply instead of only a result count.
Clarifications and empty results can continue an explicitly started voice
session after playback; unsupported requests pause for review. The server owns
the spoken text and enforces the current turn revision, membership, parent
receipt and transient audio limits. Its separate runtime flag defaults off.
Source and generated-client qualification are complete; native Windows checks,
activation and a matching signed phone release remain separate delivery gates.


</details>

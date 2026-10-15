# Product roadmap

Active priorities after the **October 15 v60 delivery**. [Features](FEATURES.md)
lists existing capabilities, [Project Status](PROJECT_STATUS.md) distinguishes
live gates and [the architecture review](ARCHITECTURE_REVIEW_2026-10-14.md)
records maintainability findings. Dated history is preserved below.

## Current priority: make natural-language search useful

The owner's October 15 feedback pauses new story-creation UX. First fix ordinary
query forms, connect existing text/confirmed people to scoped retrieval, restore
useful video-date evidence and then qualify typed local language understanding
and relevance ranking. See the [search diagnosis and implementation plan](ASSISTANT_SEARCH_REVIEW_2026-10-15.md).
The current local parser/coverage-message patch is not yet deployed. v60 device
feedback remains useful, while the broader sections below retain the backlog.

The [first negotiated text/person API slice](ASSISTANT_JOINT_SEARCH_V2.md) now
joins current photo notes/captions and reviewed identities in a protected,
source-bound request-time projection. The local Web/phone integration now shows
the chosen perspective, interpreted conditions and match reasons, and preserves
the original search version through private-workspace recovery. The current
qualification and delivery boundaries are recorded in [Project Status](PROJECT_STATUS.md).
Next admit the reviewed person/text index for a real library and qualify a small
owner-reviewed query set, then improve video date bases and local semantic
understanding/ranking. Source checks and synthetic results do not establish
real-library readiness or relevance. Private kinship activation still requires
verified account/library/person bindings; future-account approvals grant no
access until those bindings are confirmed.

The next acceptance set should cover a named person and the equivalent relative
chain, two people together with a scene, a follow-up year/media restriction,
opening the second current result, short names overlapping place words, unknown
dates, no matches and an account without kinship permission. Keep household
queries and relevance judgments in the private operator record. Record expected
people and hard filters, top-result relevance, missing-source explanations and
observed latency separately; improve
ranking only after incorrect identity/date/filter behavior is resolved.

## 1. Accept the delivered experience

Run the [v60 phone/Web trial](../clients/android/docs/PHONE_V60_TEST_GUIDE_ZH.md)
with owner and member accounts: fresh saved-story search, opening the right card,
reading its saved sections, actual playback before Continue/relistening, Pause/End,
account/library change and recovery. Complete TV v30's physical named-library and playback
check when the desktop/projector is available.

**Exit:** device version and scenario-specific observations/receipts, including
Chinese clarity and large-text/remote usability. Source/emulator results and
publication remain separate from family acceptance.

The delivered October 15 source adds a collapsed Web **Last turn timing** summary
for four client-observed stages. It appears only after confirmed playback and
the next microphone is ready, and clears on interruption or scope change. It
does not add a request or claim provider latency; the [timing note](VOICE_TURN_TIMING.md)
records the synthetic browser evidence and completed phone label checks. Web
gallery thumbnail failure now has an explicit localized fallback; protected
phone previews and optional Home TV publication retain their separate access
and delivery boundaries. Real ASR/TTS latency, physical listening and family
acceptance remain in the trial above.

## 2. Make assistant reading and conversation fluid

API/Web `53e3954` and phone v60 are delivered with complete local/native
qualification, verified backup, worker restoration and original-certificate OTA
readback. The [release record](../clients/android/docs/PHONE_V60_RELEASE_2026-10-15.md)
records exact artifacts; family acceptance remains ahead of broader narration.

v60 includes [temporary reading-size controls](READER_TEXT_SIZE.md),
[explicit preview recovery](READER_PREVIEW_RECOVERY.md), compact phone memoir
navigation and a [first-story guide](FIRST_STORY_GUIDE_ZH.md). Assistant
[saved-section narration](ASSISTANT_SEGMENT_READING.md) reads a first chapter or
memoir introduction in explicit segments. Successful playback enables Continue;
Stop and source/scope changes clear progress. Voice-requested continuation and
hands-free advancement to later chapters remain future work.

Add bounded chapter narration/continuation with explicit progress and resume,
source citations, current story/book/chapter revisions and robust cancellation.
Reuse the existing manual chapter reader's guards; do not duplicate playback
ownership or make local completion navigate without a current user intent.
Measure capture/ASR/processing/TTS/playback latency before streaming or speaking
interruption. Keep microphone consent and Pause/End visible; qualify echo and
audio-focus handling before permitting microphone/speaker overlap.

**Exit:** current-source segment identity and resumption, no replay after recovery,
Chinese/English enlarged UI checks, latency measurements and physical speech
acceptance. Scope/default behavior and legacy clients remain explicit.

The later source round compacts reading controls and follow-up labels, adds
explicit composer shortcuts, preserves user focus during delayed reload recovery
and exposes TV preview retry directly in the gallery. These phone/Web changes are
delivered in v60; TV preview retry remains an unpublished v31 source candidate. Physical acceptance remains separate.

## 3. Improve grounded family storytelling

After the current search work, resume the guided first saved story: choose a few related frames,
keep one shared narrator statement, review an editable title/attribution and
preview before explicit save. It should reuse the existing authorized picker,
draft and save/retry contracts. It must not copy that statement silently into
every asset or turn a photo note into a published story. A private fictional
three-step prototype was checked separately from v60; it is not an implemented
application workflow. See the [first-story guide](FIRST_STORY_GUIDE_ZH.md) for
the current manual path.

The synthetic corpus now has eight cases, including cross-event visual
similarity and separate subject/speaker/uploader attribution. Its planner and
canary contract checks do not establish model output quality. Next add an
explicitly approved family quality corpus for titles,
attribution, multi-photo activities, essay/chronicle/memoir forms and conflicting
contributions. Preserve original words/audio, source IDs and uncertainty; suggestions
stay reviewable. Narrative, polishing and title roles keep independent contracts.
Qualify a provider/profile and a compatible schema/backup/recovery plan before
activating generation, title suggestions, editorial or editions.

**Exit:** source-faithful proposals and measurable family/editorial quality,
explicit adoption and no unsupported factual propagation. A newer/larger model
is not a substitute for those checks.

## 4. Activate adjustable memory grouping carefully

Use capture-time evidence and qualified image similarity as candidates; keep
filename/download/received dates labeled as weaker hints. A shared original note
must remain one attributed source with reviewed links across the selected cohort.
Manual adjustment, current membership, withdrawal and restore replay remain required.
Groups/vector identity need the prepared schema and native lifecycle gates.

**Exit:** source/model/preprocessing identity, stable review/edit behavior, deletion/
restore qualification and family confirmation of suggested grouping. No silent
copy of a memory into unrelated photographs.

## 5. Make the open-source stack maintainable and deployable

- Extract reviewed private release/recovery logic into generic, fail-closed public
  controllers using synthetic fixtures and selected private manifests.
- Replace scattered dated readiness claims with the maintained status/feature
  map and capability/schema acceptance profiles; preserve strict client negotiation.
- Extend typed provider wiring for face/embedding roles only with complete identity,
  resource, shadow comparison and migration/reindex evidence.
- Remove Home TV's interactive-session dependency through a separately qualified
  operator plan; preserve its publication and LAN access boundaries.
- Keep one writer per artifact, portable paths, original signer continuity, paired
  multi-store backups and no weights/secrets/household data in Git.

**Exit:** a clean-checkout synthetic release/recovery rehearsal, clear installation
and rollback instructions, reviewed provider manifests and reproducible source
checks. Live service/task changes, migrations, signing, publishing and legacy
repository retirement still need their operation authority.

October 15 source now adds a portable read-only [API package inspector](API_PACKAGE_INSPECTION.md).
It binds the entire canonical archive to reviewed local Git blobs and a fixed
hash, with generated corruption/path/race checks. It does not extract, execute,
deploy or replace native runtime qualification. Public signing and live cutover
controllers remain later work.

## 6. Build the family memory hub

The [family memory hub design](FAMILY_MEMORY_HUB.md) adds person/event-centered
oral-history projects: long accounts recorded in resumable bounded sections,
several relatives contributing with attribution, and reviewed chapters/books
that can be read alongside original voices and media. This is future work;
current short contributions do not provide a long recording transport.

Start with subject/account/speaker identity and consent boundaries, durable
section receipts, interruption recovery and complete source citations. Then
qualify a multi-speaker editorial pilot before activating automatic stitching.
Manual links and revisions remain available throughout. The separate project
introduction uses fictional examples/cartoon illustrations, never family media.

**Source progress:** the [intake foundation](ORAL_HISTORY_INTAKE_FOUNDATION.md)
implements bounded ordered WAV sections and exact receipts with generated
reopen/concurrency/rollback evidence. It stays internal and default-off; no
transport, migration or recorder is delivered. Withdrawal, journal replay and the
internal V3→V4 writer-fenced upgrade primitive are implemented and tested. The
remaining sequence is operator/native upgrade qualification, production admission
and erasure, then a client pilot that clearly distinguishes saved and retrying.

October 15 source work implements author-only retained-source withdrawal and
V4 journal prefix replay with generated fixtures. Qualify an operator upgrade
controller, native admission and permanent erasure before exposing the long
recording transport. See [withdrawal](ORAL_HISTORY_WITHDRAWAL.md).

The source now includes the internal V3→V4 upgrade primitive with writer-fence
and final revalidation tests, plus a [five-group / twelve-case generated rehearsal](ORAL_HISTORY_QUALIFICATION.md)
covering durable section receipts, populated legacy preservation, withdrawal,
older-prefix replay and interrupted paired commits. The frozen v59 archive
retains its four-group / ten-case proposal. It does
not yet include an operator upgrade controller, native upgrade qualification or
live migration.

Reader polish now includes visible Web source-check/retry state and ephemeral
phone manual-narration segment progress. Assistant full-chapter continuation and
physical audio quality remain open; see [reader UX](READER_PROGRESS_AND_SOURCES.md).

**Exit:** accepted recording sections survive retry/restart; conflicting accounts
retain their speakers; proposed prose is faithful and adopted explicitly;
permissions and source-withdrawal/restore tests pass before family use.

## Delivery discipline

Work in bounded slices and keep one main development repository. Local source,
CI, packages, live services, installed clients and physical/family quality are
separate gates. Do not republish or activate an optional feature as a side effect
of editing documentation. Historical video errors need independent sources or a
separately reviewed salvage plan; resume only unfinished conversion work.

## Historical implementation and delivery notes

The earlier chronological notes below retain their revision and acceptance
context. Their old “next”, “pending” and “live” claims do not override the
active priorities above or current Project Status.

<details>
<summary>Expand earlier roadmap and release notes</summary>

## October 14 delivered: conversational story actions

The [fluid assistant design](ASSISTANT_FLUID_EXPERIENCE.md) connects voice, chat,
current numbered story cards and protected readers. Local work adds negotiated
“读第二个故事” and “打开第一个故事” actions, ambiguity that retains the displayed
list, and cancellation guards. The [fixed v58 candidate](../clients/android/docs/PHONE_V58_RELEASE_CANDIDATE_2026-10-14.md)
passed Windows synthetic qualification and its API/Web source is now deployed.
[Phone v58 is signed and published](../clients/android/docs/PHONE_V58_RELEASE_2026-10-14.md);
TV OTA stays v30. Physical installation and family acceptance remain pending.

Following priorities are chapter progress/continuation, measured latency and
qualified speaking interruption, then grounded storytelling and family quality
review. New providers and live editorial/grouping activation remain separate
qualification and operation gates.

## October 14 delivered: saved-memory opening speech and followups

The earlier delivery served API/Web source 4b69844 and published phone **v57**
on Windows HTTPS OTA; it is superseded by v58 above. It includes v56 followups and explicit **朗读开篇** with
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

The [implemented source](ASSISTANT_SAVED_MEMORY_READING.md) resolves current
story openings and memoir introductions for bounded local TTS, revalidating the
full source cohort before and after synthesis. Private replies keep generic
wording. It is outside fixed v56. Web and phone now provide explicit one-shot
controls with Stop, fresh-result guards and no automatic listening restart;
phone v57 is [delivered](../clients/android/docs/PHONE_V57_RELEASE_2026-10-14.md). Local acceptance is recorded in Development.

Next: complete family acceptance for delivered v57, then add a separately reviewed
voice intent for reading the selected opening. Full-chapter/multi-chapter
listening needs bounded segments, current citations, progress and cancellation;
source-grounded conversational storytelling also needs family quality review.

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

The [voice presence UI](ASSISTANT_VOICE_PRESENCE.md) is served in API/Web source
`52c4c81` and published as phone v54 with the original icon and certificate.
Native qualification, backup, restored workers and full APK readback passed;
TV remains v30. See the [delivery record](../clients/android/docs/PHONE_V54_RELEASE_2026-10-13.md).

Next: owner phone update and actual listen → reply → listen acceptance, including
visible microphone states, Pause/End and foreground interruption. Continue
saved-story/memoir retrieval with visible evidence and portable release tooling
after this device check; fixture and publication checks remain separate evidence.

## Earlier October 13 grounded voice delivery

API/Web source `5f92b94` was live; phone v53 was published with the original icon
and certificate. Native full APK and independent Mac complete range verification
passed, five upload workers were restored, and ASR/TTS remain running. TV remains
v30. The earlier v52 package stays unpublished and preserved. See the
[delivery record](../clients/android/docs/PHONE_V53_RELEASE_2026-10-13.md) for
the Mac single-connection download limitation and separate device acceptance.

Next: verify family phone updates and actual listen → reply → listen behavior;
then improve retrieval across saved stories and memoirs with visible evidence,
and make the Windows release tooling portable with executable preflight checks.

## Earlier October 13 private conversation continuation plan

The source and runtime pins in this roadmap are dated evidence. A read-only
native snapshot at 2026-10-13 13:00 Beijing verified phone OTA v51 and API
source `7daf740`; it does not show the new local narration as deployed.
The existing phone v52 candidate remains pinned to source `7f8d92b` and pending
publication. The local narration implementation described below is outside
that immutable candidate; its delivery remains pending.

The [server-owned turn contract](PRIVATE_ASSISTANT_TURNS_V1.md) now has local
implementation for an isolated schema-v2 request ledger, revision-bound search
context, account/library ownership, idempotent request recovery, fixed retention
and response-language preferences. Web has conversation selection, complete
recent-history text, GET-only recovery, and explicit deletion. The phone SDK and
coordinator are wired behind the existing assistant capability, with a separate
private conversation panel. Explicit “继续聊天” and “在这个对话中语音聊”
continue the same private thread through central text or foreground voice;
recoveries pause without replaying audio or navigation. Installed v50 remains
the package version in the earlier delivery note; a later read-only snapshot
verified phone OTA v51. These dated package records are separate from the current
source candidate.

[Conversation labels and older-history paging](PRIVATE_ASSISTANT_HISTORY_V1.md)
now add explicit full-text page reads at a fixed thread revision, ephemeral
first-question labels, and history access while discovery is unavailable.
Concurrent updates require explicit reload without losing a draft.

Current qualification and delivery gates are recorded in Development. These
changes do not publish an APK, create a Windows conversation database, or change
the live API. In the dated native snapshot above, phone OTA v51 was verified;
TV v30 remains the last recorded TV package. Neither statement is a live check
performed by this roadmap update.
The phone management panel now starts compact, preserves readable history and
explicit text/voice continuation, and expands management locally; the generated
19-case 150% simulator cohort and a focused composer-limit rerun passed. This UI
source is outside the pinned v51 candidate at `3a56870`, and no new signed APK
has been made.

The next slices are:

1. Complete the private conversation release-package/native qualification,
   preserving account/background erasure and v1 compatibility.
2. Qualify and deliver the implemented bounded narration of current ordered
   results under the [voice reliability contract](ASSISTANT_VOICE_RELIABILITY.md).
   Local source now supports result introductions and recorded-date follow-ups,
   with source revalidation after TTS and no schema, route, provider or
   preference-negotiation change. Native listening and family feedback remain.
3. Prepare explicit Windows private-store provisioning and an exact API/phone
   release with rollback; runtime activation and publication retain their gates.
4. Add grounded story/album/memoir tools and richer spoken replies only after
   local provider qualification; then evaluate real family conversation quality.
5. Evaluate the delivered private thread experience with real family questions,
   including phone interruption/recovery and language clarity.

## October 12 central personal assistant

The owner approved [拾光助手](PERSONAL_ASSISTANT.md): a central phone/Web chat
workspace, visible media/story cards and private per-user experience. One explicit
foreground Start authorizes read-only listen → reply → listen until Pause/End;
saving or changing family material retains a separate reviewed confirmation.
The synthetic [interactive prototype](assistant-design/prototype.html) was reviewed.

Phone v48 saved memoir editing has been signed and published to phone HTTPS OTA;
Windows and independent Mac complete-download checks passed. TV OTA remains v30.
See the [v48 delivery record](../clients/android/docs/PHONE_V48_RELEASE_CANDIDATE_2026-10-12.md).
Installed-phone and family acceptance remain pending.

The first workspace/voice source slice and isolated storage foundation have
local qualification recorded in [Development](DEVELOPMENT.md#october-12-central-assistant-foundation).
Phone v49 is published on HTTPS OTA; native and independent complete downloads
passed. The Web workspace is served after its separate API-action switch; native and
independent HTTPS checks passed. Owned history/preferences APIs are now source-qualified,
default-off and not deployed.

Phone v50 is now signed and published on phone HTTPS OTA, restoring the original
user-approved artwork and distinguishing update outcomes. Native and independent
complete download checks passed; installed-phone acceptance remains open. See
the [v50 delivery record](../clients/android/docs/PHONE_V50_RELEASE_CANDIDATE_2026-10-12.md).

Remaining implementation follows these layers:

1. Complete family acceptance of the delivered phone v49/Web workspace and
   foreground voice retrieval using the existing protected v1 contract. Its
   speech capability reads result counts;
   clarification and unsupported replies pause for review.
2. Integrate server-owned turns and client continuation with the qualified private
   thread/preferences APIs; admit separate storage explicitly, keep 30-day exchange
   retention and apply only supported presentation preferences.
3. Local grounded understanding, evidence-backed archive questions and typed tools
   for stories/albums/memoirs. Model and provider qualification precedes activation.
4. Reviewed proposals and explicit personal memory; contextual story handoffs,
   richer spoken replies, cross-device continuation and opt-in TV presentation.

The design approval authorizes development, not an unqualified runtime switch.
No conversation database, new provider or autonomous writing is activated by a
source build. Continuous capture is foreground-only and always visibly stoppable.

## October 12 conversation and reading follow-up

The phone [story/memoir history](PHONE_MEMORY_CHAT_NAVIGATION.md) now has a direct
latest-message action and guards detached page controls (`7d7b1ef`). Four
bilingual large-text simulator journeys passed, preserving unsent words and
explicit voice/submission boundaries. Explicit original memoir chapter/story
selection now brings its heading into view (`1094890`); the two contents and
three affected narration journeys passed. [Assistant result compatibility](ASSISTANT_RESULT_COMPATIBILITY.md)
at `c566ded` repairs seven-field server result decoding and labels optional
filename/received dates, with parser, protected transport and bilingual emulator
checks. Signed phone and served delivery remain separate.

The [full-conversation continuation](MEMORY_CHAT_CONTINUATION.md) slice now has
backend, Web and phone source implementations. The allowlisted
`memory_conversation_full` discriminator (`e042544`) keeps other 429s distinct.
Web `54f323b` and phone generated checks preserve old history and rejected words,
reuse one uncertain creation request, verify fresh history and leave the new
draft editable until Send. The complete backend profile passed 1,210 tests and
692 subtests, and all 19 Web suites passed with unchanged source snapshots at
`a1c6e94`. Four bilingual phone continuation journeys passed at 150% text size;
served Web, signed phone and family conversation quality remain delivery gates.

[Creating a phone memoir](PHONE_MEMOIR_COMPOSITION.md) from existing saved
stories is accepted at `e157679`. It supports readable-story selection, ordering,
an optional reviewed voice introduction, exact uncertain-save retry and explicit
opening of the fresh protected result. The 161-case core cohort and four
bilingual enlarged-text composer journeys passed; six shared dictation journeys
also passed. Opening the composer starts no model work or narration.

The visual phone shelf is accepted at `61847c7`, with protected covers, opening
excerpts and accessible reading actions. Its 125-case core cohort, two bilingual
150% shelf journeys and nine affected reader/composer journeys passed. Web
`a6bae31` guards obsolete shelf cards and delayed detail/denial responses;
30 focused browser checkpoints passed, including conversation-hint retention.

[Reviewed Web memoir introduction dictation](MEMOIR_INTRODUCTION_DICTATION.md)
is integrated at `bd8f6b6`, including shared microphone ownership, current-form
story ordering and bounded introduction review. Generated Node UI and adapter
checks passed; the recording correction at `cd87ab2` passed its focused browser
journey. Final complete-profile evidence is in [Development](DEVELOPMENT.md).
[Opening narration](MEMOIR_INTRODUCTION_NARRATION.md) is accepted at Web
`a8e8b47` and phone `6f140f8`, with 30 browser checkpoint groups and nine
opening/reader emulator cases passing. Enlarged bilingual renders were inspected.
Phone `a4507e3` reserves v47 for a new signed release after its private profile
and served capabilities are qualified. Following source qualification,
the next delivery gate is the complete release closure, then approved native
qualification and publication. At `263439c`, all 19 Web suites and the complete Android JVM/lint/debug
profile passed with unchanged source; nine opening/reader simulator cases and
bilingual enlarged-text inspection also passed. The public v47 release compiled
unsigned and unconfigured. The final phone narration correction at `466ada2`
also passed 28 simulator cases and the complete unchanged Android profile at
`0548d8c`; its rebuilt unsigned APK supersedes the earlier package. Family story
quality and time/similarity group boundaries still require real feedback.

## October 11 adjustable shared-memory groups

Capture-time and qualified image-similarity proposals now have a default-off
protected API and a Web photo-viewer editor. Groups retain original note IDs,
ordered media IDs, theme and sticky exclusions. Reads preserve the latest
original wording and author; no note or audio is copied into group history.
Users explicitly save and can adjust members and linked sources. Missing dates
and unavailable vectors retain manual selection; video grouping is manual.

Additive `e7c1a9d5b304` migration and companion approved-upload worker compatibility
are prepared locally. The six-hour/0.9 similarity rule is a heuristic awaiting
family calibration. See [the contract](../server/docs/security/MEMORY_GROUPS_V1.md).
The original implementation was checked locally; the later native qualification
evidence is listed below. The live feature is not activated.

Generated e7 upgrade and pre-/post-group backup restoration passed on Windows
at source `665bed5`, with independent source/database readback. This did not
make or restore a live backup. The subsequent `18eb1cc` native full-chain and
CPU/video companion canary also passed independent readback. Next delivery gates:
prepare the stopped-writer backup/restoration and compatible worker/API switch;
approve live migration and activation. Automatic suggestions separately need exact
prepared-vector profile/coverage and protected lookup qualification on Windows. The phone has a default-off group review/edit source implementation; its release and live API availability
remain delivery gates. Shared-source integration is now implemented locally:
reviewed group notes enter story and memoir evidence with their canonical origin
and byline, deduplicated for generation and chapter references. Source changes
invalidate stale saves/jobs; no note text is copied into saved source links.
See [the shared-source contract](SHARED_MEMORY_STORY_SOURCES.md).
The local source now implements [reviewed chapter source choices](CHAPTER_SOURCE_CHOICES.md):
authors can choose which notes and observations may inform each chapter,
including none. Narrative, conversation and title context honor this explicit
policy; legacy stories retain their existing behavior. Web and phone source controls
have passed their focused browser/emulator checks. The complete backend profile
passed 1,208 tests and 687 subtests at `d0d8a34`; newer client qualification and
delivery remain separate. [Spoken chapter writing](STORY_CHAPTER_DICTATION.md)
is implemented locally in phone and Web with explicit transcript review; the
full 19-suite Web profile passed at `5991695`.
[Saved phone story editing](PHONE_SAVED_STORY_EDITING.md) is implemented at
`6e3bfc8`, preserving accepted family-memory links and unsaved words through
failed conflict reloads. [Phone reading continuity](PHONE_STORY_READING_CONTINUITY.md)
now offers an explicit resume after a fresh authorized read, with encrypted local
location metadata. [New chapter arrangement](STORY_CHAPTER_ARRANGEMENT.md) lets
authors split and merge reviewed new drafts in Web and phone, retaining media
order and original sources. Family feedback on suggested group boundaries and
longer-story composition remains a following product gate.
The [Web source-conflict recovery](WEB_STORY_SOURCE_REFRESH.md) now renews a
reviewed new draft's references without replacing its manually arranged chapters
or mounted text controls. It requires fresh source review before another save;
29 focused generated browser checkpoint groups passed at `acb9036`.
The phone source at `b3ddd57` completes [album-to-story selection](PHONE_ALBUM_TO_STORY.md),
so an existing ordered album can prepare a story without selecting every moment
again. The complete Android source profile and bilingual simulator journeys
passed; release and family acceptance remain separate from these checks.
The compact selection controls at `4ef7255` retain the visible selection limit
and fold secondary album/theme/language controls. [Memoir reading continuity](PHONE_MEMOIR_READING_CONTINUITY.md)
at `c3e2706` preserves an exact, encrypted location and offers it only after fresh
parent/child checks. [Explicit next-chapter narration](MEMOIR_NARRATION_CONTINUATION.md)
at phone `92b1285` and Web `ce2467c` extends listening within one story; finishing
alone does not advance or start another chapter. The phone complete source
profile passed with a 945-test report inventory, lint and debug builds.
These slices still require served/signed delivery and a family walkthrough.
Phone `a0fdbca` now adds collapsed original memoir contents and guarded direct
story/chapter selection, with nine generated emulator journeys and a complete
949-test Android report inventory. Web `210222b` adds scalable numbered media
captions and fences old media actions, with 27 focused checkpoint groups and
the complete 19-suite profile. The bilingual enlarged-text renders were
inspected; none of these source checks publishes an update.
Do not automatically publish private memories to Home TV.

### Guarded activation preparation

An October 11 read-only runtime query found the primary still at a0, despite
newer deployed source. The new guard therefore requires an explicit starting
revision and rehearses the complete additive a0→e7 chain, preserving every old
row and object while adding nine empty tables. Its generated interruption rolls
back the earlier editorial/edition steps as well as the partial identity step.
The companion canary exercises actual CPU and video worker CLIs on generated
media; portable tests mock native worker execution. The pinned API qualification
package contains the required worker closure. The new canary passed its approved
Windows run at `18eb1cc`; independent
readback verified all source hashes, the nine empty added tables, unchanged old
rows, exact queues and decoded previews. Live stopped-writer backup/restoration,
compatible worker/API switch and feature activation remain outstanding. See the
[guard and maintenance sequence](../server/docs/security/MEMORY_GROUP_SCHEMA_APPLICATION.md).

### Phone shared-memory review

The protected phone detail view has an explicit shared-memory entry. Users can
link current original notes, select related images, manually include videos,
change the theme, exclude suggestions and adjust existing groups. Suggestions
stay anchored to the original image; removing that anchor from an existing
group disables further suggestions until it is restored. Saves require a
review and confirmation; uncertain responses retain the same mutation for retry.
Account, library and background changes clear the editor and preview cache.
The feature is absent from anonymous Home mode and TV. See the
[phone contract](PHONE_MEMORY_GROUPS.md).

### Delivery preparation

A generated e7 upgrade/restore runner is included in the pinned API package.
It rehearses additive row/schema preservation, injected DDL interruption,
original note attribution and exact group retry, pre-/post-group backup restore,
and nonempty downgrade refusal. It has no live database/media arguments and
uses the existing bounded Windows Job controller. See the
[qualification contract](../server/docs/security/MEMORY_GROUPS_V1.md#generated-upgrade-qualification).
The generated runner passed its approved native Windows run at `665bed5`;
independent readback verified 180 source files, six generated databases and both
backup restores. See [the native result](WINDOWS_CPU_CHECKS.md#october-11-memory-group-native-result).
The subsequent native full-chain and CPU/video companion result at `18eb1cc`
is recorded in [the new native result](WINDOWS_CPU_CHECKS.md#october-11-full-chain-and-companion-native-result).
Installed model/vector qualification and live activation remain separate.
Phone version 46 is already
published from older source; the next group-enabled release needs a new version
and complete newly pinned private profile before signing or OTA publication.

## October 11 native qualification follow-up

The corrected package at `b8f103b` passed all three bounded Windows synthetic
vector cleanup/catalog cases: process interruption after quarantine linking,
older-primary restoration using the archived closure, and corrupt-quarantine
refusal. Independent readback verified 172 source files, the report digest,
private storage, database progress, expected vector names and unchanged generated
originals. See the [exact native result](WINDOWS_CPU_CHECKS.md#october-11-vector-catalog-native-result).
The earlier `1db984c` failure remains retained; its 294-character fixture path
has been replaced with a 246-character layout. The runner now checks legacy
path budgets before mutation and retains sanitized fixture failure receipts.

The next gates are additive schema/backup restore compatibility, independent
catalog backup coverage, the exact installed producer profile and interrupted
task reconciliation. Power-loss durability remains unqualified. Preserve the
capture-day story picker until the visual-discovery delivery gates pass.
No live database, model, worker or service was changed by this qualification.

## October 10 installed release and next gates

The protected API/Web release at `489460b` has passed Windows synthetic
qualification and live HTTPS asset, icon, OTA and anonymous-access checks.
A stopped-writer backup covered the main database and both journals; the schema
and existing feature settings were preserved. The five existing approved-upload
workers were restored with their task definitions unchanged. Phone v46 and TV
v30 remain the published OTA releases; the owner reports installing phone v46.
These checks do not establish a new family upload or conversational voice turn.

Home TV recovery remains pending an interactive Windows desktop session. The
small-model comparison has not produced an inference result: the GPU query
passes outside the supervised Windows job and fails inside it. Keep the existing
provider configuration until bounded native execution, exact GPU residency and
human Chinese story/voice reviews pass. Generation and title-provider activation
remain separate gates.

A read-only diagnostic confirmed the configured 24 GiB Job cap and observed
about 11.4 MiB peak Job commit, while the GPU query still returned an NVML
unknown error. This does not establish the cause: a rejected allocation can
fail without raising the recorded peak. No model inference passed, and no
resource limit or live provider was changed.

The shared-story foundation now has an optional immutable image-vector record
contract and a protected, bounded library-scoped reader. These are source-only
contracts with synthetic fixtures: there is no migration, route or picker
activation. An optional internal producer now connects the verified profile to
publication and exact task completion. It recovers prepared files before model
loading, preserves interrupted claims and skips completed profiles. Legacy
embeddings lack checkpoint and preprocessing identity and must not be promoted
by guessing those values. The V3 asset-withdrawal source contract now adds exact
content-free tombstones, atomic offline restore replay and receipt-bound
all-version cleanup planning. It preserves legacy journal digests and rejects
uncommitted primary status. No live format upgrade or physical erasure is enabled.
The optional filesystem executor now covers prepared publications and completed
artifacts with a committed manifest, checksum/identity checks and recoverable
no-overwrite quarantine claims. Original media and immutable metadata remain
retained; interrupted task reconciliation is separate. A private independent
catalog now preserves complete plans and can restore matching missing metadata
into an older primary after withdrawal replay. The generated qualification runner
checks process interruption and restoration; its bounded Windows CLI later passed
the three named synthetic cases at `b8f103b`. The next gates are additive
schema/restore compatibility, installed producer qualification and the protected reviewed
picker. See [vector erasure](VECTOR_ERASURE_LIFECYCLE.md).
Journal and actual-worker recovery pass generated
process-death tests;
installed producer recovery, power-loss qualification and actual vector coverage
remain open.
The source image worker now hashes the inspected checkpoint before and after
provider loading and after inference, and compares child receipts with the
startup probe. Receipts describe the realized supported OpenCLIP evaluation
transforms, source digests, package versions and vector dimension. These are
synthetically checked snapshots, not installed-provider qualification; they
populate the optional immutable table only through the internal opt-in producer,
which has no CLI activation switch. They do not backfill legacy rows.
The existing image worker now fences task completion and failure against the
exact claimed payload/start/retry fields. These are source changes; installed
workers still use their previously verified release. Preserve the current
capture-day picker until producer, lifecycle, native coverage and reviewed
picker gates pass.
See [activity grouping](ACTIVITY_GROUPING_DESIGN.md) and
[provider qualification](MODEL_QUALIFICATION.md).

## October 10 source delivery and reader refinement

PR #13 is merged after its pinned API, Android and Windows private-reader jobs
passed. Its conversation recovery, explicit transcript review, same-day story
picker and lifecycle fixes are reviewed source. Those changes are now included
in the installed API/Web source and published phone v46; family/device behavior
remains a separate acceptance tier.

PR #14 is also merged after four hosted jobs, including the new native Windows
CPU cohort. Its recording lifecycle, story readers and TV recovery are reviewed
source. PR #15 is merged at head `cd982a9` after all five hosted jobs passed,
including seventeen generated Web suites on the locked Ubuntu browser toolchain.
The Web job covers note-save, microphone startup, readers and story workspaces
without household credentials or media.

The reviewed reader slice adds a protected Web filmstrip and scope-bound phone frame
selection, with localized position labels, enlarged-text chapter controls and
explicit navigation. See [reader behavior](STORY_READER_NAVIGATION.md). Browser
microphone startup also rejects stale permission/context completions before
showing a recording or submitting audio. A new generated Windows CPU CI profile
checks database and source-package portability without private runtime data.

Current priorities remain: finish Home TV recovery when its desktop session is
available; evaluate real family uploads and voice turns; resolve bounded GPU
qualification; then qualify provider-backed title/story quality and persisted
visual identity before enabling similarity lookup. More source tests do not
close those installed-service or human-quality gates.

The installed `489460b` release preserves older assistant reading positions and
provides explicit localized latest-reply navigation. Memoir citation loading now
updates only its panel, preserving the focused title/intro form and composition;
revision and scope checks still fence delayed results. The portable
[video source recovery planner](VIDEO_SOURCE_RECOVERY.md) is included in ordinary
CPU checks. These changes do not start conversion, change originals, or replace
the installed-service and signed-release gates.

## October 9 development home and next slice

The [provider architecture](MODEL_PROVIDER_ARCHITECTURE.md) and offline model
catalog now identify thirteen source capabilities with isolated runtime and
versioned-output replacement rules. Actual selection still uses the existing
feature-specific configuration/worker arguments. The offline
[private deployment manifest](MODEL_DEPLOYMENT_MANIFEST.md) now validates declared
bindings, artifact/runtime identities, resource budgets and distinct rollback
targets. Its report omits private values. An explicit typed bridge now maps
assistant ASR/TTS, memory contribution/narrative and independent story-title selections into private
configuration copies, preserving feature opt-ins and existing request/item/run
limits. It refuses conflicting legacy settings and never launches a service.
An [offline qualification record checker](MODEL_QUALIFICATION.md) now binds
scoped identity observations, resource samples and human voice/story reviews to
the exact current or rollback selection. ASR uses a separate pinned private audio
inventory; optional explicit hashing verifies only named files. It does not
collect observations or establish provider/device/runtime/semantic acceptance.
Schema 2 also declares native or WSL2 placement: the application host stays
separate from a provider's execution OS. Windows assistant/memory projections
can select Linux WSL loopback services alongside native Windows services without
changing schema 1. Qualification records bind the placement and keep Linux ASR
and Windows TTS in separate scopes. This describes topology only; loopback
forwarding, installed identities and voice quality still require native checks.
Private readers now account for Windows path/handle timestamp differences,
retain replacement and modification checks, and have a separate Windows CI
cohort. This improves metadata intake; it does not qualify generated stories.
The next model-infra slice is native installed-provider/device verification and
bounded Chinese voice/story evaluation, then separately approved activation.
The [October 9 local text-model comparison](LOCAL_TEXT_MODEL_SHORTLIST_2026-10-09.md)
now identifies Qwen 3.5 9B and Gemma 4 12B as initial candidates, with Qwen 3.8
27B for an isolated larger-model comparison. Source requests explicitly disable
thinking for bounded structured text. Registry identity, download authorization,
native resource/JSON checks and human story review precede any provider switch;
newer release dates and vendor benchmarks do not close these gates.
The standalone [story canary](MODEL_QUALIFICATION.md#capture-one-synthetic-story-output)
now captures one pinned synthetic narrative or companion response without the
database-backed worker. It preserves private inputs, outputs and provider
configuration identity while leaving the quality rubric unreviewed. Native
model availability, resource supervision and human assessment remain separate.
An explicit offline cold-start profile allows a single request with at most a
90-second timeout. Ordinary requests retain the 30-second cap. It adds no warm-up,
retry or production setting change; actual startup latency and story quality
still need native evidence.
A private [human-review worksheet](MODEL_QUALIFICATION.md#enter-human-judgments-with-a-private-worksheet)
now exports existing unreviewed case entries and imports judgments into a new
qualification record. It refuses stale or changed case/source identities and
preserves missing runtime/resource evidence. Provider activation and actual
listening/story assessment remain separate operator gates.
Embedding/face bindings and independent runtime catalog packaging remain future
integration work. Metadata validation does not establish installed models or
allow automatic activation.

The [activity grouping design](ACTIVITY_GROUPING_DESIGN.md) now has a pure,
synthetic photo-vector ranker. It checks a preauthorized bounded cohort, exact
vector identity and component checksums before cosine ranking. This is a
foundation only: no lookup route, real embedding coverage or model integration
exists yet. The next visual slice must preserve checkpoint/preprocessing identity
and qualify library-filtered loading before any ranking; the global index must
not be searched first and post-filtered. Similarity will remain a reviewed
candidate, never proof of an activity or a reason to copy prose automatically.

The [public monorepo](REPOSITORY_TRANSITION.md) is now the development home.
Reviewed PR #1 and hosted API/Android CI close the initial public-source delivery
gate. The legacy application repositories remain retained references; runtime,
provider quality, supported release paths and physical-device acceptance keep
their own gates. Historical pending-CI statements below refer to older snapshots.

The Web and phone grouped-story editors now have an explicit, reviewable
[same-day moments picker](../server/docs/security/STORY_RELATED_MEDIA_V1.md).
It suggests photos/videos from recorded capture dates within the current library;
the user decides which belong in the story. A common day does not prove a common
activity. Phone candidate lookup and inclusion preserve ordered selection, keep
pages and preview bytes bounded, and reject stale scope/selection responses.
See the [phone source evidence](../clients/android/docs/ANDROID_RELATED_MOMENTS_2026-10-09.md).
Title runtime/staging wiring and the dedicated `story-titles` projection are now
implemented, default off and bounded to 30 seconds. The next storytelling slice
is provider-qualified title suggestions and reviewed activity grouping. The title
role now has three independent synthetic review cases and bounded opt-in capture;
empty-source abstention makes no provider request. Current/rollback bindings and
human title judgments remain required. Continuous conversation recovery remains
a parallel priority. This source
change does not update a live server, publish an APK or enable generation.

Source implementations and accepted installed behavior are different milestones.
Use [the feature matrix](FEATURES.md) and [development evidence](DEVELOPMENT.md)
for the implemented baseline. Each slice below should finish as a complete user
journey with generated tests and rendered UI before its installation gate.

The remaining legacy D1 family-note erasure source is now preserved in this
monorepo, including immutable identity, historical library authorization,
dependent prose cleanup and offline journal upgrade/replay. It defaults off and
does not backfill old notes. Native paired-backup/migration/journal checks and
owner acceptance precede activation; source preservation is not a live erasure
operation. See the [contract](../server/docs/security/FAMILY_NOTE_ERASURE_V2.md).

The immediate maintenance slice is exact worker startup diagnosis and recovery.
[Sanitized terminal reports](../server/docs/security/APPROVED_WORKER_DIAGNOSTICS_V1.md)
are implemented in source; installing them, capturing a bounded native run and
restoring future approved-media processing retain their separate gates. Matched
story-picker release qualification includes a real a0 migration fixture with
generation/editorial/edition features off. This supports a release without a
migration for the picker itself; exact installed configuration, native package
checks, API switch and a phone update remain to be delivered.

| Priority | User journey | Completion evidence |
|---|---|---|
| 1 — Deliver existing work | Owner arranges a memoir, saves citations and transitions, then reopens it on Web and phone | Additive b1 migration and paired deletion recovery qualification; compatible workers; exact service/source; signed phone update; owner/member and revoked-access checks |
| 2 — Reliable voice conversation | User starts a foreground session or uses reviewed dictation, receives visible results and continues in the same context | Explicit session consent with Pause/End; actual playback gates the next capture; no automatic resend; uncertain receipt recovery after interruption/reload; stale-account/library rejection |
| 3 — Read and contribute | Family reads a themed story and contributes original text or audio to a selected chapter | Reader navigation, original playback, attribution, contribution review and removal of a link without deletion of its original |
| 4 — Album to long memoir | Owner chooses related media and stories, reviews a chapter outline, then arranges the book | Ordered media and chapter provenance; chronology labels; revision conflict/rebase; clear distinctions among library, album, story and memoir |
| 5 — Assisted storytelling | A bounded local worker proposes coherent prose from reviewed family contributions | Synthetic multi-chapter evaluations; source-linked facts; no invented identities/dates/dialogue; separate original/transcript/proposal; explicit owner acceptance; timeout/retry and model-quality checks |
| 6 — Product UI across clients | Phone capture, Web organization and TV viewing form distinct, consistent experiences | Responsive layouts, accessible large text, keyboard/remote focus, media fallback, playback start/seek/end and physical-device review |
| 7 — Sustainable open source | A new contributor can run a generated demo and make a small verified change | Portable setup, dependency/asset provenance, current-source verification, complete package review and hosted CI |

The offline [memoir quality case plan](../server/docs/security/MEMOIR_QUALITY_CASES_V1.md)
provides three bounded synthetic book fixtures for later human review. It
prepares a qualification plan only. Its separate opt-in canary can capture an
output for review; source tests use fake adapters and establish no prose-quality
result. Local-model evaluation and explicit owner review remain future
gates for assisted storytelling.

AI captions are evidence about individual assets. They do not by themselves
establish family context or a coherent novel. Long-form proposals need reviewed
contributions, ordered structure and revision-bound source citations. Human
arrangement remains useful while optional generation is being qualified.

Tab-session recovery of the latest uncertain submission is now implemented in
source and passed eleven synthetic browser checkpoints. It uses an explicit
existing receipt lookup and stores no question, transcript, recording, reply or
authorization token in its pointer. Live delivery remains a separate gate.
Web and phone story selectors now label recent conversation threads with the
first retained user message through an opt-in, bounded preview. The phone client
keeps the legacy response decoder available, retries the legacy list once only
for a current reader when an older server returns HTTP 400, and does not fetch
turn history just to label the list. Public unified-layout filtered JVM runs passed
168 tests across five suites, including the distinct 46-test
MemoryCommunityStoreTest; two emulator journeys at 150% text were run and
visually reviewed in the pinned Android source workspace, not this public
candidate. The Web journey has 17 generated browser checkpoints, including
Chinese/English 390 px layouts at 150% text, and the four-suite optional Web
profile passed after its test waited for the disclosure rule to load. See the
[phone preview evidence](../clients/android/docs/ANDROID_CONVERSATION_PREVIEWS_2026-10-05.md).
Current story/memoir clarification replies now explain how to continue in Web
and phone. The cue keeps recording, draft insertion and sending explicit, and
requires valid current reply metadata. Suggested questions cannot replace an
existing draft. See [clarification behavior](CONVERSATION_CLARIFICATION.md).
The next conversational work is delivery and family evaluation of these controls,
with provider-qualified follow-up quality.

Web and Android now implement bounded process-memory selected-conversation
restoration for saved stories and memoirs. They choose only from a fresh
authorized directory, load current messages before showing the notice, and open
an empty composer. Account, library, membership and target revision bindings,
plus ordered memoir children, prevent stale selection reuse. See
[conversation navigation](CONVERSATION_NAVIGATION.md) and the revision-specific
[development evidence](DEVELOPMENT.md). Served Web files, signed phone delivery
and family acceptance remain separate; navigation does not qualify a provider
or preserve unsent text.

The public source candidate now includes memoir source inspection and explicit
chapter/reply narration in Web and Android. Its four-suite Web profile passed;
filtered Android JVM runs passed 111 source-inspection-adjacent tests and 10
narration tests. These imports have no new public-candidate emulator, release
package, signed phone, native Windows worker, live service or family acceptance.
See [development evidence](DEVELOPMENT.md) for the scoped run details.

Release changes should close existing acceptance gaps before adding another
independently gated feature. Source tests, generated browser/emulator results,
provider quality, signed packages, live services and family acceptance each
have their own record.

The contributor CPU setup now has a fresh exact-lock macOS qualification: 523
tests, 215 independently reported subtests and the generated no-listener demo.
Forty standalone tooling tests cover environment reporting and CPU child
configuration isolation. A first hosted CI run and native Windows execution
remain separate gates for the open source milestone.

Current-chapter discussion preparation is now implemented in Web source and
covered by the 22-checkpoint community journey. It fills a reviewed question
without sending or changing the whole-book thread. Current Android imports
also have a complete 684-test JVM/lint/debug-build qualification. Source-only
checks do not close signed delivery, native migration or family acceptance.

## October 12 memoir composition and discovery follow-up

The current local candidate adds the phone memoir composer, reviewed opening
dictation in both clients, protected visual phone shelves, and explicit local
opening narration. [Development evidence](DEVELOPMENT.md) records accepted
source pins, generated flows and complete-profile results, including corrected
failures. These features do not enable a Windows capability or publish an APK.

On October 12, the protected API/Web release `c6b1401` completed native and
independent HTTPS readback. The live schema remained `a0c9d2e4f817`; five upload
workers were restored and observed running. Phone v47 was signed with the
existing certificate, published to HTTPS OTA and verified by complete native and
independent downloads. TV OTA remained v30. This delivery did not activate AI
generation, editorial editions, title suggestions or memory grouping. Physical
phone/family acceptance and the deferred member/TV checks remain separate.

The next source slice extends the phone composer to **edit a saved memoir**:
add/remove/reorder readable saved stories, revise its title, language and reviewed
spoken opening, and save back to the same parent. Fresh parent/child checks,
revision conflicts, uncertain-response replay and reader scope guards preserve
manual review. See [the composer and edit contract](PHONE_MEMOIR_COMPOSITION.md).
This local slice requires a later signed release before it reaches the phone.

Next product work is reviewed related-moment suggestions and collaborative
chapter editing, using family feedback from the dictate → edit → save → reopen
journey. Qualify local narrative processing and pronunciation separately before
activating them for family material.


## October 13 assistant continuation and delivery priorities

This section records the October 13 local-source plan. The immutable phone v52
candidate is source `7f8d92b` and remains pending publication; the edits in this
working source are for a later candidate. The native state listed above is a
read-only 13:00 Beijing snapshot, not evidence that these local features are
currently deployed.

The [voice reliability slice](ASSISTANT_VOICE_RELIABILITY.md) adds protected
explicit-number retrieval, safe ASR failure categories and opt-in terminal
playback events. It preserves the v1 context and receipt envelopes. Its source
qualification and next phone/API delivery are separate from the installed v51
and already activated providers. A playback event is client evidence; human
listening remains a separate acceptance step.

1. Qualify the local private conversation, older-history and protected reply
   speech candidate across server, Web and phone. Preserve explicit session
   consent, exact request recovery and individual history ownership.
2. Package an immutable API candidate and its synthetic listener-free Windows
   qualification tool. Native staging/checks, isolated store provisioning and
   live activation remain separately authorized operations.
3. Prepare the matching unsigned phone candidate with the original icon. Sign
   and publish only after source qualification and release authority.
4. Extend the grounded assistant to stories and memoirs through typed read-only
   tools, showing evidence and reviewed suggestions. Keep uncertain narrative
   inference, family mutations and collaborative edits behind explicit review.
5. Collect family feedback on voice continuity, pronunciation, retrieval and
   history clarity before broadening agent autonomy.

The [saved-memory discovery foundation](ASSISTANT_SAVED_MEMORY_CARDS_V1.md)
passed 23 discovery tests/22 subtests and 13 parser tests. The initial combined
discovery/parser/tool run passed 44 tests/40 subtests; the corrected nine-test
projection/tool rerun passed, with overlap between cohorts. The backend now has
a default-off negotiated endpoint and optional capability probe. Same-ID replay
returns stored status before fresh opt-in negotiation; history keeps legacy
30-day summaries and typed non-actionable reference counts. Web renders scoped
plain-text cards; nine focused HTTP checks, 45 controller checks and six generated
browser checkpoints passed. No live flag or API is activated. This source is
outside pinned v51 `3a56870` and native candidate `db95b6`. Typed-source reply
speech now has a separate optional probe and revalidates the current source set
before and after synthesis. The source-only qualifier exercises eight generated
scenarios. Phone cards, reviewed reader handoff and delivery remain separate gates.

The next bounded product slices are:

1. Explicit story/memoir reader opening from a fresh assistant card, bound to
   its completed owned turn and current source digest. End foreground voice
   before reader navigation and preserve unsaved reader work.
2. Matching phone negotiation and cards, with simulator checks before a new
   signed release. Keep the immutable v51 delivery candidate separate.
3. Grounded questions about a saved story or whole memoir, showing cited source
   passages and asking about uncertainty. Current retrieval is literal saved-text
   matching; it does not yet answer free-form story questions or infer new facts.
4. Reviewed related-moment suggestions and shared memory links, retaining manual
   inclusion/exclusion and original authorship. Generation and source propagation
   remain explicit separate opt-ins.


</details>

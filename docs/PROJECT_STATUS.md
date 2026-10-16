# Current project status

Source and delivery records refreshed **2026-10-16**. Live-state statements
below are the last verified v65 observations; this source round did not recheck
Windows service health. PR #47 merged the Android
chapter family-memory chooser at `2fe1586`. PR #48 merged bilingual search
clarification; API/Web source `f476c5e16f032eb427e3504997d6e33b5a500d9b` is live.
PR #49 merged phone v65 at `22472be475fd4e4b3b5423f2e96d91a773592b0d`, with
tree-equal build and review evidence `8bd9c5a63b14c607aaadbcc29cdb3f9144d2e421`.
The Windows HTTPS phone feed publishes **v65 / `0.65-chapter-memory`**. The
original signing certificate and icon were retained. The signed APK is
11,663,736 bytes with SHA-256
`40b74da0a9e9a056f247bbf8bbb511586931550ebd847c23e3ab8d4187767b2e`.
See the [v65 release record](../clients/android/docs/PHONE_V65_RELEASE_2026-10-16.md).

All five source CI jobs passed in run `38835026125`. Separate release
verification passed configured build/lint, 17 embedded-field checks, four
signing-refusal checks, 11 publication tests, native full-HTTPS verification,
an independent Mac full-stream readback and 10 Web asset checks. Postflight
preserved all eight running root tasks, including five upload workers; ASR, TTS
and OCR were unchanged. API/Web v65 pairing did not restart the API or change
schema/configuration. TV remains v30 and unchanged; TV v31 source is unpublished.
No physical phone installation or test occurred, so family/device acceptance
remains open.

PR #48's bilingual search clarification is part of the live API/Web source.
The phone v65 chooser lists accepted, consented sources using metadata-only
choices and the existing atomic link-save contract. Its release does not enable
story generation. The [reviewed chapter-proposal adoption flow](PHONE_STORY_PROPOSAL_ADOPTION.md) into an unsaved
existing-story editor is following source. Its 74 focused JVM tests, phone
build/lint and eight explicit QA-emulator journeys passed. Chinese/English
150% renders were inspected. It is not included in v65; later APK delivery and
physical family acceptance remain separate.
The provider/model story generation path remains off. The synthetic 9B
cold-capture sample took 80.422 seconds and has not had human quality review;
see the [story trial record](STORY_MODEL_TRIAL_2026-10-16.md).

PR #50 subsequently merged the [gated scene-search workspace source](ASSISTANT_SCENE_SEARCH.md)
at `93c80aa`. That merge is following source, outside the v65 release and the
last verified live API revision above; it does not establish a deployment.

## Delivery and acceptance

| Area | Latest verified evidence | Still open |
| --- | --- | --- |
| API/Web | Live source `f476c5e`; bilingual search clarification is deployed; no restart/schema/config change in the v65 pairing | Real owner/member search, voice and UX acceptance |
| Primary database | No schema change in this release pairing | Later feature/schema activation and paired recovery qualification |
| Phone | v65 original-certificate/icon APK published; five CI jobs passed, with separate native full-HTTPS and independent Mac full-stream verification | Physical installation and family/device acceptance |
| TV | v30 feed verified unchanged; v31 source unpublished | Projector/library/playback check |
| Public source | PRs #47–49 merged; phone v65 and API/Web search clarification delivered | Proposal adoption implementation under review; root checks pending |
| Story generation | Provider/model path remains off; synthetic 9B cold capture was 80.422 seconds | Human source/coherence review and remaining model cases before any activation |
| Introduction website | Public audience verified with cartoons/fictional examples | Family/design feedback; [delivery record](../website/RELEASE_2026-10-14.md) |

Earlier dated source, test and release records below retain their exact scope.
Their versions and pending statements do not override the current summary.
v59 remains an unused earlier frozen proposal; it was not published.

## Earlier search checkpoints (historical)

The paragraphs below retain their original revisions and observations. They do
not override the current source and delivery summary above.

The next local source round adds an internal search-readiness inventory and a
private offline relevance runner. It separates recorded metadata from searchable
coverage, runs actual protected search/refine/open interpretation and emits
content-free scores/check outcomes. It opens databases read-only and discards
partial results on source drift. New ingestion and video-probe handling accept
only a valid explicit QuickTime capture timestamp, preserve its local day and
leave unknown dates unknown; the worker fills null dates only. No historical
backfill, production write, model or permission activation occurred. The
[operator guide](SEARCH_READINESS_AND_RELEVANCE.md) records limitations and commands.
The focused search/source/storage cohort passes **131 tests / 81 subchecks**.
The video cohort passes **12 tests / 13 subchecks**, including a generated MP4
through real FFmpeg/ffprobe. Later full release profiles and native Windows,
real-library relevance and family/device acceptance remain open. The Android
emulator remains closed as requested; this round changes no client UI.

The current local integration connects negotiated search v2 to the private
workspace, Web and phone. It presents the chosen family perspective, actual
person/text/date/media/place conditions and evidence labels, including explicit
AI-caption wording. Recovery retains the original search version and revalidates
current source order; it neither resubmits the request nor replays navigation or
speech. Only the exact unsupported-version capability response allows a legacy
capability retry. See [the updated contract](ASSISTANT_JOINT_SEARCH_V2.md).
Focused checks pass: the generated joint-search suite (20 tests), workspace HTTP
suite (14), private kinship suite (29), reply-speech suite (8), Web wire suite
(75), and phone wire/HTTP/store suites (67). These overlapping cohorts are not
summed. The generated Web v2 journey passes five checkpoint groups, including
two reviewed people with a noun-only scene, a year refinement, opening the
second result, and lost-response GET recovery. Desktop and Chinese/English
phone layouts at 150% text were inspected. The corrected saved-memory journey
completes 27 checkpoints, including explicit Chinese/English Stop labels (its
headless browser needed bounded teardown after all assertions completed); the
legacy voice journey passes with an explicit unsupported-version capability
fixture and no search-v2 header on its v1 private turn.

Phone main and Android-test source compilation pass. Debug lint passes with no
errors at the pre-copy cohort `e55b954`; the later `acfc55c` changes only two
media-neutral UI labels and the synthetic screenshot helper. Full Android,
native Windows and physical family/device qualification remain separate gates.
The additional caller/voice JVM cohort passes 38 tests (5 workspace callers and
33 voice cases). Both English/Chinese emulator cases pass at 150% text, and four
retained renders were inspected. The final test-only assertion recognizes the
perspective in both the pre-submit banner and the interpreted result. An
isolated, unconfigured debug package preserved the existing higher-version
emulator installation; only the temporary test packages were removed afterward.
These fixture results do not establish a signed phone release or family relevance.

The complete API invocation at `f0c5176` is **incomplete**, stopped after 185
passes, 96 subchecks and two library-transfer failures. Both failed cases pass
alone with the same profile flags. Their relevant source and fixture blobs are
unchanged from the prior search baseline; repeated identity-schema verification
inside the existing three-second transfer transaction is a likely load-sensitive
timeout path. This is not a full API pass. The full Web invocation at that
revision also stopped at the legacy voice fixture's v2 readiness mismatch;
the corrected fixture and affected playback journey pass separately. A complete
release regression remains open. Earlier API-only passes below remain bound to
their stated revisions, and do not qualify this later client integration.


The next source increment adds an optional [private kinship provider](PRIVATE_KINSHIP_SEARCH.md)
for search v2. It binds an explicit library/account allowlist and chosen
perspective, resolves bilingual relative chains only to current reviewed
identities, and invalidates contexts on graph/perspective/access changes.
Household data and pending account approvals remain outside Git. The focused
generated graph/provider/HTTP suite passes 29 tests. The complete API profile at
`01cf409` passed **1,552 tests / 988 subchecks** plus the generated no-listener
demo, with unchanged start/end commit and source input hash. Staging/runtime
forwarding, existing joint/conversational and source-verifier checks also pass.
This source cohort uses fictional fixtures; private graph validation and the
bounded operator inventory remain separate private records. Live activation still needs
confirmed account/library/person bindings, client perspective display and the
separate server delivery gate. No account creation or live permission change is
implied by source checks or a private draft.

The next local source increment adds an explicitly negotiated search-v2 API
slice joining eligible current captions, saved photo memories and reviewed
people with existing date/media/place constraints. It uses a request-time
protected projection, separate source-bound contexts, authored-evidence-first
ordering and provenance reasons. Default v1 clients retain their wire contract.
See [the v2 contract and gates](ASSISTANT_JOINT_SEARCH_V2.md). Work is isolated on
`codex/search-redesign-20261015`; the concurrent story branch is separate.
That earlier API-only cohort was not integrated into clients. The current
local client integration above remains undeployed. Real index readiness, video
date bases, local semantic understanding and relevance qualification remain ahead.

The focused generated-data joint-search suite passes 19 tests, including short
Chinese/quoted text, current source invalidation, any/all, a roster beyond 500,
ranking/paging, current-result opening/refinement, personal-kinship alias refusal
and version isolation. The complete API profile at implementation commit
`b7d605b` passed **1,519 tests / 939 subchecks** plus the generated no-listener
demo. Its private invocation receipt records identical start/end commit and
source input hash, with exit code 0. Earlier interrupted runs are incomplete
records, not passes. Affected discovery/index suites and the check-driver/source
verifier checks also passed. No household data, GPU or live service was used.
Android/Web profiles, native Windows and real-library relevance were not run
for this API-only increment. Later documentation commits do not rebind this
profile evidence to a different source revision.

A later read-only owner-requested investigation confirmed ASR/turn intake but
weak deterministic query parsing and missing searchable fields in the inspected
library index. Its active fields are date, reviewed locations and media; stored
captions and confirmed face records are not yet part of this assistant index.
Unknown capture dates also cause date queries to omit videos. Private transcripts
and aggregate household coverage are retained outside Git.

A local, undeployed patch accepts ordinary conversational search openings,
clarifies possible ASR verb confusion and explains disabled indexes/missing dates.
Five focused tests and a 63-test shared HTTP cohort passed. See the
[search review](ASSISTANT_SEARCH_REVIEW_2026-10-15.md) for the ordered text/person,
date and language-understanding work. New story-creation UX is deferred.

## Delivered reading and assistant increment

v60 includes temporary prose-size presets, compact phone memoir navigation,
explicit current-image preview recovery, first-chapter/memoir-introduction
assistant segments with actual-completion-gated Continue/Stop, unsent assistant
draft recovery, visible manual reading progress and ephemeral voice-turn timing.
The [v60 trial](../clients/android/docs/PHONE_V60_TEST_GUIDE_ZH.md) links the
assistant scenarios. A photo memory is not automatically a saved multi-image
story; use the [first-story guide](FIRST_STORY_GUIDE_ZH.md).

## Runtime configuration observed

Public defaults remain closed or opt-in. These observations describe this
installation. This release preserved configuration bytes and enabled no provider.

| Capability/configuration | Observed state | Meaning |
| --- | --- | --- |
| Upload review | Enabled | Per-library owner/member policy and destination checks still apply; a receipt alone is not gallery or TV publication |
| Assistant, saved-memory cards, private reply speech | Enabled | Authenticated read-only voice/chat and fresh saved-story actions; no general administrative tool agent |
| Private workspace, assistant receipt journal, original-deletion journal | Present; backup integrity passed | Separate stores with distinct purposes and retention |
| Memory collaboration and original contributions | Enabled | Family contributions remain separate from transient assistant audio and 30-day troubleshooting records |
| Upload annotation intake | Off | Separate from original story/memoir contributions |
| Story generation and title suggestions | Off | Implemented adapters/contracts are not a live writing/title service |
| Memory groups and memoir editorial/editions | Off | Activation still requires compatible schema, provider quality, recovery and UI gates |
| Permanent family-note erasure | Off | Imported lifecycle contracts do not imply live migration/activation |
| Long oral-history intake | Internal default-off prototype | Five-group/twelve-case generated qualification does not create HTTP/client intake |

## Service/task verification

The API, five approved-upload workers, ASR and TTS tasks were running after the
switch. All 66 task enabled states were retained; only the API definition changed.
The enabled 30-second API startup trigger, ASR/TTS/OCR and Home TV configuration
were preserved. Home TV was Ready and still depends on an interactive desktop.
Task state does not establish a warm model, successful queue processing or audio
quality. No model inference or video-backlog recount was part of this release.

Keep original-source failure records. Resume unfinished conversions without
re-encoding completed videos; use the [recovery planner](VIDEO_SOURCE_RECOVERY.md)
for any separately scoped source repair.

## Qualification and next work

- Exact artifact source `53e3954`: complete API profile, 1,495 tests / 915
  subchecks plus generated no-listener demo; complete Android JVM/lint/debug
  profile, configured unsigned release assembly/lint and icon/profile checks.
- Complete Web profile at fixture-only review `2c7c924`: passed with unchanged
  inputs; all 201 packaged runtime files and complete Android tree match `53e3954`.
  Earlier failed fixture receipts remain recorded, not counted as passes.
- Native Windows: twelve assistant groups and five experimental oral groups /
  twelve cases with generated fixtures and bounded resources; no production
  data, provider or listener during qualification.
- Delivery: verified four-store backup, exact new Web assets/access denials,
  five-worker restoration, original-certificate signing and full native/HTTPS
  phone APK readback. Independent Mac manifest/UI check passed.

Next: install v60 and run owner/member reading and continuous-voice trials; then
implement the reviewed first-story flow. Long recording intake, model quality,
TV v31 delivery and broader narrative/grouping activation retain separate gates.

## Earlier progress notes

The notes below retain intermediate package counts and then-pending work.
The current qualification and delivery sections above supersede those dates.

<details>
<summary>Expand the earlier October 15 source increments</summary>

## Later source increment: oral-history intake

The [internal recording-section foundation](ORAL_HISTORY_INTAKE_FOUNDATION.md)
was developed after the installation snapshot above. It has source tests only,
no HTTP/client surface, migration or runtime configuration. Windows services,
model/worker activity, family data and v58/TV OTA feeds were not changed. Do not
interpret its source quota or generated-fixture installer as live admission.

## October 15 source increment: readers and withdrawal

Web memoir readers now show source-check state outside the collapsed original
source panel, with an explicit retry after failure. A checked source link is not
fact verification. Phone manual chapter narration displays its current speech
segment during preparation, playback and pause; progress is session-local and
clears on interruption/end. This does not extend assistant opening speech to a
full chapter. See [reader UX](READER_PROGRESS_AND_SOURCES.md).

The [oral-history withdrawal prototype](ORAL_HISTORY_WITHDRAWAL.md) adds
author-only retained-source withdrawal, content-free V4 journal bindings and
older-prefix replay. Raw WAV bytes remain retained; permanent erasure and live
admission are not implemented. There are no new routes, migrations, live flags,
service changes or APK/OTA publications in this increment.

Source `6795e57` passed the full API profile (1,465 tests / 886 subchecks and the
generated no-listener demo) and full Android profile, each with unchanged-input
receipts. The next source round adds gallery recovery and explicit portable
[release-profile preparation](ANDROID_RELEASE_PREPARATION.md#check-a-complete-private-profile).
The installation snapshot and OTA versions above remain dated delivery evidence.

## October 15 runtime refresh and product polish

A read-only Windows check at **01:03 Beijing (October 14 17:03 UTC)** again
observed API source `8bc60e8`, phone OTA v58 and TV OTA v30. The protected API,
five approved-upload workers, ASR and TTS tasks were enabled and running; Home TV
was enabled but Ready and still requires an interactive desktop session. This
check did not open a database, invoke a model, recount conversion queues or
change a task. These task states are not listener or listening-quality evidence.

Later local source adds explicit phone photo-preview retries, visible Web
gallery fallback frames and [last-turn voice timing](VOICE_TURN_TIMING.md).
The Web gallery journey passed 65 checks in installed Edge, including native
video decode, playback and seeking. Phone recovery checks passed in both the
protected and optional Home modes. Voice timing uses process-local observations,
not provider telemetry or retained transcripts. Bilingual enlarged simulator
and browser checks passed; timing fixtures do not measure real family latency.

The next delivery gate is a pinned source/API package and unsigned phone
candidate, followed by separately authorized Windows qualification, API switch,
original-certificate signing and OTA publication. No deployment or publication
is included in the overnight source checks above.

The next source slice now implements [saved-section narration](ASSISTANT_SEGMENT_READING.md)
on Web and phone: first story chapter or memoir introduction, one explicit
segment at a time, completion-gated Continue, visible Stop and final restart.
Generated backend, wire/controller and enlarged browser/emulator journeys pass.
The source-only API closure has 200 files and twelve disposable qualification
groups. Its new optional probe and segment route preserve old opening contracts.
The installed v58/TV v30 observations above remain separate delivery evidence.

The frozen `9a3faad` API profile passed 1,482 tests / 913 subchecks and the
generated demo. Later source corrects Edge's focused-Send native blur and keeps
one inferred voice language across mixed-language narration segments. Narrow
cross-browser and backend checks pass; the next candidate's complete release
profiles and immutable artifacts remain the delivery gate.


## October 15 integrated product-readiness round

Later source compacts saved-memory actions into wrapping 48-pixel/dp controls,
keeps complete accessible prompts behind short visible follow-up labels, and
removes redundant phone onboarding when current result cards are already present.
Late follow-up capability readiness now fills missing controls only for the
exact current rendered result. Its held-response Edge journey passed 27
checkpoints, including focus, duplicate and unchanged-submission checks.
Web Ctrl/Cmd+Enter uses the same guarded explicit Send path; ordinary Enter and
IME composition do not send. Reload recovery now retains the restore-start turn
identity and respects later composer focus and scroll intent. These changes do
not grant a new voice consent or automatically submit a suggested question.

TV source exposes current-page preview failures and retry directly above the
gallery. Only missing derived previews are retried. Recovery status and its
focused remote action persist after completion; paging discards the prior page's
status. Three emulator scenarios, debug lint/compilation and bilingual enlarged
renders passed. TV v31 / `0.31-preview-recovery` is reserved in source. This source is not
installed on a projector or published to OTA.

The synthetic story-quality corpus now includes eight cases, adding similar
photographs from different events and distinct subject/speaker/uploader roles.
No model inference or narrative quality pass follows from planner validation.
A new [generated oral-history qualifier](ORAL_HISTORY_QUALIFICATION.md) rehearses
four scenario groups and ten case assertions against disposable fixtures,
including older-prefix replay after withdrawal. It does not admit production
recordings or permanently erase retained sections. Its addition makes the next
source-only API package closure **201 files**; the prior 200-file packages remain
bound to their historical revisions.

The [read-only package inspector](API_PACKAGE_INSPECTION.md) verifies a pinned
canonical API archive against local committed Git blobs, with no extraction or
candidate execution. Its 26 generated checks passed. Final integrated full
profiles and exact release artifacts are recorded separately when complete.
The live v58/TV v30 snapshot above remains the latest runtime evidence; these
source additions have not changed Windows services, data or feeds.


### Follow-up reliability fixes before the next release

The frozen `bd21d27` source passed the full API profile (**1,495 tests / 915
subchecks**, plus the no-listener demo) and Android profile with unchanged-input
receipts. The next full Web run failed during an English voice scenario; a
held-session reproduction established a real product race, rather than merely a
fixture delay. Start was enabled while session restoration could still abort
capture/transcription. Current source now gates voice startup/resume/capture
until the owning restore completes, with visible setup and microphone-off text.
A failed restore leaves voice unavailable; an older restore cannot release a
newer restore's gate. Focused voice and conversation-recovery journeys pass.
The failed full run remains recorded and must be followed by a complete rerun.

The expanded quality corpus also required two older worksheet test expectations
to be updated. All **158 standard-library tooling tests** now pass, preserving
unreviewed status, exact case identity and separate narrative/title rubrics.
No model was run and no quality verdict was generated by these tests.


Phone draft continuity is also qualified through the actual ConnectedApp route:
three emulator cases cover typed/suggested draft round trips, active-thread
changes, same-thread revision refresh and zero turn/transcription/capture side
effects. The transient holder clears with account/library/protection scope or
assistant-host closure. This does not add persistence or silently choose a
conversation for an unsent request.

</details>

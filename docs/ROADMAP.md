# Product roadmap

## October 10 source delivery and reader refinement

PR #13 is merged after its pinned API, Android and Windows private-reader jobs
passed. Its conversation recovery, explicit transcript review, same-day story
picker and lifecycle fixes are reviewed source. Delivery of those exact changes
to the household API and signed phone remains a separate operation.

The next reader slice adds a protected Web filmstrip and scope-bound phone frame
selection, with localized position labels, enlarged-text chapter controls and
explicit navigation. See [reader behavior](STORY_READER_NAVIGATION.md). Browser
microphone startup also rejects stale permission/context completions before
showing a recording or submitting audio. A new generated Windows CPU CI profile
checks database and source-package portability without private runtime data.

Current priorities remain: deliver the qualified source; restore installed
media processing and Home TV with exact operation checks; evaluate real family
voice turns; then qualify provider-backed title/story quality and persisted
visual identity before enabling similarity lookup. More source tests do not
close those installed-service or human-quality gates.

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
| 2 — Reliable voice conversation | User records, reviews, submits, receives a reply and continues with an understandable context | Explicit turn boundaries; no automatic listening or resend; uncertain receipt recovery after interruption/reload; stale-account/library rejection |
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

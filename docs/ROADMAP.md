# Product roadmap

## October 9 development home and next slice

The [provider architecture](MODEL_PROVIDER_ARCHITECTURE.md) and offline model
catalog now identify thirteen source capabilities with isolated runtime and
versioned-output replacement rules. Actual selection still uses the existing
feature-specific configuration/worker arguments. The offline
[private deployment manifest](MODEL_DEPLOYMENT_MANIFEST.md) now validates declared
bindings, artifact/runtime identities, resource budgets and distinct rollback
targets. Its report omits private values. An explicit typed bridge now maps
assistant ASR/TTS and memory contribution/narrative selections into private
configuration copies, preserving feature opt-ins and existing request/item/run
limits. It refuses conflicting legacy settings and never launches a service.
An [offline qualification record checker](MODEL_QUALIFICATION.md) now binds
scoped identity observations, resource samples and human voice/story reviews to
the exact current or rollback selection. ASR uses a separate pinned private audio
inventory; optional explicit hashing verifies only named files. It does not
collect observations or establish provider/device/runtime/semantic acceptance.
The next model-infra slice is native installed-provider/device verification and
bounded Chinese voice/story evaluation, then separately approved activation.
Embedding/face bindings and independent runtime catalog packaging remain future
integration work. Metadata validation does not establish installed models or
allow automatic activation.

The [public monorepo](REPOSITORY_TRANSITION.md) is now the development home.
Reviewed PR #1 and hosted API/Android CI close the initial public-source delivery
gate. The legacy application repositories remain retained references; runtime,
provider quality, supported release paths and physical-device acceptance keep
their own gates. Historical pending-CI statements below refer to older snapshots.

The Web grouped-story editor now has an explicit, reviewable
[same-day moments picker](../server/docs/security/STORY_RELATED_MEDIA_V1.md).
It suggests photos/videos from recorded capture dates within the current library;
the user decides which belong in the story. A common day does not prove a common
activity. The next client slice is phone candidate selection, followed by
provider-qualified title suggestions and reviewed activity grouping. This source
change does not update a live server, publish an APK or enable generation.

Source implementations and accepted installed behavior are different milestones.
Use [the feature matrix](FEATURES.md) and [development evidence](DEVELOPMENT.md)
for the implemented baseline. Each slice below should finish as a complete user
journey with generated tests and rendered UI before its installation gate.

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
prepares a qualification plan only; no model is run and no prose-quality result
is claimed. Local-model evaluation and explicit owner review remain future
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
The next conversational work is understandable follow-up context and
clarification, with explicit recording and submission controls.

The legacy Android process-memory selected-conversation restoration is a
specific migration gap: this public baseline still chooses the first listed
thread when reopening. Import the bounded navigation helper and dependent
store/UI/test changes with current account/library/membership/target/revision
checks before retiring that legacy feature. This does not preserve unsent text
or bypass fresh authorization.

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

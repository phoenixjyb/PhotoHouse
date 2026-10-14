# Development and public release qualification

## Maintainer navigation

Use [Project Status](PROJECT_STATUS.md) for the dated delivered/runtime snapshot,
[Architecture](ARCHITECTURE.md) for stores and ownership, and the
[documentation index](README.md) for topic contracts. Start with
[CPU quick start](#cpu-quick-start), [Android checks](#android-checks),
[Web browser profile](#optional-web-browser-profile),
[required profiles](#required-local-profiles) and [public release gates](#public-release-gates).

Dated sections below retain qualification and delivery history at their stated
revision. “Candidate”, “not deployed”, test counts and next-step statements apply
to that record, not every later release. Do not sum overlapping checks or treat
local evidence as current hosted CI, runtime/model quality or device acceptance.
The October 14 documentation audit did not rebuild applications.

## Reader and voice recovery qualification (October 15)

The first local source round (`a3527fb`) adds visible Web memoir source-check
status/retry, phone manual narration segment progress, and the internal
[recording withdrawal prototype](ORAL_HISTORY_WITHDRAWAL.md). Web reader checks
passed 13 checkpoints/115 generated requests with no page errors. Phone reader
instrumentation passed 18 tests on the reused API 36 emulator, with compile and
debug lint and inspected Chinese 150% active/pause/resume renders.

The following round adds a direct phone receipt query in a paused uncertain
voice session and guarded Web keyboard focus after manual transcription. The
phone's focused class passed six tests, compilation and lint; Chinese/English
150% renders were inspected. Web synthetic transcription success, error, explicit
retry, changed-focus and stale-scope checks passed; Chinese 390-pixel/150% focus
recovery was inspected. These checks use fake speech and generated content.

The internal V3→V4 upgrade/withdrawal cohort passed 21 tests and nine subchecks,
including populated legacy digest preservation, rollback, deferred WAL writer
serialization and final guard mutation refusal. It has no operator CLI or live
upgrade/migration. The initial full API invocation reached two expected archive
failures because the package allowlist included an uncommitted new source file;
the committed-source package suite then passed all six tests. Complete final
profile evidence at `6795e57` passed **1,465 tests and 886 subchecks**, plus the
generated no-listener demo. The full Android profile passed its JVM tests, lint
and unconfigured phone/TV debug builds. Both private invocation receipts confirm
unchanged profile input hashes and the same start/end commit.

No Windows service, model, database, task, signed APK or OTA feed was changed by
these local rounds. Local visual results remain separate from family acceptance.

The subsequent explicit Android release-profile checker passed 11 generated
tests, including miniature pinned Git source, complete property closure,
canonical runtime origins, feature dependencies, changed permissions, restored
Windows-style metadata and late source mutation. This is preparation evidence,
not a build, signature or native Windows acceptance check.

The gallery journey passed **65 checks** in installed Edge, including native
MP4 decode, playback and seeking. Cached headless Chromium lacked H.264/AAC
codecs; its native media failure is not reported as a pass. The Edge run exposed
a stale request consuming a one-shot failure fixture; the fixture now keeps the
selected failures until explicit recovery and waits for lazy-image decoding.
Application thumbnail failure creates a localized, keyboard-openable fallback
without reassigning the failed source or fetching originals automatically.
Optional Home phone recovery passed five class cases and the final affected
case; protected phone recovery passed its English/Chinese 150% cases.

The [last-turn timing slice](VOICE_TURN_TIMING.md) passed seven Node tracker tests,
the generated voice browser journey and bilingual large-text renders. The
shared Kotlin profile passed **966 tests in 84 suites** before adding the store
integration cases; the final affected store cohort passed **19**. Phone voice
controls passed **eight** simulator cases; the final label adjustment reran its
two affected cases individually. These overlapping cohorts are not summed.
Timing details reveal only four elapsed durations after a complete observed
turn, with no extra request, persistence or provider-latency claim. The affected
closed-application inventory/import checks passed **27 tests and 18 subchecks**;
the new static UI helper is included in the **199-file** source closure.

The later [saved-section narration slice](ASSISTANT_SEGMENT_READING.md) passed
**16** new backend cases and the **16** existing opening cases. **Eight**
disposable-qualifier checks pass, and the source-only **200-file** closure now
qualifies twelve generated scenario groups, including three explicit segments
from one saved story and content-free speech receipts. Initial qualification
fixture errors used the wrong thread-create field/status; corrected fixtures
exercise the existing `thread_id` / HTTP 201 contract.

Web passed **70 Node tests** and **26 generated browser checkpoints**. Review
identified old same-index cleanup races for both opening and segment requests;
unique entry ownership now prevents a late finally block clearing its replacement.
Phone passed **33** affected store cases, **19** wire cases and **nine** simulator
cases, plus debug lint and Android-test Kotlin compilation. The active Stop case
scrolls the control fully into view and performs a real click. Chinese/English
150% renders were inspected. These counts overlap; no Windows provider, signed
APK or family listening acceptance is claimed by these source checks.

The full API profile at `9a3faad` passed **1,482 tests and 913 subchecks**, plus
the generated no-listener demo, with unchanged-input receipt. Its full Web run
then exposed an Edge native focus blur after Send became disabled. Valid explicit
Send submissions now focus the still-editable composer synchronously; no later
completion steals user-directed focus. The strict turn-trail assertion passes
in Edge and cached Chromium, including newline entry and Tab movement during a
delayed request. One concurrent diagnostic run saw a transient receipt-focus
overlap after reload; final isolated runs kept the strict assertion and passed.

A later mixed-language guard infers narration language from the complete section
so a Latin-only segment does not switch voice unexpectedly. Its final focused
backend/opening/qualifier cohort passed **41 tests and 38 subchecks**. The new
segment class contains seventeen cases; the earlier sixteen-case evidence above
belongs to the preceding source revision. Package, native and family gates stay
separate.


The full API profile at `d57a41c` passed **1,483 tests and 913 subchecks**,
plus the generated no-listener demo. Its full Android JVM/lint/unconfigured
phone and TV build profile passed with identical start/end source hashes.
The full Web run exposed an intermittent saved-source reopen assertion; two
focused reruns confirmed the saved request, exact reopened response and checked
first-chapter source. The fixture now waits for and validates that exact saved
GET before retaining the unchanged strict DOM selection assertion. The focused
journey passes; the complete Web profile is rerun separately. No product change
is inferred from that intermittent failure.


The next complete Web invocation stopped at the final English timing loop: the
fixture counted entry into `getUserMedia()` before capture setup finished. The
synthetic utterance helper now waits for active microphone state, visible Stop
and the installed audio processor before feeding frames. The affected Edge
journey passes with completion/timing assertions unchanged; Chinese 150% and
English desktop controls were inspected. This is a harness readiness fix, not
evidence of a new live speech service or physical recording result.


## Oral-history intake foundation (October 14)

The [internal intake contract](ORAL_HISTORY_INTAKE_FOUNDATION.md) passed 18 focused
tests and 15 subchecks for ordered PCM sections, exact mutation receipts,
reopened storage, owner/member isolation, concurrency, storage/receipt/schema
failure, cancellation, quotas and default-closed routes. The adjacent access and
contribution cohort passed 54 tests / 31 subchecks; scopes overlap.

The first `memory` profile run exposed a pre-existing order-dependent import in
`test_family_note_identity.py`: its worker schema test depended on another test
adding `server/scripts` to `sys.path`. It now loads the exact worker file via
`importlib` directly. The complete final profile passed **308 tests and 163
subchecks**, with one existing Starlette/httpx deprecation warning. No worker,
model, runtime, database migration or phone/Web recording interface is activated.

Full API/Web/Android builds, hosted CI, Windows native/storage/power-loss and
family/device checks were not run for this source prototype. The live v58 API
and OTA artifacts remain unchanged; current source is not a release candidate.

## Contextual voice and viewing qualification (October 14)

The local [fluid assistant slice](ASSISTANT_FLUID_EXPERIENCE.md) passed 111
saved-memory backend tests, including negotiated action shape, source-bound
opening speech, withdrawn-source concealment, current full-cohort validation,
legacy/recovered request compatibility and choice prompts that retain ordering.
Source text/action metadata stays out of persisted private replies.

Android passed 958 live-core and 17 connected JVM tests, phone lint, and
unconfigured debug/app-test assembly. One generated API 36 emulator journey
checked the explicit localized read action at 200% text; the render was inspected.
Voice tests cover successful playback before the next capture, Pause during a
held opening fetch and reading-capability loss during playback. Reader UI
navigation waits until voice ends. Phone identity is reserved as v58; these
unconfigured builds are not a signed household OTA candidate.

Web passed 65 Node tests and a generated browser journey with 20 checkpoints,
including actual continuous-session action dispatch, source opening playback,
asynchronous media-error pause, explicit typed actions, target-card focus,
ambiguity, fresh capability negotiation and a delayed old-scope reader response.
Phone at 150% text and desktop renders were inspected. Screenshot labels use
clean generated layout text after separate hostile-title escaping assertions.
Two earlier browser runs timed out during a later search setup. The fixture was
corrected to scope capability probes to the current reload and wait for current
controller readiness, rather than matching earlier page responses; the final
complete journey passed without extending that timeout.

The later release preparation ran the full API profile: **1,426 tests and
862 subchecks passed**, plus the generated no-listener demo. Two initially stale
closed-route assertions were updated for the reviewed action capability (163
registered routes). The portable qualifier now exercises contextual actions in
its existing eleven scenario groups, and a failure-injection test confirms the
action dispatch gate is checked; 47 qualifier/closure/dispatcher tests and
20 subchecks passed. The [fixed v58 phone/API candidate](../clients/android/docs/PHONE_V58_RELEASE_CANDIDATE_2026-10-14.md)
now records the configured unsigned APK, preserved icon, exact API archive and
matching Android subtree across the two build revisions. The authorized Windows
qualification passed all eleven synthetic scenario groups against this exact
archive, capped at five minutes, 2 GiB and eight processes with an 8 GiB
free-RAM admission floor. It opened no family database/media, called no models
and changed no services or tasks. Eight deployment controllers also passed native
syntax checks and a read-only bootstrap derivation; 17 local operation checks
passed, including preservation of the API startup trigger and anonymous denial
for the new action capability. The separately authorized v58 API/Web deployment
completed with a verified stopped-writer backup, exact served-byte checks,
anonymous denials, preserved startup trigger and restoration of all five upload
workers. An independent post-switch check passed. Schema a0 and configuration
bytes are unchanged. [Phone v58 delivery](../clients/android/docs/PHONE_V58_RELEASE_2026-10-14.md)
subsequently passed original-certificate signing, native publication and complete
Windows HTTPS APK readback. Sixteen local delivery checks and five native script
parses passed. Independent Mac trusted HTTPS first/last range checks match; its
additional full transfer timed out and is not counted as a pass. TV OTA stays v30.
Physical phone/TV and family listening acceptance remain pending.
Half-duplex turn taking remains in place; whole chapters,
streaming/latency changes and speaking interruption are later stages.


## Voice reliability qualification (October 13)

The [voice reliability contract](ASSISTANT_VOICE_RELIABILITY.md) passed the
complete API profile: 1,363 tests and 807 subchecks, plus the generated demo.
The later narrow ASR hardening rerun passed 18 checks, covering malformed Unicode
and rejecting arbitrary diagnostic categories. The synthetic private assistant
qualification now covers 11 scenarios, including explicit-number contexts,
terminal playback reports and durable safe recognition failures.

Phone checks passed 39 focused JVM tests with no failures or skips. A generated
API 36 simulator test checked the localized no-input error row in English and
Chinese at 150% text; both app renders were inspected. An earlier System UI ANR
interrupted one attach attempt; its evidence was retained. After dismissal, the
test passed and a separate accessibility read confirmed the QA landing choices.
Secure ordinary-page screenshots are not evidence of a blank UI.

The Web voice browser journey passed manual and continuous playback, absent
capability compatibility, all safe ASR categories, and a manual A-stop/B-start
race: late completion/error from A cannot report success for B. Each manual
attempt owns a new player and revokes its Blob URL on cleanup. The transcript
review browser journey also passed, preserving typed drafts, exact ASR parent
identity and old-account fences. Desktop/phone large-text status renders were
inspected.

These checks use generated data and synthetic speech. They do not establish
Windows candidate qualification, a signed phone release, live switching or
human listening. The phone version is reserved as v52; delivery uses separate
immutable artifact and operator receipts.

## Saved memoir editing (October 12)

The phone saved-book editor passed 822 live-core tests and 17 phone JVM tests,
unconfigured phone debug/test assembly, and phone lint. Six generated API 36
journeys passed with English and Chinese at 150% text: new memoir creation,
reviewed introduction voice input, and saved-book editing. The edit journeys
exercise permission without create authority, untouched cancellation, detached
controls, remove/add/reorder, a committed save with a lost response, exact retry,
fresh reopening, and the updated shelf revision. One language closes the saved
editor; the other explicitly opens its saved result. Both return to the same book.

Core checks also cover stale reader actions, unsent chat and voice barriers,
parent/child conflict, authorization denial cleanup, exact returned summaries,
and unchanged or reverted edits. Enlarged-text renders of both edit journeys
were inspected. The initial edit instrumentation failure came from reusing a
Ready-only wait helper for Closed/Retry-required/Saved states; a general state
wait corrected that fixture error before the complete passing rerun.

These checks use generated protected-library data and no model or live server.
They do not sign or publish an APK, establish physical-device acceptance, or
activate a capability. See [the composer/edit contract](PHONE_MEMOIR_COMPOSITION.md).

## Phone memory group checks (October 11)

The shared-memory phone editor passed 652 live-core and 17 phone JVM tests,
unconfigured debug/test assembly and debug lint with no errors (six existing
warnings). Its two generated API 36 simulator journeys cover reviewed selection,
original attribution across group members, manual adjustment, exact save retry,
native keyboard focus and Chinese/English at 150% text. Final renders were
inspected; fixtures use generated thumbnails and notes. This does not establish
a signed release, Samsung installation, provider quality or live e7 activation.
See [the feature contract](PHONE_MEMORY_GROUPS.md).

## Visual-vector publication and lifecycle checks

The ordinary `api` profile includes the optional vector publication journal,
read-only all-version cleanup planner, optional durable vector-erasure journal,
approved-task adapter and CPU-only
image-worker claim/publication checks.
They use generated SQLite/NPY fixtures and the standard library, with no model
or live service. The publication suite also runs one isolated synthetic child
which exits after file linking, then verifies journal recovery from a reopened
database. This is process-death evidence; Windows filesystem and power-loss
qualification remain separate.

The V3 asset journal suite exercises append/primary rollback, offline restore,
exact source/library verification, stale prepared bindings, legacy digest-preserving
upgrade and independently committed receipt checks for cleanup planning. It uses
private disposable databases and generated files; withdrawal is a retained-parent
status change, with no original/vector unlink. See
[asset withdrawal](ASSET_WITHDRAWAL_LIFECYCLE.md).

The separate [vector-erasure suite](VECTOR_ERASURE_LIFECYCLE.md) performs actual
filesystem cleanup only inside generated private temporary directories. It
checks complete manifests, known publication links, checksum/refusal boundaries
and resumable quarantine states. No household files or original media are deleted.
Catalog tests additionally restore an older primary lacking publication records,
exercise actual process death during archive creation and preserve partial
archives on refusal. The generated qualification runner performs the same source
operations with retained fixtures; its Windows supervisor is checked with a fake
native API locally. Source checks do not establish native Windows acceptance.

The actual-worker synthetic suite also dies after file publication and then
restarts with the same task claim, without activating a provider. It verifies
atomic task/artifact completion, approval/source guards, orphaned-intent refusal,
and duplicate completed-profile skipping. These generated checks exercise the
optional internal path; they do not decode real media or prove native inference.

Checkpoint and preprocessing receipt helpers are also in the ordinary CPU
profile. Synthetic transform objects exercise order, interpolation, crop size,
normalization and module bookkeeping without importing OpenCLIP or torchvision.
The optional image-worker suite additionally checks parent/child receipt binding,
checkpoint mutation during loading and dimension/recipe changes after probing.
An installed Windows provider canary is still required for actual transform
compatibility, dependency provenance and GPU execution.

```sh
.venv/bin/python -m pytest --noconftest -c config/pytest.ini -q \
  server/tests/security/test_visual_vector_publication.py \
  server/tests/security/test_visual_vector_worker.py \
  server/tests/security/test_immutable_image_worker.py \
  server/tests/security/test_visual_vector_cleanup.py \
  server/tests/security/test_visual_vector_erasure.py \
  server/tests/security/test_visual_vector_erasure_catalog.py \
  server/tests/security/test_vector_erasure_qualification.py \
  server/tests/security/test_asset_tombstones.py \
  server/tests/security/test_image_worker_claims.py \
  server/tests/security/test_image_embedding_receipts.py \
  server/tests/security/test_image_preprocessing_receipts.py
```

The existing image-worker media suite additionally needs NumPy/Pillow from the
optional worker test environment. No synthetic schema helper is a migration or
live activation command. See [activity grouping](ACTIVITY_GROUPING_DESIGN.md).

## Public source qualification history

This public monorepo is PhotoHouse's development home. The reviewed initial
import at `3140f1729872f689a276dcf8ecbfc0b9777c456f` passed hosted API and
Android CI through PR #1: 674 API tests with 352 subtests, 54 tooling tests,
the generated demo, and 773 Android JVM tests with lint and unconfigured
phone/TV debug builds. Later checks below remain bound to their stated revisions.
See [repository transition and legacy preservation](REPOSITORY_TRANSITION.md).

The subsequent same-day moments slice passed the complete API profile locally:
680 tests and 361 subtests, followed by the generated-data demo. Its focused
route/workspace/closed-boundary cohort passed 38 tests and 27 subtests; seven
actual-ASGI picker browser checks and ten existing workspace regression checks
passed with inspected desktop and bilingual 390px/150% renders. These cohorts
overlap and are not added together. It does not deploy the picker, change a
schema, enable a model, or integrate a native phone picker.

The subsequent phone picker source passed 591 live-core JVM tests, phone debug
and Android-test Kotlin compilation, and phone lint. Two bilingual generated-data
journeys passed on an API 36 emulator at 150% text, covering explicit lookup,
ordered video inclusion, preview clearing, save and fresh reader reopen. See the
[phone evidence](../clients/android/docs/ANDROID_RELATED_MOMENTS_2026-10-09.md)
for the exact acceptance boundary. This is an unconfigured QA build, not a new
signed or published phone release.

The worker packager now reads immutable Git blobs under the monorepo's `server/`
prefix while retaining the standalone repository and existing archive layout.
Its eight focused tests cover actual disposable Git repositories in both layouts,
dirty/untracked preservation, exact source-only contents and refusal cases.
An actual pinned `aa108411` source lookup now finds all 21 declared files; it
previously failed with `Worker source files missing`. No Windows worker was
started by this repair. The unchanged API route suite was not rerun locally
because the current system Python lacks Alembic; its earlier profile result
above remains bound to that source snapshot.

## Hosted source delivery (October 10)

PR #13 merged after the exact `2f17ed9` source passed all three hosted jobs:
936 API tests with 558 separately reported subtests, the generated demo,
92 standard-library tool tests, 812 Android JVM tests with lint and both
unconfigured debug builds, and the Windows private-reader cohort. These are
source checks; they do not update the installed API, sign a phone release,
publish OTA or establish family/device acceptance.

## Generated Windows CPU profile

PR #14 merged at head `12c10e9` after all four hosted jobs passed: 937 API
tests with 558 separately reported subtests and the generated demo, 92 source
tool tests, 812 Android JVM tests with lint/both unconfigured debug builds,
Windows private readers, and 65 Windows CPU tests with 25 subtests. The reader,
recording and TV UI source is unchanged from its local `9154e59` acceptance;
the later commit repairs only fixtures and their documentation. Hosted checks
do not change the household installation.

The optional [Windows CPU profile](WINDOWS_CPU_CHECKS.md) passed 65 tests and
25 subtests locally on macOS. Its new hosted Windows job is a separate gate and
does not replace qualification of the private installed runtime.
The first hosted run exposed Windows event-loop setup and POSIX mode-bit
assumptions in test fixtures; the [profile notes](WINDOWS_CPU_CHECKS.md) explain
the repair and the separate installed-directory ACL gate.

PR #15 merged at head `cd982a9` after all five hosted jobs passed. Its new
Ubuntu Web job completed seventeen generated suites using locked Playwright
Core and the matching headless Chromium shell. The same run passed 937 API
tests with 558 subtests, 93 source-tool tests, 812 Android JVM tests with lint and both
unconfigured debug builds, and both Windows cohorts. The local fourteen-suite
result below remains bound to its earlier Mac toolchain. The wrapper's
inherited-environment refusal and explicit tool-path preservation passed
thirteen scoped tooling checks. Hosted browser success does not establish
served household bytes or a signed-in device journey.

## Conversation reading and memoir edit checks (October 10)

The later conversation-reading and memoir-editor candidate passed all seventeen
generated Web suites locally with Node 22.17, Playwright Core 1.55 and cached
headless Chromium 1187. Focused checks preserve older reading anchors and verify
that delayed citation choices keep the title/intro form, cursor and composition
intact. Earlier failures are retained: the fixtures now wait for replacement
editors after retry and for authorized receipt refresh after a language change,
rather than matching text or cards from the preceding view. Final Chinese and
English 390 px/150% layouts were inspected; those renders use generated content.

The same candidate's declared API cohort passed 952 tests and 574 subtests,
including fifteen portable bad-video planner tests with sixteen subtests. The
generated no-listener demo passed separately, as did 93 standard-library tooling
tests. These overlapping checks are not added together. Exact source-ledger,
hosted CI, signed Android and household-service gates retain their own results.
See [Android release preparation](ANDROID_RELEASE_PREPARATION.md) for private
input profiles and artifact acceptance.

The final phone simulator cohort passed six journeys: five generated navigation
fixtures and the existing MainActivity uncertain-receipt flow. It checks older
reading preservation, actual tail geometry, the forty-turn cap, a real swipe
during observed jump-animation movement, and composer/recovery controls with
the keyboard open at 150% text. MainActivity now requests window resizing for
the keyboard instead of allowing its header to pan offscreen. Earlier failed
attempts are retained; the interrupted full-module run is not an aggregate
instrumentation pass. These generated checks do not establish a Samsung or TV
installation, microphone/provider quality, or household acceptance.
The source-bound live-core results contain 617 passing tests; the final task
was up to date because the UUID/cap changes had already been executed. Connected
debug lint passed. Two of the same navigation fixtures were rerun successfully
after correcting their screenshot sink; those results are not extra journeys.
The parent inspected the original final Chinese and English enlarged renders.

## Web assistant transcript acceptance (October 10)

The focused generated-browser journey passed six scenario groups covering
preserved typed text, explicit insertion and successful ASR receipt links,
1,024-byte boundaries, discard, malformed/untracked replies, invalid generated
WAV rejection before POST and overlapping old/current account requests. English
and Chinese 390 px/150% captures were inspected; detected-language labels update
with the UI language. No browser errors or external requests occurred. The
standard-library Web dispatcher suite passed 12 tests. These are local synthetic
checks, not a real microphone, provider, served UI or signed APK result. See
[the review contract](ASSISTANT_TRANSCRIPT_REVIEW.md).

The complete twelve-suite Web profile also passed. Its transcript suite preceded
the final detected-language label correction; the corrected fixture then passed
separately with six scenario groups and fresh inspected bilingual captures.
These overlapping checks are not combined into an additional total.

## Reader filmstrip and microphone startup checks

The final expanded Web profile passed all fourteen suites against unchanged
hashes of its five UI assets. The existing story-workspace journey also passed.
An earlier reader check exposed fixture timing around a lazy editor thumbnail;
it now waits for observable completion before snapshotting requests. A later
synthetic check reproduced an actual stale-preview error that added an
unavailable message to another story. Current image and video callbacks now
check reader ownership and attachment, and the final profile includes that
regression. Failed earlier logs remain separate from the final passing run.

The final focused capture fixture passed seven scenario groups, including stale
permission results, real pointer hold/release, immediate cancellation of held
startup, active capture cancellation and backgrounding while resume is held.
The note fixture also passed held text/audio saves, exact-draft clearing,
same-mutation retries, detached-dialog rejection, invalid-duration refusal and
maximum-duration completion during startup, plus its twelve existing history
and note scenarios. The memory-community UI contract passed eight groups. These
overlap the broader browser profile and are not added together as a test total.
The reader
fixture covers 24 frames in six chapters, explicit navigation, failed previews,
detached controls and logout. Original-resolution Chinese and English renders
were inspected at a 390 px physical viewport with 150% effective browser zoom
(260 CSS px at 1.5 device scale). These use generated media and audio APIs;
physical microphone, served UI and family acceptance remain separate.

The phone `SavedMemoryReaderNavigationUiTest` passed four generated API 36
journeys together with `lintDebug`: Chinese/English 150% text, frame/chapter
navigation, revision/order/library/account reset and removal of an eligible
item without a revision change. Both chapter buttons had equal full/visible
48 dp heights; both localized labels remained within the dialog window. An
earlier Compose-surface screenshot cropped the bottom of the Chinese capture;
the fixture now captures the full display and checks unclipped versus visible
bounds. The final bilingual full-display renders were inspected. Its preview
adapter returns no family images, and this is not signed-release or physical
phone acceptance.

The TV library-recovery journey passed with `lintDebug` on the generated
landscape emulator. Chinese/English 150% text renders were inspected: the
recovery message, Retry button, library controls and photo card remain visible.
The fixture checks full display bounds, a grid viewport of at least 120 dp,
preserved filters after two failures, and remote navigation from the recovered
selected library to a photo and its viewer. In compact landscape with enlarged
text, the decorative featured image yields space to browsing. This qualifies
TV v30 source; signing, OTA and the physical projector remain separate gates.

## D1 family-note lifecycle qualification

Pinned monorepo source `28f543c989230c8148c0af9c1300322aa8d604e5`
passed the complete Python 3.12 API profile: **876 tests and 502 subtests**,
followed by the generated no-listener demo. This includes the immutable extracted
API package check, default-off erasure route, historical-scope owner checks,
whole-edition prose erasure, journal failure fencing and explicit V1-to-V2 upgrade.
A preservation regression confirms unrelated upload annotations, contributions
and independent family notes survive erasure and replay. These cohorts use
synthetic databases; no live schema, journal or household content changed.
Native migration, paired backup/recovery and explicit live activation remain
separate delivery gates. See [the lifecycle contract](../server/docs/security/FAMILY_NOTE_ERASURE_V2.md).

## Older-schema preparation repair

The revision-aware preparation repair passed **50 tests and 12 subtests** across
small preparation, full-size preparation and runtime adapter suites. Both paths
perform actual Alembic migration to a0 on generated databases and refuse a
missing required a0 table. Later B1/C2/D1 tables are not required at a0; supported
revisions and exact D1 runtime checks stay unchanged. The supported API profile
now includes both preparation suites and a fresh-process extracted-package smoke
journey. Native/live preparation and migration remain separate gates.

## Independent title-provider wiring

Runtime and staging configurations now accept optional title provider settings
and their own default-off flag. The dedicated model projection requires the
`title_suggestions` role and an explicit opt-in, preserves conflict/rollback
checks and limits the timeout to 30 seconds. Default startup constructs no title
adapter; explicit construction performs no provider request. Title proposals
still require explicit selection and save in the existing Web/phone editors.
The runtime/staging cohort passed **38 tests and 100 subtests**; projection
checks passed **19 tests and 22 subtests**, with nine separate CLI tests. These
overlap the integrated six-suite run (**102 tests and 196 subtests**) and are
not combined into a total. No model,
GPU, native service or title quality is qualified by these fixtures.

## Conversation navigation qualification

The October 9–10 Web/phone slice keeps at most sixteen process-memory
conversation selections bound to current account, library, membership and
story/memoir revisions. Reopening uses a fresh authorized directory and history,
with an empty composer and no automatic recording or submission. Current access
denial clears the reader; delayed denial from an old phone reader cannot close
its replacement. See the [shared contract](CONVERSATION_NAVIGATION.md) and
[phone evidence](../clients/android/docs/ANDROID_CONVERSATION_NAVIGATION_2026-10-10.md).

The complete live-core cohort passed **610 JVM tests** with no failures or
errors. Phone debug and Android-test Kotlin compilation, lint and QA APK/test
assembly passed. **Five API 36 emulator tests** passed, including story and
memoir reopening in Chinese and English at 150% text; the four reader renders
were inspected. These use generated data and a separate QA application ID.
Earlier fixture-navigation and Android system-overlay failures remain separate
failed evidence. Keyboard/physical-device behavior, production signing, served
Web delivery and Windows OTA publication are not qualified by this cohort.

The complete ten-suite Web profile passed with cached Node 22, Playwright Core
1.55 and Chromium, using generated fixtures and an in-process ASGI bridge with
no listening server or production endpoint. Its navigation journey passed 23
checkpoint groups; Chinese and English 390 px/150% captures were inspected.
The profile also rechecked existing assistant recovery, memoir editors/readers,
edition inspection, title suggestions and related-media selection. Two stale
fixture issues were corrected without changing their assertions: deterministic
recovery-control scrolling and the current optional picker DOM in the shelf.

The check dispatcher has twelve passing tests. When a Web artifact directory is
selected, each suite now receives its own child directory so common result
filenames cannot replace another journey's evidence.

## Clarification presentation qualification

The subsequent Web/phone clarification slice passed the Web community contract
harness and **24 generated browser checkpoint groups**, with no page errors or
external-origin requests. Chinese and English captures use an actual 390 px
viewport and 150% text; the cue, help and suggested question remain visible
without horizontal overflow. Four focused API 36 phone journeys passed for
story and memoir readers in both languages at 150% text. Original-resolution
captures were inspected, with unclipped bounds checked inside the reader.

The journeys cover a passive ready-reply cue, preserving an existing draft,
explicit question insertion and Send, and hiding stale or invalid reply context.
Earlier fixture timing, Android system-overlay and capture-measurement failures
are retained separately from the passing journeys. These are generated browser
and unconfigured emulator results, not served Web files, a signed APK or family
acceptance. See [the presentation contract](CONVERSATION_CLARIFICATION.md).

## Visual grouping foundation

The new [visual grouping foundation](ACTIVITY_GROUPING_DESIGN.md) passed **14
synthetic CPU tests and 11 subtests** through the supported stripped environment.
They cover exact order, tolerated-norm normalization, ties, identity/checksum
refusal, foreign IDs before scoring, duplicate representations, nonconsumption
of lazy authorization inputs and hard cohort/dimension/result bounds. I/O and
process hooks are refused in the pure-function journey. The helper opens no
files or database and runs no provider. Its authorization snapshot records a
caller assertion; only later current-library integration can establish access.

## Web assistant trail qualification

The subsequent complete **eleven-suite Web profile passed**, including the new
[assistant turn trail](ASSISTANT_TURN_TRAIL.md). Five trail scenario groups cover
bounded plain-text exchanges, structured context, uncertain/malformed responses,
reload and delayed old-scope completion. The actual 390 px/150% Chinese/English
captures were inspected. Keyboard scrolling, newest-reply visibility, focus and
page-position preservation are checked without external-origin requests. The
dispatcher retains twelve passing standard-library tests. This generated profile
does not serve an update or qualify a production provider.

## Phone assistant transcript qualification

The subsequent phone assistant transcript slice passed **102 ConnectedStore JVM
tests**, three draft helper tests, phone lint and QA debug/test APK assembly.
**Six focused API 36 UI journeys** passed with fake adapters. Chinese and English
150% text captures were inspected; an overlapping two-case rerun preserved the
actual images after the test runner removed app-private files. Explicit Add
preserves typed words, Discard clears the parent link, overflow keeps both inputs,
and recording/review cannot submit. See [phone transcript evidence](../clients/android/docs/ANDROID_ASSISTANT_TRANSCRIPT_REVIEW_2026-10-10.md)
for the source, emulator and release boundaries.

## Inspect the local environment

## Worker diagnostics and matched picker qualification

The October 9 terminal-diagnostics slice passed the complete hash-locked Python
3.12 API profile: **802 tests and 473 independently reported subtests**, followed
by the generated no-listener demo. It includes 38 generated worker-report cases
and a new actual-migration a0 fixture that exercises the related-media route
through the existing-database adapter with generation/editorial/edition features
off. The fixture confirms its complete database dump is unchanged by lookup.
Focused cohorts overlap this profile and are not added to its count.

The separate seven-suite preparation cohort passed **102 tests and 37 subtests**,
including generated thumbnail/hash processing and fake embedding/face providers.
It used the same Python 3.12 environment with four additional hash-checked test
dependencies from the existing editorial lock: ImageHash, NumPy, PyWavelets and
SciPy. This is not GPU inference or a new serving environment. The eleven
standalone check-dispatch tests also passed.

Worker reports distinguish fixed refusal, SQLite, permission, I/O, interruption
and resource identifiers without copying private exception details. Child-mode
routing and terminal exit codes retain their existing behavior. See the
[report contract](../server/docs/security/APPROVED_WORKER_DIAGNOSTICS_V1.md).
These source checks do not explain an old installed scheduler failure or restart
a worker. Native package qualification, release parity review, service control,
phone signing/publication and household acceptance remain separate gates.

The earlier missing-Alembic collection limitation was resolved by restoring the
existing development lock into the monorepo's ignored environment with the
installed Python 3.12 interpreter. No model or GPU dependency is needed by the
ordinary API profile.

For the model source inventory, run `python3 tools/model_catalog.py --json`.
This standard-library check parses thirteen capability references and disabled
selection placeholders. It does not import ML dependencies, read model weights,
inspect private installation profiles or contact providers. The
[provider architecture](MODEL_PROVIDER_ARCHITECTURE.md) explains separate runtime,
resource, quality and model-replacement gates.

For a private deployment graph outside this checkout, use
`python3 tools/check_model_deployment.py --manifest /absolute/private/path --json`.
The [manifest guide](MODEL_DEPLOYMENT_MANIFEST.md) explains owner-private storage,
declared identities, distinct rollback selections and the redacted report. This
command checks configuration only; it does not read credentials, verify installed
weights, probe a runtime or apply selections. The public synthetic example has
all bindings disabled and invented artifact identities.

The typed assistant/memory bridge has a focused 15-test, 19-subtest source cohort
covering independent opt-ins, private credential injection, atomic conflict
refusal, parser/adapter timeout propagation and the existing shared worker
deadline. Three additional tool tests cover target/platform flags, redacted
projection and absent ambient credential resolution. These are configuration
checks; installed artifact/runtime identity and quality remain unverified.

The [qualification record checker](MODEL_QUALIFICATION.md) adds 18 offline
backend tests and eight standard-library CLI tests. These cover exact branch
and input-plan identities, explicit scope coverage, recorded resource/review
failures, stale/missing evidence, private metadata and bounded literal-file
hashing. Narrative input hashes match the existing generated memoir bundles.
The synthetic test files are not playable speech or model checkpoints, and the
recorded test verdicts are fixtures. No provider, GPU or semantic quality is
qualified by this source cohort.

The schema-2 WSL placement slice adds eight backend tests with ten subtests,
plus two CLI checks for Windows host projection and Linux evidence execution.
They cover strict placement, mixed native/WSL settings, rollback host refusal,
environment/distro identities, split qualification and private-instance redaction.
These tests use synthetic metadata and do not run a distro, model or service.

Run `.venv/bin/python tools/doctor.py` or add `--json` before selecting a test
profile. [Environment report](DEVELOPMENT_ENVIRONMENT.md) explains the read-only
checks and available/missing/unverified states. It inspects pinned package
versions, JDK/SDK/wrapper and optional cached browser prerequisites without
installing, building or contacting a service. A detected prerequisite is not a
test pass. Thirteen doctor tests passed, including timeout, version mismatch,
truncated probes and module paths with spaces.

The standalone [memoir canary](MODEL_QUALIFICATION.md#capture-one-synthetic-story-output)
has 15 focused source tests covering pinned cases, narrative/companion routing,
strict private settings, sanitized CLI failures, output reservation, exact file
hashes, private-file checks and separate provider/persistence failures. They use
fake adapters and block HTTP client construction. The command defaults to a
plan and has an explicit execution mode for one synthetic case. No model quality
or native runtime is qualified by these tests.

## Native Windows private-reader checks

The `windows-private-readers` CI job uses Python 3.12 and the existing locked API
dependencies. It runs the private-storage, deployment, qualification, TTS adapter
and standalone memoir-canary suites on generated fixtures. These checks exercise
native file metadata and DACL handling; provider calls remain faked, and no model,
GPU, speech playback or production activation is required. Linux API and Android
checks retain their separate acceptance scope.

The explicit cold-start canary profile has two additional source tests for
plan-only refusal and a single fake request receiving and recording a 90-second
timeout. The existing configuration suite also checks that the default cap stays
at 30 seconds, that 91 seconds is refused in cold-start mode, and that nonfinite,
boolean or invalid mode values fail closed. These tests do not contact a model.

## CPU quick start

The private [review worksheet](MODEL_QUALIFICATION.md#enter-human-judgments-with-a-private-worksheet)
has nine standard-library tests for exact source/case/rubric bindings, explicit
reviewer/time metadata, malformed inputs, private output creation before payload
write, path refusals and preserved failed/incomplete observations. Its guarded
import check refuses provider/network/process modules. These are synthetic
operator-workflow checks; they do not perform listening or establish quality.

From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r config/requirements-dev.lock
.venv/bin/python tools/check.py api
```

The Windows-reader baseline at `08e112e6ec2de68727d90b136042a7dcbc639dc3`
passed **759 API tests and 467 independently reported subtests** through
[hosted Linux CI in PR #10](https://github.com/phoenixjyb/PhotoHouse/pull/10)
on October 9, 2026, plus the generated-data demo and isolated package checks.
Its separate native Windows cohort ran 77 tests with three POSIX-only skips;
Android retained 773 JVM tests with lint/debug builds. These cohorts overlap and
are not added together. The earlier 755/460 run used an existing macOS arm64
Python 3.12.12 / pytest 9.0.3 environment without a fresh dependency install.
The private manifest cohort now contributes 20 tests and 41 subtests for declared
identities, contracts, rollback and private-file handling; the explicit
assistant/memory bridge adds 15 tests and 19 subtests.
The 89 standalone tooling tests include eight deployment doctor checks, nine qualification checks
and nine private review-workflow checks;
these counts are separate from the API profile. No model runtime or quality is
qualified by these checks. The isolated extracted API package imports the manifest, bridge and qualification
modules without a checkout fallback. The earlier 740/448 profile predates the standalone memoir inference canary.
The earlier 732/438 profile predates explicit
WSL placement. The earlier 714/419 profile predates the
qualification cohort. The earlier 699/400
profile predates the bridge, and the 680/361 profile predates the manifest.
The earlier 523/215 profile used a fresh
hash-locked environment with 27 applicable CPU packages and remains historical
evidence, along with the pytest 8.4.1 run and the 522/211, 498/197, 445-test
profiles. The current profile adds the story-workspace API contracts and covers
seven offline memoir quality planning tests, explicit memoir context and book
planning, and the conversation-preview service and transport checks. Earlier
profiles predate some of these checks. The profile covers
closed application routes, membership, uploads and approval, original deletion,
story contributions, chapters, assistant records and runtime path defaults.
The demo uses two generated images and an owner-reviewed member contribution;
anonymous library and community reads are denied. It opens no listening socket,
starts no model and makes no production connection.

To run only that disposable demo:

```sh
.venv/bin/python examples/generated-demo/check_demo.py
```

On Windows PowerShell, use the Python 3.12 launcher and Windows venv path:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r config/requirements-dev.lock
.\.venv\Scripts\python.exe tools\check.py api
```

The API profile already runs the generated-data demo. To run only that demo or
check the current source ledger, use:

```powershell
.\.venv\Scripts\python.exe examples\generated-demo\check_demo.py
.\.venv\Scripts\python.exe tools\verify_current_source.py
```

The demo uses generated data without starting a service or contacting a
provider or household server. The source verifier reports the current candidate
totals; changes to imported files need reviewed ledger records before that
check passes. These checks do not qualify native Windows services or devices.
The explicit profile uses `--noconftest` because historical inference tests have
a separate GPU and dependency lifecycle. Running every historical test is not
part of this small API development profile.

## Android checks

Install JDK 17 and Android SDK platform 34/build tools required by the Gradle
project, then set `JAVA_HOME` and `ANDROID_HOME` for your machine:

```sh
.venv/bin/python tools/check.py android
```

On Windows PowerShell, point `JAVA_HOME` at JDK 17 and `ANDROID_HOME` at your
Android SDK directory (with platform 34 and build-tools 34.0.0 installed), then
run:

```powershell
$env:JAVA_HOME = "C:\Path\To\JDK-17"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
.venv\Scripts\python.exe tools\check.py android
```

The check uses `gradlew.bat` through `cmd.exe` on Windows and `sh gradlew` on
macOS/Linux. It validates that the matching wrapper is present before dispatch.

After a build, summarize existing Gradle unit-test reports without rerunning it:

```sh
.venv/bin/python tools/android_test_report.py
```

The equivalent Windows command is
`.\.venv\Scripts\python.exe tools\android_test_report.py`. Missing required
module reports yield an incomplete inventory. Protocol reports are optional
because its current test task has no source; absence remains `no_report` and
adds no executed tests. Counts are checked against testcase outcomes. The tool
rejects malformed/entity XML, symlinks, changed files and oversized inventories.
It prints no raw test output, invokes no process and writes no files. A complete
inventory may contain failures or skips; its exit code describes readability
and completeness, not test success. Existing reports can be cached or filtered
and do not establish a fresh run, revision, APK or device acceptance.

## Read an existing Android instrumentation log

ADB's process exit status does not establish test success. AndroidJUnitRunner
can print `FAILURES!!!` and still leave `adb shell am instrument` with exit zero.
After saving its complete `-w -r` output, check it independently:

```sh
.venv/bin/python tools/android_instrumentation_report.py /absolute/path/emulator.log
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe tools\android_instrumentation_report.py C:\Path\To\emulator.log
```

This reader invokes no ADB/process/provider and writes no file. Input
is capped at 8 MiB and must be a regular non-symlink UTF-8 log. JSON reports
counts and fixed refusal codes without paths, test names, stack traces or raw
input. Exit zero and `complete: true` mean the supported runner protocol proves
one complete positive passing run: consistent runner/test fields, ordered
start/completion pairs, sequential indices, all pass statuses, matching final
summary and terminal code. Failure/error, skip/assumption, conflicting or
malformed fields, unknown statuses and truncated output remain nonzero.

The tool qualifies the bytes of an existing log only. It establishes no new
execution, freshness, source revision, APK identity, device, voice quality or
family acceptance. Keep build/source receipts and installation evidence separate.


The wrapper verifies its pinned Gradle distribution. The check runs six shared
Kotlin module test suites, phone/TV unit tests, lint and debug assembly. Without
explicit origin settings, these builds are unconfigured development artifacts.
The earlier full Android profile passed **592 JVM tests**, phone/TV lint and both
debug builds. Its acceptance record pins the Android baseline to
`312b40e1f865061ff98ec7f4d52fe3cdd31f4ff6` with the phone-v40 overlay
`9717b7aaf89f4516aa18b0daaef29ca9be7084ac`; this is the prior full-profile
revision, before the current conversation-preview source import. The protocol
module reports `NO-SOURCE`; it contributes no executed tests to that count. See
[local Android acceptance](local-android-acceptance.json) and the
[dependency inventory](ANDROID_DEPENDENCIES.md). Two focused v40 recovery/upload-history journeys passed on an Android emulator
from this unified layout at 150% text, with IME visibility asserted. Their rendered
screens were reviewed. The earlier six home-section checks belong to the preceding
source revision and are retained as historical evidence.
No installed physical-device or hosted CI result is claimed for this export.

Phone story and memoir conversation previews are imported into this public source
tree. Separate filtered `:live-core:test` runs passed 168 tests across the HTTPS API
adapter (6), wire decoder (8), repository (11), connected store (97) and memory
community store (46). This count is not included in the earlier 592-test full
Android profile. The pinned Android source workspace separately records 11
repository tests, 46 community-store tests and two synthetic API 36 emulator
journeys at 150% text with reviewed renders. Those emulator results do not establish emulator acceptance
for this public monorepo revision. See [phone preview evidence](../clients/android/docs/ANDROID_CONVERSATION_PREVIEWS_2026-10-05.md).

They are not household OTA releases. Do not add local signing keys or
`local.properties` to Git.

## Optional Web browser profile

The separate `web` profile runs four synthetic Chromium journeys for assistant
pending recovery, memoir editing, memoir reading, and story conversation. The
conversation suite covers 17 checkpoints, including legacy response compatibility,
first-message labels, one-request older-server fallback, stale-scope fencing,
draft recovery, and Chinese/English 390 px layouts at 150% text. Its focused run
passed and its screenshots were reviewed. After a readiness wait was added for
the source stylesheet rule and connected disclosure summary, the combined
four-suite profile passed. The native `list-item` marker assertion remains
strict; the fix changes the browser test only. These checks are source/toolchain
results, not live-service or family acceptance. See the
[conversation-preview contract](../server/docs/security/MEMORY_CONVERSATION_PREVIEWS_V1.md)
for the bounded opt-in response and fallback rules.

Run `python tools/check.py web` only when Node, Playwright, and Chromium are
already available. The profile is optional and does not install packages,
download a browser, start a listener, or contact a production origin. See
[Web development](WEB_DEVELOPMENT.md) for environment selection and artifact
handling. The b1 memoir editorial route remains disabled by default; browser
fixtures do not run or authorize a household migration. See
[story experience](STORY_EXPERIENCE.md) for the product boundaries.

## Required local profiles

### Optional local invocation receipt

Use `tools/check.py PROFILE --receipt /absolute/new/check.json` to record a
private local invocation without capturing raw test output or environment
values. The parent directory must exist and the destination must be new;
publication never overwrites an existing file. Without the option, the normal
profile dispatch remains unchanged. `all` still expands to `api` and `android`.

The JSON records start/end UTC times, HEAD, deterministic profile source
digests and the command exit code. Digests include relevant tracked files and
nonignored untracked source files, including dependency locks, paths, modes and
bytes. Build/cache/runtime directories and the receipt itself are excluded.
Missing Git, required source, unreadable files or symlinks make source identity
unavailable and cannot produce an unchanged-source claim. A command failure's
exit code is retained even if writing its receipt also fails.

This compares start/end snapshots; it does not prove every intermediate read,
identify installed toolchains or bind existing Gradle XML reports to this run.
It records no test counts or qualification claim. A matching snapshot and zero
exit code do not establish package, Windows, device or family acceptance. Keep
receipts outside source exports. Source `ff7c0f1` passed the 29-test generated
helper/CLI cohort and the complete 109-test tooling suite. Follow-up source
`127ca80` includes Android's shared `clients/android/contracts` resources in the
Android source digest; its focused helper/CLI cohort passed 31 tests. A real
Android profile subsequently produced matching start/end source hashes and a
zero exit code. These observations retain the limits above. Native Windows
receipt publication remains unqualified.

- API and security tests: Python 3.12, a small dependency profile, temporary SQLite and generated media.
- Android: JDK 17, pinned Gradle Wrapper, Android SDK 34; JVM tests, lint and unconfigured debug assembly.
- Web: synthetic authenticated API fixtures and responsive browser rendering.
- Optional providers: a separate machine/model installation with explicit resource and license qualification.

Ordinary development does not download model weights, connect to a household server, start scheduled tasks or read a family database.

## Public release gates

1. Export only approved files from exact revisions; exclude history and private operations evidence.
2. Review source literals and configuration. Explicit harmless loopback/synthetic examples may be documented exceptions; household endpoints may not.
3. Replace or record provenance for binary fixtures and brand assets.
4. Run the server/API/security tests and Android unit/lint/build from the new paths.
5. Resolve dependency versions, checksums and licenses, then validate the Gradle Wrapper.
6. Run a generated-data demo without any production configuration.
7. Review the complete tracked-file package and submit the curated candidate through the selected repository's pull request route.

A clean test run establishes that profile only. It does not establish a live provider, published OTA, installed device or family acceptance.

## Manual memoir editorial

The additive `b1d7e4a9c230` migration and optional editorial GET/PUT routes are
source-tested with generated SQLite and HTTP records. They retain introduction
citations and adjacent-story transitions while keeping existing memoir response
keys unchanged. Synthetic browser journeys exercise the Web editor and reader;
the reader suite has ten checks. The explicit `memory_editorial_enabled` flag
defaults to `false`; a0 remains a supported runtime revision. Passing generated
database, HTTP, or browser tests does not prove a live household migration or
service enablement. Enabling the feature requires the b1 schema, collaboration
and a deletion journal. No historical citations are backfilled. A populated b1
downgrade refuses to discard editorial records; use a reviewed backup/restore
procedure rather than dropping source history.

## Reviewed memoir editions (October 7, 2026)

The focused C2 source runs passed 121 tests and 104 subtests across 14 Python
suites. Together they cover edition service, contract, schema, provenance,
deletion, erasure, HTTP and migration, ORM migration integration, staging
configuration and packaging, approved-worker packaging and C2 compatibility,
and deletion initialization. They used the existing Python 3.12.12 environment,
whose package versions did not all match the development lock: iniconfig 2.3.0
(lock 2.1.0), packaging 26.3 (lock 25.0), and Pygments 2.21.0 (lock 2.19.2).
Treat this as focused source evidence, not an exact-lock CPU-profile result; no
packages were installed.

The edition browser journey passed with cached Chromium: the uncertain-save
retry reused an identical request, with zero browser errors and zero external
requests. An offline `:live-core:test` run passed 28 tests across the HTTPS
adapter, edition protocol, repository and coordinator suites with empty service
origins. No emulator, live migration, service, provider, signed package or
physical device was used. These results do not establish live-service or family
acceptance.

## Offline memoir quality planning

The [synthetic quality case planner](../server/docs/security/MEMOIR_QUALITY_CASES_V1.md)
emits three deterministic, bounded book bundles: a Chinese ordered-chapter
case, a two-author conflict about one shared photo, and a recent-turn/source
provenance case with an omitted source. The ordinary API profile includes seven
checks for the fixtures and plan-only CLI. The helper calls the existing bundle
validator but does not run inference, contact a provider, or report semantic
quality; it does not expand the separate three-case model canary or qualify a
native model.

Five approved-upload worker source entrypoints are included for maintainers.
They are optional operational components, outside the small CPU profile; face
and model workers have additional provider dependencies and resource requirements.
Importing or running `tools/check.py api` does not start them. The included
`run_memory_worker.py` launcher has eight synthetic checks covering read-only
preflight, explicit configuration and bounded execution with fixture providers;
these are part of the CPU profile. They do not establish native model quality.

The approved-face queue helper is stdlib-only and its 14 SQLite authorization,
claim, failure and recovery checks are part of the API profile. The separate
synthetic pipeline suite adds eight checks (22 combined with the queue tests):
it uses generated images, fake child results and temporary SQLite, with NumPy
and Pillow already available. It does not call the native inference child or
load a provider/model, and it does not require CUDA or a GPU. To run the
combined synthetic checks in an existing Python 3.12 environment that already
has these test dependencies:

```sh
python3.12 -m pytest --noconftest -c config/pytest.ini -q \
  server/tests/security/test_approved_face_queue.py \
  server/tests/security/test_approved_face_pipeline.py
```

The strict inference child and native model/provider execution remain separate
qualification steps. The face pipeline import is a new source delta and has no
native GPU or live-service acceptance; its synthetic tests do not establish
either result. Its Windows-only dynamic dependency on
`home_memory_envelope.WindowsJob` is now included in the source closure, and the
helper's local `home_preparation_resources` import is present. The existing
helper test covers input limits and fail-closed behavior on this non-Windows
host; three Windows Job Object integration tests are skipped here. That is not
native Win32 process-containment, CUDA/model or live-service qualification.

For provider qualification and privacy-safe failure evidence, see
[local model diagnostics](LOCAL_MODEL_DIAGNOSTICS.md).

## October 5 cross-client source imports

The Web source import adds original-versus-derived memoir source inspection,
explicit chapter/reply narration controls and reply continuity. The four-suite
optional Web profile passed against generated data. The focused source-inspection
suite and narration journey also passed; Chinese and English renders at 390 px
and 150% text were reviewed. The separate narration UI VM test passed. These
checks do not run a provider or household service.

The Android import adds memoir source inspection and explicit chapter/reply
narration. Filtered public-candidate JVM runs passed 111 tests for the source
inspection/integration and connected-store suites (9, 5 and 97), then 10 tests
for narration and its connected unit companions (4, 1 and 5). These are separate
from the earlier 592-test full Android profile. No emulator, release assembly,
signed APK, physical phone or live b1 service was qualified by these imports.

The approved-worker package builder's fixed source list resolves all 21 public
mapped files, including the portable processing contract. Its package and
synthetic schema/canary contract tests passed 10 tests and 13 subtests. The
selector defaults to a0; b1 testing is explicit and synthetic. This does not
build a package or qualify native Windows, GPU/provider, service or family
processing. See [the portable processing contract](../server/docs/security/APPROVED_UPLOAD_PROCESSING_V37.md)
and [canary output checks](../server/docs/security/APPROVED_WORKER_CANARY_OUTPUTS_V1.md).

At the October 5 cross-client import snapshot, the current-source verifier
passed with 828 tracked source files verified and 57 ordered overlays. Its
focused verifier tests passed 7 tests and 10 subtests.
The full API profile for those earlier imports was the separately recorded
498-test/197-subtest run. The October 6 profile below includes the newer context
and planning suites.

## October 7 saved memoir edition shelf

The phone source import adds an independent read-only shelf for saved memoir
editions. Readers with `can_save=false` can page through metadata and freshly
read a selected edition while book editing and AI arrangement controls remain
unavailable. The default-off C2 capability and existing HTTPS routes are
unchanged. The client validates current book and chapter scope; the backend
remains authoritative for membership and source closure. No prose is persisted.

The phone source checkout separately passed 86 focused JVM tests and lint with
no errors and five warnings. Its final bilingual 150% emulator journeys covered
the shelf and the existing editor/retry/keyboard flows; final renders were
reviewed. This is source-checkout emulator evidence.

In the public candidate, five filtered `:live-core:test` suites passed 86 tests
with no failures or skips. `:connected:compileDebugKotlin` and
`:connected:lintDebug` passed; lint reported six warnings and one informational
item. These checks used JDK 17, offline Gradle and empty service origins. The
candidate was not installed on an emulator or device, signed, published, or
connected to a household service.

The Web reader adds a saved-edition shelf with metadata-only pages, fresh detail
reads, source invalidation handling and explicitly started local chapter speech.
Shelf speech controls are scoped separately from private proposal and chat audio.
The optional browser fixture uses synthetic records and local mock voices; it
does not enable C2 or contact a household service.

The candidate shelf and existing editor browser journeys passed with zero browser
errors and zero external requests. The shelf fixture reported 15 metadata pages
and 54 reader requests; the editor fixture confirmed its retry reused identical
content. The 390 px Chinese and English renders at 150% text were inspected.
`python3 -m unittest tools.tests.test_check` passed all nine tests, including
dispatch and missing-suite checks for the shelf browser suite. This is targeted
candidate evidence; the complete optional Web profile was not rerun.

## October 7 edition-bound original source inspection

The saved-edition reader can explicitly request a paged source catalog, one
edition-bound source detail, or an original recording. It validates the
selected edition's current source closure on every read. C2 and original-source
runtime gates remain off by default. The focused candidate run passed 97 tests
and 43 subtests across nine edition/source suites and the closed route inventory;
the checker dispatch tests passed 11 tests. The optional browser journey passed
with two save requests carrying the same retry payload, zero browser errors and
zero external requests. Its Chinese and English 390 px renders at 150% text were
reviewed.

The phone source checkout passed its final two bilingual emulator journeys in
74.599 seconds; the explicit notice was visibly brought into view and four final
renders were reviewed. Its debug app/test build and lint passed. In the public
candidate, the filtered `:live-core:test` scope for edition, community,
`ConnectedStoreTest` and `HttpsMemoryCommunityApiTest` passed 226 tests with no
failures or skips. `:connected:compileDebugKotlin` and `:connected:lintDebug`
passed using JDK 17, offline Gradle, empty origins and two workers. Candidate
lint reports contain 0 errors, 6 warnings and 1 informational finding; compiler
warnings remain separate. No release APK, candidate emulator,
live service, production media or family acceptance was established. These are
focused candidate source and synthetic browser results; the complete API and Web
profiles were not rerun. After the voluntary-byline fix, the two focused
source API suites passed 10 tests; the existing Starlette/httpx deprecation
warning remains. After the keyboard focus/reveal and family-note attribution
updates, the focused candidate browser journey passed with two identical retry
payloads, zero browser errors and zero external requests; it covered viewport
reveal, focus preservation, and the current asset-note byline. Five narrow
candidate Python suites for jobs, processing, source service/API and contribution
references passed 61 tests and 24 subtests. The wider 65/31 and 63/44 cohorts in
the architecture map are source-checkout evidence, not candidate test totals.

## Verify an imported release snapshot

```sh
python3 tools/verify_current_source.py
python3 -m unittest discover -s tools/tests -p test_verify_current_source.py
```

The current-source checker applies the original export, reviewed public
transformations and ordered feature overlays, then hashes their recorded files.
It does not require Git history, rebuild artifacts or download providers. This
is a release/provenance check for an imported snapshot; subsequent authored
source changes need their own reviewed records before making the same claim.
The CI template checks this ledger before API tests. Include each changed source
file and its before/after digest, plus new files, in a new reviewed
`docs/feature-source-changes.json` entry in the same pull request. Keep original
export and transform records intact. This digest check does not replace privacy
or code review.
The earlier `verify_source_baseline.py` remains an initial-import checker, not a
requirement to rewrite historical records during ordinary development.

## Test runner dependency refresh — October 4, 2026

The development-only lock uses pytest 9.0.3 and explicitly pins Colorama 0.4.6
for Windows. Serving dependencies in `config/requirements-api.lock` are unchanged.
The old pytest 8.4.1 pin is affected by the local UNIX temporary-directory issue
recorded in [PyPI release metadata](https://pypi.org/pypi/pytest/8.4.1/json);
the recorded fixed release is 9.0.3. This is a test dependency update, not a
security audit of every dependency. Artifact hashes and license notices were
refreshed from the pinned releases.

A fresh CPython 3.12 Mac environment installed the lock using hash-checked binary
packages. Its supported API profile passed 445 tests (158 subtests), followed by
the generated-data, no-listener demo. The Windows amd64 CPython 3.12 wheel set and dependency markers were
qualified separately; this does not claim Windows test execution. Cross-platform
`pip download --platform` can still evaluate conditional dependencies against the
host OS: ensure the wheelhouse includes the pinned Colorama wheel before a
Windows offline installation.

## Optional memoir migration and worker rehearsal

The [separate editorial test profile](../server/docs/PHOTOHOUSE_EDITORIAL_TEST_PROFILE_2026-10-04.md)
provides a complete hash-pinned CPU environment for six fresh synthetic test
processes. Run its commands from `server/`; it does not replace the default API
profile or a serving environment. The profile's macOS run passed 103 tests;
Windows wheel metadata is qualified separately from native execution. Its
[artifact and license inventory](editorial-test-dependencies.json) also covers
conditional Windows dependencies and bundled license texts.

## Android memoir editor qualification

The optional memoir editor was qualified in the Android source checkout at
`9caf11eb4fc1445d30fd35889104839bb6f03d55`. The unified candidate imports its
nine changed Git blobs without transformation. See the
[focused commands and acceptance boundary](../clients/android/docs/MEMOIR_EDITORIAL_UI_2026-10-04.md).
All 213 focused/adjacent JVM tests and four instrumentation tests passed; final
100% / 150% synthetic screenshots were reviewed. The accepted-save / lost-ACK
journey retries the exact request and reopens the saved text and citations.
This does not advance the release version, sign an APK, contact family services
or enable the b1 schema. Keep generic branding and unconfigured endpoints when
building this public candidate.

## Optional native memoir rehearsal

The [rehearsal guide](../server/docs/PHOTOHOUSE_EDITORIAL_REHEARSAL_2026-10-04.md)
records the original six-group / 103-case fixture archive and bounded Windows
process controller. That historical extracted source passed locally; 18 portable
controller and audit-guard tests also passed. The current runner has nine fixed
groups / 151 cases, including the schema application, face queue/pipeline and
SQLite URI admission suites. The successor archive builder closes its fixture
imports from pinned Git blobs. These checks do not establish native Windows
execution or authorize a live migration.

Run the portable controller checks from `server/`:

```sh
python3 -B -m unittest discover -s tests/security -p test_bounded_windows_job.py
```

Private operator pins, Windows wheels and execution authority are excluded from
this public source snapshot. Native rehearsal uses a fresh disposable environment
and an explicitly reviewed operation; ordinary contributor checks do not stage
files on another machine.

The first native rehearsal passed staging, timeout cleanup and fresh offline
environment qualification, then stopped at a Windows fixture socket-mock
incompatibility (33 passed, 14 failed in group 1; later groups did not run). The
fixture correction has six portable guard regressions and 48 adjacent tests /
17 subtests passing. This source still requires native requalification. The
failed candidate is retained; no live migration or release is implied.

## Offline schema application

The public profile now covers the read-only-by-default a0→b1 operator, preserved
historical data and schema, backup mismatch, running tasks, literal-sensitive
schema checks and migration rollback. See the
[application contract](../server/docs/security/MEMOIR_EDITORIAL_SCHEMA_APPLICATION.md)
and [maintenance workflow](MAINTAINING.md). These synthetic checks do not stop
writers or authorize application against an installed database.

See [the product roadmap](ROADMAP.md) for the next complete user journeys.

## Windows SQLite URI admission repair

A later 139-case Windows attempt passed staging, timeout cleanup and the fresh
offline environment, then stopped at group 1: 44 passed and three generated
journal URI admissions were rejected. Groups 2–8 did not run. The guard now
parses local SQLite file URIs before native path resolution, retaining the
candidate-root restriction. Twelve focused tests and 30 subtests passed in this
unified layout. The updated private 235-file archive passed all nine groups /
151 cases on macOS; native execution still needs a separately authorized run.
The production API/worker archives were not changed by the guard repair. See the
[URI contract and failure boundary](../server/docs/security/EDITORIAL_REHEARSAL_SQLITE_URI_V1.md).

## Focused memoir development

```sh
.venv/bin/python tools/check.py memory
```

This CPU-only profile covers 14 suites: private storage, original contributions
and their references, books and editorial reads/deletions, explicit context,
read-only book planning, jobs, narratives, processing and HTTP transport. It uses
disposable synthetic data and makes no provider or production calls. The
October 6 run passed **127 tests and 76 subtests**. The full `api` profile now
also includes the context and book-planning suites; it passed **522 tests and
211 subtests**, followed by the generated no-listener demo. These runs reused
an existing Python 3.12 development environment; they are not a fresh dependency
installation or native Windows qualification.

The imported Web context choice passed its JavaScript contract harness and
17 synthetic browser checkpoints at mobile/large-text widths, with no page
errors or external origins. Whole-memoir phone planning and chapter review
from `2a8cf8e` passed 67 focused JVM tests in this unified layout. The separate
phone source workspace has bilingual emulator/lint evidence; this import does
not establish an APK, public-candidate emulator result or live generation.

Web plan-to-story navigation from `e10409d` passed 19 synthetic browser
checkpoints and its UI contract harness in this layout. It reauthorizes the
parent and child revisions while preserving the memoir companion draft.
The separate source Android directory has final bilingual 150% emulator/lint
evidence; this public import does not claim its own emulator result.

The per-story phone plan import passed 78 focused JVM tests, debug compilation
and lint in this unified layout. The four core suites are narrative store,
community store, editorial integration and narrative dictation store. The
separate source workspace has two final bilingual 150% plan-reading emulator
journeys; this layout was not installed on an emulator. Its complete standalone
tool suite passed 36 tests, including the doctor.

## CPU child environment

`tools/check.py api` and `memory` pass only platform basics into their pytest
children, set `PHOTOHOUSE_NO_DOTENV=1`, disable pytest plugin auto-discovery and
user-site imports, and discard inherited database, model, provider and Python
plugin settings. The generated demo uses the same child environment. This
is configuration isolation for supported generated checks; it does not sandbox
the parent interpreter, installed dependencies or arbitrary historical tests.
Android and Web tool selection keeps its existing configuration.

All 40 standalone tool tests passed, including four environment-dispatch checks
and the 13 doctor checks. The exact-lock API run followed this change. The
doctor separately found API, memory, Android, Web and all prerequisites
available; this inventory does not qualify builds, native Windows or services.

## Latest complete Android and Web qualification

On October 6 the current Android imports passed 684 JVM tests (24 core,
492 live-core, 130 home-core, 3 playback-core, 16 story-fixture-core, 10 phone
and 9 TV), debug lint and both debug builds. A private init script forced
actual test tasks to execute; protocol remained NO-SOURCE and adds no tests.
The run used the existing JDK 17/SDK, offline Gradle, no daemon and two workers.
Generated BuildConfig origins were empty and feature flags disabled. It was
not installed on an emulator or device, signed as a household release or
published. The earlier 592-test result remains in the acceptance data.

All four supported Web suites passed after importing `635ce03`. Its community
journey has 22 checkpoints, no page errors or external requests, and reviewed
390px/150-percent displays. The current reading chapter can prepare an editable
question without switching the whole-book conversation or sending anything.
Opening prompts now share draft/IME/voice/send guards with follow-up questions.
Fifty standalone tooling tests passed, including ten report-inventory checks.

## Independent title qualification cases (October 10)

The source planner now retains the original three memoir bundle hashes and tasks
and adds three title-only bundles. A combined offline run of planner, canary,
qualification, checker and human-review worksheet tests passed **68 tests and
59 subtests**. The title cases cover Chinese family/draft input, conflicting
English recollections and empty-source abstention. The real title adapter handles
the empty case without constructing an HTTP client; nonempty canary contract
checks use fake providers and keep every semantic criterion unreviewed.

The canary dispatches each pinned case to its explicit role/task, refuses input
or rubric substitution before output/provider construction, and validates cited,
revision-bound, review-required title outputs before private capture. No native
inference, household material, provider activation or live configuration change
was performed. Current and rollback title provider observations and human review
remain open. See [model qualification](MODEL_QUALIFICATION.md).

## October 12 story composition and reading

The full Android source profile passed JVM tasks, phone/TV lint and both debug
builds before the final chapter-arrangement and memoir-session changes. Its
report inventory was 909 tests: core 24, live-core 709, home-core 131,
playback-core 3, story-fixture-core 16, connected 17 and TV 9. Protocol had no
test source. Some unaffected tasks were up to date; this is not 909 newly
executed tests or a release signing result.

[Reading continuity](PHONE_STORY_READING_CONTINUITY.md), source `7b3e68d`, passed
five generated API 36 tests using real Android Keystore encryption. The reader
suite also passed eight journeys, including saved editing and explicit reading
resume. Fresh English and Chinese 150% resume captures were inspected after
removing an emulator System UI interruption; the earlier obscured captures are
not visual acceptance evidence.

[Chapter arrangement](STORY_CHAPTER_ARRANGEMENT.md), Web source `07a340d` and
phone source `a5396a2`, passed the 710-test live-core profile after a new fixture
was corrected to close its retained voice observer. An initial combined
instrumentation run exposed a chapter voice cleanup null dereference. The fix
binds disposal to the rendered helper. Its final follow-up passed five bilingual
chapter arrangement/dictation journeys plus two bilingual reading-resume
journeys. English and Chinese 150% chapter controls and clean resume captures
were inspected. These are generated data on the existing API 36 emulator.

Memoir voice actions in source `1e4ac83` likewise retain the rendered helper:
a delayed Add or Close from an old panel cannot consume or clear a replacement
session. The two focused JVM suites passed 81 tests, followed by phone UI
compilation. These overlapping runs must not be summed into a new full-suite
count. Full browser and any later phone checks have their own pinned results.

The 19-suite Web profile subsequently passed with the exact-source restoration
readiness fixture from `a01b4a0`. Its earlier complete-run failure was not
reproduced by two isolated runs; the strengthened fixture waits for the saved
source IDs rather than observing a transient checkbox count. This establishes
the final generated browser journey, not a proved cause of the earlier failure.
Memoir voice source `1e4ac83` also passed phone lint/debug assembly and both
English/Chinese 150% emulator journeys. Their transcript-review renders were
inspected; Add and generation stayed separate explicit actions.

[Web source-conflict recovery](WEB_STORY_SOURCE_REFRESH.md) at `acb9036` passed
29 focused browser checkpoint groups. The full profile found a partial-workspace
initialization error in the memoir edition shelf: its export control was outside
the action host. Source `b5ebf2b` preserves production footer order while mounting
under that partial host; the complete 19-suite Web profile then passed. Chinese
390 px/150% source-review controls were visually inspected. This is browser
fixture evidence, not a live Web switch.

[Phone album-to-story selection](PHONE_ALBUM_TO_STORY.md), source `b3ddd57`,
passed 12 focused wire/transport/selection tests and the complete Android source
profile with phone/TV lint and debug assembly. Its report inventory was 923 tests
(live-core 723; other module counts as above), with zero failures. Unaffected
tasks were up to date. Four API 36 creation journeys passed, including both new
album flows; two direct focused reruns extracted English/Chinese 150% renders
for visual inspection after the Gradle runner removed the app. Those overlapping
runs are not six distinct tests. Larger albums, replacement confirmation,
manual adjustment, library return and explicit outline creation were verified.

The backend profile remains the earlier 1,208 tests and 687 subtests at
`d0d8a34`; these client slices added no route or schema. No Windows service,
household database, model provider, release signing, OTA feed or physical device
was changed by these local checks.

## October 12 memoir continuity and narration

The compact phone album controls at `4ef7255` passed the same four generated
creation journeys after the layout change. English/Chinese 150% captures were
inspected; limits, larger albums, replacement confirmation and explicit outline
creation retain their original checks.

[Memoir continuity](PHONE_MEMOIR_READING_CONTINUITY.md) at `c3e2706` passed the
extended 124-test core cohort after the final current-denial parity changes.
The complete Android run before those last changes had a 934-test inventory;
its first lint attempt found two direct StateFlow reads inside composition.
Replacing them with collection fixed both errors, and phone/TV lint and debug
assembly then passed. The final focused cohort checks the later denial changes.
Six memoir encryption tests and six story encryption tests passed on the
existing API 36 emulator. The story suite includes an independently built old
envelope, preserving legacy alias, filename and authenticated context after the
shared encryption helper refactor. Two English/Chinese 150% reader journeys
verify fresh access, exact selected media, explicit Continue and Start over.
Both final offer renders were inspected. Overlapping reruns are not new tests.

[Explicit phone memoir narration](MEMOIR_NARRATION_CONTINUATION.md), source
`92b1285`, passed a 90-test memoir-store cohort and the complete Android source
profile. Its report inventory is 945 tests: core 24, live-core 745, home-core 131,
playback-core 3, story-fixture-core 16, connected 17 and TV 9; protocol has no test
source. All reports have zero failures, errors and skips. JVM tasks, phone/TV lint
and debug builds passed, with unaffected tasks up to date. This is not 945 newly
executed tests. Eighteen generic narration cases and three memoir narration
journeys passed in direct emulator instrumentation, followed by the two existing
continuity journeys. Both new English/Chinese 150% narration controls were
visually inspected. Fake local speech adapters establish control flow, not
audible quality or installed voice availability.

Web narration continuation at `ce2467c` passed 24 focused memoir checkpoint
groups and the complete 19-suite profile, with inspected English/Chinese
390 px/150% controls. Later navigation changes have their own qualification;
this result must not be attributed to an untested newer tree.

Web manual navigation at `074d096` passed the focused 24-checkpoint memoir
journey and a final complete 19-suite profile. The first full attempt timed out
at the saved story's Edit/reopen step in the workspace suite. Two isolated runs
and the final full profile passed without repository changes; instrumentation
observed the expected workspace-open/reader-closed state. The initial cause
remains unknown, and the isolated passes are not evidence of a particular fix.
Both bilingual large-text story-boundary controls were inspected. Detached
navigation cannot stop replacement narration or fetch another story.

All these checks use generated content and local debug artifacts. Release
signing, OTA, live Windows changes and family/device acceptance remain separate.

## October 12 memoir contents and media accessibility

Phone source `a0fdbca` adds a collapsed original-reader contents panel, exact
rendered-state navigation guards and selected numbered media cards. The focused
memoir-store cohort passed 94 tests. The complete supported Android source
profile then passed JVM checks, phone/TV lint and both debug builds. Its report
inventory contains 949 tests (live-core 749, other module counts as above), with
zero failures, errors or skips; unchanged tasks were up to date.

Nine direct API 36 emulator journeys passed: two detached-navigation cases, two
bilingual contents cases, two extended continuity cases and three previously
implemented narration cases. Contents opening performs no child prefetch;
explicit child selection loads only that child, and chapter selection retains
the bookmark. The first navigation test attempt used a still-attached Compose
semantics dispatcher and incorrectly treated its updated callback as stale;
the corrected test disposes the original controls before invoking them. This
was a test-fixture correction, not a claimed product fix. The first media-card
render also placed its current badge over failed-preview text; the final layout
uses a separate label line. Final English/Chinese 150% contents and selected-card
renders were inspected. Repeated continuity/narration cases are not new tests.

Web source `210222b` passed 27 focused memoir browser checkpoint groups and the
complete 19-suite profile. Final English/Chinese 390 px/150% captions were
inspected after making a two-item mobile chapter full width. Detached media
controls and delayed preview errors cannot affect replacement narration or
start fallback requests. The optional invocation receipt records matching
start/end HEAD but different source hashes because the receipt helper itself
changed during that run; it correctly reports `source_unchanged=false`. The
Web files were frozen, but this receipt must not be presented as an unchanged
whole-invocation identity.

All media, notes and speech adapters in these journeys are generated. These
results do not qualify original-media quality, native speech, a signed release,
served Windows files, a physical phone or a TV.


## October 12 chat navigation and assistant result compatibility

Phone source `c566ded` accepts the server's seven-field assistant result/open
assets and the validated date-hint extension. Two generated 150% Compose date
journeys passed; they check capture metadata precedence and localized
filename/received/unknown labels. The focused AssistantWire/AssistantTransport
JVM checks and phone debug/AndroidTest assembly/lint passed. The earlier complete
Android profile reported 951 tests, no failures, and matching optional receipt
source hashes; unchanged tasks were up to date. The added protected transport
case is later evidence, not part of that historical count.

At `7d7b1ef`, four generated story/memoir × English/Chinese latest-page journeys
passed. They verify exactly one direct page-one read, unchanged composer, no
submission/creation/transcription and no request from hidden or detached page
controls. Final bilingual 150% reader captures were inspected. A preliminary
screenshot-root selection failure was corrected. The hidden-memoir action then
reproduced an extra request before composition-lifetime guarding; after the fix,
both latest and existing newer/older controls are guarded. An initial combined
11-case run passed nine cases but failed both story cases because the delegated
fixture omitted the theme-capable story-list overload. The corrected four-case
chat run passed; this is not represented as an initial 11-case pass.

Memoir source `1094890` brings the heading into view after an explicit chapter or
story change. The two enlarged-text contents journeys assert the visible heading;
they and three affected narration cases passed in the combined run above.
Preview completion and frame selection do not trigger this scroll.

Backend source `e042544` distinguishes only the permanent 128-turn refusal with
allowlisted JSON `code: memory_conversation_full`. The 128th submission and exact
mutation retry at the cap remain accepted; the next new mutation adds neither a
turn nor a job. Authenticated HTTP checks keep global pending-work and 32-thread
creation refusals untagged. The focused jobs/editorial HTTP cohort passed 28
tests and 28 subtests. Root's combined rerun with the existing assistant HTTP
journey passed 39 tests and 33 subtests. The existing Starlette/httpx deprecation
warning remains. Client continuation controls and complete final source profiles
are following checks, not established by this backend result.

### Full-conversation continuation qualification

Web `54f323b` passed 30 focused generated checkpoint groups, including exact
429 parsing, same-UUID retries after uncertain creation or failed initial
history, retained edits, and detached controls. The complete Web profile then
passed all 19 suites at `a1c6e94`. Its optional receipt recorded exit zero and
matching source snapshots (`f68df337d7f935a54620f700e952ef2d07987d227f63286bcbdc8be43f4c4731`).
The complete backend profile passed 1,210 tests and 692 subtests at the same
HEAD, with matching API source snapshots
(`bf938d234b493db0ffd550a8dea97189b0a29d212129fee6d5b9d30b3c6b2f22`).
These receipts bind source paths and bytes at invocation boundaries; they do
not bind the installed toolchain or prove the freshness of cached Gradle reports.

The phone continuation's scoped store and transport cohort passed 115 JVM
tests, with debug assembly and lint. The complete Android source profile
before memoir-composer integration passed and its XML report inventory was
963 tests, with no failures, errors or skips; unchanged tasks were up to date.
Its receipt recorded matching Android source snapshots
(`ffc8a7aac68182b1c614f14d2d1cad25d34b3c8e2cee595f22b0efb14af435d4`)
and unchanged HEAD `04f5317`.

The first combined simulator run passed the four existing latest-page journeys
and two assistant-date journeys, but failed four new continuation assertions:
the fixture expected a rejected question in the next editable draft, although
the store correctly held it separately until Continue. After correcting the
fixture and checking the retained-question review, all four continuation
journeys passed in 90.928 seconds. They cover English/Chinese story/memoir
views at 150% text, an uncertain create and exact retry, edits during creation,
retained old history, explicit unsent transfer, and detached callbacks. The
four refusal renders and two continued renders were inspected. See the
[contract](MEMORY_CHAT_CONTINUATION.md).

The maintenance-tool suite passed 111 tests and 38 subtests after the optional
receipt-source closure changes. This is local tooling evidence, not native
Windows or installed application evidence.

All data is generated and all speech interactions retain explicit start/send/play
boundaries. No signed APK, household service switch, migration, model execution
or family-device acceptance is established by these local results.


## October 12 phone memoir composition and reviewed introduction

Accepted source `e157679` passed a 161-case focused core cohort: composition
14, introduction dictation 5, shared dictation 10, repository 22 and community
store 110. The corrected source/debug/instrumentation build passed; a stale
summary in the late conversation-denial fixture was replaced with the current
protected shelf summary before reopening. This was a fixture correction.

Four generated English/Chinese composer journeys at 150% text and six shared
dictation journeys passed on the existing API 36 emulator in 157.889 seconds.
They cover explicit selection/order/save, identical uncertain retries, current
parent reopening, reviewed voice insertion into the latest typed introduction,
over-limit retention and detached helper controls. The first voice run had two
fixture failures because it counted an existing app-wide capability request as
composer work; the corrected fixture measures its baseline. Source inspection
also removed a duplicate capability query on dictation-input mount. Visible
order controls were shortened to Move up / Move down / Remove, and all four
composer renders were inspected after rebuilding. The generated-WAV composer
fixture does not use a microphone; one shared dictation case uses the emulator
microphone with a synthetic ASR adapter. No real provider quality, family data
or physical-device result is claimed.

Web source `903a7f9` preserves an existing memoir's language when its editor has
no language selector. Editing a Chinese memoir in the English UI and retrying
the same uncertain mutation passed the 30-checkpoint generated community
journey. This does not change the locale default for a new memoir.


## October 12 protected visual memoir shelf

Phone source `61847c7` passed 12 cover-store cases and 113 community-store cases.
Covers are bounded, sequential protected thumbnails; ready and staged bytes are
wiped when the shelf leaves its scope, including uncooperative late responses.
A compile failure in a nested test helper was corrected before this passing run.
Two new bilingual 150% shelf journeys passed in 14.644 seconds after fixing
merged-tree/decorative-tag fixture selectors and a real lazy-list event reuse
issue. Render identity now recreates event nodes while preserving scroll state;
captured old read/retry actions are inert after replacement or unmount. Both
renders were inspected. The preceding combined emulator run passed all nine
affected contents/narration/composer cases but failed the two new selectors;
those failures were retained before the focused correction. The source/debug
and instrumentation build passed after the final event-lifetime correction.

Web source `a6bae31` passed 30 generated community browser checkpoints. The
exact shelf card/list/book predicate now travels into the API helper before
sending, after response and before denial cleanup. A delayed same-library 403
cannot erase the selected old-conversation hint; reopening restored the selected
conversation in the generated fixture. No new routes or media requests were
introduced by this guard.


## October 12 Web memoir introduction dictation

The generated Node UI journey covers explicit capability/record/stop/review/Add/
Save actions, edits during deferred recognition, full-text UTF-8 overflow
retention, malformed output, uncertain-save freezing, obsolete/current denials,
membership replacement and background cleanup. Browser qualification includes
English and Chinese at 390px and 150% text, synthetic WAV/capture/transcription,
and exact introduction persistence only after explicit Save.

The first introduction render fixture multiplied inherited font sizes while
walking descendants, compounding its 150% scale. The fixture now snapshots all
computed sizes before applying the scale. Its initial 34-check result remains
historical; final render evidence is recorded after the corrected run. Source
review also found memoir capture could overlap a chapter's shared microphone
reservation; the adapter correction and targeted qualification are recorded
with the accepted pin below.

Web source `bd8f6b6` passed the ten Node UI journeys, WAV encoding and shared
microphone adapter checks, JavaScript syntax and whitespace checks. A root
invocation of the UI test from the repository directory first failed because
its relative source path requires the documented `server/` working directory;
the corrected invocation passed. The final generated browser profile follows
this source pin and includes corrected enlarged-text rendering. Selection,
ordering and More controls bind the exact mounted form and membership; repeated
More actions share one in-flight page read. Old and pending-save actions cannot
mutate the current selection. Excerpts retain 240 complete Unicode codepoints.
Voice review also disables both book Save and editorial Save until resolved.

Phone version source `a4507e3` reserves v47 (`0.47-family-memoir-composer`).
The [release candidate](../clients/android/docs/PHONE_V47_RELEASE_CANDIDATE_2026-10-12.md)
records its user-facing changes and remaining private-profile, signing, OTA and
family gates. This task has not contacted Windows, changed a runtime task,
published source/APKs or installed a physical device.


## October 12 complete client profile follow-up

At `d3a9a93`, the complete Android JVM/lint/debug source profile passed in
2m26s (175 tasks: 38 executed, 137 up to date). The existing XML report inventory
was 1,014 tests with no failures, errors or skips; the report reader itself
runs no tests and does not establish cached-report freshness. The invocation
receipt records unchanged HEAD and Android source snapshots
(`ed2c2d5994c037b746b44438cc3b2a52a14af65bcb5e2b4e2c306741e1c54b5d`).

The Web profile at the same HEAD failed in the original-note browser journey: a
maximum-duration callback during delayed AudioContext resume left its shared
startup reservation set, disabling Record after the microphone had stopped.
Its exit-one receipt preserves the unchanged source invocation
(`543e408d2e1ad72228de7d2a801ef2d7a43c1c29d722a8457f6e5250d1572076`).
The failure is not counted as a passing whole Web profile. The callback fix and
final complete retry are recorded with their own source and receipt below.

A provisional unconfigured v47 unsigned release compilation passed in 51s.
The generated release config has empty origins and no optional feature enabled;
package metadata reports version 47 and signature verification correctly fails
for the unsigned artifact. Two introduction-narration source files were being
prepared during this build, so this provisional result is not a frozen source
release qualification. The final source/artifact checks supersede it below.


## October 12 explicit opening narration and recording correction

Web opening speech is accepted at `a8e8b47`: the focused generated browser
journey passed 30 checkpoint groups with no page errors or external requests.
It uses the saved introduction and book language, shares local speech ownership,
and requires an explicit start after a recording conflict. The first new guard
referenced a ticket outside its lexical scope; the corrected guard reads it
from the captured reader context. Its initial CSS-zoom fixture produced a
556px element capture at a 390px viewport and could not establish viewport fit.
The final fixture enlarges snapshotted text once and asserts direct viewport
bounds. Both 390x844 English/Chinese viewport renders were inspected. The stale
completion check invokes the actual saved callback after replacement.

Recording source `cd87ab2` passed the original-note browser journey and WAV/
shared-reservation checks. A duration-complete callback releases only its own
startup or raw capture identity before rendering controls, including while
AudioContext resume remains held. Valid recording preflight stops assistant,
family-audio and chapter/opening speech before requesting the microphone;
invalid, aborted and obsolete starts have no audio side effect. The community
voice render fixture now enlarges transcript-review controls after those nodes
exist, so the entire reviewed state is checked at 150% text.

Phone opening narration is accepted at `6f140f8`. Debug and instrumentation
compilation passed in 18s; the corrected nine-case emulator cohort passed in
26.294s (four opening cases and five affected chapter/contents cases). Both
150% English/Chinese saved-opening sections were inspected. The first run
passed six cases but failed an early logout-cleanup assertion and a wrongly
named contents class; the fixture now waits for UI disposal after logout and
uses the real class. No source behavior was changed for those fixture errors.
Blank introductions mount no speech control. Saved book language, exact text,
explicit pause/resume, navigation/logout cleanup and unchanged reading position
are covered. Shared recording denial/retry is exercised by the affected chapter
cohort; a separate opening-specific recording fixture was not added.

These are synthetic local-adapter results. They do not qualify installed voice
availability, pronunciation, private endpoints, Windows services, signed APKs,
OTA or family acceptance. The final frozen complete client profiles follow.


## October 12 frozen client release qualification

At `263439c`, all 19 Web suites passed (22:25:09–22:28:05 UTC) with unchanged
HEAD and Web source snapshot. Its receipt SHA-256 is
`ad5c197267a72deb005f62857b4d676b0dcb88be2dbadbfecbb7000a602df2a3`.
The community journey passed 34 groups and the story workspace 30; both had
zero page errors/external requests. The corrected English/Chinese introduction
review renders were inspected with the transcript controls actually enlarged.
This completes the retry after the earlier `d3a9a93` Web failure.

The Android JVM/lint/debug source profile passed at the same unchanged HEAD and
Android snapshot in 40s (175 tasks: 21 executed, 154 up to date). Its receipt
SHA-256 is `ca576983b6956210902a6626a781974e195cf417e40ed7846eb20da79a59c7f7`.
The existing XML inventory remains 1,014 tests with zero failures/errors/skips;
this reader does not run tests or establish freshness of cached reports. The
nine actual simulator opening/reader cases are recorded separately above.

The frozen unconfigured v47 release compilation passed in 30s (75 tasks:
11 executed, 64 up to date). The single unsigned APK is 10,058,085 bytes,
SHA-256 `5e38f059d25bed72edc53a46f487e3aa0a31f169cae7589b594a12f7d84202e8`.
Metadata is version 47 / `0.47-family-memoir-composer`; generated origins are
empty and optional capabilities are disabled. Signature verification reports
`DOES NOT VERIFY` / missing manifest, as expected for this unsigned artifact.
It is not a configured family-installable or published release.

Python API behavior has not changed since the complete `a1c6e94` backend
qualification above. Later server edits are Web source; the earlier API receipt
is retained under its own pin rather than represented as a new backend run.
No Windows runtime, database, media, task, model, signing key, OTA feed or physical
device was contacted or changed during this local development round.


## October 12 maintainer and delivery preparation

Instrumentation reader source `55b1a05` passed ten focused synthetic cases and
recognized the retained real nine-case pass. The earlier eight-case log with two
failures returned nonzero and only safe counts; an initial eight-case tooling
run had one incorrect fixture expectation for a missing terminal and was fixed.
The complete tooling cohort passed 121 tests in 4.817s after this accepted
source. It used generated fixtures; no Android, provider or Windows process was
started by the log reader.

The pinned five-asset Web overlay at `263439c` passed nine builder/binding tests
and a temporary extracted-router smoke. All five responses matched their
manifest hashes, with the icon path retained and no listening server. The
[local candidate handoff](LOCAL_CANDIDATE_2026-10-12.md) records archive/manifest
identities and the remaining actual-runtime, rollback and authority gates.
Phone generic release lint also passed in 29s (74 tasks: 13 executed, 61 up to
date). Native APK metadata independently reports `dev.photohouse.connected`,
version 47 and `0.47-family-memoir-composer`. This remains an unsigned,
unconfigured package, with no private delivery claim.


## October 12 final foreground and phase narration correction

Source `a63a35a` gates manual Read/Resume on the current enabled controller and
resumed lifecycle, invalidates detached actions and keeps active Pause/Stop
usable. Its first 28-case simulator run passed 27 and failed the captured Pause
check: Compose updated the reused clickable node to Resume. Source `466ada2`
keys the action node to its immutable snapshot and rendered phase; the corrected
full 28-case cohort passed in 145.835s. The strict log reader accepted its complete
terminal, zero failures/errors/skips. No failure log was removed. One existing
case reads installed-engine voice metadata without speech/provider installation;
the actual narration checks use generated adapters.

At unchanged source `0548d8c`, the complete Android JVM/lint/debug profile passed
in 71s (175 tasks, 20 executed and 155 up to date). Receipt SHA-256:
`2c32629381c83611f2b6e3ca900e87896ca11bbbf7e7d44724c8fcdace34c63f`. The existing XML report inventory has
1,014 tests with no failures/errors/skips; this count does not establish that
cached tasks freshly executed. Web source remains unchanged from its qualified
`263439c` snapshot, so its 19-suite receipt above remains the applicable result.

The rebuilt public v47 unsigned APK is 10,058,501 bytes, SHA-256
`b1a59040c5c439eaa6b0f0752652ea1097214864631903f70b70853edee22d5a`. Native package metadata confirms version 47; the
two origins remain empty and optional flags off. Expected signature refusal
confirms no release signer was used. This package supersedes the earlier public
APK; it does not establish a private build, OTA, Windows or family acceptance.

Final unsigned release compilation and generic release lint passed together in
121s (99 tasks: 17 executed, 82 up to date), at the same phone source snapshot.
No private configuration or signer was supplied.

## October 12 central assistant foundation

The owner approved [the personal assistant design](PERSONAL_ASSISTANT.md) and
an explicit foreground Start with listen/reply/listen, Pause and End. Phone and
Web source use the existing protected v1 transcription, retrieval and result-count
speech. Actual playback completion admits the next capture. Uncertainty, denied
access, provider failures and context/lifecycle changes stop progression. Manual
dictation remains reviewed, and the unsent text draft survives voice mode.

The isolated private thread/preferences module passed **10 tests and 24
subtests** using generated SQLite data. Its checks include exact owner/library
isolation, fixed 30-day exchange expiry, revisions, exact retry conflicts, bounded
opaque card IDs and concurrent snapshot reads. At that foundation stage it had no
HTTP integration or Windows database. Saved references are data; routes must
reauthorize membership and validate current revisions before returning actionable
cards.

The relevant Android live-core/phone run passed **850 core and 17 phone JVM
tests**, with no failures, errors or skips; debug/test builds and phone lint
passed. These counts cover the affected modules, not the complete Android profile.
Subsequent UI and screenshot-capture corrections have their separate checks below.
No microphone, model, family content or physical device was used by these tests.

The final **17-case simulator cohort passed in 142.969s**, with a complete
AndroidJUnitRunner terminal and zero failures, errors or skips. Navigation cases
include the actual library/account labels and available voice entry, at 150%
Chinese/English text. Pending receipt controls and the composer remain fully
visible above the IME. Voice controls preserve the typed draft and require actual
playback before another capture in the separate core driver checks. Final phone
lint and debug/test assembly also passed after the compact-layout correction.

Earlier failure evidence is retained: an outdated optional-introduction
expectation; an unnecessary pause callback when opening Privacy after End;
PixelCopy capture timeouts; and a cramped production-context keyboard layout.
The source fixes keep the UI assertions, compact the header/available actions,
and use native window screenshots. Subsequent emulator attach/system failures
occurred before tests started; the same API 36 AVD, with its data preserved,
completed the final run using the host renderer, Vulkan disabled and 3 GiB guest
RAM. This does not establish real microphone, echo or Samsung acceptance.

The three voice-display cases were then repeated successfully in 64.284s after
aligning the fixture with MainActivity's `adjustResize` and awaiting the current
committed frame before native capture. This avoids a stale/panned capture during
IME transitions. These overlap the 17-case cohort and are not added to its count.

The **20 Web suites were covered across the initial cohort and scoped follow-ups**,
not a newly passing complete invocation. One memory-community fixture took its
request-count baseline before an authorized contribution-reference GET finished;
waiting for that exact response preserves its stale-callback equality assertion.
Upload-history failures revealed a real restore race: controls appeared before
bootstrap's gallery invalidation closed the newly opened panel. The repair keeps
history unavailable until the current bootstrap settles; its delayed-catalogue
regression and all 12 upload checks passed with normal zero exit. Browser-owned
context cleanup is performed by the existing final browser close.

After that Web source correction, voice workspace/session, pending recovery and
capture-scope suites also passed with zero exit. Other tail journeys passed for
conversation navigation, titles, related media, memory groups, reader frames and
story workspace. Successful desktop/390 px/150% assistant renders were inspected.
These use generated data, fake capture/playback and a protected ASGI fixture;
they do not establish a served Web release, local-provider quality or family use.

Delivery preparation found a static-package gap: the older five-asset overlay
changed `UI_DIR` but omitted the current index's `memory-groups.js`. Overlay
format 2 now contains six assets and requires its matching verifier. Eleven
tooling tests and four script-route subtests passed, including the real current
index's deferred scripts, original-icon preservation and rejection of the old
incomplete format before any router binding. The earlier five-asset candidate
remains evidence and must not be deployed as this assistant release.

## October 12 private assistant workspace API

The new default-off private workspace API is wired through application, runtime,
strict staging configuration and the reviewed boundary inventory. It exposes
eight methods for capabilities, owned thread list/create/read/delete and own
preference read/update/reset. Identity and membership are refreshed for each
request; owners do not bypass account ownership. Stale revisions conflict.
Stored reference IDs/bindings/receipt IDs are omitted from history, leaving only
non-actionable type/count placeholders. No endpoint accepts user-supplied
assistant replies or cards. Applied preferences and server-owned turns are
explicitly unavailable.

An independent owner run of workspace HTTP/store, strict v1 assistant, runtime
adapter, staging configuration and closed-application checks passed **100 tests
and 175 subtests**. One existing Starlette/httpx deprecation warning remains.
Coverage includes user/library isolation, revocation, CSRF/origin, no-store,
strict queries/JSON, invalid revisions/enums/UUIDs, three-second body timeout and
framing mismatch, expiry/deletion, maintenance failure, reference redaction,
configuration separation and missing/malformed storage without file creation.
This is synthetic in-process evidence: no provider, listener, Windows database
or physical device was used.


Phone v49 delivery is separately recorded in its release note. The initially
prepared release controllers had mismatched authority paths; this was corrected
before execution and a contract regression added, giving 20 passing local
controller checks. One signing/publication completed, verified natively and by
independent complete trusted HTTPS download. No API restart accompanied the APK.
The separate Web package passed Windows six-route qualification, retaining the
original icon. Its rollout uses the unchanged served API entry/configuration and
format-2 static binder; it does not deploy the private workspace API.

The Web switch is now delivered; see [the exact boundary and recovery
record](WEB_ASSISTANT_DELIVERY_2026-10-12.md). The final native controller and
independent Mac HTTPS checks passed for six byte-identical assets, unchanged
icon and unchanged phone v49/TV v30 feeds. Its actual live backend remains c6;
these default-off private workspace APIs are not deployed by the static rollout.

## October 12 original Android artwork and phone v50

The user-approved original PNG is restored in the shared Android launcher and
TV banner source. Its source bytes and the phone APK's decoded pixels match the
retained original. Phone v50 includes the updater's installed-version label and
distinct current, connection/TLS and safe validation/preparation outcomes. Ten
focused wire/client tests, release assembly/lint and TV/fixture resource checks
passed. See the [artifact and delivery record](../clients/android/docs/PHONE_V50_RELEASE_CANDIDATE_2026-10-12.md).

Owner-authorized signing and phone-only publication completed, with default-TLS
full download checks on Windows and an independent Mac. The rollout's retained
size, wrapper-process and resolver-hash assumptions were corrected before feed
publication. The failed attempts remain private evidence; two added guard
regressions extend the controller cohort from 20 to 22 checks. The wrapper was
qualified by its exact hash, declared backend entry hash, task arguments and
launcher/listener ownership. A bare port or filename match was insufficient.

Signing ran once. Recovery added a corrected controller/authority beside the
verified staged files and reused the same APK. Both old feed pointers were
verified before publication; TV v30 stayed byte-identical. The API task, config,
wrapper and listener were unchanged afterward. Physical phone/TV installation
and family voice behavior remain separate acceptance gates.

## October 13 private assistant turns and clients

The [private turn contract](PRIVATE_ASSISTANT_TURNS_V1.md) now has local server,
Web and phone implementation. Isolated schema-v2 storage reserves a revision
with a bounded lease, commits exchange/result/context atomically, and recovers
the exact request without regeneration or repeated media-open effects. Current
membership and discovery bindings are checked again on recovery. The first
applied preference is textual reply language. Carried context keeps its original
expiry; private history remains separate from durable family text/audio.

Root qualification passed **84 backend tests and 63 subtests**, **20 Web client
tests**, **10 synthetic browser checkpoints**, **874 core Android tests** and
**5 simulator UI tests**. The simulator reused `Medium_Phone_API_36.0`; phone UI
fixtures used 150% font size. Web dialog checks used 1280×900 desktop, a
260×563 CSS viewport at device scale 1.5 for a phone-equivalent render, and a
390px viewport with 150% root font size. These are fixture/layout checks, not
physical device or native browser-zoom acceptance. Root inspected both rendered
clients. The existing Web foreground voice compatibility journey also passed.

The first broad API run used the wrong system Python and lacked Alembic; it was
rerun with the existing repository virtual environment. That run passed 1,249
tests and 738 subtests, with two extracted-package failures identifying omitted
workspace source files. The release allowlist now includes the store, transport,
Web module and explicit offline operator CLI. The extracted-package suite then
passed **6 tests**, including isolated imports and synthetic `a0` serving without
advancing the main database to the package migration head.

The fixed source is `7a938b7e8c78908ef340a99728348818674da298`, with provenance
recorded in `bcc2dc9`. Its 190-file source-only API ZIP has SHA-256
`0e8daa23dc5f62cccf0d98fcf281405e8bc47445ce4b0956606b77129b8926d0`
and is 3,189,380 bytes. The current-source verifier passed: 1,198 files,
1,733 feature-file records, 261 overlays and 11 public transforms. This is a
Mac-qualified candidate; Windows qualification and activation remain separate.

Phone includes private text/history beside its current v1 continuous voice
screen. Unifying continuous voice with private turns is the next integration
slice. No APK signing/publication, Windows store creation/upgrade, API restart,
provider execution or production data change is part of this qualification.

## October 13 private voice and uncertainty recovery

The [private voice contract](PRIVATE_ASSISTANT_VOICE_V1.md) now connects the
phone's central text/voice workspace to an explicitly selected owned thread.
“继续聊天” starts no microphone; “在这个对话中语音聊” starts the approved
foreground driver once. Pause/End cancel only the exact local wait, preserve
its immutable identity and question, and fence late completion. Recovered
responses pause before speech, navigation or further capture. Thread changes,
capability loss and denied access clear or stop the affected private presentation.
The unselected ordinary assistant remains v1.

Web now explains explicit abandonment, preserves the question and draft, and
permits a same-ID creation retry only after an exact GET reports absence.
Neither action resends a submitted turn. Phone has equivalent reviewed controls
and separate creation status/retry actions; terminal failures retain their
question for explicit review and conversation re-entry.

Local evidence: **887 Android core tests** passed; debug APK/test APK assembly
and debug lint passed; the final private-panel simulator cohort passed
**9 tests** on the reused Android 36 AVD. The earlier eight-test UI run also
passed before typed continuation was added. **20 Web controller tests** and
**12 synthetic browser checkpoints** passed, including POSTs lost before server
receipt, exact GET 404s, preserved drafts and deliberate same-ID creation retry.
Root inspected the large-text phone and narrow Web renders. The final scoped
core rerun rechecks private voice after bounding the central history buffer.
These synthetic tests use no household media, model inference or live database.

No new phone version is signed/published, no Windows private store is created or
upgraded, and no Windows service changes. Phone v50 and TV v30 remain the latest
verified published packages. Rich spoken answers and story/album/memoir agent
tools remain follow-up work; current speech reads grounded result counts.


## October 13 private history navigation

The [history navigation contract](PRIVATE_ASSISTANT_HISTORY_V1.md) adds opt-in
first-question labels and explicit older-message paging. Pages keep complete
text under a 240 KiB JSON budget and share one owned thread revision. Foreign
threads remain indistinguishable 404s; membership is rechecked before exposing
labels or text. A concurrent turn requires explicit reload rather than mixing
pages. Labels expire with their source and require no schema migration.

Web/phone retain readable history when discovery is down, disable unavailable
turn/voice actions, and preserve drafts. Paging neither rehydrates old actions
nor changes the selected search context. Oversized combined history is rejected
rather than silently dropping messages. Phone continuation controls now precede
the long message history.

Qualification passed **1,262 backend tests and 741 subtests**, **28 Web controller
tests**, **15 synthetic browser checkpoints**, **897 Android core tests**, phone
debug lint/build, and the final **12 private-panel simulator UI tests**. The first
12-test simulator run found a test that asserted a scrolled-off control was
visible; the check now scrolls to it, and continuation controls moved ahead of
history. The complete simulator rerun passed. After review hardening, the
**78-test scoped backend cohort** and the scoped phone coordinator tests passed
again. Root inspected the narrow Web history render. These counts belong to
local/synthetic qualification, not installed or live service acceptance.

Phone v50/TV v30 remain the verified published packages. Private storage, these
routes, providers, API actions and APK signing/publication were not activated by
this source work. Portable synthetic qualification preparation is a separate
next slice.

## October 13 portable private assistant qualification

`server/scripts/qualify_private_assistant.py --out <new-private-directory>`
creates an a0-compatible synthetic main database, reviewed discovery index and
separate schema-v2 conversation store. It exercises the actual read-only
assistant over two invented photos, then checks exact request recovery,
idempotent engine invocation, labels, older pages, revision conflicts, actor
separation and fixed retention. It starts no listener and invokes no model.

The CLI accepts no existing database, media, provider or service paths. Existing
outputs, aliases, query/fragment markers and unsafe parent paths are refused.
Reports contain aggregate synthetic results. Windows execution uses the existing
bounded Job wrapper: 15 minutes, 2 GiB process memory, four processes and an
8 GiB free-RAM admission floor. Native execution requires its own staging/run
approval. Five portable safety/behavior tests passed; source-package closure is
checked again after pinning the new script in Git.


## October 13 protected private reply speech

The candidate adds default-off saved-reply TTS with current ownership, revision
and source checks, a successful parent turn receipt and at-most-once admission
for each speech request ID. Phone/Web speak fresh clarifications and empty
results, then listen only after actual playback. Unsupported requests speak help
and pause. Recovered replies never speak or navigate automatically.

The full generated API profile passed **1,274 tests and 743 subtests**, followed
by the no-listener demo. The focused speech/configuration/closed-boundary cohort
passed 68 tests. The portable qualification tool's five tests now include fake
saved-reply synthesis, matching parent receipts and duplicate refusal. Those
cohorts overlap. Provider/model inference and real databases were not used.

Web's private controller passed 37 Node tests, plus the 15 history browser
journeys and the complete voice browser flow. Review corrected missing required
speech metadata and an overly restrictive WAV header check; the final client
requires matching successful receipt metadata, the supported bounded PCM
formats and a 30-second limit. Temporary parsed PCM copies are wiped.

The final full phone JVM profile passed 913 live-core tests; the connected
profile passed 17 tests. The 19-case private voice cohort covers cancellation
guards and capability changes during capture, synthesis and actual playback;
phone lint and debug/test assemblies passed. Four generated API 36 simulator
checks passed for Chinese at 150% text: explicit reply reading without capture,
visible loading, a long-reply reading hint, and accessible Pause/End controls.
Phone and Web speaking-state renders were inspected. These checks do not prove
Windows pronunciation, physical-device acceptance, signing or publication.

The API packager now declares its actual required main schema `a0c9d2e4f817`
instead of the historical e7 marker. This metadata correction performs no
migration. The package closure includes the listener-free qualifier and preserves
the separate, explicitly provisioned schema-v2 private store.

## October 13 compact Web conversation controls

The Web assistant keeps the current conversation visible and folds history,
preferences and deletion behind an accessible “管理对话” control. Unconfirmed
creation/turns and destructive confirmations keep those controls expanded.
Opening or closing the panel never starts capture, sends a request or changes
the selected conversation. Counts and dates require a matching current revision;
stale metadata is replaced by a continuation hint.

The 15 generated history journeys and complete voice browser flow passed after
review fixes for expanded width and stale zero-exchange counts. Expanded and
compact 390px renders at 150% text were inspected, along with the speaking
state. This is local browser evidence; the live Web release is unchanged.

## October 13 compact phone conversation controls

The phone panel keeps the selected conversation summary visible and folds
conversation management by default. History, the editable composer, and explicit
text or foreground voice continuation remain reachable; creation, list,
preferences, deletion and recovery controls open through “管理对话”. Missing
details, pending work and unresolved confirmations keep management visible.
Disclosure and confirmation state resets on account, library, generation,
thread or request changes, while drafts remain scoped and preserved.

The 19-case generated panel simulator cohort passed with Chinese 150% text. After
the composer helper changed from a routine byte count to brief localized guidance
and a clear over-limit error, the focused composer journey passed once more with
the byte limit and disabled-send behavior checked. These source UI changes are
not part of the pinned v51 candidate at `3a56870`; no new signed APK was created.
The emulator screenshots are synthetic UI evidence, not phone installation or
family acceptance.

The next phone candidate is version 51 (`0.51-private-conversation-voice`). Its
version declaration is preparation only: an unsigned package, original-icon
check, signing authority and OTA publication still have separate evidence.

The fixed v51 candidate subsequently passed offline release assembly and release
lint, plus shared phone/TV resource processing. Package identity and unsigned
status were checked. AAPT rewrites PNG encoding; decoded RGBA pixels in the APK
match the original 1254×1254 icon exactly. This does not prove launcher/device
acceptance, signing or OTA delivery.

Qualification review also moved application/database imports into the bounded
Windows child. Six portable tests and two subtests passed, including a fresh
process import check that the supervisor does not load those dependencies.
See [native qualification and identity](PRIVATE_ASSISTANT_NATIVE_QUALIFICATION.md).

## October 13 saved-memory discovery foundation

The protected discovery suite passed 23 tests and 22 subtests for literal,
kind-filtered saved-text searches, current library access, bounded immutable
references, Unicode case folding, source withdrawal, child/source revision
changes, duplicate pages, scan budgets and concurrent database commits. The
revision-bound `read_reference` service rechecks the exact current source before
returning its typed reader projection. The command parser suite passed 13 tests.
The initial combined discovery/parser/tool cohort passed 44 tests and 40
subtests; after the joined-emoji and neutral-reply fix, the focused nine-test
projection/tool cohort passed. These cohorts overlap and are not additive.

The backend now has a default-off negotiated endpoint and separate optional
capability probe. Base capabilities remain unchanged; only a fresh request that
explicitly accepts `saved_memory_cards_v1` can receive cards. Same-ID stored
turns return their existing status before negotiation, without recomputing cards.
Fresh results use current-source checks and typed opaque references; history
keeps the 30-day legacy summary and exposes references only as non-actionable
type/count placeholders. Nine focused HTTP checks passed after correcting the
synthetic seed writer and deriving its discovery index from the matching fixture.
They cover negotiation, immutable replay, access/expiry, media-context clearing,
source withdrawal and source drift after completion. The speech guard refuses
story/memoir reference turns before synthesis. The portable runtime/staging
configuration cohort passed 43 tests and 132 subtests; the closed-boundary/store
cohort passed 39 tests and 24 subtests.

Web now renders immutable plain-text story/memoir cards after a separate optional
probe. Forty-five controller checks and six generated browser checkpoints passed,
including late feature-loss fencing, missing-probe fallback, hostile source text,
GET-only recovery and 390-pixel/150% layout. The integration owner inspected the
rendered fixture. No client reader opening or phone cards are integrated yet.
The earlier fifteen-check private-workspace browser regression also passed.
These cohorts overlap and do not imply a complete new profile. This source is outside pinned v51
candidate `3a56870` and native qualification candidate `db95b6`; no flag is
activated and no live API or APK was updated. See [the saved-memory card
contract](ASSISTANT_SAVED_MEMORY_CARDS_V1.md).

The full API profile at `1fefbb9` passed 1,331 tests and 787 independently
reported subtests, plus the generated no-listener demo. Its private invocation
receipt records equal start/end source hashes and commit identity. This complete
profile precedes the saved-memory speech follow-up below.

## October 13 source-validated saved-memory speech

A separate optional saved-memory speech probe preserves the existing card/base
capability responses. Web can explicitly play a fresh generic reply, or use it
inside the already-started foreground voice session. The server loads the
matching completed exchange, validates each current story/memoir source before
and after TTS, and guards the whole reference set against database commit drift.
The current memory-group opt-in is propagated through the request-local readers.
Mixed references, changed exchange revisions, source edits/withdrawal and feature
or speech dependency loss withhold audio. Replay remains text-only and inert.

The final focused speech/turn/store/closed-boundary/qualifier cohort passed
76 tests and 39 subtests.
The controller suite passed 49 tests, including aborting active memory audio and
withholding late bytes after probe loss. The generated browser initially passed
seven checkpoints for explicit correlated playback, recovery without synthesis
and missing-speech-probe card fallback. Its final eight-checkpoint rerun also
holds audio active, disables the speech probe, then verifies pause, URL revocation,
hidden playback controls, retained cards and no new capture or turn. The first
run exposed a stale visible playback control, corrected before the passing
rerun. These counts overlap earlier cohorts.

The portable qualifier now exercises eight generated scenarios, including story
and memoir retrieval with strict legacy recovery and source edits during fake
TTS. Its six portable harness tests passed; Windows bounds and lazy supervisor
imports are unchanged. Native Windows execution is not claimed, and the existing
`db95b6` candidate retains its original six-case package and pending scope.
No Windows API/store, model, APK or task was changed by this source follow-up.

The final full API invocation at `7daf740` passed 1,337 tests and 793 subtests,
plus the generated no-listener demo, with equal source hashes at both ends.
The complete Web invocation at that source passed the new eight-checkpoint
memory journey but failed the older receipt-only recovery fixture: that fixture
had enabled the separate private store, causing the app to select private turns
instead of the legacy POST being intercepted. The fixture now explicitly omits
private-store admission and asserts that private turns are unavailable. Product
route selection is preserved; the complete Web rerun is recorded separately.

The combined voice fixture now explicitly selects `--private-workspace`; the
legacy recovery, transcript, capture and trail fixtures retain their ordinary
route. At `9249c80`, the Web rerun passed both corrected journeys and all suites
before the older title-browser script, then stopped because its default
`playwright` package was absent. The remaining seven suites passed with the
already-installed `PLAYWRIGHT_MODULE=playwright-core`. All 23 configured suites
therefore have passing cohort evidence, but no new single complete Web invocation
is claimed. The next complete command should set that module explicitly.


## October 13 current-card voice narration

The development source after `7f8d92b` supports contextual “介绍这些结果” /
“describe these results” and recorded-date follow-ups, plus bounded ordinary
search and speech overviews. Only the first three current ordered card kinds
and validated `taken_at` dates are narrated; filename/receipt hints, captions
and scene/story claims are not inferred. The ordinary speech endpoint repeats
source/context validation after synthesis before returning any audio.

Local checks use generated data and optional provider fakes:

```sh
PYTHONPATH=server/scripts:server/backend .venv/bin/python -m unittest discover -s server/tests/security -p 'test_assistant_*.py' -q
PH_BROWSER_PYTHON="$PWD/.venv/bin/python" PLAYWRIGHT_MODULE=playwright-core node server/tests/security/test_assistant_voice_session_browser.cjs
python3 tools/verify_current_source.py
```

The assistant cohort collected 156 tests: 155 passed and the external WSL
ASR adapter test was explicitly skipped because its implementation is outside
the curated CPU source export. A present adapter with broken dependencies
still fails import; the skip is not ASR service acceptance. Nine focused
narration cases are included in the cohort. The Web voice regression passes,
with desktop and 390px/150% generated narration-layout renders inspected.
Android connected debug Kotlin compilation and empty-origin QA/test APK
assembly passed with JDK 17 and the existing SDK. These checks do not qualify
Windows native TTS duration/listening or a physical phone.

The emulator QA package also passed one bilingual, 150% text ASR no-input
fixture test in 3.129 seconds; both localized renders were inspected. That
fixture checks transcript/error presentation, not acoustic ASR, TTS or the
new narration's Android layout. No physical phone was attached for this check.

The already prepared phone v52 and Windows candidate remain pinned to
`7f8d92b`; these new source changes are outside that immutable candidate.
The dated native read-only observation still reported phone OTA v51 and
TV v30, and no service switch, release signing or publication happened during
this development slice. Consult [voice reliability](ASSISTANT_VOICE_RELIABILITY.md)
for its scope and [the roadmap](ROADMAP.md) for subsequent delivery gates.

## October 13 assistant saved-memory reader source

The next source connects fresh saved-memory cards to protected story/memoir
readers on Web and phone. Separate card, reader and speech probes preserve
older-server behavior. Scope, completed-turn revision, typed references and
current source digests are revalidated; opening stops foreground voice first.

Checks for this slice:

- Assistant security suite: 166 tests, one external-adapter skip. The reader HTTP
  suite contributes nine tests; the reader/saved-card/closed-boundary cohort
  passed 51 overlapping checks. Fourteen intent parser cases include the current
  Chinese reader names.
- Six portable qualification-controller tests pass. Its existing eleven generated
  scenarios now also exercise full story/memoir handoff, hidden foreign access,
  superseded parent revisions and stale-source refusal. No network/model/family
  database is used.
- Web controller: 52 checks; generated browser journey: eleven checkpoints.
  Includes separate-probe fallback, story/memoir opening, source-policy shelf
  reopening and late old-scope responses during a replacement turn.
- Android focused core: 72 checks. Debug and instrumentation Kotlin compilation
  passed; two central-card large-text QA emulator fixtures passed in Chinese and
  English on the existing API 36 emulator. Fixture captures were inspected.
- Web story reader, memoir reader and the 390px/150% memoir card were inspected.
  Long memoir table-of-contents titles now wrap in a narrow layout.

The initial Android report-writing attempt was unsuccessful; a later serial
compile found and fixed a Character-category comparison error. Focused checks
then passed. The Gradle instrumentation task removed its target app and cache;
QA debug/test APKs were reinstalled only on the designated emulator for direct
instrumentation and capture. No physical phone, provider or Windows service was
changed. These changes are outside the already-published v54 artifact.


## October 13 saved-memory followup integration

The [followup contract](ASSISTANT_SAVED_MEMORY_FOLLOWUPS.md) binds typed and
foreground voice requests to the latest fresh saved-memory display. Generic
replies and current source excerpts/outlines retain the existing card grammar.
Clients negotiate separately, preserve older closed-route behavior with a base
capability recheck, and insert suggestions as drafts after ending voice.

Current checks:

- Assistant security discovery: 180 tests, one external-adapter skip. Exact
  parser, ownership, parent/current-source drift, hidden access, malformed
  storage, generic-only recovery and locale selection are covered.
- Six portable qualification tests passed. The eleven existing synthetic
  scenario groups now include a separate search → overview → outline → reader
  → inert recovery chain. Only generated databases/media are used.
- Web controller: 59 checks. Generated browser journey: thirteen checkpoints,
  including source-bound ordinal followups, draft-only controls, stale scope,
  literal XSS fixtures, recovery and older-route fallback. Chinese desktop and
  390px/150% memoir card renders were inspected.
- Android: 57 focused JVM checks (24 store, 13 HTTPS and 20 voice), plus fifteen
  earlier wire checks; these cohorts overlap earlier wider checks and are not
  summed. Post-review Kotlin compilation passed. Four generated emulator cases
  and Chinese/English 150% private-panel renders passed and were inspected.
  The later fixed `043c938` QA/test builds and four-case direct instrumentation
  rerun also passed after English ordinal-label polish and the v56 identity.
  Both final enlarged-text captures were inspected.
- The package allowlist includes the new followup module. API profile selection
  includes its parser test and the existing reader suite; immutable packaged
  import/qualification checks must run against the new committed source.

Phone v56 is reserved as `0.56-memory-followups`, without signing or publication.
The already published v55 release remains pinned to `c65528a`; source, runtime
and physical device acceptance stay separate. See the
[v55 delivery record](../clients/android/docs/PHONE_V55_RELEASE_2026-10-13.md).


The [fixed v56 candidate](../clients/android/docs/PHONE_V56_RELEASE_CANDIDATE_2026-10-13.md)
passed release build/lint, native Android package/unsigned-state inspection,
seventeen embedded configuration-field comparisons and original mark pixel
verification. Six immutable package tests passed; the extracted 195-file archive
independently passed all eleven synthetic scenario groups on macOS. Thirteen
profile dispatcher tests and current source-ledger verification also passed.
Native Windows qualification, live switch, signing/publication and family
acceptance remain separate gates. The pinned candidate is not the served v55.


## October 14 native v56 qualification and later opening-speech source

The fixed `043c938` backend package passed native Windows qualification: 195
files and eleven generated scenario groups, with five-minute/2 GiB/eight-process
bounds and an 8 GiB free-RAM admission floor. Eight related tasks and preserved
ASR/TTS/OCR were verified before qualification, with 48.8 GiB free RAM. Original
data, service/task state and model/provider activation were untouched. SSH
handshake resets were reconciled before command execution. Native read-only
parsing of eight API controller scripts passed using an explicitly framed input
transport after an EOF-based transport timeout; no maintenance was replayed.
Thirteen API controller checks and twenty-two phone delivery-controller checks
passed. Live switch/signing/publication are separately authorized gates.

The later [opening-speech implementation](ASSISTANT_SAVED_MEMORY_READING.md)
includes backend, Web and phone source, outside v56. The closed-app route inventory now also records
the existing followup-capability route, which the older pinned fixture omitted,
plus the two new opening-speech routes. The fixed v56 candidate's narrow
assistant/package/native qualification and the later source's complete route
inventory checks are distinct evidence; no full hosted CI result is claimed.


### Explicit saved-memory opening playback acceptance

The server suite has **16 opening-specific cases**. Fixture TestCase imports use
module aliases so discovery does not repeat unrelated tests. The membership-loss
case commits a valid revoked membership and checks the exact authorization error;
it does not mistake a fixture/schema failure for access enforcement. Exact saved
Unicode spacing is preserved, including nonbreaking and Unicode line separators,
within both 240-code-point and 600-byte limits. Empty sources remain unavailable.

The assistant discovery cohort ran **196 tests: 195 passed and one skipped**; the affected
closed-application/import cohort passed **27**, and disposable qualifier tests
passed **six**. The eleven qualification scenario groups now include exact saved
story/memoir opening speech and assert that source wording is absent from receipt
input/transcript fields. These overlapping scopes are not added together.

Web transport checks passed **63 tests**; generated browser checks passed **18
checkpoints**, including actual-play readiness, Stop, replacement-parent and old
player ownership. Manual capture and delayed microphone permission are cancelled
before reading; Stop during delayed audio-context cleanup invalidates the request,
and late cleanup cannot stop a replacement player. Explicit capture cancels the
opening player so synthesized narration cannot enter the microphone. Desktop Chinese and 150% phone-width playback renders were
inspected. Android focused core checks passed **70 tests** (26 voice/store, 24 workspace,
15 HTTPS API and five connected coordinator cases); connected UI logic passed
**17**. Debug QA build/lint and the final v57 emulator fixture passed **four**
cases. These are generated fixtures, with no account or family data. The current-conversation summary was
stacked so the English management action cannot squeeze the metadata into a
narrow column at 150% text. Original icon and fixed v56 artifacts are unchanged.

Phone v57 is reserved as `0.57-memory-opening`. No physical phone, live server,
release signing or OTA acceptance is implied by these synthetic/emulator checks.

The affected shared capture regression passed **seven generated browser checks**,
including real mouse hold/release, delayed permission, explicit cancellation,
old-account startup, stale processor/resume, abort and visibility changes. The
WAV encoder and shared reservation check also passed. No external origin was
contacted. The package-builder cohort passed six cases, and seven source-verifier
checks passed. Implementation source-ledger verification covers 1,235 files.


The [fixed phone v57 candidate](../clients/android/docs/PHONE_V57_RELEASE_CANDIDATE_2026-10-14.md)
is prepared from `4b69844`. The 195-file source-only ZIP was hash-verified after
extraction and passed all eleven generated qualification groups locally. The
unsigned phone release build/lint and 17-field private-profile verification pass;
the original packaged artwork pixels match. Native Windows qualification,
original-certificate signing, publication and family/device acceptance are open.


## October 14 API/Web and phone v57 delivery

User publication authority covered staging/native qualification, stopped-writer
backup, the API switch and guarded recovery/worker restoration, followed by
original-certificate signing, phone-only OTA publication and full verification.
The [delivery record](../clients/android/docs/PHONE_V57_RELEASE_2026-10-14.md)
contains the fixed package/APK identities and family test steps.

The first attempt exposed an inherited 194-file launcher guard against the
195-file package and a rollback speech-state assumption. The previous API passed
readback; five unchanged workers were restored before correction. A fresh
candidate executes full listener-free launcher validation before service control
and binds rollback speech to the unchanged enabled configuration. Fifteen local
API controller checks and eight native parser checks passed. Accepted source:
4b69844; schema/configuration are unchanged. Two fresh stopped-writer backup
records are preserved; no production database restore was used.

Twenty-three phone delivery checks passed. Signed APK v57 was verified natively
and through independent complete Mac HTTPS readback; TV v30's feed response is
unchanged. Final observation: eight required tasks running/enabled, ASR/TTS/OCR
identities preserved, about 47.6 GiB free RAM. Physical phone installation and
family listening acceptance remain next.


## October 15 overnight product-readiness source

The integrated source round includes explicit segmented reading, process-local
voice timing, gallery preview recovery and foreground conversation recovery.
The frozen `d57a41c` API profile passed **1,483 tests / 913 subchecks** plus the
no-listener demo; its Android profile passed with unchanged-input receipts.
Subsequent Web runs found two fixture synchronization gaps and a real reload
recovery race. Capture fixtures now wait for the actual audio processor; reader
fixtures bind the exact source response. Recovery UI now binds the pointer read
at restore start and preserves later user focus/scroll intent. Historical failed
profile runs remain failures; focused reruns do not replace the final full run.

Compact saved-memory controls passed phone bilingual enlarged render checks,
26 private-panel, 14 opening-reader and six conversation-navigation UI cases.
After accessible names were changed to begin with each visible short label,
three specifically affected instrumentation methods passed again. These scopes
overlap. Follow-up callbacks retain the complete existing query; a label is not
an automatic request. TV current-page retry passed three emulator cases, debug
lint/compilation and enlarged Chinese/English render review. No physical-device
or TV installation is inferred.

The generated oral-history cohort passed **49 tests / 24 subchecks**: intake,
withdrawal and the new four-group/ten-case disposable qualifier. The quality
planner/canary contracts passed 11 and 21 focused cases without inference. The
portable API archive inspector passed 26 generated checks, including canonical
archive identity, pinned local Git/builder identity, bounded execution and
content-free refusal reports. The API package allowlist now includes the oral
qualifier: **201 source files**, with twelve existing assistant qualification
groups and a separate four-group experimental recording rehearsal.

Current exact committed-package qualification, final complete profiles and
unsigned v59 release evidence must be recorded against the final immutable
revision. They are separate from Windows staging/native execution, live cutover,
signing, OTA and family listening acceptance. No deployment or provider activation
was authorized or performed as a consequence of the checks above.


### Follow-up: voice restoration ownership and quality worksheets

The `bd21d27` full API profile passed **1,495 tests / 915 subchecks** plus the
generated demo; Android passed its full profile. Both receipts bind unchanged
profile inputs. The complete Web run failed at the final English utterance.
A deterministic private reproduction held `/auth/session` after a language
change and proved Start could become enabled before restoration settled; later
capability loading aborted the just-started ASR. The repair adds an owned restore
gate to voice Start/Resume, manual capture and voice-origin sends. It keeps
ordinary typed submission/recovery behavior, stops prior voice and displays a
localized checking/microphone-off state. Focused Edge voice and turn-trail
journeys pass; a later full Web rerun remains required.

The standard-library tooling run found two stale worksheet inventory assertions
after the story-quality corpus grew. The worksheet test now checks all five
narrative case IDs separately from the three title case IDs. **158 tool tests**
pass with the same private, unreviewed and content-free-report boundaries. These
are not model quality or hosted CI results.


Phone composer continuity now uses a composition-local holder in ConnectedApp,
passed optionally to the central assistant screen. Its key includes current
account/library/generation/protection state, assistant host and the active private
thread ID; browsing another history entry does not itself activate that thread.
Three actual-route emulator cases passed, including thread activation versus
revision-only refresh and zero send/transcribe/capture side effects. Debug lint
and instrumentation compilation passed; no geometry changed. The default local
screen holder keeps standalone fixtures and other callers compatible.


The frozen `816b9b5` API and Android profiles passed with unchanged-input
receipts; API again reports **1,495 tests / 915 subchecks** plus the generated
demo. The next full Web run stopped in its history fixture: the HTTP response
arrived before selected-thread rendering settled. A private diagnostic observed
the selector still disabled, the target thread not selected and no history
rows. The fixture now waits for that exact target, management scope, enabled
selector and twenty rendered rows before the original explicit-open assertion.
All fifteen focused history/workspace journeys pass with their original paging,
privacy and recovery checks. No product source changed for this synchronization
repair; the next complete Web run remains a separate gate.

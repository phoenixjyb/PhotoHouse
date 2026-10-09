# Development and public release qualification

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

## Inspect the local environment

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

Run `.venv/bin/python tools/doctor.py` or add `--json` before selecting a test
profile. [Environment report](DEVELOPMENT_ENVIRONMENT.md) explains the read-only
checks and available/missing/unverified states. It inspects pinned package
versions, JDK/SDK/wrapper and optional cached browser prerequisites without
installing, building or contacting a service. A detected prerequisite is not a
test pass. Thirteen doctor tests passed, including timeout, version mismatch,
truncated probes and module paths with spaces.

## CPU quick start

From the repository root:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r config/requirements-dev.lock
.venv/bin/python tools/check.py api
```

The latest supported CPU run passed **699 tests and 400 independently reported subtests**
on October 9, 2026, plus the generated-data demo. It used the existing macOS
arm64 Python 3.12.12 / pytest 9.0.3 CPU environment; this run did not perform a
fresh dependency installation. The private model manifest contributes 19 tests
and 39 subtests for declared identities, contracts, rollback and private-file
handling. The 67 standalone tooling tests include four deployment doctor checks;
these counts are separate from the API profile. No model runtime or quality is
qualified by these checks. The earlier 680/361 profile predates the manifest.
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

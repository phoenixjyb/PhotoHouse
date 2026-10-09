# Development plan

October 6 night: source search/paging, separate chat bubbles, associated input
errors and [localized dictation recovery](ANDROID_DICTATION_RECOVERY_2026-10-06.md)
have focused synthetic evidence. The [saved-story chapter directory](ANDROID_STORY_CHAPTER_DIRECTORY_2026-10-06.md)
supports direct chapter selection with complete long titles in Chinese/English at
150% text size. Selection starts at the top of the chosen chapter. Core dictation
tests, seven combined emulator flows and debug lint passed; two directory flows
passed again after the scroll correction. These changes are next-release source.
The frozen v42 candidate remains unchanged and is still awaiting its complete
signing/staging/OTA authority. Physical phone, TV and family checks remain distinct.

The [explicit memoir context choice](ANDROID_MEMOIR_EDITORIAL_CONTEXT_CHOICE_2026-10-06.md)
now checks saved opening citations and adjacent transitions before selecting them
for chat. 85 core checks, a final 13-test repository run, two Chinese/English 150%
emulator journeys and debug lint passed. Failed checks retain the draft and require
an explicit story-only choice; retries freeze the selection and mutation.
Native provider quality, deployment and physical use remain separate gates.

The [whole-memoir plan and review](ANDROID_WHOLE_MEMOIR_DRAFT_UI_2026-10-06.md)
is implemented as a separate collapsed entry. The explicit plan precedes
queueing; the read-only proposal preserves child/chapter identities and never
writes into an individual story. Ten coordinator, 51 community integration and
six editorial integration checks passed; three emulator flows and lint passed,
with a final two-flow rendering rerun. Raw model quality and delivery remain open.
[Reviewed memoir instruction voice input](ANDROID_MEMOIR_INSTRUCTION_DICTATION_UI_2026-10-06.md)
now has 66 core checks, two bilingual 150% emulator journeys and debug lint.
Insertion preserves existing instructions and stays separate from chat and family
originals; generation needs a later explicit request. Next: narrative form choices,
bounded outline/transition review and native provider quality qualification.

October 5 local increment: [story and memoir conversation previews](ANDROID_CONVERSATION_PREVIEWS_2026-10-05.md)
distinguish threads by their first retained message and fence stale list requests.
Focused core checks and two synthetic emulator journeys passed. This source
increment is not in the frozen unsigned v41 APK or the live OTA feed.

The [optional memoir forms](ANDROID_MEMOIR_NARRATIVE_FORMS_2026-10-06.md) add
faithful chronicle, reflective essay and connected memoir directions. The default
request remains exact; combined UTF-8 limits preserve drafts and frozen retries.
71 focused JVM checks, two final unmasked Chinese/English 150% emulator journeys
and debug lint passed. These options are not model-quality or OTA acceptance.

Latest local phone slice: [memoir companion and checks](ANDROID_MEMOIR_COMPANION_2026-10-02.md).
The feature is not yet published and remains gated off by default.

Both phone readers now have [chapter source references](ANDROID_CHAPTER_SOURCES_2026-10-02.md),
with synthetic emulator and release-compilation evidence. Matching backend,
signed artifact and family acceptance remain delivery gates.

Latest local TV slice: [library focus and readable viewport](ANDROID_TV_BROWSE_FOCUS_2026-10-02.md).
Normal and 2.0 font-scale emulator navigation passed; signed publication and
projector acceptance remain separate gates.

For current phone/TV access, artifact and OTA status, use
[Phone and TV access](PHONE_TV_ACCESS_2026-09-29.md). The backend repository's
`docs/PRODUCT_ROADMAP_2026-09-29.md` is the current cross-surface feature
register. The plan below preserves the September 9 foundation decisions.

**Historical foundation document.** Platform/backend status statements below describe
that handoff's baseline. For current Android implementation and remaining live gates,
use [Android MVP status](../android/MVP_STATUS.md) and
[pilot acceptance](../android/PILOT_ACCEPTANCE.md). Do not restart the Android
foundation capsule or treat an earlier blocker as current without those records.

Updated 2026-09-09: native fixture work is ready from the frozen local tag
`refs/tags/photohouse-mobile-fixture-v1`. The backend foundation is locally tested
at `1e394f789ff1f7cef6d9930bb541186684f5a9a0`; mobile apps are not built yet.
[Session capsules](SESSION_CAPSULES.md) define executable scopes and acceptance.

## 1. Repository and implementation choices

Use one independent mobile repository, not a folder inside the inference stack.
Keep both mobile platforms together so shared contracts, fixtures, and parity
changes are reviewable in the same pull request. Keep backend application logic
in vlmPhotoHouse. Do not fork the photo database or create a second mobile-only
authorization backend beside the existing API.

Use **Kotlin/Jetpack Compose for Android** and **SwiftUI for iOS**. Share versioned
API schemas, synthetic fixtures, error behavior, and behavioral scenarios. Do not
introduce Kotlin Multiplatform, Flutter, React Native, or a WebView wrapper in
the first slice. This follows the native ReCoMo iOS contract pattern and keeps
the two build loops independent. Reconsider KMP only after stable duplicated
domain logic demonstrably justifies the Kotlin/Native build coupling.

Layout; contracts and the shared verifier now exist, platform source is next:

```text
android/                    Android wrapper, app, small core modules
ios/                        SwiftUI app, local Swift package, XcodeGen project
contracts/v1/               reviewed backend OpenAPI snapshot and synthetic fixtures
docs/                       architecture, parity, evidence, session capsules
scripts/                    independent verify-android / verify-ios / contract checks
.github/workflows/           independent Android, iOS, and contract checks
```

The backend owns the authoritative API schema. The mobile repository consumes a
versioned snapshot with backend SHA, checksum, and compatibility version. The
coordinator owns snapshot updates; clients must not invent incompatible endpoints.
Only the source-pinned subset in contracts/v1 is frozen for fixture clients.
The running legacy deployment has not been changed or validated.

## 2. Family product, not an admin console

First working prototype: invitation registration, phone/password sign-in, own
membership/library selection, photo grid, detail/captions, bilingual interface,
logout and privacy/error states. Photos and account/library controls are sufficient
navigation. Use synthetic media and an injected fixture repository with networking
disabled. A warm neutral palette, generous imagery, clear dates and accessible
controls should make it feel like a family album.

The fuller family release can add albums, text search and authorized video after
the corresponding backend and native integration contracts pass. Those features
are not requirements for the first fixture shells. People filters require reviewed
assignment quality/permissions. Never label an unconfirmed match as a relative.
Keep worker queues, disk paths, models and GPU operations out of family navigation.

UI languages: Simplified Chinese by default on phone and TV, with an English
switch and a system-language option in connected phone settings. Caption
content is separate; a caption-language selector is deferred until structured
translation metadata exists in the backend contract. Switching UI language does
not rewrite captions
or filter away media with another language. Preserve original text and label AI
output; do not promise that all older captions are already refreshed.

Deferred: automatic phone backup/upload, permanent offline albums, public sharing,
destructive library management, photo printing/export workflows, advanced themed
album generation, always-listening voice, and speakers. Theme browsing and existing
album drafts can follow the authenticated read-only release; generation/export
must later use permission-scoped jobs and confirmations.

## 3. Access model and network

Recommended pilot: invitation/owner approval and HTTPS over home/private VPN
connectivity. Network reachability is not identity. A VPN address alone must never
grant photo access, and GitHub Pages is not a backend or private-media host.
Choose a stable trusted HTTPS origin and certificate lifecycle before real login.
No global cleartext exception or accept-any-certificate code in either app.

Chosen identity flow: the owner manually sends a phone-bound invitation. A new
user submits that code, phone and password; valid redemption creates an account
and viewer membership only in the invited library. Phone is an unverified login
label; stable account ID is internal/opaque. Returning users sign in by phone and
password. No OIDC/SMS/WeChat provider, open signup or first-signup ownership.

The backend returns an opaque revocable 24-hour native bearer session, without a
refresh endpoint. Initial fixture apps keep it in memory and restart signed out.
Web cookies/CSRF remain a separate transport to the same authorization services.
Explicit offline operator provisioning/recovery exists locally; live owner setup,
restoration/reopening, stable HTTPS and host deployment remain independent gates.

Public internet access is deferred until authorization, recovery, TLS, rate limits,
monitoring and deployment rehearsal pass. Network/VPN access alone grants nothing.
No mobile task changes today's Windows listener or private tunnel.

## 4. Implementation sequence and gates

| Phase | Work | Exit evidence |
| --- | --- | --- |
| P0 | Freeze native consumer snapshot and synthetic cases | Done in this handoff: pinned schema/fixtures/shared offline check; no production network |
| P1 | Android and iOS fixture shells; backend security foundation | Backend: 198 local security tests. Apps: implement capsules B/C and record independent build/UI evidence |
| P2 | Explicit host/TLS staging and native authenticated transport | Synthetic two-account/cross-library/revocation/Range integration; no TLS bypass |
| P3 | Small authorized real-library read-only pilot | Exact signed/installed builds, privacy/logout/video/performance and family acceptance |
| P4 | Scoped search/albums, then push-to-talk voice | Separate authorized contracts, EN/ZH scenarios, ownership/cancel/privacy and provider budgets |
| P5 | Upload/offline/export and paired room devices | Separate product/privacy/deployment review for each capability |

Android leads the first build loop; iOS starts immediately from the same frozen
tag, without waiting for Android completion. Neither depends on additional offline
recovery work to build its fixture shell. Voice remains deferred until reviewed
search/voice services exist; no standalone model session is implied.

## 5. Development infrastructure

Borrow OpenGroove's separate Linux Android/macOS iOS verification jobs and
ReCoMo's contract/parity and exact-artifact handoffs. Do not import Robot code,
private GitLab/JFrog settings, music providers, signing IDs, or outdated pins.

Android: small app with Compose screens/ViewModels, immutable observable state,
repositories and native session/media adapters. Pin a compatible JDK/Gradle/AGP/
Kotlin set at bootstrap after checking current tooling. Verify wrapper checksum;
unit tests, lint, debug APK, and selected emulator tests. Initial minimum Android
API 26 is a proposal to confirm against the family's devices, not a release promise.

iOS: SwiftUI, Foundation transport, a local Swift package for contracts/session
logic, pinned XcodeGen plus committed generated project and generation drift
check. Propose iOS 17 / Swift 6, subject to device inventory. Record actual Xcode
and simulator versions; package tests and unsigned simulator build/UI tests.
Do not make iOS depend on Android Gradle in this first version.

Public PR CI: hosted runners, read-only permissions, pinned action revisions,
bounded artifact retention, synthetic images/accounts only, no home-network
access or signing secrets. Separate platform jobs must not block one another's
local builds. Root contract changes require both clients' fixture tests. A green
mock test does not prove server authorization or installed-device behavior.

Production signing is a later protected/manual lane with dedicated application
identities and increasing build numbers. Never commit keys or export real-photo
screenshots in public CI. TestFlight/Play distribution, store privacy disclosures,
device registration, and installation each need their own authorization/evidence.

Before store distribution, separately review account deletion, session/data removal,
shared-library ownership transfer and the current platform requirements. No deletion
endpoint is included in the fixture contract. Consult [Apple's account-deletion
guidance](https://developer.apple.com/support/offering-account-deletion-in-your-app/)
and [Google Play's account-deletion guidance](https://support.google.com/googleplay/android-developer/answer/13327111)
at release time; this planning pack is not store approval.

## 6. Decisions and remaining gates

The invitation plus phone/password policy and native Kotlin/Compose + SwiftUI
approach are settled for this scope. The following remain open for live delivery:

- Stable trusted HTTPS origin and private-network pilot versus internet requirement.
- Reviewed operator recovery/reopening, deployment/migration and backup rehearsal.
- Family device inventory, minimum OS support and production app identities/signing.
- Persistent sign-in lifecycle, account deletion/owner transfer, later media retention.
- Scoped search/albums and eventual voice/provider contracts.

None blocks the current fixture app assignments. No production service, store
acceptance or installed-device behavior is claimed by source or fixture tests.

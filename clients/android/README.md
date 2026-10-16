# Android clients

This directory contains the Android phone and TV apps, their shared Kotlin
modules, API contract fixtures, and Android-specific design and release notes.
The phone release baseline is **v67 / `0.67-voice-reading`**. Its signed
artifact, native HTTPS readback and CI evidence are recorded in the
[v67 release record](docs/PHONE_V67_RELEASE_2026-10-16.md). The release adds
spoken Pause/End and explicitly opted-in saved-section voice continuation;
reviewed chapter-proposal adoption remains available and generation stays off.
Physical phone installation and real ASR/TTS/family
acceptance remain open. TV OTA remains v30; v31 source is unpublished. See the dated
[project status](../../docs/PROJECT_STATUS.md) for the current delivery state.
PR #54's Android scene-search controls are included, with server capability
negotiation. This release does not activate a scene provider. The paired
API/Web source passed Windows synthetic qualification and still needs its live
cutover approval.

## Projects

The Gradle project is in [`android/`](android/), with these main components:

- `:connected` is the PhotoHouse phone app. Its Compose UI uses `:live-core`
  for account/library, story, memoir and assistant API/domain behavior, and
  `:home-core` for home-feed and catalog behavior.
- `:tv` is the TV app. It uses `:home-core` for home/catalog reads and
  `:ota-android` for the Android update client. The desktop-dependent TV flow
  still needs its physical projector check.
- `:protocol` holds shared wire models; `:playback-core` holds playback
  progress logic used by the phone and home modules; `:home-core` contains the
  HTTPS home/catalog clients, stores, discovery and video-reading logic.
- `:ota-android` contains the Android OTA client and its provider configuration.
- `:core` and `:app` are the standalone development fixture app, not the
  household phone app. `:story-fixture-core` and the optional fixture UI provide
  generated story data for development journeys.

## Local development

Use JDK 17 and Android SDK platform 34 with build tools 34.0.0. From the
PhotoHouse repository root, run the supported Android profile:

```sh
.venv/bin/python tools/check.py android
```

This runs JVM tests for the shared modules and both apps, phone and TV debug
lint, and unconfigured debug APK assembly. For a focused phone or TV iteration,
run Gradle from `clients/android/android/`:

```sh
./gradlew --no-daemon --console=plain :connected:testDebugUnitTest :connected:lintDebug :connected:assembleDebug
./gradlew --no-daemon --console=plain :tv:testDebugUnitTest :tv:lintDebug :tv:assembleDebug
```

Build origins and feature switches are optional local configuration. Keep
`local.properties`, credentials, household endpoints, signing material, media,
recordings, databases and model weights out of Git. Debug builds use no release
signer and do not install or publish an update. See the repository
[`DEVELOPMENT.md`](../../docs/DEVELOPMENT.md) for qualification details and
[`AGENTS.md`](../../AGENTS.md) for data and authorization boundaries.

## Voice and reading behavior

The assistant microphone is opt-in: mounting the screen does not record. One
explicit foreground **Start** begins temporary audio capture and read-only
assistant requests. The phone takes turns: it stops capture while a request and
reply are prepared, plays the reply, and listens again only after successful
playback. **Pause**, **End**, backgrounding, or account/library context changes
stop the session; stale replies and playback are fenced from the new context.
Uncertainty pauses the flow. Session consent does not authorize memory edits or
access changes. Outside this session, capture and transcript review remain
explicit actions.

Within that assistant flow, a user may ask to open an item in the current
displayed results or read a saved story/memoir opening. Typed requests show an
explicit action button. The opening is limited to 240 Unicode code points and
600 UTF-8 bytes. It is not a whole-chapter assistant reading mode. The phone
also has a separate, manually started chapter read-aloud control with its own
pause/resume behavior. Wait for speech to finish before speaking; assistant
streaming speech and interruption are later stages.

Earlier v59 source added explicit segmented assistant reading of a saved
story's first chapter or a memoir introduction. Continue requires the preceding
segment to finish playing and remains a separate tap; it does not advance to
later chapters or open the microphone. Later v60 source added temporary prose
size choices in the story/memoir readers, retaining the selected chapter and
unsent contribution text. These earlier checkpoints retain their original checks; later releases have
separate delivery and device evidence.

See the [v58 Chinese test guide](docs/PHONE_V58_TEST_GUIDE_ZH.md),
[v58 release record](docs/PHONE_V58_RELEASE_2026-10-14.md),
[assistant voice contract](../../docs/ASSISTANT_VOICE_RELIABILITY.md), and
[fluid assistant design](../../docs/ASSISTANT_FLUID_EXPERIENCE.md).
Candidate checks are in the [v59 guide](docs/PHONE_V59_TEST_GUIDE_ZH.md) and
[v60 reading guide](docs/PHONE_V60_TEST_GUIDE_ZH.md).

## Chapter family memory sources

A saved story's **Manage chapter memories / 管理本章回忆** panel keeps selected
source links in an unsaved draft. **Add family memory source / 添加家人回忆来源**
explicitly reads accepted, consented candidates for that chapter. The picker
shows byline, kind, submission time and optional recording duration; it does not
use original text as a preview. More pages and a failed-page retry are explicit.
Closing the picker keeps selections in the draft. Review an original through
**View family memory / 查看家人回忆**, then choose **Save links / 保存关联**.

Original words, recordings and transcripts remain separate records. No source
selection starts AI generation. Changes of story/revision/account/library or
reader lifetime fence delayed responses. Read the [shared chooser contract](../../docs/CHAPTER_FAMILY_MEMORY_CHOOSER.md)
for authorization, consent and atomic save requirements. Android qualification,
signing, OTA delivery and family acceptance remain separate gates.

## Release and acceptance

Source checks, debug APK assembly, a signed release, OTA publication,
installation, and family/device acceptance are separate evidence. The v67
release record documents the signed phone APK and published phone update; it does
not establish physical-phone or family acceptance. Native Windows and
independent Mac full-stream readback passed, and API binding plus the unchanged
TV feed were checked in postflight. Use the [Chinese v67 test guide](docs/PHONE_V67_TEST_GUIDE_ZH.md)
for voice continuation and interruption acceptance, and the [v66 guide](docs/PHONE_V66_TEST_GUIDE_ZH.md)
for retained proposal review and explicit saving. TV OTA remains v30. The
physical TV/projector check is pending. Do not treat a local check or APK
assembly as release signing, installation, or acceptance.

Keep dated release records as historical evidence. Check the current source,
release record and device state before making a delivery claim.

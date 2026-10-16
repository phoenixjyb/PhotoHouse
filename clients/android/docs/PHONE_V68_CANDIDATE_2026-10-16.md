# Phone v68 candidate: clearer voice recovery

Date: 2026-10-16

Version: **68 / `0.68-voice-recovery`**

Status: configured unsigned build, release lint and package verification passed;
signing, OTA publication and physical acceptance pending.

## Scope

The phone now explains whether a voice session paused because recognition,
a confirmed request, or audio playback failed. Chinese and English guidance
says what to do next. After failed playback, Resume returns to voice search;
it does not replay audio or continue the old reading selection automatically.
Uncertain requests retain their separate receipt-check guidance.

The microphone stays off while paused. Resume/End remain visible and explicit.
There are no new automatic retries, background listening, consent changes,
recording retention changes or account/library access changes. Existing v67
voice reading continuation remains available.

The existing production connection profile and original icon will be checked
against the unsigned package. The current signed/served version remains v67;
this document is not a publication receipt.

## Source and UI evidence

PR #70 merged as `aa8b04dd3c99b6e4a99ab2c8486548e6e478c37b`. All five CI
jobs passed at integrated review head `b51048c` (run `38881806491`). The Android
subtree matched the tested `d3df972` source. Two focused synthetic emulator tests
passed. All six fresh native Chinese/English screenshots at 150% text size were
inspected: guidance fits, microphone-off is visible and controls are reachable.
Earlier screenshots covered by Android OS ANR dialogs were rejected.

Seven emulator-controller unit tests passed. File-based APK installation keeps
the explicit emulator and separate QA-package guards. No physical phone was
selected during this qualification. The configured v68 release build and lint passed at source
`8de94671b230f389060ec3858c619d42e9b08a94`, Android subtree
`1c4bb02ce8a4d84caa800add72ed12df8cd5aa6d`. The unsigned APK is
**11,699,501 bytes**, SHA-256
`d012bcbefb92c68f64942dd7c84809cc296d9d190480813eb3e83d78ad439514`.
Native package/version and unsigned-state checks passed. All 17 embedded
settings match the existing production profile, and packaged original icon
pixels match the retained identity. Eleven profile-controller tests passed;
all 18 local links in the three release documents resolve. The later evidence
documentation does not alter that Android subtree or rebuild the APK.

## Server compatibility and delivery gates

The latest verified live API/Web source is `88de08e`, schema `a0c9d2e4f817`.
Later main source includes bilingual visual-clue additions and optional scene
recovery. Source merge does not deploy those server changes or activate scene
search or a model. The v68 guidance uses the existing voice state contract and
does not require a new API route or schema migration.

Before publication: build and inspect the exact unsigned candidate, pin its
source/tree and digest, retain the original certificate and icon, then obtain
operation authority for signing and Windows OTA publication. Verify the full
published APK and unchanged TV feed. Do not reinstall a physical phone as part
of emulator QA. Follow the [Chinese trial guide](PHONE_V68_TEST_GUIDE_ZH.md)
after an actual release; real microphone/ASR/TTS, performance and family
acceptance are separate gates.

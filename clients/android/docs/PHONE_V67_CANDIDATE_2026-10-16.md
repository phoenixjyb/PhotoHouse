# Phone v67 candidate: voice reading continuation

Date: 2026-10-16  
Version: **67 / `0.67-voice-reading`**

## Scope

This is release preparation, not a signed or published release record. The
candidate includes the merged phone voice controls and saved-section reading
continuation from PR #57 and PR #61. The paired API/Web candidate includes the
Web continuation from PR #59. The release baseline also retains PR #62's
offline scene-evaluation tools; it does not enable a scene provider or story
generation. Existing server capability negotiation still governs those features.

After a saved section finishes playing, **语音继续** explicitly starts a voice
reading session. Each “继续朗读” requests exactly one next existing segment.
Only successful playback and its owned completion receipt permit listening
again. The final segment pauses with the microphone off. Pause/End remain
reachable on both phone reader surfaces. Resume returns to voice search and
does not silently resume a reading selection.

The existing production profile and original icon are retained. The frozen v66
APK remains a distinct artifact and must never be rebuilt from this source.

## Evidence and delivery gates

PR #61 source qualification recorded 86 focused JVM cases, 18 emulator cases,
five inspected Chinese/English renders at 150% text size and five passing CI
jobs. These qualify that reviewed source, not this release artifact or a real
microphone/ASR/TTS session. Candidate build, package identity, embedded settings,
unsigned state and icon checks must bind to this round's exact source and APK.

The immutable candidate receipt records full source/tree hashes, package hashes,
build checks and remaining gates outside the public repository. Signing with
the original certificate, Windows qualification/deployment, OTA publication and
full download verification remain separate operation gates. No Windows service,
database, task, TV feed or model activation is authorized by this document.

Use the [Chinese v67 acceptance guide](PHONE_V67_TEST_GUIDE_ZH.md) after actual
delivery. Record physical phone and family acceptance separately from source,
CI, synthetic/emulator checks and signed-package/OTA verification.

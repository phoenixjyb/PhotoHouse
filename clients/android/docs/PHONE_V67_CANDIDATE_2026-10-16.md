# Phone v67 candidate: voice reading continuation

Date: 2026-10-16  
Version: **67 / `0.67-voice-reading`**

> Historical candidate-preparation record. Phone v67 has since been signed and
> published to the phone OTA feed. The delivery evidence is in the [v67 release
> record](PHONE_V67_RELEASE_2026-10-16.md); physical phone and family acceptance
> remain open.

## Scope

This page records the pre-release candidate scope and source checks. The phone
build used source commit `4c2731277ad005ae61e10ddbe665734ee6551db2`. Its Android
subtree (`4cc4db38beaced9a23833fdebe9836024bc70ef5`) is identical to the subtree
in merge `cad2572458522e9d57dc7da8a0e14b4005435bc4`.

The reviewed API/Web source is commit `88de08ef03a6a3be91e02a02941fd57b223e48c4`,
whose full repository tree matches that merge. It contains the Web continuation
from PR #59 and the optional reviewed scene-provider path from PR #63. Scene
search and story/model generation remain default-off. This phone delivery did
not activate a provider or deploy the API/Web candidate.

After a saved section finishes playing, **语音继续** explicitly starts a voice
reading session. Each “继续朗读” requests exactly one next existing segment.
Only successful playback and its owned completion receipt permit listening
again. The final segment pauses with the microphone off. Pause/End remain
reachable on both phone reader surfaces. Resume returns to voice search and
does not silently resume a reading selection.

The existing production profile and original icon are retained. The frozen v66
APK remains a distinct artifact and must never be rebuilt from this source.

## Evidence and delivery gates

PR #61 source qualification recorded 86 focused JVM cases and 18 emulator
cases. Those are source/emulator results from that review, not a v67 physical
phone or real microphone/ASR/TTS acceptance result.

The final signed artifact, native and independent HTTPS readback, and offline
API qualification are recorded in the [v67 release record](PHONE_V67_RELEASE_2026-10-16.md).
The reviewed API/Web package was qualified only with synthetic fixtures. It was
not switched live, no production schema was applied, and no provider/model or
worker was activated by this release.

Use the [Chinese v67 acceptance guide](PHONE_V67_TEST_GUIDE_ZH.md) after actual
installation. Record physical phone and family acceptance separately from
source, CI, synthetic/emulator checks and signed-package/OTA verification.

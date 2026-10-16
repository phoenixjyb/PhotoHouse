# Phone v67 release: voice reading continuation

- Date: 2026-10-16
- Phone version: **67 / `0.67-voice-reading`**
- Phone source: `4c2731277ad005ae61e10ddbe665734ee6551db2`
- Release merge: `cad2572458522e9d57dc7da8a0e14b4005435bc4`

## Phone delivery

The signed phone APK for `dev.photohouse.connected` is **11,716,984 bytes** with
SHA-256
`17cbfa7b5c644d31c880a18850e3efc9db804fa454c7d134f35957ddc4bd6589`.
It retains the original signing certificate
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`; native
signature and zip alignment verification passed. Signing left all three DEX
entries and the retained icon bytes unchanged.

The phone build used commit `4c2731277ad005ae61e10ddbe665734ee6551db2`. Its
Android subtree `4cc4db38beaced9a23833fdebe9836024bc70ef5` matches the subtree in
merge `cad2572458522e9d57dc7da8a0e14b4005435bc4`. The API/Web review source is
`88de08ef03a6a3be91e02a02941fd57b223e48c4`, whose full repository tree matches
the merge.

Phone v67 was published to the phone OTA feed. Native feed verification and
trusted HTTPS readback passed for all **11,716,984 bytes**, matching the signed
APK SHA-256 above. An independent Mac HTTPS stream verified the same complete
APK digest without saving a second APK copy. The TV v30 pointer and manifest
remained unchanged.

The phone-publication postflight confirmed that the API task, process,
configuration and listener binding and update root were unchanged at that time;
the TV v30 pointer and manifest were unchanged. A separate API/Web cutover
followed later that day and is summarized below. The phone operation did not
restart the API or change scheduled tasks. The phone postflight compared the API
binding; other host services were not inventoried.

## Source and API qualification

All five jobs in CI run `38863300472` passed. The first API attempt hit the
optional Node fixture resolution failure; its targeted retry passed before the
all-green run. Release build and lint, native unsigned package identity, all 17
embedded settings, original icon checks and feature DEX checks passed. The
earlier PR #61 qualification recorded 86 focused JVM cases and 18 emulator
cases; those results are source/emulator evidence, not physical phone
acceptance.

The API/Web source-only archive from `88de08ef` contains 237 files and has
SHA-256
`910f9e864bf04bc6cb24d0a279f0c3968ff83d180842e310c400a9ec7b771df9`. Its
bounded native synthetic qualification passed 12 assistant cases, 12 oral
history cases and 26 query-planner assertions. It did not open the production
database, use family media, invoke a provider/model, start a listener, run
workers, or change services or tasks. The oral-history schema in this check was
experimental fixture schema only; production admission and live schema
application were not qualified.

At phone publication time, the API/Web candidate had not been switched and the
live API remained on its previous `f476c5e` binding. Later on October 16, a
separate API/Web operation deployed source `88de08e`. Its native and HTTPS
readback passed, the stopped-writer backup passed integrity checks, and all five
writer workers were restored. The schema stayed `a0c9d2e4f817`; no migration or
configuration change occurred. Scene search and story/model generation remain
default-off; no model activation was part of either release operation.

## Acceptance boundary

The signed v67 app was installed and launched on a Samsung phone. This does not
establish voice behavior, real microphone/ASR/TTS quality or family acceptance;
no real voice session or family trial was recorded. Follow the
[Chinese v67 post-release acceptance guide](PHONE_V67_TEST_GUIDE_ZH.md) and record
those outcomes separately. The historical candidate scope and source notes are
in [PHONE_V67_CANDIDATE_2026-10-16.md](PHONE_V67_CANDIDATE_2026-10-16.md).

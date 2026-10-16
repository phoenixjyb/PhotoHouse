# Phone v65 release: chapter family-memory chooser

Date: 2026-10-16  
Version: **65 / `0.65-chapter-memory`**  
Source: PR #49, merge `22472be475fd4e4b3b5423f2e96d91a773592b0d`  
Tree-equal build/review evidence: `8bd9c5a63b14c607aaadbcc29cdb3f9144d2e421`

## Delivered

Phone v65 adds the explicit metadata-only family-memory chooser to saved-story
chapter link management. The chooser uses the existing contribution-candidate
API and revision-bound atomic save contract. It does not enable story generation
or change the server schema. The bilingual search clarification shipped in PR
#48; API/Web source `f476c5e16f032eb427e3504997d6e33b5a500d9b` is live.

The original phone signing certificate and icon were retained. The Windows
HTTPS OTA feed publishes this release. The signed APK is **11,663,736 bytes**
with SHA-256
`40b74da0a9e9a056f247bbf8bbb511586931550ebd847c23e3ab8d4187767b2e`.

## Qualification evidence

All five source CI jobs passed in run `38835026125`. Separate release
verification passed configured build/lint, 17 embedded-field checks, four
signing-refusal checks, 11 publication tests, native full-HTTPS verification,
independent Mac full-stream readback and 10 Web asset checks. The preceding
Android source qualification included 74 focused JVM tests, compilation, lint,
QA debug build, and three Chinese/English emulator journeys at 150% text size.
The rendered views were inspected.

Release postflight preserved all eight running root tasks and five upload
workers; ASR, TTS and OCR processes were unchanged. API/Web pairing did not
restart the API or change schema/configuration. TV remains v30 and unchanged;
v31 source is unpublished.

## Acceptance boundary

No physical phone installation or test occurred during this operation. Family
and device acceptance remain open. For a manual owner/member check, use the
[Chinese v65 test guide](PHONE_V65_TEST_GUIDE_ZH.md). The chooser permits review
of a ready transcript or original text after an explicit action; the list itself
shows metadata and does not automatically fetch or play original audio.

The separate reviewed chapter-proposal adoption flow into an unsaved existing
story editor is following source. It passed 74 focused JVM tests, build/lint
and eight QA-emulator journeys with inspected Chinese/English 150% renders.
It is not included in v65; later APK delivery and family acceptance remain open.
Provider/model story generation remains off; the synthetic 9B cold-capture sample
has not had human quality review.

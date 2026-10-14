# Phone v60 and Web/API local candidate — October 15

This is a **local qualification record**, not a release or installation notice.
The immutable artifact source is `53e3954725197906771b6dd6ca470a0d1d58da9d`.
The live installation remains the v58/API baseline in
[Project Status](../../../docs/PROJECT_STATUS.md). The prior v59 conditional
operation proposal cannot be used to substitute these v60 artifacts.

## Changes families will see after delivery

- Smaller/default/larger story and memoir prose with system text scaling retained.
- More room for phone memoir text: chapter controls remain fixed; story navigation
  moves into the scrollable reading area.
- Explicit current-image preview recovery without reopening a story, changing a
  bookmark, submitting a contribution or restarting speech.
- A [first-story guide](../../../docs/FIRST_STORY_GUIDE_ZH.md) and an updated
  [phone/Web trial](PHONE_V60_TEST_GUIDE_ZH.md).

The broader source candidate also contains prior v59 assistant reading, recovery
and progress work. It does not activate model providers, generation, grouping,
long recording intake, erasure or memoir editorial processing.

## Exact artifacts

| Item | Identity |
| --- | --- |
| Phone package | `dev.photohouse.connected`, code `60`, `0.60-reading-comfort` |
| Unsigned APK | 11,562,801 bytes; SHA-256 `bd9ea93b44383d644066604f29511e79b1fc10032cda4d622e73ebaf57776cf3` |
| Android subtree | `df7d5e9439e77b50e94beff2d8c6869db8a4984f` |
| API source archive | 201 source files, 3,607,452 bytes; SHA-256 `793a5322400dce1d44de8f673e725fab096210e4fd41574d056751b3cbe3989d` |
| API manifest | SHA-256 `819523c00fe5088a5b45e09c2fdb9397c88e43496350bacf9b1614b6cfdcd7a2` |
| Schema | Unchanged `a0c9d2e4f817`; no migration in this candidate |

Artifacts remain in private local candidate directories. No credentials, private
profile values, household media, database or model weights are in the source ZIP.
The APK uses its reviewed private build profile; those values are not reproduced
here. Original source/packaged icon pixels and all 17 embedded profile fields
match their pins. Signature verification correctly rejects this unsigned APK.

## Qualification

- Complete API profile: 1,495 tests / 915 subchecks and generated no-listener demo;
  unchanged-input receipt at the exact artifact source.
- Complete Android JVM/lint/debug-build profile: passed at the same source;
  configured offline release assembly and release lint passed separately.
- Focused preview recovery: 24 phone store cases, debug lint, four bilingual
  API 36 emulator cases, six Edge story checks and eight Edge memoir checks.
- Enlarged Chinese/English phone and browser renders were inspected. Reading
  controls and compact navigation have their own earlier focused journeys.
- Canonical archive/local Git inspection passed. An initial identity refusal is
  retained privately; the unchanged archive hash passed subsequent inspection.
- Exact extracted archive: twelve assistant groups plus five experimental
  oral-history groups / twelve cases, with generated data on Mac.

The first full Web pass stopped at a memoir text-scale fixture that repeatedly
scaled a persistent dialog and inherited line height. Its failed receipt is
retained. The fixture repair preserves the strict bilingual viewport and speech
lifecycle checks; the complete final Web qualification is recorded in
[Development](../../../docs/DEVELOPMENT.md) at its review commit. All packaged
runtime files and the Android subtree must match this immutable source before
using that later Web receipt as qualification for these artifacts.

## Remaining delivery and family gates

Native Windows generated qualification, exact guarded backup/API cutover and
worker recovery, original-certificate signing and phone HTTPS OTA publication
require their operation scope. No v60 Windows staging/execution, signing, OTA
publication, physical installation or real-family listening was performed here.
TV v31 remains a separate unpublished source candidate; the TV feed stays v30.

After delivery, use owner and member accounts for the linked trial. Check current
version, retained text, preview recovery, reading position, language, actual
audio completion before relistening, Pause/End and account/library boundaries.
Emulator/API/browser checks cannot establish physical audio quality or whether
a family story is compelling and accurate.

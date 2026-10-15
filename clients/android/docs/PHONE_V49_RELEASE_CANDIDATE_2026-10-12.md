# Phone v49 assistant workspace candidate

Version 49 (`0.49-assistant-workspace`) was signed and published to the phone
HTTPS OTA on 2026-10-12 with owner authority. Windows native verification and
independent complete HTTPS download checks passed; family/device acceptance
remains open. The Web workspace has a separate delivery operation.

## Changes

- Dedicated 拾光助手 conversation workspace with current-library context,
  media result cards and preserved editable text drafts.
- Explicit foreground Start/Resume grants read-only listen → transcribe →
  retrieve → speak result count → listen. Pause/End stay visible.
- Endpoint detection stops after sustained speech plus silence; no speech,
  provider failure, uncertain request, account/library changes, departure from
  foreground and audio-focus loss stop automatic progression.
- Only actual successful speech playback admits the next microphone capture.
  Clarifying, empty or unsupported replies stay visible and pause the loop.
- Exact accepted transcription retains server receipt correlation; input WAV
  bytes are wiped after processing. Late callbacks and denied reads cannot
  restore old private assistant context.
- Manual dictation remains separate and reviewed. Ending voice restores the
  unsent text draft. Changes to family content require their existing review.

This candidate uses the existing protected v1 assistant. It adds no API route,
main database schema, model activation or TV behavior. It does not yet include
a general local-model agent, durable private conversation APIs or cross-device
preferences. The separate backend thread/preferences store is source-only and
inactive. See [the approved design](../../../docs/PERSONAL_ASSISTANT.md).

## Delivery gates

The configured unsigned package was built/linted at clean source
`835fd900268a142f4444e2c6fa5d12ba0967f561`: **10,120,589 bytes**, SHA-256
`757ef78529f60ed5e7d30632be3b2d45bed5ec504590d2e1426559fcdac1af78`.
Native metadata confirms version 49 and its package; all 17 embedded fields
match the retained reviewed phone profile, with fixture/UIQA flags off. Signature
verification correctly rejects the unsigned package. This records the unsigned build inputs; the signed delivery is recorded below.
Family acceptance remains pending.

The affected modules passed 850 live-core and 17 phone JVM tests. Final phone
lint/debug/test assembly and 17 simulator cases passed, including actual context
labels, voice entry and receipt recovery above the IME at enlarged text. Failure
history and environment recovery are recorded in
[Development](../../../docs/DEVELOPMENT.md#october-12-central-assistant-foundation).
These are synthetic checks; real microphone and family acceptance remain open.

Pin clean source and the complete reviewed private phone profile. Build/lint
without fixture/UIQA flags; verify every DEX property, package/version, hash,
size and unsigned status. Signing, fresh private Windows staging, native package
checks, phone-pointer publication and full trusted HTTPS readback require their
exact scope authority and preserved rollback evidence. No API restart is needed
for the phone package. The separate Web workspace has its own service delivery
gate.

## Signed delivery

The signed APK is **10,139,968 bytes**, SHA-256
`94d4f602ea849ad5ab30d36f2605b2f8cd9fb620b9cd465753a701a7cb7a451c`.
Native metadata confirms `dev.photohouse.connected`, version code 49 and
`0.49-assistant-workspace`, signed with the original certificate
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.
The Android build subtree is unchanged between artifact source `835fd900…` and
reviewed checkout `af26a99…`; the APK was built from the earlier source pin.

Twenty local controller checks passed after correcting the preparer's authority
path to match the executor, before any signing or remote mutation. The original
prepared scripts/manifest remain private failure evidence. Signing happened once;
fresh Windows staging, exact native metadata/certificate/byte verification and
phone-only publication completed. Both Windows and an independent Mac read the
complete APK through trusted HTTPS and matched its size/hash. TV v30 and its feed
bytes were preserved. The phone delivery did not restart the API, change a task,
migrate a database, activate a model or install a physical device.

## Family acceptance

Start voice; ask for photos in an authorized date range; after the spoken count,
refine to videos and request the second visible result. Check the opened viewer
and return to the same conversation. Pause/End during recording, transcription
and playback; verify silence while paused and explicit Resume. Check background,
a phone call/audio focus loss, unavailable provider and uncertain network reply
without automatic resend. End voice and verify a previous typed draft remains.
Repeat in Chinese/English with enlarged text and another authorized account.
Keep family text, recordings and credentials out of public acceptance reports.

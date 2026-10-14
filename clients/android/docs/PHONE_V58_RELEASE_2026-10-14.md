# Phone v58 and API/Web delivery

Phone **58 / 0.58-contextual-memory-actions** is signed and published on the
Windows HTTPS OTA feed. API/Web source `8bc60e816e321c5a6ea4e8ca7b1ecf797b236138`
is deployed. The original certificate and launcher artwork are preserved; TV
OTA remains v30. Physical phone installation and family listening acceptance
remain open.

## Features to try

Fresh saved-story and memoir results support ordinal voice requests. During an
explicit foreground voice session, **打开第二个故事** opens the second current
story and ends listening before reader navigation. **朗读第一个故事的开篇** reads
the first current saved opening, then listens again only after successful actual
playback finishes. Typed requests expose explicit action buttons. Ambiguous or
out-of-range choices retain the displayed cohort and ask for clarification.
Pause/End, account/library changes and source revision changes fence late output;
recovered history carries no executable opening/reading metadata.

Use the [Chinese test guide](PHONE_V58_TEST_GUIDE_ZH.md). The opening remains
bounded to 240 Unicode code points and 600 UTF-8 bytes. This assistant flow uses
half-duplex turn taking; full chapters, streaming speech and speaking interruption
remain later assistant stages.

## Artifact and delivery evidence

- Package: `dev.photohouse.connected`, version code 58.
- Signed APK: **11,549,048 bytes**, SHA-256
  `63c54642e0540d3b8f044ae36d8943c5d76e44790a58bfcf24bf43c4e71daf14`.
- Original certificate SHA-256:
  `56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.
- Signature, alignment, package/version, unchanged DEX and original icon byte
  checks passed. The frozen 17-field profile and build receipts match the exact
  unsigned candidate; signing did not rebuild or rebind its source revision.
- The phone-only delivery controllers passed 16 local checks and five native
  generated-script parses. Actual Windows publication verified the native APK
  and complete HTTPS download against the signed artifact.
- Independent Mac trusted HTTPS first/last 64 KiB range checks match the signed
  file. Its additional complete download timed out during transfer; no complete
  Mac download pass is claimed and no extra APK copy was saved.
- API services/tasks, database, media and TV feed were unchanged by phone
  publication. Guarded phone-pointer rollback was prepared but was not needed.

The [fixed candidate](PHONE_V58_RELEASE_CANDIDATE_2026-10-14.md) records source,
unsigned artifact and local/emulator qualification. Android was built at
`7ff0a8e7666f9af8f8320889bfde31429be61e0c`; tree
`b6d9974057899e8728e44dc125c5abbed2fec7b5` matches the later API qualification
revision. Neither publication nor synthetic checks establish physical acceptance.

## API delivery

The separately authorized API switch passed native qualification of 195 source
files and eleven synthetic groups, then used a verified stopped-writer backup,
served-byte/anonymous-denial checks and worker restoration. Independent post-switch
verification confirmed schema `a0c9d2e4f817`, unchanged configuration, all five
upload worker definitions/running states and the 30-second startup trigger. No
migration or provider/model activation occurred. No hosted CI run is claimed.

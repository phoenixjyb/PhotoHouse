# Phone v58 contextual memory actions candidate

Status: prepared locally; native Windows qualification, live deployment, original-certificate signing and phone OTA publication remain pending. The current delivered baseline is v57.

## Fixed source and artifacts

API/Web qualification source is `8bc60e816e321c5a6ea4e8ca7b1ecf797b236138`.
Its source-only ZIP contains 195 files, is 3,461,241 bytes, and has SHA-256
`c17da6ac93af17956092957ad9e833690387c41534890a5dff04e2236e2336ac`.
All extracted members match the manifest; the extracted qualifier passed its
11 synthetic scenario groups on Mac, including contextual memory action checks.
No real database, media, provider/model, network, listener or worker was used.

The configured unsigned phone package is `dev.photohouse.connected`, version
58, `0.58-contextual-memory-actions`. It is 11,530,077 bytes, SHA-256
`ab8a45b78da38feb69ac1887a27b769cc0c14ab8c3e78733a94e6bc4a41859d4`.
It was built from `7ff0a8e7666f9af8f8320889bfde31429be61e0c`; its Android
subtree `b6d9974057899e8728e44dc125c5abbed2fec7b5` is identical at the API
qualification revision. The later commit adds server release qualification and
route-inventory checks, without changing Android source.

Offline release assembly and lint passed. Native metadata and all 17 embedded
configuration fields match the retained reviewed phone profile, with fixture
and UI QA modes disabled. Signature verification rejects this unsigned APK as
expected. The original packaged icon RGBA SHA-256 remains
`f5e55b4fe45566cf53911d6fb1be20f357f29a8e02d4d1a1e26364dac227c673`.
No household configuration, endpoint or signing material is included here.

## Behavior and acceptance

Fresh saved-story and memoir results can be addressed by ordinal. In an approved
foreground voice session, “打开第二个” opens the second current card and ends voice
before navigation; “读第一个的开篇” reads its saved opening, then listens again only
after confirmed successful playback. Typed commands expose explicit action
buttons. Ambiguous or out-of-range commands retain the full ordered cohort and
ask for a choice. The whole cohort and source ownership are revalidated; recovered
history does not retain executable action metadata or opening text.

[Development](../../../docs/DEVELOPMENT.md) records backend, Web, Android and
large-text emulator evidence. The full API profile passed 1,426 tests and 862
subchecks plus its generated no-listener demo. These are local checks, not hosted
CI, Windows runtime qualification or physical family acceptance.

After delivery, test on a signed-in phone and Web session:

1. Search for saved memories in a library with at least two stories or memoirs.
2. Start foreground voice, say “打开第二个”, and verify the correct reader opens
   with listening ended. A typed request should require the visible action button.
3. Start a fresh session and say “读第一个的开篇”. Check the saved wording,
   preparation/speaking states and that listening resumes only after sound ends.
4. Press Pause/End while preparation or playback is active. Confirm no delayed
   sound, navigation or microphone restart. Repeat after a library/account change.
5. Ask for an unavailable ordinal and verify a choice prompt preserves ordering.
   Reload history and confirm it has no automatic opening/reading action.

The release continues half-duplex turn taking. Speaking interruption, streamed
speech and whole-chapter narration are later roadmap stages.

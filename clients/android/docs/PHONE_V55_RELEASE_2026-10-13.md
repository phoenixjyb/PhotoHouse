# Phone v55 and saved-memory reader API/Web delivery

## Release identity

October 13 source: `c65528a3f9a5195655bd548e2cca1cafe6a196de`.
Phone `dev.photohouse.connected`: version 55 / `0.55-saved-memory-readers`.
The original signing certificate and launcher icon pixels are unchanged.

| Artifact | SHA-256 | Bytes |
|---|---|---|
| API/Web source ZIP | `77160fa3aa5c05236e6c986d681f068e63576c81c54847256178eb7fb6b1ba8c` | 3,372,498 |
| Unsigned phone APK | `7dc4717b8422cdcf3fce3e93f61a6e26a714910dc78c5a04088a732d9478e56a` | 11,503,745 |
| Published signed phone APK | `37653634b2b3a6d6ca2ae2214709f8cb6cf492d9a4fd022a14a7f8f006f8190a` | 11,524,472 |

Certificate SHA-256:
`56d7591b2b6c2538d506d1fe51327444f2307736cb12f5beefa08f1c410d6d28`.

## Changes

Fresh saved-memory search cards now have an explicit protected story/memoir
reader action on both Web and phone. Opening ends foreground voice first and
revalidates the completed turn, account/library, source revision and memoir
children. Historical and recovered replies remain inert. Search, speech and
reader capabilities are negotiated separately.

This release does not include the later
[saved-memory conversational followups](../../../docs/ASSISTANT_SAVED_MEMORY_FOLLOWUPS.md).

## Evidence

- The fixed 194-file API package passed Windows synthetic qualification: eleven
  scenarios, including full story/memoir reader handoff, foreign access refusal,
  superseded parents and stale sources. The child was limited to five minutes,
  2 GiB and eight processes with an 8 GiB free-RAM admission floor.
- Eight native release controllers passed parsing; thirteen local release
  protection checks passed. At 14:25 UTC on October 13, API/Web source was
  verified and five upload workers restored.
- A fresh stopped-writer backup passed four database integrity checks. Schema
  remains `a0c9d2e4f817`; configuration bytes are unchanged. Independent readback
  verified eight required tasks running/enabled and preserved ASR/TTS/OCR
  processes. Eight served Web resources match the fixed package over trusted HTTPS.
- The first independent native inventory transport timed out after 90 seconds.
  A shorter read-only invocation passed; maintenance and publication were not
  replayed. The failed transport did not change services.
- Original-certificate signing and native complete HTTPS APK verification passed.
  Phone feed publication restarted no service. TV remains v30.
- Independent Mac verification read all 11,524,472 bytes in 44 ordered HTTPS
  ranges, taking 4.19 seconds with zero reconnections. The SHA-256 matched and
  phone/TV feed responses remained stable. No duplicate APK was saved by this check.

Physical phone installation, family microphone/speaker quality and owner/member
reader acceptance remain separate gates. No model or provider was activated.

## Owner test

1. Install v55 through “检查更新”, select a library with a saved story or memoir,
   and enter 拾光助手.
2. Search using a distinctive word from its title, for example “找故事 野餐” or
   “找回忆录 夏天”. These are literal saved-text searches, not visual matches.
3. Confirm the title and excerpt; tap “打开已保存的故事” or “打开回忆录”.
   If voice mode was active, it must stop before the reader opens.
4. Confirm chapters/media correspond to that saved source. Repeat in WebUI.
5. Reopen private conversation history: old replies must not automatically
   reopen a story, play speech or restart listening.

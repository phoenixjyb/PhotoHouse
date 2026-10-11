# October 12 local memoir experience candidate

Development remains in the unified PhotoHouse repository. The accepted Web
snapshot is `263439ce34ebb894164923b674142a577b19fe68`. Phone narration
received a final correction qualified at `0548d8cbb04c02aa9ca960059a6b564358fc683f`.
The final clean source archive records its own complete HEAD in its verification
report; documentation and log-reader changes have separate source overlays.

## Implemented in this round

| Area | Accepted source | Behavior |
| --- | --- | --- |
| Conversation continuation | Backend `e042544`, Web `54f323b`, phone `e157679` | Preserve old history and rejected words; a new conversation and Send are explicit |
| Phone memoir composition | `e157679` | Choose and order 1–24 readable saved stories; reviewed opening dictation and immutable uncertain-save retry |
| Visual phone discovery | `61847c7` | Protected cover thumbnails, opening excerpts, fallback and scoped read/retry actions |
| Web opening dictation | `bd8f6b6` | Preserve typed opening, review transcript, Add, then Save; shared microphone and exact form/membership guards |
| Memoir validation | `7d13745`, `65bf10c` | Failed UUID allocation retains editable draft; actionable inline validation without losing words |
| Opening narration | Web `a8e8b47`, phone `6f140f8` | Saved words and book language; explicit local Read/Pause/Resume/Stop; no automatic chapter advance |
| Recording correction | `cd87ab2` | Duration-complete note releases its reservation during delayed resume; valid mic start stops narration |
| Manual narration correction | `a63a35a`, `466ada2` | Read/Resume require current enabled foreground scope; delayed Pause cannot become Resume; explicit Pause/Stop remain usable |
| Phone release identity | `a4507e3` | v47 / `0.47-family-memoir-composer`; TV version unchanged |

Full contracts and qualification details are in [Development](DEVELOPMENT.md),
[architecture](ARCHITECTURE.md), [features](FEATURES.md) and [roadmap](ROADMAP.md).

## Evidence and prepared artifacts

- All 19 Web suites passed at the Web snapshot. The final Android JVM/lint/debug
  profile passed at `0548d8c` with unchanged source (71s, 175 tasks).
- The final 28-case narration/opening/chapter/contents simulator cohort passed
  in 145.835s and the strict log reader accepted it. Its first run passed 27 and
  caught one stale Pause/Resume action; the phase-bound correction fixed it.
  Earlier nine-case opening qualification and corrected failure logs remain
  evidence. Earlier composition, dictation, continuation and shelf checks retain their own pins. Enlarged bilingual renders were inspected.
- The final public phone v47 unsigned APK and release lint passed together in
  121s at the final Android snapshot. Package and native manifest report version 47; origins are empty, optional capabilities off and
  signature absent. The [phone candidate](../clients/android/docs/PHONE_V47_RELEASE_CANDIDATE_2026-10-12.md)
  records its size/hash, test walkthrough and private delivery requirements.
- A source-only five-asset Web overlay is prepared from the accepted snapshot:
  958,278 bytes, ZIP SHA-256
  `af5559f8d77e4b201cfe305ff7b9bfce7c99da7d807fc2e7ead6d6af8c79349b`;
  manifest SHA-256
  `02513b32ac7f276e91f33ea06357c34b9bcb964622d195cbf0ef0edaecf5ef32`.
  Nine builder/binding tests passed. A temporary no-listener router served all
  five exact extracted files and retained the icon path. It has not been deployed.
  See [Web delivery](WEB_DELIVERY.md).
- Existing-log Android instrumentation analysis (`55b1a05`) qualifies output completeness
  only. Ten focused cases and the full 121-test tooling cohort passed; it accepted
  both complete pass logs and rejected retained failures with safe counts. It does
  not establish test freshness, APK/source identity or a device.

## Next delivery work

1. Read back the current Windows API/worker/task/database and private build
   profile identities. Historical snapshots are not current runtime evidence.
2. Pin the exact compatible server/worker candidate and finish its existing
   migration, stopped-writer backup/restore, private ACL and rollback gates before
   proposing a live switch. Shared-memory/AI/title features retain their separate
   default-off and provider/vector qualification requirements.
3. For a Web-only delivery, independently qualify the selected overlay against
   the actual API/configuration. Its archive neither migrates storage nor enables
   server capabilities. Prepare bounded switch, rollback and HTTPS hash readback.
4. Prepare v47 with all private inputs explicit, qualify its unsigned package,
   then obtain signing/publication authority for that exact artifact. The public
   APK cannot be installed as a configured household update.
5. Complete owner/member/revoked-access and family voice/story walkthroughs.
   Use feedback to refine related-moment boundaries, collaboration and longer
   storytelling; generated source checks do not establish provider quality.

No Windows operation, model change, live database/media write, signing,
publication, physical installation or family acceptance occurred in this round.

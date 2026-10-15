# Phone v64 and story review delivery

## Artifact identity

| Item | Verified value |
| --- | --- |
| Source/API package | `5480a0cc99133acc1308caf19a0e33d372cc32f6` |
| Reviewed merge | PR #25, `4e94650b9b75c2921a1990a6cdcd05a9a29ce1a4`; same source tree |
| Phone package | `dev.photohouse.connected` |
| Phone version | 64 / `0.64-story-review` |
| Signed APK | 11,647,352 bytes |
| Signed APK SHA-256 | `4e715eda37cb852b300dc6a4b272c867bca1ae4a3091ba2bb812ba2342bdab25` |
| API source ZIP | 217 files; SHA-256 `b72e72c7729e7eb37d0351d641085682c9ae3b29206730622958a59446c76435` |
| Database | `a0c9d2e4f817`, unchanged |
| TV | v30 feed unchanged |

## Delivered behavior

New Web and phone stories offer an explicit [chapter-opening title
shortcut](../../../docs/CHAPTER_OPENING_TITLE.md), including reviewed dictation
and private draft persistence. It uses literal authored chapter text, keeps a
custom title until adoption and leaves saving explicit.

[Story proposal review](../../../docs/STORY_PROPOSAL_WORDING_REVIEW.md) counts
changed, matching and unavailable chapter wording. An optional focus collapses
matching prose while retaining headings, sources, questions and review controls.
The default shows every chapter. Matching wording does not prove matching
citations or factual accuracy. Generation remains disabled in this installation;
these proposal controls do not activate it.

The release includes the latest integrated search source, preserving the live
`78a433b` search deployment as the incumbent for the guarded switch. Private
drafts, guided creation, search v2 and voice behavior retain their existing
contracts. A later [companion citation rule](../../../docs/STORY_COMPANION_GROUNDING.md)
is separate source work and is not included in this frozen v64 artifact.

## Verification and operational result

All five review-head GitHub jobs passed. The serial offline phone release build
and lint, seventeen embedded profile fields, native package identity, original
certificate, unchanged DEX, alignment and original raster icon checks passed.
No physical phone was installed or tested by this operation.

Windows qualification used generated data: twelve assistant cases, eight planner
assertions and five oral-history groups/twelve cases. It opened no production
database, provider/model or listener. The live switch then made a verified
four-store stopped-writer backup, switched only the API action, verified served
assets and anonymous access boundaries, and restored five upload workers.
Independent postflight verified all 66 task enabled states, preserved API startup
settings, six present backup files/four stores and unchanged ASR/OCR/TTS processes.
Configuration and schema were preserved; no migration or model activation ran.

Phone OTA publication bound the current API and both previous feed pointers,
validated the native signed APK and completely read it back over trusted HTTPS.
TV stayed unchanged. A separate Mac HTTPS stream verified the complete APK hash
without storing a duplicate, and checked ten served Web assets against the
frozen source. Publication required no API restart or database/media changes.
Installation, family relevance and physical audio/UX acceptance remain open.

## Try it

1. On the phone, open **检查更新** and install v64. Refresh Web to get the new UI.
2. In a new story, write chapter text or add a reviewed transcript. Try
   **用章节开头做标题** and **用作标题**. Confirm the title stays editable and no
   story is saved until you choose to save it.
3. Try a custom title, save a private draft, leave and resume it. Confirm your
   wording and chosen title return before saving the shared story explicitly.
4. If using a separately qualified generation-enabled installation, inspect the
   chapter summary and **只看正文变化** toggle. References and questions should
   remain visible. This deployment does not enable that provider path.

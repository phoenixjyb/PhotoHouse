# Phone v63 and private story draft delivery

## Artifact identity

| Item | Verified value |
| --- | --- |
| Source/API package | `975968ed8800493f9c1bd42688f21ca7f7348531` |
| Reviewed merge | PR #20, `6b1a08a61f8a33cf81a4bdc06ff397db61c2b213`; same source tree |
| Phone package | `dev.photohouse.connected` |
| Phone version | 63 / `0.63-private-story-drafts` |
| Signed APK | 11,647,352 bytes |
| Signed APK SHA-256 | `19343a87358ffcbcb71a43785bd46d71182f5e07dd1f4e74772453fa838230e6` |
| API source ZIP | 209 files; SHA-256 `fc21a2099732ff3589f179a0c5bdb35e6818ccd68cb0e63f153ab24a55709990` |
| Database | `a0c9d2e4f817`, unchanged |
| TV | v30 feed unchanged |

The original signing certificate, raster icon and private build profile are
preserved. The serial offline release build and lint pass. Native APK metadata,
all seventeen embedded build fields, unsigned/signed checks, unchanged DEX and
icon checks pass. The review head passed all five GitHub source-check jobs.

Windows offline qualification used generated fixtures: twelve assistant cases,
eight search-planner assertions and five oral-history groups/twelve cases. It
opened no production database/media, provider, network or listener. The first
qualification attempt refused an inherited helper's old source pins; corrected,
fully bound helpers passed in a fresh candidate. No live retry or migration was
used to correct that preparation failure.

The live API update used the already deployed search source `1913152` as its
incumbent. The guarded operation verified a four-store stopped-writer backup,
switched the API action, checked served bytes (including the new draft script)
and anonymous access boundaries, and restored five upload workers. Independent
postflight verified backup hashes, all 66 enabled states, startup/settings and
preserved ASR/OCR/TTS processes. Configuration, models and schema are unchanged.

The phone APK was published to the Windows phone HTTPS feed, with native package,
certificate, digest and complete HTTPS APK readback checks. An independent Mac
streamed the complete APK and matched its checksum without saving another copy;
an initial Mac stream timed out before the successful bounded retry. Both feed pointers
were bound before publication; TV was unchanged. Publication performed no API
restart or database/media write. Device installation and family acceptance are
separate from these source, native and service observations.

The subsequent main-push browser run exposed a fixture race: a failed preview
sets `img.complete` before its expected fallback finishes. The test-only follow-up
waits for decoded dimensions before capturing requests; its strict assertion
that detached controls issue no requests remains unchanged. All six focused
reader checkpoints pass. No application source or released artifact changed for
that correction; follow-up hosted CI is tied to its own commit.

## Try the update

1. On the phone, use **检查更新** and install v63. On Web, refresh the existing
   HTTPS page. Sign in and choose a library containing a few photos or videos.
2. Start a new story, choose moments and write a few words or review dictation
   before adding its text. Choose **保存私密草稿**, then leave the editor and
   reopen the app/page.
3. Choose **继续草稿**. Confirm that your wording and grouping return. Review the
   refreshed moments/sources before explicitly saving the shared story.

Draft saving itself does not publish a story or upload a recording. Drafts stay
on that device until deleted or successfully published; site-data clearing or app
removal can also remove them. Edits to an already saved story and cross-device
draft synchronization are outside this release. See [the draft contract](../../../docs/STORY_DRAFT_RESUME.md).

Grounded AI title/narrative generation, adjustable memory-group activation and
long oral-history delivery retain separate roadmap and qualification gates.

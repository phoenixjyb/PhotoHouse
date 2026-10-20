# Similar-photo stacks

**Delivery — October 19:** API/Web source `f2041c1` is live and phone v73 is
published on HTTPS OTA. See the [phone release and test steps](../clients/android/docs/PHONE_V73_RELEASE_2026-10-19.md).
The dated qualification records below describe their original gates; the later
delivery closes the API rollout and phone publication gates, while family
similarity quality, physical device acceptance and persistent curation remain open.

**Following source — October 20:** [Library-wide indexed stacks](LIBRARY_PHOTO_STACKS.md)
add consistent collapsed pagination and saved account-private choices. This is
source work only; the delivered gallery described below still uses page-local v1.

## Purpose

A sequence of near-identical photos should occupy one gallery position until a
member chooses to see the alternatives. Every original remains an ordinary
accessible asset. A stack is a reversible presentation of similar photos; it is
not an album, story, memory-group assignment or deletion decision.

## Conservative grouping

The optional `photo_stacks=1` gallery read derives stacks inside its existing
current-library authorization transaction, using only the active images on the
returned page. The default gallery response remains unchanged. No model or
original media is opened, and no database rows or saved editorial groups change.

- A valid image perceptual hash is required: exactly 16 hexadecimal characters.
- Two reliable full capture timestamps must be within five minutes, with
  compatible timezone information, and hash Hamming distance at most six.
- If both capture timestamps are unavailable, require the same uploader and
  upload-batch identity plus the stricter Hamming distance of at most two.
  The UI calls this **同批导入 / Same upload**, not a capture-date claim.
- A known capture timestamp is not replaced with receipt time to join an
  undated image. Date-only metadata does not establish a burst timestamp.
  Conflicting recorded calendar dates veto the same-upload fallback.
- Each new member must meet the criteria against every existing member. A
  chain of individually close images must not bridge unrelated endpoints.
- Videos, malformed hashes and uncertain comparisons remain separate.

Photo hashes and uploader/batch identifiers are never included in the response.
The result is bounded by the existing maximum of 100 gallery items.

## Optional wire extension

An opted-in gallery response retains every ordinary `items` entry and adds:

```json
{
  "photo_stacks": {
    "version": 1,
    "scope": "page",
    "groups": [
      {
        "id": "101",
        "cover_asset_id": "102",
        "asset_ids": ["102", "101"],
        "count": 2,
        "reason": "near_capture"
      }
    ]
  }
}
```

Only groups with at least two members are returned. Members are disjoint, belong
to the same returned page and keep gallery order. The stable group ID is the
lowest member asset ID; the initial cover is the first member in gallery order.
It is a representative, not a claim that automated quality scoring picked the
best photo. Reasons are `near_capture` or `same_upload`.

A client validates the complete extension before hiding any card. Unsupported,
missing or invalid grouping metadata must leave every image visible. Ordinary
receipt/history response contracts and search/story result views stay unchanged.

## Gallery interaction

The cover carries a visible count badge and an explicit expand control. Expanded
members can be opened normally, selected as the cover, or shown separately.
A gallery toggle reveals all photos. The original full media sequence remains
available in the viewer, including collapsed members.

Cover and separation choices apply to the current view. Account, library and
page-identity changes clear those choices; no private asset IDs are persisted
in browser local storage. These controls do not write shared curation or alter
another family member's albums or stories.

### Family trial after delivery

1. 在“照片与视频”打开有相似照片的一页，确认封面显示数量。
2. 点“展开”，逐张打开；返回后尝试换封面并收起。
3. 点“单独显示”或“显示全部照片”，确认原照片仍可打开。
4. 核对“拍摄时间接近”与“同批上传”的区别；记录错误分组供调参。
5. 切换资料库或刷新，确认本次临时选择清除，其他相册未变。

This trial requires the new API and client delivery. Older installed versions
show the ordinary gallery; the local source checks do not replace this trial.

## Delivery and follow-up

This initial contract groups each fetched gallery page. It does not claim
cross-page deduplication or hide members from pagination. Whole-library durable
stack indexing and persistent per-user overrides require a separate indexed
contract with consistent pagination, access revalidation and lifecycle handling.
The existing reviewed memory-group feature retains its editorial semantics.
TV's separate published Home catalog is not changed by this contract; TV stacks
need their own catalog projection and remote-control acceptance.

An expanded Web stack can release an individual member to its own card. The
phone's current-view **Show separately** action dissolves the whole suggested
stack. Both are temporary presentation choices, cleared on gallery reload.

Source checks, synthetic UI renders, signed app delivery, Windows deployment and
family acceptance are separate gates. This document does not authorize a service
switch, APK publication, photo deletion or model activation.

### Local source checks — October 19

The stack algorithm/route, ordinary library reads and duplicate-management
cohort passed 40 tests (18 subtests). The separate preparation/history/closed-app
cohort passed 46 tests (18 subtests), preserving the old history shape and the
reviewed route inventory. The final stack suite passed 16 tests (five subtests),
including extreme timezone dates remaining separate instead of breaking a page.
The focused generated Chromium journey passed,
including keyboard focus after rerender, lowest-ID member separation,
cover selection, full viewer navigation, invalid/unsupported metadata and
late library responses. Chinese/English phone and desktop screenshots were
inspected, including enlarged phone text and a generated valid cover image.
The focused Android cohort passed 60 JVM tests: four parser, eight gallery-store,
40 HTTPS and eight existing recovery cases, with zero failures/errors/skips.
The connected-app TLS/persistence boundary verifier also passed. The separate
unconfigured QA application and instrumentation APKs built successfully. The
explicit emulator UI run did not reach its gallery assertions: Android killed
the QA process for a startup ANR while the emulator and host were under resource
pressure. No native stack screenshots were produced, so phone visual acceptance
remains open. These are focused source checks rather than the complete
Android/hosted CI profiles.

These results use temporary generated data. They do not establish family-photo
similarity quality, hosted CI, a Windows rollout or a signed phone release.

### Combined API candidate qualification

Immutable source `966cf139aa621416a5a22b6b11cd40f299a75b55` integrates the
existing deployed search/upload guard source before packaging the gallery work.
Its full API profile passed **2,464 tests and 2,486 subtests**, followed by the
generated no-listener demo, with identical start/end commit and source hashes.
The seven immutable staging-package tests and the integrated generated Web
journey also passed. Chromium 151 rendered Chinese/English desktop and phone
layouts, including enlarged phone text.

The fixed API ZIP has 241 source files and SHA-256
`9dce639072302f0400648ad18c8bbf483c9beb3d677bbea1d456a5420be2b16c`.
The read-only inspector reconstructed it from the exact immutable Git source.
This proves source/package identity, not native Windows execution. Subsequent
documentation commits do not rebuild that artifact. Windows qualification and
cutover, full Android qualification, phone visual acceptance and signed OTA
delivery remain separate gates. No deployment or publication occurred in this
source preparation round.

### Visual-review integration qualification — October 19

A fresh read-only runtime check found the API had advanced to visual-review
source `3c2c48f`; GitHub main includes it through `1df9d89`. The later immutable
candidate `f2041c1c2cb554350112c9a163de39f4c8c0af91` integrates that source with
photo stacks. The earlier `966cf13` qualification remains evidence only for its
own artifact and must not justify replacing the newer deployed functionality.

The combined candidate passed **2,508 API tests and 2,510 subtests**, followed
by the generated no-listener demo, with unchanged source and commit throughout.
Seven staging-package tests and three generated browser journeys passed: photo
stacks, owner visual review and upload history. Synthetic enlarged Chinese
phone renders were inspected. The closed application has 174 registered routes,
including the original preparation read and the incoming owner-review routes.

The new fixed API ZIP contains 245 source files, SHA-256
`db603eb8c4f87f4daf2302c60ef94f66ddb6642ded2bef84b2afc6ea23c9af77`;
exact committed-source inspection passed. A separate generated nine-case
gallery qualification passes locally against the extracted package, including
Windows-style socketpair compatibility with ordinary network calls blocked.
This local result and read-only native syntax parsing do not establish a
Windows execution pass. Staging, temporary qualification task registration/run,
API cutover and phone signing/publication retain their separate operation gates.

### Native Windows qualification — October 19

The same immutable `f2041c1` package subsequently passed its authorized synthetic
Windows run under a temporary SYSTEM task. All nine gallery/preparation checks
passed: near-capture grouping, stricter same-upload fallback, different-batch
separation, preservation of every original item, owner receipt isolation,
foreign-library denials and safe processing-stage projection. Both child
processes proved the required Job membership, 2 GiB memory limit and eight-process
limit. Startup was limited to 10 seconds, the gallery fixture to 180 seconds,
with an 8 GiB free-memory admission floor and a five-minute task limit.

The initial Mac dispatch stopped before task registration because its encoded
command exceeded the transport limit. Read-only Windows reconciliation confirmed
the task and candidate did not exist. The unchanged hash-pinned registration
script was then staged privately and executed once through a short verified-file
bootstrap; the qualification was not replayed. Native exit code was zero, with
no output truncation or invocation error. All extracted inputs passed the final
integrity check.

The finished temporary task was removed after checking its exact definition;
all nine production task definitions remained unchanged. The run used generated
databases and fixtures only, without opening family media or production databases,
loading models, making application network requests, changing services or
publishing OTA. These results qualify this package on Windows; they do not show
that photo stacks are served by the live API or installed on a phone. API/Web
cutover, responsive-emulator UI acceptance and phone signing/publication remain
separate delivery gates.

### API/Web and phone delivery — October 19

PR #94 merged with all five hosted checks green. The API-only guarded rollout
preserved incumbent configuration, playback, reviewed people and relationship
artifacts, and schema `a0c9d2e4f817`. Four databases were backed up at the stopped
writer boundary and each copy passed an on-disk restore rehearsal. Independent
postflight verified all 245 source files, exact API listener identity, restored
nine runtime states, API settings and the other 78 task definitions. Independent
Mac trusted HTTPS checks matched the three changed static files and confirmed
anonymous gallery/preparation reads remain denied.

Phone v73 uses the same reviewed Android tree with production settings and the
original certificate/icon. Release lint/build, embedded profile checks and the
complete native/HTTPS APK readbacks passed. On the explicit emulator, the stack
controls at enlarged Chinese/English text, page-scope reset and independent
full-screen viewer checks passed. A direct stack-member-to-viewer traversal is
not part of that native test set; the generated Web journey covers its full
viewer sequence. Synthetic screenshots do not establish family-photo grouping
quality. No physical phone was installed or exercised by this rollout.

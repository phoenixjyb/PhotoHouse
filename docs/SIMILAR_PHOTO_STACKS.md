# Similar-photo stacks

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

These results use temporary generated data. They do not establish family-photo
similarity quality, hosted CI, a Windows rollout or a signed phone release.

# Independent saved memoir edition shelf

## Scope and contract

The whole-memoir reader now offers **阅读已保存的家庭版本** independently
of private AI jobs and the edition editor. A library reader with
`enabled=true, can_save=false` can list and freshly read editions even when
book editing and generation are disabled. Unavailable AI arrangement controls
are hidden from this reader-only view. The existing optional authenticated
HTTPS edition routes and wire fields are unchanged. The capability is still
controlled by the default-off C2 backend.

Metadata pages contain at most eight version receipts and no manuscript. Each
entry shows its ordinal, local saved date/time and source state in separate
text rows. Receipt revisions remain checked by the coordinator. Explicit previous/next paging replaces the visible page. A receipt or
list entry is never used as readable prose. Selecting a version fetches fresh
detail and clears prior prose before awaiting it.

The new independent decoder validates the selected edition/book/current revision,
the immutable metadata receipt identity, strict bounded manuscript fields and
contiguous chapter IDs under every current
ordered child story. It rejects foreign, duplicate, reordered and skipped child
or chapter IDs. The existing proposal-bound adoption decoder remains strict.
These client checks establish structure, not source truth: fresh server
membership and complete source-closure validation remain authoritative.

Current text supports a complete chapter directory, story labels, previous/next
navigation, unresolved questions and explicit local read-aloud. Saved AI wording
is labeled separately from original family accounts. No microphone, generation,
original-audio download, playback, save or automatic retry begins on opening.
Edition-bound original-source inspection is implemented in the next source increment; see [the inspector contract and qualification](ANDROID_EDITION_SOURCE_INSPECTOR_2026-10-07.md). A citation count alone is not an original-source read.

## State and input preservation

The shelf owns a separate read-only coordinator/repository and capability cache.
It never reads a private proposal or sends a save. Refresh rechecks capability;
old servers or disabled capability show unavailable without a fallback route.
Failed list/refresh drops metadata and prose; failed or changed/invalidated detail
cannot restore old prose. Each fresh request is fenced by account, credential,
library, session generation, book/child revisions and reader epoch.

Closing or backgrounding the selected version clears text and cancels its GET;
late results cannot repopulate it. Returning to the metadata list requires another
fresh read. Book/account/library invalidation clears the whole shelf. No prose
is persisted to disk. Chapter navigation or scope disposal stops read-aloud.

The editor's dirty/composing/rejected-input or uncertain-save state disables
shelf requests. Its frozen POST body/mutation and guarded exit remain intact.
Read-only cancellation never discards the editor's pending save.

## Qualification and delivery

Focused JVM qualification passed **86 tests**, zero failures/errors/skips:
7 shelf, 6 edition repository, 8 edition wire, 7 editor coordinator and 58
community/ConnectedStore tests. The wire tests reject malformed current chapter
scope; shelf tests cover reader-only admission, default-off capability, fresh
reads, failures, paging, cancellation and late account/source responses.

The UI fixture uses nine synthetic versions and a 24-chapter memoir, with book
editing and generation disabled. Chinese/English 150% font tests cover paged
metadata, direct last-chapter reading, explicit speech and stopping, source
invalidation, offline failure and unavailable capability. The existing two
editor/retry/keyboard journeys also exercise blocked shelf requests during an
uncertain save. Both independent shelf journeys passed again after the final
metadata-card layout and read-only AI-control polish. Debug lint passed with
0 errors and 5 warnings. Final Chinese/English list, pagination, directory,
reading and invalidation screenshots were inspected. These are four distinct
UI journeys with two final shelf reruns, not six unique tests.

Source checks used empty configured origins, JDK 17 and the existing offline
cache and emulator. No Windows operation, migration,
provider/model call, production signing, OTA publication or physical install
is part of this increment. C2 must remain off until all source-deletion types
have physical manuscript purge/replay and native restore qualification. Previously
released phone versions do not include this increment. These checks do not prove Windows,
real TTS/ASR quality or family acceptance.

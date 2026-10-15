# Phone shared memory groups

The protected photo/video detail view exposes “把回忆分享给相关照片” when the
explicit `photohouseMemoryGroupsEnabled` build choice and protected native access
are both enabled. The new property defaults to false. Home mode, anonymous TV
access, app startup and ordinary detail reads do not query group endpoints.

Opening the panel refreshes the first page of this item's original notes, then
checks group capabilities and reads the current group listing. Existing groups
hydrate original notes from every included item, preserving source attribution
and the latest returned revision. Linking a note sends only its ID, never a copy
of its title, text or audio. Other pages of notes remain available through the
existing per-photo memory reader; this editor offers only the refreshed first
page and sources already linked to loaded groups.

## Review and adjustment

Users can create a group, choose a theme, link original memories and select up
to 24 ordered media items. Manual choices come from the current gallery page,
loaded groups and returned suggestions. Videos can be included manually.
Suggestions combine recorded capture time and qualified image similarity; they
are not assumed to identify the actual event. They start unchecked and remain
anchored to the original image, without transitive expansion. Removing the
anchor from an existing group disables refresh until it is included again.
Excluded suggestions stay excluded on refresh; explicitly adding them manually
removes that exclusion. Removing a member also unlinks its notes in the draft.

The review screen shows the selected items and original sources. Saving requires
explicit confirmation. Theme, membership and source edits are frozen after the
request starts. An uncertain response keeps its exact mutation ID and body for
retry. A revision conflict preserves the draft while the user reloads the current
group and chooses whether to retain their changes for another review. A missing
or withdrawn group cannot be silently recreated. Leaving an unsaved or uncertain
draft requires confirmation; a save in flight cannot be dismissed through this
control. Backgrounding still clears private state.

## Scope and previews

The editor is bound to the current account, bearer token, library, visible item
and generation. Logout, account/library changes and backgrounding close it and
reject delayed reads, suggestions, saves and thumbnails. A denied group or
thumbnail read clears the protected parent screen. Drafts remain in memory only.
Thumbnail reads use the existing protected adapter, never a returned arbitrary
URL. Preview loading is lazy, capped at two concurrent reads and 44 cached
images of at most 2 MiB each; discarded bytes are cleared.

The existing [server v1 contract](../server/docs/security/MEMORY_GROUPS_V1.md)
defines all routes, bounded response shapes, authorization, ID-only storage and
e7 migration. The phone validates the same exact shapes, source membership,
canonical IDs and thumbnail routes. It does not call a model or infer missing
dates locally.

## Delivery

The local implementation passed 652 live-core JVM tests and 17 phone JVM tests,
debug lint (zero errors, six existing warnings), and unconfigured debug/test APK
assembly. Two generated API 36 emulator journeys passed, covering Chinese and
English at 150% text, reviewed suggestions, exact retry after a committed-but-lost
save response, keyboard focus, original attribution on another group member,
and manual removal followed by another edit. Rendered screens were inspected.
Recorded dates are formatted without shifting their written date/timezone.
Earlier failed fixture/build attempts remain separate from these final results.

Source/JVM checks and synthetic emulator review establish local behavior only.
The future release needs a pinned private build profile, appropriate version,
signature and separately authorized OTA publication. The live API needs e7
qualification, approved activation and current qualified vector coverage for
automatic suggestions. Manual grouping can work without vector services once
the storage feature is activated. Family calibration and physical Samsung/TV
acceptance remain independent. Shared-memory references are not yet used to
generate essays or memoir prose automatically.

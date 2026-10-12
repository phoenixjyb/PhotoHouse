# Phone memoir composition and saved-book editing

The phone memoir composer is an explicit way to collect existing saved stories
into a new memoir book, or revise an existing memoir that the current reader
may edit. It preserves the selected stories and their original content. Optional introduction dictation is available only through its explicit
voice controls; opening the composer does not start recording, transcription, or
other model work.

## Entry and permission checks

The shelf shows **Create a memoir from saved stories** only when the current
protected shelf response advertises `canCreate`. Tapping it starts a new
composer session with the current account, credential, generation, library,
and shelf request scope. The initial title and language follow the app locale
(`Our family memories` / `我们的家庭回忆`, `en` / `zh`). The panel itself does
not open or fetch anything on mount.

The store checks the scope again, fetches current collaboration capabilities,
then reads the books page and the first saved-story page. Creation is enabled
only if the fresh books response still grants `canCreate` for that library.
Saved-story candidates must be readable in the same library. A candidate’s
summary `canEdit` flag does not decide whether it can be collected: the memoir
operation is authorized separately, and selected stories can belong to other
family contributors. Collection preserves each saved story as-is.

## Editing a saved memoir

The saved-book reader shows **Edit memoir / 编辑回忆册** only for a parent
advertising `canEdit`. The action is bound to the rendered account, library,
reader request, book revision and ordered children. Unsent conversation words,
recording/transcription, pending AI work, source audio and unfinished editorial
work must be settled before entry. Detached reader controls cannot open an edit
or navigate while its composer is displayed.

Opening an edit reauthorizes the parent and freshly reads every selected story.
Only then does it populate the saved title, introduction, language and ordered
story selections. This uses parent edit permission independently of shelf
creation permission. Existing introduction dictation remains explicit:
Record → Stop and transcribe → Review → Add → Save. An untouched edit can be
closed immediately; changed words and selection changes require the existing
discard confirmation. Drafts remain transient and clear on backgrounding.

Users can remove or add readable saved stories, move them up or down, and revise
the book fields. An unchanged or reverted edit has no save action. Before the
first update, the store rechecks the exact base parent and all selected story
snapshots. A changed parent or source prevents the update and retains the draft;
there is no automatic overwrite or rebase. Parent conflict copy asks the user to
close and reopen to review the latest version.

Updates send the same book ID and base revision through the existing protected
save contract. An uncertain response freezes those values and the mutation ID;
retry replays the identical request without rereading the superseded parent.
This also recovers a request that committed before its response was lost. The
verified response must match the edited content, next revision and ordered child
snapshots. **Open saved memoir**, or closing a successfully saved edit, reads
the saved parent afresh and updates that book's shelf revision; it creates no
duplicate shelf entry. Cancelling an unsaved edit returns to the original reader.

This is Android source work. It adds no route, schema, provider activation or
TV change. Its signed release and family acceptance are separate delivery gates.

## Visual shelf and transient covers

Each current shelf page displays up to eight books with a protected cover or
local themed fallback, a 240-code-point introduction excerpt, story count and
media-entry total. The total counts story entries rather than unique photos.
The explicit Read memoir action remains reachable with enlarged text. Empty
pages have localized text; pagination keeps Previous and Next on separate,
wide controls.

The cover loader reads the existing protected thumbnail route sequentially,
with a 512 KiB per-cover limit. It never reads originals, child story bodies,
voice or provider services. Retry is explicit and requests only failed covers.
The transient bytes clear on composer/reader entry, shelf departure,
backgrounding or identity/library replacement. Late responses and denials from
obsolete shelves cannot restore previews or invalidate a replacement reader.
Decoded images have separate dimension/pixel bounds and are disposed when
removed. The UI rejects actions captured from detached or replaced cards.

## Draft and review

The composer accepts 1–24 distinct saved stories. Selection order is the
memoir’s story order; accessible Move up, Move down, and Remove actions make
that order explicit. The localized default title is already filled in; the user
may edit it, add an introduction, and choose Chinese or English. A title must
be nonblank and fit 512 UTF-8 bytes; an introduction may contain up to 6,000
UTF-8 bytes. Chinese is the default. Save is an explicit review action.

Each selected story is retained with its story revision, `selectionRevision`,
and `sourcePolicy` (which may be `null`). Before saving, the store fetches every
selected story again in the active library and requires the current story data,
revision, selection revision, and source policy to match the reviewed
selection. A changed or unavailable story prevents the save and leaves the
editable draft available for correction and review.

### Optional introduction dictation

Voice input is separate from opening the composer. Expanding the optional
introduction or editing its text does not query voice capabilities. The user
must explicitly choose **Dictate introduction**; only then does the app check
whether transcription is available. Recording and **Stop and transcribe** are
also explicit actions. The recognized words appear in an editable review field;
they are not inserted or saved automatically.

The introduction remains editable while transcription is pending. On **Add to
introduction**, the reviewed transcript is appended to the latest introduction
text with one newline separator, or used as the introduction when it is empty.
If the combined text exceeds 6,000 UTF-8 bytes, insertion is rejected and both
the current introduction and the full transcript remain available to edit.
Save stays blocked while voice capability loading, recording, transcription,
or an unconsumed transcript is active. The user can discard the voice input
explicitly; discarding the composition also clears its local voice helper and
draft.

The audio is transient input, not a family recording or memoir attachment. The
flow saves only introduction text when the user later chooses the memoir
composer’s explicit **Save** action. The voice helper is tied to the current
account, session generation, library, shelf scope, composer epoch, and helper
instance. Delayed recording or transcription callbacks from an old helper
cannot update a replacement composer.

## Save, retry, and opening the result

Save creates a new book with revision zero and a generated mutation ID. Once
submitted, the exact mutation is frozen. If the outcome is uncertain, **Retry
same save** resends that same mutation and ID; it does not make a second draft
or silently change the story order. Editing remains frozen until the result is
resolved.

Leaving while a save is in flight or uncertain requires an explicit choice.
The user can retry, stay, or leave and check later; leaving clears this
process-local draft and frozen retry data. Other unsaved composition work also
gets an explicit discard-and-leave confirmation. An authorization failure
closes the composer and clears its private state.

A verified success enters terminal `CREATED` state: the composer cannot save
again. **Open saved memoir** passes the verified parent ID to the existing
protected reader. That path fetches the parent book again before displaying it;
the composition flow does not prefetch child story bodies. When the user backs
out of a newly created parent that was outside the previous shelf page, the
reader returns to the shelf and reloads its first protected page so the new
book can be listed from current server state.

## Scope and local-state boundaries

The title, introduction, selected IDs and their reviewed metadata, and pending
mutation live only in the in-memory store. They are not restored after process
death. Store operations are fenced to the current account, credential identity,
generation, library, shelf scope, and action epoch. The panel also invalidates
detached controls when its rendered scope leaves composition. Delayed reads,
selection actions, retries, or an old panel cannot apply to a replacement
account, library, or composer session.

## Verification and delivery status

Accepted phone source `e157679` passed 161 focused core tests across the
composer, scoped introduction dictation, shared dictation, repository and
community store. Four generated composer journeys (English/Chinese, ordinary
composition and reviewed voice introduction) and six shared dictation journeys
passed on the API 36 emulator in 157.889 seconds. Enlarged-text renders were
inspected. The composer fixture uses a generated valid WAV and direct recording
helpers; one shared dictation journey separately exercises the emulator
microphone with a synthetic transcription adapter. Neither establishes a real
provider's recognition quality or physical-device acceptance. A source change
or passing local test is not evidence of release signing, installation, a live
service update, or family/device acceptance. Those remain separate delivery
gates, and this work does not deploy or change Windows runtime state.

## Saved-edit qualification (October 12)

The saved-edit slice passed all 822 live-core tests, 17 phone JVM tests, phone
debug/test builds and lint. Six generated API 36 journeys passed at 150% text
in English and Chinese, including unchanged cancellation, detached controls,
remove/add/reorder, a committed update whose response was lost, exact retry,
fresh saved-book reading and shelf revision replacement. The Chinese edit case
closes the saved editor; the English case uses Open saved memoir. Enlarged-text
edit renders were inspected. These are source/emulator checks; this edit feature
is not part of the already published v47 APK.

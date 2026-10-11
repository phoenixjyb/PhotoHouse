# Phone story and memoir chat navigation

## Reading and returning to the present

Story and memoir conversation history remains paged. The page label distinguishes
the latest messages from earlier messages. On an older page, **Jump to latest
messages / 跳到最新消息** requests page one directly. Newer/older controls remain
available within the eight-page limit. Navigation keeps the editable unsent draft
and does not submit a turn, create a conversation, start dictation or play speech.

The action binds the rendered account, session generation, library, reader,
target revision, conversation and displayed page. Memoir actions also bind the
book revision, ordered child-story identities/revisions and selected child.
The current page must still match, be idle and permit the requested direction.
The control's composition lifetime is checked before those state checks. A
retained callback cannot request history after the chat is folded, the user
switches to family contributions, or a replacement reader/thread is selected.
Reopening a panel creates a fresh control; it does not reactivate its old callback.

This concerns story and memoir chats. The main photo-search assistant has its
separate [conversation trail](ASSISTANT_TURN_TRAIL.md). Web already loads older
exchanges into a bounded history and offers direct latest-message navigation.

## Local evidence

Source `7d7b1ef` adds the control and guards. Four generated simulator journeys
pass in English and Chinese at 150% text size. Each goes from page one to page
three, returns directly with exactly one page-one request, preserves the composer,
and rejects hidden/detached latest and ordinary page callbacks. They also assert
zero conversation creation, submission or transcription. Bilingual story and
memoir screenshots were inspected.

The first screenshot helper selected two Compose roots and was corrected to
capture the actual reader surface. The hidden-memoir callback test then reproduced
an extra request before the lifetime guard was added. A later story fixture
timeout came from its delegated story-list overload; explicitly wiring the
theme-capable overload corrected the fixture. The final four-journey run passed.
These failures were not treated as successful qualification.

Phone debug assembly, AndroidTest assembly and lint passed. The checks use
generated data on an emulator, without a signed release, live server or family
account. Signing, OTA publication and family acceptance remain separate.

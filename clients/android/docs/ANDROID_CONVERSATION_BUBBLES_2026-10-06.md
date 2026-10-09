# Story and memoir conversation bubbles

中文摘要：故事与回忆册的连续对话使用独立消息气泡。你的讲述靠右显示，助手回复靠左显示；完整文字、参考线索、追问、保留为回忆和朗读控件继续可用。

## Source change

Base: `88230cd75de20b99ec368d0df2d544b932b9469a` on `codex/phone-v29-candidate-20260929`.

`MemoryCommunityPanel.kt` shares a private Compose message container between the story and memoir readers. User messages occupy 94% of the available width and use the theme's primary container; assistant messages use the full width and a neutral surface. Both wrap complete text without a preview limit. Speaker labels remain explicit.

The change retains existing input submission, source expansion, follow-up questions, story-message preservation, and reader speech controls. It does not change the store, wire contract, language default or audio ownership.

## Verification

The reused API36 emulator `emulator-5558` ran two synthetic journeys:

- `savedStoryCommunitySubmissionChatAndProposalStayReviewOnly`: passed in the final run, together with `:connected:lintDebug`.
- `memoirChatKeepsItsBookThreadAndEditableDraftAcrossStories`: passed in the preceding run. No memoir implementation changed after that run.

Assertions bind the reply and the preserve-message action to the appropriate speaker container. Both journeys retain their existing submission, thread, source, editable-draft and speech checks. The story test's outdated stop-toggle expectation was updated to the existing pause toggle and separate stop button; production speech behavior did not change.

Root inspected story and memoir Chinese captures at 150% text scale. Long user text wraps and the assistant's questions, source expansion and read-aloud controls remain visible. English rendering was not checked for this change.

These checks use synthetic services and establish source/emulator evidence only. No release build, signature, OTA publication, live AI response or physical-device acceptance is claimed. This source belongs to the next phone release; the frozen v42 artifact and its publication scope remain unchanged.

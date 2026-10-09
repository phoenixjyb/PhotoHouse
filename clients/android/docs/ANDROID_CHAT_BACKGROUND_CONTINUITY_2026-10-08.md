# Android chat background continuity

Story and memoir chat panels explain their context window in English and Chinese. Replies use the current story or memoir materials, the current question, and up to seven earlier exchanges in that conversation. Earlier messages remain readable, but are not automatically included. Add important background to the current question.

When Android backgrounds the app, `ConnectedStore.background()` invalidates local request generations and cancels client coroutines. It does not call the remote job cancellation endpoint for story or memoir chat. An accepted queued turn may continue remotely. On reopening a story or memoir, the app reloads the conversation list and turn history, then checks the pending job associated with the queued turn. The JVM regression `acceptedStoryAndMemoirChatsRecoverFromFreshHistoryAfterBackgroundWithoutRemoteCancel` exercises this with synthetic server history and confirms that recovery neither cancels the remote job nor resends the turn.

There is an uncertainty window if backgrounding cancels the client POST before the app learns whether the server accepted it. Local pending chat state and draft text are cleared with the protected UI state, and this flow does not promise automatic resending. Reopen the story or memoir and inspect the refreshed conversation history. The conversation selected before backgrounding is not preserved; reopening selects the server's first listed conversation.

At 150% font scale, the memoir composer brings its focused input and Send row into view when the software keyboard opens. Story navigation stays hidden while the keyboard is visible. The current chapter question is inserted as an editable draft; it is not sent until the user explicitly taps Send.

## Source checkout verification

The source `MemoryCommunityStoreTest` XML reported 59 tests, 0 failures and 0 errors, including the background-recovery regression. The source Android UI checks covered three journeys on a synthetic API 36 emulator: the current story context-window journey passed 1/1 after the context copy was shortened, and the Chinese and English memoir chapter-question journeys passed 2/2 with the final copy and keyboard behavior. The memoir book-thread journey passed 1/1 after the Send-row fix but before the final context-copy shortening, so it is recorded as earlier evidence rather than part of those three current journeys.

The source Gradle run compiled the changed production and Android test sources. A forced fresh connected lint run completed with 0 errors, 5 existing warnings (ExifInterface, target SDK, Compose ModifierParameter, SwitchIntDef, and monochrome icon) and 1 informational autoboxing issue; none points to the changed panel. UI tests used injected synthetic APIs, and the two chapter journeys temporarily enabled software-keyboard display on the test emulator, restoring its prior setting in `finally`.

These are source-checkout tests and renders. Candidate JVM, compile, and lint results are recorded separately in the candidate import ledger. No backend, live endpoint, release packaging, signing, publication, real-device or family acceptance is included in this evidence.

## Scope record

The exact source pin and file blob hashes are recorded in the candidate source import ledger. The imported files are the story/memoir panel, its Android UI test, the connected-store regression test and this note. The test fake echoes the requested book revision in chat responses; timeout diagnostics remain, and temporary bounds logging is removed.

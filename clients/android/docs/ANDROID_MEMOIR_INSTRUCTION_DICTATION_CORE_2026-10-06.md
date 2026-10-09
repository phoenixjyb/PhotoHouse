# Android memoir instruction dictation core

`MemoryBookNarrativeDictationStore` adapts the existing in-memory `MemoryDictationStore` for the memoir instruction editor. The caller must explicitly call `open()` after the user chooses dictation. Opening requires the assistant feature gate and a valid current memoir reader scope; it then asks for assistant capabilities. Construction performs no request or microphone work.

The helper binds the store to account ID, bearer object identity, library, reader generation, memoir ID and revision, ordered child IDs and revisions, and scope ID. It checks that binding before and after both capability and transcription requests. If the reader scope changes, it closes the matching old store, clears the exposed state, wipes/cancels its transient dictation state, and cancels the pending operation. A late 401/403 closes only its own binding and reaches the caller's denial callback only while that same binding remains current.

The UI can collect `state` and use the returned store for the existing recorder lifecycle. `insertTranscript` calls the editor callback only for a current nonblank transcript; a rejected insertion leaves the transcript intact for review. An accepted insertion consumes that transcript. No instruction or audio is persisted, queued, or sent to a generation job by this helper. Raw WAV ownership and wiping remain in `MemoryDictationStore`; remote transcription uses the existing assistant API and request ID behavior.

`hasUnfinishedInput` is true during capability loading, recording, transcription, or while a transcript remains unconsumed. An empty idle helper does not block memoir actions. The caller still owns UI lifecycle and passes the `MEMOIR_INSTRUCTIONS` purpose to its recorder component.

The focused unit tests use synthetic API implementations and coroutine gates. They cover explicit opening and capability gating, insertion rejection/acceptance, and stale-scope responses. They do not establish microphone, device, service, or family acceptance.

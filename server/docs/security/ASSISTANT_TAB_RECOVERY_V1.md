# Assistant tab reload recovery v1

The signed-in WebUI can recover the status of one ambiguous assistant turn after
the same tab reloads. It stores only a bounded, versioned pointer in
`sessionStorage`:

```json
{"version":1,"request_id":"canonical-uuid-v4","account_id":"…","library_id":"…"}
```

The pointer is written immediately before a turn POST. It contains no question,
transcript, recording, result, conversation context, credential, or origin. The
browser validates the exact field set, value types and bounds, canonical UUIDv4,
and serialized size before using it. Malformed, oversized, or unknown-version
entries are discarded. Storage read/write failures leave the current-page
pending and receipt behavior available; reload recovery may be unavailable.

On startup the client keeps the pointer while authentication is unresolved. Once
the server confirms the account and available libraries, recovery proceeds only
for the same account and library. If the stored library remains available, the
client selects that library for this restore. An account mismatch or unavailable
library clears the pointer without a receipt request. Explicit logout and
library/account changes clear it as well.

The assistant panel opens with an explicit receipt check. There is no automatic
receipt GET, turn replay, transcription, recording, or microphone start. While
the outcome is unresolved, sending and recording stay blocked; the existing
Clear control becomes **Acknowledge and start fresh**. A receipt GET reporting
`received` keeps the pointer and offers another check. A terminal receipt clears
the pointer and reports status honestly. A successful receipt does not restore
the reply, result cards, or search context; the user starts a new search if
needed. A missing receipt or lookup failure remains unknown until another check
or explicit acknowledgement.

The pointer uses tab-session storage and is not conversation history. Browser
session restoration can preserve it; explicit acknowledgement, logout and scope
changes remove it. See the browser [session storage lifecycle](https://developer.mozilla.org/en-US/docs/Web/API/Window/sessionStorage).
The server continues to enforce the existing authenticated account/library
receipt lookup and journal retention rules. This WebUI change
does not require a catalog migration or speech-provider change, and it does not
activate a service or qualify installed-device behavior.

## Local verification

The synthetic browser journey covers same-scope reload, GET-only recovery,
absence of duplicate turn POSTs, honest successful-receipt messaging, account
and library mismatch, malformed storage, logout clearing, and narrow/desktop
rendering. Recovery screenshots use a normal 1280×900 desktop viewport and a
390×844 viewport at 150% page zoom; checks confirm the recovery message and
actions are within the viewport and clear of the sticky navigation. Preview
tiles in this synthetic fixture can show missing-image placeholders; they are
fixture content and are outside this UI check. The test uses an in-process ASGI
bridge; it does not contact a live service or use family account data.

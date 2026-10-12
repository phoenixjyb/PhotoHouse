# Private conversation voice integration

This local slice joins the approved foreground voice controls to an owned private
conversation. It does not initialize Windows storage, enable a provider, change
services or publish an APK.

## One conversation, two input methods

A user selects or creates a private conversation and can continue it with typed
input through “继续聊天” without starting a microphone, or choose “在这个对话中语音聊”. The voice action returns to the central
assistant and starts the existing foreground listen → reply → listen controls.
The same account/library/thread revision owns each request. Pause/End, background
and context changes remain visible stopping boundaries. Capability loss stops an
active capture; denied workspace access clears protected caches. Switching or
deleting a selected thread clears its central text/audio and requires an explicit
selection before further private use, with no quiet fallback to v1. Ordinary memory dictation
and saving family text/audio retain their separate reviewed confirmations.

The phone reserves an immutable request ID synchronously before returning from
submission, so the voice controller can bind its next callback. It submits words
and a revision to the private turn API; it never supplies trusted search context.
An optional parent request header correlates a confirmed ASR receipt with the
submitted turn. Receipt metadata is accepted only from matching server headers;
private ledger completion does not imply that the separate audit journal is on.

## Pause and recovery

Cancelling local waiting cancels only the exact owned operation, retains the
question and request identity, and fences late callbacks. It does not assert
that server computation was cancelled. The client uses GET to inspect that
request. A recovered response cannot navigate, play speech or restart capture
automatically; the user reviews it before choosing another foreground action.

If the request never reached the server, GET may remain unavailable. Explicit
abandonment explains that the server may still complete the earlier request,
preserves the question and unsent draft, and creates a new conversation only
after acknowledgement. It does not delete history or resend the question. A confirmed failed/interrupted
request also retains its question for review; explicitly entering that owned
conversation again clears the central blocker before a new user submission. Lost
thread creation first checks the same owned thread ID; a manual retry reuses that
identity instead of creating another conversation.

## Acceptance

- Preserve one synchronous identity across capture, submission and recovery.
- Keep the existing v1 route when no private conversation has been selected.
- Bind selected private context to account, library, generation and thread.
- Correlate ASR receipts without claiming journal availability from ledger state.
- Fence late responses after Pause/End, scope changes and cancellation.
- Pause on recovered, clarifying, unsupported and unconfirmed responses.
- Preserve editable drafts and require deliberate abandonment or creation retry.
- Verify source, synthetic transport, simulator UX and live family use separately.

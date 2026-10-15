# Private assistant turns and continuation

Implementation contract for the next local slice. This extends the default-off
private workspace API without changing the installed assistant v1 contract.
It does not authorize a live database initialization, migration or deployment.

## User experience

A signed-in user can create a private conversation in an authorized library,
search, refine that search and continue later. A library owner cannot read another
member's private conversation. Returning to history shows saved text; opening a
result requires current authorization and an unchanged result binding.

An uncertain response pauses voice progression. The client checks the existing
request by GET rather than sending the turn again. History recovery never repeats
a navigation or playback action automatically. Personal history retains text and
bounded references for 30 days; input audio remains transient.

## Routes

All routes require current library membership, the exact account owning the
thread and explicitly admitted private storage. Existing browser CSRF/origin and
native bearer rules apply. Responses use the existing privacy headers.

Thread creation also accepts an optional client-generated `thread_id`. Reusing
that exact ID in the same account/library returns its existing thread, so an
uncertain creation does not require another POST with a new ID. A foreign thread
under that ID is never adopted. Existing library-only creation remains supported.
Thread detail adds `latest_request_id` (nullable), and each saved exchange exposes
its own `request_id` for authenticated lookup; these IDs grant no source access.
It returns the latest 20 complete exchanges and a `has_older_exchanges` boolean,
keeping the bounded response below 240 KiB without truncating saved text. Earlier
exchanges remain subject to the same retention policy and can be read through
[explicit, revision-bound older-history pages](PRIVATE_ASSISTANT_HISTORY_V1.md).

### Submit one turn

`POST /assistant/workspace/v1/threads/{thread_id}/turns`

```json
{
  "library_id": "example-library",
  "request_id": "11111111-1111-4111-8111-111111111111",
  "expected_revision": 0,
  "text": "找照片"
}
```

The client supplies neither search context nor assistant replies, cards or
effects. Text has a 1024-byte UTF-8 limit; JSON has a 20 KiB body limit and the
existing three-second receive bound. IDs are canonical version-4 UUIDs. Revisions
are integers, excluding booleans.

A completed response has this envelope:

```json
{
  "version": 1,
  "thread_id": "22222222-2222-4222-8222-222222222222",
  "request_id": "11111111-1111-4111-8111-111111111111",
  "status": "completed",
  "revision": 1,
  "recovered": false,
  "error": null,
  "result": {
    "version": 1,
    "kind": "results",
    "reply": "找到 0 项。",
    "context": null,
    "filters": null,
    "items": [],
    "total": 0,
    "has_more": false,
    "effect": null
  }
}
```

The result follows the existing strict assistant v1 result grammar. The example
illustrates the envelope; real search contexts and result items come only from
the protected discovery engine.

### Read the existing request

`GET /assistant/workspace/v1/threads/{thread_id}/requests/{request_id}?library_id=example-library`

It returns the same envelope. `status` is `pending`, `completed`, `failed` or
`interrupted`; `result` is null except for a completed request. The envelope
always has `recovered: true`. Completed cards are hydrated only after source and
membership revalidation, and their `effect` is always null on readback.
An earlier `open` result is normalized to `results` with a choose-to-open reply
when recovered, keeping the installed result grammar consistent. A completed
request's `revision` is its committed exchange revision; if another device has
advanced the thread, a follow-up at that old revision conflicts until refreshed.

The envelope always has `error`, null unless the request failed or was
interrupted. Failed/interrupted responses have a fixed, safe `error` code. They
do not expose stack traces, credentials, provider output or storage paths.
The current thread revision accompanies pending and failed responses. Deleted,
expired and foreign threads/requests return the same unavailable response.

Repeated POST with the identical request identity reads its existing state; it
does not regenerate. A changed text, revision or thread under the same request ID
conflicts. Different requests cannot generate concurrently in one thread.

## Durable state

The isolated workspace schema adds a request ledger and server-owned thread
context. A request reserves the thread revision with a 90-second lease before
computation. Completion atomically records the exchange, result summary, context
and new revision. Late or cancelled computations cannot commit after their lease
expires or fails. Only expired pending leases are reconciled as interrupted;
starting another app instance must not interrupt a live request.

Persisted summaries omit hydrated media metadata, thumbnails, raw audio and
credentials. A saved result contains bounded text, filters, ordered source IDs,
source binding/fingerprint and an optional read-only effect descriptor. GET
recovery revalidates those IDs; it never treats their storage as authorization.
Exchange/request/context expiry is fixed to the request's original timestamp.
Later conversation activity cannot extend an earlier input's retention.

Schema evolution is explicit and offline. Opening a v1 store must not migrate it
or create missing files. Existing history and preference interfaces retain their
shape. The receipt journal remains separate; a journal-finalization failure does
not cause a committed exchange to be generated again.

The source-only operator command `server/scripts/prepare_assistant_workspace.py`
requires exactly one of `--initialize PATH`, `--upgrade-v1 PATH`, or `--inspect
PATH`. Initialization is exclusive; upgrade validates the isolated v1 identity
and requires stopped writers and a private backup. Inspect uses a read-only
SQLite URI and returns aggregate metadata, never input text, account IDs or
source references. Paths are canonical local files, not SQLite URIs. This command
does not start services or enable runtime configuration; live execution retains
its operation-specific authorization gate.

## Personal presentation

The first applied preference is response language (`zh` or `en`). Other stored
preferences remain visibly unsupported until their presentation adapters exist.
Capabilities retain the existing boolean fields and may additionally declare
`applied_preferences`, a list currently limited to `locale`. No preference can
change library permissions or admit a model/provider.

## Acceptance

- Isolate accounts, libraries and threads, including owner/member combinations.
- Revalidate membership and result bindings before follow-ups and recovery.
- Test concurrent reservations, changed retries, uncertain completion, expiry,
  cancellation, deletion and replay suppression of client effects.
- Refuse malformed input and storage without implicit file creation/migration.
- Verify language preference on grounded replies; retain unsupported flags.
- Keep current assistant v1, ordinary dictation, explicit voice controls and
  default-off runtime behavior compatible.

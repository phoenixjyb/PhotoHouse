# Selected-story local model adapter

[`LocalSelectedStoryProvider`](../server/backend/app/access/selected_story_local.py)
is a default-off, asynchronous adapter for the existing selected-source story
operation. It sends one bounded structured narrative request to an explicitly
configured literal-loopback Ollama-compatible generation endpoint. It adds no
agent loop, tools, source lookup, persistence, publication, model installation,
provider discovery or automatic retry. The application still owns the selected
snapshot, citations, authorization, expiry and explicit Save.

This is source integration tested with synthetic HTTP and native-owner fixtures.
No installed model, native stop mechanism, Windows service, GPU capacity or
family device is qualified by those checks.

## Explicit binding

Construction requires a URL and model identifier. `enabled` defaults to `False`.
The only accepted URL forms use `http://127.0.0.1:<port>` or
`http://[::1]:<port>`, with an optional `/api/generate` path. Ports must be in
1–65535. Hostnames, alternate IPs, credentials, query strings, fragments and
other paths are refused. No DNS lookup or proxy configuration is needed.
The model identifier is explicit and bounded; there is no default model.

Enabling the adapter additionally requires an injected trusted native owner
with `async stop_and_reconcile(scope)`. Provider construction performs no I/O.
There is no settings, environment or staging configuration that selects it.
The existing `create_app(selected_story_provider=...)` injection can bind it;
the independent prepare-API and Web-UI flags both remain off by default.
Enabling one boundary does not enable the others.

A future reviewed host binding has this shape; it is not an activation recipe:

```python
provider = LocalSelectedStoryProvider(
    configured_loopback_url,
    configured_model,
    enabled=True,
    native_owner=qualified_native_owner,
)
# Pass provider through the existing protected app injection only after the
# separate native qualification and activation decisions. No binding is default.
```

Literal loopback establishes a routing restriction, not local inference proof.
Before household use, verify the exact server/model and any helpers execute
locally without cloud routing or fallback, and qualify their retention, resource
ownership and crash/restart behavior. A local server can itself forward work;
a model label or echoed response model name cannot rule that out.

## Bounded request and response

The adapter accepts only the already-authorized narrative bundle version 3
whose ephemeral operation UUID matches its exact `PreparationScope`. Saved
story/book and companion inputs are refused before HTTP. It detaches and
validates the input using the existing six-chapter/24-media source bounds.

Both async and existing sync narrative paths use the same pure
`_generation_payload` helper for the safety prompt, closed schema and generation
options. It preserves family-note, family-edited-caption and AI-caption status;
source text remains untrusted data. The async request has no source-discovery,
file, URL-fetch, shell, save or sharing capability. The operation UUID header is
only host correlation, never a native acknowledgement or authorization grant.

Requests are capped at 128 KiB. The async total timeout is the lesser of the
remaining host work deadline and the configured timeout (45 seconds by default,
at most 60). Response reads are capped at 128 KiB; encoded/compressed responses,
redirects, non-JSON content and mismatched lengths are refused. HTTP clients use
`trust_env=False`, `follow_redirects=False`, and identity content encoding.
There is one request attempt and no alternative provider.

Strict UTF-8 JSON parsing rejects duplicate keys and NaN/Infinity constants. The
response must match the configured model, finish normally, and contain bounded
narrative JSON. The existing validator checks exact chapter order, source
membership, text limits and required human review. It does not establish factual
truth; citations and metadata are assembled from the host snapshot afterward.
Errors expose only fixed categories and a fixed message, never provider bodies,
source words or endpoint details. No request/result cache or metrics containing
family content is added.

## Native work ownership

One adapter instance permits only one unsettled call. It retains a small
scope/settlement record until cleanup is proven. It does not hold source bundles
or generated prose in that record. Repeated cleanup for the last settled scope
is idempotent and cannot release a newer active scope.

The operation owner cancels/fences its async provider task before cleanup. The
adapter waits for its HTTP work to unwind, then asks the injected native owner
for proof. **Every dispatched request needs exact `True` from that owner, even
when HTTP returned `done: true` and valid JSON.** A cancelled Python task, closed
connection, completed response, model unload request, model-list query or root
PID exit alone is not proof that all native work for the scope stopped.

The native owner is trusted host code, not a model-produced receipt. It must
correlate the exact operation with the execution it owns and reconcile all work
and helpers within its authority. This adapter invents no native cancel endpoint
and never stops or restarts a shared model service. Native-owner implementation
and qualification remain separate. The new [process owner](SELECTED_SOURCE_STORY_NATIVE_OWNER.md)
is default-off and proves only its private process tree. This adapter refuses
that containment-only owner as direct endpoint proof; a qualified provider-to-process
binding is still required. No always-true owner is supplied in product source.

False, exceptional or overdue cleanup retains ownership. The application
quarantines its shared admission gate and does not publish a result. Explicit
reconciliation can retry proof without repeating generation. Late proof may
release the resource, but cannot revive cancelled words or clear the gate's
sticky quarantine. An interrupted cleanup waiter does not abandon the retained
cleanup task. Replacing an owner/gate after native reconciliation is a separate
host decision; constructing a fresh adapter is not crash recovery proof.

## Evidence and remaining gates

- [Adapter tests](../server/tests/security/test_selected_story_local.py) use
  `httpx.MockTransport` and bounded synthetic async streams, never a listening
  server or installed model.
- [Lifecycle tests](../server/tests/security/test_selected_story_local_lifecycle.py)
  connect the adapter to the actual operation/admission owners and synthetic
  snapshots to exercise overlap, source changes, cancellation and retained
  cleanup.
- The existing [story acceptance contract](SELECTED_SOURCE_STORY_ACCEPTANCE.md)
  still requires the frozen manual-versus-assisted benefit comparison. A valid
  schema is not model quality or a measured family benefit.

Exact native model/locality, stop/restart/retention proof, cross-process GPU
coordination, latency/quality, ASR/TTS, device acceptance and deployment remain
separate. The ordinary CPU profile remains model-free and default-off.

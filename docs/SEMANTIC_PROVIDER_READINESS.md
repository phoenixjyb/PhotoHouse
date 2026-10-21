# Provider-only semantic readiness

Semantic search remains OFF. This optional operator check probes an existing local
provider without starting it or enabling an API route. It does not establish
process ownership, library authorization, index/policy coverage, model relevance,
service recovery or activation acceptance.

## Explicit invocation

With no arguments, `server/scripts/semantic_provider_readiness.py` emits an inert
JSON plan using only the standard library. It reads no private files, imports no
PhotoHouse runtime or optional model package, and opens no socket.

An explicit check requires an absolute private semantic configuration and the
canonical configuration SHA-256 from a separately reviewed operator record:

```sh
python server/scripts/semantic_provider_readiness.py --check \
  --config "/absolute/private/semantic.json" \
  --config-sha256 "<reviewed-64-character-lowercase-hex-digest>"
```

The digest covers sorted, compact JSON, UTF-8, `ensure_ascii=False` and
`allow_nan=False`; it is distinct from a file-byte hash. Do not generate a trusted
pin by blindly accepting a document at execution time. The private configuration
loader checks the actual document against this pin before credential reads.
Existing configuration callers keep their previous behavior when no document pin
is supplied. Private path, permission, token, endpoint and joint-binding checks
still run normally.

The check accepts an exact owner-pinned 768-dimensional local encoder. It makes
one fixed synthetic encode request through the unchanged authenticated protocol,
then checks current pinned configuration and credential-backed runtime again.
Wrong binding/query/checksum, timeout, unsupported input or a changed configuration
or credential refuses readiness. A provider 422 is never counted as vector
readiness. Reviewed phrase-only and older 512-dimensional providers are outside
this check's scope.

## Evidence and limits

A successful report contains bounded identity/check fields and marks its scope
`provider_only_synthetic_protocol_check`. It includes neither private paths,
endpoint, bearer token, phrase nor vector. Failures use fixed sanitized codes.
There is no receipt-file write, model loading/download, listening socket, database
connection, index/policy payload read, retry, provider substitution or service
control. The existing loopback encoder's at-most-two-second timeout applies to
the single network exchange; filesystem work is not a hard process deadline.

A ready response is point-in-time protocol evidence from the configured responder.
A deployment controller still needs reviewed native process ownership, executable
and package pins, a bounded startup/shutdown/recovery plan, protected relevance
and latency checks, immutable index generation/refresh/retirement, rollback and
explicit activation authority. Preserve every existing live wrapper/route when
preparing a later API deployment. These source tools do not reserve a Windows
window or manage another session's processes.

## Source qualification

Source `265034e` passed the complete API profile (2,989 tests / 3,717 subtests plus
the generated no-listener demo), with unchanged source throughout the receipt.
All ten archive checks passed, including extracted no-argument planning without
optional ML imports or checkout fallback. Focused fixtures cover pin mismatch
before credentials, a configuration-read race, credential/config changes during
the exchange, malformed responses, unsupported input and timeout redaction.
No native provider-readiness invocation or production activation is claimed.

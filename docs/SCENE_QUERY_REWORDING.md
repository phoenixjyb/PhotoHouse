# Rewording an unsupported scene query

An exact query outside the optional reviewed provider's mapping now has a
distinct recovery path. The Web workspace and Android client keep the original
scene description and unsent main draft, clear old result cards, and explain in
Chinese or English that the user can reword the scene. They offer an explicit
reload of the previous search conditions before another scene submission.

This improves refusal handling. It does not expand the set of supported phrases,
translate a query, infer dialect aliases, relax filters or approve activation.
The scene-search gates remain off by default.

## User flow

1. Start with a completed, authorized photo search with resolved conditions.
2. Explicitly submit a scene description within those conditions.
3. If the exact phrase is unsupported, the server saves a terminal failed
   receipt. No ranking, new result exchange or thread revision is created.
4. The client keeps both drafts, clears the pending marker after confirming the
   receipt, and shows the rewording prompt. Scene resubmission stays blocked.
5. The user selects the reload button. The client reads the thread and its
   latest completed request, checks the captured thread/revision and current
   access/source, then rechecks the latest reference before restoring cards.
   The reload calls no encoder and submits no question.
6. The user reviews the restored conditions, edits the description, confirms
   that those conditions stay in place, and explicitly submits a new request.

The restored cards belong to the previous completed search. They are never
presented as results of the unsupported description. Source/revision conflicts
keep recovery blocked; authorization failure clears scoped content. An edit
made while the reload is in flight is preserved. Starting a full new search or
switching thread/account/library clears the transient rewording state.

If the first response is lost, the existing request-ID recovery reads its saved
failed receipt without repeating inference. An outage, malformed provider
response, busy worker or timeout retains the existing unavailable/uncertain
flow. None is presented as a meaning-related refusal. Failure to durably save
the receipt also leaves the normal recovery path in place.

## Provider protocol extension

The original v1 request and successful vector response shapes are unchanged.
The local encoder adds `X-PhotoHouse-Semantic-Refusal: 1`. Only that opt-in permits
the provider to return HTTP 422 with exactly:

```json
{
  "version": 1,
  "error": "unsupported_query",
  "binding_sha256": "<configured joint binding digest>",
  "query_sha256": "<exact original UTF-8 query digest>"
}
```

The client validates strict UTF-8/unique-key JSON, the exact closed shape,
version type, matching binding and original query hash, JSON content type,
encoding/body bounds and its existing deadline/cancellation checks. A malformed
or mismatched refusal remains unavailable. An older caller that omits the
header receives the existing generic 503 response. Older providers may ignore
the header; generic failures do not become semantic refusals.

The reviewed wrapper checks its source, binding and caller guard before exact
mapping lookup. An unknown mapping raises the distinct refusal without calling
the inner encoder. Inner failures remain generic. The transport preserves its
authentication, one-worker lease, disconnect and two-second budget behavior.

After provider refusal, the API rechecks authorization and its current source
binding. Revocation and source changes take precedence. The direct semantic
endpoint returns the safe `scene_query_unsupported` error at HTTP 422. The v4
workspace instead returns its normal envelope at HTTP 200 with `status: failed`,
`error: scene_query_unsupported`, `result: null` and the unchanged revision, only
after the failed receipt is saved. No raw query is echoed in that envelope.

## Compatibility and delivery

The new workspace error enum is accepted only for a failed v4 receipt. Fresh and
recovered clients check its revision against the submitted request. Legacy
workspace negotiation cannot read the new enum; the server returns
`search_version_unsupported`. Older strict v4 clients reject an unrecognized
enum safely, so update clients before activating this provider path. Completed
v4 results and ordinary v1–v3 search responses keep their existing schemas.

This changes source files pinned by the composite provider recipe. Existing
composite bindings cannot be reused: prepare and qualify a matching binding
for the updated implementation before running it. No binding or runtime
configuration is rewritten automatically. See the
[provider contract](REVIEWED_SCENE_PROVIDER.md) and
[offline measurement guide](REVIEWED_SCENE_MEASUREMENT.md).

Generated protocol, API, Web controller/browser and Android store/wire checks
cover refusal, replay, explicit reload, draft preservation and scope changes.
These are synthetic results. Native model relevance/resources, live activation,
signed client release, dialect/ASR and family/device acceptance remain separate.

# Rewording an unsupported scene query

**Delivery status — October 20, 10:49 Asia/Shanghai:** this guarded-search source
is merged in PR #101 and API/Web source `b170a97` is deployed and verified.
Semantic search remains **OFF**; Android source is merged, with no new APK from
this release. The [release record](SEARCH_RELEASE_2026-10-20.md) separates shipped
ordinary-search safeguards from gated scene ranking and remaining quality/device
work. R40/R41 local-only statements below describe their earlier checkpoints.

An exact query outside the optional reviewed provider's mapping now has a
distinct recovery path. The Web workspace and Android client keep the original
scene description and unsent main draft, clear old result cards, and explain in
Chinese or English that the user can reword the scene. They offer an explicit
reload of the previous search conditions before another scene submission.

This improves refusal handling. It does not expand the set of supported phrases,
translate a query, infer dialect aliases, relax filters or approve activation.
The scene-search gates remain off by default.

## Exclusion admission and clarification (October 20)

The application now checks bounded English, Chinese and mixed exclusion cues
before visual vector reads, text encoding or restoring semantic scores. This
includes “not on grass”, “不在船上”, “没有人holding的phone”, common contractions,
and explicit exclusion phrases. Authorization, the current hard filters and
source binding are checked first. The semantic source binding includes the new
admission policy, so old score snapshots cannot bypass it. Quoted scene wording
receives the same guard; quotes are opaque only in an explicit literal-caption
search. The existing `scene_query_unsupported` failed receipt and explicit client
reload/resubmit flow apply without a new wire enum.

Ordinary v2/v3 planning checks exclusions before consulting an intent model.
The closed metadata form “find photos, not videos” (also “找照片，不要视频”)
compiles to the existing positive image filter. It requires an explicit positive
counterpart and a complete trailing media clause. Bare “exclude videos” does
not imply images: the catalogue can contain other MIME types. Reviewed-name
collisions, contradictions and unconsumed conditions still require clarification.
Existing explicit media/date corrections and filter-removal commands retain
their separate closed grammar.

An unresolved v2/v3 exclusion asks what should visibly appear and requests a
complete revised search. Private pending state retains the exact original input,
authorized source binding and digest of the previous context (including null).
It is omitted from public replies/history. A short answer, reload or expired
15-minute clarification cannot drop the exclusion or invoke a planner/encoder.
The previous filters/cards remain checked against current membership and source.
A complete new search runs normal validation and replaces the unresolved request;
it must restate any conditions the user wishes to retain. Expiry changes the
prompt rather than silently broadening the search.

The next admission round also guards common Chinese negative predicates such
as “不下雪”, “未下雪” and “没落在草地上”, apostrophe variants in contractions,
and zero/absence forms such as “zero dogs”, “0 dogs” and “minus the dogs”.
The same negative-clause policy is used for descriptive source matching: a
negative caption cannot become affirmative scene evidence. A separate
affirmative clause can still supply its own evidence. Literal quoted-caption
matching remains independent and keeps the original text.

Scene ranking separately refuses known strict-count and exclusivity forms,
including “exactly two”, “at most three”, “only dogs”, “alone”, “只有两个孩子”
and “最多两辆车”. It uses the existing scene rewording receipt, keeps the prior
scope/revision, and never encodes these requests or restores their old scores.
Ordinary v2/v3 planning also refuses unresolved strict conditions before asking
an intent model to select scene spans. Its private pending clarification retains
the exact request using the same guarded continuation flow as exclusions.
Ordinary positive counts such as “two dogs” remain approximate scene cues;
their admission is not evidence that the encoder understands or counts them.
No people-count absence is inferred from a reviewed-person filter. Descriptive
matching and semantic source-policy versions changed to invalidate old bound
results; no runtime configuration or model binding is rewritten automatically.

This is a conservative admission policy, not a complete negation parser. It
does not prove that a person, object or event is absent, infer negative evidence
from missing tags/detections, or qualify arbitrary language/dialect. Unrecognized
wording and scope ambiguity remain a reason to keep semantic search disabled.
The multilingual encoder's prior negation-quality failure is not repaired by
this guard; relevance qualification and family acceptance are still required.

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

## R40 local validation

The complete API profile on immutable `38f5f8d` passed **2,593 tests and
2,632 subchecks**, plus the generated no-listener demo. Its private invocation
receipt records identical start/end commits and input hashes. Packaged-source
imports include the new policy module. A text-only replay of the prior frozen
public-photo stress queries blocked all nine negative variants and admitted all
nine positive controls; it opened no images and called no model. This is
admission evidence, not new relevance measurement.

The Web controller suites passed 97 tests. The generated scene browser journey
passed eight checkpoints, with Chinese/English desktop and phone 150-percent
text renders inspected. Android phone debug Kotlin compilation and lint passed
(79 tasks); no emulator, installation, signed release or physical acceptance
was performed. Independent source review caught additional absence wording,
including “lacking”, “absence of”, “没看见” and “无红色汽车”; those cases now
have passing admission regressions.

This round is local source preparation only. No PR, push, deployment, Windows
service/model/configuration, live library, or semantic activation changed.
The semantic gates remain disabled by default, and activation remains blocked
on model relevance, broader language/clarification qualification and separately
authorized runtime and family/device acceptance.

## R41 local validation after Mac restart

Recovered the clean R40 worktree and completed this round on immutable
`50623f9`. The complete API profile passed **2,601 tests and 2,745 subchecks**,
plus the generated no-listener demo. The private receipt records identical
start/end commits and input hashes. The focused contracts passed 183 tests and
766 subchecks before the final added conversation test; the final eight-test
constraint suite passed 113 subchecks. These overlapping results are not summed.

The new 29 synthetic negative/positive pairs have the expected admission
behavior. Source-matching checks cover generated captions, edited captions and
family notes; failed scene receipts, empty cohorts, private v3 clarification,
short replies and old-policy ranking restoration have separate regressions.
English/Chinese Web journeys used real synthetic workspace responses with
ordinary v2 negotiation. Current native-modal desktop and 390-pixel/150-percent
text captures were inspected; full prompts fit without horizontal overflow.
Short replies keep the unresolved condition, with no automatic resubmission or
reload. Earlier harness-only DOM activation and hash-navigation failures are
retained privately and excluded from accepted visual evidence. No Android build
was repeated in R41 because client source did not change; no device was tested.

A text-only admission replay verified the frozen dataset identities and did not
open images or call models. In each of English, Chinese and mixed input, the
fresh benchmark admits 12/16 requests and refuses 4/16; the earlier regression
benchmark admits 24/32 and refuses 8/32. The refused requests contain unsupported
exclusions. In the separate negation stress set, all nine negative variants are
refused and all nine positive controls remain admitted. Refusal is recorded
separately from retrieval correctness: these counts do not improve the prior
encoder scorecard or establish new model relevance. Conservative cues may also
refuse lexical phrases such as “zero hour” or a negative temperature; wider
language/recall qualification is still open.

This round is committed local source only. No push, PR, deployment, Windows
service, model, runtime configuration, private family index or semantic gate
changed. Semantic activation remains blocked. The next qualification should
report admission coverage alongside ranking quality, retain every refused case,
and separately measure ordinary positive counts, relations and vague requests
before preparing any activation proposal.

## October 20 merge and API/Web delivery closure

The integrated release includes current gallery/upload main through PRs #99/#100
and was merged as `a4e3922` in [PR #101](https://github.com/phoenixjyb/PhotoHouse/pull/101).
Qualified source `b170a97` has the identical Git tree and passed all five hosted
jobs, the complete local API profile (2,647 tests / 2,764 subtests plus demo), and
eight focused scene-browser checkpoints. Native qualification and independent
native/Mac HTTPS delivery checks passed. See the
[dated release record](SEARCH_RELEASE_2026-10-20.md) for the preservation scope.

This closes the earlier local-only rounds' merge and API/Web delivery gates.
The ordinary-search exclusion/strict-condition safeguards are delivered; the
optional scene flow remains capability-gated with semantic search OFF. No new
APK or provider was published or activated. Refusal before encoding does not
establish reliable model negation, counting, relations or vague-intent relevance.

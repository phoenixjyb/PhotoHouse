# Search functional acceptance

This is the October 25, 2026 functional-completion plan. It separates user
journeys, privacy and delivery from the earlier performance qualification.
Latency is recorded as a diagnostic for this work. The frozen 2-second target
and its failed results are unchanged; a functional result must never be
reported as a pass of that qualification.

Semantic serving remains **OFF**. Source changes, generated tests and a
qualification component do not activate it, publish an Android binary or change
library access. Deployment and activation need their own reviewed decision.

## Acceptance matrix

| User journey | Required behavior | Evidence and remaining boundary |
| --- | --- | --- |
| Find text or quoted wording | Keep quoted text literal and retain every supported hard condition. Unknown wording asks for clarification. | [Bilingual grammar](BILINGUAL_SEARCH_REQUIREMENTS.md), joint-search and exclusion HTTP tests; no claim of arbitrary language understanding. |
| Combine people, dates, media, tags and places | Apply the complete authorized filter intersection, including explicit any/all people matching. Never turn an unknown date or person into a broader query. | [Joint search](ASSISTANT_JOINT_SEARCH_V2.md), parser, discovery and request-recovery fixtures. Coverage is library-specific. |
| Use a family relationship | Resolve only current reviewed identity and account/library/perspective bindings. Unbound or unauthorized relationships do not disclose a private graph. | [Private kinship](PRIVATE_KINSHIP_SEARCH.md) and protected people/kinship tests. Source adds no real identity or sharing grant. |
| Speak or type Chinese, English or mixed input | Preserve the same hard conditions and literal wording through supported openings, refinements and corrections. | Bilingual source/HTTP fixtures. Shanxi/Jin dialect recognition, ASR accuracy and learned cross-language relevance remain separate qualifications. |
| Rank photos by a vague visual description | Require explicit scene opt-in and a freshly reviewed photo scope. Keep hard constraints outside similarity inference and refuse unsupported exclusions/counts. | [Scene qualification](SEMANTIC_SCENE_QUALIFICATION.md), scene-refusal and protected semantic tests. Serving remains default-off; real relevance needs reviewed examples. |
| Correct or clarify a request | Preserve unresolved conditions and the current authorized scope. A short reply or recovery cannot silently discard an exclusion. | [Rewording](SCENE_QUERY_REWORDING.md), pending-intent and bilingual correction fixtures. No automatic query translation or identity inference. |
| Reopen a refused scene request | Recover the exact private draft and reword guidance, hide older cards, and require an explicit fresh scope read before another scene submission. | The negotiated projection below; store, HTTP, controller and browser regressions are required. It performs no search or model call. |
| Browse and recover ranked results | Keep exact rank order and finite presentation scores; bind continuations and recovery to the current query, source and authorization. | Semantic direct-API pagination and workspace recovery tests. The workspace scene view deliberately shows the first 20 matches and discloses that limit; it has no next-page journey yet. |
| Cancel, lose the connection or retry | Distinguish unconfirmed delivery from a confirmed refusal. Read receipts without resubmitting; preserve edits and discard stale cards after scope changes. | Workspace/controller recovery and cancellation fixtures. Cooperative cancellation is not proof that a remote model process was terminated. |
| Change membership, source or policy | Recheck access and source before releasing derived results and after provider work. Refuse stale bindings and retain a safe recovery path. | Semantic mutation, membership, postflight-policy and deadline tests. Recovering the owner's own input text is not a claim that an old result remains valid. |
| See incomplete coverage or no matches | Explain searchable coverage and omissions. An empty or partial result must not claim that an object/person is absent from the whole library. | [Eligibility contract](SEMANTIC_ELIGIBILITY_DESIGN.md), coverage HTTP/UI fixtures. Qualification-only omissions do not authorize production omissions. |
| Use the feature on Web or Android | Render clear controls, refusals, coverage and accessibility states; keep older clients compatible and disabled features disabled. | Focused Web/controller/browser checks and Android's separate release process. A build is not installation or family/device acceptance. |

The matrix is a set of checkable contracts, not a statement that every real-world
acceptance step has passed. Keep the source revision and actual test evidence
beside any delivery claim.

## Recovering a confirmed scene refusal

The private workspace already retains the submitted text of failed turns.
An optional thread-metadata projection uses that record; it introduces no new
database schema or browser persistence.

A client opts in on thread GET with
`X-PhotoHouse-Scene-Reword-Version: 1`. This is input metadata, so the request
does not require semantic serving, a provider or search version 4. Without the
new header the thread response is unchanged. Older servers can ignore it and
return their existing response; the new client accepts that legacy shape.
Unsupported/duplicate negotiation and use on other private workspace routes are
refused. Other route families keep their existing contracts; this metadata
header grants no search or mutation authority.

The opted-in response adds `scene_reword`, either `null` or a closed object
containing `version`, `request_id`, `revision` and `query`. It exposes only a
confirmed `scene_query_unsupported` failure belonging to the authenticated
account, library and thread at the current revision. The latest request is
selected across all statuses before checking expiry. A newer pending,
interrupted, differently failed, completed or expired request cannot revive an
older refusal. Invalid or oversized stored scene text is not projected.

On reopen, a confirmed cue prevents hydration of older completed cards. The
client restores wording only into an empty draft, preserves unsaved edits and
shows reword guidance. It confirms the cue and thread revision before
publishing that state. An explicit reviewed-scope reload checks the current
source and authorization before enabling a corrected scene submission; it does
not automatically execute the old query. When semantic serving is unavailable,
the recovered wording remains read-only and execution controls stay disabled.

The cue contains no result cards, people labels, filters or privileged context.
A source-only change does not delete the owner's own draft, while every later
result read/search retains its independent source and membership checks.
Private/no-store response headers and account/library switching rules remain
in force.

## Source, runtime and delivery records

At the start of this round, candidate `7910852` had a recorded full local CPU
API result of 3,524 tests and 4,221 subtests. That historical run does not verify
later edits. Each new change needs its own targeted checks and independent
review; hosted checks must match the exact published head.

The later Windows program using that source produced two complete index audits,
15 protected cases and nine English/Chinese/mixed HTTPS samples over an isolated
synthetic-account database. Recovered measurement copies and the native
completion component were reaccepted independently. They do not establish
family relevance, a production roster, Web usability or installation. The raw
warm timings were 4.718 seconds median and 5.094 seconds maximum; none met the
historical 2-second target.

The program's full qualification remains failed: historical local process-family
scans were partial, and later readback rejected the staged source archive at
its per-file guard after the Windows query had run. No successful readback or
offline pair was returned. A separate explicit release covers only current
known owned scopes, backed by the retained Job/source evidence and new local
observations. It does not repair historical receipts or prove global host
freedom. No operation is replayed by this document.

## Remaining completion work

- The independently reviewed refusal-reopen source checkpoint is committed. Its
  focused HTTP checks passed 8 tests / 14 subtests, controller checks passed
  26/26, and the generated browser flow passed nine checkpoints. These are
  local synthetic checks; hosted CI, deployment and device acceptance remain
  separate.
- Reviewed grouping delivery documentation and the Android page-local notice
  are integrated from two focused commits. Keep live schema/index, refresh
  scheduling and APK/family acceptance separate from source presence. See the
  [grouping delivery checklist](PHOTO_STACK_DELIVERY.md).
- Treat workspace scene pagination beyond the first 20 as an explicit remaining
  journey, rather than claiming the direct API's page support exists in the UI.
- Review representative multilingual result relevance, production coverage and
  omission treatment before any proposed serving activation.
- For a future newly reviewed operator only, resolve the readback archive-size
  contradiction with exact archive bytes/hash and unchanged guards for other
  files. No current limit, source pin or failed claim is changed or retried.
- Keep runtime configuration/rollback, deployment, activation, signed Android
  delivery and physical-device/family checks as explicit later decisions.

See [project status](PROJECT_STATUS.md), [the dated native checkpoint](SEMANTIC_SEARCH_READINESS_2026-10-24.md),
[the API/Web release snapshot](SEARCH_RELEASE_2026-10-20.md), and
[Android release preparation](ANDROID_RELEASE_PREPARATION.md).

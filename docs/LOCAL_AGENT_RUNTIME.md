# Bounded local assistant application boundary

PH-A1 adds an injected, default-off read-only orchestration path to the existing
assistant workspace. The application remains authoritative for authentication,
library membership, source selection, language interpretation, request ownership
and saved outcomes. This increment runs with deterministic synthetic adapters;
it installs or enables no Codex runtime, model, client feature or service.

The implementation starts from main
`a4e39221a3dab8ee84bacc7c9226e7b3a71b112b`, including the guarded exclusion
clarification contract added after the engineering guide's earlier source pin.
[PH-U0](LOCAL_AGENT_ACCEPTANCE.md) defines the product comparison.
[PH-A4](SELECTED_SOURCE_STORY_DRAFT_CONTRACT.md) defines a separate proposed
selected-source drafting contract; it is not implemented by this search lane.
[PH-A0 qualification](LOCAL_AGENT_QUALIFICATION.md) records a failed stock
runtime capability ceiling. This application boundary remains usable with
synthetic adapters; no real runtime is activated by that finding.

## Injection and negotiation

The ordinary `create_app()` constructs no agent supervisor. An isolated test
application explicitly injects `assistant_agent_runtime` alongside matching
access/discovery runtimes and a healthy v2 workspace. `assistant_agent_budget`
can tighten the fixed ceilings for synthetic tests. Production runtime/staging
configuration is unchanged.

An injected adapter implements:

```python
async def run(self, turn_input, tool_dispatch, invalidation):
    projection = await tool_dispatch('search_media', {})
    return {'outcome_handle': projection['outcome_handle']}
```

`turn_input` contains version 1, the original bounded `text`, and the account's
`locale`. It contains no credential, lease, account/library identifier, private
conversation corpus or trusted source context. `invalidation` is a host-owned
threading event. An adapter owning resources must implement
`async cleanup(scope) -> bool`; only `True` affirms that its owned resources
are reconciled. A false, failed or overdue cleanup quarantines new admission.
The deterministic, resource-free fixture requires no cleanup hook. PH-A2 must
qualify real process and provider ownership separately.

The existing turn POST negotiates exactly
`accepts: ["agent_media_search_v1"]` and
`X-PhotoHouse-Search-Version: 2`. Fresh requests cannot combine other profiles
or `memory_parent`. Recovery uses the existing GET and the same v2 header.
Neither a new endpoint nor a new result/error enum is introduced. Ordinary,
saved-memory and scene requests keep their existing paths.

Durable lookup precedes fresh profile, availability and admission checks.
An existing request keeps its original thread, text and expected-revision
collision rules. A compatible replay returns its owned interpretation, even
with changed acceptance fields or no configured agent. Incompatible search
versions retain the current refusal rules; they never trigger reinterpretation.

## Host outcomes and tools

`assistant_agent_tools.py` exposes exactly three operations:

| Operation | Exact arguments | Meaning |
| --- | --- | --- |
| `get_search_capabilities` | `{}` | Current bounded readiness; no finalizable outcome |
| `search_media` | `{}` | Execute the current host v2 query/context once |
| `inspect_current_results` | `{"outcome_handle": "…"}` | Revalidate that run's already selected outcome |

The only final selector is an exact object containing `outcome_handle`.
Handles are unpredictable and specific to one run. Extra fields, another run's
handle, or no successful canonical search fail. The model cannot supply a query,
asset ID, filter, reply, pending state, context or effect.

The immutable host outcome retains the complete canonical result and exact
private pending intent. Summaries and ordered typed media references use the
existing store grammar. Tools expose only a bounded projection: at most five
ordered previews with run-local item handles, available media/date fields and
256-byte caption excerpts; summary text is at most 1 KiB, and complete encoded
tool JSON at most 16 KiB. The projection reports truncation and cannot change
stored card order or completeness. Paths, URLs, private pending metadata and
full source corpora are excluded.

A repeated canonical search consumes another attempt but only revalidates the
same outcome. It does not replan. Source/member changes invalidate the result.
An ordinary open-asset result becomes a truthful choose-to-open result with
`effect: null`; the application performs no navigation or playback.

The existing vague-date, expiry and exclusion rules remain authoritative.
Unresolved exclusions retain their private guard after presentation expiry until
a complete fresh search. Both context-bearing and context-less clarifications
retain protected source checks. A zero result or infrastructure error never
causes a broader library search.

## Lifespan, admission and recovery

`assistant_agent.py` owns one nonqueued lane across every account/thread in one
application process. It registers a strong operation before awaiting
reservation. A matching transient duplicate joins that owner; conflicting
identity stays a conflict. Each HTTP waiter independently reconstructs its
response under its own current credentials.

The work budget starts immediately before fresh reservation: at most 60 seconds,
four domain-call attempts and one concurrent domain call. Rejected and repeated
calls count. Scope checks reauthorize membership and inspect the actual pending
workspace lease and request revision before/after protected reads and before
finalization. The facade preserves the shared cooperative read budget and keeps
all synchronous database work outside runtime awaits.

Navigation, disconnect or cancellation of the HTTP wait detaches only that
waiter. The lifespan owner retains accepted reservation/execution. Deadline,
shutdown or invalidation closes tool authority and fences late output. PH-A1
adds no public user-cancel operation and makes no hard I/O or provider-stop claim.

Finalizing closes domain calls before committing through `complete_turn`.
Its returned status determines completion; an interrupted row is not success.
An in-flight reservation or commit remains owned after a timeout. The HTTP
failure can be returned while the owner reconciles the original store outcome.
No known commit is undone and no ambiguous request is interpreted twice.
Journal/response failure leads to existing readback.

Request outcome and cleanup are separate. Admission remains occupied while
owned tasks or adapter cleanup settle. Cleanup targets ten seconds; uncertainty
quarantines the optional lane and retains ownership rather than admitting more
work. Lifespan shutdown invalidates outstanding operations and bounds its wait.
An API hard crash still needs the durable lease and PH-A0/native process/provider
reconciliation before enablement; an in-memory owner is not a restart-safe queue
or a multi-worker admission mechanism.

## Validation and delivery boundary

Focused suites are `test_assistant_agent_tools.py` and
`test_assistant_agent_workspace.py`. They use temporary stores, generated media,
real protected domain reads and deterministic injected adapters. The API profile
registers those suites and the staging allowlist includes both new source
modules. Final package checks must run against the committed candidate.

Use the locked Python 3.12 environment and run:

```sh
.venv/bin/python tools/verify_current_source.py
.venv/bin/python tools/check.py api
git diff --check
```

PH-A0 exact-build/local-model qualification, PH-A2 stdio/MCP integration, PH-U0
measured benefit, client delivery, native Windows evidence and family/device
acceptance remain separate. This source increment changes no database schema,
worker, runtime configuration, household data, release signing or deployment.

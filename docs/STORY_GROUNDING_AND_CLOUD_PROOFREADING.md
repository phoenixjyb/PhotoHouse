# Story name grounding and optional cloud proofreading

## Status and scope

This document describes the current source contract and private native
qualification. It does not report a live Windows rollout, a real DeepSeek
request, or family acceptance. The new role/name-grounding/cloud-preview UI is
not live; the current rollout was blocked before effects. The cloud setting
defaults off and is unconfigured. GitHub Actions remains paused.

Story refinement keeps original narration and audio intact. Local refinement
returns a separate proposal marked for review; it does not save or publish the
proposal. The current story worker v4 profile is
`asr_editorial_v12_grounded`. Its flow performs deterministic name grounding
before one local generation call. Public name repair is not delegated to a
separate model knowledge pass.

## Separate local model roles

The optional `photohouse.household_service_recipe.v2` recipe pins a story model
and an `agent_model` separately. The explicitly approved story-refinement role
is **Qwen3-4B-Instruct-2507**. Search and the Jude assistant retain the incumbent
`qwen2.5-1.5b-instruct-q4-k-m-trial` agent role. The new role pair and
name-grounding/cloud-preview UI are not live; the current Windows rollout was
blocked before effects. Search and grouping continue on their existing paths.

Both providers share the same native launch, private exchange and
`HostInferenceAdmission` instance. Their profile uses `llama-cpp-python 0.3.36`,
two CPU threads, zero GPU layers and an 8,192-token context. One shared 4 GiB
job cap and one-job admission serialize inference. The worker selects the
pinned agent model only after validating an `agent_decision_v1` request.
Saved-story and legacy story requests use the story model. Request text cannot
supply a model path, provider or fallback. Only the selected model is loaded;
the roles do not run concurrently.

V2 requires all three unique `--agent-model-*` launch options, distinct model
labels, paths and SHA-256 pins, two CPU threads, zero GPU layers and an 8,192
token context. The launch and resource-profile digests cover both model roles.
The original v1 recipe retains its single-model behavior and rejects agent-role
fields or flags. Qualification and cutover must bind the chosen pair explicitly;
an earlier single-model result cannot prove the two-role deployment.

Private native role-story qualification covered three cases: active
cancellation, real 30-second expiry and birthday-story generation. All three
completed in 134.468 seconds on a private SQLite copy. The production original
and retained draft were unchanged. Contextual spelling and repetition improved,
but the title remained imperfect. Treat this as bounded native qualification
only; editorial quality review, live rollout and physical/family acceptance
remain open.

## Deterministic name grounding

The offline package contains a bounded roster of 2,328 public singer labels
from Wikidata under [Wikidata's CC0 licensing terms](https://www.wikidata.org/wiki/Wikidata:Licensing).
The pronunciation table contains 26,703 Chinese-character readings, derived
from [mozillazg/pinyin-data v0.15.0](https://github.com/mozillazg/pinyin-data/tree/v0.15.0)
under MIT; its license text is included in the package. The transformation and
input hashes are recorded in
[`story-grounding-provenance.json`](../server/backend/app/access/data/story-grounding-provenance.json).
Both datasets are read from fixed local package files; grounding makes no
network request and sends no family data to prepare them.

Public singer spellings are corrected only when a unique phonetic catalog match
is found in an explicit context such as a singer/artist cue or a related song,
concert or performance phrase. Multiple matches remain ambiguous and are not
guessed. A correction is limited to that grounded text; the method does not
establish that a person attended an event or that any surrounding claim is
true.

Private household names are grounded only through authorized family context:
the currently reviewed person's canonical name and aliases. An alias is
treated as that same reviewed identity; no private identity is guessed from an
unreviewed resemblance. Ambiguous aliases remain unchanged. Grounding operates
on a copied input; the original story, transcript and audio remain intact.
Generated text is still a separate `needs_review` proposal.

## Optional cloud proofreading

Cloud proofreading is an author-only, explicit action on a saved story. Normal
local editing remains available, and preview works while cloud is disabled.
`RuntimeConfiguration` and `create_app` both default
`story_cloud_proofreading_enabled` to `False` and the provider to `None`.
There is no environment-variable discovery or credential field in the user
interface. Enabling it requires an operator to inject a provider and explicitly
set the enable flag; the application also requires its explicit access and
collaboration runtime.

The preview displays the exact outgoing UTF-8 JSON body, its SHA-256, and the
fixed public destination `https://api.deepseek.com/chat/completions`. It is
off and unconfigured by default. A send requires the author to inspect that
exact preview and give explicit consent for that individual send; there is no
background cloud send. When no provider is configured, the descriptor uses
DeepSeek and `deepseek-flash` as a
disabled preset; this does not mean a key is present or a request can be sent.
The [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)
documents the endpoint and current model identifiers. Before enabling a provider,
review the [DeepSeek Privacy Policy](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html?locale=en_US)
and the service terms that apply to the account. This integration does not claim
zero retention or anonymous processing.

Only the selected saved chapter prose is included in the request, in chapter
order. It excludes story title, story/chapter IDs, asset and source references,
photos, audio, conversation history and other linked context. Reviewed names
and aliases are replaced locally with opaque placeholders and restored locally
after a valid reply. Common URL, email, local-path and obvious API-key patterns
are removed. These filters are limited safeguards: other private content may
remain, and names/placeholders or public reference matches are not proof of
anonymity or factual accuracy. The UI requires the author to inspect the full
request; its consent checkbox starts unchecked.

The preview binds the actor, library, story, revision and source fingerprint.
It expires after 600 seconds, is held in a bounded process-local cache of at
most 64 previews, and can be consumed only once. Confirmation supplies the
displayed request hash and an explicit `confirmed: "yes"`. The route checks
authorization before sending and again after the provider returns. The provider
uses one HTTPS request with no redirect, proxy-environment use or retry; failed
or invalid replies do not trigger an automatic second request.

The source routes are:

```text
POST /memory-stories/{story_id}/proofreading/preview?library=...
  {"revision":"..."}

POST /memory-stories/{story_id}/proofreading/confirm?library=...
  {"revision":"...","preview_id":"...","request_sha256":"...","confirmed":"yes"}
```

The provider must return the closed JSON shape `{"paragraphs":[...]}`, with
one paragraph per input chapter. Empty chapters stay empty. Valid suggestions
are marked `needs_review: true` and `saved: false`; the author must choose to
bring the suggestion into the editor, review it, and save it explicitly. The
saved original remains unchanged if a request fails or the suggestion is
declined.

### Explicit operator injection example

The code below shows the required injection shape only. The credential loader is
a placeholder; PhotoHouse does not implement that secret store, and the key
must remain outside Git and the application configuration UI.

```python
from app.access.story_cloud_proofreading import DeepSeekProofreader
from app.main import create_app

proofreader = DeepSeekProofreader(
    api_key=load_from_private_credential_store(),
    model="deepseek-flash",
)
app = create_app(
    access_runtime=explicit_access_runtime,
    memory_collaboration_enabled=True,
    story_cloud_proofreading_enabled=True,
    story_cloud_proofreading_provider=proofreader,
)
```

The ordinary configuration remains disabled unless these options are
explicitly supplied. This example does not authorize enabling a live service,
installing a credential, or making a provider request.

## Related implementation

- Grounder: [`story_name_grounding.py`](../server/backend/app/access/story_name_grounding.py)
- Cloud request and provider: [`story_cloud_proofreading.py`](../server/backend/app/access/story_cloud_proofreading.py)
- Author-only routes: [`story_cloud_transport.py`](../server/backend/app/access/story_cloud_transport.py)
- Runtime defaults: [`runtime.py`](../server/backend/app/access/runtime.py) and [`main.py`](../server/backend/app/main.py)
- Local security tests: [`test_story_name_grounding.py`](../server/tests/security/test_story_name_grounding.py) and [`test_story_cloud_proofreading.py`](../server/tests/security/test_story_cloud_proofreading.py)

Search and photo grouping paths are unchanged by these story-only flows.

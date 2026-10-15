# Local OpenCLIP text provider

The semantic-search pilot now has an optional provider implementation, an
authenticated loopback ASGI wrapper and an explicit probe/serve command. None
is imported or started by the normal PhotoHouse application. This source work
does not install dependencies, download weights, run a model on the Mac, change
Windows tasks or activate semantic mode for family accounts.

## Model implementation

`server/scripts/semantic_openclip.py` loads the fixed built-in `ViT-B-32`
architecture from one explicitly selected full local checkpoint and one local
gzip BPE vocabulary. Model identifiers, pretrained tags, hub selectors, default
tokenizer files and directory discovery are refused. The loader does not use
the legacy placeholder-vector helper.

Checkpoint and BPE bytes are checked before loading and rehashed afterward.
The BPE input is limited to 4 MiB compressed and 16 MiB decompressed. The recipe
records installed package versions, the BPE digest, model architecture, token
rules and hashes of the adapter, receipt helper, OpenCLIP initializer, factory,
model, tokenizer and architecture configuration. Relevant file identities are
checked before and after inference. Tokenizer query-word cache entries are
cleared after each request. No query text is written to a receipt or disk.

Exact versions must match the private configuration, with OpenCLIP >=3.1 and
Torch >=2.6 and an explicit `weights_only` loader parameter. Restricted loading
is forced during checkpoint initialization, including older OpenCLIP's fallback
path, then the prior environment is restored. A conflicting unsafe-loading
environment setting is refused. This adapter is intended for a dedicated
provider process. TorchScript/pickled-module checkpoints that require unrestricted
loading are not supported. It never retries with unrestricted loading.

The implementation uses OpenCLIP's [local checkpoint factory interface](https://github.com/mlfoundations/open_clip/blob/v3.1.0/src/open_clip/factory.py)
and [SimpleTokenizer](https://github.com/mlfoundations/open_clip/blob/v3.1.0/src/open_clip/tokenizer.py).
The restricted-loading environment behavior is documented by
[PyTorch](https://docs.pytorch.org/docs/2.6/notes/serialization.html#environment-variables).

The model must be FP32 on the explicitly chosen `cpu` or `cuda:0` device and
produce 512-component output. Input is at most 512 UTF-8 bytes and must fit 75
content tokens plus the two required control tokens. Empty tokenization,
overflow and embedded start/end tokens are refused; nothing is truncated.
Inference runs without gradients, produces a finite unit vector, and returns
the exact-query digest and canonical float32 checksum.

Serving requires a `JointSpaceBinding` whose text and image artifact digests
both match this full checkpoint, and whose text preprocessing digest equals the
observed recipe. The separate image preprocessing identity remains explicit.
The qualification digest is still an operator-reviewed attestation. The probe
records implementation identity; it is neither an independently approved
package/source allowlist nor proof of useful retrieval or language coverage.
Review installed dependencies and the probe before preparing a serving binding.

## Private configuration and commands

The JSON configuration must be an owner-private file outside the source
checkout, with no linked path components. It has exactly these keys:

- `schema`: `photohouse.semantic_text_provider.v1`
- `architecture`: `ViT-B-32`
- `checkpoint`: `path` (absolute local file) and `sha256`
- `bpe`: `path` (absolute local file) and `sha256`
- `device`: `cpu` or `cuda:0`
- `package_versions`: exact installed `open_clip_torch`, `torch`, `ftfy`, `regex`
- `binding`: null for an initial probe, or the `JointSpaceBinding` record
- `port`: explicit integer from 1024 through 65535
- `credential_file`: null for a probe, or a separate owner-private JSON file
  outside source containing exactly `token`, a 32–128 character ASCII bearer
  secret using letters, digits, underscores or hyphens

No credentials belong in source, shell arguments, receipts or URLs. The initial
probe does not open the credential file or a listening socket:

```sh
python server/scripts/serve_semantic_text.py probe --configuration "/absolute/private/provider.json"
```

It loads the selected model and encodes only the fixed synthetic phrase
`a red circle`. Its JSON output records hashes, recipe, device, dimension and a
probe checksum, with `relevance_measured: false`. It contains neither file paths
nor vector components. Run this command only in an explicitly selected native
runtime with appropriate memory/GPU capacity; source tests use stand-ins.

After native qualification and preparation of the reviewed binding/credential:

```sh
python server/scripts/serve_semantic_text.py serve --configuration "/absolute/private/provider.json"
```

The command repeats the probe, validates the serving binding, and explicitly
starts one loopback-only process. Proxy trust and request/Python logging are
disabled. Installing, running and managing this process are separate operational
actions; no scheduled task or automatic startup is added by these source files.

## Provider boundary

The only route is `POST /v1/encode-text`, using the pilot's existing exact JSON
protocol. It requires a loopback peer, the configured loopback Host/port, and a
matching bearer header before reading the body. Browser Origin and forwarding
headers, query strings, compressed requests, transfer encoding and duplicate
security headers are refused. There are no public health, docs or model-list
routes. Request bodies are limited to 4 KiB, responses to 64 KiB, and body plus
inference response processing shares a two-second cooperative deadline.

One inference lease is held until the actual worker finishes, including after
an HTTP timeout/disconnect. Later requests receive busy rather than creating
more workers. Late results and errors are withheld; future exceptions are
consumed without logging provider details. An in-progress GPU call cannot be
forcibly preempted by this wrapper. Shutdown does not wait in the ASGI lifespan;
process termination/resource control remain deployment responsibilities.

`LocalSemanticEncoder(..., bearer_token=...)` sends the private credential only
in the Authorization header, without changing the query protocol or model
binding. The older no-credential constructor remains useful for generated
fixtures; this provider always requires authentication. It is a separate
standalone service and is not mounted by `create_app` or the main HTTP boundary.

## Validation and remaining delivery work

Generated tests cover loader flags and pins, package/device refusal, input
token limits, cache cleanup, vector checks, private configuration, CLI dispatch,
authentication before body reads, request limits, late-error redaction and
retaining the inference lease after timeout. A full generated chain exercises
the search API, real HTTP client protocol, provider ASGI wrapper and model
adapter with optional ML objects replaced by stand-ins. It opens no socket and
loads no model weights.

Native checkpoint/package compatibility, memory and latency bounds, compatible
image artifacts, Chinese/English relevance, runtime configuration and
assistant/client integration are still required before enabling family semantic
search. No source or synthetic pass establishes those results.

The separate [generated pair measurement](SEMANTIC_PAIR_QUALIFICATION.md)
reuses one full checkpoint to measure simple image/text retrieval in English
and Chinese. Its results do not approve a binding or qualify legacy vectors.

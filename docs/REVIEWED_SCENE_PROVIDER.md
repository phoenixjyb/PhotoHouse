# Reviewed scene-query provider

This optional provider serves a finite set of exact, privately reviewed query
mappings. It supports a Chinese, English or mixed original mapped to an English
model input without running a translator during a request. Unlisted queries
receive the existing unavailable response; there is no guessed mapping, queue,
retry or fallback. Ordinary application defaults and scene-search gates remain
unchanged.

The [held-out intent diagnostic](SEMANTIC_SCENE_INTENT_EVALUATION_2026-10-16.md)
found meaning changes in automatic translations. This adapter makes the review
boundary explicit. It does not establish general bilingual understanding,
translation faithfulness, model relevance or native serving qualification.

## Query and binding identity

| Boundary | Checked identity |
| --- | --- |
| HTTP request | Exact original UTF-8 query and composite binding |
| Private mapping | Exact original to reviewed model input |
| Inner encoder response | Derived query hash, original encoder binding and canonical vector checksum |
| Outer response | Original query hash, composite binding and validated vector |
| Conversation and recovery | Original wording and existing protected scope; replay does not encode again |

The composite recipe includes the complete inner joint binding, projection
hash, review-reference hash, exact-match policy and implementation-bundle hash.
The outer image identity must equal the inner image identity. The outer text
identity changes only its preprocessing hash to the composite recipe hash. A
distinct qualification hash is required. The inner binding is never rewritten.
An outer binding is checked before model loading.

The implementation bundle pins the adapter, driver, direct configuration
validator, diagnostic helpers, private-file readers, vector validation,
checkpoint receipts, transport and encoder protocol. Startup verifies source
contents; requests check pinned source identity before and after encoding.
The direct encoder retains its own preprocessing and checkpoint checks.

## Private configuration

All configuration, credentials and review documents stay outside source control.
The existing private-document reader rejects links, duplicate JSON keys, unsafe
permissions and files larger than 128 KiB. References are read once, hashed and
validated from that snapshot. Hashes below are canonical JSON content hashes:
sorted object keys, compact separators, ASCII escaping and no nonfinite numbers.
Array order matters. These differ from raw file-byte hashes.

The outer configuration has exactly these keys; placeholders are illustrative
and are not an approved configuration:

```json
{
  "schema": "photohouse.reviewed_semantic_text_provider.v1",
  "encoder_configuration": {"path": "/private/encoder.json", "document_sha256": "<digest>"},
  "projection": {"path": "/private/projection.json", "document_sha256": "<digest>"},
  "binding": null,
  "port": 8915,
  "credential_file": null
}
```

The encoder document uses the existing direct-provider configuration schema and
requires a genuine inner binding. Its credential is not read or used by this
adapter. Serving additionally requires a matching composite outer binding and
a private credential document with a `token` of 32–128 ASCII letters, digits,
underscores or hyphens.

The projection document has exactly this shape:

```json
{
  "schema": "photohouse.reviewed_scene_projection.v1",
  "policy": "exact_reviewed_only",
  "review": {"status": "operator_reviewed", "reference_sha256": "<digest>"},
  "entries": [{"original": "<exact original>", "model_input": "<reviewed English>"}]
}
```

There must be 1–256 unique originals. Each string is at most 512 UTF-8 bytes;
originals are single-line without controls, and model inputs are printable ASCII
with at least one letter. Whitespace is preserved. A spelling or whitespace
variant requires its own reviewed entry. The private-file size bound can limit
the entry count before 256.

`operator_reviewed` and the review-reference hash are a trusted operator assertion
and evidence identity. The adapter does not inspect that evidence or establish
its authorship or semantic correctness. A model approval label is rejected.
The immutable mapping is not request history and cannot be edited through HTTP.
There is no hot reload; changing it requires a new matching binding and an
explicit restart. Existing library membership and revocation checks still apply.

## Explicit operations

```sh
python server/scripts/serve_reviewed_semantic_text.py
```

The no-argument plan reads no private inputs, imports no optional ML runtime,
loads no model and opens no listener.

An explicit `probe --configuration /private/provider.json` loads the configured
model and reports identities, hashes and mapping count without query text. The
outer binding may be absent for this preparation step. A probe neither serves
requests nor approves activation or qualification.

An explicit `serve --configuration /private/provider.json` requires the outer
binding and private token. It uses the existing authenticated loopback v1
transport on `127.0.0.1`, one worker and the existing two-second request budget.
One encoding lease remains occupied until a timed-out worker drains. The model
loads at startup; no request-time LLM or translation service is called.

This source round ran neither operation against a real model. It created no
real reviewed mapping, qualification binding or activation configuration.

## Evidence and delivery gates

Generated tests cover exact matching, immutable snapshots, composition and source
identity, tampering, original/derived hashes, protected person/library scope,
conversation recovery, timeout/drain behavior and isolated package imports.
They use fake encoders and generated data. They establish source behavior only.

A real pilot still needs operator-reviewed private mappings, qualification of the
exact composite recipe, compatible image-vector coverage, native resource and
serving checks, explicit activation, and family/device relevance assessment.
Broader natural-language clarification and automatic faithful translation remain
separate development work.

# Offline reviewed-provider scene measurements

`server/scripts/qualify_reviewed_semantic_scenes.py` measures the exact
[reviewed scene-query provider](REVIEWED_SCENE_PROVIDER.md) against an explicitly
selected scene set. It calls the provider with each original English, Chinese
and mixed query, then ranks the returned vectors against the same loaded
checkpoint's image tower. It retains the original language cohorts and labels.
It does not call a translator, open a library or start an HTTP service.

This is measurement support, not a qualification approval. No real mapping,
binding, model run or live activation was created with this source change.

## Required identities

The run requires an existing inner encoder binding and matching composite outer
binding in a private reviewed-provider configuration. Neither is manufactured by
the runner. Both bindings and complete exact query coverage are checked before
model loading. A missing mapping, changed original query or stale composite
recipe fails the run; there is no partial-language score or fallback.

After loading one shared image/text model, the runner observes the image
preprocessing recipe using the existing scene measurement pipeline. Before any
image or query encoding, it requires the declared image identity to match the
checkpoint hash, observed preprocessing hash, dimension 512 and unit-L2
normalization. It also requires the exact provider's inner binding to be the
model's binding. Model/version labels are configured identities, not inferred
proof of relevance.

The scene recipe includes source hashes and the exact dataset fingerprint. This
round changes the scene runner's source hash, so historical image preprocessing
receipts cannot be substituted. Use a current
[unbound scene measurement](SEMANTIC_SCENE_QUALIFICATION.md) to observe the current
recipe, then complete the separate operator qualification process before
supplying matching bindings. A different dataset or source recipe requires
matching identities again. That measurement source slice left the serving
adapter unchanged. Subsequent [refusal protocol changes](SCENE_QUERY_REWORDING.md)
require a new matching composite binding; older ones are not migrated.

## Private inputs and explicit execution

Use the existing private scene dataset schema and file/image admission rules
from the [scene measurement guide](SEMANTIC_SCENE_QUALIFICATION.md). Freeze image
selection, relevant labels, original queries and meaning-reviewed mappings
before inspecting rankings. English originals also need explicit map entries.
Extra reviewed mappings may exist, but only the selected queries are measured.
Review declarations remain operator assertions; the runner does not prove image
authenticity, label correctness or translation faithfulness.

The private run configuration has exactly:

```json
{
  "schema": "photohouse.reviewed_scene_run.v1",
  "provider_configuration": "/absolute/private/reviewed-provider.json",
  "dataset": "/absolute/private/scenes.json",
  "image_package_versions": {
    "torchvision": "EXACT_INSTALLED_VERSION",
    "Pillow": "EXACT_INSTALLED_VERSION",
    "numpy": "EXACT_INSTALLED_VERSION"
  },
  "max_elapsed_seconds": 600
}
```

The provider configuration uses the reviewed provider's existing schema, with
a nonnull outer binding. Its credential file is not read. Private documents are
read as stable snapshots with the existing permissions, link, size and strict
JSON checks. No image discovery, model download or vector publication occurs.

```sh
python server/scripts/qualify_reviewed_semantic_scenes.py
```

The default plan reads no private files, imports no optional ML packages, loads
no model and opens no listener. An actual offline run requires explicit inputs
and a new output directory beneath an existing private parent:

```sh
python server/scripts/qualify_reviewed_semantic_scenes.py --run \
  --configuration /absolute/private/reviewed-scene-run.json \
  --output-directory /absolute/private/new-reviewed-measurement
```

The output is reserved once. `started.json` precedes model loading and remains
after failure; an existing destination is never overwritten. The 30–1800-second
budget cooperatively covers model loading and measurement. It cannot preempt a
native decoder or GPU call and is not an OS resource limit. Use independently
bounded native resources for a real run.

## Report and limits

The private `measurement.json` has schema
`photohouse.reviewed_scene_measurement.v1`. It records the original dataset
fingerprint and unchanged evaluator metrics, image preprocessing/checksum
receipts, both provider identities, evaluator source hashes and per-query
receipts keyed by case/language. Each query receipt pairs the original UTF-8
hash, reviewed model-input hash, projection hash and vector checksum. The
provider's outer binding and original response hash are validated before ranking.
No raw queries, image paths, credentials or vector components are written.
The CLI prints only a bounded aggregate summary and report digest; dependency
diagnostics and errors do not expose private inputs.

Top-one/top-five, reciprocal rank and recall retain the existing pessimistic
tie policy and separate language summaries. These scores describe the selected
exact reviewed mappings. They do not measure unseen phrase coverage or establish
general bilingual/vague-intent understanding. Compare frozen cohorts separately
with the [cohort comparison helper](SEMANTIC_SCENE_QUALIFICATION.md#compare-frozen-intent-cohorts).

Timings are in-process image/provider timings. No HTTP transport, two-second
serving deadline, resource containment, live vector coverage, family/device
acceptance, dialect recognition or ASR is qualified here. Those remain separate
gates before activation.

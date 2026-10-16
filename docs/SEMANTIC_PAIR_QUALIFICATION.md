# Generated image/text pair measurements

The optional `qualify_semantic_pair.py` command measures the pinned local
OpenCLIP provider against four generated color/shape images and twelve fixed
queries: four each in English, Chinese, and mixed Chinese-English. It helps
distinguish a model that loads from a pair that retrieves these elementary
generated inputs correctly. The original eight English and Chinese queries,
all four images, and the rendering recipe remain unchanged from v1. The new
mixed-script cohort is reported separately so it cannot be hidden by an
aggregate score.
It reads no family media, database, legacy vector files, library metadata or
credentials, creates no joint-space binding, and starts no service.

The legacy `embeddings` table records model/version, dimension, path and vector
checksum, but does not retain exact checkpoint and preprocessing identities.
Those rows cannot be relabeled as compatible immutable semantic artifacts.
The separate immutable-artifact schema and programmatic image-worker path
remain optional; they are not activated or migrated by this command. A native
read-only aggregate inventory is needed to determine an installation's actual
coverage. Source capability does not prove installed schema or ready artifacts.

## Plan and explicit execution

Planning reads no private configuration and loads no optional model packages.
The case-plan and evaluation schemas are v2. The v2 case-plan digest is
`abd45ca17c022de3875324a9ebda8c747a98c590e3cacb858e0bbad3fafc4fa4`; the
v1 baseline digest was
`6380eb66df9262f173b1cece62a5b0cc749ba64bcf941ea221eba840d4750d5f`.
The v2 digest includes the new cohort and an explicit false dialect-relevance
marker. Earlier v1 results remain tied to their original digest and cannot be
compared as though they measured the new cases. The fixed mixed-script queries
are `白色背景上的red circle`, `a blue circle，白色背景`,
`白色背景上的red square`, and `a blue square，白色背景`:

```sh
python server/scripts/qualify_semantic_pair.py
```

For execution, prepare an owner-private JSON file outside source with exactly:

```json
{
  "schema": "photohouse.semantic_pair_canary.v1",
  "provider_configuration": "/absolute/private/text-provider.json",
  "image_package_versions": {
    "torchvision": "EXACT_INSTALLED_VERSION",
    "Pillow": "EXACT_INSTALLED_VERSION",
    "numpy": "EXACT_INSTALLED_VERSION"
  }
}
```

The referenced file is the existing [text-provider configuration](LOCAL_SEMANTIC_TEXT_PROVIDER.md)
with `binding: null`. Its checkpoint, BPE, device and four text-package versions
remain explicit and pinned. Select canonical local paths; a legacy runtime
directory junction is refused rather than followed implicitly. No model or
package is installed, discovered or downloaded. Use a new output directory
under an existing private parent:

```sh
python server/scripts/qualify_semantic_pair.py --run \
  --configuration "/absolute/private/pair-canary.json" \
  --output-directory "/absolute/private/new-pair-run"
```

The command reserves the output once and saves `started.json` before model
loading. Failures preserve that record. It refuses linked/source output paths,
existing destinations, malformed private JSON and installed-version drift.
Run only in an explicitly selected native runtime and an independently bounded
process. The CLI checks elapsed time cooperatively during measurement; it
does not itself enforce a hard RAM, GPU, process or startup deadline.

## What is measured

One full checkpoint is loaded through the restricted, pinned text-provider
adapter. Its image tower is reused in the same dedicated offline process.
The evaluation transform is reconstructed from the loaded visual preprocessing
configuration, following OpenCLIP's [evaluation factory](https://github.com/mlfoundations/open_clip/blob/v3.1.0/src/open_clip/factory.py).
The command observes the realized resize/crop/RGB/tensor/normalization sequence
and records exact installed package versions and source digests. These are
observed implementation identities, not an independently approved dependency
allowlist or a native sandbox.

Each source-defined image is rendered, encoded as bounded JPEG and decoded
before inference. Exact JPEG and canonical vector checksums are retained.
Text uses the existing unbound offline encoder path, including token limits
and tokenizer cache cleanup. Raw vector components and arbitrary input queries
are not saved. Source/checkpoint identities are checked throughout and fully
rehashed after the measurement.

Every query is scored against all four images. Reports include per-case ranks
and score margins, plus top-1, top-2 and mean reciprocal rank for each language
cohort and a separate twelve-case overall summary. English, Chinese, and mixed
Chinese-English remain distinct in the report. Ties within `1e-7` use the worst
rank among tied candidates. A collapsed or constant encoder therefore cannot
receive arbitrary tie-breaking credit. Scores are relative cosine similarities,
not probabilities or factual labels.

`measurement.json` records the case-plan digest, text implementation recipe,
separate generated-image preprocessing recipe, timings and results. The image
recipe identifies this canary's actual code and input profile; it does not
impersonate the legacy image worker or qualify existing family vectors.
Standard output contains the bounded measurement summary and report digest;
failures use a fixed error without local paths or provider diagnostics.

## Remaining activation gates

Even perfect results on four simple drawings establish only this generated
case performance. The mixed-script cohort uses fixed printed text, so it does
not measure ASR, spoken mixed-language recognition, Shanxi/Jin dialect
recognition, or family relevance. No dialect phrases or aliases are inferred
from these cases. These results do not establish scene retrieval, names,
identities, family-photo relevance, multilingual recall generally or acceptable
serving latency. Human review, dialect relevance, and family relevance stay
explicitly unverified, and activation and legacy-vector qualification stay
false. The v1 plan digest remains a distinct historical baseline.

Before a family pilot, prepare compatible immutable image artifacts under a
separately reviewed production image recipe, measure a larger reviewed case
set, establish selected CPU/GPU serving limits, and integrate explicit runtime
and assistant/client configuration. The existing hard-filter and library
authorization boundaries continue to apply.

The separate [private scene-set evaluator](SEMANTIC_SCENE_QUALIFICATION.md)
accepts explicitly selected natural-scene images and matched English, Chinese
and mixed queries. It reports retrieval measurements for the selected set;
it neither replaces this fixed generated baseline nor activates a provider.

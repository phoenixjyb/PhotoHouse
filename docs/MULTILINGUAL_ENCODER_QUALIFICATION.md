# Offline multilingual encoder qualification

Semantic search stays disabled while a direct multilingual encoder is evaluated.
The offline runner adds no serving provider, binding, database migration, vector
publication or activation path.

The candidate is [Google SigLIP2 base, patch 16, 256 pixels](https://huggingface.co/google/siglip2-base-patch16-256)
at revision `3f9f96cb90da5dbc758b01813f2f6f1aee24c1ab`. The official FixRes
configuration declares `model_type: siglip`: it uses `SiglipModel` and
`SiglipProcessor`, rather than the NaFlex API. The checkpoint and tokenizer have
seven exact byte/hash pins. This model produces 768-component image/text
features; existing OpenCLIP vectors have 512 components and cannot be reused.

`server/scripts/qualify_multilingual_scenes.py` prints a plan with no arguments.
That path reads no private files and imports no optional ML packages. Execution
requires `--run --configuration ABSOLUTE_PRIVATE_JSON --output-directory
NEW_ABSOLUTE_PRIVATE_DIRECTORY`. Do not put these private inputs in the checkout.

The closed `photohouse.multilingual_scene_run.v1` configuration contains exactly:

- `schema`, `model_directory`, and `dataset` (the existing reviewed scene schema).
- `artifacts`: the seven official filenames, each with exact `bytes` and `sha256`.
- `package_versions`: the exact dependency versions named by the runner.
- `max_elapsed_seconds`: an integer from 30 to 1800, a cooperative deadline.

The runner requires private canonical local paths, verified single-frame images,
and an exact model file set. It loads safe tensors locally on CPU with remote
code disabled. It records source/model/image hashes, original-query hashes,
token counts, preprocessing, normalized vector checksums and ranking metrics.
It saves neither feature arrays nor query text in the measurement. Original
Chinese, English and mixed queries reach the candidate without translation.
The model input is explicitly lowercased, with both original and model-input
hashes retained. The pinned tokenizer declares only input IDs, so no attention
mask is supplied. Overlength text is rejected before fixed-length padding;
truncation is disabled.

The parent operator must enforce hard resource limits and offline networking.
The CLI deadline cannot interrupt a hung native model call. For the first native
screen, the frozen private plan specifies two CPU threads, an 8 GiB Job Object,
four processes, 600 seconds per job and a 16 GiB free-RAM floor. The child must
prove its assigned Job before importing model packages. Model acquisition is a
separate public download operation on Windows; inference must use local files.
No model artifacts are downloaded to the Mac source workspace.

Compare the unchanged earlier public scene set as a regression and a separately
reviewed, frozen public scene set for this development round. Keep English,
Chinese and mixed results, literal/vague/contrast cohorts, and individual losses
visible. The public photos may have appeared in model training: this is a
holdout from this application's earlier evaluation work, not a training holdout.
Assistant visual/text review is not family or human acceptance. Freeze labels,
queries, resource budgets and screening criteria before any model scoring.

A completed screen does not establish production readiness. Broader negation,
count, relationship and ambiguity evaluation, private-family relevance,
compatible immutable vector coverage, protected serving integration, serving
latency and device acceptance remain separate gates. Translation-based
comparisons must also satisfy the [fidelity review contract](SEMANTIC_SCENE_TRANSLATION_FIDELITY.md);
a high retrieval score cannot establish that a translation preserved meaning.

# Approved upload processing v37: portable source and qualification notes

This note describes the public source package and its synthetic canary contract. It does not enable workers or authorize access to a live service.

## Worker scope

Workers process uploads that have been explicitly approved and mapped to an active library. Their queue checks preserve library and upload authorization; successful processing records derived outputs and any chained jobs under the selected schema revision.

## Source-only package

`build_approved_worker_package.py` reads a full immutable 40-character Git commit and selects exactly 21 source and contract-document files. It creates a deterministic archive containing no family media, credentials, configuration, model weights, dependencies or activation instructions. The archive manifest records per-file hashes and remains marked unactivated.

Run packaging from a clean local source checkout, with the output parent already present and an unused absolute output path:

```sh
python scripts/build_approved_worker_package.py --commit <40-character-commit> --out <absolute-new-package-path>
```

The schema smoke selector defaults to `a0c9d2e4f817`. An operator may explicitly select `b1d7e4a9c230` for the synthetic schema case. The selector does not migrate a production database or change a worker's installed schema:

```sh
python scripts/qualify_approved_workers_windows.py --ffmpeg <existing-ffmpeg-path> --ffprobe <existing-ffprobe-path> [--schema-revision a0c9d2e4f817|b1d7e4a9c230]
```

The canary output contract requires decoded image derivatives and video metadata/frame outputs before a result can count as complete. See [canary output requirements](APPROVED_WORKER_CANARY_OUTPUTS_V1.md).

## Acceptance boundaries

Synthetic tests use generated records, temporary databases, fake child results and local image tooling. They verify source behavior and refusal paths; they do not establish Windows scheduling, installed dependencies, GPU/model readiness, a live service, family data processing or release activation. Those require their own source-pinned operational and owner acceptance evidence.

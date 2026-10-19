# Semantic retrieval runtime configuration

Semantic retrieval is a disabled-by-default pilot. Existing staging JSON and
`RuntimeConfiguration` defaults continue to build without reading a semantic
manifest or looking up its credential. The factory loads a manifest only when
`assistant_semantic_search_enabled` is explicitly `true` and requires the
assistant, its existing private workspace, discovery indexes, and a manifest
path together. A partial selection refuses before the app is built.

Add these two fields to the private staging configuration only after an
operator has reviewed the matching encoder and image-vector cohort:

```json
{
  "assistant_semantic_search_enabled": true,
  "semantic_configuration_path": "/private/photohouse/semantic-runtime.json"
}
```

The manifest is bounded to 128 KiB, must be an owner-private regular file
outside the source tree, and has exactly this shape:

```json
{
  "format_version": 1,
  "vector_root": "/private/photohouse/image-vectors",
  "encoder_url": "http://127.0.0.1:43210/v1/encode-text",
  "encoder_timeout_seconds": 1.5,
  "credential_file": "/private/photohouse/semantic-credential.json",
  "binding": {
    "image_identity": {
      "artifact_sha256": "<64 lowercase hex>",
      "preprocessing_sha256": "<64 lowercase hex>",
      "vector_space_id": "<stable id>",
      "model_version": "<stable id>",
      "dimension": 512,
      "normalization": "unit_l2"
    },
    "text_identity": {
      "artifact_sha256": "<64 lowercase hex>",
      "preprocessing_sha256": "<64 lowercase hex>",
      "vector_space_id": "<same as image>",
      "model_version": "<stable id>",
      "dimension": 512,
      "normalization": "unit_l2"
    },
    "qualification_sha256": "<64 lowercase hex>"
  },
  "binding_sha256": "<digest produced by JointSpaceBinding.binding_sha256>",
  "operator_reviewed": true
}
```

The credential stays in a separately selected, owner-private, bounded JSON
file containing exactly `{"token":"<local encoder bearer token>"}`. It is read
only during enabled runtime construction and must satisfy the local
encoder's bearer-token format. The vector root must already exist as a private
directory, have no symlink or reparse point in its ancestry, and resolve outside
the source tree. The factory checks that the manifest, credential file, and
vector root do not overlap protected runtime paths or one another. The binding
digest pins the reviewed identities and qualification reference against accidental edits;
the `operator_reviewed` marker is an attestation from the configuration owner.
Neither proves installed model identity, multilingual query quality, or runtime
availability. The factory creates only the loopback HTTP adapter; it does not
call inference at startup. Search still requires the authenticated discovery
runtime and current hard filters.

`tools/check.py api` may provide fixture-level evidence only. It does not
activate a live encoder, install artifacts, or establish real-family retrieval
quality.

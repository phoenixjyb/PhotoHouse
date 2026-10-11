# Prepare a static Web UI overlay

A Web-only update can keep an existing backend and database revision while
selecting new static assets. Preparation does not activate editorial routes or
perform a deployment. The optional memoir reader treats absent (404) and
disabled (503) editorial endpoints as legacy reading.

From a committed source checkout, select its complete commit ID:

```sh
python server/scripts/build_access_ui_overlay.py --commit <full-commit-id> --out /absolute/path/to/new-ui.zip
```

The builder supports the unified repository's `server/` subdirectory. It reads
only five regular Git blobs: the protected UI HTML, application script, story
workspace, memory community and stylesheet. Its deterministic ZIP contains
those five assets and a manifest. It excludes the backend, configuration,
database, original media, icon and Git history, and refuses an existing output.

`server/scripts/access_ui_overlay.py` is a binding primitive. A caller must
supply the exact source commit and an independently reviewed manifest digest.
It validates every file and the closed directory structure before changing the
UI router's four static paths. The configured icon path stays unchanged.
The nine synthetic tests cover both a separate application repository and the
unified layout, tampering, unsupported members, failed-binding preservation and
actual static responses with privacy headers.

This primitive is not a service controller. A deployment still needs a pinned
entry wrapper, exact runtime/configuration checks, a private immutable overlay,
current task/process evidence, bounded restart and rollback, operation authority,
and independent HTTPS readback. Backend/schema changes and family feature flags
have separate gates. Follow [Web browser checks](WEB_DEVELOPMENT.md) and
[source packaging](SOURCE_PACKAGING.md) for local qualification.


## October 12 prepared local overlay

A five-asset overlay is prepared from source
`263439ce34ebb894164923b674142a577b19fe68`, matching the complete 19-suite
passing Web snapshot. ZIP SHA-256:
`af5559f8d77e4b201cfe305ff7b9bfce7c99da7d807fc2e7ead6d6af8c79349b`;
manifest SHA-256:
`02513b32ac7f276e91f33ea06357c34b9bcb964622d195cbf0ef0edaecf5ef32`.
The archive is 958,278 bytes. Nine builder/binding tests and a temporary local
router smoke passed; all five static response hashes matched the manifest and
the icon path remained unchanged. Neither check contacted Windows or served a
household browser. See [the candidate handoff](LOCAL_CANDIDATE_2026-10-12.md).

Before activation, read back the real API/configuration, bind this exact immutable
overlay in a qualified private wrapper, and prepare restart/rollback plus
independent HTTPS asset readback. An overlay only changes static files; it does
not enable memoir, source-group, title or AI capabilities in an older backend.
Keep those service/data/provider activation gates separate.

# Literal Rust delivery package and protected-launch integration

This chunk packages the already qualified Windows binary and adds the explicit
launcher/grouping contract for a later controlled rollout. It changes no live
service, scheduled task, configuration, database or library. GitHub CI stays off.
The current Search, grouping and Family auto-import deployment remains intact.

## Reuse the qualified binary

`rust/package_literal_kernel.py` creates a deterministic unpublished wheel. It
does not build, install or activate native code. The caller supplies the saved
qualification receipt and its reviewed SHA-256; the packager verifies the receipt
bytes/status, successful checks and AMD64 proof, then derives the native hash,
byte length and source commits from that receipt. A different binary, failed or
unverified receipt, wrong PE target, changed locked dependency notice or existing
output is a refusal.

The wheel contains the exact `.pyd`, public source/qualification digests, locked
dependency notices and a complete hashed `RECORD`. Private receipt paths and
runtime settings are not copied into its metadata. Its `cp312-abi3-win_amd64` tag
and `Requires-Python: >=3.12` reflect the qualified application runtime; using a
stable ABI in the DLL does not qualify older Python Unicode behavior.

From the source workspace, using canonical absolute input paths and a new output:

```sh
python rust/package_literal_kernel.py \
  --native "$qualified_binary" --vendor "$locked_vendor" \
  --qualification "$qualification_receipt" \
  --qualification-sha256 "$reviewed_receipt_sha256" \
  --output-dir "$new_output_directory"
```

Windows packaging requires D: inputs/output. The current qualified binary should
be reused rather than rebuilt. No dependency download is part of packaging.

## Closed launch contract

`server/scripts/rust_overlay_selection.py` is included in the curated source
archive and can be embedded in the protected launcher from one canonical source.

| Reviewed shape | Literal behavior |
| --- | --- |
| Existing three Rust selectors and vector/stack binaries | Python; no literal binary read or import |
| Explicit literal selector plus its pinned binary | `python`, `rust` or `shadow`, as declared |
| Undeclared selector, ambient native flag, changed legacy choice or extra/missing binary | Refuse |

The vector, visual and grouping choices remain fixed to their existing qualified
Rust selections. A literal rollback explicitly forwards `python`; it does not
change those choices. The environment producer copies ordinary inherited values
and refuses ambient native selector keys before adding the reviewed values.

For Rust/shadow, literal preflight requires Python 3.12+, a pinned file at the
declared module path, a clean module namespace, the exact import origin, integer
policy version 1 and three generated-text probes. The binary is checked before
and after import. Python mode performs no literal import. Grouping uses the same
closed roster validator without executing native code and retains its existing
closed diagnostic vocabulary.

## Render the reviewed source changes

`rust/render_literal_overlay.py` requires hashes of the existing protected API
launcher and grouping overlay guard. It renders both fully and parses them before
creating a fresh output directory. It replaces only the explicit native-activation,
environment-forwarding and native-roster extension points; unexpected source
shape refuses. Existing source/config/bootstrap/task and relative-member guards
remain in the result. The original vector/visual/grouping probes are preserved.

```sh
python rust/render_literal_overlay.py \
  --launcher "$reviewed_launcher" --launcher-sha256 "$launcher_sha256" \
  --guard "$reviewed_grouping_guard" --guard-sha256 "$guard_sha256" \
  --output "$new_render_directory"
```

The outputs are inert source, not a live plan or an admission. In particular they
do not reuse an old operation, grant or mutable runtime setting. The controlled
rollout still needs fresh API source/native manifests, grouping bindings,
backup/rollback scope and trusted functional readback. Preserve the existing
UI, model/provider, import task and all protected storage inputs. Use focused
local checks; do not rebuild passed kernels or start GitHub Actions.

## Local checks

```sh
PYTHONPATH=server/backend:server/tests/security python -m unittest \
  test_rust_overlay_selection test_literal_kernel_package \
  test_literal_overlay_renderer test_staging_package
```

The tests use generated PE/receipt/license fixtures and mocked native modules.
An actual qualified binary/wheel and rendered protected-source checks are
recorded separately; unit fixtures do not claim Windows activation.

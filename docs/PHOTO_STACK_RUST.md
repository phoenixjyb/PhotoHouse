# Optional Rust photo-stack engine

The whole-library builder supports an opt-in Rust candidate index and complete-link
comparison loop. Python remains the default, retaining the public function,
validation, date parsing, policy fingerprint and publication behavior. This change
does not deploy or activate an engine on the Windows workstation.

Set `PHOTOHOUSE_PHOTO_STACK_ENGINE=rust` only in the process that should use a built
extension. `python` selects the reference implementation. A selected but missing
extension raises an actionable error; native failures are not silently retried in
Python. The wire-version and native policy fingerprint must also match before
grouping. A changed grouping policy, lone-surrogate upload metadata, or a caller's
explicit allowance for more than 100,000 prepared assets uses the Python reference.
These fallbacks preserve cases outside the native kernel's supported wire format.

The core uses ordered candidate IDs, exact 64-bit hashes and integer microseconds.
It preserves gallery/member order, naive/aware separation, unknown-day upload
lookup, the 24-member cap, complete-link semantics and comparison-budget refusal.
The callback adapter makes the same grouping cancellation checks as the reference,
propagates the original Python exception and never returns partial groups. It
releases the GIL and periodically checks Python signals while running native work.

## Local build and checks

Use an existing Rust toolchain on PATH and a Python environment with the repository's
test dependencies. No models or listening service are needed.

```sh
python3 -B tools/photo_stack_native.py
PYTHONPATH=rust/photo-stack-python/target/python \
  PHOTOHOUSE_PHOTO_STACK_ENGINE=rust python3 -m pytest \
  server/tests/security/test_photo_stack_index.py \
  server/tests/security/test_photo_stack_rust.py \
  server/tests/security/test_library_photo_stacks.py \
  server/tests/security/test_library_photo_stacks_qualification.py \
  server/tests/security/test_photo_stack_worker_host.py
```

The helper copies the release library into a gitignored Python import directory.
It does not install into an ambient environment. The PyO3 adapter uses the stable
CPython ABI. Native import was checked on macOS with Python 3.12 and 3.14; Windows
and Linux binaries still need platform-specific build and runtime qualification.
There is no wheel publication or automatic runtime download.

On the shared Windows workstation, obtain fresh coordinator admission first. Use
a D: source checkout, a D: `CARGO_HOME` cache and a D: target directory. The helper
refuses other Windows cache/target roots and scopes child TEMP/TMP to that target;
it does not change machine TEMP settings. Existing compiler/interpreter binaries
may be read in place. Do not copy production data, use C: scratch, or reuse the
closed Python-only benchmark admission.

## Characterization and reproducible timing

`rust/photo-stack-core` is generated with rust-anything 2.0.2, with the Rust port in
`src/port.rs`. Its separate data-only wire seam allows exact behavior recording;
the sibling adapter adds Python cancellation without serializing callables.

```sh
PYTHONPATH=server/backend rust-anything record rust/photo-stack-core \
  --inputs rust/photo-stack-core/inputs.jsonl --count 50
PYTHONPATH=server/backend rust-anything diff rust/photo-stack-core
PYTHONPATH=server/backend rust-anything gate rust/photo-stack-core
PYTHONPATH=server/backend rust-anything bench rust/photo-stack-core
cargo clippy --manifest-path rust/photo-stack-python/Cargo.toml --all-targets -- -D warnings
python3 -B tools/photo_stack_native.py --benchmark
```

The committed recording also includes calls captured from the native contract
tests. The generated shadow module uses repository-relative source paths and can
compare the recorded seam in `RUST_ANYTHING_MODE=shadow`, returning Python results.
The application selects its backend independently through the explicit engine
setting above; it does not activate the generated shadow automatically.

The full-builder benchmark recreates the original 20,000-row fixture:
`Random(20261022)`, uniform 64-bit pHashes and `2026-10-22T08:00:00Z`. Each backend
gets one warm-up and nine sequential measured calls. Only the builder is timed;
row generation, imports and assertions are excluded, while bridge serialization
and output conversion are included. The callback-enabled variants include a
non-stopping Python callback. All runs must return zero stacks.

Local macOS arm64 / Python 3.14.8 measurements on 2026-11-20, including the bridge:

| Builder | Median wall seconds | Min–max seconds |
|---|---:|---:|
| Python | 1.846 | 1.748–2.193 |
| Rust | 0.342 | 0.335–0.358 |
| Python with cancellation callback | 1.809 | 1.797–2.416 |
| Rust with cancellation callback | 0.611 | 0.608–0.614 |

Observed median speedups were 5.41× without a callback and 2.96× with one. These
are nine-run results on a shared Mac, not a latency guarantee. The characterized
core passed 178 recorded cases, including expected refusals; the separate
callback adapter is exercised by the public-builder/worker contract tests.

The earlier native Windows Python baseline was 4.178 s median (3.952–4.474 s),
Python 3.12.10 on a Xeon W-2145. It is not a Rust measurement or a matched-hardware
comparison. This synthetic fixture stresses discovery/rejection, not real dense
photo collections. Native Windows Rust speed and installed worker acceptance
remain delivery gates. GitHub Actions remains cost-paused; all workflows remain
manual-only and must not be dispatched for this change.

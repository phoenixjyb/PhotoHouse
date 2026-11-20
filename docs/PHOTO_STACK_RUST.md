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
CPython ABI. Native import was checked on macOS with Python 3.12 and 3.14 and on
Windows x64 with Python 3.12.10 using the cross-compiled artifact described below.
Windows MSVC builds, Linux binaries and installed worker integration remain open.
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

## Native Windows comparison

The same four variants ran on Windows 11 x64 / Python 3.12.10 on 2026-11-20,
from source `163025e20456fc8bee13d0b718d81668dee0e589`. Each had one warm-up and
nine sequential measured calls with the full bridge included, using the same
20,000-row fixture described above.

| Builder | Median wall seconds | Min–max seconds | Median process CPU seconds |
|---|---:|---:|---:|
| Python | 3.802240 | 3.654861–4.255652 | 3.796875 |
| Rust | 0.661721 | 0.598461–0.711183 | 0.671875 |
| Python with cancellation callback | 3.808576 | 3.718417–4.098365 | 3.796875 |
| Rust with cancellation callback | 1.266237 | 1.194800–1.365674 | 1.265625 |

Observed median speedups were **5.75×** without a callback and **3.01×** with one.
All timing calls returned zero groups. Separately, 178 recorded kernel cases
(including 66 expected errors) and 208 public-builder parity cases (178 producing
nonempty groups) passed on Windows. Outputs, errors and exact callback counts
matched; active cancellation, the original callback exception and the exact
1,993,226-comparison budget boundary passed too.

The release extension was cross-compiled on Mac arm64 with Rust 1.98.0 and the
existing LLVM-MinGW 20261117 UCRT toolchain for `x86_64-pc-windows-gnullvm`, then
executed natively on Windows. Its SHA-256 was
`74a2741f9e3a5a3d49c243932726e7a46041aa8ae488c87dd1c696306c073bd4`.
The matching `libunwind.dll` accompanied it in the isolated benchmark directory.
This run establishes runtime behavior for that artifact; it does not qualify a
native Windows MSVC build or a distributable wheel.

The coordinator accepted the evidence and closed the bounded Windows Job,
verified the exact child/supervisor process identities absent, removed successful
executable staging and preserved results/manifests. Scratch stayed on D:; no live
library data, model execution or production activation was involved.

The earlier Windows Python-only median of 4.178 s (3.952–4.474 s) is historical;
the table above is the matched comparison for this source. This synthetic fixture
stresses discovery/rejection, not real dense photo collections or end-to-end
worker latency. Binary packaging, Linux build/runtime qualification and installed
Windows worker acceptance remain delivery gates. GitHub Actions remains
cost-paused; workflows remain manual-only and must not be dispatched for this
change.

## Preparing a native Windows candidate

Use the existing compiler and locked vendored crates in an admitted isolated D:
namespace. Build for `x86_64-pc-windows-msvc` with Cargo `--offline --locked --jobs 2`,
explicit D: Cargo home/target/TEMP, and the pinned base Python interpreter. The
Windows coordinator must enforce a Job-wide CPU cap, memory/process limits and a
timeout for the compiler and all descendants; Cargo jobs alone is not a CPU cap.
No toolchain installation or dependency download is needed on the workstation.

`tools/package_photo_stack_native.py` creates an unpublished
`cp39-abi3-win_amd64` wheel from an explicitly selected release DLL, source commit
and lock-matching vendored crates. It retains project/scaffolding notices and
checksum-verified license files for every locked registry dependency. The wheel
has deterministic members and a complete RECORD. Packaging alone does not prove
that a binary imports or that its runtime DLL dependencies are available.

Extract the wheel into a fresh directory and import it with the direct base
interpreter using `-I -S -B` and only that explicit module path. Inspect the PE
imports and kernel/policy handshake before testing. Do not install it into the
household runtime as part of qualification.

`tools/photo_stack_benchmark.py` measures generated nonempty libraries in separate
processes. `bursts` contains 12,800 rows forming 400 groups of 24 and 400 groups of
8; `mixed` contains 6,400 rows forming 400 groups of 16 across aware/naive times,
timezone offsets and unknown-time upload batches. Run both Python and Rust, with
and without callbacks, using one warm-up and nine measured calls per process.
For example, inside the admitted D: checkout:

```sh
python -I -S -B tools/photo_stack_benchmark.py --fixture bursts --engine rust \
  --native-dir D:/explicit-candidate/import --runs 9 --output D:/explicit-candidate/bursts-rust.json
```

Compare exact input/output digests and callback counts as well as time. Process
peak memory includes input generation, warm-up and all measured calls; it is not
an allocation-only kernel measurement. Cancellation records both total call time
and propagation time after the stop callback requests cancellation.

The isolated worker acceptance cohort is
`server/tests/security/test_photo_stack_worker_host.py`. It uses generated,
migrated databases/journals and checks publication/no-op, changed-source retry,
retained hash failures, locking, cancellation rollback and deletion-history
identity. Run with Rust explicitly selected and count actual native calls. Keep
failed/uncertain scratch and diagnostics; successful scratch cleanup follows Job
closure, source/result verification and coordinator release. Existing dependency
roots may be explicitly added without executing ambient `.pth`/`sitecustomize`.

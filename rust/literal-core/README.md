# Literal-search quality core

`port::quality` fuses token coverage, whole-phrase boundary and code-point length
for already-normalized ASCII/common CJK text. It returns `None` for unsupported
Unicode or inputs above 64 KiB so the Python matcher remains authoritative.
This does not change literal eligibility, normalization, provenance or ranking.

`run_batch` is only the JSON characterization adapter. The `app` dependency in
its analyzer report is the project's original Python oracle, not a missing Rust
dependency. Production uses the separate `literal-python` direct binding and
does not serialize each source through JSON. All Rust source forbids unsafe code.

The checked-in generated-data corpus is reproducible behavior evidence. From
this crate, with the local Rust tools on PATH:

```sh
CARGO_NET_OFFLINE=true rust-anything build .
rust-anything diff .
rust-anything bench .
CARGO_NET_OFFLINE=true rust-anything gate .
```

The application defaults to Python and imports no native module in that mode.
See [performance, shadow mode and qualification limits](../../docs/LITERAL_SEARCH_RUST.md).

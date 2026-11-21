# vector-core

Characterized numeric core for PhotoHouse's optional vector acceleration.
See [the integration contract](../../docs/RUST_VECTOR_KERNEL.md).

`run_batch` is a JSON/hex characterization envelope for rust-anything, not the
runtime bridge. `Kernel` implements bounded immutable byte-buffer normalization
and scoring. Production PyO3 bindings live in `../vector-python`.

```sh
python3 ../generate_vector_cases.py
rust-anything record . --inputs ../vector-inputs.jsonl
rust-anything build .
rust-anything diff .
rust-anything bench .
rust-anything shadow .
rust-anything gate .
```

Original corpus outputs and errors are immutable compatibility evidence. Shadow
and benchmark artifacts are generated locally; the application stays on Python
unless a separately qualified runtime explicitly selects the optional kernel.

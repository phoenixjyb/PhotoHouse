# Photo-stack Rust core

Generated with rust-anything 2.0.2, then implemented in `src/port.rs`.
The reference unit is `server/backend/app/access/photo_stack_reference/`;
its wire seam keeps validation and timestamp parsing in Python.

See [the integration guide](../../docs/PHOTO_STACK_RUST.md) for builds,
record/diff/gate commands, native tests and benchmarks.
The production callback adapter is the sibling `photo-stack-python` crate.

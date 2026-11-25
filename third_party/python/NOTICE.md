# Accurate summation attribution

The partial-sum accumulation and half-even correction in
`rust/vector-core/src/port.rs` are adapted from CPython 3.12.10
`Modules/mathmodule.c`, `math_fsum`:
https://github.com/python/cpython/blob/v3.12.10/Modules/mathmodule.c

Copyright (c) 2001-2023 Python Software Foundation. All Rights Reserved.
The PSF license and preceding Python notices are retained in LICENSE.txt
(the installed CPython distribution license, including later copyright years).

Changes: translate the arithmetic to safe Rust, accept finite/special f64 values
from bounded byte-buffer operations, return error codes instead of Python C API
exceptions, and retain exact half-even correction. No fast-math or fused product
substitution is used. PhotoHouse inputs and expected behavior remain unchanged.

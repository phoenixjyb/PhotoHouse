//! Small direct binding; no serialization or global text cache in the hot call.
#![forbid(unsafe_code)]
use pyo3::prelude::*;
use pyo3::types::PyString;

#[pyfunction]
fn quality(content: &Bound<'_, PyString>, phrase: &Bound<'_, PyString>) -> Option<(i64, i64, i64)> {
    // Lone surrogates are legal Python input: preserve the original fallback.
    match (content.to_cow(), phrase.to_cow()) {
        (Ok(content), Ok(phrase)) => literal_core::port::quality(&content, &phrase),
        _ => None,
    }
}

#[pymodule]
fn photohouse_literal_kernel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("POLICY_VERSION", 1)?;
    m.add_function(wrap_pyfunction!(quality, m)?)?;
    Ok(())
}

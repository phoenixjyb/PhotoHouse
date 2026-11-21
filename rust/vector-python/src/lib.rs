//! Immutable-buffer adapter. Python retains row callbacks and all scope checks.
#![forbid(unsafe_code)]
use pyo3::exceptions::{PyOverflowError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use vector_core::port::Kernel;

fn error(message: String) -> PyErr {
    if let Some(text) = message.strip_prefix("OverflowError: ") {
        PyOverflowError::new_err(text.to_owned())
    } else {
        PyValueError::new_err(
            message
                .strip_prefix("ValueError: ")
                .unwrap_or(&message)
                .to_owned(),
        )
    }
}
#[pyfunction]
fn canonicalize<'py>(
    py: Python<'py>,
    data: &[u8],
    dimension: usize,
    checksum: Py<PyAny>,
) -> PyResult<Bound<'py, PyBytes>> {
    let mut failure = None;
    let out = py.detach(|| {
        Kernel::canonicalize(
            data,
            dimension,
            cfg!(target_endian = "little"),
            &mut |index| {
                Python::attach(|py| {
                    py.check_signals()
                        .and_then(|()| checksum.call1(py, (index,)))
                        .and_then(|x| x.extract::<String>(py))
                })
                .map_err(|e| {
                    failure = Some(e);
                    "callback failure".into()
                })
            },
        )
    });
    if let Some(e) = failure {
        return Err(e);
    }
    Ok(PyBytes::new(py, &out.map_err(error)?))
}
#[pyfunction]
fn score(
    py: Python<'_>,
    data: &[u8],
    query: &[u8],
    dimension: usize,
    selected: Py<PyAny>,
) -> PyResult<Vec<(usize, f64)>> {
    let mut failure = None;
    let out = py.detach(|| {
        Kernel::score(
            data,
            query,
            dimension,
            cfg!(target_endian = "little"),
            &mut |index| {
                Python::attach(|py| {
                    py.check_signals()
                        .and_then(|()| selected.call1(py, (index,)))
                        .and_then(|x| x.extract::<bool>(py))
                })
                .map_err(|e| {
                    failure = Some(e);
                    "callback failure".into()
                })
            },
        )
    });
    if let Some(e) = failure {
        return Err(e);
    }
    out.map_err(error)
}
#[pyfunction]
fn best_seed(
    py: Python<'_>,
    data: &[u8],
    queries: &[u8],
    dimension: usize,
    observe: Py<PyAny>,
) -> PyResult<Vec<(usize, usize, f64)>> {
    let mut failure = None;
    let out = py.detach(|| {
        Kernel::best_seed(
            data,
            queries,
            dimension,
            cfg!(target_endian = "little"),
            &mut |index| {
                Python::attach(|py| {
                    py.check_signals()
                        .and_then(|()| observe.call1(py, (index,)))
                        .map(|_| ())
                })
                .map_err(|e| {
                    failure = Some(e);
                    "callback failure".into()
                })
            },
        )
    });
    if let Some(e) = failure {
        return Err(e);
    }
    out.map_err(error)
}
#[pymodule]
fn photohouse_vector_kernel(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("KERNEL_VERSION", 1)?;
    module.add("POLICY_FINGERPRINT", "canonical-f32-fsum-v1:4096:4194304")?;
    module.add_function(wrap_pyfunction!(canonicalize, module)?)?;
    module.add_function(wrap_pyfunction!(score, module)?)?;
    module.add(
        "VISUAL_POLICY_FINGERPRINT",
        "best-seed-fsum-v1:24:512:4096:4194304",
    )?;
    module.add_function(wrap_pyfunction!(best_seed, module)?)?;
    Ok(())
}

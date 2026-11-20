//! Production callback adapter for the separately characterized pure Rust core.
#![forbid(unsafe_code)]
use photo_stack_core::port::Kernel;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

#[pyfunction]
#[pyo3(signature = (payload, check=None))]
fn group(py: Python<'_>, payload: String, check: Option<Py<PyAny>>) -> PyResult<String> {
    let mut callback_error = None;
    let mut checks = 0_u64;
    let result = py.detach(|| {
        Kernel::run(&payload, &mut || {
            checks += 1;
            if check.is_none() && !checks.is_multiple_of(4096) {
                return Ok(());
            }
            Python::attach(|py| {
                let result = py.check_signals().and_then(|()| match &check {
                    Some(callback) => callback.call0(py).map(|_| ()),
                    None => Ok(()),
                });
                result.map_err(|error| {
                    callback_error = Some(error);
                    "Python cancellation or signal".to_owned()
                })
            })
        })
    });
    if let Some(error) = callback_error {
        return Err(error);
    }
    result.map_err(|message| {
        PyValueError::new_err(
            message
                .strip_prefix("ValueError: ")
                .unwrap_or(&message)
                .to_owned(),
        )
    })
}

#[pymodule]
fn photohouse_photo_stack(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add("KERNEL_VERSION", 1)?;
    module.add("POLICY_FINGERPRINT", "complete-link-v1:8:4:300:24")?;
    module.add_function(wrap_pyfunction!(group, module)?)?;
    Ok(())
}

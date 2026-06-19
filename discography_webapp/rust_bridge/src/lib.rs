use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use pyo3_asyncio::tokio::future_into_py;
use soulseek_rs::{Client, ClientSettings, SearchResult};
use std::sync::Arc;
use tokio::sync::Mutex;
use std::time::Duration;

lazy_static::lazy_static! {
    static ref CLIENT: Arc<Mutex<Option<Client>>> = Arc::new(Mutex::new(None));
}

/// An asynchronous Rust function that connects to the Soulseek network
#[pyfunction]
fn connect_to_soulseek_async<'py>(py: Python<'py>, username: String, password: String) -> PyResult<&'py PyAny> {
    future_into_py(py, async move {
        let settings = ClientSettings::new(username.clone(), password);
        let mut client = Client::with_settings(settings);

        let result = tokio::task::spawn_blocking(move || {
            client.connect();
            match client.login() {
                Ok(_) => Ok(client),
                Err(e) => Err(format!("Login failed: {}", e))
            }
        }).await.unwrap();

        match result {
            Ok(c) => {
                let mut guard = CLIENT.lock().await;
                *guard = Some(c);
                println!("Rust Engine: Authenticated and connected as {}", username);
                Ok(true)
            }
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
        }
    })
}

/// An asynchronous Rust function that performs a search on the Soulseek network
#[pyfunction]
fn rust_search_async<'py>(py: Python<'py>, query: String) -> PyResult<&'py PyAny> {
    future_into_py(py, async move {
        let client_arc = CLIENT.clone();

        let query_clone = query.clone();
        let results: Result<Vec<SearchResult>, String> = tokio::task::spawn_blocking(move || {
            let guard = client_arc.blocking_lock();
            if let Some(ref client) = *guard {
                client.search(&query_clone, Duration::from_secs(5))
                    .map_err(|e| e.to_string())
            } else {
                Err("Not connected to Soulseek".to_string())
            }
        }).await.unwrap();

        match results {
            Ok(res_list) => {
                Python::with_gil(|py| {
                    let list = PyList::empty(py);
                    for res in res_list {
                        for file in res.files {
                            let dict = PyDict::new(py);
                            dict.set_item("filename", &file.name)?;
                            dict.set_item("user", &res.username)?;
                            dict.set_item("size", file.size)?;
                            dict.set_item("speed", res.speed)?;
                            dict.set_item("slots", res.slots > 0)?;

                            // Extract bitrate from attribs if available
                            // Key 0 is often bitrate in Soulseek
                            let bitrate = file.attribs.get(&0).cloned().unwrap_or(0);
                            dict.set_item("bitrate", bitrate)?;

                            // Infer extension
                            let ext = std::path::Path::new(&file.name)
                                .extension()
                                .and_then(|s| s.to_str())
                                .map(|s| format!(".{}", s.to_lowercase()))
                                .unwrap_or_default();
                            dict.set_item("extension", ext)?;

                            list.append(dict)?;
                        }
                    }
                    Ok(list.to_object(py))
                })
            }
            Err(e) => {
                Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(format!("Search failed: {}", e)))
            }
        }
    })
}


struct TransferInner {
    is_finished: bool,
    error: Option<String>,
}

#[pyclass]
#[derive(Clone)]
pub struct RustTransfer {
    filename: String,
    inner: std::sync::Arc<std::sync::Mutex<TransferInner>>,
}

#[pymethods]
impl RustTransfer {
    #[getter]
    fn is_finished(&self) -> bool {
        self.inner.lock().unwrap().is_finished
    }

    #[getter]
    fn error(&self) -> Option<String> {
        self.inner.lock().unwrap().error.clone()
    }

    #[getter]
    fn filename(&self) -> String {
        self.filename.clone()
    }
}

/// An asynchronous Rust function that downloads a file from the Soulseek network
#[pyfunction]
fn rust_download_async<'py>(py: Python<'py>, username: String, filename: String, size: u64, download_directory: String) -> PyResult<&'py PyAny> {
    let client_arc = CLIENT.clone();

    future_into_py(py, async move {
        let result = tokio::task::spawn_blocking(move || {
            let rx = {
                let guard = client_arc.blocking_lock();
                if let Some(ref client) = *guard {
                    client.download(filename.clone(), username, size, download_directory)
                        .map_err(|e| e.to_string())
                } else {
                    Err("Not connected to Soulseek".to_string())
                }
            }?;

            let inner = std::sync::Arc::new(std::sync::Mutex::new(TransferInner {
                is_finished: false,
                error: None,
            }));

            let transfer = RustTransfer {
                filename: filename.clone(),
                inner: inner.clone(),
            };

            Ok::<_, String>((rx, inner, transfer))
        }).await.unwrap();

        match result {
            Ok((rx, inner, transfer)) => {
                // Spawn background blocking task to wait for completion
                tokio::task::spawn_blocking(move || {
                    loop {
                        match rx.recv() {
                            Ok(soulseek_rs::DownloadStatus::Completed) => {
                                let mut guard = inner.lock().unwrap();
                                guard.is_finished = true;
                                break;
                            }
                            Ok(soulseek_rs::DownloadStatus::Failed) => {
                                let mut guard = inner.lock().unwrap();
                                guard.is_finished = true;
                                guard.error = Some("Download failed".to_string());
                                break;
                            }
                            Ok(_) => continue,
                            Err(_) => {
                                let mut guard = inner.lock().unwrap();
                                guard.is_finished = true;
                                guard.error = Some("Download channel closed unexpectedly".to_string());
                                break;
                            }
                        }
                    }
                });
                Ok(transfer)
            }
            Err(e) => Err(PyErr::new::<pyo3::exceptions::PyRuntimeError, _>(e))
        }
    })
}

#[pymodule]
fn bob_soulseek_rs(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(connect_to_soulseek_async, m)?)?;
    m.add_function(wrap_pyfunction!(rust_search_async, m)?)?;
    m.add_function(wrap_pyfunction!(rust_download_async, m)?)?;
    m.add_class::<RustTransfer>()?;
    Ok(())
}

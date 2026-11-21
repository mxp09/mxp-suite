//! Comandos que la interfaz llama con `invoke(...)`.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Emitter, State};

use crate::download::{self, errors::DownloadError, CancelHandle, Request};

#[tauri::command]
pub async fn tools_status() -> Vec<crate::tools::ToolStatus> {
    tauri::async_runtime::spawn_blocking(crate::tools::check_all).await.unwrap_or_default()
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AppInfo {
    version: &'static str,
    os: String,
    data_dir: String,
    download_dir: String,
}

#[tauri::command]
pub fn app_info() -> AppInfo {
    AppInfo {
        version: env!("CARGO_PKG_VERSION"),
        os: crate::platform::os_version().0,
        data_dir: crate::paths::app_data_dir().display().to_string(),
        download_dir: crate::paths::default_download_dir().display().to_string(),
    }
}

/// Descargas en curso, por id, para poder cancelarlas.
#[derive(Default)]
pub struct Jobs {
    next: AtomicU64,
    running: Mutex<HashMap<u64, CancelHandle>>,
}

#[derive(Clone, Serialize)]
struct JobEvent<'a> {
    id: u64,
    #[serde(flatten)]
    progress: &'a download::Progress,
}

/// Lanza una descarga y devuelve su id. El progreso llega por el evento "download".
#[tauri::command]
pub fn download_start(app: AppHandle, jobs: State<'_, Jobs>, request: Request) -> u64 {
    let id = jobs.next.fetch_add(1, Ordering::Relaxed) + 1;
    let cancel = CancelHandle::default();
    jobs.running.lock().unwrap().insert(id, cancel.clone());
    std::thread::spawn(move || {
        let emit = |p: &download::Progress| {
            let _ = app.emit("download", JobEvent { id, progress: p });
        };
        download::download(&request, &cancel, &emit);
        use tauri::Manager;
        app.state::<Jobs>().running.lock().unwrap().remove(&id);
    });
    id
}

#[tauri::command]
pub fn download_cancel(jobs: State<'_, Jobs>, id: u64) {
    if let Some(c) = jobs.running.lock().unwrap().get(&id) {
        c.cancel();
    }
}

#[tauri::command]
pub async fn video_info(
    url: String,
    cookies_browser: Option<String>,
    cookies_file: Option<String>,
) -> Result<download::Info, DownloadError> {
    tauri::async_runtime::spawn_blocking(move || {
        download::info(&url, cookies_browser.as_deref(), cookies_file.as_deref().map(std::path::Path::new))
    })
    .await
    .expect("hilo de info")
}

#[derive(Serialize)]
pub struct Playlist {
    urls: Vec<String>,
    title: Option<String>,
}

#[tauri::command]
pub async fn playlist_expand(
    url: String,
    cookies_browser: Option<String>,
    cookies_file: Option<String>,
) -> Result<Playlist, DownloadError> {
    tauri::async_runtime::spawn_blocking(move || {
        download::expand_playlist(&url, cookies_browser.as_deref(), cookies_file.as_deref().map(std::path::Path::new), 500)
            .map(|(urls, title)| Playlist { urls, title })
    })
    .await
    .expect("hilo de playlist")
}

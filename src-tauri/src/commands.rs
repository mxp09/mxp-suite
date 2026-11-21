//! Comandos que la interfaz llama con `invoke(...)`.

use serde::Serialize;

#[tauri::command]
pub async fn tools_status() -> Vec<crate::tools::ToolStatus> {
    tauri::async_runtime::spawn_blocking(crate::tools::check_all).await.unwrap_or_default()
}

#[derive(Serialize)]
pub struct AppInfo {
    version: &'static str,
    os: String,
    data_dir: String,
}

#[tauri::command]
pub fn app_info() -> AppInfo {
    AppInfo {
        version: env!("CARGO_PKG_VERSION"),
        os: crate::platform::os_version().0,
        data_dir: crate::paths::app_data_dir().display().to_string(),
    }
}

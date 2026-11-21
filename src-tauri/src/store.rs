//! Ajustes e historial en %APPDATA%\MXP_Downloader, con el MISMO formato que
//! la 3.x: quien actualice conserva su carpeta, sus formatos y su historial.

use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::paths;

const HISTORY_LIMIT: usize = 100;

// Varias descargas pueden terminar a la vez: sin este cerrojo dos escrituras
// simultáneas pisaban entradas (bug real de la 3.x).
static LOCK: Mutex<()> = Mutex::new(());

fn read_json(path: &PathBuf) -> Option<Value> {
    serde_json::from_slice(&std::fs::read(path).ok()?).ok()
}

/// Escritura atómica: si se corta la luz a mitad, el archivo viejo sigue entero.
fn write_json(path: &PathBuf, value: &Value) -> std::io::Result<()> {
    let tmp = path.with_extension("json.tmp");
    std::fs::write(&tmp, serde_json::to_vec_pretty(value)?)?;
    std::fs::rename(&tmp, path)
}

fn settings_path() -> PathBuf {
    paths::app_data_dir().join("settings.json")
}

fn history_path() -> PathBuf {
    paths::app_data_dir().join("history.json")
}

/// Los ajustes son un objeto libre: la interfaz decide qué guarda.
pub fn load_settings() -> Value {
    match read_json(&settings_path()) {
        Some(v @ Value::Object(_)) => v,
        _ => Value::Object(Default::default()),
    }
}

pub fn save_settings(v: &Value) {
    let _g = LOCK.lock().unwrap();
    if let Err(e) = write_json(&settings_path(), v) {
        tracing::warn!("No se pudieron guardar los ajustes: {e}");
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct HistoryEntry {
    pub title: String,
    pub url: String,
    pub format: String,
    pub date: String,
    /// Nuevo en la 4.0: ruta del archivo, para "Abrir" desde el historial.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub file: Option<String>,
}

pub fn history() -> Vec<HistoryEntry> {
    read_json(&history_path()).and_then(|v| serde_json::from_value(v).ok()).unwrap_or_default()
}

pub fn add_history(title: &str, url: &str, format: &str, file: Option<String>) {
    let _g = LOCK.lock().unwrap();
    let mut list = history();
    list.insert(0, HistoryEntry {
        title: title.into(),
        url: url.into(),
        format: format.to_uppercase(),
        date: chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string(),
        file,
    });
    list.truncate(HISTORY_LIMIT);
    if let Ok(v) = serde_json::to_value(&list) {
        let _ = write_json(&history_path(), &v);
    }
}

pub fn clear_history() {
    let _g = LOCK.lock().unwrap();
    let _ = write_json(&history_path(), &Value::Array(vec![]));
}

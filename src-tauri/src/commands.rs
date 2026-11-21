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
        let p = download::download(&request, &cancel, &emit);
        if p.status == "finished" {
            crate::store::add_history(
                p.title.as_deref().unwrap_or("Sin título"),
                &request.url,
                &request.format,
                p.file.as_ref().map(|f| f.display().to_string()),
            );
        }
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

#[tauri::command]
pub fn settings_load() -> serde_json::Value {
    crate::store::load_settings()
}

#[tauri::command]
pub fn settings_save(settings: serde_json::Value) {
    crate::store::save_settings(&settings)
}

#[tauri::command]
pub fn history_list() -> Vec<crate::store::HistoryEntry> {
    crate::store::history()
}

#[tauri::command]
pub fn history_clear() {
    crate::store::clear_history()
}

// ── Transcripción ─────────────────────────────────────────────────────────────

use crate::transcribe::{self, export, model::Granularity, models};

#[derive(Default)]
pub struct Transcriptions {
    running: Mutex<HashMap<u64, transcribe::Cancel>>,
    done: Mutex<HashMap<u64, transcribe::model::Transcript>>,
    models: Mutex<HashMap<String, Arc<AtomicBool>>>,
}

use std::sync::atomic::AtomicBool;
use std::sync::Arc;

#[derive(Clone, Serialize)]
struct SentenceOut {
    start: f64,
    end: f64,
    text: String,
}

#[derive(Clone, Serialize)]
struct TranscriptEvent {
    id: u64,
    /// running | done | error | cancelled
    status: &'static str,
    message: String,
    percent: f64,
    source: Option<String>,
    language: Option<String>,
    duration: Option<f64>,
    sentences: Option<Vec<SentenceOut>>,
}

#[tauri::command]
pub fn transcribe_languages() -> Vec<(&'static str, &'static str)> {
    transcribe::LANGUAGES.to_vec()
}

#[tauri::command]
pub fn transcribe_start(app: AppHandle, jobs: State<'_, Jobs>, tr: State<'_, Transcriptions>, options: transcribe::Options) -> u64 {
    let id = jobs.next.fetch_add(1, Ordering::Relaxed) + 1;
    let cancel = transcribe::Cancel::default();
    tr.running.lock().unwrap().insert(id, cancel.clone());
    std::thread::spawn(move || {
        use tauri::Manager;
        let ev = |status, message: String, percent| TranscriptEvent {
            id, status, message, percent, source: None, language: None, duration: None, sentences: None,
        };
        let result = transcribe::transcribe(&options, &cancel, &|msg, pct| {
            let _ = app.emit("transcribe", ev("running", msg.to_string(), pct));
        });
        let state = app.state::<Transcriptions>();
        state.running.lock().unwrap().remove(&id);
        let out = match result {
            Ok(t) => {
                let mut e = ev("done", "Listo".into(), 100.0);
                e.sentences = Some(t.sentences().iter().map(|s| SentenceOut { start: s.start, end: s.end, text: s.text() }).collect());
                e.source = Some(t.source.clone());
                e.language = Some(t.language.clone());
                e.duration = Some(t.duration);
                state.done.lock().unwrap().insert(id, t);
                e
            }
            Err(msg) if msg == "cancelado" => ev("cancelled", msg, 0.0),
            Err(msg) => {
                tracing::error!("Transcripción fallida: {msg}");
                ev("error", msg, 0.0)
            }
        };
        let _ = app.emit("transcribe", out);
    });
    id
}

#[tauri::command]
pub fn transcribe_cancel(tr: State<'_, Transcriptions>, id: u64) {
    if let Some(c) = tr.running.lock().unwrap().get(&id) {
        c.cancel();
    }
}

/// Exporta. `edits` = texto de cada frase tal como lo dejó el usuario en el editor.
#[tauri::command]
pub fn transcribe_export(
    tr: State<'_, Transcriptions>,
    id: u64,
    format: String,
    path: String,
    granularity: Option<Granularity>,
    stamps: bool,
    edits: Option<Vec<String>>,
) -> Result<(), String> {
    let mut map = tr.done.lock().unwrap();
    let t = map.get_mut(&id).ok_or("Esa transcripción ya no está en memoria.")?;
    if let Some(e) = edits {
        t.apply_edits(&e);
    }
    let g = granularity.unwrap_or_else(|| export::default_granularity(&format));
    export::export(t, &format, std::path::Path::new(&path), g, stamps)
}

#[tauri::command]
pub fn models_list() -> Vec<models::ModelStatus> {
    models::list()
}

#[derive(Clone, Serialize)]
struct ModelEvent {
    key: String,
    /// downloading | done | error | cancelled
    status: &'static str,
    done: u64,
    total: u64,
    error: Option<String>,
}

#[tauri::command]
pub fn model_download(app: AppHandle, tr: State<'_, Transcriptions>, key: String) {
    let flag = Arc::new(AtomicBool::new(false));
    tr.models.lock().unwrap().insert(key.clone(), flag.clone());
    std::thread::spawn(move || {
        use tauri::Manager;
        let last = std::cell::Cell::new(std::time::Instant::now());
        let res = models::download(&key, &flag, &|done, total| {
            // Como mucho 4 avisos por segundo: un modelo de 3 GB son miles de trozos.
            if last.get().elapsed().as_millis() > 250 {
                last.set(std::time::Instant::now());
                let _ = app.emit("model", ModelEvent { key: key.clone(), status: "downloading", done, total, error: None });
            }
        });
        app.state::<Transcriptions>().models.lock().unwrap().remove(&key);
        let (status, error) = match res {
            Ok(()) => ("done", None),
            Err(e) if e == "cancelado" => ("cancelled", None),
            Err(e) => ("error", Some(e)),
        };
        let _ = app.emit("model", ModelEvent { key, status, done: 0, total: 0, error });
    });
}

#[tauri::command]
pub fn model_cancel(tr: State<'_, Transcriptions>, key: String) {
    if let Some(f) = tr.models.lock().unwrap().get(&key) {
        f.store(true, Ordering::Relaxed);
    }
}

#[tauri::command]
pub fn model_delete(key: String) -> Result<(), String> {
    models::delete(&key).map_err(|e| e.to_string())
}

// ── Convertir y comprimir ─────────────────────────────────────────────────────

#[derive(Default)]
pub struct MediaJobs(Mutex<HashMap<u64, crate::media::Cancel>>);

#[derive(Clone, Serialize)]
struct MediaEvent {
    id: u64,
    /// running | done | error | cancelled
    status: &'static str,
    percent: f64,
    file: Option<String>,
    error: Option<String>,
}

#[tauri::command]
pub fn media_start(app: AppHandle, jobs: State<'_, Jobs>, media: State<'_, MediaJobs>, job: crate::media::Job) -> u64 {
    let id = jobs.next.fetch_add(1, Ordering::Relaxed) + 1;
    let cancel = crate::media::Cancel::default();
    media.0.lock().unwrap().insert(id, cancel.clone());
    std::thread::spawn(move || {
        use tauri::Manager;
        let last = std::cell::Cell::new(std::time::Instant::now());
        let r = crate::media::process(&job, &cancel, &|pct| {
            if last.get().elapsed().as_millis() > 200 {
                last.set(std::time::Instant::now());
                let _ = app.emit("media", MediaEvent { id, status: "running", percent: pct * 100.0, file: None, error: None });
            }
        });
        app.state::<MediaJobs>().0.lock().unwrap().remove(&id);
        let ev = match r {
            Ok(f) => MediaEvent { id, status: "done", percent: 100.0, file: Some(f.display().to_string()), error: None },
            Err(e) if e == "cancelado" => MediaEvent { id, status: "cancelled", percent: 0.0, file: None, error: None },
            Err(e) => MediaEvent { id, status: "error", percent: 0.0, file: None, error: Some(e) },
        };
        let _ = app.emit("media", ev);
    });
    id
}

#[tauri::command]
pub fn media_cancel(media: State<'_, MediaJobs>, id: u64) {
    if let Some(c) = media.0.lock().unwrap().get(&id) {
        c.cancel();
    }
}

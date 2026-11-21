//! Descargas con yt-dlp.exe (el oficial, sin Python).
//!
//! yt-dlp corre como proceso aparte y nos habla por líneas con prefijo
//! (MXPPROG, MXPFILE…) que pedimos con --progress-template y --print. Así el
//! progreso no depende de su salida "humana", que cambia entre versiones.

pub mod errors;

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};

use serde::{Deserialize, Serialize};

use crate::platform;
use crate::tools::{self, Tool};
use errors::{classify, retry_with_fallback, DownloadError};

/// Contenedores donde yt-dlp sabe incrustar la miniatura.
const THUMBNAIL_FORMATS: &[&str] = &["mp3", "m4a", "mp4", "m4v", "mov", "mkv", "mka", "flac", "ogg", "opus"];

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    Video,
    Audio,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Request {
    pub url: String,
    pub kind: Kind,
    /// Altura máxima (1080, 720…). None = la mejor disponible.
    pub max_height: Option<u32>,
    /// mp4, mkv, webm, mov / mp3, m4a, wav, flac, opus…
    pub format: String,
    /// kbps para audio con pérdida (320, 192…).
    #[serde(default = "default_bitrate")]
    pub audio_bitrate: u32,
    pub output_dir: PathBuf,
    /// Recorte en segundos.
    pub start: Option<f64>,
    pub end: Option<f64>,
    pub cookies_browser: Option<String>,
    pub cookies_file: Option<PathBuf>,
}

fn default_bitrate() -> u32 {
    320
}

#[derive(Clone, Debug, Serialize, Default)]
#[serde(rename_all = "camelCase")]
pub struct Progress {
    /// fetching | downloading | processing | finished | error | cancelled
    pub status: &'static str,
    pub percent: f64,
    /// Bytes por segundo.
    pub speed: Option<f64>,
    /// Segundos restantes.
    pub eta: Option<f64>,
    pub title: Option<String>,
    pub file: Option<PathBuf>,
    pub error: Option<DownloadError>,
}

/// Rutas de las herramientas que yt-dlp necesita.
pub struct Toolset {
    pub yt_dlp: PathBuf,
    pub ffmpeg: Option<PathBuf>,
    pub deno: Option<PathBuf>,
}

impl Toolset {
    pub fn resolve() -> Result<Self, DownloadError> {
        let yt = tools::check(Tool::YtDlp);
        let Some(yt_dlp) = yt.path else {
            return Err(DownloadError {
                category: "engine_missing",
                message: "El motor de descarga no funciona en este PC.".into(),
                hint: format!(
                    "Motivo: {}. Reinstala MXP Suite para repararlo.",
                    yt.problem.unwrap_or_else(|| "desconocido".into())
                ),
                raw: String::new(),
            });
        };
        Ok(Toolset { yt_dlp, ffmpeg: tools::check(Tool::Ffmpeg).path, deno: tools::check(Tool::Deno).path })
    }
}

/// Argumentos comunes a toda llamada a yt-dlp.
fn base_args(t: &Toolset, cookies_browser: Option<&str>, cookies_file: Option<&Path>, evasive: bool) -> Vec<String> {
    let mut a: Vec<String> = vec![
        // Ni configuraciones del usuario ni avisos de actualización: siempre igual.
        "--ignore-config".into(),
        "--no-update".into(),
        "--encoding".into(), "utf-8".into(),
        "--socket-timeout".into(), "30".into(),
        // Un corte momentáneo o un 5xx pasajero no debe tumbar la descarga.
        "--retries".into(), "5".into(),
        "--fragment-retries".into(), "10".into(),
        "--extractor-retries".into(), "3".into(),
        "--retry-sleep".into(), "http:exp=1:30".into(),
        "--sleep-requests".into(), "0.5".into(),
    ];
    if let Some(ff) = &t.ffmpeg {
        a.push("--ffmpeg-location".into());
        a.push(ff.display().to_string());
    }
    // Runtime JS para los retos de YouTube: sin él hay menos formatos o 403.
    if let Some(deno) = &t.deno {
        a.push("--js-runtimes".into());
        a.push(format!("deno:{}", deno.display()));
    }
    if let Some(b) = cookies_browser.filter(|b| !b.is_empty()) {
        a.push("--cookies-from-browser".into());
        a.push(b.to_string());
    }
    if let Some(f) = cookies_file.filter(|f| f.is_file()) {
        a.push("--cookies".into());
        a.push(f.display().to_string());
    }
    if evasive {
        // Segunda pasada tras un 403/bot-check: otros clientes de reproducción
        // y parecer Chrome a nivel TLS (el yt-dlp.exe oficial trae curl_cffi).
        a.push("--extractor-args".into());
        a.push("youtube:player_client=tv,web_safari,android_vr".into());
        a.push("--impersonate".into());
        a.push("chrome".into());
    }
    a
}

/// Argumentos de una descarga completa. Función pura: se prueba sin red.
pub fn download_args(r: &Request, t: &Toolset, evasive: bool) -> Vec<String> {
    let mut a = base_args(t, r.cookies_browser.as_deref(), r.cookies_file.as_deref(), evasive);
    let fmt = r.format.to_lowercase();

    match r.kind {
        Kind::Audio => {
            a.extend(["-f".into(), "bestaudio/best".into(), "-x".into(), "--audio-format".into(), fmt.clone()]);
            a.extend(["--audio-quality".into(), format!("{}K", r.audio_bitrate)]);
        }
        Kind::Video => {
            // WEBM solo admite VP9/AV1 + Opus: pedir H.264/AAC y unirlos en
            // .webm fallaba con "Conversion failed" en la 3.x.
            let (v, au) = if fmt == "webm" { ("webm", "webm") } else { ("mp4", "m4a") };
            let h = r.max_height.map(|h| format!("[height<={h}]")).unwrap_or_default();
            a.push("-f".into());
            a.push(format!("bestvideo{h}[ext={v}]+bestaudio[ext={au}]/bestvideo{h}+bestaudio/best{h}/bestvideo+bestaudio/best"));
            a.push("-S".into());
            a.push(if fmt == "webm" { "res,vcodec:vp9,acodec:opus,tbr" } else { "res,vcodec:h264,acodec:aac,tbr" }.into());
            a.push("--merge-output-format".into());
            a.push(fmt.clone());
        }
    }

    a.push("--embed-metadata".into());
    if THUMBNAIL_FORMATS.contains(&fmt.as_str()) {
        a.push("--embed-thumbnail".into());
    }
    if r.start.is_some() || r.end.is_some() {
        // yt-dlp baja SOLO ese tramo y corta en el fotograma exacto.
        let s = r.start.unwrap_or(0.0);
        let e = r.end.map(|e| e.to_string()).unwrap_or_else(|| "inf".into());
        a.push("--download-sections".into());
        a.push(format!("*{s}-{e}"));
        a.push("--force-keyframes-at-cuts".into());
    }

    a.extend([
        "--no-playlist".into(),
        "--no-overwrites".into(),
        "--no-mtime".into(),
        "--windows-filenames".into(),
        // Nombre largo + carpeta profunda superaba los 260 caracteres.
        "--trim-filenames".into(), "150".into(),
        "-N".into(), "4".into(),
        "-o".into(), r.output_dir.join("%(title)s.%(ext)s").display().to_string(),
        "--quiet".into(), "--progress".into(), "--newline".into(),
        "--progress-template".into(),
        "download:MXPPROG %(progress.{status,downloaded_bytes,total_bytes,total_bytes_estimate,speed,eta})j".into(),
        "--progress-template".into(),
        "postprocess:MXPPP %(progress.status)s".into(),
        "--print".into(), "before_dl:MXPTITLE %(title)s".into(),
        "--print".into(), "after_move:MXPFILE %(filepath)s".into(),
        "--".into(),
        r.url.clone(),
    ]);
    a
}

fn command(t: &Toolset, args: &[String]) -> Command {
    let mut cmd = Command::new(&t.yt_dlp);
    cmd.args(args)
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());
    platform::hide_console(&mut cmd);
    cmd
}

/// Proceso en curso, para poder cancelarlo desde otro hilo.
#[derive(Clone, Default)]
pub struct CancelHandle {
    inner: Arc<Mutex<(bool, Option<u32>)>>,
}

impl CancelHandle {
    pub fn cancel(&self) {
        let mut g = self.inner.lock().unwrap();
        g.0 = true;
        if let Some(pid) = g.1 {
            // yt-dlp lanza ffmpeg: hay que cerrar el árbol entero, no solo el padre.
            platform::kill_tree(pid);
        }
    }
    pub fn is_cancelled(&self) -> bool {
        self.inner.lock().unwrap().0
    }
    fn set_pid(&self, pid: Option<u32>) {
        self.inner.lock().unwrap().1 = pid;
    }
}

#[derive(Deserialize)]
struct RawProgress {
    status: Option<String>,
    downloaded_bytes: Option<f64>,
    total_bytes: Option<f64>,
    total_bytes_estimate: Option<f64>,
    speed: Option<f64>,
    eta: Option<f64>,
}

/// Interpreta una línea de salida. Devuelve None si no es nuestra.
fn parse_line(line: &str, p: &mut Progress) -> bool {
    if let Some(json) = line.strip_prefix("MXPPROG ") {
        let Ok(raw) = serde_json::from_str::<RawProgress>(json) else { return false };
        if raw.status.as_deref() == Some("finished") {
            p.status = "processing";
            p.percent = 100.0;
        } else {
            let total = raw.total_bytes.or(raw.total_bytes_estimate).unwrap_or(0.0);
            p.status = "downloading";
            if total > 0.0 {
                p.percent = (raw.downloaded_bytes.unwrap_or(0.0) / total * 100.0).min(100.0);
            }
            p.speed = raw.speed;
            p.eta = raw.eta;
        }
        true
    } else if line.starts_with("MXPPP ") {
        p.status = "processing";
        p.percent = 100.0;
        true
    } else if let Some(t) = line.strip_prefix("MXPTITLE ") {
        p.title = Some(t.to_string());
        true
    } else if let Some(f) = line.strip_prefix("MXPFILE ") {
        p.file = Some(PathBuf::from(f));
        true
    } else {
        false
    }
}

/// Una pasada completa. Ok(Progress final) o el error de yt-dlp ya clasificado.
fn run_once(
    t: &Toolset,
    args: &[String],
    cancel: &CancelHandle,
    on: &dyn Fn(&Progress),
) -> Result<Progress, DownloadError> {
    let mut child: Child = command(t, args).spawn().map_err(|e| classify(&e.to_string()))?;
    cancel.set_pid(Some(child.id()));

    // stderr en otro hilo para que no se llene el búfer y bloquee a yt-dlp.
    let stderr = child.stderr.take().expect("stderr");
    let err_thread = std::thread::spawn(move || {
        BufReader::new(stderr).lines().map_while(Result::ok).collect::<Vec<_>>()
    });

    let mut p = Progress { status: "fetching", ..Default::default() };
    on(&p);
    for line in BufReader::new(child.stdout.take().expect("stdout")).lines().map_while(Result::ok) {
        if parse_line(line.trim_end(), &mut p) {
            on(&p);
        }
    }
    let status = child.wait().map_err(|e| classify(&e.to_string()))?;
    cancel.set_pid(None);
    let stderr_lines = err_thread.join().unwrap_or_default();

    if status.success() {
        return Ok(p);
    }
    // Lo más útil es la última línea "ERROR:"; si no hay, la última línea a secas.
    let raw = stderr_lines
        .iter()
        .rev()
        .find(|l| l.contains("ERROR"))
        .or_else(|| stderr_lines.last())
        .cloned()
        .unwrap_or_else(|| format!("yt-dlp terminó con código {:?}", status.code()));
    tracing::warn!("yt-dlp falló: {}", stderr_lines.join(" | "));
    Err(classify(&raw))
}

/// Descarga completa con reintento evasivo. `on` recibe cada actualización.
pub fn download(r: &Request, cancel: &CancelHandle, on: &dyn Fn(&Progress)) -> Progress {
    let finish = |p: Progress| {
        on(&p);
        p
    };
    let t = match Toolset::resolve() {
        Ok(t) => t,
        Err(e) => return finish(Progress { status: "error", error: Some(e), ..Default::default() }),
    };
    if let Err(e) = std::fs::create_dir_all(&r.output_dir) {
        return finish(Progress { status: "error", error: Some(classify(&e.to_string())), ..Default::default() });
    }

    let before = list_dir(&r.output_dir);
    let first = run_once(&t, &download_args(r, &t, false), cancel, on);
    let result = match first {
        Err(e) if !cancel.is_cancelled() && retry_with_fallback(&e) => {
            tracing::info!("Reintento evasivo tras: {}", e.raw);
            on(&Progress { status: "fetching", title: Some("Reintentando con otro método…".into()), ..Default::default() });
            // Si el reintento también falla, se informa del error ORIGINAL: es
            // el que explica qué pasa (en la 3.2.0 el segundo lo tapaba).
            run_once(&t, &download_args(r, &t, true), cancel, on).map_err(|_| e)
        }
        other => other,
    };

    if cancel.is_cancelled() {
        remove_partials(&r.output_dir, &before);
        return finish(Progress { status: "cancelled", ..Default::default() });
    }
    match result {
        Ok(mut p) => {
            p.status = "finished";
            p.percent = 100.0;
            finish(p)
        }
        Err(e) => {
            tracing::error!("Descarga fallida {}: {}", r.url, e.raw);
            finish(Progress { status: "error", error: Some(e), ..Default::default() })
        }
    }
}

fn list_dir(dir: &Path) -> std::collections::HashSet<PathBuf> {
    std::fs::read_dir(dir)
        .map(|rd| rd.filter_map(|e| e.ok().map(|e| e.path())).collect())
        .unwrap_or_default()
}

/// Tras cancelar, borra los restos a medias que dejó yt-dlp (.part, .ytdl,
/// fragmentos). Solo archivos nuevos y con esas extensiones: nunca toca lo
/// que ya estaba ni lo que bajan otras descargas de la cola a la vez.
fn remove_partials(dir: &Path, before: &std::collections::HashSet<PathBuf>) {
    for path in list_dir(dir).difference(before) {
        let name = path.file_name().unwrap_or_default().to_string_lossy().to_lowercase();
        if name.ends_with(".part") || name.ends_with(".ytdl") || name.contains(".part-frag") {
            let _ = std::fs::remove_file(path);
        }
    }
}

/// Metadatos para la vista previa (título, miniatura, duración…).
#[derive(Debug, Serialize, Deserialize, Default)]
pub struct Info {
    pub title: Option<String>,
    pub thumbnail: Option<String>,
    pub duration: Option<f64>,
    pub uploader: Option<String>,
    pub extractor_key: Option<String>,
    pub webpage_url: Option<String>,
}

fn run_json(t: &Toolset, args: Vec<String>) -> Result<serde_json::Value, DownloadError> {
    let out = command(t, &args).output().map_err(|e| classify(&e.to_string()))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        let line = err.lines().rev().find(|l| l.contains("ERROR")).or(err.lines().last()).unwrap_or("");
        return Err(classify(line));
    }
    serde_json::from_slice(&out.stdout).map_err(|e| classify(&e.to_string()))
}

pub fn info(url: &str, cookies_browser: Option<&str>, cookies_file: Option<&Path>) -> Result<Info, DownloadError> {
    let t = Toolset::resolve()?;
    let mut first_err = None;
    for evasive in [false, true] {
        let mut a = base_args(&t, cookies_browser, cookies_file, evasive);
        a.extend(["-J".into(), "--no-playlist".into(), "--".into(), url.into()]);
        match run_json(&t, a) {
            Ok(v) => return serde_json::from_value(v).map_err(|e| classify(&e.to_string())),
            Err(e) => {
                let retry = !evasive && retry_with_fallback(&e);
                first_err.get_or_insert(e);
                if !retry {
                    break;
                }
            }
        }
    }
    Err(first_err.expect("hubo al menos un intento"))
}

/// URLs de una playlist o canal (solo el índice, sin resolver cada vídeo).
pub fn expand_playlist(
    url: &str,
    cookies_browser: Option<&str>,
    cookies_file: Option<&Path>,
    limit: usize,
) -> Result<(Vec<String>, Option<String>), DownloadError> {
    let t = Toolset::resolve()?;
    let mut a = base_args(&t, cookies_browser, cookies_file, false);
    a.extend(["-J".into(), "--flat-playlist".into(), "--playlist-end".into(), limit.to_string(), "--".into(), url.into()]);
    let v = run_json(&t, a)?;
    let title = v.get("title").and_then(|x| x.as_str()).map(String::from);
    let Some(entries) = v.get("entries").and_then(|e| e.as_array()) else {
        return Ok((vec![url.to_string()], title));
    };
    let urls = entries
        .iter()
        .filter_map(|e| e.get("url").or_else(|| e.get("webpage_url")).and_then(|u| u.as_str()).map(String::from))
        .collect();
    Ok((urls, title))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn toolset() -> Toolset {
        Toolset { yt_dlp: "yt-dlp.exe".into(), ffmpeg: Some("C:\\bin\\ffmpeg.exe".into()), deno: None }
    }

    fn request(kind: Kind, format: &str) -> Request {
        Request {
            url: "https://youtu.be/x".into(),
            kind,
            max_height: Some(1080),
            format: format.into(),
            audio_bitrate: 320,
            output_dir: "C:\\Users\\Iván\\Descargas".into(),
            start: None,
            end: None,
            cookies_browser: None,
            cookies_file: None,
        }
    }

    #[test]
    fn video_mp4_args() {
        let a = download_args(&request(Kind::Video, "MP4"), &toolset(), false);
        let f = &a[a.iter().position(|x| x == "-f").unwrap() + 1];
        assert!(f.starts_with("bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"));
        assert!(a.contains(&"--embed-thumbnail".to_string()));
        assert!(!a.contains(&"--impersonate".to_string()));
        // La URL va siempre tras "--": una URL que empiece por "-" no se toma por opción.
        assert_eq!(a[a.len() - 2], "--");
    }

    #[test]
    fn webm_uses_vp9_and_no_thumbnail_in_wav() {
        let a = download_args(&request(Kind::Video, "webm"), &toolset(), false);
        assert!(a.iter().any(|x| x.contains("[ext=webm]+bestaudio[ext=webm]")));
        let a = download_args(&request(Kind::Audio, "wav"), &toolset(), false);
        assert!(!a.contains(&"--embed-thumbnail".to_string()));
        assert!(a.contains(&"--audio-format".to_string()));
    }

    #[test]
    fn trim_and_evasive() {
        let mut r = request(Kind::Video, "mp4");
        r.start = Some(10.0);
        r.end = Some(25.5);
        let a = download_args(&r, &toolset(), true);
        assert!(a.contains(&"*10-25.5".to_string()));
        assert!(a.contains(&"--impersonate".to_string()));
    }

    #[test]
    fn progress_lines() {
        let mut p = Progress::default();
        assert!(parse_line(r#"MXPPROG {"status": "downloading", "downloaded_bytes": 50, "total_bytes": 200, "speed": 1000.0, "eta": 3}"#, &mut p));
        assert_eq!((p.status, p.percent), ("downloading", 25.0));
        assert!(parse_line("MXPTITLE Canción — ñandú", &mut p));
        assert_eq!(p.title.as_deref(), Some("Canción — ñandú"));
        assert!(parse_line("MXPFILE C:\\Users\\Iván\\a b.mp4", &mut p));
        assert!(!parse_line("[youtube] algo", &mut p));
    }
}

#[cfg(test)]
mod net_tests {
    //! Necesitan internet y vendor/bin: `cargo test -- --ignored`.
    use super::*;

    #[test]
    #[ignore]
    fn info_of_url_with_mix_list() {
        let i = info("https://www.youtube.com/watch?v=R0kBGOYid_o&list=RDR0kBGOYid_o", None, None).unwrap();
        assert!(i.title.unwrap().contains("Farruko"));
    }

    #[test]
    #[ignore]
    fn cancel_stops_download() {
        let dir = std::env::temp_dir().join("mxp-cancel-test");
        let r = Request {
            url: "https://www.youtube.com/watch?v=R0kBGOYid_o".into(),
            kind: Kind::Video,
            max_height: Some(1080),
            format: "mp4".into(),
            audio_bitrate: 320,
            output_dir: dir,
            start: None,
            end: None,
            cookies_browser: None,
            cookies_file: None,
        };
        let cancel = CancelHandle::default();
        let c2 = cancel.clone();
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_secs(8));
            c2.cancel();
        });
        let t0 = std::time::Instant::now();
        let p = download(&r, &cancel, &|_| {});
        assert_eq!(p.status, "cancelled");
        assert!(t0.elapsed().as_secs() < 20, "tardó {:?} en cancelar", t0.elapsed());
    }
}

//! Transcripción local con whisper.cpp (whisper-cli oficial, en proceso aparte).
//!
//! Decisiones medidas en la 3.2 que se mantienen:
//!  · sin --vad: con VAD los tiempos por palabra salían corridos;
//!  · sin -dtw: exige desactivar flash-attention y no mejoraba los tiempos.

pub mod export;
pub mod model;
pub mod models;

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

use serde::Deserialize;

use crate::download::{self, CancelHandle, Kind, Request};
use crate::platform;
use crate::tools::{self, Tool};
use model::{Transcript, Word};

pub const LANGUAGES: &[(&str, &str)] = &[
    ("auto", "Detectar automáticamente"), ("es", "Español"), ("en", "English"), ("pt", "Português"),
    ("fr", "Français"), ("de", "Deutsch"), ("it", "Italiano"), ("ca", "Català"), ("nl", "Nederlands"),
    ("pl", "Polski"), ("ru", "Русский"), ("ja", "日本語"), ("zh", "中文"), ("ko", "한국어"), ("ar", "العربية"),
];

#[derive(Clone, Debug, Deserialize)]
pub struct Options {
    /// Ruta local o URL.
    pub source: String,
    pub model: String,
    #[serde(default = "auto")]
    pub language: String,
    #[serde(default)]
    pub translate: bool,
    #[serde(default)]
    pub prompt: String,
    pub cookies_browser: Option<String>,
    pub cookies_file: Option<PathBuf>,
}

fn auto() -> String {
    "auto".into()
}

/// Cancelación compartida con el proceso en curso (yt-dlp, ffmpeg o whisper).
#[derive(Clone, Default)]
pub struct Cancel {
    flag: Arc<AtomicBool>,
    download: CancelHandle,
    pid: Arc<std::sync::Mutex<Option<u32>>>,
}

impl Cancel {
    pub fn cancel(&self) {
        self.flag.store(true, Ordering::Relaxed);
        self.download.cancel();
        if let Some(pid) = *self.pid.lock().unwrap() {
            platform::kill_tree(pid);
        }
    }
    pub fn is_set(&self) -> bool {
        self.flag.load(Ordering::Relaxed)
    }
}

/// Carpeta temporal que se borra sola al terminar, pase lo que pase.
struct TempDir(PathBuf);
impl TempDir {
    fn new() -> std::io::Result<Self> {
        static N: std::sync::atomic::AtomicU32 = std::sync::atomic::AtomicU32::new(0);
        let p = std::env::temp_dir().join(format!("mxp_tr_{}_{}", std::process::id(), N.fetch_add(1, Ordering::Relaxed)));
        std::fs::create_dir_all(&p)?;
        Ok(TempDir(p))
    }
}
impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn is_url(s: &str) -> bool {
    s.starts_with("http://") || s.starts_with("https://")
}

fn to_wav(src: &Path, dst: &Path) -> Result<(), String> {
    let ffmpeg = tools::check(Tool::Ffmpeg).path.ok_or("FFmpeg no funciona en este PC; reinstala MXP Suite.")?;
    let mut cmd = Command::new(ffmpeg);
    cmd.args(["-y", "-loglevel", "error", "-i"]).arg(src).args(["-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le"]).arg(dst);
    platform::hide_console(&mut cmd);
    let out = cmd.output().map_err(|e| e.to_string())?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        return Err(format!("No se pudo leer el audio: {}", err.lines().last().unwrap_or("formato no reconocido")));
    }
    Ok(())
}

#[derive(Deserialize)]
struct WhisperJson {
    result: Option<WhisperResult>,
    #[serde(default)]
    transcription: Vec<Segment>,
}
#[derive(Deserialize)]
struct WhisperResult {
    language: Option<String>,
}
#[derive(Deserialize)]
struct Segment {
    #[serde(default)]
    tokens: Vec<Token>,
}
#[derive(Deserialize)]
struct Token {
    text: String,
    offsets: Offsets,
    #[serde(default = "one")]
    p: f32,
}
#[derive(Deserialize)]
struct Offsets {
    from: i64,
    to: i64,
}
fn one() -> f32 {
    1.0
}

/// Tokens de whisper → palabras. Un token con espacio inicial abre palabra nueva.
fn tokens_to_words(segments: Vec<Segment>) -> Vec<Word> {
    let mut words: Vec<Word> = Vec::new();
    for tok in segments.into_iter().flat_map(|s| s.tokens) {
        if tok.text.is_empty() || tok.text.starts_with("[_") {
            continue; // [_BEG_], [_TT_123]… marcas internas
        }
        let (start, end) = (tok.offsets.from as f64 / 1000.0, tok.offsets.to as f64 / 1000.0);
        match words.last_mut() {
            Some(last) if !tok.text.starts_with(' ') => {
                last.text.push_str(&tok.text);
                last.end = last.end.max(end);
                last.p = last.p.min(tok.p);
            }
            _ => words.push(Word { start, end, text: tok.text, p: tok.p }),
        }
    }
    words
}

pub fn transcribe(o: &Options, cancel: &Cancel, progress: &dyn Fn(&str, f64)) -> Result<Transcript, String> {
    let whisper = tools::check(Tool::Whisper);
    let cli = whisper.path.ok_or_else(|| {
        format!("El motor de transcripción no funciona en este PC ({}). Reinstala MXP Suite.", whisper.problem.unwrap_or_default())
    })?;
    let m = models::find(&o.model).ok_or("Modelo desconocido.")?;
    if !models::is_installed(m) {
        return Err(format!("El modelo {} no está descargado.", m.name));
    }
    let work = TempDir::new().map_err(|e| e.to_string())?;

    // 1. Origen: si es una URL se baja solo el audio, con las mismas opciones
    //    (cookies, Deno, reintentos) que una descarga normal.
    let (source, title, audio_path) = if is_url(&o.source) {
        let req = Request {
            url: o.source.clone(),
            kind: Kind::Audio,
            max_height: None,
            format: "m4a".into(),
            audio_bitrate: 192,
            output_dir: work.0.clone(),
            start: None,
            end: None,
            cookies_browser: o.cookies_browser.clone(),
            cookies_file: o.cookies_file.clone(),
        };
        let p = download::download(&req, &cancel.download, &|p| {
            if p.status == "downloading" {
                progress("Descargando el audio…", p.percent * 0.25);
            }
        });
        match (p.status, p.file) {
            ("finished", Some(f)) => (f, p.title.unwrap_or_else(|| o.source.clone()), None),
            ("cancelled", _) => return Err("cancelado".into()),
            _ => return Err(p.error.map(|e| e.full_text()).unwrap_or_else(|| "No se pudo bajar el audio.".into())),
        }
    } else {
        let p = PathBuf::from(&o.source);
        if !p.is_file() {
            return Err("El archivo ya no está en su sitio.".into());
        }
        let name = p.file_name().unwrap_or_default().to_string_lossy().to_string();
        (p.clone(), name, Some(p.display().to_string()))
    };
    if cancel.is_set() {
        return Err("cancelado".into());
    }

    // 2. A WAV de 16 kHz mono, que es lo que espera whisper.
    progress("Preparando el audio…", 27.0);
    let wav = work.0.join("audio16k.wav");
    to_wav(&source, &wav)?;
    let duration = (std::fs::metadata(&wav).map(|m| m.len()).unwrap_or(44).saturating_sub(44)) as f64 / 32000.0;

    // 3. whisper-cli. Hilos: los núcleos disponibles, máximo 8 (más no acelera).
    let threads = std::thread::available_parallelism().map(|n| n.get().min(8)).unwrap_or(4);
    let out_base = work.0.join("out");
    let mut cmd = Command::new(&cli);
    cmd.arg("-m").arg(models::path(m)).arg("-f").arg(&wav).args(["-l", &o.language, "-ojf", "-pp", "-np", "-t", &threads.to_string(), "-of"]).arg(&out_base);
    if o.translate {
        cmd.arg("-tr");
    }
    if !o.prompt.trim().is_empty() {
        cmd.args(["--prompt", o.prompt.trim()]);
    }
    cmd.stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::piped());
    platform::hide_console(&mut cmd);
    let mut child = cmd.spawn().map_err(|e| format!("No se pudo iniciar el motor de transcripción: {e}"))?;
    *cancel.pid.lock().unwrap() = Some(child.id());
    let re = regex::Regex::new(r"progress\s*=\s*(\d+)%").expect("regex");
    let mut tail: Vec<String> = Vec::new();
    for line in BufReader::new(child.stderr.take().expect("stderr")).lines().map_while(Result::ok) {
        if let Some(c) = re.captures(&line) {
            let pct: f64 = c[1].parse().unwrap_or(0.0);
            progress("Transcribiendo…", 30.0 + pct * 0.7);
        } else if !line.trim().is_empty() {
            tail.push(line);
            if tail.len() > 5 {
                tail.remove(0);
            }
        }
    }
    let status = child.wait().map_err(|e| e.to_string())?;
    *cancel.pid.lock().unwrap() = None;
    if cancel.is_set() {
        return Err("cancelado".into());
    }
    let json_path = out_base.with_extension("json");
    if !status.success() || !json_path.is_file() {
        let why = platform::explain_exit_code(status.code().unwrap_or(0)).map(str::to_string).unwrap_or_else(|| tail.join(" "));
        tracing::error!("whisper-cli falló ({:?}): {}", status.code(), tail.join(" | "));
        return Err(format!("La transcripción falló: {why}"));
    }
    let data: WhisperJson = serde_json::from_slice(&std::fs::read(&json_path).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
    progress("Listo", 100.0);
    Ok(Transcript {
        words: tokens_to_words(data.transcription),
        language: data.result.and_then(|r| r.language).unwrap_or_else(|| o.language.clone()),
        source: title,
        audio_path,
        duration,
        edits: vec![],
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tokens_join_into_words() {
        let json = r#"{"result":{"language":"es"},"transcription":[{"tokens":[
            {"text":"[_BEG_]","offsets":{"from":0,"to":0},"p":1.0},
            {"text":" Hol","offsets":{"from":0,"to":200},"p":0.9},
            {"text":"a","offsets":{"from":200,"to":400},"p":0.8},
            {"text":" mundo","offsets":{"from":400,"to":900},"p":0.95}]}]}"#;
        let data: WhisperJson = serde_json::from_str(json).unwrap();
        let words = tokens_to_words(data.transcription);
        assert_eq!(words.len(), 2);
        assert_eq!(words[0].text, " Hola");
        assert_eq!((words[0].end, words[0].p), (0.4, 0.8));
    }
}

//! Herramientas externas (ffmpeg, ffprobe, yt-dlp, deno).
//!
//! Regla de la casa desde la 3.x: una herramienta no cuenta como instalada
//! porque el archivo exista, sino porque **se ejecuta y responde**. Y si no
//! responde, se dice por qué en palabras que entienda cualquiera.

use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::Duration;

use serde::Serialize;
use wait_timeout::ChildExt;

use crate::{paths, platform};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Tool {
    Ffmpeg,
    Ffprobe,
    YtDlp,
    Deno,
    Whisper,
}

impl Tool {
    pub const ALL: [Tool; 5] = [Tool::Ffmpeg, Tool::Ffprobe, Tool::YtDlp, Tool::Deno, Tool::Whisper];

    pub fn exe(self) -> &'static str {
        match self {
            Tool::Ffmpeg => "ffmpeg.exe",
            Tool::Ffprobe => "ffprobe.exe",
            Tool::YtDlp => "yt-dlp.exe",
            Tool::Deno => "deno.exe",
            // Va en su propia carpeta con sus DLL (ggml, runtime de VC++).
            Tool::Whisper => "whisper/whisper-cli.exe",
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Tool::Ffmpeg => "FFmpeg (conversión de video y audio)",
            Tool::Ffprobe => "FFprobe (lectura de archivos de video)",
            Tool::YtDlp => "Motor de descarga (yt-dlp)",
            Tool::Deno => "Deno (necesario para YouTube)",
            Tool::Whisper => "Motor de transcripción (whisper.cpp)",
        }
    }

    fn version_args(self) -> &'static [&'static str] {
        match self {
            Tool::Ffmpeg | Tool::Ffprobe => &["-version"],
            Tool::YtDlp => &["--version"],
            Tool::Deno | Tool::Whisper => &["--version"],
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct ToolStatus {
    pub tool: Tool,
    pub label: &'static str,
    pub ok: bool,
    pub path: Option<PathBuf>,
    pub version: Option<String>,
    /// Por qué no funciona, en lenguaje llano. None si funciona.
    pub problem: Option<String>,
}

/// Sitios donde buscar, por orden. El PATH del sistema NO se usa a propósito:
/// en la 3.x un ffmpeg viejo del usuario podía colarse y romper conversiones.
///
/// Manda la copia del instalador, salvo yt-dlp: ese se actualiza solo (los
/// sitios cambian cada pocas semanas) y su copia nueva vive en la carpeta del
/// usuario. La otra carpeta queda de reserva si la primera falla.
fn candidates(tool: Tool) -> Vec<PathBuf> {
    let user = paths::user_bin_dir().join(tool.exe());
    let bundled = paths::bundled_bin_dir().join(tool.exe());
    if tool == Tool::YtDlp { vec![user, bundled] } else { vec![bundled, user] }
}

/// Ejecuta `exe args` y devuelve la primera línea de salida, o el motivo del fallo.
pub fn probe(exe: &Path, args: &[&str], timeout: Duration) -> Result<String, String> {
    if !exe.is_file() {
        return Err("no está el archivo (¿lo borró el antivirus?)".into());
    }
    let mut cmd = Command::new(exe);
    cmd.args(args).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    platform::hide_console(&mut cmd);
    let mut child = cmd.spawn().map_err(|e| explain_spawn_error(&e))?;
    let status = match child.wait_timeout(timeout).map_err(|e| e.to_string())? {
        Some(s) => s,
        None => {
            let _ = child.kill();
            return Err(format!("no respondió en {} s", timeout.as_secs()));
        }
    };
    let out = child.wait_with_output().map_err(|e| e.to_string())?;
    if !status.success() {
        let code = status.code().unwrap_or(-1);
        return Err(platform::explain_exit_code(code)
            .map(str::to_string)
            .unwrap_or_else(|| format!("terminó con error (código {code:#x})")));
    }
    // Unos escriben la versión por stdout y otros (whisper-cli) por stderr.
    let text = format!("{}
{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    let line = text.lines().find(|l| l.to_lowercase().contains("version")).or_else(|| text.lines().find(|l| !l.trim().is_empty()));
    Ok(line.unwrap_or("").trim().to_string())
}

fn explain_spawn_error(e: &std::io::Error) -> String {
    match e.raw_os_error() {
        Some(2) | Some(3) => "no está el archivo (¿lo borró el antivirus?)".into(),
        Some(5) => "Windows no deja ejecutarlo (permisos o antivirus)".into(),
        Some(193) => "el archivo está dañado o incompleto".into(),
        Some(225) => "el antivirus lo ha bloqueado como amenaza".into(),
        Some(1260) => "una directiva de Windows impide ejecutarlo".into(),
        _ => format!("no se pudo ejecutar ({e})"),
    }
}

/// Primera versión que funciona de la herramienta. Si ninguna, el motivo de la última.
pub fn check(tool: Tool) -> ToolStatus {
    let mut last_problem = None;
    for path in candidates(tool) {
        match probe(&path, tool.version_args(), Duration::from_secs(20)) {
            Ok(version) => {
                return ToolStatus {
                    tool,
                    label: tool.label(),
                    ok: true,
                    path: Some(path),
                    version: Some(version),
                    problem: None,
                }
            }
            // Que no exista en la carpeta de usuario es lo normal; solo cuenta
            // el motivo si de verdad había algo que no arrancó.
            Err(p) if path.is_file() || last_problem.is_none() => last_problem = Some(p),
            Err(_) => {}
        }
    }
    tracing::warn!("{} no disponible: {:?}", tool.exe(), last_problem);
    ToolStatus { tool, label: tool.label(), ok: false, path: None, version: None, problem: last_problem }
}

pub fn check_all() -> Vec<ToolStatus> {
    // En paralelo: arrancar ffmpeg/yt-dlp en frío tarda ~1 s cada uno.
    let handles: Vec<_> = Tool::ALL.iter().map(|&t| std::thread::spawn(move || check(t))).collect();
    handles.into_iter().map(|h| h.join().expect("hilo de comprobación")).collect()
}

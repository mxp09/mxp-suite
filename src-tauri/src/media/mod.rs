//! Convertir y comprimir video, audio e imágenes con FFmpeg.
//! Port de core/engines/video_audio.py, images.py y gpu.py de la 3.x.

pub mod gpu;

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};

use serde::Deserialize;

use crate::platform;
use crate::tools::{self, Tool};

pub const VIDEO_EXT: &[&str] = &["mp4", "mkv", "mov", "avi", "webm", "wmv", "flv", "m4v", "mpg", "mpeg", "3gp", "ts", "mts"];
pub const AUDIO_EXT: &[&str] = &["mp3", "wav", "flac", "m4a", "aac", "ogg", "opus", "wma", "aiff", "alac"];
pub const IMAGE_EXT: &[&str] = &["jpg", "jpeg", "png", "webp", "avif", "bmp", "tif", "tiff", "heic", "heif", "gif"];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MediaType {
    Video,
    Audio,
    Image,
}

pub fn media_type(path: &Path) -> Option<MediaType> {
    let ext = path.extension()?.to_string_lossy().to_lowercase();
    if VIDEO_EXT.contains(&ext.as_str()) {
        Some(MediaType::Video)
    } else if AUDIO_EXT.contains(&ext.as_str()) {
        Some(MediaType::Audio)
    } else if IMAGE_EXT.contains(&ext.as_str()) {
        Some(MediaType::Image)
    } else {
        None
    }
}

#[derive(Clone, Debug, Deserialize)]
pub struct Job {
    pub input: PathBuf,
    /// Formato destino: "mp4", "mp4 (hevc)", "webm (av1)", "mp3", "webp"…
    /// Vacío = el mismo formato que el original (comprimir sin convertir).
    #[serde(default)]
    pub format: String,
    /// none | medium | high | extreme
    #[serde(default = "none")]
    pub level: String,
    /// Peso máximo en MB (WhatsApp, Discord…). Solo video.
    pub target_mb: Option<f64>,
    /// None = junto al original.
    pub output_dir: Option<PathBuf>,
}

fn none() -> String {
    "none".into()
}

/// Proceso ffmpeg en curso, para poder cancelarlo.
#[derive(Clone, Default)]
pub struct Cancel(Arc<Mutex<(bool, Option<u32>)>>);

impl Cancel {
    pub fn cancel(&self) {
        let mut g = self.0.lock().unwrap();
        g.0 = true;
        if let Some(pid) = g.1 {
            platform::kill_tree(pid);
        }
    }
    fn is_set(&self) -> bool {
        self.0.lock().unwrap().0
    }
}

fn ffmpeg() -> Result<PathBuf, String> {
    tools::check(Tool::Ffmpeg).path.ok_or_else(|| "FFmpeg no funciona en este PC; reinstala MXP Suite.".into())
}

fn hms(s: &str) -> Option<f64> {
    let p: Vec<f64> = s.trim().split(':').map(|x| x.parse().ok()).collect::<Option<_>>()?;
    (p.len() == 3).then(|| p[0] * 3600.0 + p[1] * 60.0 + p[2])
}

/// La línea de ffmpeg que de verdad explica el fallo.
fn relevant_error(lines: &[String]) -> String {
    let keys = ["Error", "error", "Invalid", "No such", "failed", "unable", "Unknown encoder", "not supported"];
    lines
        .iter()
        .rev()
        .find(|l| keys.iter().any(|k| l.contains(k)))
        .or(lines.last())
        .cloned()
        .unwrap_or_else(|| "error desconocido".into())
}

/// Ejecuta ffmpeg informando del avance (0–1) a partir de "Duration" y "time=".
fn run(args: &[String], cancel: &Cancel, on: &dyn Fn(f64)) -> Result<(), String> {
    let mut cmd = Command::new(ffmpeg()?);
    cmd.args(args).stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::piped());
    platform::hide_console(&mut cmd);
    let mut child = cmd.spawn().map_err(|e| e.to_string())?;
    cancel.0.lock().unwrap().1 = Some(child.id());
    let (mut total, mut lines) = (None, Vec::new());
    let re_dur = regex::Regex::new(r"Duration:\s*([\d:.]+)").unwrap();
    let re_time = regex::Regex::new(r"time=\s*([\d:.]+)").unwrap();
    // ffmpeg separa el progreso con \r: se leen trozos y se parte por ambos.
    let mut reader = BufReader::new(child.stderr.take().expect("stderr"));
    let mut buf = Vec::new();
    while reader.read_until(b'\r', &mut buf).map(|n| n > 0).unwrap_or(false) {
        for line in String::from_utf8_lossy(&buf).split(['\r', '\n']).filter(|l| !l.trim().is_empty()) {
            if total.is_none() {
                total = re_dur.captures(line).and_then(|c| hms(&c[1]));
            }
            if let (Some(t), Some(c)) = (total, re_time.captures(line)) {
                if let Some(cur) = hms(&c[1]) {
                    on((cur / t).clamp(0.0, 1.0));
                }
            }
            lines.push(line.to_string());
            if lines.len() > 40 {
                lines.remove(0);
            }
        }
        buf.clear();
    }
    let status = child.wait().map_err(|e| e.to_string())?;
    cancel.0.lock().unwrap().1 = None;
    if cancel.is_set() {
        return Err("cancelado".into());
    }
    if status.success() {
        Ok(())
    } else {
        Err(relevant_error(&lines))
    }
}

fn s(v: &[&str]) -> Vec<String> {
    v.iter().map(|x| x.to_string()).collect()
}

/// Nombre de salida que nunca pisa un archivo existente: "video_comprimido (2).mp4".
fn output_path(job: &Job, suffix: &str, ext: &str) -> PathBuf {
    let dir = job.output_dir.clone().unwrap_or_else(|| job.input.parent().map(Path::to_path_buf).unwrap_or_default());
    let stem = job.input.file_stem().unwrap_or_default().to_string_lossy();
    let mut p = dir.join(format!("{stem}{suffix}.{ext}"));
    let mut n = 2;
    while p.exists() {
        p = dir.join(format!("{stem}{suffix} ({n}).{ext}"));
        n += 1;
    }
    p
}

fn duration_of(input: &Path) -> Option<f64> {
    let probe = tools::check(Tool::Ffprobe).path?;
    let mut cmd = Command::new(probe);
    cmd.args(["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]).arg(input);
    platform::hide_console(&mut cmd);
    String::from_utf8_lossy(&cmd.output().ok()?.stdout).trim().parse().ok()
}

/// CRF y escalado por nivel de compresión (los mismos de la 3.x).
fn level_params(level: &str) -> (&'static str, Option<&'static str>) {
    match level {
        "medium" => ("28", None),
        "high" => ("32", Some("scale='min(1280,iw)':-2")),
        "extreme" => ("36", Some("scale='min(854,iw)':-2")),
        _ => ("22", None),
    }
}

fn video(job: &Job, cancel: &Cancel, on: &dyn Fn(f64)) -> Result<PathBuf, String> {
    let src_ext = job.input.extension().unwrap_or_default().to_string_lossy().to_lowercase();
    let fmt = if job.format.is_empty() { src_ext.clone() } else { job.format.to_lowercase() };
    if let Some(mb) = job.target_mb {
        return video_to_size(job, mb, cancel, on);
    }
    // Video → MP3/WAV/…: sacar el audio, que es lo que se busca.
    if AUDIO_EXT.contains(&fmt.as_str()) {
        return audio(job, cancel, on);
    }
    let (container, codec) = match fmt.as_str() {
        "mp4 (hevc)" => ("mp4", "hevc"),
        "webm" => ("webm", "vp9"),
        "webm (av1)" => ("webm", "av1"),
        "gif" => ("gif", "gif"),
        other => (other, "h264"),
    };
    let suffix = if job.level == "none" { "" } else { "_comprimido" };
    let out = output_path(job, suffix, container);
    if codec == "gif" {
        // GIF: 12 fps y 480 px con paleta propia; si no, pesa una barbaridad.
        let args = vec!["-y".into(), "-i".into(), job.input.display().to_string(), "-vf".into(),
            "fps=12,scale='min(480,iw)':-2:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse".into(), out.display().to_string()];
        return run(&args, cancel, on).map(|_| out);
    }
    let (crf, scale) = level_params(&job.level);
    let audio: Vec<String> = match codec {
        "vp9" | "av1" => s(&["-c:a", "libopus", "-b:a", "128k"]),
        _ => s(&["-c:a", "aac", "-b:a", "160k"]),
    };
    // GPU primero si respondió en la detección; la CPU siempre de reserva.
    let mut encoders: Vec<&str> = gpu::best_encoder(codec).into_iter().collect();
    encoders.push(gpu::cpu_encoder(codec));
    let mut last = String::new();
    for enc in encoders {
        let mut args = vec!["-y".into(), "-i".into(), job.input.display().to_string(), "-c:v".into(), enc.into()];
        args.extend(gpu::encoder_args(enc, crf));
        if let Some(f) = scale {
            args.extend(s(&["-vf", f]));
        }
        if container == "mp4" || container == "mov" {
            args.extend(s(&["-movflags", "+faststart"])); // que empiece a reproducirse antes de bajarse entero
        }
        args.extend(audio.clone());
        args.push(out.display().to_string());
        match run(&args, cancel, on) {
            Ok(()) => return Ok(out),
            Err(e) if e == "cancelado" => return Err(e),
            Err(e) => {
                tracing::warn!("{enc} falló, se prueba el siguiente: {e}");
                let _ = std::fs::remove_file(&out);
                last = e;
            }
        }
    }
    Err(last)
}

/// Clava el tamaño: bitrate calculado desde la duración y 2 pasadas (libx264).
fn video_to_size(job: &Job, target_mb: f64, cancel: &Cancel, on: &dyn Fn(f64)) -> Result<PathBuf, String> {
    let duration = duration_of(&job.input).ok_or("No se pudo leer la duración del video.")?;
    let audio_kbps = 96.0;
    // 4 % de margen para el contenedor y la variación del encoder.
    let video_kbps = (target_mb * 8.0 * 1024.0 * 0.96 / duration - audio_kbps).floor();
    if video_kbps < 80.0 {
        return Err(format!("El video es demasiado largo ({:.0} min) para caber en {target_mb} MB. Recórtalo o elige un tamaño mayor.", duration / 60.0));
    }
    let out = output_path(job, &format!("_{}MB", target_mb.round()), "mp4");
    let passlog = std::env::temp_dir().join(format!("mxp_2pass_{}", std::process::id()));
    let common: Vec<String> = vec![
        "-c:v".into(), "libx264".into(), "-preset".into(), "medium".into(), "-b:v".into(), format!("{video_kbps}k"),
        "-vf".into(), "scale='min(1280,iw)':-2".into(), "-passlogfile".into(), passlog.display().to_string(),
    ];
    let input = job.input.display().to_string();
    let mut p1 = vec!["-y".into(), "-i".into(), input.clone()];
    p1.extend(common.clone());
    p1.extend(s(&["-pass", "1", "-an", "-f", "null", "NUL"]));
    let mut p2 = vec!["-y".into(), "-i".into(), input];
    p2.extend(common);
    p2.extend(s(&["-pass", "2", "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart"]));
    p2.push(out.display().to_string());
    let r = run(&p1, cancel, &|x| on(x / 2.0)).and_then(|_| run(&p2, cancel, &|x| on(0.5 + x / 2.0)));
    for ext in ["-0.log", "-0.log.mbtree"] {
        let _ = std::fs::remove_file(format!("{}{ext}", passlog.display()));
    }
    r.map(|_| out)
}

fn audio(job: &Job, cancel: &Cancel, on: &dyn Fn(f64)) -> Result<PathBuf, String> {
    let src_ext = job.input.extension().unwrap_or_default().to_string_lossy().to_lowercase();
    let fmt = if job.format.is_empty() { src_ext } else { job.format.to_lowercase() };
    let bitrate = match job.level.as_str() {
        "medium" => "160k",
        "high" => "128k",
        "extreme" => "96k",
        _ => "320k",
    };
    let codec: Vec<String> = match fmt.as_str() {
        "mp3" => s(&["-c:a", "libmp3lame", "-b:a", bitrate]),
        "wav" => s(&["-c:a", "pcm_s16le"]),
        "flac" => s(&["-c:a", "flac"]),
        "m4a" | "aac" => s(&["-c:a", "aac", "-b:a", if bitrate == "320k" { "256k" } else { bitrate }]),
        "ogg" | "opus" => s(&["-c:a", "libopus", "-b:a", if bitrate == "320k" { "192k" } else { bitrate }]),
        other => return Err(format!("Formato de audio no soportado: {other}")),
    };
    let out = output_path(job, if job.level == "none" { "" } else { "_comprimido" }, &fmt);
    let mut args = vec!["-y".into(), "-i".into(), job.input.display().to_string(), "-vn".into()];
    args.extend(codec);
    args.push(out.display().to_string());
    run(&args, cancel, on).map(|_| out)
}

fn image(job: &Job, cancel: &Cancel, on: &dyn Fn(f64)) -> Result<PathBuf, String> {
    let src_ext = job.input.extension().unwrap_or_default().to_string_lossy().to_lowercase();
    let mut fmt = if job.format.is_empty() { src_ext } else { job.format.to_lowercase() };
    if fmt == "jpeg" {
        fmt = "jpg".into();
    }
    if fmt == "heic" || fmt == "heif" {
        // FFmpeg lee HEIC (fotos de iPhone) pero no lo escribe: se guarda en JPG.
        fmt = "jpg".into();
    }
    let quality = match job.level.as_str() {
        "medium" => 70,
        "high" => 50,
        "extreme" => 30,
        _ => 90,
    };
    let mut args = vec!["-y".into(), "-i".into(), job.input.display().to_string(), "-frames:v".into(), "1".into()];
    match fmt.as_str() {
        // -q:v de JPG va de 2 (mejor) a 31 (peor).
        "jpg" => args.extend(["-q:v".into(), (2 + (100 - quality) * 29 / 100).to_string()]),
        "webp" => args.extend(["-c:v".into(), "libwebp".into(), "-quality".into(), quality.to_string()]),
        "avif" => args.extend(["-c:v".into(), "libaom-av1".into(), "-still-picture".into(), "1".into(), "-crf".into(), (63 - quality * 63 / 100).to_string()]),
        "png" => args.extend(s(&["-compression_level", "9"])),
        "bmp" | "tif" | "tiff" | "gif" => {}
        other => return Err(format!("Formato de imagen no soportado: {other}")),
    }
    if quality < 60 && job.level != "none" {
        args.extend(s(&["-vf", "scale='min(1920,iw)':-2"]));
    }
    let out = output_path(job, if job.level == "none" { "" } else { "_comprimido" }, &fmt);
    args.push(out.display().to_string());
    run(&args, cancel, on).map(|_| out)
}

pub fn process(job: &Job, cancel: &Cancel, on: &dyn Fn(f64)) -> Result<PathBuf, String> {
    if !job.input.is_file() {
        return Err("El archivo ya no está en su sitio.".into());
    }
    let r = match media_type(&job.input) {
        Some(MediaType::Video) => video(job, cancel, on),
        Some(MediaType::Audio) => audio(job, cancel, on),
        Some(MediaType::Image) => image(job, cancel, on),
        None => Err("Tipo de archivo no reconocido.".into()),
    };
    if let Err(e) = &r {
        if e != "cancelado" {
            tracing::error!("Conversión fallida {}: {e}", job.input.display());
        }
    }
    r
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn types_and_names() {
        assert_eq!(media_type(Path::new("a.MP4")), Some(MediaType::Video));
        assert_eq!(media_type(Path::new("a.heic")), Some(MediaType::Image));
        assert_eq!(media_type(Path::new("a.txt")), None);
        assert_eq!(hms("00:01:02.50"), Some(62.5));
    }

    #[test]
    fn output_never_overwrites() {
        let dir = std::env::temp_dir().join("mxp out ñ");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("v_comprimido.mp4"), b"x").unwrap();
        let job = Job { input: dir.join("v.mov"), format: "mp4".into(), level: "high".into(), target_mb: None, output_dir: None };
        assert_eq!(output_path(&job, "_comprimido", "mp4"), dir.join("v_comprimido (2).mp4"));
        let _ = std::fs::remove_dir_all(&dir);
    }
}

#[cfg(test)]
mod ffmpeg_tests {
    //! Necesitan vendor/bin: `MXP_TOOLS_DIR=… cargo test -- --ignored`.
    use super::*;

    fn make_clip(dir: &Path) -> PathBuf {
        let clip = dir.join("clip prueba.mov");
        let args = s(&["-y", "-f", "lavfi", "-i", "testsrc=s=1280x720:d=4", "-f", "lavfi", "-i", "sine=d=4", "-shortest", "-c:v", "libx264", "-c:a", "aac"]);
        let mut a = args;
        a.push(clip.display().to_string());
        run(&a, &Cancel::default(), &|_| {}).unwrap();
        clip
    }

    #[test]
    #[ignore]
    fn convert_compress_image_audio() {
        let dir = std::env::temp_dir().join("mxp media ñandú");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let clip = make_clip(&dir);
        let job = |format: &str, level: &str, mb: Option<f64>| Job { input: clip.clone(), format: format.into(), level: level.into(), target_mb: mb, output_dir: None };
        for j in [job("mp4", "none", None), job("webm", "high", None), job("", "none", Some(1.0)), job("gif", "none", None)] {
            let out = process(&j, &Cancel::default(), &|_| {}).unwrap_or_else(|e| panic!("{j:?}: {e}"));
            assert!(out.metadata().unwrap().len() > 1000, "{out:?}");
        }
        let sized = dir.join("clip prueba_1MB.mp4");
        assert!(sized.metadata().unwrap().len() <= 1024 * 1024, "no cupo en 1 MB");
        // Audio e imagen a partir del mismo clip.
        let mp3 = process(&Job { input: clip.clone(), format: "mp3".into(), ..job("", "none", None) }, &Cancel::default(), &|_| {}).unwrap();
        assert_eq!(mp3.extension().unwrap(), "mp3");
        let png = dir.join("frame.png");
        run(&vec!["-y".into(), "-i".into(), clip.display().to_string(), "-frames:v".into(), "1".into(), png.display().to_string()], &Cancel::default(), &|_| {}).unwrap();
        for fmt in ["jpg", "webp", "avif"] {
            let out = process(&Job { input: png.clone(), format: fmt.into(), level: "medium".into(), target_mb: None, output_dir: None }, &Cancel::default(), &|_| {})
                .unwrap_or_else(|e| panic!("{fmt}: {e}"));
            assert!(out.is_file());
        }
        let _ = std::fs::remove_dir_all(&dir);
    }
}

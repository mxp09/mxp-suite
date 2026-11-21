//! ¿Hay encoder de GPU que funcione? No se adivina por la marca: se prueba
//! codificando de verdad un clip mínimo, y solo se confía en el que responde.
//! El resultado se guarda una semana en gpu.json (por si cambias de tarjeta).

use std::collections::HashMap;
use std::process::{Command, Stdio};
use std::sync::OnceLock;
use std::time::{Duration, SystemTime};

use serde::{Deserialize, Serialize};
use wait_timeout::ChildExt;

use crate::{paths, platform, tools};

const CANDIDATES: &[(&str, &[&str])] = &[
    ("h264", &["h264_nvenc", "h264_qsv", "h264_amf"]),
    ("hevc", &["hevc_nvenc", "hevc_qsv", "hevc_amf"]),
    ("av1", &["av1_nvenc", "av1_qsv", "av1_amf"]),
];
const CACHE_MAX_AGE: Duration = Duration::from_secs(7 * 24 * 3600);

pub fn cpu_encoder(codec: &str) -> &'static str {
    match codec {
        "hevc" => "libx265",
        "av1" => "libsvtav1",
        "vp9" => "libvpx-vp9",
        _ => "libx264",
    }
}

/// Parámetros de calidad/velocidad correctos para cada encoder.
pub fn encoder_args(encoder: &str, q: &str) -> Vec<String> {
    let v: Vec<&str> = match encoder {
        "libsvtav1" => vec!["-preset", "8", "-crf", q],
        "libvpx-vp9" => vec!["-b:v", "0", "-crf", q, "-row-mt", "1", "-deadline", "good", "-cpu-used", "4"],
        e if e.ends_with("_nvenc") => vec!["-preset", "p4", "-rc", "vbr", "-cq", q],
        e if e.ends_with("_qsv") => vec!["-global_quality", q],
        e if e.ends_with("_amf") => vec!["-quality", "balanced", "-rc", "cqp", "-qp_i", q, "-qp_p", q],
        _ => vec!["-preset", "veryfast", "-crf", q],
    };
    v.into_iter().map(String::from).collect()
}

#[derive(Serialize, Deserialize, Default)]
struct Cache {
    checked_at: u64,
    working: HashMap<String, String>,
}

/// 320×240 a propósito: con 64×64 AMF daba un falso "no hay GPU" (resolución
/// por debajo de su mínimo), medido en una RX 6700 XT real en la 3.x.
fn probe(encoder: &str) -> bool {
    let Some(ff) = tools::check(tools::Tool::Ffmpeg).path else { return false };
    let mut cmd = Command::new(ff);
    cmd.args(["-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:s=320x240:d=0.2", "-frames:v", "5", "-c:v", encoder, "-f", "null", "-"])
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    platform::hide_console(&mut cmd);
    let Ok(mut child) = cmd.spawn() else { return false };
    match child.wait_timeout(Duration::from_secs(8)) {
        Ok(Some(s)) => s.success(),
        _ => {
            let _ = child.kill();
            false
        }
    }
}

fn detect() -> HashMap<String, String> {
    let path = paths::app_data_dir().join("gpu-encoders.json");
    let now = SystemTime::now().duration_since(SystemTime::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    if let Some(c) = std::fs::read(&path).ok().and_then(|b| serde_json::from_slice::<Cache>(&b).ok()) {
        if now.saturating_sub(c.checked_at) < CACHE_MAX_AGE.as_secs() {
            return c.working;
        }
    }
    let mut working = HashMap::new();
    for (codec, encoders) in CANDIDATES {
        if let Some(e) = encoders.iter().find(|e| probe(e)) {
            working.insert(codec.to_string(), e.to_string());
        }
    }
    tracing::info!("Encoders de GPU que responden: {working:?}");
    let _ = std::fs::write(&path, serde_json::to_vec(&Cache { checked_at: now, working: working.clone() }).unwrap_or_default());
    working
}

pub fn best_encoder(codec: &str) -> Option<&'static str> {
    static CELL: OnceLock<HashMap<String, String>> = OnceLock::new();
    let found = CELL.get_or_init(detect).get(codec)?;
    CANDIDATES.iter().flat_map(|(_, e)| e.iter()).find(|e| *e == found).copied()
}

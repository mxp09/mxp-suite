//! Modelos de Whisper: catálogo, cuáles hay en disco y descarga verificada.
//! Mismo catálogo y misma carpeta que la 3.x: los modelos ya bajados sirven.

use std::io::{Read, Write};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};

use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::paths;

const HF_BASE: &str = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/";

#[derive(Clone, Copy, Serialize)]
pub struct ModelInfo {
    pub key: &'static str,
    pub file: &'static str,
    pub bytes: u64,
    #[serde(skip)]
    pub sha256: &'static str,
    pub name: &'static str,
    pub description: &'static str,
}

pub const MODELS: &[ModelInfo] = &[
    ModelInfo { key: "tiny", file: "ggml-tiny.bin", bytes: 77_691_713,
        sha256: "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
        name: "Tiny", description: "Pruebas o PCs muy lentos (poca precisión)" },
    ModelInfo { key: "base", file: "ggml-base.bin", bytes: 147_951_465,
        sha256: "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
        name: "Base", description: "Rápido, voz clara y notas" },
    ModelInfo { key: "small", file: "ggml-small.bin", bytes: 487_601_967,
        sha256: "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
        name: "Small", description: "Equilibrado" },
    ModelInfo { key: "turbo-q5", file: "ggml-large-v3-turbo-q5_0.bin", bytes: 574_041_195,
        sha256: "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2",
        name: "Large-v3-turbo comprimido", description: "Recomendado: casi la máxima precisión, rápido en CPU" },
    ModelInfo { key: "medium", file: "ggml-medium.bin", bytes: 1_533_763_059,
        sha256: "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208",
        name: "Medium", description: "Alta precisión, más lento (pesado)" },
    ModelInfo { key: "turbo", file: "ggml-large-v3-turbo.bin", bytes: 1_624_555_275,
        sha256: "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69",
        name: "Large-v3-turbo", description: "Precisión máxima a buena velocidad (pesado)" },
    ModelInfo { key: "large", file: "ggml-large-v3.bin", bytes: 3_095_033_483,
        sha256: "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2",
        name: "Large-v3", description: "Precisión máxima, el más lento (pesado)" },
];

pub const DEFAULT_MODEL: &str = "turbo-q5";

pub fn find(key: &str) -> Option<&'static ModelInfo> {
    MODELS.iter().find(|m| m.key == key)
}

pub fn path(m: &ModelInfo) -> PathBuf {
    paths::models_dir().join(m.file)
}

/// Instalado = está y con el tamaño exacto (una descarga cortada no cuenta).
pub fn is_installed(m: &ModelInfo) -> bool {
    std::fs::metadata(path(m)).map(|md| md.len() == m.bytes).unwrap_or(false)
}

#[derive(Serialize)]
pub struct ModelStatus {
    #[serde(flatten)]
    pub info: ModelInfo,
    pub installed: bool,
}

pub fn list() -> Vec<ModelStatus> {
    MODELS.iter().map(|m| ModelStatus { info: *m, installed: is_installed(m) }).collect()
}

pub fn delete(key: &str) -> std::io::Result<()> {
    match find(key) {
        Some(m) if path(m).exists() => std::fs::remove_file(path(m)),
        _ => Ok(()),
    }
}

/// Descarga por streaming (hasta 3 GB) con reanudación: si se corta la red,
/// el siguiente intento sigue donde se quedó en vez de empezar de cero.
/// El hash se comprueba siempre sobre el archivo completo.
pub fn download(key: &str, cancel: &AtomicBool, progress: &dyn Fn(u64, u64)) -> Result<(), String> {
    let m = find(key).ok_or("modelo desconocido")?;
    let final_path = path(m);
    let part = final_path.with_extension("bin.part");

    let mut have = std::fs::metadata(&part).map(|md| md.len()).unwrap_or(0);
    if have > m.bytes {
        let _ = std::fs::remove_file(&part);
        have = 0;
    }
    if have < m.bytes {
        let url = format!("{HF_BASE}{}", m.file);
        let mut req = ureq::get(&url);
        if have > 0 {
            req = req.header("Range", &format!("bytes={have}-"));
        }
        let resp = req.call().map_err(|e| crate::net::explain(&e))?;
        // 206 = el servidor acepta continuar; 200 = manda el archivo entero.
        if resp.status() == 200 {
            have = 0;
        }
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .write(true)
            .append(have > 0)
            .truncate(have == 0)
            .open(&part)
            .map_err(|e| format!("no se puede escribir el modelo: {e}"))?;
        let mut body = resp.into_body().into_reader();
        let mut buf = vec![0u8; 1 << 20];
        loop {
            if cancel.load(Ordering::Relaxed) {
                return Err("cancelado".into());
            }
            let n = body.read(&mut buf).map_err(|e| format!("se cortó la descarga: {e}"))?;
            if n == 0 {
                break;
            }
            file.write_all(&buf[..n]).map_err(|e| format!("no se puede escribir el modelo: {e}"))?;
            have += n as u64;
            progress(have, m.bytes);
        }
    }

    let mut hasher = Sha256::new();
    let mut f = std::fs::File::open(&part).map_err(|e| e.to_string())?;
    std::io::copy(&mut f, &mut hasher).map_err(|e| e.to_string())?;
    drop(f);
    if format!("{:x}", hasher.finalize()) != m.sha256 {
        let _ = std::fs::remove_file(&part);
        return Err(format!("{}: la descarga no coincide con su hash publicado; vuelve a intentarlo", m.name));
    }
    std::fs::rename(&part, &final_path).map_err(|e| e.to_string())
}

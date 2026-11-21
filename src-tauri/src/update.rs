//! Actualizaciones: de la app (instalador nuevo) y del motor yt-dlp.
//!
//! App: mismo contrato que la 3.x (mxp_common/updater.py) para que ambas
//! convivan en el repo compartido: solo cuentan los releases con un
//! instalador "MXP_Downloader_Setup*.exe", y nada se ejecuta si su SHA-256 no
//! coincide con el SHA256SUMS.txt publicado (falla en cerrado).
//!
//! yt-dlp: los sitios cambian cada pocas semanas; un motor viejo = errores
//! 403. Se comprueba como mucho cada 6 h y la copia nueva va a la carpeta del
//! usuario (la del instalador puede no ser escribible).

use std::io::Read;
use std::path::PathBuf;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::{net, paths, tools};

const REPO: &str = "mxp09/mxp-suite";
const ASSET_PREFIX: &str = "MXP_Downloader_Setup";
const CHECK_EVERY: Duration = Duration::from_secs(6 * 3600);

fn now() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

fn agent() -> ureq::Agent {
    net::agent(Some(Duration::from_secs(120)))
}

fn get_text(url: &str) -> Result<String, String> {
    agent().get(url).call().map_err(|e| net::explain(&e))?.into_body().read_to_string().map_err(|e| e.to_string())
}

fn get_bytes(url: &str, max: u64) -> Result<Vec<u8>, String> {
    let mut v = Vec::new();
    agent()
        .get(url)
        .call()
        .map_err(|e| net::explain(&e))?
        .into_body()
        .into_reader()
        .take(max)
        .read_to_end(&mut v)
        .map_err(|e| format!("se cortó la descarga: {e}"))?;
    Ok(v)
}

fn sha256_hex(data: &[u8]) -> String {
    format!("{:x}", Sha256::digest(data))
}

/// Busca el hash de `name` en un archivo de sumas "hash  nombre".
fn find_sum(sums: &str, name: &str) -> Option<String> {
    sums.lines().find_map(|l| {
        let mut it = l.split_whitespace();
        let (h, n) = (it.next()?, it.next()?);
        (n.trim_start_matches('*') == name).then(|| h.trim_start_matches('\u{feff}').to_lowercase())
    })
}

fn parse_version(s: &str) -> Vec<u64> {
    s.split('.').map(|p| p.parse().unwrap_or(0)).collect()
}

pub fn is_newer(candidate: &str, current: &str) -> bool {
    let (mut a, mut b) = (parse_version(candidate), parse_version(current));
    let n = a.len().max(b.len());
    a.resize(n, 0);
    b.resize(n, 0);
    a > b
}

// ── App ──────────────────────────────────────────────────────────────────────

#[derive(Clone, Debug, Serialize)]
pub struct UpdateInfo {
    pub version: String,
    pub notes: String,
    pub size: u64,
    #[serde(skip)]
    url: String,
    #[serde(skip)]
    asset: String,
    #[serde(skip)]
    sums_url: Option<String>,
}

#[derive(Deserialize)]
struct Release {
    tag_name: String,
    #[serde(default)]
    body: Option<String>,
    #[serde(default)]
    draft: bool,
    #[serde(default)]
    prerelease: bool,
    assets: Vec<Asset>,
}
#[derive(Deserialize)]
struct Asset {
    name: String,
    browser_download_url: String,
    size: u64,
}

fn parse_release(r: Release) -> Option<UpdateInfo> {
    if r.draft || r.prerelease {
        return None;
    }
    let installer = r.assets.iter().find(|a| a.name.starts_with(ASSET_PREFIX) && a.name.to_lowercase().ends_with(".exe"))?;
    let re = regex::Regex::new(r"(\d+(?:\.\d+)+)").unwrap();
    let version = re.captures(&r.tag_name).or_else(|| re.captures(&installer.name))?[1].to_string();
    Some(UpdateInfo {
        version,
        notes: r.body.unwrap_or_default().trim().to_string(),
        size: installer.size,
        url: installer.browser_download_url.clone(),
        asset: installer.name.clone(),
        sums_url: r.assets.iter().find(|a| a.name == "SHA256SUMS.txt").map(|a| a.browser_download_url.clone()),
    })
}

/// La versión más nueva publicada para esta app, si es más nueva que la actual.
pub fn check_app() -> Result<Option<UpdateInfo>, String> {
    let body = get_text(&format!("https://api.github.com/repos/{REPO}/releases?per_page=30"))?;
    let releases: Vec<Release> = serde_json::from_str(&body).map_err(|e| e.to_string())?;
    let best = releases
        .into_iter()
        .filter_map(parse_release)
        .filter(|u| is_newer(&u.version, env!("CARGO_PKG_VERSION")))
        .max_by(|a, b| parse_version(&a.version).cmp(&parse_version(&b.version)));
    Ok(best)
}

/// Descarga el instalador, lo verifica y lo lanza. Quien llame debe cerrar la
/// app justo después (no se puede sobrescribir un .exe en ejecución).
pub fn install_app(u: &UpdateInfo) -> Result<(), String> {
    let sums_url = u.sums_url.as_ref().ok_or("El release no trae SHA256SUMS.txt: no se instala nada sin verificar.")?;
    let expected = find_sum(&get_text(sums_url)?, &u.asset).ok_or("El instalador no aparece en SHA256SUMS.txt.")?;
    let data = get_bytes(&u.url, 2 << 30)?;
    if sha256_hex(&data) != expected {
        return Err("La descarga no coincide con la firma publicada y se ha descartado. Inténtalo más tarde.".into());
    }
    let dest = std::env::temp_dir().join(&u.asset);
    std::fs::write(&dest, data).map_err(|e| e.to_string())?;
    std::process::Command::new(&dest).spawn().map_err(|e| format!("No se pudo abrir el instalador: {e}"))?;
    Ok(())
}

// ── yt-dlp ───────────────────────────────────────────────────────────────────

#[derive(Serialize, Deserialize, Default)]
struct EngineState {
    last_check: u64,
}

fn state_path() -> PathBuf {
    paths::app_data_dir().join("engine-update.json")
}

/// Actualiza yt-dlp si hay versión nueva. Devuelve la versión instalada si
/// actualizó. Sin red o si algo falla, no pasa nada: se sigue con el que hay.
pub fn update_ytdlp_if_stale(force: bool) -> Result<Option<String>, String> {
    let mut st: EngineState = std::fs::read(state_path()).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default();
    if !force && now().saturating_sub(st.last_check) < CHECK_EVERY.as_secs() {
        return Ok(None);
    }
    let current = tools::check(tools::Tool::YtDlp).version.unwrap_or_default();
    let latest: serde_json::Value =
        serde_json::from_str(&get_text("https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest")?).map_err(|e| e.to_string())?;
    st.last_check = now();
    let _ = std::fs::write(state_path(), serde_json::to_vec(&st).unwrap_or_default());
    let tag = latest["tag_name"].as_str().unwrap_or_default().to_string();
    if tag.is_empty() || tag == current {
        return Ok(None);
    }
    let base = format!("https://github.com/yt-dlp/yt-dlp/releases/download/{tag}/");
    let expected = find_sum(&get_text(&format!("{base}SHA2-256SUMS"))?, "yt-dlp.exe").ok_or("sin hash publicado para yt-dlp.exe")?;
    let data = get_bytes(&format!("{base}yt-dlp.exe"), 200 << 20)?;
    if sha256_hex(&data) != expected {
        return Err("yt-dlp descargado no coincide con su hash".into());
    }
    let target = paths::user_bin_dir().join("yt-dlp.exe");
    let tmp = target.with_extension("exe.new");
    std::fs::write(&tmp, data).map_err(|e| e.to_string())?;
    // Solo se queda si arranca de verdad aquí (antivirus, CPU, lo que sea).
    tools::probe(&tmp, &["--version"], Duration::from_secs(30)).map_err(|e| {
        let _ = std::fs::remove_file(&tmp);
        format!("el yt-dlp nuevo no arranca: {e}")
    })?;
    std::fs::rename(&tmp, &target).map_err(|e| e.to_string())?;
    tracing::info!("yt-dlp actualizado a {tag}");
    Ok(Some(tag))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn versions() {
        assert!(is_newer("4.0.0", "3.2.1"));
        assert!(is_newer("3.10.0", "3.9.9"));
        assert!(!is_newer("3.2.1", "3.2.1"));
        assert!(is_newer("3.2.1.1", "3.2.1"));
    }

    #[test]
    fn sums() {
        let s = "\u{feff}abc123  MXP_Downloader_Setup_v4.0.0.exe\nfff  *otro.exe";
        assert_eq!(find_sum(s, "MXP_Downloader_Setup_v4.0.0.exe").as_deref(), Some("abc123"));
        assert_eq!(find_sum(s, "otro.exe").as_deref(), Some("fff"));
        assert_eq!(find_sum(s, "nada.exe"), None);
    }

    #[test]
    fn releases_of_other_apps_are_ignored() {
        let r = |tag: &str, asset: &str| Release {
            tag_name: tag.into(), body: None, draft: false, prerelease: false,
            assets: vec![Asset { name: asset.into(), browser_download_url: "u".into(), size: 1 }],
        };
        assert!(parse_release(r("v4.0.0", "MXP_Downloader_Setup_v4.0.0.exe")).is_some());
        assert!(parse_release(r("denoiser-v1.1.0", "MXP_Denoiser_Setup_v1.1.0.exe")).is_none());
        assert!(parse_release(r("v3.0.1", "MXP_Suite_Pro_v3.0.1.zip")).is_none());
    }
}

#[cfg(test)]
mod net_tests {
    use super::*;

    #[test]
    #[ignore]
    fn real_github() {
        // No hay nada más nuevo que la versión en desarrollo…
        assert!(check_app().unwrap().is_none());
        // …y la 3.2.1 publicada se reconoce como release de esta app.
        let body = get_text(&format!("https://api.github.com/repos/{REPO}/releases?per_page=30")).unwrap();
        let rel: Vec<Release> = serde_json::from_str(&body).unwrap();
        assert!(rel.into_iter().filter_map(parse_release).any(|u| u.version == "3.2.1"));
        // yt-dlp: forzar comprobación (descarga solo si hay versión nueva).
        println!("yt-dlp: {:?}", update_ytdlp_if_stale(true));
    }
}

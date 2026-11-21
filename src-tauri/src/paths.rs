//! Rutas de la app. Los datos viven en %APPDATA%\MXP_Downloader: el mismo
//! sitio que la 3.x, así historial, ajustes y modelos se conservan al actualizar.

use std::path::PathBuf;

pub const APP_ID: &str = "MXP_Downloader";

fn ensure(p: PathBuf) -> PathBuf {
    let _ = std::fs::create_dir_all(&p);
    p
}

pub fn app_data_dir() -> PathBuf {
    let base = std::env::var_os("APPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(|| std::env::temp_dir());
    ensure(base.join(APP_ID))
}

/// Carpeta del ejecutable (lo que deja el instalador).
pub fn install_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."))
}

/// Herramientas que trae el instalador (solo lectura).
pub fn bundled_bin_dir() -> PathBuf {
    // En desarrollo se puede apuntar a otra carpeta sin copiar binarios.
    if let Some(dir) = std::env::var_os("MXP_TOOLS_DIR") {
        return PathBuf::from(dir);
    }
    install_dir().join("bin")
}

/// Herramientas actualizadas por la app (escribible por el usuario).
pub fn user_bin_dir() -> PathBuf {
    ensure(app_data_dir().join("bin"))
}

pub fn logs_dir() -> PathBuf {
    ensure(app_data_dir().join("logs"))
}

pub fn models_dir() -> PathBuf {
    ensure(app_data_dir().join("models"))
}

/// Carpeta de descargas por defecto (la de Windows, aunque esté movida a OneDrive u otro disco).
pub fn default_download_dir() -> PathBuf {
    crate::platform::known_downloads_dir()
        .or_else(|| std::env::var_os("USERPROFILE").map(|h| PathBuf::from(h).join("Downloads")))
        .unwrap_or_else(|| std::env::temp_dir())
}

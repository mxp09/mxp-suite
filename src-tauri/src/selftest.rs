//! `mxp-suite.exe --self-test [--report <archivo>]`
//!
//! Prueba real de que todo funciona en ESTE PC. La usa el instalador antes de
//! dar la instalación por buena y la usamos en las pruebas en Windows limpio.
//! Código de salida 0 = todo lo esencial funciona.

use std::path::Path;

use serde::Serialize;

use crate::{paths, platform, tools};

/// Windows 10 1809: lo mínimo que piden WebView2 y yt-dlp.
const MIN_WINDOWS_BUILD: u32 = 17763;

#[derive(Serialize)]
pub struct Check {
    pub id: String,
    pub label: String,
    pub ok: bool,
    /// Si falla, ¿impide usar la app?
    pub essential: bool,
    pub detail: String,
}

#[derive(Serialize)]
pub struct Report {
    pub ok: bool,
    pub version: &'static str,
    pub checks: Vec<Check>,
}

fn check(id: &str, label: &str, essential: bool, result: Result<String, String>) -> Check {
    let (ok, detail) = match result {
        Ok(d) => (true, d),
        Err(d) => (false, d),
    };
    Check { id: id.into(), label: label.into(), ok, essential, detail }
}

fn writable(dir: &Path) -> Result<String, String> {
    let probe = dir.join(".mxp-write-test");
    std::fs::write(&probe, b"ok")
        .and_then(|_| std::fs::remove_file(&probe))
        .map(|_| dir.display().to_string())
        .map_err(|e| match e.raw_os_error() {
            // Acceso controlado a carpetas de Defender devuelve "acceso denegado".
            Some(5) => format!(
                "Windows no deja escribir en {} (¿Acceso controlado a carpetas de Defender?)",
                dir.display()
            ),
            _ => format!("no se puede escribir en {}: {e}", dir.display()),
        })
}

fn cpu_features() -> String {
    let mut f = vec![];
    if std::arch::is_x86_feature_detected!("sse4.2") { f.push("SSE4.2") }
    if std::arch::is_x86_feature_detected!("avx") { f.push("AVX") }
    if std::arch::is_x86_feature_detected!("avx2") { f.push("AVX2") }
    if std::arch::is_x86_feature_detected!("fma") { f.push("FMA") }
    if f.is_empty() { "básico".into() } else { f.join(", ") }
}

pub fn run() -> Report {
    let mut checks = Vec::new();

    let (os, build) = platform::os_version();
    checks.push(check(
        "os",
        "Versión de Windows",
        true,
        if build >= MIN_WINDOWS_BUILD {
            Ok(os)
        } else {
            Err(format!("{os}: hace falta Windows 10 (versión 1809) o más nuevo"))
        },
    ));
    checks.push(check("cpu", "Procesador", false, Ok(cpu_features())));
    checks.push(check(
        "webview2",
        "Microsoft Edge WebView2",
        true,
        platform::webview2_version().map(|v| format!("versión {v}")).ok_or_else(|| "no instalado".into()),
    ));
    checks.push(check("data-dir", "Carpeta de datos", true, writable(&paths::app_data_dir())));
    checks.push(check("downloads-dir", "Carpeta de descargas", true, writable(&paths::default_download_dir())));

    for status in tools::check_all() {
        let result = match (status.ok, status.version, status.problem) {
            (true, Some(v), _) => Ok(v),
            (_, _, Some(p)) => Err(p),
            _ => Err("no disponible".into()),
        };
        checks.push(check(&format!("tool:{}", status.tool.exe()), status.label, true, result));
    }

    let ok = checks.iter().all(|c| c.ok || !c.essential);
    Report { ok, version: env!("CARGO_PKG_VERSION"), checks }
}

pub fn run_cli(args: &[String]) -> i32 {
    let report = run();
    for c in &report.checks {
        let mark = if c.ok { "OK  " } else if c.essential { "FALLA" } else { "aviso" };
        println!("[{mark}] {}: {}", c.label, c.detail);
        tracing::info!("self-test {} ok={} {}", c.id, c.ok, c.detail);
    }
    println!("{}", if report.ok { "RESULTADO: todo listo" } else { "RESULTADO: faltan componentes" });

    if let Some(path) = args.iter().position(|a| a == "--report").and_then(|i| args.get(i + 1)) {
        // BOM: Inno Setup solo lee bien los acentos de un UTF-8 con BOM.
        let json = serde_json::to_string_pretty(&report).unwrap_or_default();
        if let Err(e) = std::fs::write(path, format!("\u{feff}{json}")) {
            eprintln!("No se pudo escribir el informe en {path}: {e}");
        }
    }
    if report.ok { 0 } else { 1 }
}

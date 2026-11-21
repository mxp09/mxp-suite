//! Errores de red en lenguaje llano (descargas de modelos, actualizaciones).

pub fn explain(e: &ureq::Error) -> String {
    let raw = e.to_string();
    let low = raw.to_lowercase();
    if low.contains("certificate") && (low.contains("expired") || low.contains("not yet valid")) {
        "la fecha u hora de tu PC está mal y la conexión segura falla (ajústala en Configuración → Hora e idioma)".into()
    } else if low.contains("certificate") || low.contains("tls") || low.contains("ssl") {
        format!("conexión segura rechazada (¿antivirus o proxy de empresa inspeccionando HTTPS?): {raw}")
    } else if low.contains("dns") || low.contains("resolve") || low.contains("no such host") {
        "sin conexión a internet (no se encuentra el servidor)".into()
    } else if low.contains("timed out") || low.contains("timeout") {
        "la conexión tardó demasiado; revisa tu internet".into()
    } else if let ureq::Error::StatusCode(code) = e {
        format!("el servidor respondió con error {code}")
    } else {
        format!("error de red: {raw}")
    }
}

/// Cliente HTTP de la app. TLS del propio Windows (SChannel): usa los
/// certificados del sistema, así funciona tras proxies de empresa o antivirus
/// que inspeccionan HTTPS con su propio certificado raíz.
pub fn agent(timeout: Option<std::time::Duration>) -> ureq::Agent {
    use ureq::tls::{TlsConfig, TlsProvider};
    ureq::Agent::config_builder()
        .tls_config(TlsConfig::builder().provider(TlsProvider::NativeTls).build())
        .timeout_global(timeout)
        .timeout_connect(Some(std::time::Duration::from_secs(20)))
        .user_agent(concat!("MXP-Suite/", env!("CARGO_PKG_VERSION")))
        .build()
        .into()
}

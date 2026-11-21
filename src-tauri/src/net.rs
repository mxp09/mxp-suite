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

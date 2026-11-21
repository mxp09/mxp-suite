//! Errores de yt-dlp traducidos a algo que el usuario pueda arreglar.
//! Port de core/errors.py de la 3.x: mismas categorías y mismos textos.

use std::sync::OnceLock;

use regex::Regex;
use serde::Serialize;

#[derive(Clone, Debug, Serialize, PartialEq)]
pub struct DownloadError {
    /// Identificador estable para que la interfaz reaccione (p. ej. ofrecer cookies).
    pub category: &'static str,
    pub message: String,
    pub hint: String,
    /// Texto original de yt-dlp, para el log.
    pub raw: String,
}

impl DownloadError {
    pub fn full_text(&self) -> String {
        format!("{} {}", self.message, self.hint).trim().to_string()
    }
}

type Rule = (&'static str, &'static [&'static str], &'static str, &'static str);

// (categoría, patrones, mensaje, pista). El orden importa: lo más específico
// primero, porque el bot-check de YouTube también contiene "Sign in".
const RULES: &[Rule] = &[
    ("cookie_decrypt",
     &[r"could not (find|copy) .*cookies? database", r"could not.*be decrypted",
       r"failed to decrypt", r"cannot decrypt .*cookies", r"could not load cookies"],
     "No se pudieron leer las cookies del navegador que elegiste.",
     "Suele pasar porque el navegador está abierto y bloquea su propio archivo de cookies: \
      ciérralo del todo (revisa que no siga en la bandeja del sistema) y vuelve a intentarlo. \
      Si sigue sin funcionar, usa un archivo cookies.txt exportado (Cookies → Archivo)."),
    ("bot_check",
     &[r"sign in to confirm.*not a bot", r"confirm you.?re not a bot",
       r"failed to extract any player response", r"please sign in"],
     "El sitio está pidiendo verificar que no eres un bot.",
     "Abre Cookies y elige el navegador donde tengas la sesión iniciada (por ejemplo Chrome). \
      Es el arreglo habitual para esto."),
    ("age_restricted",
     &[r"age.?restricted", r"confirm your age", r"inappropriate for some users"],
     "El vídeo tiene restricción de edad.",
     "Activa las cookies de tu navegador con una sesión iniciada y mayor de edad."),
    ("private",
     &[r"private video", r"video is private", r"login required",
       r"requested content is not available", r"only available to",
       r"members.?only", r"this post is not available"],
     "El contenido es privado o requiere iniciar sesión.",
     "Si tienes acceso con tu cuenta, activa las cookies del navegador."),
    ("geo",
     &[r"available in your country", r"geo.?restricted", r"geo.?block",
       r"blocked it in your country", r"not available from your location",
       r"available in your location"],
     "El contenido está bloqueado en tu país.",
     "Necesitarías una VPN en la región donde sí esté disponible."),
    ("unavailable",
     &[r"video unavailable", r"has been removed", r"no longer available",
       r"account.*(terminated|closed)", r"does not exist", r"http error 404", r"deleted"],
     "El contenido ya no existe o fue eliminado.",
     "Comprueba que el enlace siga funcionando en el navegador."),
    ("forbidden",
     &[r"http error 403", r"forbidden"],
     "El servidor rechazó la petición (error 403).",
     "Suele arreglarse activando las cookies del navegador. Si persiste, el motor de descarga \
      se actualiza solo: vuelve a intentarlo en unas horas."),
    ("rate_limited",
     &[r"http error 429", r"too many requests", r"rate.?limit"],
     "El sitio ha limitado las peticiones por exceso de intentos.",
     "Espera unos minutos antes de volver a intentarlo y descarga en tandas más pequeñas."),
    ("clock",
     &[r"certificate (is not yet valid|has expired)"],
     "La fecha u hora de tu PC está mal y la conexión segura falla.",
     "Ajusta la fecha y hora de Windows (Configuración → Hora e idioma → Sincronizar ahora)."),
    ("disk_full",
     &[r"no space left on device", r"errno 28", r"not enough space"],
     "No queda espacio en el disco de destino.",
     "Libera espacio o elige otra carpeta de destino."),
    ("access_denied",
     &[r"permission denied", r"errno 13", r"access is denied"],
     "Windows no deja guardar en la carpeta de destino.",
     "Elige otra carpeta. Si usas Defender, revisa «Acceso controlado a carpetas»."),
    ("network",
     &[r"unable to download webpage", r"getaddrinfo", r"name resolution",
       r"timed out", r"connection (aborted|refused|reset|error)",
       r"network is unreachable", r"ssl", r"max retries exceeded"],
     "No se pudo conectar con el sitio.",
     "Revisa tu conexión a internet y vuelve a intentarlo."),
    ("unsupported",
     &[r"unsupported url", r"no suitable extractor", r"is not a valid url"],
     "Este enlace no es compatible.",
     "Comprueba que sea la URL directa del vídeo y no la de una búsqueda o una página de perfil."),
    ("no_formats",
     &[r"requested format is not available", r"no video formats found", r"no formats found"],
     "No hay ningún formato descargable con la calidad pedida.",
     "Prueba con otra resolución o con «Máxima calidad»."),
];

fn compiled() -> &'static [Vec<Regex>] {
    static CELL: OnceLock<Vec<Vec<Regex>>> = OnceLock::new();
    CELL.get_or_init(|| {
        RULES
            .iter()
            .map(|(_, pats, _, _)| pats.iter().map(|p| Regex::new(p).expect("regex válida")).collect())
            .collect()
    })
}

/// Nunca falla: si nada encaja, devuelve el texto original, que sigue siendo
/// más útil que un mensaje genérico que apunta a la causa equivocada.
pub fn classify(raw: &str) -> DownloadError {
    let cleaned = raw.trim().trim_start_matches("ERROR:").trim().to_string();
    let haystack = cleaned.to_lowercase();
    let hit = compiled().iter().position(|pats| pats.iter().any(|re| re.is_match(&haystack)));
    match hit {
        Some(i) => {
            let (category, _, message, hint) = RULES[i];
            DownloadError { category, message: message.into(), hint: hint.into(), raw: cleaned }
        }
        None => DownloadError {
            category: "unknown",
            message: "No se pudo procesar este enlace.".into(),
            hint: cleaned.clone(),
            raw: cleaned,
        },
    }
}

/// 403 y bot-check suelen arreglarse solos con otra estrategia de extracción.
pub fn retry_with_fallback(e: &DownloadError) -> bool {
    matches!(e.category, "forbidden" | "bot_check")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn categories() {
        let cases = [
            ("ERROR: [youtube] x: Sign in to confirm you're not a bot", "bot_check"),
            ("ERROR: unable to download video data: HTTP Error 403: Forbidden", "forbidden"),
            ("ERROR: [youtube] x: Private video. Sign in if you've been granted access", "private"),
            ("The uploader has not made this video available in your country", "geo"),
            ("ERROR: [youtube] x: Video unavailable", "unavailable"),
            ("HTTP Error 429: Too Many Requests", "rate_limited"),
            ("Unsupported URL: https://example.com", "unsupported"),
            ("Requested format is not available", "no_formats"),
            ("[Errno 28] No space left on device", "disk_full"),
            ("Could not copy Chrome cookie database", "cookie_decrypt"),
            ("[SSL: CERTIFICATE_VERIFY_FAILED] certificate has expired", "clock"),
            ("Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>", "network"),
        ];
        for (raw, cat) in cases {
            assert_eq!(classify(raw).category, cat, "{raw}");
        }
    }

    #[test]
    fn unknown_keeps_text() {
        let e = classify("ERROR: algo raro");
        assert_eq!(e.category, "unknown");
        assert_eq!(e.hint, "algo raro");
    }

    #[test]
    fn impersonate_error_is_not_retryable() {
        // El error que vio un usuario real en la 3.2.0 no debe disparar otro reintento.
        let e = classify(r#"Impersonate target "chrome" is not available"#);
        assert!(!retry_with_fallback(&e));
    }
}

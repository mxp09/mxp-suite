"""
Traducción de los errores de yt-dlp a algo que el usuario pueda accionar.

Antes todo fallo acababa en el mismo texto — "Verifica que sea público y
exista" — daba igual que fuese un 403, un vídeo privado, un bloqueo geográfico
o el wifi caído. Eso manda a la gente a investigar donde no es: se reportaron
vídeos con millones de visitas, perfectamente públicos, con ese mensaje.

Aquí cada causa se identifica y se dice exactamente qué hacer.
"""

import re
from dataclasses import dataclass


@dataclass
class DownloadError:
    """Un fallo clasificado, listo para mostrar."""

    category: str    # identificador estable, para que la UI pueda reaccionar
    message: str     # qué ha pasado, en una frase
    hint: str = ""   # qué puede hacer el usuario al respecto
    raw: str = ""    # el texto original de yt-dlp, para el log

    @property
    def full_text(self) -> str:
        return f"{self.message} {self.hint}".strip()

    @property
    def needs_cookies(self) -> bool:
        """True si activar las cookies del navegador probablemente lo arregle."""
        return self.category in ("bot_check", "forbidden", "private", "age_restricted")


# (categoría, patrones, mensaje, pista)
# El orden importa: lo más específico primero, porque un mensaje de bot-check
# de YouTube también contiene la palabra "Sign in".
_RULES = [
    (
        "bot_check",
        [r"sign in to confirm.*not a bot", r"confirm you.?re not a bot",
         r"failed to extract any player response", r"please sign in"],
        "El sitio está pidiendo verificar que no eres un bot.",
        "Abre Ajustes → Cookies y elige el navegador donde tengas la sesión "
        "iniciada (por ejemplo Chrome). Es el arreglo habitual para esto.",
    ),
    (
        "age_restricted",
        [r"age.?restricted", r"confirm your age", r"inappropriate for some users"],
        "El vídeo tiene restricción de edad.",
        "Activa las cookies de tu navegador en Ajustes con una sesión "
        "iniciada y mayor de edad.",
    ),
    (
        "private",
        [r"private video", r"video is private", r"login required",
         r"requested content is not available", r"only available to",
         r"members.?only", r"this post is not available"],
        "El contenido es privado o requiere iniciar sesión.",
        "Si tienes acceso con tu cuenta, activa las cookies del navegador en Ajustes.",
    ),
    (
        "geo",
        # "available in your country" cubre tanto "not available in your
        # country" como el texto real de YouTube, "The uploader has not made
        # this video available in your country".
        [r"available in your country", r"geo.?restricted", r"geo.?block",
         r"blocked it in your country", r"not available from your location",
         r"available in your location"],
        "El contenido está bloqueado en tu país.",
        "Necesitarías una VPN en la región donde sí esté disponible.",
    ),
    (
        "unavailable",
        [r"video unavailable", r"has been removed", r"no longer available",
         r"account.*(terminated|closed)", r"does not exist", r"http error 404",
         r"deleted"],
        "El contenido ya no existe o fue eliminado.",
        "Comprueba que el enlace siga funcionando en el navegador.",
    ),
    (
        "forbidden",
        [r"http error 403", r"forbidden"],
        "El servidor rechazó la petición (error 403).",
        "Suele arreglarse activando las cookies del navegador en Ajustes. "
        "Si persiste, el motor de descarga se actualiza solo: vuelve a "
        "intentarlo en unas horas.",
    ),
    (
        "rate_limited",
        [r"http error 429", r"too many requests", r"rate.?limit"],
        "El sitio ha limitado las peticiones por exceso de intentos.",
        "Espera unos minutos antes de volver a intentarlo, y descarga en "
        "tandas más pequeñas.",
    ),
    (
        "network",
        [r"unable to download webpage", r"getaddrinfo", r"name resolution",
         r"timed out", r"connection (aborted|refused|reset|error)",
         r"network is unreachable", r"ssl", r"max retries exceeded"],
        "No se pudo conectar con el sitio.",
        "Revisa tu conexión a internet y vuelve a intentarlo.",
    ),
    (
        "unsupported",
        [r"unsupported url", r"no suitable extractor", r"is not a valid url"],
        "Este enlace no es compatible.",
        "Comprueba que sea la URL directa del vídeo y no la de una búsqueda "
        "o una página de perfil.",
    ),
    (
        "no_formats",
        [r"requested format is not available", r"no video formats found",
         r"no formats found"],
        "No hay ningún formato descargable con la calidad pedida.",
        "Prueba con otra resolución, o con «Máxima Calidad».",
    ),
    (
        "engine_missing",
        [r"no module named .?yt_dlp"],
        "Falta el motor de descarga.",
        "Cierra y vuelve a abrir la app para que lo instale, o reinstala la "
        "aplicación si el problema sigue.",
    ),
]


def classify(error) -> DownloadError:
    """
    Convierte una excepción (o su texto) en un DownloadError con mensaje útil.

    Nunca lanza: si nada encaja, devuelve el texto original, que sigue siendo
    infinitamente mejor que un mensaje genérico que apunta a la causa errónea.
    """
    raw = str(error) if error is not None else ""
    # yt-dlp prefija sus errores con "ERROR: " y a veces con el nombre del extractor
    cleaned = re.sub(r"^ERROR:\s*", "", raw).strip()
    haystack = cleaned.lower()

    for category, patterns, message, hint in _RULES:
        if any(re.search(pattern, haystack) for pattern in patterns):
            return DownloadError(category, message, hint, cleaned)

    return DownloadError(
        "unknown",
        "No se pudo procesar este enlace.",
        cleaned,
        cleaned,
    )


def is_retryable_with_fallback(error) -> bool:
    """
    True si merece la pena reintentar con otra estrategia de extracción.

    403 y bot-check son casi siempre culpa de que el sitio no se cree que
    seamos un navegador. Con impersonación y otro cliente de reproducción la
    segunda pasada suele funcionar sin que el usuario tenga que hacer nada.
    """
    return classify(error).category in ("forbidden", "bot_check")

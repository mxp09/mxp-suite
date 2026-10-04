"""
Utilidades generales para el Video Downloader.
Detección de plataforma, validación de URL, manejo de rutas.
"""

import os
import re
import sys
from urllib.parse import urlparse
from typing import Optional


def get_resource_path(relative_path: str) -> str:
    """
    Resuelve la ruta absoluta para un recurso en el directorio de la app (assets).
    """
    if getattr(sys, 'frozen', False):
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# Las rutas de datos viven en mxp_common para que la app, el updater y el
# instalador coincidan siempre en dónde está cada cosa. Se reexportan aquí
# para no romper los imports existentes.
from mxp_common.paths import get_app_dir, get_bin_dir, get_engine_dir  # noqa: E402,F401


# ─── Patrones de URL por plataforma ────────────────────────────────────────────

PLATFORM_PATTERNS = {
    "YouTube": [
        r"(youtube\.com|youtu\.be)",
        r"youtube\.com/shorts/",
    ],
    "TikTok": [
        r"(tiktok\.com|vm\.tiktok\.com)",
    ],
    "Instagram": [
        r"(instagram\.com|instagr\.am)",
    ],
    "Facebook": [
        r"(facebook\.com|fb\.watch|fb\.com)",
    ],
    "X": [
        r"(x\.com|twitter\.com)",
    ],
}

PLATFORM_ICONS = {
    "YouTube": "▶️",
    "TikTok": "♪",
    "Instagram": "📷",
    "Facebook": "📘",
    "X": "𝕏",
    "Desconocido": "🔗",
}


def detect_platform(url: str) -> str:
    """Detecta la plataforma a partir de la URL."""
    url_lower = url.lower().strip()
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return platform
    return "Desconocido"


def get_platform_icon(platform: str) -> str:
    """Retorna el icono emoji para la plataforma."""
    return PLATFORM_ICONS.get(platform, "🔗")


def validate_url(url: str) -> bool:
    """Valida que la URL tenga un formato válido."""
    url = url.strip()
    if not url:
        return False
    try:
        result = urlparse(url)
        return all([result.scheme in ("http", "https"), result.netloc])
    except Exception:
        return False


def sanitize_filename(name: str) -> str:
    """Limpia caracteres no válidos para nombre de archivo en Windows."""
    # Remueve caracteres no permitidos en Windows
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # Remueve caracteres de control
    name = re.sub(r'[\x00-\x1f\x7f]', '', name)
    # Limita longitud
    name = name[:200].strip()
    return name if name else "video"


def get_default_download_dir() -> str:
    """Retorna la carpeta de Descargas del usuario."""
    if sys.platform == "win32":
        # Intenta obtener la carpeta de Descargas de Windows
        import winreg
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
            )
            downloads_path, _ = winreg.QueryValueEx(key, "{374DE290-123F-4565-9164-39C4925E467B}")
            winreg.CloseKey(key)
            if os.path.isdir(downloads_path):
                return downloads_path
        except Exception:
            pass

    # Fallback: ~/Downloads o ~/Descargas
    home = os.path.expanduser("~")
    for folder_name in ["Downloads", "Descargas"]:
        path = os.path.join(home, folder_name)
        if os.path.isdir(path):
            return path

    # Último fallback: home del usuario
    return home


def format_bytes(bytes_val: float) -> str:
    """Formatea bytes a representación legible (KB, MB, GB)."""
    if bytes_val is None or bytes_val < 0:
        return "—"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"


def format_eta(seconds: float) -> str:
    """Formatea segundos a mm:ss o hh:mm:ss."""
    if seconds is None or seconds < 0:
        return "—"
    seconds = int(seconds)
    if seconds < 3600:
        return f"{seconds // 60}:{seconds % 60:02d}"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:02d}"


def show_windows_notification(title: str, message: str):
    """
    Notificación nativa de Windows (globo) mediante PowerShell, sin bloquear.

    El texto viaja por variables de entorno, NUNCA interpolado en el script:
    el título del vídeo viene del sitio remoto, y antes un título con una
    comilla simple cerraba el string de PowerShell y ejecutaba lo que viniera
    detrás. Además se usa Popen (no run): antes la ventana de Tk se congelaba
    1-2 s esperando a que PowerShell arrancara en cada descarga terminada.
    """
    import subprocess
    powershell_code = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$n = New-Object System.Windows.Forms.NotifyIcon; "
        "$n.Icon = [System.Drawing.SystemIcons]::Information; "
        "$n.BalloonTipIcon = 'Info'; "
        "$n.BalloonTipTitle = $env:MXP_NOTIFY_TITLE; "
        "$n.BalloonTipText = $env:MXP_NOTIFY_TEXT; "
        "$n.Visible = $true; "
        "$n.ShowBalloonTip(5000); "
        "Start-Sleep -Seconds 6; "
        "$n.Dispose()"
    )
    env = dict(os.environ, MXP_NOTIFY_TITLE=title[:63], MXP_NOTIFY_TEXT=message[:255])
    try:
        subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", powershell_code],
            env=env,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass


def parse_time_str(time_str: str) -> Optional[int]:
    """Convierte un string de tiempo (HH:MM:SS, MM:SS o SS) a segundos totales."""
    time_str = time_str.strip()
    if not time_str:
        return None
    try:
        parts = list(map(int, time_str.split(':')))
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 1:
            return parts[0]
    except Exception:
        pass
    return None




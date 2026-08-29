"""
Rutas de datos de la app. Todo lo que la app escribe vive bajo %APPDATA%\<APP_ID>,
nunca junto al ejecutable — así la app funciona igual instalada en Archivos de
Programa, en un pendrive o en una carpeta de solo lectura.
"""

import os
import sys

from mxp_common.version import APP_ID


def get_app_dir() -> str:
    """Carpeta de datos de la app en AppData. Se crea si no existe."""
    base = os.getenv("APPDATA") or os.path.expanduser("~")
    app_dir = os.path.join(base, APP_ID)
    os.makedirs(app_dir, exist_ok=True)
    return app_dir


def get_bin_dir() -> str:
    """Carpeta de binarios externos (ffmpeg, ffprobe)."""
    bin_dir = os.path.join(get_app_dir(), "bin")
    os.makedirs(bin_dir, exist_ok=True)
    return bin_dir


def get_engine_dir() -> str:
    """
    Carpeta del motor yt-dlp actualizable.

    Se antepone a sys.path al arrancar, así que el yt-dlp que hay aquí gana
    sobre cualquier copia empaquetada. Es lo que permite actualizar el motor
    sin reinstalar la app.
    """
    engine_dir = os.path.join(get_app_dir(), "engine")
    os.makedirs(engine_dir, exist_ok=True)
    return engine_dir


def get_install_dir() -> str:
    """
    Carpeta donde vive el ejecutable (o el código fuente en desarrollo).

    Aquí es donde el instalador deja bin/ y engine/, así que se consulta antes
    que AppData: si el instalador ya dejó ffmpeg, no hay nada que descargar.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # mxp_common/ está un nivel por debajo de la raíz del proyecto
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

"""
mxp_common — Módulo compartido de la suite MXP.

Contiene lo que todas las apps necesitan igual:
  · version.py       — fuente única de la versión y la identidad de la app
  · paths.py         — rutas de datos, binarios y motor en AppData
  · binaries.py      — resolución, descarga y VERIFICACIÓN REAL de ffmpeg/ffprobe/yt-dlp
  · updater.py       — comprobación de versión nueva contra GitHub Releases
  · update_dialog.py — el popup de "hay una versión nueva"

Se copia dentro de cada app en lugar de instalarse como paquete, para que
cada build de PyInstaller siga siendo autocontenido.
"""

from mxp_common.version import __version__, APP_ID, APP_NAME, GITHUB_REPO

__all__ = ["__version__", "APP_ID", "APP_NAME", "GITHUB_REPO"]

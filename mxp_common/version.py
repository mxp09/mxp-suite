"""
Fuente única de verdad de la versión de MXP Downloader.

Todo lo que muestre o compare una versión lee de aquí: el footer de la UI,
el recurso de versión del .exe, el instalador de Inno Setup y el updater.
No dupliques el número en ningún otro sitio.
"""

# Versión semántica (MAJOR.MINOR.PATCH). Los releases de GitHub se etiquetan "v" + esto.
__version__ = "1.1.0"

# Identidad de la app
APP_ID = "MXP_Downloader"          # nombre de la carpeta en %APPDATA%
APP_NAME = "MXP Downloader"        # nombre visible
GITHUB_REPO = "mxp09/mxp-downloader"  # repo donde se publican los releases

# Metadatos para el recurso de versión de Windows
COMPANY_NAME = "MXP Productions"
DESCRIPTION = "Descarga de video y audio, conversor y compresor."
COPYRIGHT = "© 2026 Iván Chong"


def version_tuple() -> tuple:
    """Devuelve la versión como tupla de enteros, para comparar."""
    return tuple(int(p) for p in __version__.split("."))


def version_info_4() -> str:
    """Versión en formato de 4 componentes que exige el recurso de Windows."""
    parts = __version__.split(".")
    while len(parts) < 4:
        parts.append("0")
    return ".".join(parts[:4])

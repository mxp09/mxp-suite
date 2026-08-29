"""
Fuente única de verdad de la versión de MXP Downloader.

Todo lo que muestre o compare una versión lee de aquí: el footer de la UI,
el recurso de versión del .exe, el instalador de Inno Setup y el updater.
No dupliques el número en ningún otro sitio.
"""

# Versión semántica (MAJOR.MINOR.PATCH). Los releases de GitHub se etiquetan "v" + esto.
# Va en 3.x porque la línea pública ya iba por ahí: el último release de
# mxp-suite es v3.0.1 (MXP_Suite_Pro_v3.0.1.zip, 17 descargas). Ponerle 1.1.0
# habría hecho que el updater viera 3.0.1 como "más nueva" y ofreciera a todo
# el mundo volver justo a la versión con el bug del 403.
__version__ = "3.1.0"

# Identidad de la app
APP_ID = "MXP_Downloader"          # nombre de la carpeta en %APPDATA%
APP_NAME = "MXP Downloader"        # nombre visible
GITHUB_REPO = "mxp09/mxp-suite"    # repo donde se publican los releases

# mxp-suite es un repo COMPARTIDO por varias apps de la suite, así que no vale
# con mirar "el último release": el más reciente podría ser de otra app. El
# updater solo considera releases que traigan un archivo que empiece por esto.
ASSET_PREFIX = "MXP_Downloader_Setup"

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

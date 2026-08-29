"""
Logging compartido de la suite.

El Denoiser ya escribía a `logs/out.txt`/`err.txt` desde su punto de entrada;
el Downloader no tenía nada equivalente — solo `print`s que en modo ventana
(sin consola) van a ninguna parte. Sin un archivo que revisar, cualquier fallo
en la máquina de otra persona es imposible de diagnosticar a distancia.

Uso, una vez al arrancar la app:

    from mxp_common.logs import setup_logging
    logger = setup_logging()
"""

import logging
import logging.handlers
import os

from mxp_common.paths import get_app_dir

_MAX_BYTES = 2 * 1024 * 1024  # 2 MB por archivo
_BACKUP_COUNT = 3             # + hasta 3 rotados, ~8 MB en total como tope


def setup_logging(name: str = "MXP") -> logging.Logger:
    """
    Configura un logger raíz que escribe a `%APPDATA%/<app>/logs/app.log`.

    Rota al llegar a 2 MB para que el archivo nunca crezca sin límite en una
    sesión larga. Es idempotente: llamarlo dos veces no duplica handlers.
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # ya configurado (p. ej. si algo llama dos veces)

    logs_dir = os.path.join(get_app_dir(), "logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, "app.log")

    handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))

    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    logger.info("=== Sesión iniciada ===")
    return logger

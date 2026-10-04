"""
Ajustes del usuario que sobreviven al cierre (carpeta, formatos, cookies...).

Antes todo volvía a los valores por defecto en cada arranque.
"""

import json
import os

from core.utils import get_app_dir

_PATH = os.path.join(get_app_dir(), "settings.json")


def load() -> dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(data: dict):
    """Escritura atómica (.tmp + os.replace), igual que el historial."""
    try:
        with open(_PATH + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(_PATH + ".tmp", _PATH)
    except OSError:
        pass  # perder los ajustes no es motivo para fallar al cerrar

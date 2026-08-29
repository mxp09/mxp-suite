import os
import json
import threading
from datetime import datetime
from typing import List, Dict
from core.utils import get_app_dir

class HistoryManager:
    """
    Gestiona el historial de descargas en un archivo JSON.

    Con hasta 3 descargas concurrentes, es normal que dos terminen casi a la
    vez y llamen a `add_entry` desde hilos distintos casi al mismo tiempo. Sin
    protección, ambas leen el mismo estado y la que escribe segunda pisa la
    entrada de la primera — el historial pierde descargas en silencio. El
    lock es de CLASE (no de instancia) a propósito: cada descarga crea su
    propio `HistoryManager()`, así que un lock por instancia no protegería nada.
    """

    _lock = threading.Lock()

    def __init__(self):
        self.history_path = os.path.join(get_app_dir(), "history.json")
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.history_path):
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _write(self, history: List[Dict]):
        """
        Escritura atómica: a un archivo `.tmp` y luego `os.replace`.

        Si el proceso se interrumpe a mitad de un `json.dump` directo sobre
        `history.json`, el archivo queda truncado y corrupto, y la próxima
        lectura pierde el historial entero. `os.replace` en Windows es una
        operación de directorio, no puede quedar a medias.
        """
        tmp_path = self.history_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)
        os.replace(tmp_path, self.history_path)

    def add_entry(self, title: str, url: str, format_ext: str):
        """Añade una nueva entrada al historial."""
        entry = {
            "title": title,
            "url": url,
            "format": format_ext.upper(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        with self._lock:
            history = self.get_all()
            history.insert(0, entry)  # Nueva entrada al principio
            history = history[:100]   # Limitar a las últimas 100 descargas
            self._write(history)

    def get_all(self) -> List[Dict]:
        """Retorna todas las entradas del historial."""
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def clear(self):
        """Limpia el historial."""
        with self._lock:
            self._write([])

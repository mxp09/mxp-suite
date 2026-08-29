import os
import json
from datetime import datetime
from typing import List, Dict
from core.utils import get_app_dir

class HistoryManager:
    """Gestiona el historial de descargas en un archivo JSON."""

    def __init__(self):
        self.history_path = os.path.join(get_app_dir(), "history.json")
        self._ensure_file()

    def _ensure_file(self):
        if not os.path.exists(self.history_path):
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump([], f)

    def add_entry(self, title: str, url: str, format_ext: str):
        """Añade una nueva entrada al historial."""
        entry = {
            "title": title,
            "url": url,
            "format": format_ext.upper(),
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        history = self.get_all()
        history.insert(0, entry)  # Nueva entrada al principio
        
        # Limitar a las últimas 100 descargas
        history = history[:100]
        
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=4, ensure_ascii=False)

    def get_all(self) -> List[Dict]:
        """Retorna todas las entradas del historial."""
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def clear(self):
        """Limpia el historial."""
        with open(self.history_path, "w", encoding="utf-8") as f:
            json.dump([], f)

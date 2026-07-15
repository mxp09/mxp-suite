import os
import sys
import requests
import zipfile
import io
import threading
from typing import Callable, Optional
from core.utils import get_bin_dir

class BinaryManager:
    """Gestiona la descarga y verificación de yt-dlp y ffmpeg."""

    YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
    # Usamos una versión específica de BtbN para mayor estabilidad en descarga directa
    FFMPEG_URL = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

    def __init__(self, progress_callback: Optional[Callable[[str, float], None]] = None):
        """
        Args:
            progress_callback: Función que recibe (mensaje, porcentaje).
        """
        self.progress_callback = progress_callback
        self.bin_dir = get_bin_dir()

    def check_binaries(self) -> bool:
        """Verifica si los binarios necesarios ya existen en bin_dir o en el PATH del sistema."""
        import shutil
        
        # yt-dlp debe estar sí o sí en el directorio de binarios local
        ytdlp_exists = os.path.exists(os.path.join(self.bin_dir, "yt-dlp.exe"))
        if not ytdlp_exists:
            return False

        # Para ffmpeg, checkeamos bin_dir O si está disponible en el PATH
        ffmpeg_exists = os.path.exists(os.path.join(self.bin_dir, "ffmpeg.exe")) or shutil.which("ffmpeg") is not None

        return ffmpeg_exists

    def setup_binaries(self):
        """Inicia el proceso de descarga en un hilo separado."""
        if self.check_binaries():
            if self.progress_callback:
                self.progress_callback("Binarios listos", 100)
            return

        thread = threading.Thread(target=self._download_all, daemon=True)
        thread.start()

    def _download_all(self):
        import shutil
        try:
            # 1. Descargar yt-dlp si no existe localmente
            ytdlp_path = os.path.join(self.bin_dir, "yt-dlp.exe")
            if not os.path.exists(ytdlp_path):
                self._download_file(self.YTDLP_URL, "yt-dlp.exe", "Descargando motor (yt-dlp)...", 0, 30)
            else:
                if self.progress_callback:
                    self.progress_callback("Motor local detectado", 30)
            
            # 2. Descargar y extraer FFmpeg si no está en bin_dir ni en el PATH del sistema
            ffmpeg_exists = os.path.exists(os.path.join(self.bin_dir, "ffmpeg.exe")) or shutil.which("ffmpeg") is not None
            
            if not ffmpeg_exists:
                self._download_and_extract_ffmpeg(30, 100)
            else:
                if self.progress_callback:
                    self.progress_callback("FFmpeg detectado en el sistema", 100)
            
            if self.progress_callback:
                self.progress_callback("Configuración completada", 100)
        except Exception as e:
            if self.progress_callback:
                self.progress_callback(f"Error en setup: {str(e)}", -1)

    def _download_file(self, url: str, filename: str, msg: str, start_p: float, end_p: float):
        path = os.path.join(self.bin_dir, filename)
        response = requests.get(url, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        with open(path, "wb") as f:
            downloaded = 0
            for data in response.iter_content(chunk_size=4096):
                downloaded += len(data)
                f.write(data)
                if total_size > 0:
                    p = start_p + (downloaded / total_size) * (end_p - start_p)
                    if self.progress_callback:
                        self.progress_callback(msg, p)

    def _download_and_extract_ffmpeg(self, start_p: float, end_p: float):
        msg = "Descargando FFmpeg (esto puede tardar)..."
        if self.progress_callback:
            self.progress_callback(msg, start_p)
            
        response = requests.get(self.FFMPEG_URL, stream=True)
        total_size = int(response.headers.get('content-length', 0))
        
        buffer = io.BytesIO()
        downloaded = 0
        for data in response.iter_content(chunk_size=8192):
            downloaded += len(data)
            buffer.write(data)
            if total_size > 0:
                p = start_p + (downloaded / total_size) * (end_p - start_p) * 0.8 # Dejamos 20% para extracción
                if self.progress_callback:
                    self.progress_callback(msg, p)
        
        if self.progress_callback:
            self.progress_callback("Extrayendo FFmpeg...", start_p + (end_p - start_p) * 0.85)

        with zipfile.ZipFile(buffer) as z:
            # Buscamos ffmpeg.exe dentro del ZIP
            for member in z.namelist():
                if member.endswith("ffmpeg.exe"):
                    filename = os.path.basename(member)
                    with z.open(member) as source, open(os.path.join(self.bin_dir, filename), "wb") as target:
                        target.write(source.read())

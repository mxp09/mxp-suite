"""
Preparación de las dependencias externas de MXP Downloader.

Es una capa fina sobre mxp_common.binaries, que es donde vive la lógica real y
compartida con el resto de la suite. Aquí solo se define QUÉ necesita esta app
y en qué orden.

Qué cambió respecto a la versión anterior:
  · Se descargaban 18 MB de yt-dlp.exe que **nunca se ejecutaban** — el motor
    real era el módulo Python compilado dentro del .exe. Ahora se instala el
    paquete yt_dlp de verdad, fuera del ejecutable y actualizable.
  · Un binario se daba por bueno con os.path.exists(). Ahora se ejecuta para
    comprobar que responde, así una descarga cortada no pasa por buena.
  · Faltaba ffprobe, que yt-dlp necesita para elegir formatos correctamente.
"""

import threading
from typing import Callable, Optional

from mxp_common.binaries import EngineManager, FFmpegManager

ProgressCallback = Callable[[str, float], None]


class BinaryManager:
    """Deja ffmpeg, ffprobe y el motor yt-dlp listos para usar."""

    def __init__(self, progress_callback: Optional[ProgressCallback] = None):
        self.progress_callback = progress_callback
        self.ffmpeg = FFmpegManager(progress_callback)
        self.engine = EngineManager(progress_callback)

    def check_binaries(self) -> bool:
        """True si todo está instalado y responde."""
        self.ffmpeg.refresh()
        return self.ffmpeg.is_ready() and self.engine.is_installed()

    def missing(self) -> list:
        """Lista legible de lo que falta, para poder decírselo al usuario."""
        pending = list(self.ffmpeg.missing())
        if not self.engine.is_installed():
            pending.append("motor de descarga (yt-dlp)")
        return pending

    def setup_binaries(self, on_done: Optional[Callable[[bool], None]] = None):
        """
        Descarga lo que falte en segundo plano.

        `on_done` recibe True si al terminar todo está listo. Se llama desde el
        hilo de trabajo, así que quien lo use debe volver al hilo de Tk con
        after() antes de tocar widgets.
        """
        if self.check_binaries():
            if self.progress_callback:
                self.progress_callback("Todo listo", 100)
            if on_done:
                on_done(True)
            return

        def _work():
            ok = True
            try:
                # ffmpeg es lo más pesado, se lleva el 70% de la barra
                ok = self.ffmpeg.ensure(0, 70) and ok
                ok = self.engine.ensure(70, 100) and ok
            except Exception as exc:
                ok = False
                if self.progress_callback:
                    self.progress_callback(
                        f"No se pudieron instalar las dependencias: {exc}", -1
                    )
            if ok and self.progress_callback:
                self.progress_callback("Todo listo", 100)
            if on_done:
                on_done(ok)

        threading.Thread(target=_work, daemon=True).start()

    def update_engine_async(self):
        """
        Actualiza yt-dlp en segundo plano si toca (máximo una vez cada 6 h).

        Es el arreglo de fondo del error 403: el motor deja de envejecer con el
        ejecutable y se mantiene al día solo, que es lo que los sitios exigen
        para seguir funcionando.
        """
        threading.Thread(target=self.engine.update_if_stale, daemon=True).start()

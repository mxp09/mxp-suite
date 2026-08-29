"""
Motor de descarga basado en yt-dlp.
Maneja la configuración, ejecución en hilo separado, y reporte de progreso.
"""

import os
import sys
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import yt_dlp

from core.utils import get_default_download_dir


# ─── Tipos ──────────────────────────────────────────────────────────────────────

class VideoResolution(Enum):
    """Resoluciones de video disponibles."""
    BEST = ("Máxima Calidad", None)        # Sin límite — la mejor disponible
    RES_2160 = ("4K (2160p)", 2160)
    RES_1440 = ("2K (1440p)", 1440)
    RES_1080 = ("1080p Full HD", 1080)
    RES_720 = ("720p HD", 720)
    RES_480 = ("480p", 480)
    RES_360 = ("360p", 360)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def height(self):
        return self.value[1]


class Quality(Enum):
    BEST = "best"
    AUDIO_ONLY = "audio_only"


class DownloadStatus(Enum):
    IDLE = "idle"
    FETCHING_INFO = "fetching_info"
    DOWNLOADING = "downloading"
    MERGING = "merging"
    FINISHED = "finished"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class ProgressData:
    """Datos de progreso enviados a la GUI."""
    status: DownloadStatus = DownloadStatus.IDLE
    percent: float = 0.0
    speed: str = ""
    eta: str = ""
    filename: str = ""
    total_size: str = ""
    downloaded: str = ""
    error_message: str = ""
    video_title: str = ""


# ─── Callback type ──────────────────────────────────────────────────────────────

ProgressCallback = Callable[[ProgressData], None]


# ─── Clase principal ────────────────────────────────────────────────────────────

class VideoDownloader:
    """Wrapper sobre yt-dlp con soporte para progreso y cancelación."""

    def __init__(self):
        self._cancel_event = threading.Event()
        self._download_thread: Optional[threading.Thread] = None
        self._is_downloading = False

    @property
    def is_downloading(self) -> bool:
        return self._is_downloading

    def _build_opts(
        self,
        quality: Quality,
        resolution: VideoResolution,
        output_dir: str,
        progress_callback: Optional[ProgressCallback],
        format_ext: str = "mp4",
        audio_bitrate: str = "320",
        cookies_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
    ) -> dict:
        """Construye el diccionario de opciones para yt-dlp."""

        output_template = os.path.join(output_dir, "%(title)s.%(ext)s")

        # ── Formato según calidad ──
        if quality == Quality.AUDIO_ONLY:
            format_str = "bestaudio/best"
            postprocessors = [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": format_ext,
                    "preferredquality": audio_bitrate,
                },
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail", "already_have_thumbnail": False},
            ]
        else:
            max_h = resolution.height
            if max_h is not None:
                format_str = (
                    f"bestvideo[height<={max_h}][ext=mp4]+bestaudio[ext=m4a]"
                    f"/bestvideo[height<={max_h}]+bestaudio"
                    f"/best[height<={max_h}]"
                    f"/bestvideo+bestaudio/best"
                )
            else:
                format_str = (
                    "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
                    "/bestvideo+bestaudio"
                    "/best"
                )
            postprocessors = [
                {"key": "FFmpegMetadata", "add_metadata": True},
                {"key": "EmbedThumbnail", "already_have_thumbnail": False},
            ]

        opts = {
            "format": format_str,
            "merge_output_format": format_ext,
            "outtmpl": output_template,
            "postprocessors": postprocessors,
            "format_sort": ["res", "vcodec:h264", "acodec:aac", "tbr"],
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "overwrites": True,
            "writethumbnail": True,  # Habilitado para incrustar
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
            },
        }

        # ── Binaries Path (AppData) ──
        from core.utils import get_bin_dir
        ffmpeg_dir = get_bin_dir()
        ffmpeg_exe = os.path.join(ffmpeg_dir, "ffmpeg.exe")
        
        if os.path.exists(ffmpeg_exe):
            opts["ffmpeg_location"] = ffmpeg_exe
        
        # Inyectar yt-dlp path si estamos en modo standalone
        if getattr(sys, 'frozen', False):
            opts["ffmpeg_location"] = ffmpeg_exe

        # ── Progress hook ──
        if progress_callback:
            opts["progress_hooks"] = [self._make_progress_hook(progress_callback)]
            opts["postprocessor_hooks"] = [self._make_postprocessor_hook(progress_callback)]

        # ── Cookies ──
        if cookies_browser:
            opts["cookiesfrombrowser"] = (cookies_browser,)
        elif cookies_file and os.path.isfile(cookies_file):
            opts["cookiefile"] = cookies_file

        return opts

    def _make_progress_hook(self, callback: ProgressCallback):
        """Crea el hook de progreso para yt-dlp."""

        def hook(d: dict):
            # Verificar cancelación
            if self._cancel_event.is_set():
                raise yt_dlp.utils.DownloadCancelled("Descarga cancelada por el usuario")

            status = d.get("status", "")

            if status == "downloading":
                # Calcular porcentaje
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                downloaded = d.get("downloaded_bytes", 0)

                if total > 0:
                    percent = (downloaded / total) * 100
                else:
                    # Usar la cadena de porcentaje de yt-dlp
                    percent_str = d.get("_percent_str", "0%")
                    try:
                        percent = float(percent_str.strip().replace("%", ""))
                    except (ValueError, AttributeError):
                        percent = 0.0

                speed_str = d.get("_speed_str", "")
                if speed_str:
                    speed_str = speed_str.strip()

                eta_str = d.get("_eta_str", "")
                if eta_str:
                    eta_str = eta_str.strip()

                progress = ProgressData(
                    status=DownloadStatus.DOWNLOADING,
                    percent=min(percent, 100.0),
                    speed=speed_str,
                    eta=eta_str,
                    filename=d.get("filename", ""),
                    video_title=d.get("info_dict", {}).get("title", ""),
                )
                callback(progress)

            elif status == "finished":
                progress = ProgressData(
                    status=DownloadStatus.MERGING,
                    percent=100.0,
                    filename=d.get("filename", ""),
                    video_title=d.get("info_dict", {}).get("title", ""),
                )
                callback(progress)

        return hook

    def _make_postprocessor_hook(self, callback: ProgressCallback):
        """Hook para postprocesamiento (merge, extracción de audio)."""

        def hook(d: dict):
            if self._cancel_event.is_set():
                return

            status = d.get("status", "")
            if status == "started":
                progress = ProgressData(
                    status=DownloadStatus.MERGING,
                    percent=100.0,
                )
                callback(progress)
            elif status == "finished":
                progress = ProgressData(
                    status=DownloadStatus.FINISHED,
                    percent=100.0,
                )
                callback(progress)

        return hook

    def _trim_video(self, input_path: str, start_time: str, end_time: str) -> str:
        """Recorta el video usando ffmpeg de forma rápida (stream copy)."""
        import subprocess
        from core.utils import get_bin_dir
        
        ffmpeg_exe = os.path.join(get_bin_dir(), "ffmpeg.exe")
        if not os.path.exists(ffmpeg_exe):
            return input_path # No se puede recortar

        ext = os.path.splitext(input_path)[1]
        output_path = input_path.replace(ext, f"_trimmed{ext}")
        
        cmd = [ffmpeg_exe, "-y", "-i", input_path]
        if start_time: cmd += ["-ss", start_time]
        if end_time: cmd += ["-to", end_time]
        cmd += ["-c", "copy", output_path]
        
        try:
            subprocess.run(cmd, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
            # Eliminar original si el recorte funcionó
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                os.remove(input_path)
                return output_path
        except Exception:
            pass
        return input_path

    def download(
        self,
        url: str,
        quality: Quality = Quality.BEST,
        resolution: VideoResolution = VideoResolution.BEST,
        output_dir: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        format_ext: str = "mp4",
        audio_bitrate: str = "320",
        cookies_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
        start_time: str = "",
        end_time: str = "",
    ):
        """Inicia la descarga con soporte para trimming y metadatos."""
        if self._is_downloading:
            return

        if output_dir is None:
            output_dir = get_default_download_dir()

        os.makedirs(output_dir, exist_ok=True)
        self._cancel_event.clear()
        self._is_downloading = True

        def _run():
            try:
                if progress_callback:
                    progress_callback(ProgressData(status=DownloadStatus.FETCHING_INFO))

                opts = self._build_opts(
                    quality=quality,
                    resolution=resolution,
                    output_dir=output_dir,
                    progress_callback=progress_callback,
                    format_ext=format_ext,
                    audio_bitrate=audio_bitrate,
                    cookies_browser=cookies_browser,
                    cookies_file=cookies_file,
                )

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=True) # Descargar directamente para evitar doble llamada si es posible
                    title = info.get("title", "Video")
                    filepath = ydl.prepare_filename(info)
                    
                    # yt-dlp puede cambiar la extensión tras el post-procesado
                    if not os.path.exists(filepath):
                        # Intentar encontrar el archivo con la extensión final
                        base = os.path.splitext(filepath)[0]
                        for f in os.listdir(output_dir):
                            if f.startswith(os.path.basename(base)):
                                filepath = os.path.join(output_dir, f)
                                break

                    # Aplicar Trimming si es necesario
                    if (start_time or end_time) and os.path.exists(filepath):
                        if progress_callback:
                            progress_callback(ProgressData(status=DownloadStatus.MERGING, video_title="Recortando video..."))
                        filepath = self._trim_video(filepath, start_time, end_time)

                if not self._cancel_event.is_set() and progress_callback:
                    # Registrar en historial (este manager se inyectará o usará globalmente)
                    from core.history import HistoryManager
                    HistoryManager().add_entry(title, url, format_ext)
                    
                    progress_callback(ProgressData(
                        status=DownloadStatus.FINISHED,
                        percent=100.0,
                        video_title=title,
                    ))

            except Exception as e:
                if progress_callback:
                    progress_callback(ProgressData(status=DownloadStatus.ERROR, error_message=str(e)))
            finally:
                self._is_downloading = False

        self._download_thread = threading.Thread(target=_run, daemon=True)
        self._download_thread.start()

    def cancel(self):
        """Cancela la descarga en curso."""
        if self._is_downloading:
            self._cancel_event.set()

    def get_info(self, url: str) -> Optional[dict]:
        """Extrae metadatos del video sin descargar."""
        opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception:
            return None

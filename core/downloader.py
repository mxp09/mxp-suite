"""
Motor de descarga basado en yt-dlp.
Maneja la configuración, ejecución en hilo separado, y reporte de progreso.
"""

import logging
import os
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Tuple

import yt_dlp

from core import errors
from core.utils import get_default_download_dir, parse_time_str
from mxp_common.binaries import DenoManager, FFmpegManager

logger = logging.getLogger("MXP")

# Instancia única a nivel de módulo. FFmpegManager ya cachea internamente la
# ruta resuelta (self._paths), pero eso no servía de nada si cada llamada
# creaba su propio FFmpegManager de usar y tirar — resolve_tool() lanzaba un
# "ffmpeg -version" real en cada _build_opts/_info_opts/expand_playlist,
# hasta dos veces por descarga y dos por cada consulta de metadatos (que
# ahora se dispara en cada URL pegada). Con la instancia compartida, el
# subproceso solo se ejecuta una vez por sesión.
_ffmpeg = FFmpegManager()
_deno = DenoManager()

# Contenedores donde yt-dlp puede incrustar la miniatura (EmbedThumbnailPP).
THUMBNAIL_FORMATS = {"mp3", "m4a", "mp4", "m4v", "mov", "mkv", "mka", "flac", "ogg", "opus"}


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
        noplaylist: bool = True,
        evasive: bool = False,
    ) -> dict:
        """
        Construye el diccionario de opciones para yt-dlp.

        `evasive` activa la segunda pasada que se usa tras un 403: impersonación
        TLS y clientes de reproducción alternativos. No se usa de entrada porque
        es más lenta y no hace falta en la mayoría de descargas.
        """

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
            ]
        else:
            # WEBM solo admite VP9/AV1 + Opus/Vorbis: pedir streams mp4+m4a
            # (H.264/AAC) y luego unirlos en .webm fallaba con "Conversion
            # failed". El resto de contenedores (mp4/mkv/mov) aceptan H.264.
            # ponytail: sin re-codificación; un sitio sin streams webm puede
            # seguir fallando en WEBM (YouTube siempre los tiene).
            v_ext, a_ext = ("webm", "webm") if format_ext == "webm" else ("mp4", "m4a")
            h = f"[height<={resolution.height}]" if resolution.height else ""
            format_str = (
                f"bestvideo{h}[ext={v_ext}]+bestaudio[ext={a_ext}]"
                f"/bestvideo{h}+bestaudio/best{h}/bestvideo+bestaudio/best"
            )
            postprocessors = [
                {"key": "FFmpegMetadata", "add_metadata": True},
            ]

        # yt-dlp solo sabe incrustar portada en estos contenedores; en WAV o
        # WEBM el postprocesador lanza error y tumbaba la descarga entera.
        embed_thumb = format_ext in THUMBNAIL_FORMATS
        if embed_thumb:
            postprocessors.append({"key": "EmbedThumbnail", "already_have_thumbnail": False})

        opts = {
            "format": format_str,
            "merge_output_format": format_ext,
            "outtmpl": output_template,
            "postprocessors": postprocessors,
            "format_sort": ["res", "vcodec:vp9", "acodec:opus", "tbr"] if format_ext == "webm"
                           else ["res", "vcodec:h264", "acodec:aac", "tbr"],
            "noplaylist": noplaylist,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            # Nunca pisar un archivo existente del usuario en silencio.
            "overwrites": False,
            "writethumbnail": embed_thumb,

            # ── Reintentos ──
            # Sin esto, un corte momentáneo o un 5xx pasajero mataba la descarga
            # entera. yt-dlp sabe reintentar solo; solo había que pedírselo.
            "retries": 5,
            "fragment_retries": 10,
            "extractor_retries": 3,
            "retry_sleep_functions": {"http": lambda n: min(2 ** n, 30)},
            "sleep_interval_requests": 0.5,
            "socket_timeout": 30,
            # Descarga fragmentos (DASH/HLS: YouTube, directos) en paralelo.
            "concurrent_fragment_downloads": 4,
            "ignoreerrors": False,
        }

        # NO se fija un User-Agent propio a propósito. La versión anterior
        # forzaba un Chrome/126 escrito a mano en 2024, que pisaba el UA que
        # yt-dlp mantiene al día y que, siendo tan viejo, era en sí mismo una
        # señal de bot para YouTube. Dejar que yt-dlp ponga el suyo es parte
        # del arreglo del 403, no un descuido.

        if evasive:
            # Segunda pasada: pedirle a YouTube clientes de reproducción
            # distintos, que es lo que suele desbloquear un 403.
            opts["extractor_args"] = {
                "youtube": {"player_client": ["tv", "web_safari", "android_vr"]}
            }
            # Y parecer un navegador de verdad a nivel de TLS. curl_cffi ya
            # viene empaquetado con la app, pero la impersonación es una mejora
            # opcional: si esta versión de yt-dlp no la soporta, se sigue sin
            # ella en vez de tirar la descarga.
            try:
                from yt_dlp.networking.impersonate import ImpersonateTarget
                opts["impersonate"] = ImpersonateTarget("chrome")
            except Exception:
                pass

        # ── FFmpeg ──
        # Se resuelve buscando en bin/ junto al ejecutable, en AppData y en el
        # PATH, y verificando que el binario responde. Antes se apuntaba a
        # AppData a ciegas y, en modo empaquetado, se asignaba esa ruta incluso
        # si el archivo no existía — con lo que el merge fallaba sin explicación.
        # Se usa la instancia compartida `_ffmpeg` (no `resolve_tool()` suelto)
        # para no relanzar "ffmpeg -version" en cada llamada.
        if _ffmpeg.ffmpeg:
            opts["ffmpeg_location"] = _ffmpeg.ffmpeg

        # Runtime JS para los retos de YouTube (yt-dlp >= 2025.11). Sin él,
        # YouTube devuelve menos formatos o directamente 403.
        if _deno.path:
            opts["js_runtimes"] = {"deno": {"path": _deno.path}}

        # ── Progress hook ──
        if progress_callback:
            opts["progress_hooks"] = [self._make_progress_hook(progress_callback)]
            opts["postprocessor_hooks"] = [self._make_postprocessor_hook(progress_callback)]

        # ── Cookies ──
        # Antes esto era un elif: elegir navegador hacía que un cookies.txt
        # seleccionado se ignorase sin decir nada. Ahora se aplican los dos si
        # el usuario configuró los dos.
        if cookies_browser:
            opts["cookiesfrombrowser"] = (cookies_browser,)
        if cookies_file and os.path.isfile(cookies_file):
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

            # Solo MERGING. Este hook salta una vez por CADA postprocesador
            # (metadatos, miniatura...), así que emitir FINISHED aquí daba la
            # descarga por terminada tras el primero: la app liberaba el hueco
            # de concurrencia y avisaba "completado" mientras aún se
            # procesaba. El único FINISHED lo emite _run() al acabar del todo.
            if d.get("status") in ("started", "finished"):
                callback(ProgressData(status=DownloadStatus.MERGING, percent=100.0))

        return hook

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

        def _attempt(evasive: bool):
            """Una pasada de descarga completa. Devuelve (título, ruta)."""
            opts = self._build_opts(
                quality=quality,
                resolution=resolution,
                output_dir=output_dir,
                progress_callback=progress_callback,
                format_ext=format_ext,
                audio_bitrate=audio_bitrate,
                cookies_browser=cookies_browser,
                cookies_file=cookies_file,
                evasive=evasive,
            )
            if start_time or end_time:
                # yt-dlp descarga SOLO ese tramo y corta en el fotograma exacto.
                # Sustituye al recorte posterior con ffmpeg, que bajaba el
                # vídeo entero y rompía rutas con la extensión repetida.
                start = parse_time_str(start_time) or 0
                end = parse_time_str(end_time) if end_time else float("inf")
                opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(start, end)])
                opts["force_keyframes_at_cuts"] = True

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "Video")
                # Ruta final real tras el postproceso (puede cambiar la
                # extensión). Antes se buscaba por prefijo en la carpeta y podía
                # devolver otro archivo con un título parecido.
                downloads = info.get("requested_downloads") or [{}]
                filepath = downloads[0].get("filepath") or ydl.prepare_filename(info)

            return title, filepath

        def _run():
            try:
                if progress_callback:
                    progress_callback(ProgressData(status=DownloadStatus.FETCHING_INFO))

                # Primer intento normal. Si el sitio responde con 403 o pide
                # verificación de bot, se repite una vez con impersonación y
                # otros clientes de reproducción: eso resuelve la mayoría de
                # 403 sin que el usuario tenga que tocar nada.
                try:
                    title, _filepath = _attempt(evasive=False)
                except Exception as first_error:
                    if (self._cancel_event.is_set()
                            or not errors.is_retryable_with_fallback(first_error)):
                        raise
                    if progress_callback:
                        progress_callback(ProgressData(
                            status=DownloadStatus.FETCHING_INFO,
                            video_title="Reintentando con otro método...",
                        ))
                    title, _filepath = _attempt(evasive=True)

                if not self._cancel_event.is_set() and progress_callback:
                    from core.history import HistoryManager
                    HistoryManager().add_entry(title, url, format_ext)

                    progress_callback(ProgressData(
                        status=DownloadStatus.FINISHED,
                        percent=100.0,
                        video_title=title,
                    ))

            except Exception as e:
                # Al log con traceback: antes el error solo salía en pantalla y no
                # había forma de diagnosticarlo después.
                logger.exception("Descarga fallida: %s", url)
                if progress_callback:
                    # Mensaje accionable en vez del volcado crudo de yt-dlp
                    detail = errors.classify(e)
                    progress_callback(ProgressData(
                        status=DownloadStatus.ERROR,
                        error_message=detail.full_text,
                    ))
            finally:
                self._is_downloading = False

        self._download_thread = threading.Thread(target=_run, daemon=True)
        self._download_thread.start()

    def cancel(self):
        """Cancela la descarga en curso."""
        if self._is_downloading:
            self._cancel_event.set()

    def _info_opts(self, cookies_browser=None, cookies_file=None,
                   noplaylist: bool = True, evasive: bool = False) -> dict:
        """
        Opciones para consultar metadatos, derivadas de las mismas que usa la
        descarga real.

        Antes get_info() tenía su propio diccionario suelto, sin cookies, sin
        reintentos y sin nada: la vista previa podía fallar en un vídeo que la
        descarga sí conseguía, y viceversa. Reutilizar _build_opts() elimina
        esa discrepancia de raíz.
        """
        opts = self._build_opts(
            quality=Quality.BEST,
            resolution=VideoResolution.BEST,
            output_dir=os.getcwd(),
            progress_callback=None,
            cookies_browser=cookies_browser,
            cookies_file=cookies_file,
            noplaylist=noplaylist,
            evasive=evasive,
        )
        # Nada de esto tiene sentido cuando no se descarga
        for key in ("postprocessors", "writethumbnail", "outtmpl",
                    "merge_output_format", "overwrites"):
            opts.pop(key, None)
        opts["skip_download"] = True
        return opts

    def get_info(
        self,
        url: str,
        cookies_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
    ) -> Tuple[Optional[dict], Optional["errors.DownloadError"]]:
        """
        Extrae metadatos sin descargar.

        Devuelve (info, None) si sale bien, o (None, DownloadError) con la causa
        REAL del fallo. La versión anterior hacía `except Exception: return None`,
        así que un 403, un vídeo privado, un bloqueo geográfico y la red caída
        acababan todos en el mismo mensaje "verifica que sea público y exista" —
        que en el caso más común (un 403) mandaba al usuario a mirar donde no era.
        """
        last_error = None
        # Primer intento normal; si es un 403 o un bot-check, se repite con
        # impersonación antes de rendirse.
        for evasive in (False, True):
            try:
                opts = self._info_opts(cookies_browser, cookies_file, evasive=evasive)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                if info:
                    return info, None
                last_error = "El sitio no devolvió información del contenido."
            except Exception as exc:
                last_error = exc
                if not errors.is_retryable_with_fallback(exc):
                    break

        return None, errors.classify(last_error)

    def expand_playlist(
        self,
        url: str,
        cookies_browser: Optional[str] = None,
        cookies_file: Optional[str] = None,
        limit: int = 500,
    ) -> Tuple[list, Optional[str], Optional["errors.DownloadError"]]:
        """
        Convierte una URL de playlist o canal en la lista de URLs que contiene.

        Devuelve (urls, titulo_de_la_lista, error). Si la URL es de un vídeo
        suelto devuelve esa misma URL en una lista de un elemento, para que
        quien llame pueda tratar ambos casos igual.

        Existe porque `noplaylist` estaba fijado a True en todo el código: pegar
        una playlist daba como mucho un vídeo, y a menudo el error genérico.
        """
        try:
            opts = self._info_opts(cookies_browser, cookies_file, noplaylist=False)
            # extract_flat solo lee el índice, sin resolver cada vídeo: una lista
            # de 200 tarda segundos en vez de minutos.
            opts["extract_flat"] = "in_playlist"
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            return [], None, errors.classify(exc)

        if not info:
            return [], None, errors.classify("El sitio no devolvió información.")

        entries = info.get("entries")
        if entries is None:
            return [url], info.get("title"), None

        urls = []
        for entry in entries:
            if not entry:
                continue
            entry_url = entry.get("url") or entry.get("webpage_url")
            if entry_url:
                urls.append(entry_url)
            if len(urls) >= limit:
                break

        return urls, info.get("title"), None

"""
Ventana principal de la aplicación Video Downloader.
Integra todos los componentes y orquesta el flujo de descarga.
"""

import os
import sys
import queue
import customtkinter as ctk

from gui.theme import Colors, Fonts, Spacing, Window, Radius
from gui.components import (
    HeaderFrame,
    URLInputFrame,
    QualitySelector,
    TrimmingFrame,
    OutputFolderFrame,
    CookieSettingsFrame,
    DownloadButton,
    ProgressPanel,
    FooterFrame,
    SetupProgressOverlay,
    HistoryWindow,
    ThumbnailPreviewFrame,
    ConverterPanelFrame,
    CompressorPanelFrame,
)
from core.downloader import VideoDownloader, Quality, VideoResolution, DownloadStatus, ProgressData
from core.utils import validate_url, show_windows_notification
from core.binaries import BinaryManager


import tkinterdnd2.TkinterDnD as tkdnd

class App(ctk.CTk, tkdnd.DnDWrapper):
    """Aplicación principal de Video Downloader."""

    def __init__(self):
        ctk.CTk.__init__(self)
        try:
            self.TkdndVersion = tkdnd._require(self)
        except Exception:
            pass
            
        self.title("MXP Suite")
        self.configure(fg_color=Colors.BG_DARK)

        # Intentar cargar icono
        try:
            from core.utils import get_resource_path
            icon_path = get_resource_path("assets/logo_transparente.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
        except Exception:
            pass
        self.active_jobs = {}  # url -> downloader_instance
        self.downloader = VideoDownloader()
        self._progress_queue: queue.Queue = queue.Queue()
        self._download_queue: list[dict] = []  # Cola de trabajos pendientes
        self._history_window = None
        self._metadata_queue: queue.Queue[dict] = queue.Queue()
        self._current_metadata_url = ""
        self._metadata_timer = None          # id del debounce de metadatos
        self._job_settings: dict = {}        # url -> ajustes con los que se lanzó
        self._failed_jobs: dict = {}         # url -> ajustes, para reintentar

        # ── Construir interfaz ──
        self._build_ui()

        # Configurar dimensiones iniciales y límites después de construir la UI
        self.geometry(f"{Window.WIDTH}x{Window.HEIGHT}")
        self.minsize(Window.MIN_WIDTH, Window.MIN_HEIGHT)

        # Centrar la ventana en la pantalla
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (Window.WIDTH // 2)
        y = (screen_height // 2) - (Window.HEIGHT // 2)
        self.geometry(f"{Window.WIDTH}x{Window.HEIGHT}+{x}+{y}")

        # ── Iniciar servicios ──
        self._poll_progress()
        self._setup_binaries()
        self._check_for_updates()

    def _check_for_updates(self):
        """
        Avisa si hay una versión nueva publicada.

        Todo ocurre en segundo plano y con margen tras el arranque: si no hay
        internet o no hay nada nuevo, no pasa absolutamente nada visible.
        """
        try:
            from mxp_common.update_dialog import attach_update_check
            attach_update_check(
                self,
                palette={
                    "bg": Colors.BG_SECONDARY,
                    "surface": Colors.BG_TERTIARY,
                    "border": Colors.BORDER_LIGHT,
                    "text": Colors.TEXT_PRIMARY,
                    "text_muted": Colors.TEXT_SECONDARY,
                    "accent": Colors.ACCENT_PRIMARY,
                    "accent_hover": Colors.BUTTON_HOVER,
                    "accent_text": Colors.BUTTON_TEXT,
                    "error": Colors.ERROR,
                },
            )
        except Exception:
            pass  # el updater nunca puede impedir que la app arranque

    def _build_ui(self):
        """Construye toda la interfaz gráfica con Sidebar."""
        
        # ── SETUP PROGRESS (SUPERIOR) ──
        self.setup_overlay = SetupProgressOverlay(self)
        self.setup_overlay.pack(fill="x", side="top")

        # ── SIDEBAR ──
        self.sidebar = ctk.CTkFrame(self, width=70, fg_color=Colors.BG_SECONDARY, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")

        # Separador vertical fino de 1px estilo electron
        self.sidebar_sep = ctk.CTkFrame(self, width=1, fg_color=Colors.BORDER, corner_radius=0)
        self.sidebar_sep.pack(side="left", fill="y")

        # Logo de la Sidebar
        self.sidebar_logo = ctk.CTkLabel(
            self.sidebar,
            text="MXP",
            font=(Fonts.FAMILY, 16, "bold"),
            text_color=Colors.ACCENT_YELLOW
        )
        self.sidebar_logo.pack(pady=(Spacing.XL, Spacing.SM))
        
        # Botón Descargador
        self.btn_nav_down = ctk.CTkButton(
            self.sidebar,
            text="📥",
            font=(Fonts.FAMILY, 20),
            fg_color=Colors.BG_TERTIARY,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.ACCENT_YELLOW,
            corner_radius=Radius.MD,
            width=48,
            height=48,
            command=lambda: self._switch_page("downloader")
        )
        self.btn_nav_down.pack(pady=Spacing.SM)

        # Botón Conversor
        self.btn_nav_conv = ctk.CTkButton(
            self.sidebar,
            text="🔄",
            font=(Fonts.FAMILY, 20),
            fg_color="transparent",
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.MD,
            width=48,
            height=48,
            command=lambda: self._switch_page("converter")
        )
        self.btn_nav_conv.pack(pady=Spacing.SM)

        # Botón Compresor
        self.btn_nav_comp = ctk.CTkButton(
            self.sidebar,
            text="🗜",
            font=(Fonts.FAMILY, 20),
            fg_color="transparent",
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.MD,
            width=48,
            height=48,
            command=lambda: self._switch_page("compressor")
        )
        self.btn_nav_comp.pack(pady=Spacing.SM)

        # Botón Historial
        self.history_btn = ctk.CTkButton(
            self.sidebar,
            text="📜",
            font=(Fonts.FAMILY, 20),
            fg_color="transparent",
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.MD,
            width=48,
            height=48,
            command=self._show_history
        )
        self.history_btn.pack(pady=Spacing.SM)

        # ── MAIN CONTENT (SCROLLABLE) ──
        self.main_container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=Colors.BG_TERTIARY,
            scrollbar_button_hover_color=Colors.BORDER_LIGHT,
        )
        self.main_container.pack(side="right", fill="both", expand=True)

        # Componentes
        self.header = HeaderFrame(self.main_container)
        self.header.pack(fill="x")

        self.url_input = URLInputFrame(self.main_container, on_url_change=self._on_url_change)
        self.url_input.pack(fill="x")

        self.thumbnail_preview = ThumbnailPreviewFrame(self.main_container)
        self.thumbnail_preview.pack(fill="x")

        options_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        options_frame.pack(fill="x")

        left_col = ctk.CTkFrame(options_frame, fg_color="transparent")
        left_col.pack(side="left", fill="both", expand=True)
        self.quality_selector = QualitySelector(left_col)
        self.quality_selector.pack(fill="x")

        right_col = ctk.CTkFrame(options_frame, fg_color="transparent")
        right_col.pack(side="right", fill="both", expand=True)
        self.output_folder = OutputFolderFrame(right_col)
        self.output_folder.pack(fill="x")

        # TRIMMING (Nueva sección superior a cookies)
        self.trimming_settings = TrimmingFrame(self.main_container)
        self.trimming_settings.pack(fill="x")

        self.cookies_settings = CookieSettingsFrame(self.main_container)
        self.cookies_settings.pack(fill="x")

        self.download_btn = DownloadButton(self.main_container, command=self._add_to_queue, cancel_command=self._cancel_download)
        self.download_btn.pack(fill="x")

        self.progress_panel = ProgressPanel(self.main_container, cancel_callback=self._cancel_single_download)
        self.progress_panel.pack(fill="x")

        self.footer = FooterFrame(self.main_container)
        self.footer.pack(fill="x")

        # ── CONVERTER CONTENT (SCROLLABLE - OCULTO POR DEFECTO) ──
        self.converter_container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=Colors.BG_TERTIARY,
            scrollbar_button_hover_color=Colors.BORDER_LIGHT,
        )
        self.converter_panel = ConverterPanelFrame(self.converter_container)
        self.converter_panel.pack(fill="both", expand=True)

        # ── COMPRESSOR CONTENT (SCROLLABLE - OCULTO POR DEFECTO) ──
        self.compressor_container = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            scrollbar_button_color=Colors.BG_TERTIARY,
            scrollbar_button_hover_color=Colors.BORDER_LIGHT,
        )
        self.compressor_panel = CompressorPanelFrame(self.compressor_container)
        self.compressor_panel.pack(fill="both", expand=True)

    def _setup_binaries(self):
        """
        Verifica que las dependencias estén listas y descarga lo que falte.

        Los binarios ya no se dan por buenos porque exista el archivo: se
        ejecutan para comprobar que responden. Una descarga cortada dejaba un
        ffmpeg.exe a medias que parecía correcto y luego fallaba en cada
        conversión sin decir por qué.
        """
        self.binary_manager = BinaryManager(progress_callback=self._on_setup_progress)

        if self.binary_manager.check_binaries():
            self.setup_overlay.pack_forget()
            # Mantener yt-dlp al día en segundo plano: es lo que evita que los
            # 403 vuelvan según los sitios van cambiando su extracción.
            self.binary_manager.update_engine_async()
            return

        faltan = ", ".join(self.binary_manager.missing())
        self.download_btn.set_enabled(False)
        self.setup_overlay.update_progress(f"Preparando: {faltan}...", 0)
        self.binary_manager.setup_binaries(
            on_done=lambda ok: self.after(0, self._on_setup_done, ok)
        )

    def _on_setup_progress(self, msg: str, percent: float):
        """Actualiza la barra de setup. Llega desde un hilo de descarga."""
        self.after(0, self._apply_setup_progress, msg, percent)

    def _apply_setup_progress(self, msg: str, percent: float):
        self.setup_overlay.update_progress(msg, max(percent, 0))

    def _on_setup_done(self, ok: bool):
        """Fin de la instalación de dependencias, ya en el hilo de Tk."""
        if ok:
            self.download_btn.set_enabled(True)
            self.setup_overlay.update_progress("Todo listo", 100)
            self.after(1500, self.setup_overlay.pack_forget)
            return

        # Sin dependencias la app no puede descargar, y el usuario merece
        # saberlo en vez de encontrarse un botón muerto sin explicación.
        faltan = ", ".join(self.binary_manager.missing()) or "las dependencias"
        self.setup_overlay.update_progress(
            f"No se pudo instalar {faltan}. Revisa tu conexión y reinicia la app.",
            0,
        )

    def _show_history(self):
        """Abre la ventana de historial."""
        if self._history_window is None or not self._history_window.winfo_exists():
            self._history_window = HistoryWindow(self)
        else:
            self._history_window.focus()

    def _switch_page(self, page_name: str):
        if page_name == "downloader":
            # Ocultar convertidor y compresor
            self.converter_container.pack_forget()
            self.compressor_container.pack_forget()
            
            # Mostrar descargador
            self.main_container.pack(side="right", fill="both", expand=True)
            
            # Actualizar botones sidebar
            self.btn_nav_down.configure(fg_color=Colors.BG_TERTIARY, text_color=Colors.ACCENT_YELLOW)
            self.btn_nav_conv.configure(fg_color="transparent", text_color=Colors.TEXT_PRIMARY)
            self.btn_nav_comp.configure(fg_color="transparent", text_color=Colors.TEXT_PRIMARY)
        elif page_name == "converter":
            # Ocultar descargador y compresor
            self.main_container.pack_forget()
            self.compressor_container.pack_forget()
            
            # Mostrar convertidor
            self.converter_container.pack(side="right", fill="both", expand=True)
            
            # Actualizar botones sidebar
            self.btn_nav_conv.configure(fg_color=Colors.BG_TERTIARY, text_color=Colors.ACCENT_YELLOW)
            self.btn_nav_down.configure(fg_color="transparent", text_color=Colors.TEXT_PRIMARY)
            self.btn_nav_comp.configure(fg_color="transparent", text_color=Colors.TEXT_PRIMARY)
        elif page_name == "compressor":
            # Ocultar descargador y convertidor
            self.main_container.pack_forget()
            self.converter_container.pack_forget()
            
            # Mostrar compresor
            self.compressor_container.pack(side="right", fill="both", expand=True)
            
            # Actualizar botones sidebar
            self.btn_nav_comp.configure(fg_color=Colors.BG_TERTIARY, text_color=Colors.ACCENT_YELLOW)
            self.btn_nav_down.configure(fg_color="transparent", text_color=Colors.TEXT_PRIMARY)
            self.btn_nav_conv.configure(fg_color="transparent", text_color=Colors.TEXT_PRIMARY)

    def _fetch_metadata_thread(self, url: str):
        """Hilo secundario para obtener info del video."""
        try:
            info, error = self.downloader.get_info(
                url,
                cookies_browser=self.cookies_settings.get_cookies_browser(),
                cookies_file=self.cookies_settings.get_cookies_file(),
            )
            if info:
                # Enviar los metadatos al hilo principal
                from core.utils import detect_platform
                duration = info.get("duration", 0)

                # Intentar obtener la mejor miniatura de la lista
                thumbnail = info.get("thumbnail", "")
                if not thumbnail and info.get("thumbnails"):
                    thumbnail = info["thumbnails"][-1].get("url", "")

                self._metadata_queue.put({
                    "status": "success",
                    "url": url,
                    "title": info.get("title", "Video"),
                    "duration": duration,
                    "thumbnail": thumbnail,
                    "platform": detect_platform(url)
                })
            else:
                self._metadata_queue.put({
                    "status": "failed",
                    "url": url,
                    "error": error.full_text if error else "",
                    "category": error.category if error else "unknown",
                })
        except Exception as exc:
            from core import errors
            detail = errors.classify(exc)
            self._metadata_queue.put({
                "status": "failed",
                "url": url,
                "error": detail.full_text,
                "category": detail.category,
            })

    def _handle_metadata(self, meta: dict):
        """Procesa y actualiza los metadatos en el hilo principal."""
        if meta.get("url") == self.url_input.get_url():
            if meta.get("status") == "success":
                self.thumbnail_preview.update_metadata(
                    title=meta.get("title"),
                    duration_sec=meta.get("duration"),
                    thumbnail_url=meta.get("thumbnail"),
                    platform=meta.get("platform")
                )
                self.trimming_settings.set_duration(meta.get("duration", 0))
            else:
                # Se muestra la causa REAL. Antes todo fallo — 403, vídeo
                # privado, bloqueo geográfico, wifi caído — daba el mismo
                # "verifica que sea público y exista", que mandaba al usuario
                # a mirar donde no era.
                self.thumbnail_preview.show_error(
                    meta.get("error")
                    or "No se pudo obtener información de este enlace."
                )
                self.trimming_settings.set_duration(0)

    def _on_url_change(self, url: str):
        is_valid = validate_url(url) or len(self.url_input.get_urls()) > 1
        self.download_btn.set_enabled(is_valid)

        if not validate_url(url):
            self._current_metadata_url = ""
            self.thumbnail_preview.hide()
            return

        if url == self._current_metadata_url:
            return

        self._current_metadata_url = url
        self.thumbnail_preview.show_loading()

        # Debounce de 600 ms. Antes se lanzaba una consulta de red en CADA
        # tecla pulsada: escribir o pegar una URL disparaba decenas de
        # peticiones simultáneas, que es justo lo que provoca el rate-limit
        # y acaba en 403.
        if self._metadata_timer is not None:
            try:
                self.after_cancel(self._metadata_timer)
            except Exception:
                pass
        self._metadata_timer = self.after(600, self._start_metadata_fetch, url)

    def _start_metadata_fetch(self, url: str):
        """Lanza la consulta de metadatos una vez pasado el debounce."""
        self._metadata_timer = None
        if url != self._current_metadata_url:
            return  # el usuario siguió escribiendo; esta URL ya no interesa
        import threading
        threading.Thread(
            target=self._fetch_metadata_thread,
            args=(url,),
            daemon=True,
        ).start()

    def _current_job_settings(self) -> dict:
        """Ajustes comunes a todos los trabajos que se encolen ahora."""
        mode = self.quality_selector.get_mode()
        res_key = self.quality_selector.get_resolution_key()
        return {
            "quality": Quality.AUDIO_ONLY if mode == "audio_only" else Quality.BEST,
            "resolution": VideoResolution[res_key],
            "output_dir": self.output_folder.get_folder(),
            "format_ext": (
                self.quality_selector.get_audio_format() if mode == "audio_only"
                else self.quality_selector.get_video_format()
            ),
            "audio_bitrate": self.quality_selector.get_audio_bitrate(),
            "cookies_browser": self.cookies_settings.get_cookies_browser(),
            "cookies_file": self.cookies_settings.get_cookies_file(),
            "start_time": self.trimming_settings.get_times()[0],
            "end_time": self.trimming_settings.get_times()[1],
        }

    def _add_to_queue(self):
        """
        Encola las descargas. Acepta una URL, varias, o una playlist entera.

        Una playlist se resuelve en segundo plano porque puede tardar unos
        segundos; el resto se encola al momento.
        """
        urls = self.url_input.get_urls()
        urls = [u for u in urls if validate_url(u)]
        if not urls:
            return

        # Validar tiempos de recorte
        if not self.trimming_settings.validate_times():
            show_windows_notification(
                "Recorte Inválido ⚠️",
                "Corrige el formato o los límites de tiempo de recorte."
            )
            return

        settings = self._current_job_settings()

        # El recorte solo tiene sentido sobre un vídeo concreto: aplicarlo a
        # una lista entera recortaría los 20 vídeos por el mismo minuto.
        if len(urls) > 1 and (settings["start_time"] or settings["end_time"]):
            settings["start_time"] = ""
            settings["end_time"] = ""

        # Una sola URL que además puede ser una playlist: se resuelve aparte
        if len(urls) == 1 and self._looks_like_playlist(urls[0]):
            self._expand_and_enqueue(urls[0], settings)
            return

        self._enqueue_urls(urls, settings)

    @staticmethod
    def _looks_like_playlist(url: str) -> bool:
        """Heurística barata para no consultar la red en cada enlace suelto."""
        markers = ("list=", "/playlist", "/channel/", "/c/", "/@", "/user/", "/sets/")
        return any(marker in url for marker in markers)

    def _expand_and_enqueue(self, url: str, settings: dict):
        """
        Resuelve una playlist o canal a la lista de vídeos que contiene.

        Antes esto era imposible: `noplaylist` estaba fijado a True en todo el
        código, así que pegar una lista descargaba como mucho un vídeo — y a
        menudo solo daba el error genérico.
        """
        import threading

        self.progress_panel.show()
        self.progress_panel.set_status("Leyendo la lista de vídeos...")

        def _work():
            urls, title, error = self.downloader.expand_playlist(
                url,
                cookies_browser=settings["cookies_browser"],
                cookies_file=settings["cookies_file"],
            )
            self.after(0, self._on_playlist_expanded, url, urls, title, error, settings)

        threading.Thread(target=_work, daemon=True).start()

    def _on_playlist_expanded(self, url, urls, title, error, settings):
        """Vuelta al hilo de Tk con el resultado de expandir la lista."""
        if error or not urls:
            self.progress_panel.set_status(
                error.full_text if error else "La lista no contiene vídeos descargables."
            )
            # Aun así se intenta como enlace suelto: puede ser un vídeo dentro
            # de una playlist, y el usuario probablemente quería ese vídeo.
            self._enqueue_urls([url], settings)
            return

        if len(urls) > 1:
            self.progress_panel.set_status(
                f"Lista «{title or 'sin título'}»: {len(urls)} vídeos en cola."
            )
        self._enqueue_urls(urls, settings)

    def _enqueue_urls(self, urls: list, settings: dict):
        """Mete N trabajos en la cola y arranca el procesamiento."""
        for url in urls:
            if url in self.active_jobs:
                continue  # ya se está descargando
            self._download_queue.append({"url": url, **settings})

        self.url_input._clear()
        self._process_next_in_queue()

    def _retry_failed(self):
        """Reencola solo los enlaces que fallaron, sin repetir los que ya fueron."""
        failed = list(self._failed_jobs.items())
        if not failed:
            return
        self._failed_jobs.clear()
        self.progress_panel.set_status(f"Reintentando {len(failed)} descarga(s)...")
        for url, settings in failed:
            self.progress_panel.remove_job(url)
            self._download_queue.append({"url": url, **settings})
        self._process_next_in_queue()

    def _process_next_in_queue(self):
        """Procesa los siguientes elementos en la cola respetando el límite de 3 concurrentes."""
        while self._download_queue and len(self.active_jobs) < 3:
            job = self._download_queue.pop(0)
            url = job["url"]
            
            # Crear un nuevo downloader para esta descarga en paralelo
            downloader = VideoDownloader()
            self.active_jobs[url] = downloader

            # Recordar con qué ajustes se lanzó, por si hay que reintentarla
            self._job_settings[url] = {k: v for k, v in job.items() if k != "url"}

            # Mostrar e inicializar el item de progreso específico
            self.progress_panel.show()
            self.progress_panel.add_job(url, url)

            # Lanzar la descarga
            downloader.download(
                progress_callback=lambda data, u=url: self._enqueue_progress(data, u),
                **job
            )

        # Con una tanda grande, decir cuántas quedan esperando turno
        if self._download_queue:
            self.progress_panel.set_status(
                f"{len(self.active_jobs)} descargando · "
                f"{len(self._download_queue)} en espera"
            )

        # Actualizar estado del botón de descargar/cancelar
        if self.active_jobs:
            self.download_btn.set_downloading(True)
            self.url_input.set_enabled(True)  # Permitir encolar más mientras se descarga
        else:
            self.download_btn.set_downloading(False)

    def _cancel_download(self):
        """Cancela todas las descargas activas y limpia la cola."""
        for url, downloader in list(self.active_jobs.items()):
            try:
                downloader.cancel()
            except Exception:
                pass
        self.active_jobs.clear()
        self._download_queue.clear()
        self.progress_panel.clear_all()
        self.download_btn.set_downloading(False)

    def _cancel_single_download(self, url: str):
        """Cancela una descarga específica por URL."""
        if url in self.active_jobs:
            try:
                self.active_jobs[url].cancel()
            except Exception:
                pass
            del self.active_jobs[url]
        
        # Eliminar también de la cola pendiente si estaba allí
        self._download_queue = [j for j in self._download_queue if j["url"] != url]
        
        # Quitar de la UI
        self.progress_panel.remove_job(url)
        
        # Si ya no quedan descargas activas, volver a estado normal en el botón principal
        if not self.active_jobs:
            self.download_btn.set_downloading(False)

    def _enqueue_progress(self, data: ProgressData, url: str):
        self._progress_queue.put((data, url))

    def _poll_progress(self):
        # 1. Cola de progreso de descargas
        try:
            while not self._progress_queue.empty():
                item = self._progress_queue.get_nowait()
                if isinstance(item, tuple) and len(item) == 2:
                    data, url = item
                    self._handle_progress(data, url)
        except Exception:
            pass

        # 2. Cola de metadatos de miniaturas
        try:
            while not self._metadata_queue.empty():
                meta = self._metadata_queue.get_nowait()
                self._handle_metadata(meta)
        except Exception:
            pass

        self.after(50, self._poll_progress)

    def _handle_progress(self, data: ProgressData, url: str):
        if url not in self.active_jobs:
            return
            
        status = data.status
        
        if status == DownloadStatus.FETCHING_INFO:
            self.progress_panel.update_progress(url, status="Obteniendo información...", percent=0.0)
        elif status == DownloadStatus.DOWNLOADING:
            self.progress_panel.update_progress(
                url, 
                status="Descargando...", 
                percent=data.percent,
                speed=data.speed,
                eta=data.eta,
                title=data.video_title or data.filename
            )
        elif status == DownloadStatus.MERGING:
            self.progress_panel.update_progress(url, status="Procesando/Uniendo audio...", percent=100.0)
        elif status in (DownloadStatus.FINISHED, DownloadStatus.ERROR, DownloadStatus.CANCELLED):
            if status == DownloadStatus.FINISHED:
                self.progress_panel.update_progress(url, status="¡Descarga completada! ✅", percent=100.0)
                show_windows_notification(
                    "¡Descarga Completada! ✅",
                    f"Se ha descargado correctamente: {data.video_title or 'tu archivo multimedia'}."
                )
            elif status == DownloadStatus.ERROR:
                self.progress_panel.update_progress(url, status=f"Error: {data.error_message}", percent=0.0)
                show_windows_notification(
                    "Error de Descarga ❌",
                    f"No se pudo completar la descarga. Error: {data.error_message[:80]}"
                )
                # Guardar los ajustes con los que se intentó, para poder
                # reintentar solo este enlace sin repetir los que sí funcionaron.
                settings = self._job_settings.get(url)
                if settings:
                    self._failed_jobs[url] = settings
            else:
                self.progress_panel.update_progress(url, status="Cancelado", percent=0.0)

            # Quitar de trabajos activos
            if url in self.active_jobs:
                del self.active_jobs[url]
            self._job_settings.pop(url, None)

            # Los fallos se quedan en pantalla: si desaparecen a los 4 segundos
            # como los éxitos, en una tanda larga nadie llega a leer qué pasó.
            if status != DownloadStatus.ERROR:
                self.after(4000, lambda u=url: self.progress_panel.remove_job(u))

            # Procesar el siguiente en la cola
            self._process_next_in_queue()

            # Si ya no quedan descargas activas, restaurar el botón principal
            if not self.active_jobs and not self._download_queue:
                self.download_btn.set_downloading(False)
                self._show_batch_summary()

    def _show_batch_summary(self):
        """Resumen al terminar una tanda, con opción de reintentar los fallidos."""
        failed = len(self._failed_jobs)
        if failed == 0:
            self.progress_panel.set_status("")
            self.progress_panel.set_retry_action(None)
            return

        self.progress_panel.set_status(
            f"{failed} descarga(s) no se completaron. Puedes reintentarlas."
        )
        self.progress_panel.set_retry_action(self._retry_failed)

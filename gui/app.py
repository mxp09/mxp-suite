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
        """Verifica y descarga los binarios necesarios."""
        bm = BinaryManager(progress_callback=self._on_setup_progress)
        if not bm.check_binaries():
            self.download_btn.set_enabled(False)
            bm.setup_binaries()
        else:
            self.setup_overlay.pack_forget()

    def _on_setup_progress(self, msg: str, percent: float):
        """Actualiza la barra de setup."""
        self.setup_overlay.update_progress(msg, percent)
        if percent >= 100:
            self.download_btn.set_enabled(True)

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
            info = self.downloader.get_info(url)
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
                self._metadata_queue.put({"status": "failed", "url": url})
        except Exception:
            self._metadata_queue.put({"status": "failed", "url": url})

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
                self.thumbnail_preview.show_error("No se pudo obtener información de este video. Verifica que sea público y exista.")
                self.trimming_settings.set_duration(0)

    def _on_url_change(self, url: str):
        is_valid = validate_url(url)
        self.download_btn.set_enabled(is_valid)

        if is_valid:
            if url != self._current_metadata_url:
                self._current_metadata_url = url
                self.thumbnail_preview.show_loading()
                
                # Lanzar hilo en segundo plano para no bloquear la interfaz
                import threading
                threading.Thread(
                    target=self._fetch_metadata_thread,
                    args=(url,),
                    daemon=True
                ).start()
        else:
            self._current_metadata_url = ""
            self.thumbnail_preview.hide()

    def _add_to_queue(self):
        """Añade una descarga a la cola."""
        url = self.url_input.get_url()
        if not validate_url(url): return

        # Validar tiempos de recorte
        if not self.trimming_settings.validate_times():
            show_windows_notification(
                "Recorte Inválido ⚠️",
                "Corrige el formato o los límites de tiempo de recorte."
            )
            return

        # Recoger settings actuales
        mode = self.quality_selector.get_mode()
        res_key = self.quality_selector.get_resolution_key()
        
        job = {
            "url": url,
            "quality": Quality.AUDIO_ONLY if mode == "audio_only" else Quality.BEST,
            "resolution": VideoResolution[res_key],
            "output_dir": self.output_folder.get_folder(),
            "format_ext": self.quality_selector.get_audio_format() if mode == "audio_only" else self.quality_selector.get_video_format(),
            "audio_bitrate": self.quality_selector.get_audio_bitrate(),
            "cookies_browser": self.cookies_settings.get_cookies_browser(),
            "cookies_file": self.cookies_settings.get_cookies_file(),
            "start_time": self.trimming_settings.get_times()[0],
            "end_time": self.trimming_settings.get_times()[1]
        }
        
        self._download_queue.append(job)
        self.url_input._clear()
        
        # Procesar cola de inmediato
        self._process_next_in_queue()

    def _process_next_in_queue(self):
        """Procesa los siguientes elementos en la cola respetando el límite de 3 concurrentes."""
        while self._download_queue and len(self.active_jobs) < 3:
            job = self._download_queue.pop(0)
            url = job["url"]
            
            # Crear un nuevo downloader para esta descarga en paralelo
            downloader = VideoDownloader()
            self.active_jobs[url] = downloader
            
            # Mostrar e inicializar el item de progreso específico
            self.progress_panel.show()
            self.progress_panel.add_job(url, url)
            
            # Lanzar la descarga
            downloader.download(
                progress_callback=lambda data, u=url: self._enqueue_progress(data, u),
                **job
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
            else:
                self.progress_panel.update_progress(url, status="Cancelado", percent=0.0)
                
            # Quitar de trabajos activos
            if url in self.active_jobs:
                del self.active_jobs[url]
                
            # Autoremover el item de la UI después de 4 segundos
            self.after(4000, lambda u=url: self.progress_panel.remove_job(u))
            
            # Procesar el siguiente en la cola
            self._process_next_in_queue()
            
            # Si ya no quedan descargas activas, restaurar el botón principal
            if not self.active_jobs:
                self.download_btn.set_downloading(False)

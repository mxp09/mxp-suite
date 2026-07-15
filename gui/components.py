"""
Componentes reutilizables de la GUI.
Cada clase es un frame/widget autocontenido de CustomTkinter.
"""

import os
import tkinter as tk
from tkinter import filedialog
from typing import Callable, Optional

import customtkinter as ctk

from gui.theme import Colors, Fonts, Spacing, Radius, PLATFORM_COLORS
from core.utils import detect_platform, get_platform_icon, validate_url, get_default_download_dir, get_resource_path
from PIL import Image


# ═══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════════════════════════════════

class HeaderFrame(ctk.CTkFrame):
    """Encabezado con título y descripción de la app."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        # ── Contenedor con gradiente visual ──
        self.inner = ctk.CTkFrame(
            self,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=Radius.LG,
            border_width=1,
            border_color=Colors.BORDER,
        )
        self.inner.pack(fill="x", padx=Spacing.LG, pady=(Spacing.LG, Spacing.SM))

        # Título principal
        title_frame = ctk.CTkFrame(self.inner, fg_color="transparent")
        title_frame.pack(fill="x", padx=Spacing.XL, pady=(Spacing.XL, Spacing.XS))

        # Cargar Logo del usuario (Transparente)
        try:
            from PIL import Image, ImageOps
            logo_path = get_resource_path("assets/logo_transparente.png")
            pil_image = Image.open(logo_path)
            
            # Evitar estiramiento: Ajustar al cuadrado de 64x64 manteniendo proporción
            # Creamos un lienzo transparente cuadrado
            size = (64, 64)
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))
            pil_image.thumbnail(size, Image.Resampling.LANCZOS)
            
            # Centrar la imagen en el lienzo
            x = (size[0] - pil_image.width) // 2
            y = (size[1] - pil_image.height) // 2
            canvas.paste(pil_image, (x, y))
            
            self.logo_image = ctk.CTkImage(light_image=canvas, dark_image=canvas, size=size)
            self.icon_label = ctk.CTkLabel(title_frame, text="", image=self.logo_image)
        except Exception:
            self.icon_label = ctk.CTkLabel(
                title_frame,
                text="⬇",
                font=(Fonts.FAMILY, 32),
                text_color=Colors.ACCENT_YELLOW,
            )
        
        self.icon_label.pack(side="left", padx=(0, Spacing.LG))

        title_text = ctk.CTkFrame(title_frame, fg_color="transparent")
        title_text.pack(side="left", fill="x", expand=True)

        self.title_label = ctk.CTkLabel(
            title_text,
            text="MXP Downloader",
            font=(Fonts.FAMILY, Fonts.SIZE_HERO, "bold"),
            text_color=Colors.TEXT_PRIMARY,
            anchor="w",
        )
        self.title_label.pack(anchor="w")

        self.subtitle_label = ctk.CTkLabel(
            title_text,
            text="Descarga multimedia con máxima fidelidad",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            text_color=Colors.TEXT_SECONDARY,
            anchor="w",
        )
        self.subtitle_label.pack(anchor="w")

        # Badges de plataformas
        badges_frame = ctk.CTkFrame(self.inner, fg_color="transparent")
        badges_frame.pack(fill="x", padx=Spacing.XL, pady=(Spacing.XS, Spacing.LG))

        platforms = [
            ("▶ YouTube", Colors.YOUTUBE_RED),
            ("♪ TikTok", Colors.TIKTOK_CYAN),
            ("📷 Instagram", Colors.INSTAGRAM_PINK),
            ("📘 Facebook", Colors.FACEBOOK_BLUE),
            ("𝕏 X", Colors.TEXT_PRIMARY),
        ]

        for name, color in platforms:
            badge = ctk.CTkLabel(
                badges_frame,
                text=f"  {name}  ",
                font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold"),
                text_color=color,
                fg_color=Colors.BG_TERTIARY,
                corner_radius=Radius.SM,
                height=24,
            )
            badge.pack(side="left", padx=(0, Spacing.SM))


# ═══════════════════════════════════════════════════════════════════════════════
#  URL INPUT
# ═══════════════════════════════════════════════════════════════════════════════

class URLInputFrame(ctk.CTkFrame):
    """Campo de entrada de URL con detección de plataforma."""

    def __init__(self, master, on_url_change: Optional[Callable] = None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.on_url_change = on_url_change

        # ── Label ──
        label_frame = ctk.CTkFrame(self, fg_color="transparent")
        label_frame.pack(fill="x", padx=Spacing.LG, pady=(Spacing.MD, Spacing.XS))

        ctk.CTkLabel(
            label_frame,
            text="URL del video",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"),
            text_color=Colors.TEXT_PRIMARY,
        ).pack(side="left")

        self.platform_badge = ctk.CTkLabel(
            label_frame,
            text="",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold"),
            text_color=Colors.TEXT_SECONDARY,
            fg_color=Colors.BG_TERTIARY,
            corner_radius=Radius.SM,
            height=22,
        )
        self.platform_badge.pack(side="right")
        self.platform_badge.pack_forget()  # Oculto inicialmente

        # ── Input + Botón Pegar ──
        input_frame = ctk.CTkFrame(
            self,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=Radius.MD,
            border_width=1,
            border_color=Colors.BORDER,
        )
        input_frame.pack(fill="x", padx=Spacing.LG)

        self.url_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Pega aquí la URL del video...",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY),
            text_color=Colors.TEXT_PRIMARY,
            placeholder_text_color=Colors.TEXT_MUTED,
            fg_color="transparent",
            border_width=0,
            height=48,
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=Spacing.MD)

        # Registrar evento de escritura
        self.url_entry.bind("<KeyRelease>", self._on_key_release)

        self.paste_btn = ctk.CTkButton(
            input_frame,
            text="📋 Pegar",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            fg_color=Colors.BG_TERTIARY,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            width=90,
            height=36,
            command=self._paste_from_clipboard,
        )
        self.paste_btn.pack(side="right", padx=Spacing.SM, pady=Spacing.SM)

        self.clear_btn = ctk.CTkButton(
            input_frame,
            text="✕",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY),
            fg_color="transparent",
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_MUTED,
            corner_radius=Radius.SM,
            width=36,
            height=36,
            command=self._clear,
        )
        self.clear_btn.pack(side="right", pady=Spacing.SM)
        self.clear_btn.pack_forget()  # Oculto hasta que haya texto

    def _paste_from_clipboard(self):
        """Pega contenido del portapapeles."""
        try:
            clipboard = self.clipboard_get()
            if clipboard:
                self.url_entry.delete(0, "end")
                self.url_entry.insert(0, clipboard.strip())
                self._on_key_release(None)
        except tk.TclError:
            pass

    def _clear(self):
        """Limpia el campo de URL."""
        self.url_entry.delete(0, "end")
        self.platform_badge.pack_forget()
        self.clear_btn.pack_forget()
        if self.on_url_change:
            self.on_url_change("")

    def _on_key_release(self, event):
        """Detecta plataforma al escribir."""
        url = self.url_entry.get().strip()

        if url:
            self.clear_btn.pack(side="right", pady=Spacing.SM)
            platform = detect_platform(url)
            icon = get_platform_icon(platform)
            color = PLATFORM_COLORS.get(platform, Colors.TEXT_SECONDARY)

            self.platform_badge.configure(
                text=f"  {icon} {platform}  ",
                text_color=color,
            )
            self.platform_badge.pack(side="right")
        else:
            self.platform_badge.pack_forget()
            self.clear_btn.pack_forget()

        if self.on_url_change:
            self.on_url_change(url)

    def get_url(self) -> str:
        """Retorna la URL actual."""
        return self.url_entry.get().strip()

    def set_enabled(self, enabled: bool):
        """Habilita o deshabilita el input."""
        state = "normal" if enabled else "disabled"
        self.url_entry.configure(state=state)
        self.paste_btn.configure(state=state)


# ═══════════════════════════════════════════════════════════════════════════════
#  QUALITY SELECTOR
# ═══════════════════════════════════════════════════════════════════════════════

class QualitySelector(ctk.CTkFrame):
    """Selector de calidad con tipo (Video/Audio), resolución, formato y bitrate."""

    # Opciones de Video
    RESOLUTION_OPTIONS = [
        ("⚡ Máxima Calidad", "BEST"),
        ("🎯 4K (2160p)", "RES_2160"),
        ("🎯 2K (1440p)", "RES_1440"),
        ("🎯 1080p Full HD", "RES_1080"),
        ("🎯 720p HD", "RES_720"),
        ("🎯 480p", "RES_480"),
        ("🎯 360p", "RES_360"),
    ]
    VIDEO_FORMATS = ["MP4", "MKV", "MOV", "WEBM"]

    # Opciones de Audio
    AUDIO_FORMATS = ["MP3", "WAV"]
    AUDIO_BITRATES = ["320 kbps", "256 kbps", "192 kbps", "128 kbps"]

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        ctk.CTkLabel(
            self,
            text="Calidad y Formato",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"),
            text_color=Colors.TEXT_PRIMARY,
        ).pack(anchor="w", padx=Spacing.LG, pady=(Spacing.MD, Spacing.XS))

        selector_frame = ctk.CTkFrame(
            self,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=Radius.MD,
            border_width=1,
            border_color=Colors.BORDER,
        )
        selector_frame.pack(fill="x", padx=Spacing.LG)

        self.quality_var = ctk.StringVar(value="best")

        # ── SECCIÓN VIDEO ──
        self.video_radio = ctk.CTkRadioButton(
            selector_frame,
            text="🎬  Video (Imagen + Sonido)",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY),
            text_color=Colors.TEXT_PRIMARY,
            fg_color=Colors.ACCENT_PRIMARY,
            hover_color=Colors.ACCENT_GOLD,
            border_color=Colors.BORDER_LIGHT,
            variable=self.quality_var,
            value="best",
            command=self._update_visibility,
        )
        self.video_radio.pack(anchor="w", padx=Spacing.LG, pady=(Spacing.MD, Spacing.XS))

        self.video_options_frame = ctk.CTkFrame(selector_frame, fg_color="transparent")
        self.video_options_frame.pack(fill="x", padx=(Spacing.LG + 24, Spacing.LG), pady=(0, Spacing.SM))

        # Dropdown: Resolución
        res_label = ctk.CTkLabel(self.video_options_frame, text="Res:", font=(Fonts.FAMILY, Fonts.SIZE_SMALL), text_color=Colors.TEXT_SECONDARY)
        res_label.pack(side="left", padx=(0, 5))
        self.resolution_var = ctk.StringVar(value="⚡ Máxima Calidad")
        self.resolution_menu = self._create_menu(self.video_options_frame, self.resolution_var, [label for label, _ in self.RESOLUTION_OPTIONS], width=140)
        self.resolution_menu.pack(side="left", padx=(0, 10))

        # Dropdown: Formato Video
        fmt_v_label = ctk.CTkLabel(self.video_options_frame, text="Formato:", font=(Fonts.FAMILY, Fonts.SIZE_SMALL), text_color=Colors.TEXT_SECONDARY)
        fmt_v_label.pack(side="left", padx=(0, 5))
        self.video_format_var = ctk.StringVar(value="MP4")
        self.video_format_menu = self._create_menu(self.video_options_frame, self.video_format_var, self.VIDEO_FORMATS, width=80)
        self.video_format_menu.pack(side="left")

        # Separador sutil
        self.separator = ctk.CTkFrame(selector_frame, fg_color=Colors.BORDER, height=1)
        self.separator.pack(fill="x", padx=Spacing.LG, pady=Spacing.XS)

        # ── SECCIÓN AUDIO ──
        self.audio_radio = ctk.CTkRadioButton(
            selector_frame,
            text="🎵  Solo Audio",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY),
            text_color=Colors.TEXT_PRIMARY,
            fg_color=Colors.ACCENT_PRIMARY,
            hover_color=Colors.ACCENT_GOLD,
            border_color=Colors.BORDER_LIGHT,
            variable=self.quality_var,
            value="audio_only",
            command=self._update_visibility,
        )
        self.audio_radio.pack(anchor="w", padx=Spacing.LG, pady=(Spacing.XS, Spacing.MD))

        self.audio_options_frame = ctk.CTkFrame(selector_frame, fg_color="transparent")
        
        # Dropdown: Formato Audio
        fmt_a_label = ctk.CTkLabel(self.audio_options_frame, text="Formato:", font=(Fonts.FAMILY, Fonts.SIZE_SMALL), text_color=Colors.TEXT_SECONDARY)
        fmt_a_label.pack(side="left", padx=(0, 5))
        self.audio_format_var = ctk.StringVar(value="MP3")
        self.audio_format_menu = self._create_menu(self.audio_options_frame, self.audio_format_var, self.AUDIO_FORMATS, width=80, command=self._on_audio_format_change)
        self.audio_format_menu.pack(side="left", padx=(0, 10))

        # Dropdown: Bitrate
        self.bitrate_label = ctk.CTkLabel(self.audio_options_frame, text="Calidad:", font=(Fonts.FAMILY, Fonts.SIZE_SMALL), text_color=Colors.TEXT_SECONDARY)
        self.bitrate_label.pack(side="left", padx=(0, 5))
        self.audio_bitrate_var = ctk.StringVar(value="320 kbps")
        self.audio_bitrate_menu = self._create_menu(self.audio_options_frame, self.audio_bitrate_var, self.AUDIO_BITRATES, width=100)
        self.audio_bitrate_menu.pack(side="left")

        # Inicializar visibilidad
        self._update_visibility()

    def _create_menu(self, master, variable, values, width, command=None):
        """Helper para crear menús de opciones con estilo uniforme."""
        return ctk.CTkOptionMenu(
            master,
            variable=variable,
            values=values,
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color=Colors.BG_TERTIARY,
            button_color=Colors.BG_TERTIARY,
            button_hover_color=Colors.BG_HOVER,
            dropdown_fg_color=Colors.BG_SECONDARY,
            dropdown_hover_color=Colors.BG_HOVER,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            height=32,
            width=width,
            command=command
        )

    def _update_visibility(self):
        """Gestiona la visibilidad de los sub-paneles de opciones."""
        mode = self.quality_var.get()
        if mode == "best":
            self.audio_options_frame.pack_forget()
            self.video_options_frame.pack(fill="x", padx=(Spacing.LG + 24, Spacing.LG), pady=(0, Spacing.SM))
        else:
            self.video_options_frame.pack_forget()
            self.audio_options_frame.pack(fill="x", padx=(Spacing.LG + 24, Spacing.LG), pady=(0, Spacing.MD))
            self._on_audio_format_change(self.audio_format_var.get())

    def _on_audio_format_change(self, fmt):
        """Oculta el bitrate si el formato es WAV (sin pérdida)."""
        if fmt == "WAV":
            self.bitrate_label.pack_forget()
            self.audio_bitrate_menu.pack_forget()
        else:
            self.bitrate_label.pack(side="left", padx=(0, 5))
            self.audio_bitrate_menu.pack(side="left")

    def get_mode(self) -> str:
        """Retorna 'best' (video) o 'audio_only'."""
        return self.quality_var.get()

    def get_video_format(self) -> str:
        return self.video_format_var.get().lower()

    def get_audio_format(self) -> str:
        return self.audio_format_var.get().lower()

    def get_audio_bitrate(self) -> str:
        # Retorna solo el número (e.g. "320")
        return self.audio_bitrate_var.get().split()[0]

    def get_resolution_key(self) -> str:
        """Retorna la key de resolución seleccionada (e.g. 'BEST', 'RES_1080')."""
        current_label = self.resolution_var.get()
        for label, key in self.RESOLUTION_OPTIONS:
            if label == current_label:
                return key
        return "BEST"


# ═══════════════════════════════════════════════════════════════════════════════
#  OUTPUT FOLDER
# ═══════════════════════════════════════════════════════════════════════════════

class OutputFolderFrame(ctk.CTkFrame):
    """Selector de carpeta de salida."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        ctk.CTkLabel(
            self,
            text="Guardar en",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"),
            text_color=Colors.TEXT_PRIMARY,
        ).pack(anchor="w", padx=Spacing.LG, pady=(Spacing.MD, Spacing.XS))

        folder_frame = ctk.CTkFrame(
            self,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=Radius.MD,
            border_width=1,
            border_color=Colors.BORDER,
        )
        folder_frame.pack(fill="x", padx=Spacing.LG)

        self.folder_var = ctk.StringVar(value=get_default_download_dir())

        self.folder_entry = ctk.CTkEntry(
            folder_frame,
            textvariable=self.folder_var,
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            text_color=Colors.TEXT_SECONDARY,
            fg_color="transparent",
            border_width=0,
            height=42,
            state="readonly",
        )
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=Spacing.MD)

        self.browse_btn = ctk.CTkButton(
            folder_frame,
            text="📂 Cambiar",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            fg_color=Colors.BG_TERTIARY,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            width=100,
            height=34,
            command=self._browse_folder,
        )
        self.browse_btn.pack(side="right", padx=Spacing.SM, pady=Spacing.SM)

    def _browse_folder(self):
        """Abre diálogo para seleccionar carpeta."""
        folder = filedialog.askdirectory(
            title="Seleccionar carpeta de descarga",
            initialdir=self.folder_var.get(),
        )
        if folder:
            self.folder_var.set(folder)

    def get_folder(self) -> str:
        """Retorna la carpeta seleccionada."""
        return self.folder_var.get()


# ═══════════════════════════════════════════════════════════════════════════════
#  COOKIE SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

class CookieSettingsFrame(ctk.CTkFrame):
    """Panel de configuración de cookies (expandible)."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._expanded = False

        # ── Botón toggle ──
        self.toggle_btn = ctk.CTkButton(
            self,
            text="🍪  Configuración de Cookies (Opcional)  ▸",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color="transparent",
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_SECONDARY,
            anchor="w",
            height=32,
            command=self._toggle,
        )
        self.toggle_btn.pack(fill="x", padx=Spacing.LG, pady=(Spacing.SM, 0))

        # ── Panel expandible ──
        self.content = ctk.CTkFrame(
            self,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=Radius.MD,
            border_width=1,
            border_color=Colors.BORDER,
        )

        # Método 1: Desde el navegador
        ctk.CTkLabel(
            self.content,
            text="Método 1: Cookies del navegador",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            text_color=Colors.TEXT_PRIMARY,
        ).pack(anchor="w", padx=Spacing.LG, pady=(Spacing.MD, Spacing.XS))

        self.browser_var = ctk.StringVar(value="ninguno")
        browser_menu = ctk.CTkOptionMenu(
            self.content,
            variable=self.browser_var,
            values=["ninguno", "chrome", "firefox", "edge", "brave", "opera"],
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color=Colors.BG_TERTIARY,
            button_color=Colors.BG_TERTIARY,
            button_hover_color=Colors.BG_HOVER,
            dropdown_fg_color=Colors.BG_SECONDARY,
            dropdown_hover_color=Colors.BG_HOVER,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            height=34,
            width=200,
        )
        browser_menu.pack(anchor="w", padx=Spacing.LG, pady=(0, Spacing.SM))

        # Separador
        ctk.CTkFrame(
            self.content,
            fg_color=Colors.BORDER,
            height=1,
        ).pack(fill="x", padx=Spacing.LG, pady=Spacing.XS)

        # Método 2: Archivo cookies.txt
        ctk.CTkLabel(
            self.content,
            text="Método 2: Archivo cookies.txt",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            text_color=Colors.TEXT_PRIMARY,
        ).pack(anchor="w", padx=Spacing.LG, pady=(Spacing.SM, Spacing.XS))

        file_frame = ctk.CTkFrame(self.content, fg_color="transparent")
        file_frame.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.MD))

        self.cookie_file_var = ctk.StringVar(value="")
        self.cookie_entry = ctk.CTkEntry(
            file_frame,
            textvariable=self.cookie_file_var,
            placeholder_text="Ruta al archivo cookies.txt...",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            text_color=Colors.TEXT_SECONDARY,
            placeholder_text_color=Colors.TEXT_MUTED,
            fg_color=Colors.BG_DARK,
            border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Radius.SM,
            height=34,
        )
        self.cookie_entry.pack(side="left", fill="x", expand=True, padx=(0, Spacing.SM))

        ctk.CTkButton(
            file_frame,
            text="📄",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY),
            fg_color=Colors.BG_TERTIARY,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            width=40,
            height=34,
            command=self._browse_cookies,
        ).pack(side="right")

        # Nota
        ctk.CTkLabel(
            self.content,
            text="💡 Necesario para Instagram/Facebook con login",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY),
            text_color=Colors.TEXT_MUTED,
        ).pack(anchor="w", padx=Spacing.LG, pady=(0, Spacing.MD))

    def _toggle(self):
        """Expande/colapsa el panel."""
        self._expanded = not self._expanded
        if self._expanded:
            self.content.pack(fill="x", padx=Spacing.LG, pady=(Spacing.XS, 0))
            self.toggle_btn.configure(text="🍪  Configuración de Cookies (Opcional)  ▾")
        else:
            self.content.pack_forget()
            self.toggle_btn.configure(text="🍪  Configuración de Cookies (Opcional)  ▸")

    def _browse_cookies(self):
        """Abre diálogo para seleccionar cookies.txt."""
        filepath = filedialog.askopenfilename(
            title="Seleccionar archivo de cookies",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if filepath:
            self.cookie_file_var.set(filepath)

    def get_cookies_browser(self) -> Optional[str]:
        """Retorna el navegador seleccionado para cookies, o None."""
        val = self.browser_var.get()
        return val if val != "ninguno" else None

    def get_cookies_file(self) -> Optional[str]:
        """Retorna la ruta al archivo cookies.txt, o None."""
        val = self.cookie_file_var.get().strip()
        return val if val and os.path.isfile(val) else None


# ═══════════════════════════════════════════════════════════════════════════════
#  DOWNLOAD BUTTON
# ═══════════════════════════════════════════════════════════════════════════════

class DownloadButton(ctk.CTkFrame):
    """Botón de descarga con estados visuales."""

    def __init__(self, master, command: Callable, cancel_command: Callable, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self._download_command = command
        self._cancel_command = cancel_command
        self._is_downloading = False

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=Spacing.LG, pady=Spacing.MD)

        self.download_btn = ctk.CTkButton(
            btn_frame,
            text="⬇  Descargar Video",
            font=(Fonts.FAMILY, Fonts.SIZE_SUBTITLE, "bold"),
            fg_color=Colors.ACCENT_PRIMARY,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.BUTTON_TEXT,
            corner_radius=Radius.LG,
            height=52,
            command=self._on_click,
        )
        self.download_btn.pack(fill="x")

    def _on_click(self):
        if self._is_downloading:
            self._cancel_command()
        else:
            self._download_command()

    def set_downloading(self, downloading: bool):
        """Cambia al estado de descarga."""
        self._is_downloading = downloading
        if downloading:
            self.download_btn.configure(
                text="✕  Cancelar Descarga",
                fg_color=Colors.ERROR,
                hover_color="#c0392b",
            )
        else:
            self.download_btn.configure(
                text="⬇  Descargar Video",
                fg_color=Colors.ACCENT_PRIMARY,
                hover_color=Colors.BUTTON_HOVER,
            )

    def set_enabled(self, enabled: bool):
        """Habilita o deshabilita el botón."""
        self.download_btn.configure(
            state="normal" if enabled else "disabled",
            fg_color=Colors.ACCENT_PRIMARY if enabled else Colors.BUTTON_DISABLED,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  PROGRESS PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class DownloadProgressItem(ctk.CTkFrame):
    """Elemento individual de progreso de descarga con botón de cancelar."""
    def __init__(self, master, url, title="Descarga", cancel_callback=None, **kwargs):
        super().__init__(master, fg_color=Colors.BG_TERTIARY, corner_radius=Radius.SM, border_width=1, border_color=Colors.BORDER, **kwargs)
        self.url = url
        self.cancel_callback = cancel_callback
        
        # Usar grid para alinear el botón cerrar a la derecha
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        
        # Contenedor de información (Izquierda)
        left_frame = ctk.CTkFrame(self, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=Spacing.MD, pady=Spacing.SM)
        
        # Título
        self.title_label = ctk.CTkLabel(
            left_frame,
            text=f"🎬 {title[:60] + '...' if len(title) > 60 else title}",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            text_color=Colors.TEXT_PRIMARY,
            anchor="w"
        )
        self.title_label.pack(fill="x", pady=(0, Spacing.XS))
        
        # Progreso
        self.progress_bar = ctk.CTkProgressBar(
            left_frame,
            fg_color=Colors.PROGRESS_BG,
            progress_color=Colors.ACCENT_YELLOW,
            corner_radius=Radius.SM,
            height=8
        )
        self.progress_bar.pack(fill="x", pady=Spacing.XS)
        self.progress_bar.set(0)
        
        # Detalles
        details = ctk.CTkFrame(left_frame, fg_color="transparent")
        details.pack(fill="x")
        
        self.status_label = ctk.CTkLabel(details, text="Preparando...", font=(Fonts.FAMILY, Fonts.SIZE_TINY), text_color=Colors.TEXT_SECONDARY)
        self.status_label.pack(side="left")
        
        self.details_label = ctk.CTkLabel(details, text="", font=(Fonts.FAMILY_MONO, Fonts.SIZE_TINY), text_color=Colors.TEXT_MUTED)
        self.details_label.pack(side="right")
        
        # Botón de cancelación (Derecha)
        if self.cancel_callback:
            self.cancel_btn = ctk.CTkButton(
                self,
                text="✕",
                width=24,
                height=24,
                fg_color="transparent",
                hover_color=Colors.ERROR,
                text_color=Colors.TEXT_SECONDARY,
                font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
                command=self._on_cancel
            )
            self.cancel_btn.grid(row=0, column=1, padx=Spacing.MD, pady=Spacing.SM, sticky="e")

    def _on_cancel(self):
        if self.cancel_callback:
            self.cancel_callback(self.url)

    def update_data(self, status, percent=0.0, speed="", eta="", title=""):
        if title:
            self.title_label.configure(text=f"🎬 {title[:60] + '...' if len(title) > 60 else title}")
        self.progress_bar.set(percent / 100.0)
        self.status_label.configure(text=status)
        
        det = ""
        if speed: det += f"⚡ {speed} "
        if eta: det += f"│ ⏱ {eta}"
        self.details_label.configure(text=det)


class ProgressPanel(ctk.CTkFrame):
    """Contenedor de progreso de descargas múltiples."""

    def __init__(self, master, cancel_callback=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self._visible = False
        self.items: dict[str, DownloadProgressItem] = {}
        self.cancel_callback = cancel_callback

    def show(self):
        if not self._visible:
            self.container.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.SM))
            self._visible = True

    def hide(self):
        if self._visible:
            self.container.pack_forget()
            self._visible = False

    def add_job(self, url, title):
        self.show()
        if url in self.items:
            return
        item = DownloadProgressItem(self.container, url, title, cancel_callback=self.cancel_callback)
        item.pack(fill="x", pady=Spacing.XS)
        self.items[url] = item

    def remove_job(self, url):
        if url in self.items:
            try:
                self.items[url].destroy()
            except Exception:
                pass
            del self.items[url]
        if not self.items:
            self.hide()

    def clear_all(self):
        for item in list(self.items.values()):
            try:
                item.destroy()
            except Exception:
                pass
        self.items.clear()
        self.hide()

    def update_progress(self, url, status, percent=0.0, speed="", eta="", title=""):
        if url not in self.items:
            self.add_job(url, title or url)
        self.items[url].update_data(status, percent, speed, eta, title)


# ═══════════════════════════════════════════════════════════════════════════════
#  TRIMMING SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════

class TrimmingRangeSlider(ctk.CTkFrame):
    """Un slider de rango interactivo (dos deslizadores) usando Tkinter Canvas."""
    
    def __init__(self, master, duration=100, on_change=None, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.duration = duration
        self.on_change = on_change
        
        self.start_sec = 0
        self.end_sec = duration
        
        self.active_handle = None  # 'start' o 'end'
        self.canvas_width = 300
        self.track_height = 6
        self.handle_radius = 8
        self.y_center = 20
        
        self.canvas = tk.Canvas(
            self,
            height=40,
            bg=Colors.BG_SECONDARY,
            highlightthickness=0,
            bd=0
        )
        self.canvas.pack(fill="x", padx=10, pady=5)
        
        self.canvas.bind("<Configure>", self._on_configure)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Motion>", self._on_motion)
        
    def set_duration(self, duration: int):
        self.duration = duration if duration > 0 else 100
        self.start_sec = 0
        self.end_sec = self.duration
        self._redraw()
        
    def set_values(self, start_sec: int, end_sec: int):
        self.start_sec = max(0, min(start_sec, self.duration))
        self.end_sec = max(self.start_sec, min(end_sec, self.duration))
        self._redraw()
        
    def _sec_to_x(self, sec: float) -> float:
        margin = 15
        usable_width = self.canvas_width - 2 * margin
        ratio = sec / self.duration
        return margin + ratio * usable_width
        
    def _x_to_sec(self, x: float) -> float:
        margin = 15
        usable_width = self.canvas_width - 2 * margin
        ratio = (x - margin) / usable_width
        ratio = max(0.0, min(ratio, 1.0))
        return ratio * self.duration

    def _on_configure(self, event):
        self.canvas_width = event.width
        self.canvas.configure(bg=Colors.BG_SECONDARY)
        self._redraw()
        
    def _redraw(self):
        self.canvas.delete("all")
        margin = 15
        
        # 1. Track de fondo (inactivo)
        x_left_limit = margin
        x_right_limit = self.canvas_width - margin
        
        self.canvas.create_rectangle(
            x_left_limit, self.y_center - self.track_height/2,
            x_right_limit, self.y_center + self.track_height/2,
            fill=Colors.BG_DARK,
            outline="",
            width=0
        )
        
        # 2. Track activo (línea amarilla)
        x_start = self._sec_to_x(self.start_sec)
        x_end = self._sec_to_x(self.end_sec)
        
        self.canvas.create_rectangle(
            x_start, self.y_center - self.track_height/2,
            x_end, self.y_center + self.track_height/2,
            fill=Colors.ACCENT_YELLOW,
            outline="",
            width=0
        )
        
        # 3. Tirador izquierdo (círculo blanco con borde amarillo)
        self.canvas.create_oval(
            x_start - self.handle_radius, self.y_center - self.handle_radius,
            x_start + self.handle_radius, self.y_center + self.handle_radius,
            fill="#FFFFFF",
            outline=Colors.ACCENT_YELLOW,
            width=2,
            tags="start_handle"
        )
        
        # 4. Tirador derecho
        self.canvas.create_oval(
            x_end - self.handle_radius, self.y_center - self.handle_radius,
            x_end + self.handle_radius, self.y_center + self.handle_radius,
            fill="#FFFFFF",
            outline=Colors.ACCENT_YELLOW,
            width=2,
            tags="end_handle"
        )
        
    def _on_press(self, event):
        x = event.x
        x_start = self._sec_to_x(self.start_sec)
        x_end = self._sec_to_x(self.end_sec)
        
        dist_start = abs(x - x_start)
        dist_end = abs(x - x_end)
        
        if dist_start < dist_end and dist_start < 20:
            self.active_handle = 'start'
        elif dist_end < 20:
            self.active_handle = 'end'
        else:
            self.active_handle = None
            
    def _on_drag(self, event):
        if not self.active_handle:
            return
            
        sec = self._x_to_sec(event.x)
        
        if self.active_handle == 'start':
            self.start_sec = min(sec, self.end_sec - 1)
            self.start_sec = max(0, self.start_sec)
        else:
            self.end_sec = max(sec, self.start_sec + 1)
            self.end_sec = min(self.duration, self.end_sec)
            
        self._redraw()
        
        if self.on_change:
            self.on_change(int(self.start_sec), int(self.end_sec))
            
    def _on_release(self, event):
        self.active_handle = None

    def _on_motion(self, event):
        x = event.x
        x_start = self._sec_to_x(self.start_sec)
        x_end = self._sec_to_x(self.end_sec)
        dist_start = abs(x - x_start)
        dist_end = abs(x - x_end)
        
        if dist_start < 12 or dist_end < 12:
            self.canvas.configure(cursor="size_we")
        else:
            self.canvas.configure(cursor="")


class TrimmingFrame(ctk.CTkFrame):
    """Panel de recorte de video (expandible) con slider de rango interactivo y presets."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._expanded = False
        self.video_duration = 0
        self._updating_from_slider = False

        # ── Botón toggle ──
        self.toggle_btn = ctk.CTkButton(
            self,
            text="✂️  Recortar Video (Opcional)  ▸",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color="transparent",
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_SECONDARY,
            anchor="w",
            height=32,
            command=self._toggle,
        )
        self.toggle_btn.pack(fill="x", padx=Spacing.LG, pady=(Spacing.SM, 0))

        # ── Panel expandible ──
        self.content = ctk.CTkFrame(
            self,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=Radius.MD,
            border_width=1,
            border_color=Colors.BORDER,
        )

        # Fila 0: Slider de Rango
        self.slider_info_label = ctk.CTkLabel(
            self.content,
            text="📍 Rango: 00:00:00 - 00:00:00  |  Seleccionado: 00:00:00  |  Total: 00:00:00",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            text_color=Colors.ACCENT_YELLOW,
            anchor="w"
        )
        self.slider_info_label.pack(fill="x", padx=Spacing.LG, pady=(Spacing.MD, 0))

        self.slider = TrimmingRangeSlider(
            self.content,
            duration=100,
            on_change=self._on_slider_change
        )
        self.slider.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.XS))

        # Fila 1: Entradas de tiempo (HH:MM:SS)
        self.inputs_row = ctk.CTkFrame(self.content, fg_color="transparent")
        self.inputs_row.pack(fill="x", padx=Spacing.LG, pady=Spacing.XS)

        label_font = (Fonts.FAMILY, Fonts.SIZE_SMALL, "bold")
        input_args = {
            "font": (Fonts.FAMILY, Fonts.SIZE_SMALL),
            "text_color": Colors.TEXT_PRIMARY,
            "fg_color": Colors.BG_DARK,
            "border_width": 1,
            "border_color": Colors.BORDER,
            "corner_radius": Radius.SM,
            "height": 34,
            "width": 100
        }

        # Tiempo Inicio
        start_frame = ctk.CTkFrame(self.inputs_row, fg_color="transparent")
        start_frame.pack(side="left", padx=(0, Spacing.LG))
        ctk.CTkLabel(start_frame, text="Inicio (HH:MM:SS):", font=label_font).pack(anchor="w")
        self.start_entry = ctk.CTkEntry(start_frame, placeholder_text="00:00:00", **input_args)
        self.start_entry.pack(pady=(Spacing.XS, 0))
        self.start_entry.bind("<KeyRelease>", lambda e: self.validate_times())

        # Tiempo Fin
        end_frame = ctk.CTkFrame(self.inputs_row, fg_color="transparent")
        end_frame.pack(side="left", padx=(0, Spacing.LG))
        ctk.CTkLabel(end_frame, text="Fin (HH:MM:SS):", font=label_font).pack(anchor="w")
        self.end_entry = ctk.CTkEntry(end_frame, placeholder_text="00:05:00", **input_args)
        self.end_entry.pack(pady=(Spacing.XS, 0))
        self.end_entry.bind("<KeyRelease>", lambda e: self.validate_times())

        # Fila 2: Presets (Botones rápidos)
        presets_row = ctk.CTkFrame(self.content, fg_color="transparent")
        presets_row.pack(fill="x", padx=Spacing.LG, pady=Spacing.XS)

        preset_btn_args = {
            "font": (Fonts.FAMILY, Fonts.SIZE_TINY),
            "fg_color": Colors.BG_TERTIARY,
            "hover_color": Colors.BG_HOVER,
            "text_color": Colors.TEXT_SECONDARY,
            "corner_radius": Radius.SM,
            "height": 24,
        }

        self.btn_intro = ctk.CTkButton(presets_row, text="Omitir Intro (-30s)", command=self._preset_intro, **preset_btn_args)
        self.btn_intro.pack(side="left", padx=(0, Spacing.XS))

        self.btn_outro = ctk.CTkButton(presets_row, text="Omitir Outro (-15s)", command=self._preset_outro, **preset_btn_args)
        self.btn_outro.pack(side="left", padx=(0, Spacing.XS))

        self.btn_minute = ctk.CTkButton(presets_row, text="Primer Minuto", command=self._preset_minute, **preset_btn_args)
        self.btn_minute.pack(side="left", padx=(0, Spacing.XS))

        self.btn_reset = ctk.CTkButton(
            presets_row,
            text="Restablecer",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY),
            fg_color=Colors.BG_DARK,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_SECONDARY,
            corner_radius=Radius.SM,
            height=24,
            command=self._preset_reset
        )
        self.btn_reset.pack(side="left", padx=(0, Spacing.XS))

        # Fila 3: Mensaje de Advertencia
        self.warning_label = ctk.CTkLabel(
            self.content,
            text="💡 Deja vacío para descargar completo",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY),
            text_color=Colors.TEXT_MUTED,
            anchor="w"
        )
        self.warning_label.pack(fill="x", padx=Spacing.LG, pady=(Spacing.XS, Spacing.MD))

    def _toggle(self):
        self._expanded = not self._expanded
        if self._expanded:
            self.content.pack(fill="x", padx=Spacing.LG, pady=(Spacing.XS, 0))
            self.toggle_btn.configure(text="✂️  Recortar Video (Opcional)  ▾")
        else:
            self.content.pack_forget()
            self.toggle_btn.configure(text="✂️  Recortar Video (Opcional)  ▸")

    def _preset_intro(self):
        self.start_entry.delete(0, "end")
        self.start_entry.insert(0, "00:00:30")
        self.validate_times()

    def _preset_outro(self):
        if self.video_duration > 15:
            end_sec = self.video_duration - 15
            h = end_sec // 3600
            m = (end_sec % 3600) // 60
            s = end_sec % 60
            formatted = f"{h:02d}:{m:02d}:{s:02d}"
            
            self.end_entry.delete(0, "end")
            self.end_entry.insert(0, formatted)
        self.validate_times()

    def _preset_minute(self):
        self.start_entry.delete(0, "end")
        self.start_entry.insert(0, "00:00:00")
        self.end_entry.delete(0, "end")
        self.end_entry.insert(0, "00:01:00")
        self.validate_times()

    def _preset_reset(self):
        self.start_entry.delete(0, "end")
        self.end_entry.delete(0, "end")
        self.validate_times()

    def set_duration(self, duration_sec: int):
        self.video_duration = duration_sec if duration_sec > 0 else 0
        self.slider.set_duration(self.video_duration if self.video_duration > 0 else 1)
        
        self.start_entry.delete(0, "end")
        self.end_entry.delete(0, "end")
        
        if self.video_duration <= 0:
            self.slider_info_label.configure(text="⚠️ Rango: No disponible  |  Total: No disponible")
            self.warning_label.configure(text="💡 Introduce una URL válida para activar el recorte", text_color=Colors.TEXT_MUTED)
        else:
            self._update_slider_label(0, self.video_duration)
            self.warning_label.configure(text="💡 Deja vacío para descargar completo", text_color=Colors.TEXT_MUTED)
        self.validate_times()

    def _on_slider_change(self, start_sec: int, end_sec: int):
        if self.video_duration <= 0:
            return
            
        self._updating_from_slider = True
        
        def format_time(sec):
            h = sec // 3600
            m = (sec % 3600) // 60
            s = sec % 60
            return f"{h:02d}:{m:02d}:{s:02d}"
            
        self.start_entry.delete(0, "end")
        self.start_entry.insert(0, format_time(start_sec))
        
        self.end_entry.delete(0, "end")
        self.end_entry.insert(0, format_time(end_sec))
        
        self._update_slider_label(start_sec, end_sec)
        self.validate_times()
        
        self._updating_from_slider = False

    def _update_slider_label(self, start_sec: int, end_sec: int):
        from core.utils import format_eta
        if self.video_duration <= 0:
            self.slider_info_label.configure(text="⚠️ Rango: No disponible  |  Total: No disponible")
            return
        range_sec = end_sec - start_sec
        info_text = f"📍 Rango: {format_eta(start_sec)} - {format_eta(end_sec)}  |  Seleccionado: {format_eta(range_sec)}  |  Total: {format_eta(self.video_duration)}"
        self.slider_info_label.configure(text=info_text)

    def validate_times(self) -> bool:
        """Valida que los tiempos sean lógicos y estén en límites."""
        from core.utils import parse_time_str
        
        start_val = self.start_entry.get().strip()
        end_val = self.end_entry.get().strip()
        
        if self.video_duration <= 0:
            if start_val or end_val:
                self.warning_label.configure(text="⚠️ No se puede recortar: Duración del video desconocida", text_color=Colors.ERROR)
                return False
            self.warning_label.configure(text="💡 Introduce una URL válida para activar el recorte", text_color=Colors.TEXT_MUTED)
            return True
            
        if not start_val and not end_val:
            self.warning_label.configure(text="💡 Deja vacío para descargar completo", text_color=Colors.TEXT_MUTED)
            if not self._updating_from_slider:
                self.slider.set_values(0, self.video_duration)
                self._update_slider_label(0, self.video_duration)
            return True
            
        start_sec = parse_time_str(start_val) if start_val else 0
        end_sec = parse_time_str(end_val) if end_val else self.video_duration
        if end_sec is None:
            end_sec = self.video_duration

        if (start_val and start_sec is None) or (end_val and end_sec is None):
            self.warning_label.configure(text="⚠️ Formato incorrecto. Usa HH:MM:SS o MM:SS", text_color=Colors.ERROR)
            return False
            
        if start_sec < 0 or end_sec < 0:
            self.warning_label.configure(text="⚠️ Los tiempos no pueden ser negativos", text_color=Colors.ERROR)
            return False

        if start_sec >= end_sec:
            self.warning_label.configure(text="⚠️ El tiempo de inicio debe ser menor al de fin", text_color=Colors.ERROR)
            return False

        if self.video_duration > 0:
            if start_sec > self.video_duration:
                self.warning_label.configure(text=f"⚠️ El inicio excede la duración del video ({start_val} > {self.video_duration}s)", text_color=Colors.ERROR)
                return False
            if end_sec > self.video_duration:
                self.warning_label.configure(text=f"⚠️ El fin excede la duración del video ({end_val} > {self.video_duration}s)", text_color=Colors.ERROR)
                return False

        self.warning_label.configure(text="✅ Tiempos de recorte válidos", text_color=Colors.SUCCESS)
        
        if not self._updating_from_slider:
            self.slider.set_values(start_sec, end_sec)
            self._update_slider_label(start_sec, end_sec)
            
        return True

    def get_times(self) -> tuple[str, str]:
        return self.start_entry.get().strip(), self.end_entry.get().strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  HISTORY WINDOW
# ═══════════════════════════════════════════════════════════════════════════════

class HistoryWindow(ctk.CTkToplevel):
    """Ventana de historial de descargas."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.title("Historial de Descargas — MXP")
        self.geometry("600x480")
        self.configure(fg_color=Colors.BG_DARK)
        self.attributes("-topmost", True)

        # Centrar la ventana de historial
        self.update_idletasks()
        w, h = 600, 480
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw // 2) - (w // 2)
        y = (sh // 2) - (h // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

        # Header Container
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)

        # Título
        ctk.CTkLabel(
            header_frame, 
            text="📜 Historial de Descargas", 
            font=(Fonts.FAMILY, Fonts.SIZE_TITLE, "bold"),
            text_color=Colors.ACCENT_YELLOW
        ).pack(side="left")

        # Botón de limpiar historial
        self.clear_btn = ctk.CTkButton(
            header_frame,
            text="🧹 Limpiar Historial",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            fg_color=Colors.ERROR,
            hover_color="#c0392b",
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            width=130,
            height=28,
            command=self._clear_history
        )
        self.clear_btn.pack(side="right")

        # Scrollable area
        self.scroll = ctk.CTkScrollableFrame(
            self, 
            fg_color=Colors.BG_SECONDARY, 
            corner_radius=Radius.MD,
            border_width=1,
            border_color=Colors.BORDER
        )
        self.scroll.pack(fill="both", expand=True, padx=Spacing.LG, pady=(0, Spacing.LG))

        self._load_history()

    def _clear_history(self):
        """Limpia el historial del disco y vacía el contenedor visual."""
        from core.history import HistoryManager
        HistoryManager().clear()
        # Eliminar todos los widgets hijos en la interfaz de scroll
        for widget in self.scroll.winfo_children():
            widget.destroy()
        self._load_history()

    def _load_history(self):
        from core.history import HistoryManager
        history = HistoryManager().get_all()

        if not history:
            ctk.CTkLabel(self.scroll, text="No hay descargas registradas.", font=(Fonts.FAMILY, Fonts.SIZE_BODY), text_color=Colors.TEXT_MUTED).pack(pady=Spacing.XL)
            return

        for entry in history:
            item = ctk.CTkFrame(self.scroll, fg_color=Colors.BG_TERTIARY, corner_radius=Radius.SM)
            item.pack(fill="x", pady=Spacing.XS, padx=Spacing.XS)

            # Contenido del item
            content = ctk.CTkFrame(item, fg_color="transparent")
            content.pack(fill="x", padx=Spacing.MD, pady=Spacing.MD)

            title = entry.get("title", "Sin título")
            ctk.CTkLabel(content, text=title[:60] + "..." if len(title) > 60 else title, font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"), text_color=Colors.TEXT_PRIMARY, anchor="w").pack(fill="x")
            
            meta = f"{entry.get('date')}  │  {entry.get('format')}  │  {entry.get('url')[:30]}..."
            ctk.CTkLabel(content, text=meta, font=(Fonts.FAMILY_MONO, Fonts.SIZE_TINY), text_color=Colors.TEXT_SECONDARY, anchor="w").pack(fill="x")


# ═══════════════════════════════════════════════════════════════════════════════
#  SETUP PROGRESS (BARRA SUPERIOR)
# ═══════════════════════════════════════════════════════════════════════════════

class SetupProgressOverlay(ctk.CTkFrame):
    """Barra superior para mostrar progreso de configuración de binarios."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color=Colors.BG_SECONDARY, height=4, **kwargs)
        
        self.progress_bar = ctk.CTkProgressBar(
            self,
            fg_color=Colors.PROGRESS_BG,
            progress_color=Colors.ACCENT_YELLOW,
            corner_radius=0,
            height=4
        )
        self.progress_bar.pack(fill="x")
        self.progress_bar.set(0)

        self.label = ctk.CTkLabel(
            self,
            text="Configurando componentes...",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold"),
            text_color=Colors.ACCENT_YELLOW,
            height=20
        )
        self.label.pack(fill="x")

    def update_progress(self, msg: str, percent: float):
        if percent < 0:
            self.label.configure(text=msg, text_color=Colors.ERROR)
            self.progress_bar.configure(progress_color=Colors.ERROR)
            self.progress_bar.set(1.0)
            return

        self.label.configure(text=msg)
        self.progress_bar.set(percent / 100.0)
        
        if percent >= 100:
            self.after(2000, self.pack_forget)


# ═══════════════════════════════════════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════════════════════════════════════

class FooterFrame(ctk.CTkFrame):
    """Footer con información de la app."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        ctk.CTkLabel(
            self,
            text="Powered by yt-dlp  ·  Local & Free  ·  v1.0",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY),
            text_color=Colors.TEXT_MUTED,
        ).pack(pady=Spacing.SM)


# ═══════════════════════════════════════════════════════════════════════════════
#  THUMBNAIL PREVIEW
# ═══════════════════════════════════════════════════════════════════════════════

class ThumbnailPreviewFrame(ctk.CTkFrame):
    """Muestra una previsualización de miniatura, título y duración del video."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.panel = ctk.CTkFrame(
            self,
            fg_color=Colors.BG_SECONDARY,
            corner_radius=Radius.LG,
            border_width=1,
            border_color=Colors.BORDER,
        )
        self._visible = False
        
        # Elementos de la interfaz (Grid layout)
        self.panel.grid_columnconfigure(0, weight=0) # Miniatura
        self.panel.grid_columnconfigure(1, weight=1) # Info (Título, Duración)

        # ── 1. Contenedor de la Imagen principal ──
        self.image_label = ctk.CTkLabel(
            self.panel,
            text="Cargando miniatura... 🔄",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            text_color=Colors.TEXT_SECONDARY,
            width=180,
            height=101,
            fg_color=Colors.BG_DARK,
            corner_radius=Radius.SM
        )
        self.image_label.grid(row=0, column=0, padx=Spacing.LG, pady=Spacing.LG, sticky="nsew")

        # ── 2. Contenedor de Textos ──
        self.text_container = ctk.CTkFrame(self.panel, fg_color="transparent")
        self.text_container.grid(row=0, column=1, padx=(0, Spacing.LG), pady=Spacing.LG, sticky="nsew")

        self.title_label = ctk.CTkLabel(
            self.text_container,
            text="Obteniendo información...",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"),
            text_color=Colors.TEXT_PRIMARY,
            anchor="w",
            justify="left",
            wraplength=450
        )
        self.title_label.pack(fill="x", anchor="w", pady=(Spacing.XS, Spacing.XS))

        self.duration_label = ctk.CTkLabel(
            self.text_container,
            text="",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            text_color=Colors.ACCENT_YELLOW,
            anchor="w"
        )
        self.duration_label.pack(fill="x", anchor="w")

        self.platform_label = ctk.CTkLabel(
            self.text_container,
            text="",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold"),
            text_color=Colors.TEXT_MUTED,
            anchor="w"
        )
        self.platform_label.pack(fill="x", anchor="w")

    def show(self):
        """Muestra el panel."""
        if not self._visible:
            self.panel.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.SM))
            self._visible = True

    def hide(self):
        """Oculta el panel."""
        if self._visible:
            self.panel.pack_forget()
            self._visible = False

    def show_loading(self):
        """Configura el panel en estado de carga."""
        self.title_label.configure(text="Obteniendo información del video...", text_color=Colors.TEXT_SECONDARY)
        self.image_label.configure(text="Cargando miniatura... 🔄", image=None)
        self.duration_label.configure(text="")
        self.platform_label.configure(text="")
        self.show()

    def show_error(self, message: str):
        """Muestra un mensaje de error en el panel."""
        self.title_label.configure(text=message, text_color=Colors.ERROR)
        self.image_label.configure(text="⚠️ Error", image=None)
        self.duration_label.configure(text="")
        self.platform_label.configure(text="")
        self.show()

    def update_metadata(self, title: str, duration_sec: int, thumbnail_url: str, platform: str):
        """Actualiza la miniatura y textos usando un hilo secundario para descargar la imagen."""
        from core.utils import format_eta
        
        dur_str = f"⏱ Duración: {format_eta(duration_sec)}" if duration_sec else "⏱ Duración: Desconocida (Live stream?)"
        
        self.title_label.configure(text=title, text_color=Colors.TEXT_PRIMARY)
        self.duration_label.configure(text=dur_str)
        self.platform_label.configure(text=f"📍 Plataforma detectada: {platform}")

        # Descarga de miniatura principal
        if thumbnail_url:
            thumbnail_url = str(thumbnail_url).strip()
            if thumbnail_url.startswith("//"):
                thumbnail_url = "https:" + thumbnail_url
            import threading
            threading.Thread(target=self._load_image_from_url, args=(thumbnail_url,), daemon=True).start()
        else:
            self.image_label.configure(text="🎬 Sin miniatura", image=None)

    def _load_image_from_url(self, url: str):
        """Descarga la imagen en segundo plano y la aplica a la GUI de forma segura."""
        import requests
        from io import BytesIO
        from PIL import Image
        
        try:
            # Deshabilitar advertencias de SSL
            try:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass
                
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=5, verify=False)
            if response.status_code == 200:
                img_data = BytesIO(response.content)
                pil_image = Image.open(img_data)
                
                # Redimensionar a 180x101
                pil_image = pil_image.resize((180, 101), Image.Resampling.LANCZOS)
                
                # Crear imagen CTk y guardar referencia en la instancia para evitar GC
                self.thumbnail_image = ctk.CTkImage(light_image=pil_image, dark_image=pil_image, size=(180, 101))
                
                self.after(0, lambda: self.image_label.configure(text="", image=self.thumbnail_image))
            else:
                self.after(0, lambda: self.image_label.configure(text="🎬 Miniatura no disponible", image=None))
        except Exception as e:
            print(f"[DEBUG] Error al descargar miniatura de URL {url}: {e}")
            self.after(0, lambda: self.image_label.configure(text="🎬 Error al cargar miniatura", image=None))


# ═══════════════════════════════════════════════════════════════════════════════
#  CONVERTER PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class ConverterPanelFrame(ctk.CTkFrame):
    """Panel principal del Conversor unificado con diseño OLED negro."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        
        # Inicializar motores
        from core.engines.images import ImageEngine
        from core.engines.video_audio import MediaEngine
        from core.utils import get_default_download_dir
        
        self.image_engine = ImageEngine()
        self.media_engine = MediaEngine()
        
        self.selected_files = []
        self.output_dir = get_default_download_dir()
        self._is_converting = False
        
        # ── 1. Header ──
        self.header = ctk.CTkFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        self.header.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)
        
        header_content = ctk.CTkFrame(self.header, fg_color="transparent")
        header_content.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(
            header_content,
            text="MXP Converter",
            font=(Fonts.FAMILY, Fonts.SIZE_TITLE, "bold"),
            text_color=Colors.ACCENT_YELLOW,
            anchor="w"
        ).pack(fill="x")
        
        ctk.CTkLabel(
            header_content,
            text="Conversor local de video, audio e imágenes",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            text_color=Colors.TEXT_SECONDARY,
            anchor="w"
        ).pack(fill="x", pady=(Spacing.XS, 0))

        # ── 2. Contenedor de Opciones ──
        options_frame = ctk.CTkFrame(self, fg_color="transparent")
        options_frame.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
        options_frame.grid_columnconfigure(0, weight=1)
        options_frame.grid_columnconfigure(1, weight=1)
        
        # ── Columna Izquierda: Selección de Archivos ──
        left_col = ctk.CTkFrame(options_frame, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        left_col.grid(row=0, column=0, padx=(0, Spacing.MD), sticky="nsew")
        
        left_content = ctk.CTkFrame(left_col, fg_color="transparent")
        left_content.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(left_content, text="📁 Selección de Archivos", font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"), text_color=Colors.TEXT_PRIMARY, anchor="w").pack(fill="x")
        
        self.btn_select = ctk.CTkButton(
            left_content,
            text="Buscar Archivos",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            fg_color=Colors.BG_TERTIARY,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            height=34,
            command=self._select_files
        )
        self.btn_select.pack(fill="x", pady=Spacing.MD)
        
        self.files_list = ctk.CTkScrollableFrame(
            left_content,
            height=120,
            fg_color=Colors.BG_DARK,
            border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Radius.SM
        )
        self.files_list.pack(fill="both", expand=True)

        # Configurar Drag & Drop nativo
        try:
            from tkinterdnd2 import DND_FILES
            self.files_list.drop_target_register(DND_FILES)
            self.files_list.dnd_bind('<<Drop>>', self._on_file_drop)
            if hasattr(self.files_list, "_parent_canvas"):
                self.files_list._parent_canvas.drop_target_register(DND_FILES)
                self.files_list._parent_canvas.dnd_bind('<<Drop>>', self._on_file_drop)
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_file_drop)
        except Exception:
            pass

        # ── Columna Derecha: Configuración de Conversión ──
        right_col = ctk.CTkFrame(options_frame, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        right_col.grid(row=0, column=1, padx=(Spacing.MD, 0), sticky="nsew")
        
        right_content = ctk.CTkFrame(right_col, fg_color="transparent")
        right_content.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(right_content, text="⚙️ Configuración", font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"), text_color=Colors.TEXT_PRIMARY, anchor="w").pack(fill="x")
        
        # Categoría
        ctk.CTkLabel(right_content, text="Categoría:", font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold"), text_color=Colors.TEXT_MUTED, anchor="w").pack(fill="x", pady=(Spacing.MD, 0))
        self.category_var = tk.StringVar(value="Video")
        self.category_menu = ctk.CTkOptionMenu(
            right_content,
            variable=self.category_var,
            values=["Video", "Audio", "Imagen"],
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color=Colors.BG_TERTIARY,
            button_color=Colors.BG_TERTIARY,
            button_hover_color=Colors.BG_HOVER,
            dropdown_fg_color=Colors.BG_SECONDARY,
            dropdown_hover_color=Colors.BG_HOVER,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            height=32,
            command=self._on_category_change
        )
        self.category_menu.pack(fill="x", pady=(Spacing.XS, 0))
        
        # Formato / Acción Destino
        self.format_label = ctk.CTkLabel(right_content, text="Formato Destino:", font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold"), text_color=Colors.TEXT_MUTED, anchor="w")
        self.format_label.pack(fill="x", pady=(Spacing.MD, 0))
        
        self.format_var = tk.StringVar()
        self.format_menu = ctk.CTkOptionMenu(
            right_content,
            variable=self.format_var,
            values=[],
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color=Colors.BG_TERTIARY,
            button_color=Colors.BG_TERTIARY,
            button_hover_color=Colors.BG_HOVER,
            dropdown_fg_color=Colors.BG_SECONDARY,
            dropdown_hover_color=Colors.BG_HOVER,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            height=32
        )
        self.format_menu.pack(fill="x", pady=(Spacing.XS, 0))

        self._update_format_menu("Video")

        # Ayuda contextual
        self.hint_label = ctk.CTkLabel(
            right_content,
            text="💡 Puedes seleccionar videos (MP4/MKV) en la categoría 'Audio' para extraer su sonido a MP3/WAV.",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY),
            text_color=Colors.TEXT_MUTED,
            wraplength=220,
            justify="left"
        )
        self.hint_label.pack(fill="x", pady=(Spacing.MD, 0))

        # ── 3. Carpeta de Destino ──
        dest_card = ctk.CTkFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        dest_card.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
        
        dest_content = ctk.CTkFrame(dest_card, fg_color="transparent")
        dest_content.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(dest_content, text="📁 Guardar en:", font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"), text_color=Colors.TEXT_PRIMARY).pack(side="left")
        
        self.dest_entry = ctk.CTkEntry(
            dest_content,
            placeholder_text=self.output_dir,
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color=Colors.BG_DARK,
            border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Radius.SM,
            height=34
        )
        self.dest_entry.pack(side="left", fill="x", expand=True, padx=Spacing.MD)
        self.dest_entry.insert(0, self.output_dir)
        self.dest_entry.configure(state="readonly")
        
        self.btn_dest = ctk.CTkButton(
            dest_content,
            text="Cambiar",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            fg_color=Colors.BG_TERTIARY,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            width=80,
            height=34,
            command=self._select_dest
        )
        self.btn_dest.pack(side="right")

        # ── 4. Botón Ejecutar y Barra de Progreso ──
        self.btn_convert = ctk.CTkButton(
            self,
            text="Iniciar Conversión 🔄",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"),
            fg_color=Colors.ACCENT_PRIMARY,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.BUTTON_TEXT,
            corner_radius=Radius.LG,
            height=52,
            command=self._start_conversion
        )
        self.btn_convert.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
        
        self.progress_bar = ctk.CTkProgressBar(
            self,
            fg_color=Colors.PROGRESS_BG,
            progress_color=Colors.ACCENT_YELLOW,
            corner_radius=Radius.SM,
            height=8
        )
        self.progress_bar.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
        self.progress_bar.set(0)

        # ── 5. Consola de Registro ──
        log_card = ctk.CTkFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        log_card.pack(fill="both", expand=True, padx=Spacing.LG, pady=(0, Spacing.LG))
        
        log_content = ctk.CTkFrame(log_card, fg_color="transparent")
        log_content.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(log_content, text="📋 Registro de Actividad", font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"), text_color=Colors.TEXT_PRIMARY, anchor="w").pack(fill="x")
        
        self.log_console = ctk.CTkTextbox(
            log_content,
            fg_color=Colors.BG_DARK,
            text_color=Colors.TEXT_SECONDARY,
            font=(Fonts.FAMILY_MONO, Fonts.SIZE_SMALL),
            border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Radius.SM,
            height=160
        )
        self.log_console.pack(fill="both", expand=True, pady=(Spacing.SM, 0))
        self.log_console.insert("1.0", "Listo para convertir archivos.\n")
        self.log_console.configure(state="disabled")
        
        self._update_files_list_ui()

    def _update_files_list_ui(self):
        """Limpia y dibuja la lista de archivos con botones de eliminar."""
        for w in self.files_list.winfo_children():
            w.destroy()
            
        if not self.selected_files:
            lbl = ctk.CTkLabel(
                self.files_list,
                text="⬇  Arrastra archivos aquí, o usa 'Buscar Archivos'",
                font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
                text_color=Colors.TEXT_MUTED,
                anchor="w"
            )
            lbl.pack(fill="x", padx=5, pady=5)
            return

        for fpath in self.selected_files:
            row = ctk.CTkFrame(self.files_list, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            try:
                size_mb = os.path.getsize(fpath) / (1024 * 1024)
                text = f"• {os.path.basename(fpath)} ({size_mb:.1f} MB)"
            except Exception:
                text = f"• {os.path.basename(fpath)}"
                
            lbl = ctk.CTkLabel(
                row,
                text=text,
                font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
                text_color=Colors.TEXT_SECONDARY,
                anchor="w"
            )
            lbl.pack(side="left", fill="x", expand=True, padx=(5, 0))
            
            btn_remove = ctk.CTkButton(
                row,
                text="✕",
                width=20,
                height=20,
                fg_color="transparent",
                hover_color=Colors.ERROR,
                text_color=Colors.TEXT_SECONDARY,
                font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
                command=lambda p=fpath: self._remove_file(p)
            )
            btn_remove.pack(side="right", padx=5)

    def _remove_file(self, path):
        if path in self.selected_files:
            self.selected_files.remove(path)
            self._update_files_list_ui()
            self._log(f"Quitado de la cola: {os.path.basename(path)}\n")

    def _on_file_drop(self, event):
        """Manejador nativo de Drag & Drop para arrastrar archivos a la app."""
        import re
        data = event.data
        paths = re.findall(r'{([^}]+)}|([^\s{}]+)', data)
        parsed_paths = [p[0] or p[1] for p in paths]
        
        valid_paths = [p for p in parsed_paths if os.path.exists(p)]
        if valid_paths:
            for p in valid_paths:
                if p not in self.selected_files:
                    self.selected_files.append(p)
                    
            ext = os.path.splitext(self.selected_files[0])[1].lower()
            detected = "Video"
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
                detected = "Imagen"
            elif ext in ['.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac']:
                detected = "Audio"
                
            self.category_var.set(detected)
            self._update_format_menu(detected)
            self._update_files_list_ui()
            self._log(f"📥 Archivos cargados por arrastre: {len(valid_paths)} nuevos archivos agregados.\n")

    def _select_files(self):
        """Abre buscador de archivos locales aplicando filtro selectivo según la categoría."""
        category = self.category_var.get()
        if category == "Video":
            filetypes = [
                ("Archivos de Video", "*.mp4;*.mkv;*.avi;*.mov;*.webm"),
                ("Todos los archivos", "*.*")
            ]
        elif category == "Audio":
            filetypes = [
                ("Archivos de Audio y Video (Extracción)", "*.mp3;*.wav;*.flac;*.m4a;*.ogg;*.aac;*.mp4;*.mkv;*.avi;*.mov"),
                ("Todos los archivos", "*.*")
            ]
        elif category == "Imagen":
            filetypes = [
                ("Archivos de Imagen", "*.jpg;*.jpeg;*.png;*.webp;*.bmp"),
                ("Todos los archivos", "*.*")
            ]
        else:
            filetypes = [("Todos los archivos", "*.*")]

        paths = filedialog.askopenfilenames(title="Seleccionar Archivos para Convertir", filetypes=filetypes)
        if paths:
            for p in paths:
                if p not in self.selected_files:
                    self.selected_files.append(p)
            self._update_files_list_ui()
            self._log(f"Archivos cargados: {len(paths)} nuevos archivos agregados para {category}.\n")

    def _select_dest(self):
        """Selecciona carpeta de destino."""
        path = filedialog.askdirectory(title="Seleccionar Carpeta de Destino")
        if path:
            self.output_dir = path
            self.dest_entry.configure(state="normal")
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, self.output_dir)
            self.dest_entry.configure(state="readonly")
            self._log(f"Carpeta de salida cambiada a: {self.output_dir}\n")

    def _on_category_change(self, val):
        self._update_format_menu(val)

    def _update_format_menu(self, category):
        self.format_menu.configure(state="normal")
        if category == "Video":
            self.format_label.configure(text="Formato Destino:")
            formats = ["MP4", "MKV", "MOV", "AVI", "WEBM"]
        elif category == "Audio":
            self.format_label.configure(text="Formato Destino:")
            formats = ["MP3", "WAV", "FLAC", "M4A"]
        elif category == "Imagen":
            self.format_label.configure(text="Formato Destino:")
            formats = ["JPG", "PNG", "WEBP", "BMP"]
        self.format_menu.configure(values=formats)
        self.format_var.set(formats[0])

    def _log(self, text):
        """Escribe en la consola de registro."""
        self.log_console.configure(state="normal")
        self.log_console.insert("end", text)
        self.log_console.see("end")
        self.log_console.configure(state="disabled")

    def _start_conversion(self):
        """Inicia el proceso de conversión en un hilo secundario."""
        if self._is_converting:
            return
        if not self.selected_files:
            from core.utils import show_windows_notification
            show_windows_notification("MXP Converter ⚠️", "Selecciona al menos un archivo para iniciar la conversión.")
            return
            
        self._is_converting = True
        self.btn_convert.configure(state="disabled", text="Procesando... 🔄")
        self.btn_select.configure(state="disabled")
        self.progress_bar.set(0)
        
        import threading
        threading.Thread(target=self._run_conversion, daemon=True).start()

    def _run_conversion(self):
        category = self.category_var.get()
        target = self.format_var.get()
        
        total = len(self.selected_files)
        self._log(f"\n--- Iniciando Proceso: {category} -> {target} ---\n")
        
        success_count = 0
        base_text = "Iniciando..."
        
        for i, file_path in enumerate(self.selected_files):
            if not os.path.exists(file_path):
                self._log(f"[✗ Error] Archivo no existe: {file_path}\n")
                continue
                
            res = None
            file_base_progress = i / total
            file_range = 1.0 / total

            def make_progress_cb(base, rng):
                def cb(pct):
                    overall = base + pct * rng
                    pct_int = int(overall * 100)
                    self.after(0, lambda p=overall, t=pct_int: (
                        self.progress_bar.set(p),
                        self.btn_convert.configure(text=f"Procesando {t}%... 🔄")
                    ))
                return cb

            prog_cb = make_progress_cb(file_base_progress, file_range)
            
            # ── 1. Proceso de VIDEO / AUDIO ──
            if category == "Video":
                res = self.media_engine.process_video(file_path, target, self.output_dir, "Ninguno", self._log_callback, progress_callback=prog_cb)
            elif category == "Audio":
                res = self.media_engine.process_audio(file_path, target, self.output_dir, self._log_callback, progress_callback=prog_cb)
                
            # ── 2. Proceso de IMÁGENES ──
            elif category == "Imagen":
                res = self.image_engine.process_image(file_path, target, self.output_dir, "Ninguno", self._log_callback)
                # Imágenes son instantáneas, simular progreso completo
                self.after(0, lambda p=(i+1)/total: self.progress_bar.set(p))
                    
            if res:
                success_count += 1
            
            # Marcar archivo completo
            self.after(0, lambda p=(i+1)/total: self.progress_bar.set(p))
            
        self._log(f"\n--- Proceso Finalizado: {success_count} de {total} completados. ---\n")
        
        from core.utils import show_windows_notification
        if success_count == total:
            show_windows_notification("MXP Converter ✅", f"Conversión completa. Todos los archivos ({success_count}) procesados con éxito.")
        else:
            show_windows_notification("MXP Converter ⚠️", f"Conversión finalizada. {success_count} exitosos, {total - success_count} fallidos.")
            
        self.after(0, self._reset_ui_after_convert)

    def _log_callback(self, msg):
        self.after(0, lambda: self._log(f"{msg}\n"))

    def _reset_ui_after_convert(self):
        self._is_converting = False
        self.progress_bar.set(1.0)
        self.btn_convert.configure(state="normal", text="Iniciar Conversión 🔄")
        self.btn_select.configure(state="normal")


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPRESSOR PANEL
# ═══════════════════════════════════════════════════════════════════════════════

class CompressorPanelFrame(ctk.CTkFrame):
    """Panel principal del Compresor dedicado con diseño OLED negro."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        
        from core.engines.images import ImageEngine
        from core.engines.video_audio import MediaEngine
        from core.utils import get_default_download_dir
        
        self.image_engine = ImageEngine()
        self.media_engine = MediaEngine()
        
        self.selected_files = []
        self.output_dir = get_default_download_dir()
        self._is_compressing = False
        
        # ── 1. Header ──
        self.header = ctk.CTkFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        self.header.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)
        
        header_content = ctk.CTkFrame(self.header, fg_color="transparent")
        header_content.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(
            header_content,
            text="MXP Compressor",
            font=(Fonts.FAMILY, Fonts.SIZE_TITLE, "bold"),
            text_color=Colors.ACCENT_YELLOW,
            anchor="w"
        ).pack(fill="x")
        
        ctk.CTkLabel(
            header_content,
            text="Optimiza y reduce el peso de tus archivos multimedia de forma local",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            text_color=Colors.TEXT_SECONDARY,
            anchor="w"
        ).pack(fill="x", pady=(Spacing.XS, 0))

        # ── 2. Contenedor de Opciones ──
        options_frame = ctk.CTkFrame(self, fg_color="transparent")
        options_frame.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
        options_frame.grid_columnconfigure(0, weight=1)
        options_frame.grid_columnconfigure(1, weight=1)
        
        # ── Columna Izquierda: Selección de Archivos ──
        left_col = ctk.CTkFrame(options_frame, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        left_col.grid(row=0, column=0, padx=(0, Spacing.MD), sticky="nsew")
        
        left_content = ctk.CTkFrame(left_col, fg_color="transparent")
        left_content.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(left_content, text="📁 Selección de Archivos", font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"), text_color=Colors.TEXT_PRIMARY, anchor="w").pack(fill="x")
        
        self.btn_select = ctk.CTkButton(
            left_content,
            text="Buscar Archivos",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            fg_color=Colors.BG_TERTIARY,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            height=34,
            command=self._select_files
        )
        self.btn_select.pack(fill="x", pady=Spacing.MD)
        
        self.files_list = ctk.CTkScrollableFrame(
            left_content,
            height=120,
            fg_color=Colors.BG_DARK,
            border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Radius.SM
        )
        self.files_list.pack(fill="both", expand=True)

        # Drag & Drop nativo
        try:
            from tkinterdnd2 import DND_FILES
            self.files_list.drop_target_register(DND_FILES)
            self.files_list.dnd_bind('<<Drop>>', self._on_file_drop)
            if hasattr(self.files_list, "_parent_canvas"):
                self.files_list._parent_canvas.drop_target_register(DND_FILES)
                self.files_list._parent_canvas.dnd_bind('<<Drop>>', self._on_file_drop)
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_file_drop)
        except Exception:
            pass

        # ── Columna Derecha: Configuración de Compresión ──
        right_col = ctk.CTkFrame(options_frame, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        right_col.grid(row=0, column=1, padx=(Spacing.MD, 0), sticky="nsew")
        
        right_content = ctk.CTkFrame(right_col, fg_color="transparent")
        right_content.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(right_content, text="⚙️ Configuración", font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"), text_color=Colors.TEXT_PRIMARY, anchor="w").pack(fill="x")
        
        # Categoría
        ctk.CTkLabel(right_content, text="Categoría:", font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold"), text_color=Colors.TEXT_MUTED, anchor="w").pack(fill="x", pady=(Spacing.MD, 0))
        self.category_var = tk.StringVar(value="Video")
        self.category_menu = ctk.CTkOptionMenu(
            right_content,
            variable=self.category_var,
            values=["Video", "Audio", "Imagen"],
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color=Colors.BG_TERTIARY,
            button_color=Colors.BG_TERTIARY,
            button_hover_color=Colors.BG_HOVER,
            dropdown_fg_color=Colors.BG_SECONDARY,
            dropdown_hover_color=Colors.BG_HOVER,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            height=32,
            command=self._on_category_change
        )
        self.category_menu.pack(fill="x", pady=(Spacing.XS, 0))
        
        # Nivel de Compresión
        self.level_label = ctk.CTkLabel(right_content, text="Nivel de Compresión:", font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold"), text_color=Colors.TEXT_MUTED, anchor="w")
        self.level_label.pack(fill="x", pady=(Spacing.MD, 0))
        
        self.level_var = tk.StringVar()
        self.level_menu = ctk.CTkOptionMenu(
            right_content,
            variable=self.level_var,
            values=[],
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color=Colors.BG_TERTIARY,
            button_color=Colors.BG_TERTIARY,
            button_hover_color=Colors.BG_HOVER,
            dropdown_fg_color=Colors.BG_SECONDARY,
            dropdown_hover_color=Colors.BG_HOVER,
            dropdown_text_color=Colors.TEXT_PRIMARY,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            height=32
        )
        self.level_menu.pack(fill="x", pady=(Spacing.XS, 0))
        
        # Ayuda contextual
        self.hint_label = ctk.CTkLabel(
            right_content,
            text="",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY),
            text_color=Colors.TEXT_MUTED,
            wraplength=220,
            justify="left"
        )
        self.hint_label.pack(fill="x", pady=(Spacing.MD, 0))
        self._update_level_menu("Video")

        # ── 3. Carpeta de Destino ──
        dest_card = ctk.CTkFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        dest_card.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
        
        dest_content = ctk.CTkFrame(dest_card, fg_color="transparent")
        dest_content.pack(fill="x", padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(dest_content, text="📁 Guardar en:", font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"), text_color=Colors.TEXT_PRIMARY).pack(side="left")
        
        self.dest_entry = ctk.CTkEntry(
            dest_content,
            placeholder_text=self.output_dir,
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
            fg_color=Colors.BG_DARK,
            border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Radius.SM,
            height=34
        )
        self.dest_entry.pack(side="left", fill="x", expand=True, padx=Spacing.MD)
        self.dest_entry.insert(0, self.output_dir)
        self.dest_entry.configure(state="readonly")
        
        self.btn_dest = ctk.CTkButton(
            dest_content,
            text="Cambiar",
            font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
            fg_color=Colors.BG_TERTIARY,
            hover_color=Colors.BG_HOVER,
            text_color=Colors.TEXT_PRIMARY,
            corner_radius=Radius.SM,
            width=80,
            height=34,
            command=self._select_dest
        )
        self.btn_dest.pack(side="right")

        # ── 4. Botón Ejecutar y Barra de Progreso ──
        # Disclaimer de uso de CPU
        self.disclaimer_lbl = ctk.CTkLabel(
            self,
            text="⚠️ Nota: La compresión de video es una tarea intensiva. El proceso se ejecuta en prioridad baja para que tu PC no se ralentice.",
            font=(Fonts.FAMILY, Fonts.SIZE_TINY),
            text_color=Colors.TEXT_MUTED,
            anchor="center"
        )
        self.disclaimer_lbl.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.XS))

        self.btn_compress = ctk.CTkButton(
            self,
            text="Iniciar Compresión 🗜",
            font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"),
            fg_color=Colors.ACCENT_PRIMARY,
            hover_color=Colors.BUTTON_HOVER,
            text_color=Colors.BUTTON_TEXT,
            corner_radius=Radius.LG,
            height=52,
            command=self._start_compression
        )
        self.btn_compress.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
        
        self.progress_bar = ctk.CTkProgressBar(
            self,
            fg_color=Colors.PROGRESS_BG,
            progress_color=Colors.ACCENT_YELLOW,
            corner_radius=Radius.SM,
            height=8
        )
        self.progress_bar.pack(fill="x", padx=Spacing.LG, pady=(0, Spacing.LG))
        self.progress_bar.set(0)

        # ── 5. Consola de Registro ──
        log_card = ctk.CTkFrame(self, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.LG, border_width=1, border_color=Colors.BORDER)
        log_card.pack(fill="both", expand=True, padx=Spacing.LG, pady=(0, Spacing.LG))
        
        log_content = ctk.CTkFrame(log_card, fg_color="transparent")
        log_content.pack(fill="both", expand=True, padx=Spacing.LG, pady=Spacing.LG)
        
        ctk.CTkLabel(log_content, text="📋 Registro de Actividad", font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"), text_color=Colors.TEXT_PRIMARY, anchor="w").pack(fill="x")
        
        self.log_console = ctk.CTkTextbox(
            log_content,
            fg_color=Colors.BG_DARK,
            text_color=Colors.TEXT_SECONDARY,
            font=(Fonts.FAMILY_MONO, Fonts.SIZE_SMALL),
            border_width=1,
            border_color=Colors.BORDER,
            corner_radius=Radius.SM,
            height=160
        )
        self.log_console.pack(fill="both", expand=True, pady=(Spacing.SM, 0))
        self.log_console.insert("1.0", "Listo para optimizar y comprimir archivos.\n")
        self.log_console.configure(state="disabled")
        
        self._update_files_list_ui()

    def _update_files_list_ui(self):
        """Limpia y dibuja la lista de archivos con botones de eliminar en Compressor."""
        for w in self.files_list.winfo_children():
            w.destroy()
            
        if not self.selected_files:
            lbl = ctk.CTkLabel(
                self.files_list,
                text="⬇  Arrastra archivos aquí, o usa 'Buscar Archivos'",
                font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
                text_color=Colors.TEXT_MUTED,
                anchor="w"
            )
            lbl.pack(fill="x", padx=5, pady=5)
            return

        for fpath in self.selected_files:
            row = ctk.CTkFrame(self.files_list, fg_color="transparent")
            row.pack(fill="x", pady=2)
            
            try:
                size_mb = os.path.getsize(fpath) / (1024 * 1024)
                text = f"• {os.path.basename(fpath)} ({size_mb:.1f} MB)"
            except Exception:
                text = f"• {os.path.basename(fpath)}"
                
            lbl = ctk.CTkLabel(
                row,
                text=text,
                font=(Fonts.FAMILY, Fonts.SIZE_SMALL),
                text_color=Colors.TEXT_SECONDARY,
                anchor="w"
            )
            lbl.pack(side="left", fill="x", expand=True, padx=(5, 0))
            
            btn_remove = ctk.CTkButton(
                row,
                text="✕",
                width=20,
                height=20,
                fg_color="transparent",
                hover_color=Colors.ERROR,
                text_color=Colors.TEXT_SECONDARY,
                font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold"),
                command=lambda p=fpath: self._remove_file(p)
            )
            btn_remove.pack(side="right", padx=5)

    def _remove_file(self, path):
        if path in self.selected_files:
            self.selected_files.remove(path)
            self._update_files_list_ui()
            self._log(f"Quitado de la cola: {os.path.basename(path)}\n")

    def _on_file_drop(self, event):
        import re
        data = event.data
        paths = re.findall(r'{([^}]+)}|([^\s{}]+)', data)
        parsed_paths = [p[0] or p[1] for p in paths]
        
        valid_paths = [p for p in parsed_paths if os.path.exists(p)]
        if valid_paths:
            for p in valid_paths:
                if p not in self.selected_files:
                    self.selected_files.append(p)
            ext = os.path.splitext(self.selected_files[0])[1].lower()
            detected = "Video"
            if ext in ['.jpg', '.jpeg', '.png', '.webp', '.bmp']:
                detected = "Imagen"
            elif ext in ['.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac']:
                detected = "Audio"
                
            self.category_var.set(detected)
            self._update_level_menu(detected)
            self._update_files_list_ui()
            self._log(f"📥 Archivos cargados por arrastre: {len(valid_paths)} nuevos archivos agregados.\n")

    def _select_files(self):
        category = self.category_var.get()
        if category == "Video":
            filetypes = [
                ("Archivos de Video", "*.mp4;*.mkv;*.avi;*.mov;*.webm"),
                ("Todos los archivos", "*.*")
            ]
        elif category == "Audio":
            filetypes = [
                ("Archivos de Audio", "*.mp3;*.wav;*.flac;*.m4a;*.ogg;*.aac"),
                ("Todos los archivos", "*.*")
            ]
        elif category == "Imagen":
            filetypes = [
                ("Archivos de Imagen", "*.jpg;*.jpeg;*.png;*.webp;*.bmp"),
                ("Todos los archivos", "*.*")
            ]
        else:
            filetypes = [("Todos los archivos", "*.*")]

        paths = filedialog.askopenfilenames(title="Seleccionar Archivos para Comprimir", filetypes=filetypes)
        if paths:
            for p in paths:
                if p not in self.selected_files:
                    self.selected_files.append(p)
            self._update_files_list_ui()
            self._log(f"Archivos cargados: {len(paths)} nuevos archivos agregados para compresión de {category}.\n")

    def _select_dest(self):
        path = filedialog.askdirectory(title="Seleccionar Carpeta de Destino")
        if path:
            self.output_dir = path
            self.dest_entry.configure(state="normal")
            self.dest_entry.delete(0, "end")
            self.dest_entry.insert(0, self.output_dir)
            self.dest_entry.configure(state="readonly")
            self._log(f"Carpeta de salida cambiada a: {self.output_dir}\n")

    def _on_category_change(self, val):
        self._update_level_menu(val)

    def _update_level_menu(self, category):
        self.level_menu.configure(state="normal")
        if category == "Video":
            self.level_label.configure(text="Nivel de Compresión:")
            formats = ["Media (Buen balance)", "Alta (WhatsApp/Discord - Max 16MB)", "Extrema (Correo - Max 8MB)"]
            self.hint_label.configure(text="💡 El nivel 'Alta' comprime a 720p y el bitrate. 'Extrema' reduce a 480p.")
        elif category == "Audio":
            self.level_label.configure(text="Bitrate Objetivo:")
            formats = ["128 kbps (Ahorro de espacio)", "96 kbps (Móvil básico)", "64 kbps (Baja calidad/Voz)"]
            self.hint_label.configure(text="💡 Ideal para podcasts, conferencias o grabaciones largas de voz.")
        elif category == "Imagen":
            self.level_label.configure(text="Nivel de Calidad:")
            formats = ["Media (Calidad 70%)", "Alta Compresión (Calidad 50%)", "Máxima Compresión (Calidad 30%)"]
            self.hint_label.configure(text="💡 Reduce el peso de fotos capturadas a alta resolución.")
        self.level_menu.configure(values=formats)
        self.level_var.set(formats[0])

    def _log(self, text):
        self.log_console.configure(state="normal")
        self.log_console.insert("end", text)
        self.log_console.see("end")
        self.log_console.configure(state="disabled")

    def _start_compression(self):
        if self._is_compressing:
            return
        if not self.selected_files:
            from core.utils import show_windows_notification
            show_windows_notification("MXP Compressor ⚠️", "Selecciona al menos un archivo para iniciar la compresión.")
            return
            
        self._is_compressing = True
        self.btn_compress.configure(state="disabled", text="Comprimiendo... 🗜")
        self.btn_select.configure(state="disabled")
        self.progress_bar.set(0)
        
        import threading
        threading.Thread(target=self._run_compression, daemon=True).start()

    def _run_compression(self):
        category = self.category_var.get()
        level = self.level_var.get()
        
        total = len(self.selected_files)
        self._log(f"\n--- Iniciando Compresión: {category} (Nivel: {level}) ---\n")
        
        success_count = 0
        
        for i, file_path in enumerate(self.selected_files):
            if not os.path.exists(file_path):
                self._log(f"[✗ Error] Archivo no existe: {file_path}\n")
                continue
                
            res = None
            orig_size = os.path.getsize(file_path) / (1024 * 1024)
            file_base_progress = i / total
            file_range = 1.0 / total

            def make_progress_cb(base, rng):
                def cb(pct):
                    overall = base + pct * rng
                    pct_int = int(overall * 100)
                    self.after(0, lambda p=overall, t=pct_int: (
                        self.progress_bar.set(p),
                        self.btn_compress.configure(text=f"Comprimiendo {t}%... 🗜")
                    ))
                return cb

            prog_cb = make_progress_cb(file_base_progress, file_range)
            
            if category == "Video":
                comp_param = "Media (Buena Calidad)"
                if "Alta" in level:
                    comp_param = "Alta (Para Redes Sociales)"
                elif "Extrema" in level:
                    comp_param = "Extrema"
                
                ext_orig = os.path.splitext(file_path)[1][1:].upper()
                res = self.media_engine.process_video(file_path, ext_orig, self.output_dir, comp_param, self._log_callback, progress_callback=prog_cb)
                
            elif category == "Audio":
                bitrate = "128k"
                if "96 kbps" in level:
                    bitrate = "96k"
                elif "64 kbps" in level:
                    bitrate = "64k"
                
                ext_orig = os.path.splitext(file_path)[1][1:].upper()
                res = self.media_engine.process_audio(file_path, ext_orig, self.output_dir, self._log_callback, bitrate=bitrate, progress_callback=prog_cb)
                
            elif category == "Imagen":
                comp_param = "Media (Buena Calidad)"
                if "Alta Compresión" in level:
                    comp_param = "Alta (Para Redes Sociales)"
                elif "Máxima Compresión" in level:
                    comp_param = "Extrema"
                    
                ext_orig = os.path.splitext(file_path)[1][1:].upper()
                res = self.image_engine.process_image(file_path, ext_orig, self.output_dir, comp_param, self._log_callback)
                # Imágenes son instantáneas — simular progreso completo
                self.after(0, lambda p=(i+1)/total: self.progress_bar.set(p))
                    
            if res and os.path.exists(res):
                success_count += 1
                new_size = os.path.getsize(res) / (1024 * 1024)
                savings = ((orig_size - new_size) / orig_size) * 100
                self._log(f"[✓] {os.path.basename(file_path)}: {orig_size:.1f} MB → {new_size:.1f} MB  (−{savings:.0f}%)\n")
            elif res is None:
                self._log(f"[✗] {os.path.basename(file_path)}: Falló la compresión. Revisa el Registro de Actividad.\n")

            # Marcar archivo completo
            self.after(0, lambda p=(i+1)/total: self.progress_bar.set(p))
            
        self._log(f"\n--- Compresión Finalizada: {success_count} de {total} procesados. ---\n")
        
        from core.utils import show_windows_notification
        if success_count == total:
            show_windows_notification("MXP Compressor 🗜", f"Optimización completa. {success_count} archivos comprimidos con éxito.")
        else:
            show_windows_notification("MXP Compressor ⚠️", f"Finalizado. {success_count} exitosos, {total - success_count} fallidos.")
            
        self.after(0, self._reset_ui_after_compress)

    def _log_callback(self, msg):
        self.after(0, lambda: self._log(f"{msg}\n"))

    def _reset_ui_after_compress(self):
        self._is_compressing = False
        self.progress_bar.set(1.0)
        self.btn_compress.configure(state="normal", text="Iniciar Compresión 🗜")
        self.btn_select.configure(state="normal")


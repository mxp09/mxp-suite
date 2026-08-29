"""
El popup de "hay una versión nueva".

Se mantiene deliberadamente agnóstico de la app: recibe una paleta y funciona
igual en el Downloader y en el Denoiser. Toda la parte de red ocurre en hilos;
la interfaz solo se toca desde el hilo de Tk mediante `after()`.
"""

import threading
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from mxp_common.updater import UpdateChecker, UpdateInfo
from mxp_common.version import APP_NAME

# Paleta por defecto (marca MXP: negro con acento amarillo).
DEFAULT_PALETTE = {
    "bg": "#0F0F0F",
    "surface": "#1A1A1A",
    "border": "#2A2A2A",
    "text": "#F2F2F2",
    "text_muted": "#A0A0A0",
    "accent": "#FFE600",
    "accent_hover": "#FFF04D",
    "accent_text": "#000000",
    "error": "#E74C3C",
}


class UpdateDialog(ctk.CTkToplevel):
    """Ventana que anuncia la versión nueva y, si el usuario acepta, la instala."""

    def __init__(self, parent, info: UpdateInfo, checker: UpdateChecker,
                 palette: Optional[dict] = None, app_name: str = APP_NAME):
        super().__init__(parent)

        self.info = info
        self.checker = checker
        self.palette = {**DEFAULT_PALETTE, **(palette or {})}
        self._downloading = False

        self.title(f"Actualización disponible — {app_name}")
        self.geometry("520x460")
        self.minsize(460, 400)
        self.configure(fg_color=self.palette["bg"])
        self.resizable(False, True)

        self._build_ui(app_name)
        self._center_on(parent)

        # Aparece por encima y toma el foco, pero sin secuestrar la app: si el
        # usuario la cierra con la X, equivale a "más tarde".
        self.transient(parent)
        self.after(120, self.grab_set)
        self.protocol("WM_DELETE_WINDOW", self._on_later)

    # ── Construcción ───────────────────────────────────────────────────────

    def _build_ui(self, app_name: str):
        container = ctk.CTkFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=24, pady=24)

        ctk.CTkLabel(
            container,
            text="Hay una versión nueva",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.palette["text"],
            anchor="w",
        ).pack(fill="x")

        ctk.CTkLabel(
            container,
            text=f"{app_name} {self.info.version} ya está disponible "
                 f"(tienes la {self.checker.current_version}).",
            font=ctk.CTkFont(size=13),
            text_color=self.palette["text_muted"],
            anchor="w",
            justify="left",
            wraplength=460,
        ).pack(fill="x", pady=(6, 16))

        # ── Notas del release ──
        notes_box = ctk.CTkTextbox(
            container,
            fg_color=self.palette["surface"],
            border_color=self.palette["border"],
            border_width=1,
            text_color=self.palette["text_muted"],
            font=ctk.CTkFont(size=12),
            wrap="word",
            corner_radius=10,
        )
        notes_box.pack(fill="both", expand=True)
        notes_box.insert("1.0", self.info.notes or "Sin notas para esta versión.")
        notes_box.configure(state="disabled")

        # ── Zona de progreso (oculta hasta que se pulsa Descargar) ──
        self.status_label = ctk.CTkLabel(
            container,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=self.palette["text_muted"],
            anchor="w",
        )
        self.progress_bar = ctk.CTkProgressBar(
            container,
            height=6,
            corner_radius=3,
            fg_color=self.palette["surface"],
            progress_color=self.palette["accent"],
        )
        self.progress_bar.set(0)

        # ── Botones ──
        self.buttons = ctk.CTkFrame(container, fg_color="transparent")
        self.buttons.pack(fill="x", pady=(16, 0))

        self.skip_button = ctk.CTkButton(
            self.buttons,
            text="Omitir esta versión",
            width=140,
            height=36,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.palette["surface"],
            text_color=self.palette["text_muted"],
            border_width=1,
            border_color=self.palette["border"],
            font=ctk.CTkFont(size=12),
            command=self._on_skip,
        )
        self.skip_button.pack(side="left")

        self.download_button = ctk.CTkButton(
            self.buttons,
            text="Descargar e instalar",
            width=170,
            height=36,
            corner_radius=8,
            fg_color=self.palette["accent"],
            hover_color=self.palette["accent_hover"],
            text_color=self.palette["accent_text"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._on_download,
        )
        self.download_button.pack(side="right")

        self.later_button = ctk.CTkButton(
            self.buttons,
            text="Más tarde",
            width=100,
            height=36,
            corner_radius=8,
            fg_color="transparent",
            hover_color=self.palette["surface"],
            text_color=self.palette["text_muted"],
            border_width=1,
            border_color=self.palette["border"],
            font=ctk.CTkFont(size=12),
            command=self._on_later,
        )
        self.later_button.pack(side="right", padx=(0, 8))

    def _center_on(self, parent):
        """Centra el diálogo sobre la ventana principal."""
        try:
            self.update_idletasks()
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 3}")
        except Exception:
            pass  # centrar es cosmético; si falla, que aparezca donde sea

    # ── Acciones ───────────────────────────────────────────────────────────

    def _on_skip(self):
        self.checker.skip_version(self.info.version)
        self._close()

    def _on_later(self):
        if self._downloading:
            return  # no dejar cerrar a mitad de la descarga
        self._close()

    def _close(self):
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _on_download(self):
        if self._downloading:
            return
        self._downloading = True

        self.download_button.configure(state="disabled", text="Descargando...")
        self.skip_button.configure(state="disabled")
        self.later_button.configure(state="disabled")
        self.status_label.pack(fill="x", pady=(14, 4), before=self.buttons)
        self.progress_bar.pack(fill="x", before=self.buttons)

        threading.Thread(target=self._download_worker, daemon=True).start()

    def _download_worker(self):
        """Corre en un hilo. Todo lo que toque la UI pasa por `after()`."""

        def on_progress(message: str, percent: float):
            self.after(0, self._set_progress, message, percent)

        try:
            installer_path = self.checker.download(self.info, on_progress)
        except Exception as exc:
            self.after(0, self._on_download_failed, str(exc))
            return
        self.after(0, self._on_download_done, installer_path)

    def _set_progress(self, message: str, percent: float):
        if not self.winfo_exists():
            return
        self.status_label.configure(text=message, text_color=self.palette["text_muted"])
        self.progress_bar.set(max(0.0, min(percent, 100.0)) / 100.0)

    def _on_download_failed(self, error: str):
        self._downloading = False
        self.status_label.configure(text=error, text_color=self.palette["error"])
        self.progress_bar.pack_forget()
        self.download_button.configure(state="normal", text="Reintentar")
        self.skip_button.configure(state="normal")
        self.later_button.configure(state="normal")

    def _on_download_done(self, installer_path: str):
        self.status_label.configure(
            text="Descarga verificada. Se abrirá el instalador y la app se cerrará."
        )
        try:
            self.checker.launch_installer(installer_path)
        except Exception as exc:
            self._on_download_failed(f"No se pudo abrir el instalador: {exc}")
            return
        # El instalador no puede sobrescribir un .exe en uso, así que salimos.
        self.after(600, self._quit_app)

    def _quit_app(self):
        root = self.master
        self._close()
        try:
            root.quit()
            root.destroy()
        except Exception:
            import sys
            sys.exit(0)


def attach_update_check(parent, checker: Optional[UpdateChecker] = None,
                        palette: Optional[dict] = None,
                        app_name: str = APP_NAME, delay: float = 2.0):
    """
    Cablea la comprobación de actualizaciones a una ventana con una sola línea.

    Arranca la consulta en segundo plano tras `delay` segundos (para no competir
    con el arranque) y, solo si hay algo nuevo, muestra el diálogo. Sin red o
    sin versión nueva no ocurre absolutamente nada visible.
    """
    checker = checker or UpdateChecker()

    def on_result(info: Optional[UpdateInfo]):
        if info is None:
            return
        # El callback llega desde un hilo; volver al hilo de Tk antes de crear widgets.
        try:
            parent.after(0, lambda: UpdateDialog(parent, info, checker, palette, app_name))
        except (tk.TclError, RuntimeError):
            pass  # la ventana ya se cerró

    checker.check_async(on_result, delay=delay)
    return checker

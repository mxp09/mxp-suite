"""
MXP Downloader — Punto de entrada principal.

Dependencias de Python:
    pip install customtkinter Pillow requests tkinterdnd2

Dependencias externas (ffmpeg, ffprobe y el motor yt-dlp):
    Las deja el instalador, y si faltan la app las descarga y verifica sola en
    el primer arranque. No hace falta instalar nada a mano ni tocar el PATH.
"""

import os
import sys

# El directorio del proyecto tiene que estar en sys.path antes que nada para
# que `mxp_common` sea importable tanto ejecutando el .pyw como congelado.
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Logging ──
# Antes, un fallo en la máquina de otra persona no dejaba ningún rastro que
# revisar: en modo ventana (sin consola) los `print` no van a ninguna parte.
# A partir de aquí queda un archivo en %APPDATA%/MXP_Downloader/logs/app.log
# que se puede pedir cuando alguien reporte "no me funciona".
from mxp_common.logs import setup_logging  # noqa: E402

logger = setup_logging()


def _log_unhandled(exc_type, exc_value, exc_tb):
    logger.critical("Excepción no controlada", exc_info=(exc_type, exc_value, exc_tb))


sys.excepthook = _log_unhandled

# ── Motor de descarga ──
# yt-dlp vive fuera del ejecutable, en %APPDATA%, para poder actualizarse sin
# reinstalar la app. Esto DEBE ejecutarse antes de cualquier `import yt_dlp`
# (que ocurre dentro de gui.app), así que va aquí arriba a propósito.
from mxp_common.binaries import activate_engine  # noqa: E402

_ENGINE_READY = activate_engine()

import customtkinter as ctk  # noqa: E402


def _install_engine_blocking() -> bool:
    """
    Primer arranque sin motor: instalarlo antes de abrir la ventana.

    Sin yt-dlp la app no puede hacer su trabajo, así que aquí sí se espera —
    pero mostrando una ventana con progreso, no una pantalla congelada.
    """
    from mxp_common.binaries import EngineManager

    splash = ctk.CTk()
    splash.title("MXP Downloader — Preparando")
    splash.geometry("420x150")
    splash.resizable(False, False)
    splash.configure(fg_color="#0F0F0F")

    label = ctk.CTkLabel(
        splash,
        text="Instalando el motor de descarga...",
        font=("Segoe UI", 13),
        text_color="#F2F2F2",
        wraplength=380,
    )
    label.pack(pady=(34, 14), padx=20)

    bar = ctk.CTkProgressBar(splash, width=340, height=6,
                             fg_color="#1A1A1A", progress_color="#FFE600")
    bar.set(0)
    bar.pack()

    result = {"ok": False}

    def on_progress(message, percent):
        def apply():
            label.configure(text=message)
            bar.set(max(0.0, min(percent, 100.0)) / 100.0)
        try:
            splash.after(0, apply)
        except Exception:
            pass

    def work():
        result["ok"] = EngineManager(on_progress).ensure()
        try:
            splash.after(400, splash.destroy)
        except Exception:
            pass

    import threading
    threading.Thread(target=work, daemon=True).start()
    splash.mainloop()
    return result["ok"]


def main():
    global _ENGINE_READY

    # El instalador nos invoca con --setup-deps para dejar ffmpeg y el motor
    # listos. En ese modo no se abre ninguna ventana: se instala, se verifica
    # y se devuelve un codigo de salida que el instalador comprueba.
    from mxp_common.bootstrap import maybe_run_from_argv
    maybe_run_from_argv(need_engine=True)

    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    if not _ENGINE_READY:
        if not _install_engine_blocking():
            import tkinter.messagebox as mb
            mb.showerror(
                "MXP Downloader",
                "No se pudo instalar el motor de descarga.\n\n"
                "Comprueba tu conexión a internet y vuelve a abrir la aplicación.",
            )
            return
        activate_engine()

    from gui.app import App

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

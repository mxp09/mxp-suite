"""
Video Downloader — Punto de entrada principal.
Aplicación de escritorio para descargar videos usando yt-dlp.

Dependencias:
    pip install yt-dlp customtkinter Pillow

Requisitos del sistema:
    - Python 3.9+
    - ffmpeg instalado y en el PATH
"""

import customtkinter as ctk


def main():
    # ── Configuración global de CustomTkinter ──
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    # ── Importar y lanzar la app ──
    from gui.app import App

    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()

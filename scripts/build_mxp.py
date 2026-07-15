import os
import shutil
import subprocess
import sys

# ─── Configuración ─────────────────────────────────────────────────────────────

APP_NAME = "MXPDownloader"
ENTRY_POINT = "MXPDOWNLOADER.pyw"
ICON_PATH = "assets/icon.ico"
OUTPUT_DIR = "dist"

# Metadata Profesional
COMPANY_NAME = "MXP Productions"
PRODUCT_NAME = "MXP Downloader"
DESCRIPTION = "Herramienta profesional de gestión de medios."
COPYRIGHT = "© 2026 Iván Chong"
VERSION = "1.0.0.0"
ICON_PATH = "assets/logo_transparente.ico"

# ─── Funciones ────────────────────────────────────────────────────────────────

def run_command(command):
    print(f" Ejecutando: {' '.join(command)}")
    result = subprocess.run(command, shell=True)
    if result.returncode != 0:
        print(f" Error: El comando falló con código {result.returncode}")
        sys.exit(1)

def clean():
    print(" Limpiando carpetas de construcción...")
    for folder in ["build", OUTPUT_DIR, f"{APP_NAME}.dist", f"{APP_NAME}.build"]:
        if os.path.exists(folder):
            shutil.rmtree(folder)

def build():
    print(f" Compilando {PRODUCT_NAME} con Nuitka Standalone...")
    
    command = [
        "py", "-m", "nuitka",
        "--standalone",
        "--windows-disable-console",
        f"--windows-icon-from-ico={ICON_PATH}",
        "--plugin-enable=tk-inter",
        "--include-package-data=customtkinter",
        
        # Metadata
        f"--company-name={COMPANY_NAME}",
        f"--product-name={PRODUCT_NAME}",
        f"--file-description={DESCRIPTION}",
        f"--copyright={COPYRIGHT}",
        f"--file-version={VERSION}",
        f"--product-version={VERSION}",
        
        # Optimizaciones
        "--assume-yes-for-downloads",
        "--output-dir=" + OUTPUT_DIR,
        f"--output-filename={APP_NAME}.exe",
        
        ENTRY_POINT
    ]
    
    run_command(command)

def post_process():
    print(" Organizando archivos de distribución...")
    
    # Nuitka genera una carpeta .dist dentro de OUTPUT_DIR
    source_dist = os.path.join(OUTPUT_DIR, f"{APP_NAME}.dist")
    final_dist = os.path.join(OUTPUT_DIR, f"{PRODUCT_NAME}_Standalone")
    
    if os.path.exists(final_dist):
        shutil.rmtree(final_dist)
    
    os.rename(source_dist, final_dist)
    
    # Copiar carpetas necesarias
    for folder in ["assets", "bin"]:
        if os.path.exists(folder):
            print(f" Copiando {folder} a la carpeta de salida...")
            shutil.copytree(folder, os.path.join(final_dist, folder))

    print(f"\n ¡Éxito! Distribución lista en: {final_dist}")

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    clean()
    build()
    post_process()

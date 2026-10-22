"""
Motor de transcripción local: whisper.cpp (MIT) + modelos GGML de Whisper.

Mismo contrato que ffmpeg/Deno en binaries.py: se descarga, se verifica el
SHA-256 publicado y solo cuenta como listo si el ejecutable responde.
Todo vive en %APPDATA%/MXP_Downloader/{transcriber,models}.
"""

import io
import os
import shutil
import subprocess
import sys
import zipfile
from typing import Callable, Dict, List, Optional

from mxp_common.binaries import check_sha256, download_to_buffer, verify_executable
from mxp_common.paths import get_app_dir

ProgressCallback = Callable[[str, float], None]

# Versión fijada (con hash) en lugar de "latest": los releases sueltos de
# whisper.cpp a veces salen sin binarios de Windows (v1.9.3 y v1.9.4 no traen).
WHISPER_ZIP_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/v1.9.2/whisper-bin-x64.zip"
WHISPER_ZIP_SHA256 = "49dcc16de826f20bd53d44f947a1ae49dfa81f86cad67a64d80820cb192d674a"

HF_BASE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"

# clave -> (archivo, bytes, sha256, nombre visible, descripción)
MODELS: Dict[str, tuple] = {
    "tiny": ("ggml-tiny.bin", 77691713,
             "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
             "Tiny", "Pruebas o PCs muy lentos (poca precisión)"),
    "base": ("ggml-base.bin", 147951465,
             "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
             "Base", "Rápido, voz clara y notas"),
    "small": ("ggml-small.bin", 487601967,
              "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
              "Small", "Equilibrado"),
    "turbo-q5": ("ggml-large-v3-turbo-q5_0.bin", 574041195,
                 "394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2",
                 "Large-v3-turbo comprimido", "Recomendado: casi la máxima precisión, rápido en CPU"),
    "medium": ("ggml-medium.bin", 1533763059,
               "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208",
               "Medium", "Alta precisión, más lento (pesado)"),
    "turbo": ("ggml-large-v3-turbo.bin", 1624555275,
              "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69",
              "Large-v3-turbo", "Precisión máxima a buena velocidad (pesado)"),
    "large": ("ggml-large-v3.bin", 3095033483,
              "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2",
              "Large-v3", "Precisión máxima, el más lento (pesado)"),
}
DEFAULT_MODEL = "turbo-q5"
HEAVY_BYTES = 1_000_000_000


def transcriber_dir() -> str:
    path = os.path.join(get_app_dir(), "transcriber")
    os.makedirs(path, exist_ok=True)
    return path


def models_dir() -> str:
    path = os.path.join(get_app_dir(), "models")
    os.makedirs(path, exist_ok=True)
    return path


def whisper_cli() -> Optional[str]:
    """Ruta de whisper-cli.exe si existe y responde, si no None."""
    exe = os.path.join(transcriber_dir(), "whisper-cli.exe")
    return exe if verify_executable(exe, flag="--version") else None


# Runtime de Visual C++ que whisper-cli.exe necesita (compilado con OpenMP).
# Un Windows limpio no lo trae: sin esto salía "no se encontró VCOMP140.DLL".
VC_RUNTIME_DLLS = ("vcomp140.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll")
_STATUS_DLL_NOT_FOUND = 0xC0000135


def _vc_runtime_source() -> str:
    """Carpeta de donde copiar el runtime: la que empaqueta el .exe, o System32 en desarrollo."""
    if getattr(sys, "frozen", False):
        return os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)), "vcrt")
    return os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")


def install_vc_runtime() -> bool:
    """Copia las DLL del runtime junto a whisper-cli.exe. True si quedaron todas."""
    src_dir, target = _vc_runtime_source(), transcriber_dir()
    for name in VC_RUNTIME_DLLS:
        src, dst = os.path.join(src_dir, name), os.path.join(target, name)
        if os.path.isfile(src) and not os.path.isfile(dst):
            shutil.copy2(src, dst + ".part")
            os.replace(dst + ".part", dst)
    return all(os.path.isfile(os.path.join(target, n)) for n in VC_RUNTIME_DLLS)


def diagnose_engine() -> str:
    """Explica en una línea por qué whisper-cli no arranca ('' si arranca)."""
    exe = os.path.join(transcriber_dir(), "whisper-cli.exe")
    if not os.path.isfile(exe):
        return "falta whisper-cli.exe"
    try:
        res = subprocess.run([exe, "--version"], capture_output=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as exc:
        return f"no arranca ({exc})"
    if res.returncode == 0:
        return ""
    if res.returncode & 0xFFFFFFFF == _STATUS_DLL_NOT_FOUND:
        missing = [n for n in VC_RUNTIME_DLLS if not os.path.isfile(os.path.join(transcriber_dir(), n))]
        return "faltan DLL del sistema: " + (", ".join(missing) or "desconocida")
    return f"no arranca (código {res.returncode & 0xFFFFFFFF:#x})"


def model_path(key: str) -> str:
    return os.path.join(models_dir(), MODELS[key][0])


def installed_models() -> List[str]:
    """Modelos presentes con el tamaño exacto esperado (descarga completa)."""
    return [k for k, m in MODELS.items()
            if os.path.isfile(model_path(k)) and os.path.getsize(model_path(k)) == m[1]]


def human_size(n: int) -> str:
    return f"{n / 1e9:.1f} GB" if n >= 1e9 else f"{n / 1e6:.0f} MB"


def install_engine_from_zip(data: bytes) -> bool:
    """Extrae whisper-cli.exe y sus DLL (whisper/ggml) del zip oficial ya verificado."""
    check_sha256(data, WHISPER_ZIP_SHA256, "Motor de transcripción")
    target = transcriber_dir()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.namelist():
            name = os.path.basename(member)
            if name == "whisper-cli.exe" or (name.endswith(".dll") and name.startswith(("whisper", "ggml"))):
                with archive.open(member) as src, open(os.path.join(target, name + ".part"), "wb") as out:
                    out.write(src.read())
                os.replace(os.path.join(target, name + ".part"), os.path.join(target, name))
    install_vc_runtime()
    return whisper_cli() is not None


def ensure_engine(progress: Optional[ProgressCallback] = None, start=0.0, end=100.0) -> bool:
    if whisper_cli():
        return True
    # Instalaciones 3.2.0: el exe está pero le falta el runtime VC++. Se
    # repara copiándolo, sin volver a descargar nada.
    if os.path.isfile(os.path.join(transcriber_dir(), "whisper-cli.exe")):
        install_vc_runtime()
        if whisper_cli():
            return True
    data = download_to_buffer(WHISPER_ZIP_URL, progress, "Descargando el motor de transcripción...",
                              start, end, timeout=60.0).getvalue()
    return install_engine_from_zip(data)


def install_model_file(key: str, src_path: str) -> bool:
    """Coloca un modelo ya descargado (p. ej. por el instalador) tras verificar su hash."""
    import hashlib
    filename, size, sha, *_ = MODELS[key]
    digest = hashlib.sha256()
    with open(src_path, "rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != sha:
        return False
    import shutil
    shutil.move(src_path, model_path(key))  # mover funciona también entre unidades
    return True


def download_model(key: str, progress: Optional[ProgressCallback] = None, cancel=None) -> bool:
    """Descarga un modelo a disco por streaming (pueden ser 3 GB) y verifica su hash."""
    import hashlib
    import requests
    filename, size, sha, label, _ = MODELS[key]
    final = model_path(key)
    tmp = final + ".part"
    digest = hashlib.sha256()
    done = 0
    with requests.get(HF_BASE + filename, stream=True, timeout=60) as response:
        response.raise_for_status()
        with open(tmp, "wb") as out:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if cancel is not None and cancel.is_set():
                    out.close()
                    os.remove(tmp)
                    return False
                out.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress:
                    progress(f"Descargando modelo {label}... {human_size(done)} de {human_size(size)}",
                             done * 100.0 / size)
    if digest.hexdigest() != sha:
        os.remove(tmp)
        raise RuntimeError(f"Modelo {label}: la descarga no coincide con su hash publicado")
    os.replace(tmp, final)
    return True

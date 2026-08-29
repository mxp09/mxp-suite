"""
Resolución, descarga y verificación de las dependencias externas.

La diferencia clave con la versión anterior: aquí un binario no se da por bueno
porque exista el archivo, sino porque **se ejecuta y responde**. Una descarga
cortada a la mitad deja un ffmpeg.exe de 3 MB que os.path.exists() aprueba
encantado y que luego falla en cada conversión sin explicar por qué.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from typing import Callable, Optional, Tuple

import requests

from mxp_common.paths import get_bin_dir, get_engine_dir, get_install_dir

# Callback de progreso: (mensaje, porcentaje 0-100). -1 en porcentaje = error.
ProgressCallback = Callable[[str, float], None]

FFMPEG_ZIP_URL = (
    "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
    "ffmpeg-master-latest-win64-gpl.zip"
)
PYPI_YTDLP_JSON = "https://pypi.org/pypi/yt-dlp/json"

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


# ─── Verificación real ──────────────────────────────────────────────────────────

def verify_executable(path: str, timeout: float = 10.0) -> bool:
    """
    Comprueba que el binario existe Y arranca de verdad.

    Un archivo truncado por una descarga cortada, o bloqueado por el antivirus,
    supera os.path.exists() pero falla aquí — que es justo lo que queremos.
    """
    if not path or not os.path.isfile(path):
        return False
    try:
        res = subprocess.run(
            [path, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
        return res.returncode == 0
    except Exception:
        return False


def resolve_tool(name: str) -> Optional[str]:
    """
    Busca una herramienta (ffmpeg / ffprobe) en orden de preferencia:
      1. bin/ junto al ejecutable   -> lo que deja el instalador
      2. %APPDATA%/<app>/bin        -> lo que descarga la app por su cuenta
      3. el PATH del sistema        -> lo que el usuario ya tuviera

    Devuelve la ruta solo si el binario responde. None si no hay ninguno usable.
    """
    exe = f"{name}.exe" if os.name == "nt" else name

    candidates = [
        os.path.join(get_install_dir(), "bin", exe),
        os.path.join(get_bin_dir(), exe),
    ]
    from_path = shutil.which(name)
    if from_path:
        candidates.append(from_path)

    for candidate in candidates:
        if verify_executable(candidate):
            return candidate
    return None


# ─── Descarga con progreso ──────────────────────────────────────────────────────

def download_to_buffer(
    url: str,
    progress_callback: Optional[ProgressCallback] = None,
    message: str = "Descargando...",
    start_pct: float = 0.0,
    end_pct: float = 100.0,
    timeout: float = 30.0,
) -> io.BytesIO:
    """Descarga a memoria informando del progreso. Lanza excepción si falla."""
    buffer = io.BytesIO()
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            buffer.write(chunk)
            downloaded += len(chunk)
            if progress_callback and total > 0:
                pct = start_pct + (downloaded / total) * (end_pct - start_pct)
                progress_callback(message, pct)
    buffer.seek(0)
    return buffer


def download_to_file(
    url: str,
    dest_path: str,
    progress_callback: Optional[ProgressCallback] = None,
    message: str = "Descargando...",
    start_pct: float = 0.0,
    end_pct: float = 100.0,
    timeout: float = 30.0,
) -> str:
    """
    Descarga a disco de forma atómica: escribe en .part y solo renombra al
    terminar. Si se corta la conexión no queda un archivo a medias haciéndose
    pasar por bueno.
    """
    parent = os.path.dirname(dest_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp_path = dest_path + ".part"
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        total = int(response.headers.get("content-length", 0))
        downloaded = 0
        with open(tmp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                if progress_callback and total > 0:
                    pct = start_pct + (downloaded / total) * (end_pct - start_pct)
                    progress_callback(message, pct)
    os.replace(tmp_path, dest_path)
    return dest_path


# ─── FFmpeg ─────────────────────────────────────────────────────────────────────

class FFmpegManager:
    """Garantiza que ffmpeg y ffprobe existan y funcionen."""

    TOOLS = ("ffmpeg", "ffprobe")

    def __init__(self, progress_callback: Optional[ProgressCallback] = None):
        self.progress_callback = progress_callback
        self._paths = {}

    def _report(self, message: str, pct: float):
        if self.progress_callback:
            self.progress_callback(message, pct)

    def path(self, name: str) -> Optional[str]:
        """Ruta verificada de la herramienta, o None si no está disponible."""
        if name not in self._paths:
            self._paths[name] = resolve_tool(name)
        return self._paths[name]

    @property
    def ffmpeg(self) -> Optional[str]:
        return self.path("ffmpeg")

    @property
    def ffprobe(self) -> Optional[str]:
        return self.path("ffprobe")

    def is_ready(self) -> bool:
        return all(self.path(t) for t in self.TOOLS)

    def missing(self) -> list:
        return [t for t in self.TOOLS if not self.path(t)]

    def refresh(self):
        """Olvida las rutas cacheadas y vuelve a buscar."""
        self._paths.clear()

    def ensure(self, start_pct: float = 0.0, end_pct: float = 100.0) -> bool:
        """
        Deja ffmpeg y ffprobe listos, descargándolos si hace falta.
        Devuelve True si al terminar ambos responden.
        """
        if self.is_ready():
            self._report("FFmpeg listo", end_pct)
            return True

        self._report("Descargando FFmpeg (puede tardar un minuto)...", start_pct)
        buffer = download_to_buffer(
            FFMPEG_ZIP_URL,
            self.progress_callback,
            "Descargando FFmpeg...",
            start_pct,
            start_pct + (end_pct - start_pct) * 0.85,
            timeout=60.0,
        )

        self._report("Extrayendo FFmpeg...", start_pct + (end_pct - start_pct) * 0.9)
        bin_dir = get_bin_dir()
        wanted = {f"{t}.exe" for t in self.TOOLS}
        with zipfile.ZipFile(buffer) as archive:
            for member in archive.namelist():
                basename = os.path.basename(member)
                if basename in wanted:
                    target = os.path.join(bin_dir, basename)
                    tmp = target + ".part"
                    with archive.open(member) as source, open(tmp, "wb") as out:
                        shutil.copyfileobj(source, out)
                    os.replace(tmp, target)

        # Invalidar la caché para que la verificación mire el archivo nuevo
        self.refresh()
        ok = self.is_ready()
        self._report(
            "FFmpeg listo" if ok else "FFmpeg no se pudo instalar",
            end_pct if ok else -1,
        )
        return ok


# ─── Motor yt-dlp actualizable ──────────────────────────────────────────────────

class EngineManager:
    """
    Mantiene yt-dlp en %APPDATA%/<app>/engine como paquete Python sustituible.

    Antes yt-dlp iba compilado dentro del .exe: el motor se quedaba congelado en
    la fecha del build y, como los sitios cambian su extracción cada pocas
    semanas, acababa devolviendo 403 sin que hubiera forma de arreglarlo salvo
    recompilar y redistribuir la app entera. Aquí vive fuera y se actualiza solo.
    """

    STAMP_FILE = "engine.json"
    CHECK_INTERVAL_SECONDS = 6 * 60 * 60  # no molestar a PyPI más de una vez cada 6 h

    def __init__(self, progress_callback: Optional[ProgressCallback] = None):
        self.progress_callback = progress_callback
        self.engine_dir = get_engine_dir()

    def _report(self, message: str, pct: float):
        if self.progress_callback:
            self.progress_callback(message, pct)

    @property
    def _stamp_path(self) -> str:
        return os.path.join(self.engine_dir, self.STAMP_FILE)

    def _read_stamp(self) -> dict:
        try:
            with open(self._stamp_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_stamp(self, data: dict):
        try:
            with open(self._stamp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # el sello es una optimización, no algo por lo que fallar

    def installed_version(self) -> Optional[str]:
        """Versión instalada, o None si el motor no está o está incompleto."""
        if not os.path.isdir(os.path.join(self.engine_dir, "yt_dlp")):
            return None
        return self._read_stamp().get("version")

    def is_installed(self) -> bool:
        return self.installed_version() is not None

    def latest_release(self) -> Tuple[str, str]:
        """
        Consulta PyPI y devuelve (versión, url_del_wheel).

        Se usa PyPI y no los releases de GitHub porque el wheel es un zip que se
        extrae tal cual y da el paquete yt_dlp/ ya listo para importar.
        """
        response = requests.get(PYPI_YTDLP_JSON, timeout=10)
        response.raise_for_status()
        data = response.json()
        version = data["info"]["version"]
        for entry in data["urls"]:
            if entry.get("packagetype") == "bdist_wheel" and entry["filename"].endswith(
                "-py3-none-any.whl"
            ):
                return version, entry["url"]
        raise RuntimeError("PyPI no devolvió un wheel utilizable de yt-dlp")

    def _verify_importable(self) -> bool:
        """
        Comprueba que el motor recién instalado arranca de verdad, lanzando un
        `import yt_dlp` en un intérprete aparte (no en este proceso, para no
        arriesgarse a dejarlo en un estado raro si el import falla a medias).

        Solo hace falta en Python 3.10: yt-dlp ya avisa que lo va a deprecar y
        lo retirará "poco después" de que 3.10 llegue a su end-of-life
        (oct-2026, ver https://github.com/yt-dlp/yt-dlp/issues/16916). Sin esta
        comprobación, el día que publiquen una versión que ya no arranque en
        3.10, la actualización automática de las 6h la instalaría igual y
        rompería la app en todas las máquinas sin que nadie tocara nada. En
        3.11+ no hace falta el coste extra de lanzar un subproceso.
        """
        if sys.version_info >= (3, 11):
            return True
        try:
            result = subprocess.run(
                [sys.executable, "-c", "import yt_dlp"],
                cwd=self.engine_dir,
                capture_output=True,
                timeout=15,
                creationflags=_NO_WINDOW,
            )
            return result.returncode == 0
        except Exception:
            return False

    def install(
        self,
        version: str,
        wheel_url: str,
        start_pct: float = 0.0,
        end_pct: float = 100.0,
    ) -> bool:
        """Descarga el wheel y reemplaza el motor. Devuelve True si quedó usable."""
        message = f"Descargando motor de descarga (yt-dlp {version})..."
        self._report(message, start_pct)
        buffer = download_to_buffer(
            wheel_url,
            self.progress_callback,
            message,
            start_pct,
            start_pct + (end_pct - start_pct) * 0.85,
        )

        self._report(
            "Instalando motor de descarga...", start_pct + (end_pct - start_pct) * 0.9
        )
        staging = os.path.join(self.engine_dir, ".staging")
        shutil.rmtree(staging, ignore_errors=True)
        os.makedirs(staging, exist_ok=True)
        with zipfile.ZipFile(buffer) as archive:
            archive.extractall(staging)

        staged_pkg = os.path.join(staging, "yt_dlp")
        if not os.path.isdir(staged_pkg):
            shutil.rmtree(staging, ignore_errors=True)
            self._report("El motor descargado no es válido", -1)
            return False

        # Reemplazo en dos pasos: el motor viejo solo se borra cuando el nuevo
        # ya está extraído entero, así un fallo a mitad no deja la app sin motor.
        final_pkg = os.path.join(self.engine_dir, "yt_dlp")
        old_pkg = final_pkg + ".old"
        shutil.rmtree(old_pkg, ignore_errors=True)
        had_previous = os.path.isdir(final_pkg)
        if had_previous:
            os.replace(final_pkg, old_pkg)
        os.replace(staged_pkg, final_pkg)

        # Verificación real: el swap puede haber dejado un paquete que no
        # arranca en este intérprete (típicamente porque yt-dlp ya dejó de
        # soportar esta versión de Python). Si es así, se deshace en vez de
        # dejar la app sin motor funcional hasta el próximo reinicio.
        if not self._verify_importable():
            shutil.rmtree(final_pkg, ignore_errors=True)
            if had_previous:
                os.replace(old_pkg, final_pkg)
            shutil.rmtree(staging, ignore_errors=True)
            stamp = self._read_stamp()
            stamp["last_check"] = time.time()
            stamp["blocked_version"] = version
            self._write_stamp(stamp)
            self._report(
                f"El motor yt-dlp {version} no es compatible con esta versión "
                f"de Python; se mantiene la versión anterior.",
                -1,
            )
            return had_previous

        shutil.rmtree(old_pkg, ignore_errors=True)
        shutil.rmtree(staging, ignore_errors=True)

        stamp = self._read_stamp()
        stamp.pop("blocked_version", None)
        stamp.update(
            {"version": version, "installed_at": time.time(), "last_check": time.time()}
        )
        self._write_stamp(stamp)
        self._report(f"Motor yt-dlp {version} listo", end_pct)
        return True

    def ensure(self, start_pct: float = 0.0, end_pct: float = 100.0) -> bool:
        """Instala el motor si falta. No comprueba actualizaciones."""
        if self.is_installed():
            self._report("Motor de descarga listo", end_pct)
            return True
        try:
            version, url = self.latest_release()
            return self.install(version, url, start_pct, end_pct)
        except Exception as exc:
            self._report(f"No se pudo instalar el motor de descarga: {exc}", -1)
            return False

    def update_if_stale(self) -> Optional[str]:
        """
        Comprueba y aplica una actualización del motor, como mucho una vez cada
        6 horas. Pensado para llamarse en un hilo al arrancar: si no hay red o
        PyPI no responde, no pasa nada y se sigue con el motor que ya hay.

        Devuelve la versión nueva si actualizó, None en cualquier otro caso.
        """
        stamp = self._read_stamp()
        if time.time() - stamp.get("last_check", 0) < self.CHECK_INTERVAL_SECONDS:
            return None

        try:
            version, url = self.latest_release()
        except Exception:
            return None

        # last_check se actualiza siempre que la consulta a PyPI responda,
        # pase lo que pase después: si no, un install() que falla por algo
        # ajeno a la versión (disco lleno, etc.) haría que se reintentara en
        # cada llamada en vez de esperar las 6h.
        stamp["last_check"] = time.time()
        self._write_stamp(stamp)

        if version == stamp.get("version"):
            return None

        # Ya se intentó esta versión y no arrancó en este Python (ver
        # install()/_verify_importable). No tiene sentido volver a
        # descargarla cada 6h hasta que PyPI publique una más nueva.
        if version == stamp.get("blocked_version"):
            return None

        return version if self.install(version, url) else None


def activate_engine() -> bool:
    """
    Antepone la carpeta del motor a sys.path.

    Debe llamarse ANTES de cualquier `import yt_dlp`, es decir lo primero de
    todo en el punto de entrada. Devuelve True si hay un motor que activar.
    """
    engine_dir = get_engine_dir()
    if engine_dir in sys.path:
        sys.path.remove(engine_dir)
    sys.path.insert(0, engine_dir)
    return os.path.isdir(os.path.join(engine_dir, "yt_dlp"))

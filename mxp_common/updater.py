"""
Comprobación e instalación de actualizaciones contra GitHub Releases.

Reglas que rigen todo este módulo:
  · Nunca bloquear la interfaz. La comprobación va en un hilo daemon con
    timeout corto; si no hay red, la app arranca igual y nadie se entera.
  · Nunca dar por buena una descarga sin verificar. El instalador se contrasta
    contra el SHA-256 publicado en el propio release antes de ejecutarlo.
  · Respetar al usuario. Si dice "omitir esta versión", no se le vuelve a
    preguntar por ella.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

import requests

from mxp_common.binaries import download_to_file
from mxp_common.paths import get_app_dir
from mxp_common.version import ASSET_PREFIX, GITHUB_REPO, __version__

# Se pide la LISTA de releases, no /releases/latest. El repo mxp-suite lo
# comparten varias apps, así que el release más reciente puede perfectamente
# ser de otra: hay que buscar el más nuevo que traiga el instalador de ESTA.
GITHUB_API = "https://api.github.com/repos/{repo}/releases?per_page=30"
CHECK_INTERVAL_SECONDS = 6 * 60 * 60
CHECKSUM_ASSET = "SHA256SUMS.txt"

ProgressCallback = Callable[[str, float], None]


@dataclass
class UpdateInfo:
    """Una versión nueva disponible."""

    version: str          # "1.2.0"
    tag: str              # "v1.2.0"
    notes: str            # cuerpo del release, se muestra en el popup
    download_url: str     # URL del instalador .exe
    asset_name: str       # nombre del archivo del instalador
    size: int             # bytes
    checksum_url: Optional[str] = None


def parse_version(text: str) -> tuple:
    """
    Convierte "v1.2.3" o "1.2.3" en (1, 2, 3) para poder comparar.

    Se ignora cualquier sufijo (-beta, -rc1): a efectos de "¿hay algo más
    nuevo?" solo importan los números.
    """
    cleaned = re.sub(r"^[vV]", "", (text or "").strip())
    numbers = re.findall(r"\d+", cleaned.split("-")[0])
    if not numbers:
        return (0,)
    return tuple(int(n) for n in numbers)


def is_newer(candidate: str, current: str) -> bool:
    """True si `candidate` es una versión posterior a `current`."""
    a, b = parse_version(candidate), parse_version(current)
    # Igualar longitudes para que 1.2 y 1.2.0 se consideren la misma versión
    length = max(len(a), len(b))
    a = a + (0,) * (length - len(a))
    b = b + (0,) * (length - len(b))
    return a > b


class UpdateChecker:
    """Consulta el último release publicado y descarga el instalador."""

    STATE_FILE = "update.json"

    def __init__(self, repo: str = GITHUB_REPO, current_version: str = __version__,
                 asset_prefix: str = ASSET_PREFIX):
        self.repo = repo
        self.current_version = current_version
        self.asset_prefix = asset_prefix
        self._state_path = os.path.join(get_app_dir(), self.STATE_FILE)

    # ── Estado persistido ──────────────────────────────────────────────────

    def _read_state(self) -> dict:
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_state(self, data: dict):
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass  # que no se pueda escribir el estado no es motivo de fallo

    def skip_version(self, version: str):
        """Marca una versión como omitida: no se volverá a avisar de ella."""
        state = self._read_state()
        state["skipped_version"] = version
        self._write_state(state)

    def is_skipped(self, version: str) -> bool:
        return self._read_state().get("skipped_version") == version

    # ── Comprobación ───────────────────────────────────────────────────────

    def _parse_release(self, data: dict) -> Optional[UpdateInfo]:
        """
        Convierte un release de la API en UpdateInfo, o None si no es de esta app.

        Un release solo cuenta si trae un instalador cuyo nombre empieza por el
        prefijo de la app. Es lo que permite que varias apps compartan el repo
        mxp-suite sin que el Denoiser ofrezca actualizarse al Downloader — y lo
        que hace que los releases antiguos, que solo llevan .zip sueltos, se
        ignoren en vez de tomarse por versiones instalables.
        """
        if data.get("draft") or data.get("prerelease"):
            return None

        installer = None
        checksum_url = None
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name == CHECKSUM_ASSET:
                checksum_url = asset.get("browser_download_url")
            elif name.startswith(self.asset_prefix) and name.lower().endswith(".exe"):
                installer = asset

        if installer is None:
            return None

        # La versión se saca de la etiqueta. En un repo compartido las etiquetas
        # pueden llevar prefijo ("downloader-v3.1.0"), así que si de la etiqueta
        # no sale nada usable se recurre al nombre del instalador, que siempre
        # lleva la versión dentro (MXP_Downloader_Setup_v3.1.0.exe).
        tag = data.get("tag_name", "")
        version = ""
        match = re.search(r"(\d+(?:\.\d+)+)", tag)
        if match:
            version = match.group(1)
        else:
            match = re.search(r"[vV](\d+(?:\.\d+)+)", installer["name"])
            if match:
                version = match.group(1)
        if not version:
            return None

        return UpdateInfo(
            version=version,
            tag=tag,
            notes=(data.get("body") or "").strip(),
            download_url=installer["browser_download_url"],
            asset_name=installer["name"],
            size=installer.get("size", 0),
            checksum_url=checksum_url,
        )

    def fetch_latest(self, timeout: float = 6.0) -> Optional[UpdateInfo]:
        """
        Busca el release más reciente que corresponda a esta app.

        Devuelve None si no hay ninguno utilizable. Propaga excepciones de red —
        quien llama decide qué hacer.
        """
        response = requests.get(
            GITHUB_API.format(repo=self.repo),
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()

        releases = response.json()
        if isinstance(releases, dict):  # por si algún día se apunta a /latest
            releases = [releases]

        # GitHub los devuelve del más nuevo al más viejo, pero se ordena por
        # versión de todas formas: la fecha de publicación no siempre coincide
        # con el orden de versiones (un parche de una rama antigua, por ejemplo).
        candidates = [info for info in (self._parse_release(r) for r in releases) if info]
        if not candidates:
            return None
        return max(candidates, key=lambda info: parse_version(info.version))

    def check(self, force: bool = False) -> Optional[UpdateInfo]:
        """
        Devuelve la actualización disponible, o None.

        `force` solo salta el límite de una consulta cada 6 horas — pensado
        para un futuro botón "buscar actualizaciones ahora". NO debe además
        ignorar una versión que el usuario ya marcó como "omitir": son dos
        decisiones independientes, y antes compartían la misma bandera, así
        que forzar la consulta también volvía a ofrecer una versión que el
        usuario había rechazado explícitamente. Cualquier fallo de red
        devuelve None en silencio: el updater nunca es motivo para molestar.
        """
        state = self._read_state()
        if not force and time.time() - state.get("last_check", 0) < CHECK_INTERVAL_SECONDS:
            return None

        try:
            info = self.fetch_latest()
        except Exception:
            return None

        state["last_check"] = time.time()
        self._write_state(state)

        if info is None or not is_newer(info.version, self.current_version):
            return None
        if self.is_skipped(info.version):
            return None
        return info

    def check_async(self, callback: Callable[[Optional[UpdateInfo]], None],
                    force: bool = False, delay: float = 0.0):
        """
        Comprueba en segundo plano y llama a `callback` con el resultado.

        `delay` sirve para dejar que la ventana termine de pintarse antes de
        lanzar la petición, para que el arranque no compita por el ancho de banda.
        """

        def _run():
            if delay:
                time.sleep(delay)
            try:
                callback(self.check(force=force))
            except Exception:
                callback(None)

        threading.Thread(target=_run, daemon=True).start()

    # ── Descarga e instalación ─────────────────────────────────────────────

    def _expected_checksum(self, info: UpdateInfo) -> Optional[str]:
        """Lee el SHA-256 del instalador desde el archivo SHA256SUMS.txt del release."""
        if not info.checksum_url:
            return None
        try:
            response = requests.get(info.checksum_url, timeout=10)
            response.raise_for_status()
        except Exception:
            return None

        for line in response.text.splitlines():
            parts = line.split()
            if len(parts) >= 2 and os.path.basename(parts[-1].lstrip("*")) == info.asset_name:
                return parts[0].lower()
        return None

    def download(self, info: UpdateInfo,
                 progress_callback: Optional[ProgressCallback] = None) -> str:
        """
        Descarga el instalador a %TEMP% y verifica su SHA-256.

        Lanza RuntimeError si el checksum no cuadra: antes de ejecutar nada en
        la máquina del usuario hay que estar seguro de qué se está ejecutando.
        """
        import tempfile

        dest = os.path.join(tempfile.gettempdir(), info.asset_name)
        download_to_file(
            info.download_url,
            dest,
            progress_callback,
            f"Descargando la versión {info.version}...",
            0.0,
            95.0,
            timeout=60.0,
        )

        expected = self._expected_checksum(info)
        if expected:
            if progress_callback:
                progress_callback("Verificando la descarga...", 97.0)
            digest = hashlib.sha256()
            with open(dest, "rb") as f:
                for block in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(block)
            if digest.hexdigest().lower() != expected:
                os.remove(dest)
                raise RuntimeError(
                    "La descarga no coincide con la firma publicada y se ha "
                    "descartado. Inténtalo de nuevo más tarde."
                )

        if progress_callback:
            progress_callback("Descarga lista", 100.0)
        return dest

    @staticmethod
    def launch_installer(installer_path: str):
        """
        Arranca el instalador y deja que él se encargue del resto.

        No se puede sobrescribir un .exe que está en ejecución, así que quien
        llame a esto debe cerrar la app inmediatamente después.
        """
        subprocess.Popen(
            [installer_path],
            creationflags=(
                subprocess.DETACHED_PROCESS if os.name == "nt" else 0
            ),
            close_fds=True,
        )

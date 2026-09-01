"""
Detección de aceleración por GPU para la codificación de video.

Mismo principio que ya usa mxp_common/binaries.py para ffmpeg/yt-dlp: no se
adivina si hay una GPU compatible mirando el fabricante o el modelo — se
prueba el encoder de verdad, con una codificación mínima real, y solo se
confía en el que responde. Una GPU "NVIDIA" no garantiza que NVENC esté
disponible (hay modelos de gama baja sin él, o con drivers que no lo
exponen); probar es la única forma fiable de saberlo.
"""

import json
import logging
import os
import subprocess
import time
from typing import Optional

logger = logging.getLogger("MXP")

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0

# Un encoder de GPU por familia de códec, por fabricante. Se prueban en este
# orden y se usa el primero que responda — no hace falta saber de antemano
# qué GPU tiene la máquina.
CANDIDATES = {
    "h264": ["h264_nvenc", "h264_qsv", "h264_amf"],
    "hevc": ["hevc_nvenc", "hevc_qsv", "hevc_amf"],
    "av1": ["av1_nvenc", "av1_qsv", "av1_amf"],
}

# Cómo construir los flags de calidad/velocidad para cada familia de encoder.
# Este es precisamente el motivo por el que "cambiar el nombre del códec" no
# basta: NVENC no entiende -crf, QSV no entiende -cq, etc. Cada fabricante
# tiene su propio flag de calidad y no son intercambiables.
#
# `quality` recibe el mismo CRF numérico (18-36 aprox, más alto = más
# compresión/menos calidad) que ya usaba el código para libx264/libx265, y
# cada perfil lo traduce a la escala que su encoder realmente entiende.
def _cpu_h264_h265(quality: str) -> list:
    return ["-preset", "veryfast", "-crf", quality]


def _cpu_av1(quality: str) -> list:
    # libsvtav1 no tiene -preset con nombres; usa 0 (más lento/mejor) a 13
    # (más rápido/peor). 8 es un punto medio razonable para uso interactivo.
    return ["-preset", "8", "-crf", quality]


def _nvenc(quality: str) -> list:
    return ["-preset", "p4", "-rc", "vbr", "-cq", quality]


def _qsv(quality: str) -> list:
    return ["-global_quality", quality]


def _amf(quality: str) -> list:
    return ["-quality", "balanced", "-rc", "cqp", "-q", quality]


ENCODER_PROFILES = {
    "libx264": _cpu_h264_h265,
    "libx265": _cpu_h264_h265,
    "libsvtav1": _cpu_av1,
    "h264_nvenc": _nvenc, "hevc_nvenc": _nvenc, "av1_nvenc": _nvenc,
    "h264_qsv": _qsv, "hevc_qsv": _qsv, "av1_qsv": _qsv,
    "h264_amf": _amf, "hevc_amf": _amf, "av1_amf": _amf,
}

# CPU de respaldo para cada familia — a esto se cae si la GPU falla o no hay
# ninguna disponible.
CPU_FALLBACK = {"h264": "libx264", "hevc": "libx265", "av1": "libsvtav1"}


def encoder_args(encoder: str, quality: str) -> list:
    """Flags de calidad/velocidad correctos para este encoder concreto."""
    builder = ENCODER_PROFILES.get(encoder, _cpu_h264_h265)
    return builder(quality)


def probe_encoder(ffmpeg_path: str, encoder: str, timeout: float = 5.0) -> bool:
    """
    Prueba un encoder con una codificación real, pequeña y rápida — pero real:
    si el driver, la licencia o el hardware no lo soportan, ffmpeg lo dice
    aquí y no a mitad de una conversión de verdad.

    320x240 y no algo más pequeño a propósito: se probó primero con 64x64 y
    dio un falso negativo con AMF en hardware real (Radeon RX 6700 XT) —
    "encoder->Init() failed with error 5", que no es que el encoder no exista,
    es que 64x64 está por debajo de su resolución mínima soportada. Con
    320x240 la misma máquina codifica sin problema. Un umbral tan pequeño
    habría hecho creer a la app que no hay GPU cuando sí la hay.
    """
    cmd = [
        ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=black:s=320x240:d=0.2",
        "-frames:v", "5", "-c:v", encoder,
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
        return result.returncode == 0
    except Exception:
        return False


class GpuEncoders:
    """
    Detecta y cachea qué encoders de GPU responden de verdad en esta máquina.

    El resultado se guarda en disco (mismo patrón que engine.json) para no
    volver a probar cada encoder en cada arranque — probar de verdad implica
    lanzar varios procesos ffmpeg, y aunque sean rápidos, no tiene sentido
    repetirlo si el hardware no ha cambiado.
    """

    CACHE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60  # una semana: por si se cambia de GPU

    def __init__(self, ffmpeg_path: str, cache_path: Optional[str] = None):
        self.ffmpeg_path = ffmpeg_path
        self.cache_path = cache_path
        self._working: dict = {}
        self._loaded = False

    def _load_cache(self) -> Optional[dict]:
        if not self.cache_path or not os.path.isfile(self.cache_path):
            return None
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if time.time() - data.get("probed_at", 0) > self.CACHE_MAX_AGE_SECONDS:
                return None
            if data.get("ffmpeg_path") != self.ffmpeg_path:
                return None  # otro ffmpeg (p. ej. build distinto) -> reprobar
            return data.get("working", {})
        except Exception:
            return None

    def _save_cache(self):
        if not self.cache_path:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump({
                    "ffmpeg_path": self.ffmpeg_path,
                    "probed_at": time.time(),
                    "working": self._working,
                }, f, indent=2)
        except Exception:
            pass  # el caché es una optimización, no algo por lo que fallar

    def ensure_probed(self):
        """Prueba cada candidato una vez (o reutiliza el caché reciente)."""
        if self._loaded:
            return
        self._loaded = True

        cached = self._load_cache()
        if cached is not None:
            self._working = cached
            return

        for codec, candidates in CANDIDATES.items():
            found = None
            for encoder in candidates:
                if probe_encoder(self.ffmpeg_path, encoder):
                    found = encoder
                    break
            self._working[codec] = found
            if found:
                logger.info(f"Encoder de GPU disponible para {codec}: {found}")
        self._save_cache()

    def best_encoder(self, codec: str) -> Optional[str]:
        """Nombre del encoder de GPU que respondió para este códec, o None."""
        self.ensure_probed()
        return self._working.get(codec)

    def refresh(self):
        """Fuerza una nueva ronda de pruebas (p. ej. si cambió el hardware)."""
        self._loaded = False
        self._working = {}
        self.ensure_probed()

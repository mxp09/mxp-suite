"""
Transcribe un archivo o una URL con whisper.cpp y devuelve palabras con tiempo.

Decisiones medidas (oct-2026, whisper.cpp v1.9.2):
  · Sin --vad: con VAD los tiempos de TOKEN no se remapean al audio original
    (los de segmento sí), así que los timestamps por palabra salían corridos.
  · Sin -dtw: exige desactivar flash-attention (más lento) y en las pruebas
    no mejoró los tiempos frente a los offsets de token.
"""

import json
import os
import re
import subprocess
import tempfile
import threading
from typing import Callable, Optional

from core.transcription.model import Transcript, Word
from mxp_common import transcriber
from mxp_common.binaries import FFmpegManager

ProgressCallback = Callable[[str, float], None]
_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
_PROGRESS_RE = re.compile(r"progress\s*=\s*(\d+)%")

LANGUAGES = {
    "Detectar automáticamente": "auto", "Español": "es", "English": "en", "Português": "pt",
    "Français": "fr", "Deutsch": "de", "Italiano": "it", "Català": "ca", "Nederlands": "nl",
    "Polski": "pl", "Русский": "ru", "日本語": "ja", "中文": "zh", "한국어": "ko", "العربية": "ar",
}


class Cancelled(Exception):
    pass


def _download_audio(url: str, workdir: str, progress: ProgressCallback, cancel: threading.Event) -> tuple:
    """Baja solo el audio de la URL reutilizando las opciones del descargador (cookies, Deno, reintentos)."""
    import yt_dlp
    from core.downloader import Quality, VideoDownloader, VideoResolution

    def hook(d):
        if cancel.is_set():
            raise Cancelled()
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            if total:
                progress("Descargando el audio...", d.get("downloaded_bytes", 0) * 25.0 / total)

    opts = VideoDownloader()._build_opts(Quality.AUDIO_ONLY, VideoResolution.BEST, workdir, None)
    opts.update({"format": "bestaudio/best", "postprocessors": [], "writethumbnail": False,
                 "outtmpl": os.path.join(workdir, "audio.%(ext)s"), "progress_hooks": [hook]})
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = (info.get("requested_downloads") or [{}])[0].get("filepath") or ydl.prepare_filename(info)
    return path, info.get("title") or url


def _to_wav(src: str, dst: str):
    ffmpeg = FFmpegManager().ffmpeg
    if not ffmpeg:
        raise RuntimeError("No se encontró FFmpeg.")
    result = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", src, "-vn", "-ar", "16000",
                             "-ac", "1", "-c:a", "pcm_s16le", dst],
                            capture_output=True, text=True, creationflags=_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError("No se pudo leer el audio: " + (result.stderr.strip().splitlines() or ["?"])[-1])


def parse_whisper_json(data: dict, offset: float = 0.0) -> list:
    """Tokens de whisper -> palabras. Un token con espacio inicial abre palabra nueva."""
    words = []
    for segment in data.get("transcription", []):
        for token in segment.get("tokens", []):
            text = token.get("text", "")
            if text.startswith("[_") or not text:   # [_BEG_], [_TT_123]...
                continue
            start = token["offsets"]["from"] / 1000 + offset
            end = token["offsets"]["to"] / 1000 + offset
            if text.startswith(" ") or not words:
                words.append(Word(start, end, text, token.get("p", 1.0)))
            else:
                last = words[-1]
                last.text += text
                last.end = max(last.end, end)
                last.prob = min(last.prob, token.get("p", 1.0))
    return words


def transcribe(source: str, model_key: str, language: str = "auto", translate: bool = False,
               prompt: str = "", progress: Optional[ProgressCallback] = None,
               cancel: Optional[threading.Event] = None) -> Transcript:
    progress = progress or (lambda *_: None)
    cancel = cancel or threading.Event()
    cli = transcriber.whisper_cli()
    if not cli:
        raise RuntimeError("El motor de transcripción no está instalado. Reinicia la app para repararlo.")
    model = transcriber.model_path(model_key)
    if not os.path.isfile(model):
        raise RuntimeError("Ese modelo no está descargado.")

    # ignore_cleanup_errors: en Windows un proceso recién terminado puede
    # retener el WAV un instante y el borrado no debe tapar el error real.
    with tempfile.TemporaryDirectory(prefix="mxp_tr_", ignore_cleanup_errors=True) as workdir:
        title = os.path.basename(source)
        audio_path = "" if re.match(r"https?://", source) else os.path.abspath(source)
        if re.match(r"https?://", source):
            source, title = _download_audio(source, workdir, progress, cancel)
        if cancel.is_set():
            raise Cancelled()
        progress("Preparando el audio...", 27)
        wav = os.path.join(workdir, "audio16k.wav")
        _to_wav(source, wav)
        duration = max(0.0, (os.path.getsize(wav) - 44) / 32000)

        cmd = [cli, "-m", model, "-f", wav, "-l", language, "-ojf", "-of",
               os.path.join(workdir, "out"), "-pp", "-np", "-t", str(min(8, os.cpu_count() or 4))]
        if translate:
            cmd.append("-tr")
        if prompt.strip():
            cmd += ["--prompt", prompt.strip()]
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="ignore", creationflags=_NO_WINDOW)
        tail = []
        for line in proc.stderr:
            if cancel.is_set():
                proc.kill()
                proc.wait()   # que suelte el WAV antes de borrar la carpeta temporal
                raise Cancelled()
            tail = (tail + [line.strip()])[-5:]
            match = _PROGRESS_RE.search(line)
            if match:
                progress("Transcribiendo...", 30 + int(match.group(1)) * 0.7)
        proc.wait()
        if cancel.is_set():
            raise Cancelled()
        out_json = os.path.join(workdir, "out.json")
        if proc.returncode != 0 or not os.path.isfile(out_json):
            raise RuntimeError("La transcripción falló: " + (" ".join(tail) or f"código {proc.returncode}"))
        with open(out_json, "rb") as f:
            data = json.load(f)

    words = parse_whisper_json(data)
    progress("Listo", 100)
    return Transcript(words=words, language=data.get("result", {}).get("language", language),
                      source=title, audio_path=audio_path, duration=duration)

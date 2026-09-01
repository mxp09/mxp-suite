import subprocess
import os
import re
import threading
from mxp_common.binaries import FFmpegManager
from mxp_common.paths import get_app_dir
from core import gpu

def _parse_duration_secs(duration_str):
    """Convierte HH:MM:SS.ms a segundos."""
    try:
        parts = duration_str.strip().split(":")
        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
        return h * 3600 + m * 60 + s
    except Exception:
        return None

def _run_ffmpeg_with_progress(cmd, log_callback, progress_callback):
    """
    Ejecuta ffmpeg, parsea el stderr para extraer duración total y
    tiempo actual procesado, y llama progress_callback(0-1).
    Retorna (returncode, error_lines).
    """
    total_duration = None
    error_lines = []

    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        universal_newlines=True,
        encoding="utf-8",
        errors="ignore",
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS
    )

    for line in proc.stderr:
        line = line.rstrip()
        error_lines.append(line)

        # Detectar duración total del archivo
        if total_duration is None:
            m = re.search(r"Duration:\s*([\d:\.]+)", line)
            if m:
                total_duration = _parse_duration_secs(m.group(1))

        # Detectar tiempo procesado actual
        if progress_callback and total_duration:
            m = re.search(r"time=\s*([\d:\.]+)", line)
            if m:
                current = _parse_duration_secs(m.group(1))
                if current is not None and total_duration > 0:
                    pct = min(current / total_duration, 1.0)
                    progress_callback(pct)

    proc.wait()
    return proc.returncode, error_lines


def _relevant_error(err_lines):
    """La última línea de ffmpeg que de verdad explica el fallo, si hay una."""
    relevant = [l for l in err_lines if any(k in l for k in ("Error", "error", "Invalid", "No such", "failed", "unable"))]
    return relevant[-1] if relevant else (err_lines[-1] if err_lines else "Error desconocido")


# Formato destino (tal como lo elige el usuario) -> (contenedor, códec de video).
# "MP4 (HEVC)" y "WEBM (AV1)" son las opciones nuevas; todo lo demás mantiene
# el comportamiento de siempre. Cualquier formato no listado aquí (MKV/MOV/AVI,
# o lo que el Compresor derive de la extensión de un archivo de entrada) cae al
# valor por defecto más abajo: mismo contenedor, H.264 — que es exactamente lo
# que el código ya hacía en su rama "else".
VIDEO_FORMAT_MAP = {
    "mp4": ("mp4", "h264"),
    "mp4 (hevc)": ("mp4", "hevc"),
    "webm": ("webm", "vp9"),
    "webm (av1)": ("webm", "av1"),
}

# Códec de audio que acompaña a cada códec de video. mp4/mkv/mov/avi con
# H.264/H.265 siguen llevando AAC como siempre; los contenedores WebM con
# VP9/AV1 pasan de Vorbis a Opus (mejor compresión al mismo códec "clásico"
# que la gente espera de WebM).
AUDIO_FOR_VIDEO_CODEC = {"h264": "aac", "hevc": "aac", "vp9": "libopus", "av1": "libopus"}

# Códec de CPU para cada códec de video. Es el segundo intento si la GPU no
# está disponible o falla a mitad de proceso, y el único intento para vp9
# (no hay encoder de GPU de VP9 realista en hardware de consumo).
CPU_CODEC = {"h264": "libx264", "hevc": "libx265", "av1": "libsvtav1", "vp9": "libvpx-vp9"}


class MediaEngine:
    def __init__(self):
        # Se reutiliza el mismo FFmpegManager que usa core/downloader.py: mira
        # bin/ junto al ejecutable, luego AppData, luego el PATH, y VERIFICA
        # que el binario responde antes de darlo por bueno. Antes esto solo
        # comprobaba os.path.exists() en un único sitio y, si faltaba, pasaba
        # el literal "ffmpeg" a subprocess a ciegas — si no estaba en el PATH,
        # el conversor/compresor fallaba con un FileNotFoundError sin explicar
        # por qué, y aunque estuviera, un binario corrupto no se detectaba.
        self._ffmpeg_manager = FFmpegManager()
        self.ffmpeg_path = self._ffmpeg_manager.ffmpeg or "ffmpeg"

        # Detección de GPU: se prueba una sola vez (con caché en disco) y se
        # reutiliza durante toda la vida de esta instancia. Nunca falla si no
        # hay GPU o si la detección misma da algún problema — simplemente no
        # se ofrece aceleración y todo sigue por CPU como antes.
        gpu_cache = os.path.join(get_app_dir(), "gpu.json")
        self._gpu = gpu.GpuEncoders(self.ffmpeg_path, cache_path=gpu_cache)

    def _video_codec_args(self, encoder, crf):
        """Flags de velocidad/calidad correctos para ESTE encoder concreto."""
        return gpu.encoder_args(encoder, crf)

    def _encoders_to_try(self, codec):
        """
        Lista de encoders a intentar para este códec, GPU primero si hay uno
        que respondió en la detección, CPU siempre al final como red de
        seguridad. vp9 no tiene entrada de GPU en la tabla y va directo a CPU.
        """
        attempts = []
        gpu_encoder = self._gpu.best_encoder(codec) if codec in gpu.CANDIDATES else None
        if gpu_encoder:
            attempts.append(gpu_encoder)
        cpu_encoder = CPU_CODEC.get(codec, "libx264")
        if cpu_encoder not in attempts:
            attempts.append(cpu_encoder)
        return attempts

    def process_video(self, input_path, target_format, output_dir=None, compression="Ninguno", log_callback=print, progress_callback=None):
        key = target_format.strip().lower()
        container, codec = VIDEO_FORMAT_MAP.get(key, (key, "h264"))

        base_name = os.path.splitext(os.path.basename(input_path))[0]
        if output_dir:
            output_path = os.path.join(output_dir, f"{base_name}_compressed.{container}")
        else:
            output_path = os.path.splitext(input_path)[0] + f"_compressed.{container}"

        # Parámetros de compresión (igual que antes)
        crf = "22"
        scale_filter = None
        if compression == "Media (Buena Calidad)":
            crf = "28"
        elif compression == "Alta (Para Redes Sociales)":
            crf = "32"
            scale_filter = "scale='min(1280,iw)':-2"
        elif compression == "Extrema":
            crf = "36"
            scale_filter = "scale='min(854,iw)':-2"  # Reducir a max 480p de ancho para compresión extrema

        audio_codec = AUDIO_FOR_VIDEO_CODEC.get(codec, "aac")
        audio_args = ["-c:a", audio_codec] + (["-b:a", "128k"] if audio_codec == "aac" else [])

        encoders = self._encoders_to_try(codec)
        try:
            log_callback(f"[VIDEO] Procesando {os.path.basename(input_path)} → {target_format.upper()} (Preset: {compression})...")

            last_detail = "Error desconocido"
            for attempt_num, encoder in enumerate(encoders):
                cmd = [self.ffmpeg_path, "-y", "-i", input_path, "-c:v", encoder]
                cmd.extend(self._video_codec_args(encoder, crf))
                if scale_filter:
                    cmd.extend(["-vf", scale_filter])
                cmd.extend(audio_args)
                cmd.append(output_path)

                rc, err_lines = _run_ffmpeg_with_progress(cmd, log_callback, progress_callback)
                if rc == 0:
                    if attempt_num > 0:
                        log_callback(f"[GPU] {encoders[0]} falló; completado por CPU ({encoder}).")
                    log_callback(f"[✓ Éxito] Generado: {os.path.basename(output_path)}")
                    return output_path

                last_detail = _relevant_error(err_lines)
                if attempt_num < len(encoders) - 1:
                    log_callback(f"[GPU] {encoder} falló (código {rc}): {last_detail} — reintentando por CPU...")

            log_callback(f"[✗ Error] FFmpeg falló (código {rc}): {last_detail}")
            return None
        except FileNotFoundError:
            log_callback("[✗ Error] FFmpeg no encontrado. Verifica que los binarios estén instalados.")
            return None
        except Exception as e:
            log_callback(f"[✗ Error] Excepción inesperada al procesar video: {e}")
            return None

    def process_audio(self, input_path, target_format, output_dir=None, log_callback=print, bitrate=None, progress_callback=None):
        output_format = target_format.lower()
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        if output_dir:
            output_path = os.path.join(output_dir, f"{base_name}_compressed.{output_format}")
        else:
            output_path = os.path.splitext(input_path)[0] + f"_compressed.{output_format}"

        cmd = [self.ffmpeg_path, "-y", "-i", input_path]

        # Cada formato lleva su códec explícito. Antes "m4a", "ogg" y "aac"
        # caían al `else` genérico (solo -b:a, sin -c:a): ffmpeg adivinaba el
        # códec por la extensión del contenedor de salida, lo cual funcionaba
        # por casualidad más que por diseño — y el selector de archivos del
        # Compresor (gui/components.py) ya promete aceptar los tres.
        if output_format == "mp3":
            cmd.extend(["-c:a", "libmp3lame", "-b:a", bitrate or "320k"])
        elif output_format == "wav":
            cmd.extend(["-c:a", "pcm_s16le"])
        elif output_format == "flac":
            cmd.extend(["-c:a", "flac"])
        elif output_format in ("m4a", "aac"):
            cmd.extend(["-c:a", "aac", "-b:a", bitrate or "192k"])
        elif output_format == "ogg":
            cmd.extend(["-c:a", "libopus", "-b:a", bitrate or "192k"])
        else:
            cmd.extend(["-b:a", bitrate or "192k"])

        cmd.append(output_path)

        try:
            log_callback(f"[AUDIO] Procesando {os.path.basename(input_path)} → {target_format.upper()} (Bitrate: {bitrate or 'Original'})...")
            rc, err_lines = _run_ffmpeg_with_progress(cmd, log_callback, progress_callback)
            if rc == 0:
                log_callback(f"[✓ Éxito] Generado: {os.path.basename(output_path)}")
                return output_path
            else:
                detail = _relevant_error(err_lines)
                log_callback(f"[✗ Error] FFmpeg falló (código {rc}): {detail}")
                return None
        except FileNotFoundError:
            log_callback("[✗ Error] FFmpeg no encontrado. Verifica que los binarios estén instalados.")
            return None
        except Exception as e:
            log_callback(f"[✗ Error] Excepción inesperada al procesar audio: {e}")
            return None

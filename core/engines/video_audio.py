import subprocess
import os
import re
import threading
from core.utils import get_bin_dir

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


class MediaEngine:
    def __init__(self):
        # Buscar ffmpeg en el bin_dir local o en el PATH
        bin_dir = get_bin_dir()
        self.ffmpeg_path = os.path.join(bin_dir, "ffmpeg.exe")
        
        import shutil
        if not os.path.exists(self.ffmpeg_path):
            self.ffmpeg_path = shutil.which("ffmpeg") or "ffmpeg"

    def process_video(self, input_path, target_format, output_dir=None, compression="Ninguno", log_callback=print, progress_callback=None):
        output_format = target_format.lower()
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        if output_dir:
            output_path = os.path.join(output_dir, f"{base_name}_compressed.{output_format}")
        else:
            output_path = os.path.splitext(input_path)[0] + f"_compressed.{output_format}"
        
        cmd = [self.ffmpeg_path, "-y", "-i", input_path]
        
        # Parámetros de compresión
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
            
        if output_format == "mp4":
            cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", crf])
            if scale_filter:
                cmd.extend(["-vf", scale_filter])
            cmd.extend(["-c:a", "aac", "-b:a", "128k"])
        elif output_format == "webm":
            b_v = "1M" if compression == "Ninguno" else ("600k" if compression == "Media (Buena Calidad)" else "300k")
            cmd.extend(["-c:v", "libvpx", "-b:v", b_v, "-c:a", "libvorbis"])
            if scale_filter:
                cmd.extend(["-vf", scale_filter])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", crf])
            if scale_filter:
                cmd.extend(["-vf", scale_filter])
            cmd.extend(["-c:a", "aac"])
            
        cmd.append(output_path)
        
        try:
            log_callback(f"[VIDEO] Procesando {os.path.basename(input_path)} → {target_format.upper()} (Preset: {compression})...")
            rc, err_lines = _run_ffmpeg_with_progress(cmd, log_callback, progress_callback)
            if rc == 0:
                log_callback(f"[✓ Éxito] Generado: {os.path.basename(output_path)}")
                return output_path
            else:
                # Filtrar y mostrar las líneas de error útiles de ffmpeg
                relevant = [l for l in err_lines if any(k in l for k in ("Error", "error", "Invalid", "No such", "failed", "unable"))]
                detail = relevant[-1] if relevant else (err_lines[-1] if err_lines else "Error desconocido")
                log_callback(f"[✗ Error] FFmpeg falló (código {rc}): {detail}")
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
        
        if output_format == "mp3":
            cmd.extend(["-b:a", bitrate or "320k"])
        elif output_format == "wav":
            cmd.extend(["-c:a", "pcm_s16le"])
        elif output_format == "flac":
            cmd.extend(["-c:a", "flac"])
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
                relevant = [l for l in err_lines if any(k in l for k in ("Error", "error", "Invalid", "No such", "failed", "unable"))]
                detail = relevant[-1] if relevant else (err_lines[-1] if err_lines else "Error desconocido")
                log_callback(f"[✗ Error] FFmpeg falló (código {rc}): {detail}")
                return None
        except FileNotFoundError:
            log_callback("[✗ Error] FFmpeg no encontrado. Verifica que los binarios estén instalados.")
            return None
        except Exception as e:
            log_callback(f"[✗ Error] Excepción inesperada al procesar audio: {e}")
            return None

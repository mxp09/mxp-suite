"""
Instalación de dependencias sin interfaz, para que la use el instalador.

El reparto de trabajo con Inno Setup es deliberado: Inno descarga los archivos
(tiene una página de progreso nativa con velocidad y tiempo restante) y este
módulo los instala y los verifica. Así no hay dos implementaciones de descarga
que puedan divergir, y la verificación —ejecutar el binario y comprobar que
responde— es exactamente la misma que usa la app en tiempo de ejecución.

Se invoca desde el ejecutable congelado:

    "MXP Downloader.exe" --setup-deps --ffmpeg-zip <ruta> --ytdlp-wheel <ruta>

Código de salida 0 si todo quedó listo, 1 si no. El instalador lo comprueba y
no deja terminar en verde con las dependencias a medias, que es exactamente lo
que dejaba a la gente con una app instalada que no funcionaba.
"""

import logging
import os
import shutil
import sys
import traceback
import zipfile

from mxp_common.binaries import DenoManager, EngineManager, FFmpegManager
from mxp_common.paths import get_bin_dir, get_engine_dir

_logger = logging.getLogger("MXP")


def _log(message: str):
    """
    Una línea por paso. El instalador la recoge si necesita mostrarla.

    Va al logger de archivo (setup_logging() ya se ejecutó antes de llegar
    aquí, desde el punto de entrada) Y a stdout si lo hay. Solo con print()
    esto se perdía en silencio: cuando Inno Setup lanza el .exe con Exec()
    (en vez de un terminal), el proceso hijo no tiene un stdout válido al que
    escribir — que es precisamente el caso que más importa depurar, porque es
    la instalación real y desatendida, no una prueba manual en consola.
    """
    _logger.info(message)
    try:
        if sys.stdout is not None:
            print(message, flush=True)
    except Exception:
        pass


def _log_exception(message: str):
    """Como _log(), pero incluyendo el traceback completo en el archivo de log."""
    _logger.error(message, exc_info=True)
    try:
        if sys.stdout is not None:
            print(f"{message}\n{traceback.format_exc()}", flush=True)
    except Exception:
        pass


def install_ffmpeg_from_zip(zip_path: str) -> bool:
    """Extrae ffmpeg.exe y ffprobe.exe de un zip ya descargado."""
    bin_dir = get_bin_dir()
    wanted = {"ffmpeg.exe", "ffprobe.exe"}
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                name = os.path.basename(member)
                if name in wanted:
                    target = os.path.join(bin_dir, name)
                    tmp = target + ".part"
                    with archive.open(member) as src, open(tmp, "wb") as out:
                        shutil.copyfileobj(src, out)
                    os.replace(tmp, target)
    except Exception as exc:
        _log(f"ERROR extrayendo FFmpeg: {exc}")
        return False
    return True


def install_engine_from_wheel(wheel_path: str) -> bool:
    """Instala el paquete yt_dlp desde un wheel ya descargado."""
    engine_dir = get_engine_dir()
    staging = os.path.join(engine_dir, ".staging")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        with zipfile.ZipFile(wheel_path) as archive:
            archive.extractall(staging)
        staged = os.path.join(staging, "yt_dlp")
        if not os.path.isdir(staged):
            _log("ERROR: el wheel no contiene el paquete yt_dlp")
            return False

        final = os.path.join(engine_dir, "yt_dlp")
        shutil.rmtree(final, ignore_errors=True)
        os.replace(staged, final)
    except Exception as exc:
        _log(f"ERROR instalando el motor: {exc}")
        return False
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    # Sellar la versión leyéndola del nombre del wheel (yt_dlp-2026.8.19-...)
    version = "desconocida"
    parts = os.path.basename(wheel_path).split("-")
    if len(parts) > 1:
        version = parts[1]
    EngineManager()._write_stamp({"version": version, "last_check": 0})
    return True


def run_setup(ffmpeg_zip=None, ytdlp_wheel=None, need_engine=True,
              whisper_zip=None, whisper_models=None, result_file=None) -> int:
    """
    Deja las dependencias listas y verificadas.

    Los archivos ya descargados se usan si se pasan; si no, se descargan aquí.
    Ese segundo camino es la red de seguridad para cuando la descarga del
    instalador falla: la app puede repetir el proceso ella sola al arrancar.
    """
    ok = True
    # Lo que falta, en palabras que el instalador le enseña al usuario.
    problems = []

    # ── FFmpeg ──
    ffmpeg = FFmpegManager()
    if ffmpeg.is_ready():
        _log("FFmpeg ya estaba instalado y responde.")
    else:
        if ffmpeg_zip and os.path.isfile(ffmpeg_zip):
            _log("Instalando FFmpeg...")
            install_ffmpeg_from_zip(ffmpeg_zip)
            ffmpeg.refresh()
        if not ffmpeg.is_ready():
            _log("Descargando FFmpeg...")
            try:
                ffmpeg.ensure()
            except Exception as exc:
                _log(f"ERROR descargando FFmpeg: {exc}")

        # No basta con que el archivo exista: se ejecuta para comprobarlo.
        if ffmpeg.is_ready():
            _log("FFmpeg verificado.")
        else:
            _log("ERROR: FFmpeg no quedó utilizable.")
            problems.append("FFmpeg (conversión de video y audio)")
            ok = False

    # ── Motor yt-dlp ──
    if need_engine:
        engine = EngineManager()
        if engine.is_installed():
            _log(f"Motor yt-dlp ya instalado ({engine.installed_version()}).")
        else:
            if ytdlp_wheel and os.path.isfile(ytdlp_wheel):
                _log("Instalando el motor de descarga...")
                install_engine_from_wheel(ytdlp_wheel)
            if not engine.is_installed():
                _log("Descargando el motor de descarga...")
                try:
                    engine.ensure()
                except Exception as exc:
                    _log(f"ERROR descargando el motor: {exc}")

            if engine.is_installed():
                _log(f"Motor yt-dlp verificado ({engine.installed_version()}).")
            else:
                _log("ERROR: el motor de descarga no quedó utilizable.")
                problems.append("Motor de descarga (yt-dlp)")
                ok = False

        # ── Deno (runtime JS que YouTube exige a yt-dlp) ──
        deno = DenoManager()
        try:
            deno.ensure()
        except Exception as exc:
            _log(f"ERROR descargando Deno: {exc}")
        if deno.is_ready():
            _log("Deno verificado.")
        else:
            _log("ERROR: Deno no quedó utilizable.")
            problems.append("Deno (necesario para YouTube)")
            ok = False

        # ── Impersonación (curl_cffi): el reintento tras un 403 la necesita ──
        try:
            import yt_dlp.networking._curlcffi  # noqa: F401
            _log("Impersonación de navegador verificada.")
        except Exception as exc:
            _log(f"ERROR: impersonación no disponible: {exc}")
            problems.append("Impersonación de navegador (curl_cffi)")
            ok = False

    # ── Transcripción: motor whisper.cpp + modelos elegidos en el instalador ──
    ok = setup_transcription(whisper_zip, whisper_models or [], problems) and ok

    _log("LISTO" if ok else "INCOMPLETO")
    if result_file:
        try:
            # utf-8-sig: Inno Setup solo decodifica bien los acentos con BOM.
            with open(result_file, "w", encoding="utf-8-sig") as f:
                f.write("OK\n" if ok else "\n".join(problems) + "\n")
        except Exception:
            _log_exception("No se pudo escribir el resultado para el instalador")
    return 0 if ok else 1


def setup_transcription(whisper_zip, whisper_models, problems=None) -> bool:
    """
    `whisper_models` son pares "clave=ruta" de lo que bajó el instalador. Si un
    archivo falta o no cuadra su hash, se descarga aquí: el instalador no
    termina en verde sin el motor y TODOS los modelos pedidos funcionando.
    """
    from mxp_common import transcriber

    if problems is None:
        problems = []
    ok = True
    if not transcriber.whisper_cli():
        try:
            if whisper_zip and os.path.isfile(whisper_zip):
                _log("Instalando el motor de transcripción...")
                with open(whisper_zip, "rb") as f:
                    transcriber.install_engine_from_zip(f.read())
            if not transcriber.whisper_cli():
                _log("Descargando el motor de transcripción...")
                transcriber.ensure_engine()
        except Exception as exc:
            _log(f"ERROR instalando el motor de transcripción: {exc}")
    if transcriber.whisper_cli():
        _log("Motor de transcripción verificado.")
    else:
        reason = transcriber.diagnose_engine()
        _log(f"ERROR: el motor de transcripción no quedó utilizable: {reason}")
        problems.append(f"Motor de transcripción ({reason})")
        ok = False

    for pair in whisper_models:
        key, _, path = pair.partition("=")
        if key not in transcriber.MODELS:
            _log(f"Modelo desconocido ignorado: {key}")
            continue
        if key in transcriber.installed_models():
            _log(f"Modelo {key} ya instalado.")
            continue
        try:
            if path and os.path.isfile(path) and transcriber.install_model_file(key, path):
                _log(f"Modelo {key} instalado y verificado.")
                continue
            _log(f"Descargando el modelo {key}...")
            transcriber.download_model(key)
        except Exception as exc:
            _log(f"ERROR con el modelo {key}: {exc}")
        if key not in transcriber.installed_models():
            _log(f"ERROR: el modelo {key} no quedó instalado.")
            problems.append(f"Modelo de transcripción {key}")
            ok = False
    return ok


def maybe_run_from_argv(need_engine=True):
    """
    Atiende `--setup-deps` si viene en la línea de comandos.

    Devuelve True si actuó como instalador (y el llamante debe salir sin abrir
    la ventana), False si es un arranque normal de la app.
    """
    if "--setup-deps" not in sys.argv:
        return False

    def arg(name):
        if name in sys.argv:
            index = sys.argv.index(name) + 1
            if index < len(sys.argv):
                return sys.argv[index]
        return None

    sys.exit(run_setup(
        ffmpeg_zip=arg("--ffmpeg-zip"),
        ytdlp_wheel=arg("--ytdlp-wheel"),
        need_engine=need_engine,
        whisper_zip=arg("--whisper-zip"),
        whisper_models=[sys.argv[i + 1] for i, a in enumerate(sys.argv[:-1]) if a == "--whisper-model"],
        result_file=arg("--result-file"),
    ))

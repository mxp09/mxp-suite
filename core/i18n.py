"""
Módulo de internacionalización (i18n) para MXP Suite.
Permite alternar entre Español e Inglés con persistencia en config.json.
"""

import os
import json

# Nombre del archivo de configuración para portabilidad
CONFIG_FILE = "config.json"

# Idioma predeterminado
_current_language = "es"

# Diccionario de traducciones
TRANSLATIONS = {
    "es": {
        "app_title": "MXP Suite",
        "app_subtitle": "Descarga multimedia con máxima fidelidad",
        "downloader_tab": "📥 Descargador",
        "converter_tab": "🔄 Conversor",
        "compressor_tab": "🗜 Compresor",
        "history_tab": "📜 Historial",
        
        # URL Input Frame
        "url_label": "URL del video",
        "url_placeholder": "Pega aquí la URL del video...",
        "btn_paste": "📋 Pegar",
        
        # Details Frame
        "details_title": "Detalles del Video",
        "video_title": "Título:",
        "video_duration": "Duración:",
        "video_channel": "Canal:",
        "video_views": "Vistas:",
        "video_published": "Publicado:",
        
        # Quality Frame
        "quality_title": "Opciones de Calidad",
        "quality_desc": "Selecciona la calidad deseada:",
        "format_label": "Formato:",
        "format_both": "Video + Audio (Fusión)",
        "format_audio": "Solo Audio (Conversión MP3)",
        "res_label": "Resolución máxima:",
        "res_best": "Mejor Disponible",
        
        # Output Folder Frame
        "output_title": "Carpeta de Destino",
        "save_label": "Guardar en:",
        "btn_browse": "🔎 Buscar...",
        "btn_open_folder": "Abrir carpeta",
        
        # Trimming Frame
        "trim_title": "Recortar Video (Opcional)",
        "trim_desc": "Habilita la barra para definir un fragmento de tiempo específico:",
        "trim_enable": "Recortar fragmento de video",
        "trim_start": "Inicio:",
        "trim_end": "Fin:",
        "trim_full": "Completo",
        "trim_disabled_msg": "⚠️ No se puede recortar: Duración del video desconocida",
        
        # Cookie Frame
        "cookie_title": "Cookies de Navegador (Opcional)",
        "cookie_desc": "Carga tus cookies para descargar videos privados o con restricción de edad:",
        "cookie_enable": "Usar cookies del navegador",
        
        # Download Button Frame
        "btn_download_now": "Descargar ahora",
        "btn_waiting_link": "Esperando enlace...",
        "btn_fetching_info": "Obteniendo información...",
        "btn_error_info": "Error al obtener info",
        
        # Progress Panel Frame
        "panel_active_downloads": "Descargas Activas",
        "panel_work_queue": "Cola de Trabajos",
        "panel_speed": "Velocidad:",
        "panel_remaining": "Restante:",
        "status_waiting": "Esperando en cola...",
        "status_finished": "Finalizado",
        "status_canceled": "Cancelado",
        "status_error": "Error",
        "status_processing": "Procesando...",
        "status_downloading": "Descargando...",
        "status_extracting": "Extrayendo audio...",
        "status_merging": "Fusionando pistas...",
        
        # Converter Panel Frame
        "conv_title": "MXP Converter (Conversión de Medios)",
        "conv_drag_drop": "Arrastra tus archivos aquí o haz clic en Buscar",
        "btn_conv_browse": "Buscar Archivos",
        "conv_cat_label": "Categoría de Archivos:",
        "conv_fmt_label": "Formato de Salida:",
        "btn_conv_start": "Iniciar Conversión",
        "conv_history_title": "Conversiones en Curso / Completadas",
        "conv_empty_history": "Historial vacío. Agrega archivos para comenzar.",
        "conv_status_ready": "Listo para convertir",
        "conv_status_done": "Completado",
        "conv_status_err": "Error en proceso",
        
        # Categories and Formats
        "cat_audio": "Audio",
        "cat_video": "Video",
        "cat_image": "Imagen",
        "cat_pdf": "Documentos (PDF)",
        
        # Compressor Panel Frame
        "comp_title": "MXP Compressor (Compresión de Medios)",
        "comp_level_label": "Nivel de Compresión:",
        "comp_level_med": "Media (Buen balance)",
        "comp_level_high": "Alta (WhatsApp/Discord)",
        "comp_level_ext": "Extrema (Ahorro del 90%)",
        "btn_comp_start": "Iniciar Compresión",
        "comp_history_title": "Compresiones en Curso / Completadas",
        "comp_status_ready": "Listo para comprimir",
        "comp_saving": "Ahorro",
        
        # Setup Progress Overlay
        "setup_environment": "Configurando entorno de la aplicación...",
        
        # History Window
        "hist_window_title": "Historial de Descargas",
        "hist_empty": "No hay descargas registradas.",
        "btn_hist_clear": "Limpiar Historial",
        
        # General Dialogs / Messages
        "dialog_alert": "Atención",
        "dialog_success": "Éxito",
        "dialog_error": "Error",
        "msg_invalid_url": "⚠️ La URL ingresada no es válida. Por favor verifica el enlace.",
        "msg_download_success": "¡Descarga completada con éxito!",
        "msg_download_error": "Ocurrió un error al descargar el video.",
        "msg_select_files_first": "Por favor, agrega archivos a la lista primero.",
        "msg_binaries_error": "Error al inicializar los componentes del sistema (FFmpeg). Descargas limitadas.",
        "msg_video_not_available": "⚠️ No se pudo obtener información de este video. Verifica que sea público y exista.",
    },
    "en": {
        "app_title": "MXP Suite",
        "app_subtitle": "Media download with maximum fidelity",
        "downloader_tab": "📥 Downloader",
        "converter_tab": "🔄 Converter",
        "compressor_tab": "🗜 Compressor",
        "history_tab": "📜 History",
        
        # URL Input Frame
        "url_label": "Video URL",
        "url_placeholder": "Paste video URL here...",
        "btn_paste": "📋 Paste",
        
        # Details Frame
        "details_title": "Video Details",
        "video_title": "Title:",
        "video_duration": "Duration:",
        "video_channel": "Channel:",
        "video_views": "Views:",
        "video_published": "Published:",
        
        # Quality Frame
        "quality_title": "Quality Options",
        "quality_desc": "Select desired quality:",
        "format_label": "Format:",
        "format_both": "Video + Audio (Merged)",
        "format_audio": "Audio Only (MP3 Conversion)",
        "res_label": "Max resolution:",
        "res_best": "Best Available",
        
        # Output Folder Frame
        "output_title": "Destination Folder",
        "save_label": "Save to:",
        "btn_browse": "🔎 Browse...",
        "btn_open_folder": "Open folder",
        
        # Trimming Frame
        "trim_title": "Trim Video (Optional)",
        "trim_desc": "Enable the bar to define a specific time fragment:",
        "trim_enable": "Trim video fragment",
        "trim_start": "Start:",
        "trim_end": "End:",
        "trim_full": "Full Length",
        "trim_disabled_msg": "⚠️ Cannot trim: Unknown video duration",
        
        # Cookie Frame
        "cookie_title": "Browser Cookies (Optional)",
        "cookie_desc": "Load your cookies to download private or age-restricted videos:",
        "cookie_enable": "Use browser cookies",
        
        # Download Button Frame
        "btn_download_now": "Download now",
        "btn_waiting_link": "Waiting for link...",
        "btn_fetching_info": "Fetching info...",
        "btn_error_info": "Error fetching info",
        
        # Progress Panel Frame
        "panel_active_downloads": "Active Downloads",
        "panel_work_queue": "Work Queue",
        "panel_speed": "Speed:",
        "panel_remaining": "Remaining:",
        "status_waiting": "Waiting in queue...",
        "status_finished": "Finished",
        "status_canceled": "Canceled",
        "status_error": "Error",
        "status_processing": "Processing...",
        "status_downloading": "Downloading...",
        "status_extracting": "Extracting audio...",
        "status_merging": "Merging tracks...",
        
        # Converter Panel Frame
        "conv_title": "MXP Converter (Media Conversion)",
        "conv_drag_drop": "Drag your files here or click Browse",
        "btn_conv_browse": "Browse Files",
        "conv_cat_label": "File Category:",
        "conv_fmt_label": "Output Format:",
        "btn_conv_start": "Start Conversion",
        "conv_history_title": "Conversions in Progress / Completed",
        "conv_empty_history": "History empty. Add files to start.",
        "conv_status_ready": "Ready to convert",
        "conv_status_done": "Completed",
        "conv_status_err": "Error in process",
        
        # Categories and Formats
        "cat_audio": "Audio",
        "cat_video": "Video",
        "cat_image": "Image",
        "cat_pdf": "Documents (PDF)",
        
        # Compressor Panel Frame
        "comp_title": "MXP Compressor (Media Compression)",
        "comp_level_label": "Compression Level:",
        "comp_level_med": "Medium (Good balance)",
        "comp_level_high": "High (WhatsApp/Discord)",
        "comp_level_ext": "Extreme (90% Saving)",
        "btn_comp_start": "Start Compression",
        "comp_history_title": "Compressions in Progress / Completed",
        "comp_status_ready": "Ready to compress",
        "comp_saving": "Saving",
        
        # Setup Progress Overlay
        "setup_environment": "Setting up application environment...",
        
        # History Window
        "hist_window_title": "Download History",
        "hist_empty": "No downloads recorded.",
        "btn_hist_clear": "Clear History",
        
        # General Dialogs / Messages
        "dialog_alert": "Attention",
        "dialog_success": "Success",
        "dialog_error": "Error",
        "msg_invalid_url": "⚠️ The entered URL is invalid. Please verify the link.",
        "msg_download_success": "Download completed successfully!",
        "msg_download_error": "An error occurred while downloading the video.",
        "msg_select_files_first": "Please, add files to the list first.",
        "msg_binaries_error": "Error initializing system components (FFmpeg). Downloads limited.",
        "msg_video_not_available": "⚠️ Could not fetch info for this video. Verify that it is public and exists.",
    }
}

def load_config_language():
    """Carga el idioma desde el archivo config.json."""
    global _current_language
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _current_language = data.get("language", "es")
    except Exception:
        _current_language = "es"
    return _current_language

def save_config_language(lang):
    """Guarda el idioma en el archivo config.json."""
    global _current_language
    _current_language = lang
    try:
        data = {}
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except Exception:
                    data = {}
        data["language"] = lang
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass

def get_current_language():
    """Retorna el idioma actual."""
    return _current_language

def _(key):
    """Retorna el texto traducido correspondiente a la clave en el idioma activo."""
    lang = _current_language
    return TRANSLATIONS.get(lang, TRANSLATIONS["es"]).get(key, TRANSLATIONS["es"].get(key, key))

# Inicializar cargando el idioma guardado
load_config_language()

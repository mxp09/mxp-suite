"""
Tema visual y constantes de diseño para la aplicación.
Paleta oscura premium con acentos en gradiente cyan-purple.
"""


# ─── Paleta de colores ──────────────────────────────────────────────────────────

class Colors:
    # Fondos principales (Negro Mate y Gris Carbón)
    BG_DARK = "#000000"          # Fondo principal (negro puro)
    BG_SECONDARY = "#0F0F0F"     # Paneles / tarjetas
    BG_TERTIARY = "#1A1A1A"      # Elevación secundaria
    BG_INPUT = "#000000"         # Fondo de inputs
    BG_HOVER = "#1F1F1F"         # Hover sobre elementos

    # Bordes (Sutiles y oscuros)
    BORDER = "#1A1A1A"           # Bordes muy discretos
    BORDER_LIGHT = "#2A2A2A"     # Bordes de inputs

    # Texto (Blanco roto para evitar fatiga)
    TEXT_PRIMARY = "#F2F2F2"     # Texto principal
    TEXT_SECONDARY = "#A0A0A0"   # Texto secundario
    TEXT_MUTED = "#666666"       # Texto tenue
    TEXT_LINK = "#FFE600"        # Enlaces (Amarillo)

    # Acentos — Amarillo / Oro Minimalista
    ACCENT_YELLOW = "#FFE600"    # Amarillo principal
    ACCENT_GOLD = "#D4BF00"      # Oro oscuro
    ACCENT_PRIMARY = "#FFE600"   # Acento principal (botones)

    # Estado
    SUCCESS = "#2ECC71"          # Verde éxito
    ERROR = "#E74C3C"            # Rojo error
    WARNING = "#F1C40F"          # Amarillo advertencia
    INFO = "#3498DB"             # Azul info

    # Plataformas (mantener colores originales pero sutiles)
    YOUTUBE_RED = "#FF0000"
    TIKTOK_CYAN = "#00F2EA"
    INSTAGRAM_PINK = "#E1306C"
    FACEBOOK_BLUE = "#1877F2"

    # Botón de descarga (Degradado muy sutil)
    BUTTON_GRADIENT_START = "#FFE600"
    BUTTON_GRADIENT_END = "#D4BF00"
    BUTTON_HOVER = "#FFF04D"
    BUTTON_ACTIVE = "#B3A200"
    BUTTON_DISABLED = "#1A1A1A"
    BUTTON_TEXT = "#000000"      # Texto negro sobre amarillo

    # Progress bar
    PROGRESS_BG = "#1A1A1A"
    PROGRESS_FILL = "#FFE600"


# ─── Plataforma → Color ────────────────────────────────────────────────────────

PLATFORM_COLORS = {
    "YouTube": Colors.YOUTUBE_RED,
    "TikTok": Colors.TIKTOK_CYAN,
    "Instagram": Colors.INSTAGRAM_PINK,
    "Facebook": Colors.FACEBOOK_BLUE,
    "X": Colors.TEXT_PRIMARY,
    "Desconocido": Colors.TEXT_SECONDARY,
}


# ─── Tipografía ─────────────────────────────────────────────────────────────────

class Fonts:
    # Familias (se intentan en orden, fallback a sans-serif del sistema)
    FAMILY = "Segoe UI"
    FAMILY_MONO = "Cascadia Code"

    # Tamaños
    SIZE_HERO = 28
    SIZE_TITLE = 20
    SIZE_SUBTITLE = 16
    SIZE_BODY = 14
    SIZE_SMALL = 12
    SIZE_TINY = 10


# ─── Espaciado ──────────────────────────────────────────────────────────────────

class Spacing:
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24
    XXL = 32


# ─── Bordes redondeados ────────────────────────────────────────────────────────

class Radius:
    SM = 6
    MD = 10
    LG = 14
    XL = 20
    PILL = 50


# ─── Dimensiones de ventana ────────────────────────────────────────────────────

class Window:
    WIDTH = 900
    HEIGHT = 680
    MIN_WIDTH = 750
    MIN_HEIGHT = 580

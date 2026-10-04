"""
Iconos vectoriales (Tabler, MIT) en lugar de emojis.

Los emojis se dibujan distinto en cada versión de Windows (y a veces ni se
ven); estos PNG blancos se tiñen al color pedido y se cachean.
"""

from functools import lru_cache

import customtkinter as ctk
from PIL import Image

from core.utils import get_resource_path


@lru_cache(maxsize=256)
def icon(name: str, color: str = "#F2F2F2", size: int = 18) -> ctk.CTkImage:
    """CTkImage del icono `name` (assets/icons/<name>.png) teñido a `color`."""
    mask = Image.open(get_resource_path(f"assets/icons/{name}.png")).getchannel("A")
    tinted = Image.new("RGBA", mask.size, color)
    tinted.putalpha(mask)
    return ctk.CTkImage(light_image=tinted, dark_image=tinted, size=(size, size))

"""
Piezas del diseño "Studio" (v3.2): barra lateral, cabecera de página, chips
y tarjetas seleccionables. Todo con la paleta de siempre (negro + amarillo).
"""

from typing import Callable

import customtkinter as ctk

from gui.icons import icon
from gui.theme import Colors, Fonts, Radius, Spacing, Window


class Sidebar(ctk.CTkFrame):
    """Navegación principal: icono + texto, la página activa en amarillo."""

    def __init__(self, master, items, on_select: Callable[[str], None], footer: str = ""):
        super().__init__(master, width=Window.SIDEBAR_WIDTH, fg_color=Colors.BG_SIDEBAR, corner_radius=0)
        self.pack_propagate(False)
        self._on_select = on_select
        self._buttons = {}
        self._icons = {}

        brand = ctk.CTkFrame(self, fg_color="transparent")
        brand.pack(fill="x", padx=Spacing.LG, pady=(Spacing.XL, Spacing.XL))
        ctk.CTkLabel(brand, text="M", width=30, height=30, corner_radius=8,
                     fg_color=Colors.ACCENT_YELLOW, text_color=Colors.BUTTON_TEXT,
                     font=(Fonts.FAMILY, 14, "bold")).pack(side="left")
        ctk.CTkLabel(brand, text="MXP Suite", text_color=Colors.TEXT_PRIMARY,
                     font=(Fonts.FAMILY, 15, "bold")).pack(side="left", padx=(Spacing.SM, 0))

        for key, label, icon_name, badge in items:
            self._icons[key] = icon_name
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", padx=Spacing.SM, pady=2)
            btn = ctk.CTkButton(
                row, text=f"  {label}", anchor="w", height=38, corner_radius=Radius.MD,
                font=(Fonts.FAMILY, Fonts.SIZE_BODY), fg_color="transparent",
                hover_color=Colors.BG_HOVER, text_color=Colors.TEXT_SECONDARY,
                image=icon(icon_name, Colors.TEXT_SECONDARY),
                command=lambda k=key: self._on_select(k),
            )
            btn.pack(fill="x")
            if badge:
                ctk.CTkLabel(row, text=badge, height=18, corner_radius=4,
                             fg_color=Colors.ACCENT_YELLOW, text_color=Colors.BUTTON_TEXT,
                             font=(Fonts.FAMILY, Fonts.SIZE_TINY, "bold")).place(relx=1.0, x=-8, rely=0.5, anchor="e")
            self._buttons[key] = btn

        ctk.CTkLabel(self, text=footer, text_color=Colors.TEXT_MUTED, justify="left",
                     font=(Fonts.FAMILY, Fonts.SIZE_TINY)).pack(side="bottom", anchor="w",
                                                              padx=Spacing.LG, pady=Spacing.LG)

    def set_active(self, key: str):
        for k, btn in self._buttons.items():
            active = k == key
            color = Colors.ACCENT_YELLOW if active else Colors.TEXT_SECONDARY
            btn.configure(fg_color=Colors.BG_TERTIARY if active else "transparent",
                          text_color=color, image=icon(self._icons[k], color))


class PageHeader(ctk.CTkFrame):
    """Título grande + subtítulo, arriba de cada página."""

    def __init__(self, master, title: str, subtitle: str = ""):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=title, anchor="w", text_color=Colors.TEXT_PRIMARY,
                     font=(Fonts.FAMILY, 24, "bold")).pack(fill="x")
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, anchor="w", text_color=Colors.TEXT_SECONDARY,
                         font=(Fonts.FAMILY, Fonts.SIZE_SMALL)).pack(fill="x")


class Chip(ctk.CTkButton):
    """Botón pequeño con borde que abre/cierra un panel. Amarillo si está abierto."""

    def __init__(self, master, text: str, icon_name: str, command: Callable):
        self._icon_name = icon_name
        super().__init__(master, text=text, height=30, corner_radius=Radius.SM,
                         font=(Fonts.FAMILY, Fonts.SIZE_SMALL), fg_color="transparent",
                         hover_color=Colors.BG_HOVER, border_width=1,
                         border_color=Colors.BORDER_LIGHT, text_color=Colors.TEXT_SECONDARY,
                         image=icon(icon_name, Colors.TEXT_SECONDARY, 16), command=command)

    def set_active(self, active: bool):
        color = Colors.ACCENT_YELLOW if active else Colors.TEXT_SECONDARY
        self.configure(text_color=color, image=icon(self._icon_name, color, 16),
                       border_color=Colors.ACCENT_YELLOW if active else Colors.BORDER_LIGHT)


class ModeCard(ctk.CTkFrame):
    """Tarjeta seleccionable (Video / Audio / Texto) con icono, título y detalle."""

    def __init__(self, master, title: str, detail: str, icon_name: str,
                 command: Callable, selected: bool = False):
        super().__init__(master, fg_color=Colors.BG_SECONDARY, corner_radius=Radius.MD,
                         border_width=1, border_color=Colors.BORDER, cursor="hand2")
        self._icon_name = icon_name
        self._command = command
        self.icon_label = ctk.CTkLabel(self, text="", image=icon(icon_name, Colors.TEXT_SECONDARY, 20))
        self.icon_label.pack(anchor="w", padx=Spacing.MD, pady=(Spacing.MD, 2))
        self.title_label = ctk.CTkLabel(self, text=title, anchor="w", text_color=Colors.TEXT_PRIMARY,
                                        font=(Fonts.FAMILY, Fonts.SIZE_BODY, "bold"))
        self.title_label.pack(fill="x", padx=Spacing.MD)
        self.detail_label = ctk.CTkLabel(self, text=detail, anchor="w", text_color=Colors.TEXT_SECONDARY,
                                         font=(Fonts.FAMILY, Fonts.SIZE_SMALL))
        self.detail_label.pack(fill="x", padx=Spacing.MD, pady=(0, Spacing.MD))
        for widget in (self, self.icon_label, self.title_label, self.detail_label):
            widget.bind("<Button-1>", lambda _e: self._command())
        self.set_selected(selected)

    def set_selected(self, selected: bool):
        self.configure(border_color=Colors.ACCENT_YELLOW if selected else Colors.BORDER,
                       fg_color=Colors.ACCENT_SOFT if selected else Colors.BG_SECONDARY)
        self.icon_label.configure(image=icon(self._icon_name,
                                             Colors.ACCENT_YELLOW if selected else Colors.TEXT_SECONDARY, 20))

    def set_detail(self, text: str):
        self.detail_label.configure(text=text)


class EmptyState(ctk.CTkFrame):
    """Mensaje centrado con icono cuando una lista está vacía."""

    def __init__(self, master, icon_name: str, title: str, body: str = ""):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text="", image=icon(icon_name, Colors.TEXT_MUTED, 28)).pack(pady=(Spacing.XL, Spacing.SM))
        ctk.CTkLabel(self, text=title, text_color=Colors.TEXT_SECONDARY,
                     font=(Fonts.FAMILY, Fonts.SIZE_SMALL, "bold")).pack()
        if body:
            ctk.CTkLabel(self, text=body, text_color=Colors.TEXT_MUTED, wraplength=180, justify="center",
                         font=(Fonts.FAMILY, Fonts.SIZE_TINY)).pack(pady=(2, 0))

"""Componentes visuais reutilizáveis (cartões, botões, campos, estados vazios)."""
from __future__ import annotations

from typing import Callable, Optional

import flet as ft

from app.ui import theme as t


def card(content: ft.Control, padding: int = 20, expand: bool | int = False, level: int = 1,
         bgcolor: str = t.SURFACE, **kwargs) -> ft.Container:
    return ft.Container(
        content=content,
        padding=padding,
        bgcolor=bgcolor,
        border_radius=t.RADIUS_LG,
        border=ft.Border.all(1, t.BORDER),
        shadow=t.shadow(level),
        expand=expand,
        **kwargs,
    )


def title(text: str, size: int = 20) -> ft.Text:
    return ft.Text(text, size=size, weight=ft.FontWeight.W_700, color=t.TEXT)


def subtitle(text: str, size: int = 13) -> ft.Text:
    return ft.Text(text, size=size, color=t.TEXT_MUTED)


def section_header(text: str, caption: str | None = None, actions: list[ft.Control] | None = None) -> ft.Row:
    left = ft.Column([title(text, 17)] + ([subtitle(caption, 12)] if caption else []), spacing=2, expand=True)
    return ft.Row([left, *(actions or [])], vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _btn_style(bg: str, fg: str, border: str | None = None) -> ft.ButtonStyle:
    return ft.ButtonStyle(
        bgcolor={ft.ControlState.DEFAULT: bg, ft.ControlState.DISABLED: t.BORDER},
        color={ft.ControlState.DEFAULT: fg, ft.ControlState.DISABLED: t.TEXT_FAINT},
        overlay_color="#1AFFFFFF" if bg not in (t.SURFACE, "transparent") else "#0D1F4D3A",
        shape=ft.RoundedRectangleBorder(radius=10),
        padding=ft.Padding.symmetric(horizontal=18, vertical=14),
        elevation={ft.ControlState.DEFAULT: 0, ft.ControlState.HOVERED: 1},
        side=ft.BorderSide(1, border) if border else None,
        text_style=ft.TextStyle(size=14, weight=ft.FontWeight.W_600, font_family=t.FONT),
        animation_duration=ft.Duration(milliseconds=160),
    )


def primary_button(text: str, on_click: Callable | None = None, icon: ft.IconData | None = None,
                   expand: bool = False, color: str = t.PINE, **kwargs) -> ft.Button:
    return ft.Button(content=text, icon=icon, on_click=on_click, style=_btn_style(color, t.SURFACE),
                     expand=expand, **kwargs)


def secondary_button(text: str, on_click: Callable | None = None, icon: ft.IconData | None = None,
                     expand: bool = False, **kwargs) -> ft.Button:
    return ft.Button(content=text, icon=icon, on_click=on_click,
                     style=_btn_style(t.SURFACE, t.TEXT, t.BORDER), expand=expand, **kwargs)


def danger_button(text: str, on_click: Callable | None = None, icon: ft.IconData | None = None,
                  **kwargs) -> ft.Button:
    return ft.Button(content=text, icon=icon, on_click=on_click, style=_btn_style(t.WINE, t.SURFACE), **kwargs)


def ghost_icon(icon: ft.IconData, on_click: Callable | None = None, tooltip: str | None = None,
               color: str = t.TEXT_MUTED, size: int = 20, **kwargs) -> ft.IconButton:
    return ft.IconButton(
        icon=icon, icon_color=color, icon_size=size, tooltip=tooltip, on_click=on_click,
        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10),
                             overlay_color="#121F4D3A"),
        **kwargs,
    )


def text_field(label: str, value: str = "", icon: ft.IconData | None = None, hint: str | None = None,
               multiline: bool = False, expand: bool | int = False, **kwargs) -> ft.TextField:
    return ft.TextField(
        label=label,
        value=value,
        hint_text=hint,
        prefix_icon=icon,
        multiline=multiline,
        min_lines=3 if multiline else None,
        max_lines=5 if multiline else 1,
        border_radius=10,
        border_color=t.BORDER,
        focused_border_color=t.PINE,
        focused_border_width=1.6,
        filled=True,
        fill_color=t.SURFACE_ALT,
        text_size=14,
        label_style=ft.TextStyle(color=t.TEXT_MUTED, size=13),
        cursor_color=t.PINE,
        content_padding=ft.Padding.symmetric(horizontal=14, vertical=14),
        expand=expand,
        **kwargs,
    )


def search_field(hint: str, on_change: Callable, value: str = "", expand: bool | int = True) -> ft.TextField:
    return ft.TextField(
        hint_text=hint,
        value=value,
        prefix_icon=ft.Icons.SEARCH_ROUNDED,
        on_change=on_change,
        border_radius=12,
        border_color=t.BORDER,
        focused_border_color=t.PINE,
        filled=True,
        fill_color=t.SURFACE,
        text_size=14,
        height=46,
        content_padding=ft.Padding.symmetric(horizontal=12, vertical=0),
        expand=expand,
    )


def empty_state(icon: ft.IconData, heading: str, message: str,
                action: Optional[ft.Control] = None, compact: bool = False) -> ft.Container:
    return ft.Container(
        alignment=ft.Alignment.CENTER,
        padding=ft.Padding.symmetric(vertical=24 if compact else 48, horizontal=16),
        content=ft.Column(
            [
                ft.Container(
                    ft.Icon(icon, size=30 if compact else 38, color=t.PINE),
                    bgcolor=t.PINE_SOFT, border_radius=40, padding=16 if compact else 20,
                ),
                ft.Text(heading, size=15, weight=ft.FontWeight.W_600, color=t.TEXT, text_align=ft.TextAlign.CENTER),
                ft.Text(message, size=13, color=t.TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                *([action] if action else []),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
            tight=True,
        ),
    )


def pill(text: str, color: str, bgcolor: str, icon: ft.IconData | None = None, size: int = 11) -> ft.Container:
    items: list[ft.Control] = []
    if icon:
        items.append(ft.Icon(icon, size=size + 2, color=color))
    items.append(ft.Text(text, size=size, color=color, weight=ft.FontWeight.W_600))
    return ft.Container(
        ft.Row(items, spacing=4, tight=True),
        bgcolor=bgcolor, border_radius=20, padding=ft.Padding.symmetric(horizontal=9, vertical=3),
    )


def stat_card(label: str, value: str, icon: ft.IconData, color: str, soft: str,
              caption: str | None = None, compact: bool = False, tiny: bool = False) -> ft.Container:
    """``tiny`` (celular): sem ícone e com fonte menor para caber em duas colunas."""
    if tiny:
        return card(ft.Column([
            ft.Row([ft.Icon(icon, color=color, size=15),
                    ft.Text(label, size=11, color=t.TEXT_MUTED, weight=ft.FontWeight.W_500, expand=True,
                            no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS)], spacing=6),
            ft.Text(value, size=16, weight=ft.FontWeight.W_700, color=t.TEXT, no_wrap=True),
        ], spacing=4, tight=True), padding=12)
    return card(
        ft.Row(
            [
                ft.Container(ft.Icon(icon, color=color, size=20 if compact else 22), bgcolor=soft,
                             border_radius=12, padding=9 if compact else 11),
                ft.Column(
                    [
                        ft.Text(label, size=12, color=t.TEXT_MUTED, weight=ft.FontWeight.W_500),
                        ft.Text(value, size=17 if compact else 21, weight=ft.FontWeight.W_700, color=t.TEXT,
                                no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                        *([ft.Text(caption, size=11, color=t.TEXT_FAINT)] if caption else []),
                    ],
                    spacing=1, expand=True, tight=True,
                ),
            ],
            spacing=12,
        ),
        padding=14 if compact else 18,
    )


def avatar(initials: str, image: bytes | None = None, radius: int = 20) -> ft.Control:
    if image:
        return ft.Container(
            ft.Image(src=image, width=radius * 2, height=radius * 2, fit=ft.BoxFit.COVER),
            width=radius * 2, height=radius * 2, border_radius=radius, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            border=ft.Border.all(2, t.SURFACE), shadow=t.shadow(1),
        )
    return ft.Container(
        ft.Text(initials, size=radius * 0.7, weight=ft.FontWeight.W_700, color=t.PINE),
        width=radius * 2, height=radius * 2, border_radius=radius, bgcolor=t.PINE_SOFT,
        alignment=ft.Alignment.CENTER, border=ft.Border.all(2, t.SURFACE),
    )


def labeled_value(label: str, value: str, icon: ft.IconData) -> ft.Row:
    return ft.Row(
        [
            ft.Icon(icon, size=18, color=t.TEXT_FAINT),
            ft.Column([ft.Text(label, size=11, color=t.TEXT_MUTED),
                       ft.Text(value or "—", size=14, color=t.TEXT, selectable=True)],
                      spacing=0, expand=True, tight=True),
        ],
        spacing=12, vertical_alignment=ft.CrossAxisAlignment.START,
    )

"""Navegação adaptativa: barra lateral (desktop), trilho (tablet) e barra inferior (celular)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft

from app import config
from app.ui import theme as t


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    icon: ft.IconData
    selected_icon: ft.IconData
    caption: str


NAV_ITEMS = [
    NavItem("calendar", "Calendário", ft.Icons.CALENDAR_MONTH_OUTLINED, ft.Icons.CALENDAR_MONTH_ROUNDED,
            "Compromissos e datas"),
    NavItem("calculator", "Calculadora", ft.Icons.CALCULATE_OUTLINED, ft.Icons.CALCULATE_ROUNDED,
            "Expressões e histórico"),
    NavItem("people", "Pessoas", ft.Icons.PEOPLE_OUTLINE_ROUNDED, ft.Icons.PEOPLE_ROUNDED,
            "Cadastro e contatos"),
    NavItem("finance", "Finanças", ft.Icons.ACCOUNT_BALANCE_WALLET_OUTLINED,
            ft.Icons.ACCOUNT_BALANCE_WALLET_ROUNDED, "Entradas, despesas e WhatsApp"),
]


class Sidebar:
    """Barra lateral estilo macOS (desktop) ou trilho compacto (tablet)."""

    def __init__(self, selected: str, on_select: Callable[[str], None], compact: bool = False):
        self.selected = selected
        self.on_select = on_select
        self.compact = compact
        self.items: dict[str, ft.Container] = {}
        self.control = self._build()

    def _item(self, item: NavItem) -> ft.Container:
        active = item.key == self.selected
        icon = ft.Icon(item.selected_icon if active else item.icon, size=22,
                       color=t.PINE if active else t.TEXT_MUTED)
        if self.compact:
            body = ft.Column([icon, ft.Text(item.label, size=10, no_wrap=True, color=t.PINE if active else t.TEXT_MUTED,
                                            weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_500)],
                             spacing=3, horizontal_alignment=ft.CrossAxisAlignment.CENTER, tight=True)
        else:
            body = ft.Row([
                icon,
                ft.Column([
                    ft.Text(item.label, size=14, weight=ft.FontWeight.W_600 if active else ft.FontWeight.W_500,
                            color=t.TEXT),
                    ft.Text(item.caption, size=11, color=t.TEXT_MUTED, no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS),
                ], spacing=0, tight=True, expand=True),
            ], spacing=12)
        return ft.Container(
            body,
            padding=ft.Padding.symmetric(horizontal=12 if not self.compact else 4, vertical=10),
            border_radius=12,
            bgcolor=t.PINE_SOFT if active else None,
            on_click=lambda _, k=item.key: self.on_select(k),
            ink=False,
            animate=ft.Animation(180, ft.AnimationCurve.EASE_OUT),
            tooltip=item.label if self.compact else None,
            on_hover=self._hover,
            data=item.key,
        )

    def _hover(self, e: ft.ControlEvent) -> None:
        c: ft.Container = e.control
        if c.data == self.selected:
            return
        c.bgcolor = "#0C1F4D3A" if e.data in (True, "true") else None
        c.update()

    def set_selected(self, key: str) -> None:
        self.selected = key
        for item in NAV_ITEMS:
            new = self._item(item)
            old = self.items[item.key]
            old.content, old.bgcolor = new.content, new.bgcolor
        self.control.update()

    def _build(self) -> ft.Container:
        for item in NAV_ITEMS:
            self.items[item.key] = self._item(item)
        footer = ft.Container(
            ft.Row([
                ft.Icon(ft.Icons.LOCK_OUTLINE_ROUNDED, size=16, color=t.PINE),
                ft.Column([
                    ft.Text("Dados locais", size=12, weight=ft.FontWeight.W_600, color=t.TEXT),
                    ft.Text(f"SQLite · v{config.APP_VERSION}", size=11, color=t.TEXT_MUTED),
                ], spacing=0, tight=True),
            ], spacing=10),
            padding=12, border_radius=12, bgcolor=t.GOLD_SOFT,
            border=ft.Border.all(1, ft.Colors.with_opacity(0.35, t.GOLD)),
        )
        column_items: list[ft.Control] = []
        if not self.compact:
            column_items.append(ft.Container(
                ft.Text("MÓDULOS", size=11, weight=ft.FontWeight.W_700, color=t.TEXT_FAINT),
                padding=ft.Padding.only(left=12, bottom=4, top=4)))
        column_items += list(self.items.values())
        column_items.append(ft.Container(expand=True))
        if not self.compact:
            column_items.append(footer)
        return ft.Container(
            ft.Column(column_items, spacing=4, expand=True),
            width=96 if self.compact else 248,
            padding=ft.Padding.symmetric(horizontal=8 if self.compact else 14, vertical=16),
            bgcolor=ft.Colors.with_opacity(0.72, t.SURFACE),
            blur=ft.Blur(12, 12),
            border=ft.Border.only(right=ft.BorderSide(1, t.BORDER)),
        )


def bottom_navigation(selected: str, on_select: Callable[[str], None]) -> ft.NavigationBar:
    keys = [i.key for i in NAV_ITEMS]
    return ft.NavigationBar(
        selected_index=keys.index(selected),
        destinations=[ft.NavigationBarDestination(icon=i.icon, selected_icon=i.selected_icon, label=i.label)
                      for i in NAV_ITEMS],
        on_change=lambda e: on_select(keys[e.control.selected_index]),
        bgcolor=t.SURFACE,
        indicator_color=t.PINE_SOFT,
        elevation=0,
        border=ft.Border.only(top=ft.BorderSide(1, t.BORDER)),
        label_behavior=ft.NavigationBarLabelBehavior.ALWAYS_SHOW,
        height=68,
    )

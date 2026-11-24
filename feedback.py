"""Feedback ao usuário: notificações, confirmações e indicador de carregamento."""
from __future__ import annotations

from typing import Callable

import flet as ft

from app.ui import theme as t
from app.ui.components.widgets import danger_button, primary_button, secondary_button


class Notifier:
    """Exibe mensagens de sucesso, erro e informação (SnackBar flutuante)."""

    STYLES = {
        "success": (t.PINE, ft.Icons.CHECK_CIRCLE_ROUNDED),
        "error": (t.WINE, ft.Icons.ERROR_ROUNDED),
        "info": (t.TEXT, ft.Icons.INFO_ROUNDED),
    }

    def __init__(self, page: ft.Page):
        self.page = page

    def _show(self, kind: str, message: str) -> None:
        color, icon = self.STYLES[kind]
        width = self.page.width or 800
        bar = ft.SnackBar(
            content=ft.Row(
                [ft.Icon(icon, color=t.GOLD if kind == "success" else t.SURFACE, size=20),
                 ft.Text(message, color=t.SURFACE, size=14, expand=True)],
                spacing=10,
            ),
            bgcolor=color,
            behavior=ft.SnackBarBehavior.FLOATING,
            shape=ft.RoundedRectangleBorder(radius=12),
            width=min(440, width - 32) if width > 640 else None,
            margin=None if width > 640 else ft.Margin.all(12),
            duration=ft.Duration(milliseconds=3200 if kind != "error" else 4500),
            show_close_icon=kind == "error",
            close_icon_color=t.SURFACE,
        )
        self.page.show_dialog(bar)

    def success(self, message: str) -> None:
        self._show("success", message)

    def error(self, message: str) -> None:
        self._show("error", message)

    def info(self, message: str) -> None:
        self._show("info", message)


def close_dialog(dialog: ft.DialogControl) -> None:
    """Fecha um diálogo específico (e não apenas o do topo da pilha)."""
    if dialog.open:
        dialog.open = False
        try:
            dialog.update()
        except Exception:
            pass


def dialog_shape() -> ft.RoundedRectangleBorder:
    return ft.RoundedRectangleBorder(radius=t.RADIUS_LG)


def confirm(page: ft.Page, title: str, message: str, on_confirm: Callable[[], None],
            confirm_text: str = "Excluir", danger: bool = True) -> None:
    """Diálogo de confirmação (usado antes de excluir registros)."""

    def close(_=None):
        close_dialog(dlg)

    def accept(_):
        close_dialog(dlg)
        on_confirm()

    action = danger_button(confirm_text, accept, ft.Icons.DELETE_OUTLINE_ROUNDED) if danger \
        else primary_button(confirm_text, accept)
    dlg = ft.AlertDialog(
        modal=True,
        icon=ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED if danger else ft.Icons.HELP_OUTLINE_ROUNDED,
                     color=t.WINE if danger else t.PINE, size=32),
        title=ft.Text(title, size=18, weight=ft.FontWeight.W_700, text_align=ft.TextAlign.CENTER),
        content=ft.Container(ft.Text(message, size=14, color=t.TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                             width=360),
        actions=[secondary_button("Cancelar", close), action],
        actions_alignment=ft.MainAxisAlignment.CENTER,
        shape=dialog_shape(),
        bgcolor=t.SURFACE,
    )
    page.show_dialog(dlg)


class Busy:
    """Indicador de carregamento modal para operações mais demoradas (ex.: fotos)."""

    def __init__(self, page: ft.Page, message: str = "Processando…"):
        self.page = page
        self.dialog = ft.AlertDialog(
            modal=True,
            content=ft.Row([ft.ProgressRing(width=22, height=22, stroke_width=2.5, color=t.PINE),
                            ft.Text(message, size=14)], spacing=14, tight=True),
            shape=dialog_shape(),
            bgcolor=t.SURFACE,
        )

    def __enter__(self):
        self.page.show_dialog(self.dialog)
        return self

    def __exit__(self, *exc):
        close_dialog(self.dialog)
        return False

"""Captura de foto pela câmera do dispositivo (opcional).

Usa a extensão oficial ``flet-camera`` (Android, iOS e Web). Extensões do
Flet só ficam disponíveis em apps empacotados com ``flet build``; no modo
de desenvolvimento (``flet run``) ou em desktop, a câmera não existe no
cliente e o diálogo informa isso, sugerindo a galeria.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

import flet as ft

from app.ui import theme as t
from app.ui.components.feedback import close_dialog, dialog_shape
from app.ui.components.widgets import primary_button, secondary_button

try:  # dependência opcional
    import flet_camera as fc
except Exception:  # pragma: no cover - depende do ambiente
    fc = None


def camera_supported(page: ft.Page) -> bool:
    return fc is not None and (page.web or page.platform in (ft.PagePlatform.ANDROID, ft.PagePlatform.IOS))


async def open_camera(page: ft.Page, on_captured: Callable[[bytes], Awaitable[None] | None],
                      on_error: Callable[[str], None]) -> None:
    if fc is None:
        on_error("Câmera indisponível: instale o pacote opcional flet-camera.")
        return
    camera = fc.Camera(expand=True, preview_enabled=True)
    status = ft.Text("Iniciando a câmera…", size=13, color=t.TEXT_MUTED)
    capture_btn = primary_button("Capturar", icon=ft.Icons.CAMERA_ALT_ROUNDED, disabled=True)

    async def capture(_):
        capture_btn.disabled = True
        status.value = "Capturando…"
        dlg.update()
        try:
            data = await asyncio.wait_for(camera.take_picture(), timeout=10)
        except Exception as exc:
            close_dialog(dlg)
            on_error(f"Não foi possível capturar a foto: {exc}")
            return
        close_dialog(dlg)
        result = on_captured(bytes(data))
        if asyncio.iscoroutine(result):
            await result

    capture_btn.on_click = capture
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("Fotografar", size=18, weight=ft.FontWeight.W_700),
        content=ft.Container(ft.Column([ft.Container(camera, height=320, border_radius=12,
                                                     clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                                                     bgcolor="#000000"), status], tight=True),
                             width=420),
        actions=[secondary_button("Cancelar", lambda _: close_dialog(dlg)), capture_btn],
        shape=dialog_shape(), bgcolor=t.SURFACE,
    )
    page.show_dialog(dlg)
    try:
        cameras = await asyncio.wait_for(camera.get_available_cameras(), timeout=6)
        if not cameras:
            raise RuntimeError("nenhuma câmera encontrada")
        front = next((c for c in cameras if getattr(c, "lens_direction", None) and
                      str(c.lens_direction).lower().endswith("front")), cameras[0])
        await asyncio.wait_for(camera.initialize(front, fc.ResolutionPreset.HIGH, enable_audio=False), timeout=10)
        status.value = "Posicione o rosto no centro e toque em Capturar."
        capture_btn.disabled = False
        dlg.update()
    except Exception as exc:
        close_dialog(dlg)
        on_error("Câmera indisponível neste modo de execução "
                 f"({exc or 'sem resposta'}). Selecione uma imagem da galeria.")

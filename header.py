"""Cabeçalho com identidade visual, detalhes natalinos e neve animada."""
from __future__ import annotations

import asyncio
import random
from datetime import date

import flet as ft

from app import config
from app.ui import theme as t
from app.utils.formatters import date_long


def days_until_christmas(today: date | None = None) -> int:
    today = today or date.today()
    xmas = date(today.year, 12, 25)
    if today > xmas:
        xmas = date(today.year + 1, 12, 25)
    return (xmas - today).days


class SnowLayer:
    """Flocos discretos caindo dentro do cabeçalho (animação nativa de posição)."""

    def __init__(self, page: ft.Page, height: float, count: int = 16):
        self.page = page
        self.height = height
        self.count = count
        self.running = False
        self.flakes: list[ft.Container] = []
        self.stack = ft.Stack(expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE)
        self.control = ft.TransparentPointer(content=self.stack, expand=True)
        self._generation = 0

    def _new_flake(self) -> ft.Container:
        size = random.choice([3, 3, 4, 4, 5, 6])
        return ft.Container(
            width=size, height=size, border_radius=size,
            bgcolor=ft.Colors.with_opacity(random.uniform(0.35, 0.85), t.SURFACE),
            left=random.uniform(0, 1), top=-10,
            animate_position=ft.Animation(1, ft.AnimationCurve.LINEAR),
        )

    def start(self, width: float) -> None:
        self.stop()
        self.running = True
        self._generation += 1
        gen = self._generation
        self.flakes = [self._new_flake() for _ in range(self.count)]
        self.stack.controls = list(self.flakes)
        try:
            self.stack.update()  # flocos precisam estar na página antes de animar
        except Exception:
            return
        for i, flake in enumerate(self.flakes):
            self.page.run_task(self._fall, flake, width, gen, i * 0.45)

    def stop(self) -> None:
        self.running = False
        self._generation += 1
        self.stack.controls = []
        self.flakes = []
        try:
            self.stack.update()
        except Exception:
            pass

    async def _fall(self, flake: ft.Container, width: float, gen: int, delay: float) -> None:
        await asyncio.sleep(delay)
        while self.running and gen == self._generation:
            duration = random.uniform(5.0, 9.0)
            x = random.uniform(0, max(width - 10, 10))
            try:
                # "teleporte" com animação de 1 ms: manter o mesmo tipo de widget animado no Flutter
                flake.animate_position = ft.Animation(1, ft.AnimationCurve.LINEAR)
                flake.left, flake.top = x, -10
                flake.update()
                await asyncio.sleep(0.05)
                flake.animate_position = ft.Animation(int(duration * 1000), ft.AnimationCurve.LINEAR)
                flake.left = x + random.uniform(-40, 40)
                flake.top = self.height + 10
                flake.update()
            except Exception:  # controle removido da página (troca de layout)
                return
            await asyncio.sleep(duration + random.uniform(0.2, 1.5))


class Header:
    def __init__(self, page: ft.Page, compact: bool, snow_enabled: bool, on_toggle_snow):
        self.page = page
        self.compact = compact
        self.height = 64 if compact else 84
        self.snow_enabled = snow_enabled
        self.on_toggle_snow = on_toggle_snow
        self.snow = SnowLayer(page, self.height, count=10 if compact else 18)
        self.snow_btn = ft.IconButton(
            icon=ft.Icons.AC_UNIT_ROUNDED,
            icon_color=t.SURFACE if snow_enabled else ft.Colors.with_opacity(0.45, t.SURFACE),
            tooltip="Desativar neve" if snow_enabled else "Ativar neve",
            on_click=self._toggle,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), overlay_color="#22FFFFFF"),
        )
        self.control = self._build()

    def _toggle(self, _):
        self.snow_enabled = not self.snow_enabled
        self.snow_btn.icon_color = t.SURFACE if self.snow_enabled else ft.Colors.with_opacity(0.45, t.SURFACE)
        self.snow_btn.tooltip = "Desativar neve" if self.snow_enabled else "Ativar neve"
        if self.snow_enabled:
            self.snow.start(self.page.width or 1000)
        else:
            self.snow.stop()
        self.on_toggle_snow(self.snow_enabled)
        self.control.update()

    def start(self) -> None:
        if self.snow_enabled:
            self.snow.start(self.page.width or 1000)

    def stop(self) -> None:
        self.snow.stop()

    def _stars(self) -> list[ft.Control]:
        """Pequenas estrelas douradas fixas — detalhe discreto."""
        spots = [(0.38, 14, 9), (0.47, 46, 7), (0.58, 20, 10), (0.66, 52, 6), (0.74, 12, 8)]
        if self.compact:
            spots = spots[2:]
        return [
            ft.Container(
                ft.Icon(ft.Icons.STAR_ROUNDED, size=size, color=ft.Colors.with_opacity(0.55, t.GOLD)),
                align=ft.Alignment(x * 2 - 1, (top / self.height) * 2 - 1),
            )
            for x, top, size in spots
        ]

    def _build(self) -> ft.Container:
        today = date.today()
        days = days_until_christmas(today)
        xmas_text = "Feliz Natal!" if days == 0 else (f"{days} dias para o Natal" if days > 1 else "Amanhã é Natal!")
        logo = ft.Container(
            ft.Image(src="icons/icon.png", width=40 if not self.compact else 34,
                     height=40 if not self.compact else 34, fit=ft.BoxFit.CONTAIN),
            shadow=[ft.BoxShadow(blur_radius=12, color="#40000000", offset=ft.Offset(0, 3))],
            border_radius=10,
        )
        titles = ft.Column(
            [
                ft.Text(config.APP_NAME if not self.compact else config.APP_SHORT_NAME,
                        size=18 if self.compact else 20, weight=ft.FontWeight.W_700, color=t.SURFACE),
                ft.Text(
                    f"{config.APP_EDITION} · {date_long(today)}" if not self.compact else date_long(today).split(",")[0].capitalize() + f", {today.day:02d}/{today.month:02d}",
                    size=12, color=ft.Colors.with_opacity(0.75, t.SURFACE),
                ),
            ],
            spacing=0, tight=True, alignment=ft.MainAxisAlignment.CENTER,
        )
        right: list[ft.Control] = []
        if days <= 60:
            right.append(ft.Container(
                ft.Row([ft.Icon(ft.Icons.PARK_ROUNDED, size=15, color=t.GOLD),
                        ft.Text(xmas_text if not self.compact else f"{days}d", size=12,
                                color=t.GOLD_SOFT, weight=ft.FontWeight.W_600)], spacing=6, tight=True),
                padding=ft.Padding.symmetric(horizontal=12, vertical=6),
                border_radius=20,
                bgcolor=ft.Colors.with_opacity(0.12, t.SURFACE),
                border=ft.Border.all(1, ft.Colors.with_opacity(0.25, t.GOLD)),
                tooltip="Contagem regressiva para o Natal",
            ))
        right.append(self.snow_btn)
        content = ft.Container(
            ft.Row([logo, titles, ft.Container(expand=True), *right], spacing=12,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.Padding.symmetric(horizontal=16 if self.compact else 24),
        )
        return ft.Container(
            height=self.height,
            gradient=ft.LinearGradient(
                begin=ft.Alignment.CENTER_LEFT, end=ft.Alignment.CENTER_RIGHT,
                colors=[t.PINE_DARK, t.PINE, "#24583F"],
            ),
            border=ft.Border.only(bottom=ft.BorderSide(2, ft.Colors.with_opacity(0.55, t.GOLD))),
            shadow=t.shadow(2),
            content=ft.Stack([*self._stars(), self.snow.control, content], expand=True),
        )

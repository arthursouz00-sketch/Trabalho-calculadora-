"""Identidade visual: paleta natalina minimalista e tema do Flet."""
from __future__ import annotations

import flet as ft

# ---- Paleta ----
PINE = "#1F4D3A"          # verde pinheiro (cor primária)
PINE_DARK = "#123326"
PINE_SOFT = "#E5EFE9"
WINE = "#8C2434"          # vermelho vinho (destaques / despesas / ações destrutivas)
WINE_SOFT = "#F7E8EB"
GOLD = "#C9A55C"          # dourado suave (detalhes)
GOLD_SOFT = "#F8F1E1"
ICE = "#F4F6F5"           # branco gelo (fundo)
SURFACE = "#FFFFFF"
SURFACE_ALT = "#FAFBFA"
TEXT = "#1C2420"
TEXT_MUTED = "#66716B"
TEXT_FAINT = "#9AA39E"
BORDER = "#E2E7E4"
INCOME = "#2D7A55"
EXPENSE = WINE
INFO = "#2F5D8C"

FONT = "Inter"

RADIUS_SM = 8
RADIUS = 12
RADIUS_LG = 18

CATEGORY_COLORS = ["#1F4D3A", "#8C2434", "#C9A55C", "#2F5D8C", "#6E8B3D",
                   "#B5653A", "#5B4B8A", "#3E7C7B", "#8A8F8C"]


def shadow(level: int = 1) -> list[ft.BoxShadow]:
    """Sombras suaves em camadas, ao estilo macOS."""
    if level <= 0:
        return []
    alpha = {1: "0F", 2: "17", 3: "22"}.get(level, "22")
    return [
        ft.BoxShadow(blur_radius=2, spread_radius=0, color=f"#{alpha}1C2420", offset=ft.Offset(0, 1)),
        ft.BoxShadow(blur_radius=8 * level, spread_radius=-2, color=f"#{alpha}1C2420", offset=ft.Offset(0, 2 * level)),
    ]


def build_theme() -> ft.Theme:
    return ft.Theme(
        font_family=FONT,
        color_scheme_seed=PINE,
        color_scheme=ft.ColorScheme(
            primary=PINE,
            on_primary=SURFACE,
            secondary=GOLD,
            tertiary=WINE,
            error=WINE,
            surface=SURFACE,
            on_surface=TEXT,
            outline=BORDER,
            outline_variant=BORDER,
        ),
        scaffold_bgcolor=ICE,
        divider_color=BORDER,
        hover_color="#0A1F4D3A",
        splash_color="#141F4D3A",
    )

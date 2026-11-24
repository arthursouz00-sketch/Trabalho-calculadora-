"""Gráficos financeiros desenhados com controles nativos (sem dependências extras).

Os valores vêm do banco a cada atualização; as barras usam animação de
tamanho para uma transição suave.
"""
from __future__ import annotations

import flet as ft

from app.services.finance_service import MonthBar
from app.ui import theme as t
from app.ui.components import widgets as w
from app.utils.formatters import money


def _compact_money(cents: int) -> str:
    value = cents / 100
    if value >= 1_000_000:
        return f"R$ {value / 1_000_000:.1f} mi".replace(".", ",")
    if value >= 1_000:
        return f"R$ {value / 1_000:.1f} mil".replace(".", ",")
    return f"R$ {value:.0f}"


def category_bars(data: list[tuple[str, int]]) -> ft.Control:
    """Barras horizontais: despesas por categoria no mês."""
    if not data:
        return w.empty_state(ft.Icons.PIE_CHART_OUTLINE_ROUNDED, "Sem despesas no mês",
                             "Registre despesas para ver a distribuição por categoria.", compact=True)
    total = sum(v for _, v in data) or 1
    biggest = data[0][1] or 1
    rows: list[ft.Control] = []
    for i, (category, cents) in enumerate(data):
        color = t.CATEGORY_COLORS[i % len(t.CATEGORY_COLORS)]
        pct = cents / total * 100
        rows.append(ft.Column([
            ft.Row([
                ft.Container(width=10, height=10, border_radius=3, bgcolor=color),
                ft.Text(category, size=13, color=t.TEXT, weight=ft.FontWeight.W_500, expand=True),
                ft.Text(f"{pct:.0f}%".replace(".", ","), size=12, color=t.TEXT_MUTED),
                ft.Text(money(cents), size=13, weight=ft.FontWeight.W_600, color=t.TEXT, width=110,
                        text_align=ft.TextAlign.RIGHT),
            ], spacing=8),
            ft.Container(
                ft.Row([
                    ft.Container(bgcolor=color, border_radius=6, expand=max(int(cents / biggest * 1000), 8)),
                    ft.Container(expand=max(1000 - int(cents / biggest * 1000), 0) or None),
                ], spacing=0),
                height=10, bgcolor=t.SURFACE_ALT, border_radius=6, border=ft.Border.all(1, t.BORDER),
            ),
        ], spacing=6, tight=True))
    return ft.Column(rows, spacing=14, tight=True)


def month_columns(bars: list[MonthBar], height: int = 180) -> ft.Control:
    """Colunas agrupadas: entradas x despesas nos últimos meses."""
    peak = max([b.income_cents for b in bars] + [b.expense_cents for b in bars] + [0])
    if peak == 0:
        return w.empty_state(ft.Icons.BAR_CHART_ROUNDED, "Sem movimentações",
                             "Os últimos meses aparecerão aqui assim que houver lançamentos.", compact=True)

    def bar(cents: int, color: str, label: str) -> ft.Container:
        h = max(cents / peak * height, 3 if cents else 0)
        return ft.Container(width=14, height=h, bgcolor=color, border_radius=ft.BorderRadius.only(top_left=5, top_right=5),
                            tooltip=f"{label}: {money(cents)}",
                            animate_size=ft.Animation(450, ft.AnimationCurve.EASE_OUT_CUBIC))

    groups = []
    for b in bars:
        groups.append(ft.Column([
            ft.Container(ft.Row([bar(b.income_cents, t.INCOME, "Entradas"), bar(b.expense_cents, t.WINE, "Despesas")],
                                spacing=4, vertical_alignment=ft.CrossAxisAlignment.END, tight=True),
                         height=height, alignment=ft.Alignment.BOTTOM_CENTER),
            ft.Text(b.label, size=12, color=t.TEXT_MUTED),
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6, expand=True, tight=True))
    grid_lines = ft.Column(
        [ft.Row([ft.Text(_compact_money(int(peak * f)), size=10, color=t.TEXT_FAINT, width=64),
                 ft.Container(height=1, bgcolor=t.BORDER, expand=True)], spacing=6)
         for f in (1, 0.5, 0)],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN, height=height + 8,
    )
    legend = ft.Row([
        ft.Row([ft.Container(width=10, height=10, border_radius=3, bgcolor=t.INCOME),
                ft.Text("Entradas", size=12, color=t.TEXT_MUTED)], spacing=6, tight=True),
        ft.Row([ft.Container(width=10, height=10, border_radius=3, bgcolor=t.WINE),
                ft.Text("Despesas", size=12, color=t.TEXT_MUTED)], spacing=6, tight=True),
    ], spacing=18)
    chart = ft.Stack([
        ft.Container(grid_lines, padding=ft.Padding.only(bottom=22)),
        ft.Container(ft.Row(groups, spacing=4, vertical_alignment=ft.CrossAxisAlignment.END),
                     padding=ft.Padding.only(left=70)),
    ], height=height + 30)
    return ft.Column([chart, legend], spacing=12, tight=True)


def balance_meter(income: int, expense: int) -> ft.Control:
    """Barra de proporção gasto/receita do mês."""
    if income <= 0 and expense <= 0:
        return ft.Container()
    ratio = expense / income if income else 1.0
    used = min(ratio, 1.0)
    color = t.INCOME if ratio < 0.7 else (t.GOLD if ratio < 1 else t.WINE)
    msg = (f"Você usou {ratio * 100:.0f}% das entradas do mês".replace(".", ",") if income
           else "Há despesas sem entradas registradas no mês")
    return ft.Column([
        ft.Row([ft.Text(msg, size=13, color=t.TEXT, expand=True),
                ft.Text(f"{money(expense)} de {money(income)}", size=12, color=t.TEXT_MUTED)]),
        ft.ProgressBar(value=used, color=color, bgcolor=t.SURFACE_ALT, bar_height=10, border_radius=6),
    ], spacing=8, tight=True)

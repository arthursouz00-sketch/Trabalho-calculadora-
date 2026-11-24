"""Módulo 4 — Gestão financeira (lançamentos, resumo, gráficos e WhatsApp)."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Optional

import flet as ft

from app.database.models import EXPENSE, INCOME, Transaction
from app.modules.finance import charts
from app.modules.finance.transaction_form import open_transaction_form
from app.modules.finance.whatsapp_panel import WhatsAppPanel
from app.services.appointment_service import shift_month
from app.ui import theme as t
from app.ui.components import widgets as w
from app.ui.components.feedback import confirm
from app.ui.context import ModuleView
from app.utils.formatters import date_br, money, month_year

TABS = [("entries", "Lançamentos", ft.Icons.RECEIPT_LONG_OUTLINED),
        ("charts", "Gráficos", ft.Icons.INSIGHTS_ROUNDED),
        ("whatsapp", "WhatsApp", ft.Icons.CHAT_OUTLINED)]


class FinanceView(ModuleView):
    key = "finance"

    def __init__(self, ctx):
        super().__init__(ctx)
        today = date.today()
        self.year, self.month = today.year, today.month
        self.tab = "entries"
        self.kind_filter = "all"
        self.term = ""
        self.whatsapp = WhatsAppPanel(ctx, on_change=self._refresh_summary)
        self.summary_holder: Optional[ft.Container] = None
        self.body_holder: Optional[ft.Container] = None
        self._search_task: Optional[asyncio.Task] = None
        self.entries_holder: Optional[ft.Container] = None

    # ================= interface =================
    def build(self) -> ft.Control:
        mobile = self.ctx.is_mobile
        month_nav = ft.Container(
            ft.Row([
                w.ghost_icon(ft.Icons.CHEVRON_LEFT_ROUNDED, lambda _: self._change_month(-1), "Mês anterior"),
                ft.Text(month_year(self.year, self.month), size=14, weight=ft.FontWeight.W_600, color=t.TEXT,
                        width=160, text_align=ft.TextAlign.CENTER),
                w.ghost_icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, lambda _: self._change_month(1), "Próximo mês"),
            ], spacing=0, tight=True),
            bgcolor=t.SURFACE, border_radius=12, border=ft.Border.all(1, t.BORDER),
        )
        add_btn = w.primary_button("Novo lançamento" if not mobile else "Novo", lambda _: self._open_form(),
                                   ft.Icons.ADD_ROUNDED)
        if mobile:
            head = ft.Column([
                ft.Row([w.title("Finanças", 20), ft.Container(expand=True), add_btn]),
                ft.Row([month_nav], alignment=ft.MainAxisAlignment.CENTER),
            ], spacing=10)
        else:
            head = ft.Row([ft.Column([w.title("Finanças", 22), w.subtitle("Controle de entradas e despesas")],
                                     spacing=2, expand=True, tight=True), month_nav, add_btn], spacing=12)
        self.summary_holder = ft.Container(self._summary())
        tabs = ft.SegmentedButton(
            segments=[ft.Segment(value=k, label=ft.Text(label, size=13 if mobile else 14, no_wrap=True),
                                 icon=None if mobile else ft.Icon(icon)) for k, label, icon in TABS],
            selected=[self.tab], allow_empty_selection=False, show_selected_icon=False,
            on_change=self._tab_changed,
            style=ft.ButtonStyle(
                bgcolor={ft.ControlState.SELECTED: t.PINE, ft.ControlState.DEFAULT: t.SURFACE},
                color={ft.ControlState.SELECTED: t.SURFACE, ft.ControlState.DEFAULT: t.TEXT_MUTED},
                shape=ft.RoundedRectangleBorder(radius=10), side=ft.BorderSide(1, t.BORDER),
                padding=ft.Padding.symmetric(horizontal=8 if mobile else 16, vertical=10),
            ),
        )
        self.body_holder = ft.Container(self._body(), animate_opacity=ft.Animation(200, ft.AnimationCurve.EASE_OUT))
        return ft.Column([head, self.summary_holder, ft.Row([tabs], scroll=ft.ScrollMode.AUTO, alignment=ft.MainAxisAlignment.CENTER if mobile else ft.MainAxisAlignment.START), self.body_holder],
                         spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def _summary(self) -> ft.Control:
        f = self.ctx.services.finance
        overall = f.overall()
        month = f.month_summary(self.year, self.month)
        compact = not self.ctx.is_desktop
        tiny = self.ctx.is_mobile
        period = None if tiny else month_year(self.year, self.month)
        balance_color = t.INCOME if overall.balance_cents >= 0 else t.WINE
        cards = [
            w.stat_card("Saldo atual", money(overall.balance_cents), ft.Icons.ACCOUNT_BALANCE_ROUNDED,
                        balance_color, t.PINE_SOFT if overall.balance_cents >= 0 else t.WINE_SOFT,
                        "Acumulado até hoje", compact, tiny),
            w.stat_card("Entradas do mês", money(month.income_cents), ft.Icons.TRENDING_UP_ROUNDED, t.INCOME,
                        t.PINE_SOFT, period, compact, tiny),
            w.stat_card("Despesas do mês", money(month.expense_cents), ft.Icons.TRENDING_DOWN_ROUNDED, t.WINE,
                        t.WINE_SOFT, period, compact, tiny),
            w.stat_card("Resultado do mês", money(month.balance_cents, signed=True), ft.Icons.SAVINGS_OUTLINED,
                        "#8A6A2B", t.GOLD_SOFT, period, compact, tiny),
        ]
        return ft.ResponsiveRow([ft.Container(c, col={"xs": 6, "md": 6, "lg": 3}) for c in cards],
                                spacing=12, run_spacing=12)

    def _body(self) -> ft.Control:
        if self.tab == "charts":
            return self._charts()
        if self.tab == "whatsapp":
            return self.whatsapp.build()
        return self._entries()

    # ---------- lançamentos ----------
    def _entries(self) -> ft.Control:
        filters = ft.Row([
            self._filter_chip("all", "Todos"), self._filter_chip(INCOME, "Entradas"),
            self._filter_chip(EXPENSE, "Despesas"),
        ], spacing=6)
        search = w.search_field("Buscar descrição ou categoria", self._on_search, self.term,
                                expand=not self.ctx.is_mobile)
        toolbar = ft.Column([filters, search], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH) \
            if self.ctx.is_mobile else \
            ft.Row([filters, ft.Container(width=12), search], spacing=6)
        self.entries_holder = ft.Container(self._entries_content())
        return w.card(ft.Column([toolbar, self.entries_holder], spacing=12, tight=True),
                      padding=12 if self.ctx.is_mobile else 18)

    def _entries_content(self) -> ft.Control:
        kind = None if self.kind_filter == "all" else self.kind_filter
        items = self.ctx.services.finance.list_month(self.year, self.month, kind, self.term)
        if not items:
            filtered = self.term or kind
            return w.empty_state(
                ft.Icons.RECEIPT_LONG_OUTLINED,
                "Nenhum lançamento encontrado" if filtered else "Nenhum lançamento neste mês",
                "Ajuste os filtros ou a busca." if filtered else
                "Registre entradas e despesas — ou envie uma mensagem de teste na aba WhatsApp.",
                None if filtered else w.primary_button("Registrar lançamento", lambda _: self._open_form(),
                                                       ft.Icons.ADD_ROUNDED))
        return self._table(items) if self.ctx.is_desktop else self._list(items)

    def _filter_chip(self, key: str, label: str) -> ft.Container:
        active = self.kind_filter == key
        return ft.Container(
            ft.Text(label, size=13, weight=ft.FontWeight.W_600, color=t.SURFACE if active else t.TEXT_MUTED),
            bgcolor=t.PINE if active else t.SURFACE_ALT, border_radius=20,
            border=ft.Border.all(1, t.PINE if active else t.BORDER),
            padding=ft.Padding.symmetric(horizontal=14, vertical=8),
            on_click=lambda _, k=key: self._set_filter(k),
            animate=ft.Animation(150, ft.AnimationCurve.EASE_OUT),
        )

    def _kind_badge(self, tx: Transaction) -> ft.Container:
        return w.pill("Entrada" if tx.is_income else "Despesa", t.INCOME if tx.is_income else t.WINE,
                      t.PINE_SOFT if tx.is_income else t.WINE_SOFT,
                      ft.Icons.ARROW_UPWARD_ROUNDED if tx.is_income else ft.Icons.ARROW_DOWNWARD_ROUNDED)

    def _source_icon(self, tx: Transaction) -> list[ft.Control]:
        if tx.source == "whatsapp":
            return [ft.Icon(ft.Icons.CHAT_OUTLINED, size=14, color=t.PINE, tooltip="Lançado via WhatsApp (teste)")]
        return []

    def _table(self, items: list[Transaction]) -> ft.Control:
        heading = ft.TextStyle(size=12, weight=ft.FontWeight.W_700, color=t.TEXT_MUTED, font_family=t.FONT)
        rows = []
        for tx in items:
            rows.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(date_br(tx.date), size=13)),
                ft.DataCell(ft.Row([ft.Text(tx.description, size=14, weight=ft.FontWeight.W_500),
                                    *self._source_icon(tx)], spacing=6, tight=True)),
                ft.DataCell(ft.Text(tx.category, size=13, color=t.TEXT_MUTED)),
                ft.DataCell(self._kind_badge(tx)),
                ft.DataCell(ft.Text(money(tx.signed_cents, signed=True), size=14, weight=ft.FontWeight.W_700,
                                    color=t.INCOME if tx.is_income else t.WINE)),
                ft.DataCell(ft.Row([
                    w.ghost_icon(ft.Icons.EDIT_OUTLINED, lambda _, x=tx: self._open_form(x), "Editar", size=19),
                    w.ghost_icon(ft.Icons.DELETE_OUTLINE_ROUNDED, lambda _, x=tx: self._ask_delete(x), "Excluir",
                                 color=t.WINE, size=19),
                ], spacing=0, tight=True)),
            ]))
        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("DATA", style=heading)), ft.DataColumn(ft.Text("DESCRIÇÃO", style=heading)),
                     ft.DataColumn(ft.Text("CATEGORIA", style=heading)), ft.DataColumn(ft.Text("TIPO", style=heading)),
                     ft.DataColumn(ft.Text("VALOR", style=heading), numeric=True),
                     ft.DataColumn(ft.Text("AÇÕES", style=heading))],
            rows=rows, heading_row_color=t.SURFACE_ALT, heading_row_height=42, data_row_min_height=54,
            data_row_max_height=54, divider_thickness=0.6, column_spacing=26, expand=True,
        )
        if self.ctx.width >= 1280:
            return ft.Column([table], horizontal_alignment=ft.CrossAxisAlignment.STRETCH, tight=True)
        return ft.Row([table], scroll=ft.ScrollMode.AUTO)

    def _list(self, items: list[Transaction]) -> ft.Control:
        tiles = []
        for tx in items:
            tiles.append(ft.Container(
                ft.Row([
                    ft.Container(ft.Icon(ft.Icons.ARROW_UPWARD_ROUNDED if tx.is_income else ft.Icons.ARROW_DOWNWARD_ROUNDED,
                                         size=18, color=t.INCOME if tx.is_income else t.WINE),
                                 bgcolor=t.PINE_SOFT if tx.is_income else t.WINE_SOFT, border_radius=12, padding=9),
                    ft.Column([
                        ft.Row([ft.Text(tx.description, size=14, weight=ft.FontWeight.W_600, no_wrap=True,
                                        overflow=ft.TextOverflow.ELLIPSIS, expand=True), *self._source_icon(tx)],
                               spacing=4),
                        ft.Text(f"{tx.category} · {date_br(tx.date)}", size=12, color=t.TEXT_MUTED),
                    ], spacing=2, expand=True, tight=True),
                    ft.Text(money(tx.signed_cents, signed=True), size=14, weight=ft.FontWeight.W_700,
                            color=t.INCOME if tx.is_income else t.WINE),
                    ft.PopupMenuButton(
                        icon=ft.Icons.MORE_VERT_ROUNDED, icon_color=t.TEXT_MUTED, tooltip="Ações",
                        items=[ft.PopupMenuItem(content="Editar", icon=ft.Icons.EDIT_OUTLINED,
                                                on_click=lambda _, x=tx: self._open_form(x)),
                               ft.PopupMenuItem(content="Excluir", icon=ft.Icons.DELETE_OUTLINE_ROUNDED,
                                                on_click=lambda _, x=tx: self._ask_delete(x))],
                    ),
                ], spacing=10),
                padding=ft.Padding.only(left=10, top=8, bottom=8), border_radius=14, bgcolor=t.SURFACE_ALT,
                border=ft.Border.all(1, t.BORDER), on_click=lambda _, x=tx: self._open_form(x),
            ))
        return ft.Column(tiles, spacing=8, tight=True)

    # ---------- gráficos ----------
    def _charts(self) -> ft.Control:
        f = self.ctx.services.finance
        month = f.month_summary(self.year, self.month)
        cat_card = w.card(ft.Column([
            w.section_header("Despesas por categoria", month_year(self.year, self.month)),
            charts.balance_meter(month.income_cents, month.expense_cents),
            charts.category_bars(f.expenses_by_category(self.year, self.month)),
        ], spacing=16, tight=True), padding=16 if self.ctx.is_mobile else 22)
        months_card = w.card(ft.Column([
            w.section_header("Entradas x despesas", "Últimos 6 meses"),
            charts.month_columns(f.last_months(self.year, self.month), height=150 if self.ctx.is_mobile else 200),
        ], spacing=16, tight=True), padding=16 if self.ctx.is_mobile else 22)
        if self.ctx.is_desktop:
            return ft.Row([ft.Container(cat_card, expand=1), ft.Container(months_card, expand=1)], spacing=18,
                          vertical_alignment=ft.CrossAxisAlignment.START)
        return ft.Column([cat_card, months_card], spacing=14)

    # ================= ações =================
    def _reload_body(self) -> None:
        self.body_holder.content = self._body()
        try:
            self.body_holder.update()
        except Exception:
            pass

    def _refresh_summary(self) -> None:
        self.summary_holder.content = self._summary()
        try:
            self.summary_holder.update()
        except Exception:
            pass

    def _refresh_all(self, *_):
        self._refresh_summary()
        self._reload_body()

    def _tab_changed(self, e) -> None:
        self.tab = e.control.selected[0]
        self._reload_body()

    def _set_filter(self, key: str) -> None:
        self.kind_filter = key
        self._reload_body()

    async def _on_search(self, e) -> None:
        self.term = e.control.value or ""
        if self._search_task and not self._search_task.done():
            self._search_task.cancel()

        async def delayed():
            await asyncio.sleep(0.3)
            self.entries_holder.content = self._entries_content()  # o campo de busca mantém o foco
            try:
                self.entries_holder.update()
            except Exception:
                pass
        self._search_task = asyncio.create_task(delayed())

    def _change_month(self, delta: int) -> None:
        self.year, self.month = shift_month(self.year, self.month, delta)
        self.refresh()

    def _open_form(self, tx: Optional[Transaction] = None) -> None:
        def saved(saved_tx: Transaction):
            if saved_tx.date.year != self.year or saved_tx.date.month != self.month:
                self.year, self.month = saved_tx.date.year, saved_tx.date.month
                self.refresh()
            else:
                self._refresh_all()
        open_transaction_form(self.ctx, tx, on_saved=saved)

    def _ask_delete(self, tx: Transaction) -> None:
        confirm(self.page, "Excluir lançamento?",
                f"“{tx.description}” ({money(tx.amount_cents)}) de {date_br(tx.date)} será removido.",
                lambda: self.ctx.run_safely(lambda: self.ctx.services.finance.delete(tx.id), "Lançamento excluído.",
                                            then=self._refresh_all))

    def live_refresh(self) -> None:
        """Chamado quando um lançamento chega pelo WhatsApp real."""
        self._refresh_summary()
        if self.tab == "whatsapp":
            self.whatsapp.reload()
        elif self.body_holder is not None:
            self._reload_body()

    def on_show(self) -> None:
        self.refresh()

"""Formulário de lançamento financeiro (novo, edição ou sugestão vinda do WhatsApp)."""
from __future__ import annotations

from datetime import date, datetime
from typing import Callable, Optional

import flet as ft

from app.database.models import EXPENSE, INCOME, Transaction
from app.services.finance_service import categories_for
from app.ui import theme as t
from app.ui.components import widgets as w
from app.ui.components.feedback import close_dialog, dialog_shape
from app.ui.context import AppContext
from app.utils.formatters import date_br
from app.utils.validators import ValidationError, parse_date_br


def _amount_text(cents: int) -> str:
    reais, cent = divmod(cents, 100)
    return f"{reais:,}".replace(",", ".") + f",{cent:02d}"


def open_transaction_form(ctx: AppContext, existing: Optional[Transaction] = None,
                          on_saved: Optional[Callable[[Transaction], None]] = None,
                          save_handler: Optional[Callable[[Transaction], Transaction]] = None,
                          title: Optional[str] = None, banner: Optional[ft.Control] = None) -> None:
    """``existing`` sem id = valores sugeridos; ``save_handler`` permite outro fluxo de gravação
    (ex.: confirmação de mensagem do WhatsApp)."""
    page = ctx.page
    svc = ctx.services.finance
    state = {"kind": existing.kind if existing else EXPENSE}

    kind_btn = ft.SegmentedButton(
        segments=[ft.Segment(value=EXPENSE, label=ft.Text("Despesa"), icon=ft.Icon(ft.Icons.ARROW_DOWNWARD_ROUNDED)),
                  ft.Segment(value=INCOME, label=ft.Text("Entrada"), icon=ft.Icon(ft.Icons.ARROW_UPWARD_ROUNDED))],
        selected=[state["kind"]],
        allow_empty_selection=False,
        show_selected_icon=False,
        style=ft.ButtonStyle(
            bgcolor={ft.ControlState.SELECTED: t.PINE_SOFT},
            color={ft.ControlState.SELECTED: t.PINE, ft.ControlState.DEFAULT: t.TEXT_MUTED},
            shape=ft.RoundedRectangleBorder(radius=10),
            side=ft.BorderSide(1, t.BORDER),
        ),
    )
    desc_f = w.text_field("Descrição *", existing.description if existing else "", ft.Icons.NOTES_ROUNDED,
                          max_length=100, autofocus=existing is None)
    amount_f = w.text_field("Valor *", _amount_text(existing.amount_cents) if existing else "",
                            ft.Icons.PAYMENTS_OUTLINED, hint="0,00", prefix="R$ ",
                            keyboard_type=ft.KeyboardType.NUMBER, expand=True)
    date_f = w.text_field("Data *", date_br(existing.date if existing else date.today()), ft.Icons.EVENT_ROUNDED,
                          hint="DD/MM/AAAA", expand=True)

    def category_options(kind: str) -> list[ft.DropdownOption]:
        return [ft.DropdownOption(key=c, text=c) for c in categories_for(kind)]

    initial_cat = existing.category if existing and existing.category in categories_for(state["kind"]) else None
    category_dd = ft.Dropdown(
        label="Categoria *", leading_icon=ft.Icons.SELL_OUTLINED, options=category_options(state["kind"]),
        value=initial_cat, border_radius=10, border_color=t.BORDER, focused_border_color=t.PINE, filled=True,
        fill_color=t.SURFACE_ALT, expand=True, menu_height=320,
    )

    def kind_changed(e):
        state["kind"] = e.control.selected[0] if e.control.selected else EXPENSE
        current = category_dd.value
        category_dd.options = category_options(state["kind"])
        category_dd.value = current if current in categories_for(state["kind"]) else None
        dlg.update()

    kind_btn.on_change = kind_changed

    def pick_date(_):
        def changed(e):
            if e.control.value:
                v = e.control.value
                date_f.value = date_br(v.date() if isinstance(v, datetime) else v)
                date_f.error = None
                date_f.update()
        try:
            current = parse_date_br(date_f.value)
        except ValidationError:
            current = date.today()
        page.show_dialog(ft.DatePicker(value=datetime.combine(current, datetime.min.time()),
                                       first_date=datetime(2000, 1, 1), last_date=datetime(2100, 12, 31),
                                       on_change=changed, confirm_text="OK", cancel_text="Cancelar",
                                       help_text="Data do lançamento"))

    date_f.suffix = ft.IconButton(ft.Icons.CALENDAR_MONTH_ROUNDED, icon_color=t.PINE, on_click=pick_date,
                                  tooltip="Escolher data")
    fields = {"description": desc_f, "amount": amount_f, "date": date_f}

    def save(_):
        for f in fields.values():
            f.error = None
        category_dd.error_text = None
        try:
            tx = svc.build(state["kind"], desc_f.value, amount_f.value, category_dd.value or "", date_f.value,
                           existing.id if existing else None,
                           source=existing.source if existing else "manual")
        except ValidationError as exc:
            if exc.field == "category":
                category_dd.error_text = str(exc)
            elif exc.field in fields:
                fields[exc.field].error = str(exc)
            else:
                ctx.notify.error(str(exc))
            dlg.update()
            return
        holder: dict = {}

        def do_save():
            holder["tx"] = (save_handler or svc.save)(tx)

        def after():
            close_dialog(dlg)
            if on_saved:
                on_saved(holder["tx"])

        ctx.run_safely(do_save, "Lançamento atualizado." if existing and existing.id else "Lançamento registrado.",
                       then=after)

    desc_f.on_submit = save
    amount_f.on_submit = save
    stacked = ctx.is_mobile
    pair = ft.Column([amount_f, date_f], spacing=12) if stacked else ft.Row([amount_f, date_f], spacing=12)
    body: list[ft.Control] = []
    if banner:
        body.append(banner)
    body += [ft.Row([kind_btn], alignment=ft.MainAxisAlignment.CENTER), desc_f, pair, ft.Row([category_dd])]
    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Row([ft.Icon(ft.Icons.RECEIPT_LONG_ROUNDED, color=t.PINE),
                      ft.Text(title or ("Editar lançamento" if existing and existing.id else "Novo lançamento"),
                              size=18, weight=ft.FontWeight.W_700)], spacing=10),
        content=ft.Container(ft.Column(body, spacing=12, tight=True,
                                       horizontal_alignment=ft.CrossAxisAlignment.STRETCH), width=480),
        actions=[w.secondary_button("Cancelar", lambda _: close_dialog(dlg)),
                 w.primary_button("Salvar", save, ft.Icons.CHECK_ROUNDED)],
        shape=dialog_shape(), bgcolor=t.SURFACE, scrollable=True,
        inset_padding=ft.Padding.symmetric(horizontal=12, vertical=24) if stacked else None,
    )
    page.show_dialog(dlg)

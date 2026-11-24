"""Módulo 1 — Calendário e compromissos."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

import flet as ft

from app.database.models import Appointment
from app.services.appointment_service import month_grid, shift_month
from app.ui import theme as t
from app.ui.components import widgets as w
from app.ui.components.feedback import close_dialog, confirm, dialog_shape
from app.ui.context import ModuleView
from app.utils.formatters import WEEKDAYS_SHORT, date_br, date_long, month_year
from app.utils.validators import ValidationError, parse_date_br


class CalendarView(ModuleView):
    key = "calendar"

    def __init__(self, ctx):
        super().__init__(ctx)
        today = date.today()
        self.year, self.month = today.year, today.month
        self.selected = today

    # ================= interface =================
    def build(self) -> ft.Control:
        svc = self.ctx.services
        weeks = month_grid(self.year, self.month)
        counts = svc.appointments.counts_for_grid(weeks)
        people = svc.people.search()
        birthdays = {(p.birth_date.month, p.birth_date.day) for p in people if p.birth_date}
        calendar_card = self._calendar_card(weeks, counts, birthdays)
        day_panel = self._day_panel(people)
        if self.ctx.is_desktop:
            return ft.Row([ft.Container(calendar_card, expand=11), ft.Container(day_panel, expand=9)],
                          spacing=22, vertical_alignment=ft.CrossAxisAlignment.START, expand=True)
        return ft.Column([calendar_card, day_panel], spacing=14, scroll=ft.ScrollMode.AUTO, expand=True)

    def _calendar_card(self, weeks, counts: dict[date, int], birthdays: set) -> ft.Container:
        mobile = self.ctx.is_mobile
        nav = ft.Row(
            [
                ft.Column([w.title(month_year(self.year, self.month), 18 if mobile else 22),
                           w.subtitle("Toque em um dia para ver os compromissos" if mobile
                                      else "Selecione um dia para ver e cadastrar compromissos")],
                          spacing=2, expand=True, tight=True),
                w.ghost_icon(ft.Icons.CHEVRON_LEFT_ROUNDED, lambda _: self._change_month(-1), "Mês anterior"),
                ft.TextButton("Hoje", on_click=self._go_today,
                              style=ft.ButtonStyle(color=t.PINE, shape=ft.RoundedRectangleBorder(radius=10))),
                w.ghost_icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, lambda _: self._change_month(1), "Próximo mês"),
            ],
            spacing=2,
        )
        header = ft.Row(
            [ft.Container(ft.Text(d if not mobile else d[0], size=12, weight=ft.FontWeight.W_600,
                                  color=t.WINE if i >= 5 else t.TEXT_MUTED),
                          expand=True, alignment=ft.Alignment.CENTER) for i, d in enumerate(WEEKDAYS_SHORT)],
            spacing=4,
        )
        rows = [ft.Row([self._day_cell(d, counts.get(d, 0), (d.month, d.day) in birthdays) for d in week],
                       spacing=4 if not mobile else 2) for week in weeks]
        legend = ft.Row(
            [self._legend_dot(t.PINE, "Com compromissos"), self._legend_star("Aniversário"),
             self._legend_ring("Hoje")],
            spacing=16, wrap=True,
        )
        return w.card(ft.Column([nav, ft.Divider(height=8, color="transparent"), header, *rows,
                                 ft.Divider(height=6, color="transparent"), legend],
                                spacing=4 if not mobile else 2, tight=True),
                      padding=14 if mobile else 22)

    def _legend_dot(self, color, text):
        return ft.Row([ft.Container(width=7, height=7, border_radius=4, bgcolor=color),
                       ft.Text(text, size=11, color=t.TEXT_MUTED)], spacing=6, tight=True)

    def _legend_star(self, text):
        return ft.Row([ft.Icon(ft.Icons.CAKE_ROUNDED, size=12, color=t.GOLD),
                       ft.Text(text, size=11, color=t.TEXT_MUTED)], spacing=6, tight=True)

    def _legend_ring(self, text):
        return ft.Row([ft.Container(width=12, height=12, border_radius=6, border=ft.Border.all(1.5, t.WINE)),
                       ft.Text(text, size=11, color=t.TEXT_MUTED)], spacing=6, tight=True)

    def _day_cell(self, d: date, count: int, birthday: bool) -> ft.Container:
        mobile = self.ctx.is_mobile
        in_month = d.month == self.month
        is_today = d == date.today()
        selected = d == self.selected
        color = t.SURFACE if selected else (t.TEXT if in_month else t.TEXT_FAINT)
        dots: list[ft.Control] = [
            ft.Container(width=6, height=6, border_radius=3,
                         bgcolor=t.GOLD if selected else (t.PINE if in_month else t.TEXT_FAINT))
            for _ in range(min(count, 3))
        ]
        if birthday:
            dots.append(ft.Icon(ft.Icons.CAKE_ROUNDED, size=10, color=t.GOLD))
        body = ft.Column(
            [
                ft.Text(str(d.day), size=13 if mobile else 15,
                        weight=ft.FontWeight.W_700 if (selected or is_today) else ft.FontWeight.W_500, color=color),
                ft.Row(dots, spacing=3, alignment=ft.MainAxisAlignment.CENTER, height=10),
            ],
            spacing=2 if mobile else 4,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            tight=True,
        )
        tooltip = None
        if not mobile and (count or birthday):
            parts = []
            if count:
                parts.append(f"{count} compromisso(s)")
            if birthday:
                parts.append("aniversário")
            tooltip = ", ".join(parts)
        return ft.Container(
            body,
            expand=True,
            height=48 if mobile else 64,
            alignment=ft.Alignment.CENTER,
            border_radius=10 if mobile else 12,
            bgcolor=t.PINE if selected else (t.SURFACE_ALT if in_month else None),
            border=ft.Border.all(1.5, t.WINE) if (is_today and not selected) else
            ft.Border.all(1, t.BORDER if in_month and not selected else "transparent"),
            shadow=t.shadow(2) if selected else None,
            on_click=lambda _, day=d: self._select(day),
            animate=ft.Animation(160, ft.AnimationCurve.EASE_OUT),
            tooltip=tooltip,
        )

    def _day_panel(self, people) -> ft.Container:
        svc = self.ctx.services
        items = svc.appointments.by_day(self.selected)
        bdays = [p for p in people if p.has_birthday_on(self.selected)]
        heading = date_long(self.selected).replace(f" de {self.selected.year}", "")
        caption = "Nenhum compromisso" if not items else f"{len(items)} compromisso{'s' if len(items) > 1 else ''}"
        add_btn = w.primary_button("Novo" if self.ctx.is_mobile else "Novo compromisso",
                                   lambda _: self._open_form(), ft.Icons.ADD_ROUNDED)
        content: list[ft.Control] = [
            ft.Row([ft.Column([w.title(heading[0].upper() + heading[1:], 17), w.subtitle(caption, 12)],
                              spacing=2, expand=True, tight=True), add_btn]),
        ]
        for p in bdays:
            age = p.age(self.selected)
            content.append(ft.Container(
                ft.Row([ft.Icon(ft.Icons.CAKE_ROUNDED, color=t.GOLD, size=18),
                        ft.Text(f"Aniversário de {p.full_name}" + (f" · {age} anos" if age is not None else ""),
                                size=13, color=t.TEXT, expand=True)], spacing=10),
                bgcolor=t.GOLD_SOFT, border_radius=10, padding=ft.Padding.symmetric(horizontal=12, vertical=9),
            ))
        if items:
            content.extend(self._appointment_tile(a) for a in items)
        else:
            content.append(w.empty_state(
                ft.Icons.EVENT_AVAILABLE_ROUNDED, "Dia livre",
                "Nenhum compromisso para esta data. Use “Novo compromisso” para adicionar.", compact=True))
        upcoming = [a for a in svc.appointments.upcoming(6) if a.date != self.selected][:4]
        if upcoming:
            content.append(ft.Divider(height=18, color=t.BORDER))
            content.append(ft.Text("PRÓXIMOS", size=11, weight=ft.FontWeight.W_700, color=t.TEXT_FAINT))
            for a in upcoming:
                content.append(ft.Container(
                    ft.Row([
                        ft.Container(ft.Text(f"{a.date.day:02d}/{a.date.month:02d}", size=12,
                                             weight=ft.FontWeight.W_600, color=t.PINE),
                                     bgcolor=t.PINE_SOFT, border_radius=8,
                                     padding=ft.Padding.symmetric(horizontal=8, vertical=4)),
                        ft.Text(f"{a.time.strftime('%H:%M')} · {a.title}", size=13, color=t.TEXT, expand=True,
                                no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                        ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, size=18, color=t.TEXT_FAINT),
                    ], spacing=10),
                    on_click=lambda _, d=a.date: self._select(d, jump=True),
                    border_radius=10, padding=ft.Padding.symmetric(horizontal=6, vertical=6),
                ))
        column = ft.Column(content, spacing=10, scroll=ft.ScrollMode.AUTO if self.ctx.is_desktop else None,
                           expand=self.ctx.is_desktop)
        return w.card(column, padding=14 if self.ctx.is_mobile else 22, expand=self.ctx.is_desktop)

    def _appointment_tile(self, a: Appointment) -> ft.Container:
        details: list[ft.Control] = [
            ft.Text(a.title, size=15, weight=ft.FontWeight.W_600, color=t.TEXT),
        ]
        if a.description:
            details.append(ft.Text(a.description, size=13, color=t.TEXT_MUTED, max_lines=3,
                                   overflow=ft.TextOverflow.ELLIPSIS))
        if a.person_name:
            details.append(w.pill(a.person_name, t.PINE, t.PINE_SOFT, ft.Icons.PERSON_ROUNDED))
        return ft.Container(
            ft.Row(
                [
                    ft.Container(
                        ft.Text(a.time.strftime("%H:%M"), size=13, weight=ft.FontWeight.W_700, color=t.PINE_DARK),
                        bgcolor=t.GOLD_SOFT, border_radius=10,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
                        border=ft.Border.all(1, ft.Colors.with_opacity(0.4, t.GOLD)),
                    ),
                    ft.Column(details, spacing=4, expand=True, tight=True),
                    w.ghost_icon(ft.Icons.EDIT_OUTLINED, lambda _, x=a: self._open_form(x), "Editar", size=19),
                    w.ghost_icon(ft.Icons.DELETE_OUTLINE_ROUNDED, lambda _, x=a: self._ask_delete(x), "Excluir",
                                 color=t.WINE, size=19),
                ],
                spacing=12, vertical_alignment=ft.CrossAxisAlignment.START,
            ),
            padding=12,
            border_radius=14,
            bgcolor=t.SURFACE_ALT,
            border=ft.Border.all(1, t.BORDER),
        )

    # ================= ações =================
    def _select(self, d: date, jump: bool = False) -> None:
        self.selected = d
        if d.month != self.month or d.year != self.year:
            self.year, self.month = d.year, d.month
        self.refresh()

    def _change_month(self, delta: int) -> None:
        self.year, self.month = shift_month(self.year, self.month, delta)
        self.refresh()

    def _go_today(self, _=None) -> None:
        self._select(date.today())

    def on_show(self) -> None:
        self.refresh()  # atualiza aniversários/pessoas cadastradas em outro módulo

    def _ask_delete(self, a: Appointment) -> None:
        def do_delete():
            self.ctx.run_safely(lambda: self.ctx.services.appointments.delete(a.id), "Compromisso excluído.",
                                then=self.refresh)
        confirm(self.page, "Excluir compromisso?",
                f"“{a.title}” em {date_br(a.date)} às {a.time.strftime('%H:%M')} será removido definitivamente.",
                do_delete)

    def _open_form(self, existing: Optional[Appointment] = None) -> None:
        page = self.page
        people = self.ctx.services.people.search()
        title_f = w.text_field("Título *", existing.title if existing else "", ft.Icons.TITLE_ROUNDED,
                               max_length=80, autofocus=True)
        desc_f = w.text_field("Descrição", existing.description if existing else "", ft.Icons.NOTES_ROUNDED,
                              multiline=True, max_length=500)
        day = existing.date if existing else self.selected
        date_f = w.text_field("Data *", date_br(day), ft.Icons.EVENT_ROUNDED, hint="DD/MM/AAAA", expand=True)
        time_f = w.text_field("Horário *", existing.time.strftime("%H:%M") if existing else "09:00",
                              ft.Icons.SCHEDULE_ROUNDED, hint="HH:MM", expand=True)
        person_dd = ft.Dropdown(
            label="Pessoa relacionada (opcional)",
            leading_icon=ft.Icons.PERSON_OUTLINE_ROUNDED,
            options=[ft.DropdownOption(key="", text="Nenhuma")] +
                    [ft.DropdownOption(key=str(p.id), text=p.full_name) for p in people],
            value=str(existing.person_id) if existing and existing.person_id else "",
            border_radius=10, border_color=t.BORDER, focused_border_color=t.PINE, filled=True,
            fill_color=t.SURFACE_ALT, expand=True, enable_filter=True, editable=len(people) > 8,
            menu_height=300,
        )

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
                current = self.selected
            page.show_dialog(ft.DatePicker(value=datetime.combine(current, datetime.min.time()),
                                           first_date=datetime(2000, 1, 1), last_date=datetime(2100, 12, 31),
                                           on_change=changed, confirm_text="OK", cancel_text="Cancelar",
                                           help_text="Data do compromisso"))

        def pick_time(_):
            def changed(e):
                if e.control.value:
                    time_f.value = e.control.value.strftime("%H:%M")
                    time_f.error = None
                    time_f.update()
            page.show_dialog(ft.TimePicker(confirm_text="OK", cancel_text="Cancelar", help_text="Horário",
                                           on_change=changed, hour_format=ft.TimePickerHourFormat.H24))

        date_f.suffix = ft.IconButton(ft.Icons.CALENDAR_MONTH_ROUNDED, icon_color=t.PINE, on_click=pick_date,
                                      tooltip="Escolher no calendário")
        time_f.suffix = ft.IconButton(ft.Icons.ACCESS_TIME_ROUNDED, icon_color=t.PINE, on_click=pick_time,
                                      tooltip="Escolher horário")
        fields = {"title": title_f, "description": desc_f, "date": date_f, "time": time_f}

        def save(_):
            for f in fields.values():
                f.error = None
            svc = self.ctx.services.appointments
            try:
                when = parse_date_br(date_f.value, "date")
                appointment = svc.build(title_f.value, desc_f.value, when, time_f.value,
                                        int(person_dd.value) if person_dd.value else None,
                                        existing.id if existing else None)
            except ValidationError as exc:
                target = fields.get(exc.field or "")
                if target:
                    target.error = str(exc)
                else:
                    self.ctx.notify.error(str(exc))
                dlg.update()
                return
            def after():
                close_dialog(dlg)
                self._select(appointment.date)
            self.ctx.run_safely(lambda: svc.save(appointment),
                                "Compromisso atualizado." if existing else "Compromisso cadastrado.", then=after)

        title_f.on_submit = save
        stacked = self.ctx.is_mobile
        date_time = ft.Column([date_f, time_f], spacing=12) if stacked else ft.Row([date_f, time_f], spacing=12)
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ft.Icons.EVENT_NOTE_ROUNDED, color=t.PINE),
                          ft.Text("Editar compromisso" if existing else "Novo compromisso", size=18,
                                  weight=ft.FontWeight.W_700)], spacing=10),
            content=ft.Container(ft.Column([title_f, desc_f, date_time, ft.Row([person_dd])], spacing=12,
                                           tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                                 width=480),
            scrollable=True,
            actions=[w.secondary_button("Cancelar", lambda _: close_dialog(dlg)),
                     w.primary_button("Salvar", save, ft.Icons.CHECK_ROUNDED)],
            shape=dialog_shape(),
            bgcolor=t.SURFACE,
            inset_padding=ft.Padding.symmetric(horizontal=12, vertical=24) if stacked else None,
        )
        page.show_dialog(dlg)

"""Módulo 3 — Cadastro e gerenciamento de pessoas (CRUD com fotografia)."""
from __future__ import annotations

import asyncio
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import flet as ft

from app.database.models import Person
from app.services.image_service import ALLOWED_EXTENSIONS, ImageProcessingError, process_photo
from app.ui import theme as t
from app.ui.components import widgets as w
from app.ui.components.camera import camera_supported, open_camera
from app.ui.components.feedback import Busy, close_dialog, confirm, dialog_shape
from app.ui.context import ModuleView
from app.utils.runtime import run_blocking
from app.utils.formatters import date_br, phone_br
from app.utils.validators import ValidationError, parse_date_br


class PeopleView(ModuleView):
    key = "people"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.term = ""
        self.list_holder: Optional[ft.Column] = None
        self.count_text: Optional[ft.Text] = None
        self._search_task: Optional[asyncio.Task] = None

    # ================= interface =================
    def build(self) -> ft.Control:
        mobile = self.ctx.is_mobile
        total = self.ctx.services.people.count()
        self.count_text = w.subtitle(self._count_caption(total))
        search = w.search_field("Buscar por nome, e-mail, telefone ou endereço", self._on_search, self.term,
                                expand=False)
        add_btn = w.primary_button("Nova pessoa" if not mobile else "Nova", lambda _: self._open_form(),
                                   ft.Icons.PERSON_ADD_ALT_1_ROUNDED)
        head = ft.Row([ft.Column([w.title("Pessoas", 20 if mobile else 22), self.count_text], spacing=2,
                                 expand=True, tight=True), add_btn])
        self.list_holder = ft.Column([self._list_content()], expand=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
        return ft.Column([head, search, self.list_holder], spacing=14, expand=True,
                         horizontal_alignment=ft.CrossAxisAlignment.STRETCH)

    @staticmethod
    def _count_caption(total: int) -> str:
        if total == 0:
            return "Nenhuma pessoa cadastrada"
        return f"{total} pessoa{'s' if total != 1 else ''} cadastrada{'s' if total != 1 else ''}"

    def _list_content(self) -> ft.Control:
        people = self.ctx.services.people.search(self.term)
        if not people:
            if self.term:
                return w.card(w.empty_state(ft.Icons.SEARCH_OFF_ROUNDED, "Nenhum resultado",
                                            f"Nada encontrado para “{self.term}”. Tente outro termo."))
            return w.card(w.empty_state(
                ft.Icons.GROUP_ADD_OUTLINED, "Seu cadastro está vazio",
                "Adicione pessoas com foto, contato, aniversário e endereço. Os aniversários aparecem no calendário.",
                w.primary_button("Cadastrar primeira pessoa", lambda _: self._open_form(), ft.Icons.ADD_ROUNDED)))
        if self.ctx.is_desktop:
            return self._table(people)
        return self._cards(people)

    def _thumb(self, p: Person, radius: int = 20) -> ft.Control:
        return w.avatar(p.initials, self.ctx.services.people.photo_bytes(p, thumb=True), radius)

    def _table(self, people: list[Person]) -> ft.Control:
        heading = ft.TextStyle(size=12, weight=ft.FontWeight.W_700, color=t.TEXT_MUTED, font_family=t.FONT)
        rows = []
        for p in people:
            age = p.age()
            birth = f"{date_br(p.birth_date)} ({age} anos)" if p.birth_date else "—"
            rows.append(ft.DataRow(
                cells=[
                    ft.DataCell(ft.Row([self._thumb(p, 18),
                                        ft.Text(p.full_name, size=14, weight=ft.FontWeight.W_600, color=t.TEXT)],
                                       spacing=12)),
                    ft.DataCell(ft.Text(phone_br(p.phone) or "—", size=13)),
                    ft.DataCell(ft.Text(p.email or "—", size=13, overflow=ft.TextOverflow.ELLIPSIS)),
                    ft.DataCell(ft.Text(birth, size=13)),
                    ft.DataCell(ft.Row([
                        w.ghost_icon(ft.Icons.VISIBILITY_OUTLINED, lambda _, x=p: self._show_details(x), "Detalhes",
                                     size=19),
                        w.ghost_icon(ft.Icons.EDIT_OUTLINED, lambda _, x=p: self._open_form(x), "Editar", size=19),
                        w.ghost_icon(ft.Icons.DELETE_OUTLINE_ROUNDED, lambda _, x=p: self._ask_delete(x), "Excluir",
                                     color=t.WINE, size=19),
                    ], spacing=0, tight=True)),
                ],
                on_select_change=lambda _, x=p: self._show_details(x),
            ))
        table = ft.DataTable(
            columns=[ft.DataColumn(ft.Text("NOME", style=heading)), ft.DataColumn(ft.Text("TELEFONE", style=heading)),
                     ft.DataColumn(ft.Text("E-MAIL", style=heading)),
                     ft.DataColumn(ft.Text("NASCIMENTO", style=heading)),
                     ft.DataColumn(ft.Text("AÇÕES", style=heading))],
            rows=rows,
            heading_row_color=t.SURFACE_ALT,
            heading_row_height=44,
            data_row_min_height=60,
            data_row_max_height=60,
            divider_thickness=0.6,
            horizontal_lines=ft.BorderSide(0.6, t.BORDER),
            column_spacing=28,
            show_checkbox_column=False,
            expand=True,
        )
        wide = self.ctx.width >= 1280
        inner: ft.Control = table if wide else ft.Row([table], scroll=ft.ScrollMode.AUTO)
        return w.card(ft.Column([inner], scroll=ft.ScrollMode.AUTO, expand=True,
                                horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                      padding=ft.Padding.symmetric(horizontal=8, vertical=8), expand=True)

    def _cards(self, people: list[Person]) -> ft.Control:
        tiles = []
        for p in people:
            line2 = " · ".join(x for x in [phone_br(p.phone), p.email] if x) or "Sem contato informado"
            badges: list[ft.Control] = []
            if p.has_birthday_on(date.today()):
                badges.append(w.pill("Aniversário hoje", t.WINE, t.WINE_SOFT, ft.Icons.CAKE_ROUNDED))
            tiles.append(ft.Container(
                ft.Row([
                    self._thumb(p, 24),
                    ft.Column([ft.Text(p.full_name, size=15, weight=ft.FontWeight.W_600, color=t.TEXT,
                                       no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                               ft.Text(line2, size=12, color=t.TEXT_MUTED, no_wrap=True,
                                       overflow=ft.TextOverflow.ELLIPSIS), *badges],
                              spacing=3, expand=True, tight=True),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT_ROUNDED, color=t.TEXT_FAINT),
                ], spacing=14),
                padding=14, border_radius=16, bgcolor=t.SURFACE, border=ft.Border.all(1, t.BORDER),
                shadow=t.shadow(1), on_click=lambda _, x=p: self._show_details(x),
            ))
        if self.ctx.layout == "tablet":
            return ft.GridView(tiles, max_extent=420, child_aspect_ratio=4.2, spacing=12, run_spacing=12,
                               expand=True)
        return ft.ListView(tiles, spacing=10, expand=True, padding=ft.Padding.only(bottom=16))

    def _reload_list(self) -> None:
        self.list_holder.controls = [self._list_content()]
        self.count_text.value = self._count_caption(self.ctx.services.people.count())
        try:
            self.list_holder.update()
            self.count_text.update()
        except Exception:
            pass

    # ================= busca (com pequeno atraso para não consultar a cada tecla) =================
    async def _on_search(self, e) -> None:
        self.term = e.control.value or ""
        if self._search_task and not self._search_task.done():
            self._search_task.cancel()

        async def delayed():
            await asyncio.sleep(0.25)
            self._reload_list()
        self._search_task = asyncio.create_task(delayed())

    # ================= detalhes =================
    def _show_details(self, p: Person) -> None:
        p = self.ctx.services.people.get(p.id) or p
        photo = self.ctx.services.people.photo_bytes(p)
        age = p.age()
        if photo:
            image: ft.Control = ft.Container(
                ft.Image(src=photo, width=132, height=132, fit=ft.BoxFit.COVER),
                width=132, height=132, border_radius=66, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                border=ft.Border.all(4, t.SURFACE), shadow=t.shadow(2))
        else:
            image = w.avatar(p.initials, None, 56)
        info = ft.Column([
            w.labeled_value("Telefone", phone_br(p.phone), ft.Icons.PHONE_OUTLINED),
            w.labeled_value("E-mail", p.email, ft.Icons.MAIL_OUTLINE_ROUNDED),
            w.labeled_value("Nascimento", f"{date_br(p.birth_date)}" + (f" · {age} anos" if age is not None else ""),
                            ft.Icons.CAKE_OUTLINED),
            w.labeled_value("Endereço", p.address, ft.Icons.PLACE_OUTLINED),
            w.labeled_value("Cadastrado em", _fmt_created(p.created_at), ft.Icons.HISTORY_ROUNDED),
        ], spacing=14, tight=True)

        def edit(_):
            close_dialog(dlg)
            self._open_form(p)

        def delete(_):
            close_dialog(dlg)
            self._ask_delete(p)

        dlg = ft.AlertDialog(
            content=ft.Container(ft.Column([
                ft.Container(ft.Column([image, ft.Text(p.full_name, size=20, weight=ft.FontWeight.W_700,
                                                       text_align=ft.TextAlign.CENTER)],
                                       horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12, tight=True),
                             alignment=ft.Alignment.CENTER, padding=ft.Padding.only(bottom=8)),
                ft.Divider(color=t.BORDER), info], tight=True, spacing=12), width=420),
            actions=[ft.TextButton("Excluir", icon=ft.Icons.DELETE_OUTLINE_ROUNDED, on_click=delete,
                                   style=ft.ButtonStyle(color=t.WINE)),
                     w.secondary_button("Fechar", lambda _: close_dialog(dlg)),
                     w.primary_button("Editar", edit, ft.Icons.EDIT_ROUNDED)],
            actions_alignment=ft.MainAxisAlignment.END,
            shape=dialog_shape(), bgcolor=t.SURFACE, scrollable=True,
            inset_padding=ft.Padding.symmetric(horizontal=12, vertical=24) if self.ctx.is_mobile else None,
        )
        self.page.show_dialog(dlg)

    def _ask_delete(self, p: Person) -> None:
        def do_delete():
            self.ctx.run_safely(lambda: self.ctx.services.people.delete(p.id), f"{p.full_name} foi excluído(a).",
                                then=self._reload_list)
        confirm(self.page, "Excluir cadastro?",
                f"Os dados e a foto de {p.full_name} serão removidos. Compromissos ligados a esta pessoa "
                "serão mantidos, sem o vínculo.", do_delete)

    # ================= formulário =================
    def _open_form(self, existing: Optional[Person] = None) -> None:
        page = self.page
        svc = self.ctx.services.people
        state = {"photo": None, "remove": False}  # bytes da nova foto / remoção solicitada
        current_photo = svc.photo_bytes(existing) if existing else None
        preview = ft.Container(width=104, height=104)

        def render_preview():
            data = state["photo"] or (None if state["remove"] else current_photo)
            initials = existing.initials if existing else "+"
            if data:
                preview.content = ft.Container(ft.Image(src=data, width=104, height=104, fit=ft.BoxFit.COVER),
                                               width=104, height=104, border_radius=52,
                                               clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                                               border=ft.Border.all(3, t.SURFACE), shadow=t.shadow(2))
            else:
                preview.content = ft.Container(
                    ft.Icon(ft.Icons.ADD_A_PHOTO_OUTLINED, color=t.PINE, size=32) if initials == "+" else
                    ft.Text(initials, size=34, weight=ft.FontWeight.W_700, color=t.PINE),
                    width=104, height=104, border_radius=52, bgcolor=t.PINE_SOFT, alignment=ft.Alignment.CENTER,
                    border=ft.Border.all(2, t.BORDER))
            remove_btn.visible = bool(data)

        async def accept_image(data: bytes):
            try:
                with Busy(page, "Tratando imagem…"):
                    # Pillow: corrige orientação, recorta, redimensiona e comprime (prévia já padronizada)
                    photo, _ = await run_blocking(process_photo, data)
            except ImageProcessingError as exc:
                self.ctx.notify.error(str(exc))
                return
            state["photo"], state["remove"] = photo, False
            render_preview()
            dlg.update()

        async def pick_gallery(_):
            try:
                files = await self.ctx.file_picker.pick_files(
                    dialog_title="Selecionar fotografia", file_type=ft.FilePickerFileType.CUSTOM,
                    allowed_extensions=ALLOWED_EXTENSIONS, with_data=page.web)
            except Exception as exc:
                self.ctx.notify.error(f"Não foi possível abrir a galeria: {exc}")
                return
            if not files:
                return
            f = files[0]
            try:
                data = f.bytes if f.bytes else await run_blocking(Path(f.path).read_bytes)
            except (OSError, TypeError) as exc:
                self.ctx.notify.error(f"Não foi possível ler o arquivo: {exc}")
                return
            await accept_image(data)

        async def take_photo(_):
            await open_camera(page, accept_image, self.ctx.notify.error)

        def remove_photo(_):
            state["photo"], state["remove"] = None, True
            render_preview()
            dlg.update()

        remove_btn = ft.TextButton("Remover foto", icon=ft.Icons.DELETE_OUTLINE_ROUNDED, on_click=remove_photo,
                                   style=ft.ButtonStyle(color=t.WINE))
        photo_buttons: list[ft.Control] = [w.secondary_button("Galeria", pick_gallery, ft.Icons.PHOTO_LIBRARY_OUTLINED)]
        if camera_supported(page):
            photo_buttons.append(w.secondary_button("Câmera", take_photo, ft.Icons.PHOTO_CAMERA_OUTLINED))
        render_preview()

        name_f = w.text_field("Nome completo *", existing.full_name if existing else "", ft.Icons.BADGE_OUTLINED,
                              max_length=120, capitalization=ft.TextCapitalization.WORDS, autofocus=not existing)
        phone_f = w.text_field("Telefone", phone_br(existing.phone) if existing else "", ft.Icons.PHONE_OUTLINED,
                               hint="(11) 98765-4321", keyboard_type=ft.KeyboardType.PHONE, expand=True)
        email_f = w.text_field("E-mail", existing.email if existing else "", ft.Icons.MAIL_OUTLINE_ROUNDED,
                               hint="nome@dominio.com", keyboard_type=ft.KeyboardType.EMAIL, expand=True)
        birth_f = w.text_field("Data de nascimento", date_br(existing.birth_date) if existing else "",
                               ft.Icons.CAKE_OUTLINED, hint="DD/MM/AAAA", keyboard_type=ft.KeyboardType.DATETIME)
        address_f = w.text_field("Endereço", existing.address if existing else "", ft.Icons.PLACE_OUTLINED,
                                 multiline=True, max_length=250)

        def pick_birth(_):
            def changed(e):
                if e.control.value:
                    v = e.control.value
                    birth_f.value = date_br(v.date() if isinstance(v, datetime) else v)
                    birth_f.error = None
                    birth_f.update()
            try:
                start = parse_date_br(birth_f.value, allow_empty=True) or date(1990, 1, 1)
            except ValidationError:
                start = date(1990, 1, 1)
            page.show_dialog(ft.DatePicker(value=datetime.combine(start, datetime.min.time()),
                                           first_date=datetime(1900, 1, 1), last_date=datetime.now(),
                                           date_picker_mode=ft.DatePickerMode.YEAR, on_change=changed,
                                           confirm_text="OK", cancel_text="Cancelar", help_text="Data de nascimento"))

        birth_f.suffix = ft.IconButton(ft.Icons.CALENDAR_MONTH_ROUNDED, icon_color=t.PINE, on_click=pick_birth,
                                       tooltip="Escolher data")
        fields = {"full_name": name_f, "phone": phone_f, "email": email_f, "birth_date": birth_f,
                  "address": address_f}

        async def save(_):
            for f in fields.values():
                f.error = None
            try:
                person = svc.build(name_f.value, phone_f.value, email_f.value, birth_f.value, address_f.value,
                                   existing.id if existing else None)
            except ValidationError as exc:
                if exc.field in fields:
                    fields[exc.field].error = str(exc)
                else:
                    self.ctx.notify.error(str(exc))
                dlg.update()
                return
            save_btn.disabled = True
            dlg.update()
            try:
                with Busy(page, "Salvando…"):
                    await run_blocking(svc.save, person, state["photo"], state["remove"])
            except (ImageProcessingError, ValidationError) as exc:
                save_btn.disabled = False
                dlg.update()
                self.ctx.notify.error(str(exc))
                return
            except Exception as exc:
                save_btn.disabled = False
                dlg.update()
                self.ctx.notify.error(f"Não foi possível salvar: {exc}")
                return
            close_dialog(dlg)
            self._reload_list()
            self.ctx.notify.success("Cadastro atualizado." if existing else "Pessoa cadastrada com sucesso.")

        save_btn = w.primary_button("Salvar", save, ft.Icons.CHECK_ROUNDED)
        stacked = self.ctx.is_mobile
        contact = ft.Column([phone_f, email_f], spacing=12) if stacked else ft.Row([phone_f, email_f], spacing=12)
        photo_block = ft.Row(
            [preview, ft.Column([ft.Text("Fotografia", size=14, weight=ft.FontWeight.W_600),
                                 ft.Text("JPG, PNG, WEBP… A imagem é recortada, redimensionada e comprimida.",
                                         size=12, color=t.TEXT_MUTED),
                                 ft.Row(photo_buttons, spacing=8), remove_btn],
                                spacing=6, expand=True, tight=True)],
            spacing=18,
        )
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ft.Icons.PERSON_ROUNDED, color=t.PINE),
                          ft.Text("Editar pessoa" if existing else "Nova pessoa", size=18,
                                  weight=ft.FontWeight.W_700)], spacing=10),
            content=ft.Container(ft.Column([photo_block, ft.Divider(color=t.BORDER), name_f, contact, birth_f,
                                            address_f], spacing=12, tight=True,
                                           horizontal_alignment=ft.CrossAxisAlignment.STRETCH), width=540),
            actions=[w.secondary_button("Cancelar", lambda _: close_dialog(dlg)), save_btn],
            shape=dialog_shape(), bgcolor=t.SURFACE, scrollable=True,
            inset_padding=ft.Padding.symmetric(horizontal=12, vertical=24) if stacked else None,
        )
        page.show_dialog(dlg)

    def on_show(self) -> None:
        self._reload_list()


def _fmt_created(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y às %H:%M")
    except (ValueError, TypeError):
        return value or "—"

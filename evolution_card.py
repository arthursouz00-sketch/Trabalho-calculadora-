"""Cartão "Conectar meu WhatsApp" (Evolution API): configuração, QR Code e status."""
from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from typing import Callable

import flet as ft

from app.services.whatsapp.evolution import EvolutionError, only_digits
from app.ui import theme as t
from app.ui.components import widgets as w
from app.ui.components.feedback import Busy, close_dialog, dialog_shape
from app.ui.context import AppContext
from app.utils.runtime import IS_BROWSER, run_blocking
from app.utils.formatters import phone_br


def _fmt_phone(number: str) -> str:
    d = only_digits(number)
    if d.startswith("55") and len(d) in (12, 13):
        return "+55 " + phone_br(d[2:])
    return f"+{d}" if d else "—"


class EvolutionCard:
    def __init__(self, ctx: AppContext, on_status_change: Callable[[], None]):
        self.ctx = ctx
        self.on_status_change = on_status_change
        self.state = "desconhecido"
        self.holder = ft.Container()

    @property
    def live(self):
        return self.ctx.services.live

    @property
    def page(self) -> ft.Page:
        return self.ctx.page

    # ================= interface =================
    def build(self) -> ft.Control:
        self.holder = ft.Container(self._content())
        return self.holder

    def _content(self) -> ft.Control:
        if IS_BROWSER:
            return w.card(ft.Column([
                w.section_header("Conectar meu WhatsApp", "Assistente financeiro no seu número via Evolution API"),
                w.pill("Indisponível na versão web de demonstração", "#8A6A2B", t.GOLD_SOFT, ft.Icons.INFO_OUTLINE),
                ft.Text("Esta versão roda inteira no navegador, que não pode receber webhooks. A conexão real "
                        "com o seu WhatsApp funciona no app instalado (python main.py) com a Evolution API — "
                        "veja docs/WHATSAPP_EVOLUTION.md. Aqui ao lado você pode testar o mesmo assistente "
                        "pela simulação.", size=12, color=t.TEXT_MUTED),
            ], spacing=12, tight=True), padding=16 if self.ctx.is_mobile else 22)
        cfg = self.live.config
        connected = self.state == "open"
        listening = self.live.listening
        server = self.live.server

        def pill(ok: bool, text: str, icon) -> ft.Container:
            return w.pill(text, t.PINE if ok else "#8A6A2B", t.PINE_SOFT if ok else t.GOLD_SOFT, icon)

        status = ft.Row([
            pill(connected, f"WhatsApp: {'conectado ' + _fmt_phone(cfg.owner_number) if connected else self._state_label()}",
                 ft.Icons.PHONE_IPHONE_ROUNDED),
            pill(listening, (f"Recebendo na porta {cfg.webhook_port}" + (f" · {server.received} evento(s)"
                                                                         if server and server.received else ""))
                 if listening else "Recebimento desligado", ft.Icons.SENSORS_ROUNDED),
        ], spacing=8, wrap=True)

        self.url_f = w.text_field("URL da Evolution API", cfg.base_url, ft.Icons.LINK_ROUNDED,
                                  hint="http://localhost:8080")
        self.key_f = w.text_field("API key (AUTHENTICATION_API_KEY)", cfg.api_key, ft.Icons.KEY_ROUNDED,
                                  password=True, can_reveal_password=True)
        self.inst_f = w.text_field("Nome da instância", cfg.instance, ft.Icons.DNS_OUTLINED, expand=True)
        self.port_f = w.text_field("Porta do webhook", str(cfg.webhook_port), ft.Icons.SETTINGS_ETHERNET_ROUNDED,
                                   keyboard_type=ft.KeyboardType.NUMBER, expand=True)
        self.host_f = w.text_field("Endereço deste computador visto pela Evolution", cfg.webhook_host,
                                   ft.Icons.COMPUTER_ROUNDED,
                                   hint="host.docker.internal (Docker no mesmo PC)")
        self.auth_f = w.text_field("Outros números autorizados (opcional)", cfg.authorized_numbers,
                                   ft.Icons.VERIFIED_USER_OUTLINED, hint="Ex.: 5511912345678, 5521998765432")
        self.auto_sw = ft.Switch(
            label="Salvar automaticamente (responda “desfazer” para cancelar)", value=cfg.auto_save,
            active_color=t.PINE, label_text_style=ft.TextStyle(size=13))
        pair = ft.Row([self.inst_f, self.port_f], spacing=10) if not self.ctx.is_mobile else \
            ft.Column([self.inst_f, self.port_f], spacing=10)

        settings_tile = ft.ExpansionTile(
            title=ft.Text("Configurações da Evolution API", size=13, weight=ft.FontWeight.W_600),
            subtitle=ft.Text("Valores do arquivo deploy/evolution/.env", size=11, color=t.TEXT_MUTED),
            controls=[ft.Column([self.url_f, self.key_f, pair, self.host_f, self.auth_f, self.auto_sw],
                                spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)],
            expanded=not cfg.api_key, tile_padding=ft.Padding.symmetric(horizontal=0),
            controls_padding=ft.Padding.only(bottom=8),
            shape=ft.RoundedRectangleBorder(radius=10), collapsed_shape=ft.RoundedRectangleBorder(radius=10),
        )

        buttons: list[ft.Control] = []
        if connected:
            buttons += [w.secondary_button("Enviar boas-vindas", self._welcome, ft.Icons.WAVING_HAND_OUTLINED),
                        w.secondary_button("Salvar", self._save_only, ft.Icons.SAVE_OUTLINED)]
        else:
            buttons.append(w.primary_button("Conectar meu WhatsApp", self._connect, ft.Icons.QR_CODE_2_ROUNDED))
        buttons.append(w.ghost_icon(ft.Icons.REFRESH_ROUNDED, self._check, "Verificar conexão", color=t.PINE))
        if listening or cfg.enabled:
            buttons.append(w.ghost_icon(ft.Icons.POWER_SETTINGS_NEW_ROUNDED, self._disable,
                                        "Desligar recebimento", color=t.WINE))

        how = ft.Text(
            "Depois de conectar, abra no seu WhatsApp a conversa “Mensagem para mim mesmo” (seu próprio "
            "número) e escreva, por exemplo: “Comprei um lanche foi 3 reais”. Só essa conversa é lida — "
            "as demais são ignoradas.", size=12, color=t.TEXT_MUTED)

        return w.card(ft.Column([
            w.section_header("Conectar meu WhatsApp", "Assistente financeiro no seu número via Evolution API"),
            status, how, settings_tile, ft.Row(buttons, spacing=8),
        ], spacing=12, tight=True), padding=16 if self.ctx.is_mobile else 22)

    def _state_label(self) -> str:
        return {"connecting": "aguardando QR Code", "close": "desconectado", "not_found": "instância não criada",
                "erro": "Evolution API inacessível"}.get(self.state, "não verificado")

    def rerender(self) -> None:
        self.holder.content = self._content()
        try:
            self.holder.update()
        except Exception:
            pass
        self.on_status_change()

    # ================= ações =================
    def _read_form(self):
        try:
            port = int(only_digits(self.port_f.value) or "0")
        except ValueError:
            port = 0
        if not 1024 <= port <= 65535:
            raise EvolutionError("Porta do webhook inválida (use entre 1024 e 65535).")
        url = (self.url_f.value or "").strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise EvolutionError("A URL deve começar com http:// ou https://")
        if not (self.key_f.value or "").strip():
            raise EvolutionError("Informe a API key da Evolution API.")
        inst = (self.inst_f.value or "").strip()
        if not inst:
            raise EvolutionError("Informe o nome da instância.")
        return replace(self.live.config, base_url=url, api_key=self.key_f.value.strip(), instance=inst,
                       webhook_port=port, webhook_host=(self.host_f.value or "").strip() or "host.docker.internal",
                       authorized_numbers=self.auth_f.value or "", auto_save=bool(self.auto_sw.value))

    async def _save_only(self, _=None) -> None:
        try:
            cfg = self._read_form()
            self.live.save(cfg)
            if cfg.enabled:
                await run_blocking(self.live.activate)
                await run_blocking(self.live.client.set_webhook)
        except (EvolutionError, RuntimeError) as exc:
            self.ctx.notify.error(str(exc))
            return
        self.ctx.notify.success("Configurações salvas.")
        self.rerender()

    async def _check(self, _=None) -> None:
        try:
            self.state = await run_blocking(self.live.client.connection_state)
            if self.state == "open":
                await run_blocking(self.live.refresh_owner)
        except EvolutionError as exc:
            self.state = "erro"
            self.ctx.notify.error(str(exc))
        self.rerender()

    async def _disable(self, _=None) -> None:
        cfg = replace(self.live.config, enabled=False)
        self.live.save(cfg)
        self.live.deactivate()
        self.ctx.notify.info("Recebimento de mensagens do WhatsApp desligado.")
        self.rerender()

    async def _welcome(self, _=None) -> None:
        try:
            await run_blocking(self.live.send_welcome)
        except Exception as exc:
            self.ctx.notify.error(f"Não foi possível enviar: {exc}")
            return
        self.ctx.notify.success("Mensagem enviada para o seu WhatsApp.")
        self.on_status_change()

    async def _connect(self, _=None) -> None:
        try:
            cfg = replace(self._read_form(), enabled=True)
        except EvolutionError as exc:
            self.ctx.notify.error(str(exc))
            return
        self.live.save(cfg)
        try:
            with Busy(self.page, "Conectando à Evolution API…"):
                await run_blocking(self.live.activate)       # servidor de webhook local
                self.state = await run_blocking(self.live.setup)  # instância + webhook
        except (EvolutionError, RuntimeError) as exc:
            self.state = "erro"
            self.rerender()
            self.ctx.notify.error(str(exc))
            return
        if self.state == "open":
            await run_blocking(self.live.refresh_owner)
            self.ctx.notify.success("WhatsApp já está conectado. Recebimento ativado!")
            self.rerender()
            return
        self.rerender()
        await self._qr_dialog()

    async def _qr_dialog(self) -> None:
        page = self.page
        qr_box = ft.Container(ft.ProgressRing(color=t.PINE), width=280, height=280, alignment=ft.Alignment.CENTER,
                              bgcolor=t.SURFACE, border_radius=12, border=ft.Border.all(1, t.BORDER))
        status = ft.Text("Gerando QR Code…", size=13, color=t.TEXT_MUTED, text_align=ft.TextAlign.CENTER)
        phone_f = w.text_field("Ou conecte com código: seu número com DDD", "", ft.Icons.PHONE_ROUNDED,
                               hint="5511987654321", keyboard_type=ft.KeyboardType.PHONE)
        code_txt = ft.Text("", size=26, weight=ft.FontWeight.W_700, color=t.PINE, selectable=True,
                           text_align=ft.TextAlign.CENTER)
        running = {"on": True}

        def stop(_=None):
            running["on"] = False
            close_dialog(dlg)

        async def load_qr(number: str = ""):
            try:
                result = await run_blocking(self.live.client.connect, number)
            except EvolutionError as exc:
                status.value = str(exc)
                dlg.update()
                return
            if result["pairing_code"]:
                code_txt.value = result["pairing_code"]
                status.value = ("No celular: WhatsApp › Aparelhos conectados › Conectar aparelho › "
                                "Conectar com número de telefone, e digite o código acima.")
            if result["qr_png"]:
                qr_box.content = ft.Image(src=result["qr_png"], width=264, height=264, fit=ft.BoxFit.CONTAIN)
                if not result["pairing_code"]:
                    status.value = ("No celular: WhatsApp › Aparelhos conectados › Conectar aparelho, "
                                    "e aponte para o QR Code.")
            elif not result["pairing_code"]:
                qr_box.content = ft.Icon(ft.Icons.HOURGLASS_EMPTY_ROUNDED, color=t.TEXT_FAINT, size=40)
                status.value = "A Evolution ainda não gerou o QR Code. Tentando de novo…"
            dlg.update()

        async def pairing(_):
            if len(only_digits(phone_f.value)) < 12:
                phone_f.error = "Use o formato 55 + DDD + número"
                dlg.update()
                return
            phone_f.error = None
            await load_qr(phone_f.value)

        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row([ft.Icon(ft.Icons.QR_CODE_2_ROUNDED, color=t.PINE),
                          ft.Text("Conectar meu WhatsApp", size=18, weight=ft.FontWeight.W_700)], spacing=10),
            content=ft.Container(ft.Column([
                ft.Row([qr_box], alignment=ft.MainAxisAlignment.CENTER), code_txt, status,
                ft.Divider(color=t.BORDER), phone_f,
                ft.Row([w.secondary_button("Gerar código", pairing, ft.Icons.PIN_OUTLINED)],
                       alignment=ft.MainAxisAlignment.END),
            ], spacing=10, tight=True, horizontal_alignment=ft.CrossAxisAlignment.STRETCH), width=420),
            actions=[w.secondary_button("Fechar", stop)],
            shape=dialog_shape(), bgcolor=t.SURFACE, scrollable=True,
            inset_padding=ft.Padding.symmetric(horizontal=12, vertical=24) if self.ctx.is_mobile else None,
        )
        page.show_dialog(dlg)
        await load_qr()
        last_qr = time.monotonic()
        deadline = time.monotonic() + 300
        while running["on"] and time.monotonic() < deadline:
            await asyncio.sleep(3)
            if not running["on"]:
                return
            try:
                self.state = await run_blocking(self.live.client.connection_state)
            except EvolutionError:
                continue
            if self.state == "open":
                running["on"] = False
                close_dialog(dlg)
                await run_blocking(self.live.refresh_owner)
                try:
                    await run_blocking(self.live.send_welcome)
                except Exception:
                    pass
                self.ctx.notify.success("WhatsApp conectado! Escreva na conversa “Mensagem para mim mesmo”.")
                self.rerender()
                return
            if time.monotonic() - last_qr > 25 and not code_txt.value:  # QR expira em ~40 s
                await load_qr()
                last_qr = time.monotonic()
        if running["on"]:
            close_dialog(dlg)
            self.ctx.notify.info("Tempo esgotado. Clique em “Conectar meu WhatsApp” para tentar de novo.")

    async def initial_check(self) -> None:
        if IS_BROWSER:
            return
        if self.live.config.enabled and self.live.config.api_key:
            await self._check()

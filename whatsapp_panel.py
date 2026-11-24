"""Painel do WhatsApp: conversa em tempo real + conexão com o seu número.

* Com a Evolution API conectada, as mensagens que você escreve na conversa
  "Mensagem para mim mesmo" aparecem aqui em tempo real, junto com as
  respostas do assistente.
* Sem conexão (ou como reserva na apresentação), o campo de texto simula o
  recebimento no formato do webhook da WhatsApp Cloud API.
"""
from __future__ import annotations

import json
from typing import Callable, Optional

import flet as ft

from app.database.models import EXPENSE, INCOME, Transaction
from app.services.whatsapp import ChatItem
from app.services.whatsapp.gateway import WebhookFormatError
from app.ui import theme as t
from app.ui.components import widgets as w
from app.ui.components.feedback import confirm
from app.ui.context import AppContext
from app.modules.finance.evolution_card import EvolutionCard
from app.modules.finance.transaction_form import open_transaction_form
from app.utils.formatters import date_br, money

EXAMPLES = [
    "Gastei R$ 45,00 no mercado hoje.",
    "Recebi 3.500 de salário",
    "Paguei 120,50 da conta de luz ontem",
    "Uber 23,90",
    "Comprei presentes de Natal por 250 reais",
]

CHAT_BG = "#EEF2EF"
BUBBLE_OUT = "#DCEFE3"


class WhatsAppPanel:
    def __init__(self, ctx: AppContext, on_change: Callable[[], None]):
        self.ctx = ctx
        self.on_change = on_change  # avisa a tela de finanças para recalcular saldos
        self.last_payload: Optional[dict] = None
        self.messages_col: Optional[ft.ListView] = None
        self.input: Optional[ft.TextField] = None
        self.payload_view: Optional[ft.Container] = None
        self.evo = EvolutionCard(ctx, on_status_change=self._refresh_header)
        self.sub_text: Optional[ft.Text] = None
        self.banner_text: Optional[ft.Text] = None
        self._checked = False

    @property
    def automation(self):
        return self.ctx.services.whatsapp

    # ================= interface =================
    def build(self) -> ft.Control:
        chat = self._chat()
        evo = self.evo.build()
        if not self._checked:
            self._checked = True
            self.ctx.page.run_task(self.evo.initial_check)
        if self.ctx.is_desktop:
            return ft.Row([ft.Container(chat, width=460),
                           ft.Column([evo, self._explainer()], spacing=18, expand=True)],
                          spacing=22, vertical_alignment=ft.CrossAxisAlignment.START, expand=True)
        return ft.Column([evo, chat, self._explainer()], spacing=14)

    def _live_on(self) -> bool:
        return self.ctx.services.live.listening

    def _header_texts(self) -> tuple[str, str]:
        if self._live_on():
            return ("Conectado ao seu WhatsApp · tempo real",
                    "Escreva na conversa “Mensagem para mim mesmo”. O campo abaixo continua simulando.")
        return ("WhatsApp · ambiente de testes", "Simulação local: nenhuma mensagem real é enviada ou lida.")

    def _refresh_header(self) -> None:
        if not self.sub_text:
            return
        self.sub_text.value, self.banner_text.value = self._header_texts()
        try:
            self.sub_text.update()
            self.banner_text.update()
        except Exception:
            pass

    def reload(self) -> None:
        """Atualiza a conversa (chamado quando chega mensagem real)."""
        self._reload()
        self.evo.rerender()

    def _chat(self) -> ft.Control:
        mobile = self.ctx.is_mobile
        self.messages_col = ft.ListView(spacing=8, padding=14, auto_scroll=True, expand=True)
        self._fill_messages()
        self.input = ft.TextField(
            hint_text="Digite uma mensagem de teste…", border_radius=22, filled=True, fill_color=t.SURFACE,
            border_color=t.BORDER, focused_border_color=t.PINE, text_size=14, expand=True,
            content_padding=ft.Padding.symmetric(horizontal=16, vertical=10), on_submit=self._send,
            max_length=300, counter="",
        )
        send = ft.IconButton(ft.Icons.SEND_ROUNDED, icon_color=t.SURFACE, bgcolor=t.PINE, on_click=self._send,
                             tooltip="Enviar (simulado)",
                             style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=12))
        chips = ft.Row([
            ft.Container(ft.Text(ex, size=12, color=t.PINE), bgcolor=t.SURFACE, border_radius=16,
                         border=ft.Border.all(1, "#CFE0D5"), padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                         on_click=lambda _, m=ex: self._send_text(m), tooltip="Enviar este exemplo")
            for ex in EXAMPLES
        ], spacing=6, scroll=ft.ScrollMode.AUTO)
        sub, banner = self._header_texts()
        self.sub_text = ft.Text(sub, size=11, color=ft.Colors.with_opacity(0.75, t.SURFACE))
        self.banner_text = ft.Text(banner, size=12, color="#6F5520", expand=True)
        top = ft.Container(
            ft.Row([
                ft.Container(ft.Icon(ft.Icons.SMART_TOY_OUTLINED, color=t.SURFACE, size=20), bgcolor=t.PINE,
                             border_radius=20, padding=8),
                ft.Column([ft.Text("Assistente Financeiro", size=14, weight=ft.FontWeight.W_700, color=t.SURFACE),
                           self.sub_text], spacing=0, tight=True, expand=True),
                ft.IconButton(ft.Icons.DELETE_SWEEP_OUTLINED, icon_color=t.SURFACE, tooltip="Limpar conversa",
                              on_click=self._ask_clear),
            ], spacing=10),
            gradient=ft.LinearGradient(colors=[t.PINE_DARK, t.PINE], begin=ft.Alignment.CENTER_LEFT,
                                       end=ft.Alignment.CENTER_RIGHT),
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
        )
        sandbox = ft.Container(
            ft.Row([ft.Icon(ft.Icons.SCIENCE_OUTLINED, size=16, color="#8A6A2B"),
                    self.banner_text], spacing=8),
            bgcolor=t.GOLD_SOFT, padding=ft.Padding.symmetric(horizontal=14, vertical=8),
        )
        bottom = ft.Container(ft.Column([chips, ft.Row([self.input, send], spacing=8)], spacing=8, tight=True),
                              padding=ft.Padding.only(left=12, right=12, top=8, bottom=12), bgcolor=CHAT_BG)
        return ft.Container(
            ft.Column([top, sandbox, ft.Container(self.messages_col, expand=True, bgcolor=CHAT_BG), bottom],
                      spacing=0, expand=True),
            height=540 if mobile else 560,
            border_radius=t.RADIUS_LG, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            border=ft.Border.all(1, t.BORDER), shadow=t.shadow(2), bgcolor=CHAT_BG,
        )

    def _fill_messages(self) -> None:
        try:
            items = self.automation.history()
        except Exception as exc:
            self.messages_col.controls = [ft.Text(f"Erro ao carregar conversa: {exc}", color=t.WINE)]
            return
        if not items:
            self.messages_col.controls = [ft.Container(
                ft.Column([
                    ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE_ROUNDED, color=t.PINE, size=34),
                    ft.Text("Envie uma mensagem de teste", size=14, weight=ft.FontWeight.W_600, color=t.TEXT),
                    ft.Text("Ex.: “Gastei R$ 45,00 no mercado hoje.” A automação vai sugerir um lançamento "
                            "para você confirmar.", size=12, color=t.TEXT_MUTED, text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8, tight=True),
                padding=30, alignment=ft.Alignment.CENTER)]
            return
        self.messages_col.controls = [self._bubble(item) for item in items]

    def _bubble(self, item: ChatItem) -> ft.Control:
        m = item.message
        incoming = m.direction == "in"  # mensagem do "usuário" para o número de testes
        time_txt = m.created_at[11:16] if m.created_at else ""
        status_icon: list[ft.Control] = []
        if incoming:
            icon, color, tip = {
                "confirmed": (ft.Icons.TASK_ALT_ROUNDED, t.INCOME, "Lançado no financeiro"),
                "discarded": (ft.Icons.DO_NOT_DISTURB_ON_OUTLINED, t.TEXT_FAINT, "Descartado"),
                "ignored": (ft.Icons.HELP_OUTLINE_ROUNDED, t.TEXT_FAINT, "Sem valor identificado"),
                "pending": (ft.Icons.PENDING_OUTLINED, t.GOLD, "Aguardando confirmação"),
            }.get(m.status, (ft.Icons.DONE_ALL_ROUNDED, t.TEXT_FAINT, ""))
            status_icon = [ft.Icon(icon, size=14, color=color, tooltip=tip)]
            if m.external_id.startswith("evo."):
                status_icon.insert(0, ft.Icon(ft.Icons.PHONE_IPHONE_ROUNDED, size=12, color=t.PINE,
                                              tooltip="Recebida do seu WhatsApp"))
        bubble = ft.Container(
            ft.Column([
                ft.Text(m.body, size=14, color=t.TEXT, selectable=True),
                ft.Row([ft.Text(time_txt, size=10, color=t.TEXT_FAINT), *status_icon], spacing=4, tight=True,
                       alignment=ft.MainAxisAlignment.END),
            ], spacing=3, tight=True, horizontal_alignment=ft.CrossAxisAlignment.END),
            bgcolor=BUBBLE_OUT if incoming else t.SURFACE,
            border_radius=ft.BorderRadius.only(top_left=14, top_right=14, bottom_left=14 if incoming else 4,
                                               bottom_right=4 if incoming else 14),
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            shadow=[ft.BoxShadow(blur_radius=2, color="#14000000", offset=ft.Offset(0, 1))],
        )
        # Column (e não Row) limita a largura: textos longos quebram linha dentro do balão
        aligned = ft.Column([bubble], horizontal_alignment=ft.CrossAxisAlignment.END if incoming
                            else ft.CrossAxisAlignment.START, tight=True)
        bubble_wrap = ft.Container(aligned, padding=ft.Padding.only(left=48 if incoming else 0,
                                                                   right=0 if incoming else 48))
        if item.suggestion and m.status == "pending":
            return ft.Column([bubble_wrap, self._suggestion_card(item)], spacing=8, tight=True)
        return bubble_wrap

    def _suggestion_card(self, item: ChatItem) -> ft.Control:
        s = item.suggestion
        is_income = s.kind == INCOME
        color = t.INCOME if is_income else t.WINE

        def line(label: str, value: str, bold: bool = False) -> ft.Row:
            return ft.Row([ft.Text(label, size=12, color=t.TEXT_MUTED, width=82),
                           ft.Text(value, size=13, color=t.TEXT, expand=True,
                                   weight=ft.FontWeight.W_700 if bold else ft.FontWeight.W_500)], spacing=8)

        notes = [ft.Text(f"• {n}", size=11, color="#8A6A2B") for n in s.notes]
        conf_pct = int(s.confidence * 100)
        return ft.Container(
            ft.Column([
                ft.Row([ft.Icon(ft.Icons.AUTO_AWESOME_ROUNDED, size=16, color=t.GOLD),
                        ft.Text("Sugestão de lançamento", size=13, weight=ft.FontWeight.W_700, color=t.TEXT,
                                expand=True),
                        w.pill(f"confiança {conf_pct}%", t.PINE if conf_pct >= 70 else "#8A6A2B",
                               t.PINE_SOFT if conf_pct >= 70 else t.GOLD_SOFT)]),
                line("Tipo", "Entrada" if is_income else "Despesa"),
                line("Categoria", s.category),
                line("Valor", money(s.amount_cents), bold=True),
                line("Descrição", s.description),
                line("Data", date_br(s.date)),
                *notes,
                ft.Row([
                    ft.TextButton("Descartar", on_click=lambda _, i=item: self._discard(i),
                                  style=ft.ButtonStyle(color=t.WINE)),
                    w.ghost_icon(ft.Icons.EDIT_OUTLINED, lambda _, i=item: self._edit(i), "Editar antes de salvar",
                                 color=t.PINE),
                    w.primary_button("Confirmar", lambda _, i=item: self._confirm(i), ft.Icons.CHECK_ROUNDED),
                ], spacing=6, alignment=ft.MainAxisAlignment.END),
            ], spacing=6, tight=True),
            bgcolor=t.SURFACE, border_radius=14, padding=14,
            border=ft.Border.only(left=ft.BorderSide(4, color)), shadow=t.shadow(1),
            margin=ft.Margin.only(left=24),
        )

    def _explainer(self) -> ft.Control:
        steps = [
            (ft.Icons.MARK_CHAT_UNREAD_OUTLINED, "Mensagem recebida",
             "O provedor envia um webhook (formato WhatsApp Cloud API)."),
            (ft.Icons.PSYCHOLOGY_OUTLINED, "Interpretação",
             "Regras identificam valor, tipo, categoria, data e descrição."),
            (ft.Icons.FACT_CHECK_OUTLINED, "Sugestão + confirmação",
             "Nada é gravado sem você confirmar, editar ou descartar."),
            (ft.Icons.STORAGE_ROUNDED, "Lançamento no SQLite",
             "O registro entra no financeiro com origem “WhatsApp”."),
        ]
        step_controls = []
        for i, (icon, title, text) in enumerate(steps, start=1):
            step_controls.append(ft.Row([
                ft.Container(ft.Text(str(i), size=13, weight=ft.FontWeight.W_700, color=t.PINE), width=30, height=30,
                             border_radius=15, bgcolor=t.PINE_SOFT, alignment=ft.Alignment.CENTER),
                ft.Column([ft.Row([ft.Icon(icon, size=16, color=t.PINE),
                                   ft.Text(title, size=14, weight=ft.FontWeight.W_600)], spacing=6),
                           ft.Text(text, size=12, color=t.TEXT_MUTED)], spacing=2, expand=True, tight=True),
            ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START))
        self.payload_view = ft.Container(
            ft.Text(self._payload_text(), size=11, font_family="monospace", color="#D8E6DD", selectable=True),
            bgcolor="#14231C", border_radius=12, padding=14,
        )
        gateway = self.automation.gateway
        return w.card(ft.Column([
            w.section_header("Como funciona a integração", "Arquitetura pronta para conectar a uma API oficial"),
            *step_controls,
            ft.Divider(color=t.BORDER),
            ft.Row([w.pill(f"Provedor: {gateway.name}", t.PINE, t.PINE_SOFT, ft.Icons.HUB_OUTLINED),
                    w.pill("Sem envio real", "#8A6A2B", t.GOLD_SOFT, ft.Icons.SHIELD_OUTLINED)], spacing=8, wrap=True),
            ft.ExpansionTile(
                title=ft.Text("Último webhook recebido (JSON)", size=13, weight=ft.FontWeight.W_600),
                subtitle=ft.Text("Payload no mesmo formato enviado pela Meta", size=11, color=t.TEXT_MUTED),
                controls=[self.payload_view], tile_padding=ft.Padding.symmetric(horizontal=0),
                shape=ft.RoundedRectangleBorder(radius=10), collapsed_shape=ft.RoundedRectangleBorder(radius=10),
            ),
            ft.Text("Para produção seria necessário: conta WhatsApp Business verificada, token da Cloud API, "
                    "endpoint HTTPS público para o webhook e consentimento dos usuários.",
                    size=11, color=t.TEXT_FAINT),
        ], spacing=14, tight=True), padding=16 if self.ctx.is_mobile else 22)

    def _payload_text(self) -> str:
        if not self.last_payload:
            return "Envie uma mensagem para visualizar o payload."
        return json.dumps(self.last_payload, indent=2, ensure_ascii=False)

    # ================= ações =================
    def _send(self, _=None) -> None:
        text = (self.input.value or "").strip()
        if not text:
            self.ctx.notify.info("Digite uma mensagem para simular o recebimento.")
            return
        self.input.value = ""
        self._send_text(text)

    def _send_text(self, text: str) -> None:
        gateway = self.automation.gateway
        try:
            payload = gateway.build_incoming_payload(text)
            self.last_payload = payload
            self.automation.handle_webhook(payload)
        except WebhookFormatError as exc:
            self.ctx.notify.error(str(exc))
            return
        except Exception as exc:
            self.ctx.notify.error(f"Falha ao processar a mensagem: {exc}")
            return
        self._reload()

    def _reload(self) -> None:
        self._fill_messages()
        if self.payload_view:
            self.payload_view.content.value = self._payload_text()
        try:
            self.messages_col.update()
            if self.payload_view:
                self.payload_view.update()
            self.input.update()
        except Exception:
            pass

    def _to_transaction(self, item: ChatItem) -> Transaction:
        s = item.suggestion
        return self.ctx.services.finance.build(
            s.kind, s.description, f"{s.amount_cents / 100:.2f}", s.category, s.date, source="whatsapp")

    def _confirm(self, item: ChatItem) -> None:
        def action():
            self.automation.confirm(item.message.id, self._to_transaction(item))

        def after():
            self._reload()
            self.on_change()

        self.ctx.run_safely(action, "Lançamento confirmado e salvo no financeiro.", then=after)

    def _edit(self, item: ChatItem) -> None:
        s = item.suggestion
        draft = Transaction(kind=s.kind if s.kind in (INCOME, EXPENSE) else EXPENSE, description=s.description,
                            amount_cents=s.amount_cents, category=s.category, date=s.date, source="whatsapp")
        banner = ft.Container(
            ft.Row([ft.Icon(ft.Icons.CHAT_OUTLINED, size=16, color=t.PINE),
                    ft.Text(f"“{item.message.body}”", size=12, color=t.TEXT_MUTED, italic=True, expand=True)],
                   spacing=8),
            bgcolor=t.PINE_SOFT, border_radius=10, padding=10)

        def saved(_tx):
            self._reload()
            self.on_change()

        open_transaction_form(self.ctx, draft, on_saved=saved, title="Revisar sugestão",
                              save_handler=lambda tx: self.automation.confirm(item.message.id, tx), banner=banner)

    def _discard(self, item: ChatItem) -> None:
        self.ctx.run_safely(lambda: self.automation.discard(item.message.id), "Sugestão descartada.",
                            then=self._reload)

    def _ask_clear(self, _) -> None:
        def clear():
            self.last_payload = None
            self.ctx.run_safely(self.automation.clear_history, "Conversa de testes apagada.", then=self._reload)
        confirm(self.page, "Limpar conversa?",
                "As mensagens de teste serão apagadas. Lançamentos já confirmados continuam no financeiro.",
                clear, confirm_text="Limpar")

    @property
    def page(self) -> ft.Page:
        return self.ctx.page

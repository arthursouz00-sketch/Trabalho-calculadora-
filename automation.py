"""Automação: webhook -> interpretação -> sugestão -> confirmação -> lançamento.

Dois canais usam o mesmo fluxo:
* **Sandbox** (simulação dentro do app): a sugestão aparece no painel e é
  confirmada por botão.
* **WhatsApp real (Evolution API)**: você escreve na conversa "Mensagem para
  mim mesmo" e o assistente responde no próprio WhatsApp. Com ``auto_save``
  o lançamento é salvo na hora (responda *desfazer* para cancelar); sem ele,
  o assistente pede *sim* / *não* antes de salvar.
"""
from __future__ import annotations

import logging
import threading
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Optional

from app.database.connection import DatabaseError
from app.database.models import ChatMessage, Transaction, TransactionSuggestion
from app.database.repositories import MessageRepository
from app.services.finance_service import FinanceService, categories_for
from app.services.whatsapp.gateway import MessagingGateway, parse_webhook
from app.services.whatsapp.interpreter import interpret
from app.utils.formatters import MONTHS, date_br, money

log = logging.getLogger("visual_office.whatsapp")

BOT_MARK = "🤖"  # toda resposta do assistente começa com isto (evita responder a si mesmo)

HELP_TEXT = (
    f"{BOT_MARK} *Visual Office — assistente financeiro*\n"
    "Escreva seus gastos e ganhos do jeito que falaria:\n"
    "• _Comprei um lanche foi 3 reais_\n"
    "• _Paguei 120,50 de luz ontem_\n"
    "• _Recebi 3.500 de salário_\n\n"
    "Comandos: *saldo* · *extrato* · *desfazer* · *ajuda*"
)


@dataclass
class ChatItem:
    message: ChatMessage
    suggestion: Optional[TransactionSuggestion] = None


def _norm(text: str) -> str:
    text = "".join(c for c in unicodedata.normalize("NFD", text.lower()) if unicodedata.category(c) != "Mn")
    return text.strip(" .!?*_")


YES = {"sim", "s", "ok", "confirmar", "confirmo", "confirma", "pode salvar", "salvar", "isso"}
NO = {"nao", "n", "cancelar", "cancela", "descartar", "descarta"}


class WhatsAppAutomation:
    def __init__(self, gateway: MessagingGateway, messages: MessageRepository, finance: FinanceService):
        self.gateway = gateway              # sandbox (simulação)
        self.live_gateway: Optional[MessagingGateway] = None  # Evolution API, quando conectada
        self.live_config = None             # EvolutionConfig ativo
        self.messages = messages
        self.finance = finance
        self._lock = threading.Lock()
        self._listeners: list[Callable[[str], None]] = []

    # ---------- avisos para a interface ----------
    def add_listener(self, callback: Callable[[str], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[str], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify(self, summary: str) -> None:
        for cb in list(self._listeners):
            try:
                cb(summary)
            except Exception:
                log.exception("Listener falhou")

    # ---------- entrada: sandbox ----------
    def handle_webhook(self, payload: dict[str, Any]) -> list[ChatItem]:
        """Processa um webhook no formato da Cloud API (sandbox). Repetidas são ignoradas."""
        items = []
        for incoming in parse_webhook(payload):
            if self.messages.exists(incoming.external_id):
                continue
            suggestion = interpret(incoming.body, date.fromtimestamp(incoming.timestamp))
            msg = ChatMessage(
                external_id=incoming.external_id, direction="in", sender=incoming.sender,
                body=incoming.body, status="pending" if suggestion else "ignored",
            )
            msg.id = self.messages.add(msg)
            items.append(ChatItem(msg, suggestion))
            if suggestion is None:
                self._reply(incoming.sender, "Não encontrei um valor nessa mensagem. "
                                             "Tente algo como: \"Gastei R$ 45,00 no mercado hoje\".")
        return items

    def simulate_incoming(self, body: str) -> list[ChatItem]:
        """Somente no sandbox: gera o payload de teste e o processa como webhook."""
        build = getattr(self.gateway, "build_incoming_payload", None)
        if not self.gateway.is_sandbox or build is None:
            raise RuntimeError("Simulação disponível apenas no ambiente de testes.")
        return self.handle_webhook(build(body))

    # ---------- entrada: WhatsApp real (Evolution API) ----------
    def handle_evolution_webhook(self, payload: dict[str, Any]) -> list[str]:
        """Processa um webhook ``messages.upsert`` da Evolution API. Retorna resumos do que foi feito."""
        from app.services.whatsapp.evolution import parse_evolution_webhook  # import tardio

        cfg = self.live_config
        if cfg is None or self.live_gateway is None:
            return []
        accepted, owner = parse_evolution_webhook(payload, cfg)
        if owner and not cfg.owner_number:
            cfg.owner_number = owner
        done: list[str] = []
        with self._lock:  # webhooks chegam em threads paralelas
            for m in accepted:
                raw_id = m.external_id.removeprefix("evo.")
                if m.body.startswith(BOT_MARK) or raw_id in getattr(self.live_gateway, "sent_ids", set()):
                    continue  # resposta do próprio assistente
                if self.messages.exists(m.external_id):
                    continue  # webhook repetido
                try:
                    done.append(self._process_live(m))
                except DatabaseError as exc:  # ex.: duplicado em corrida
                    log.warning("Mensagem ignorada: %s", exc)
                except Exception as exc:
                    log.exception("Falha ao processar mensagem")
                    self._safe_live_reply(m.chat_number, f"{BOT_MARK} Não consegui processar: {exc}")
        for summary in done:
            self._notify(summary)
        return done

    def _process_live(self, m) -> str:
        cfg = self.live_config
        chat = m.chat_number
        cmd = _norm(m.body)
        ref_day = date.fromtimestamp(m.timestamp)

        def store(status: str, tx_id: Optional[int] = None) -> int:
            return self.messages.add(ChatMessage(external_id=m.external_id, direction="in", sender=chat,
                                                 body=m.body, status=status, transaction_id=tx_id))

        if cmd in ("ajuda", "menu", "help", "comandos", "oi", "ola"):
            store("ignored")
            self._safe_live_reply(chat, HELP_TEXT)
            return "Ajuda enviada no WhatsApp"
        if cmd == "saldo":
            store("ignored")
            self._safe_live_reply(chat, self._balance_text())
            return "Saldo enviado no WhatsApp"
        if cmd in ("extrato", "ultimos", "lancamentos"):
            store("ignored")
            self._safe_live_reply(chat, self._statement_text())
            return "Extrato enviado no WhatsApp"
        if cmd in ("desfazer", "apagar", "apaga", "excluir ultimo", "cancelar ultimo"):
            store("ignored")
            return self._undo_last(chat)
        if cmd in YES or cmd in NO:
            pending = self.messages.latest(chat, "pending")
            store("ignored")
            if not pending:
                self._safe_live_reply(chat, f"{BOT_MARK} Não há lançamento aguardando confirmação.")
                return "Nada pendente"
            if cmd in YES:
                tx = self._suggestion_to_tx(interpret(pending.body, _created_date(pending.created_at)))
                saved = self.confirm(pending.id, tx)
                return f"{_kind(saved)} de {money(saved.amount_cents)} confirmada pelo WhatsApp"
            self.discard(pending.id)
            return "Sugestão descartada pelo WhatsApp"

        suggestion = interpret(m.body, ref_day)
        if suggestion is None:
            store("ignored")
            self._safe_live_reply(chat, f"{BOT_MARK} Não encontrei um valor nessa mensagem.\n"
                                   "Ex.: _Comprei um lanche foi 3 reais_ — ou envie *ajuda*.")
            return "Mensagem sem valor"
        if cfg.auto_save:
            tx = self._suggestion_to_tx(suggestion)
            saved = self.finance.save(tx)
            store("confirmed", saved.id)
            self._safe_live_reply(chat, self._saved_text(saved, undo_hint=True))
            return f"{_kind(saved)} de {money(saved.amount_cents)} registrada pelo WhatsApp"
        store("pending")
        self._safe_live_reply(chat, (
            f"{BOT_MARK} Entendi: *{'Entrada' if suggestion.kind == 'income' else 'Despesa'}* de "
            f"*{money(suggestion.amount_cents)}*\n"
            f"• {suggestion.description} ({suggestion.category}) · {date_br(suggestion.date)}\n"
            "Responda *sim* para salvar ou *não* para descartar."))
        return f"Sugestão de {money(suggestion.amount_cents)} aguardando confirmação"

    def _suggestion_to_tx(self, s: Optional[TransactionSuggestion]) -> Transaction:
        if s is None:
            raise ValueError("Mensagem sem valor reconhecível.")
        category = s.category if s.category in categories_for(s.kind) else "Outros"
        return self.finance.build(s.kind, s.description, f"{s.amount_cents / 100:.2f}", category, s.date,
                                  source="whatsapp")

    def _undo_last(self, chat: str) -> str:
        last = self.messages.latest(chat, "confirmed", with_transaction=True)
        tx = self.finance.get(last.transaction_id) if last else None
        if not last or not tx:
            self._safe_live_reply(chat, f"{BOT_MARK} Não há lançamento recente do WhatsApp para desfazer.")
            return "Nada para desfazer"
        self.finance.delete(tx.id)
        self.messages.set_status(last.id, "discarded")
        self._safe_live_reply(chat, f"{BOT_MARK} ↩️ Desfeito: {tx.description} — {money(tx.amount_cents)}.\n"
                               f"💰 Saldo atual: *{money(self.finance.overall().balance_cents)}*")
        return f"Lançamento de {money(tx.amount_cents)} desfeito pelo WhatsApp"

    def _saved_text(self, tx: Transaction, undo_hint: bool) -> str:
        text = (f"{BOT_MARK} ✅ *{_kind(tx)} registrada*\n"
                f"• {tx.description} — *{money(tx.amount_cents)}*\n"
                f"• {tx.category} · {date_br(tx.date)}\n\n"
                f"💰 Saldo atual: *{money(self.finance.overall().balance_cents)}*")
        if undo_hint:
            text += "\n_Errou? Responda *desfazer*._"
        return text

    def _balance_text(self) -> str:
        today = date.today()
        month = self.finance.month_summary(today.year, today.month)
        return (f"{BOT_MARK} 💰 *Saldo atual: {money(self.finance.overall().balance_cents)}*\n"
                f"{MONTHS[today.month - 1].capitalize()}: entradas {money(month.income_cents)} · "
                f"despesas {money(month.expense_cents)}")

    def _statement_text(self) -> str:
        today = date.today()
        items = self.finance.list_month(today.year, today.month)[:6]
        if not items:
            return f"{BOT_MARK} Nenhum lançamento em {MONTHS[today.month - 1]}."
        lines = [f"{BOT_MARK} *Últimos lançamentos*"]
        for tx in items:
            sign = "+" if tx.is_income else "−"
            lines.append(f"{tx.date.strftime('%d/%m')} {sign} {money(tx.amount_cents)} · {tx.description}")
        lines.append(f"\n💰 Saldo atual: *{money(self.finance.overall().balance_cents)}*")
        return "\n".join(lines)

    # ---------- histórico ----------
    def history(self) -> list[ChatItem]:
        items = []
        for msg in self.messages.recent():
            suggestion = None
            if msg.direction == "in" and msg.status == "pending":
                ref = _created_date(msg.created_at)
                suggestion = interpret(msg.body, ref)
            items.append(ChatItem(msg, suggestion))
        return items

    def clear_history(self) -> None:
        self.messages.clear()

    # ---------- decisão do usuário (painel ou WhatsApp) ----------
    def confirm(self, message_id: int, transaction: Transaction) -> Transaction:
        msg = self.messages.get(message_id)
        if msg is None or msg.status != "pending":
            raise ValueError("Esta mensagem já foi processada.")
        transaction.source = "whatsapp"
        saved = self.finance.save(transaction)
        self.messages.set_status(message_id, "confirmed", saved.id)
        if _is_live(msg):
            self._safe_live_reply(msg.sender, self._saved_text(saved, undo_hint=False))
        else:
            self._reply(msg.sender, f"{_kind(saved)} registrada: {saved.description} — "
                                    f"{money(saved.amount_cents)} ({saved.category}, {date_br(saved.date)}).")
        return saved

    def discard(self, message_id: int) -> None:
        msg = self.messages.get(message_id)
        if msg is None or msg.status != "pending":
            raise ValueError("Esta mensagem já foi processada.")
        self.messages.set_status(message_id, "discarded")
        if _is_live(msg):
            self._safe_live_reply(msg.sender, f"{BOT_MARK} Ok, lançamento descartado.")
        else:
            self._reply(msg.sender, "Ok, o lançamento foi descartado.")

    # ---------- respostas ----------
    def _reply(self, to: str, body: str) -> None:
        external_id = self.gateway.send_text(to, body)
        self.messages.add(ChatMessage(external_id=external_id, direction="out", sender="bot",
                                      body=body, status="sent"))

    def _live_reply(self, to: str, body: str) -> None:
        external_id = self.live_gateway.send_text(to, body)
        self.messages.add(ChatMessage(external_id=external_id, direction="out", sender="bot",
                                      body=body, status="sent"))

    def _safe_live_reply(self, to: str, body: str) -> None:
        if self.live_gateway is None:
            return
        try:
            self._live_reply(to, body)
        except Exception as exc:  # o lançamento já foi salvo; só a resposta falhou
            log.warning("Não foi possível responder no WhatsApp: %s", exc)


def _is_live(msg: ChatMessage) -> bool:
    return msg.external_id.startswith("evo.")


def _kind(tx: Transaction) -> str:
    return "Entrada" if tx.is_income else "Despesa"


def _created_date(created_at: str) -> date:
    try:
        return datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").date()
    except (ValueError, TypeError):
        return date.today()

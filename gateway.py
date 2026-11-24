"""Camada de transporte de mensagens (arquitetura preparada para API).

``MessagingGateway`` define o contrato que qualquer provedor deve cumprir.
Nesta versão acadêmica existe somente ``SandboxGateway``: um ambiente de
testes **local** que gera payloads no mesmo formato do webhook da WhatsApp
Cloud API (Meta) e registra as respostas sem enviá-las a ninguém.

Para uma integração real, seria criada uma classe ``CloudApiGateway`` que
implementa ``send_text`` via HTTPS (token oficial, número verificado e
consentimento dos usuários) e um endpoint web que receba o webhook e o
repasse a ``parse_webhook`` — o restante do sistema não precisaria mudar.
"""
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class IncomingMessage:
    external_id: str
    sender: str
    sender_name: str
    body: str
    timestamp: int


class WebhookFormatError(ValueError):
    pass


def parse_webhook(payload: dict[str, Any]) -> list[IncomingMessage]:
    """Extrai mensagens de texto de um payload no formato da WhatsApp Cloud API.

    Estrutura esperada: ``entry[].changes[].value.messages[]`` com
    ``type == "text"``. Outros tipos (imagem, áudio, status) são ignorados.
    """
    if not isinstance(payload, dict) or payload.get("object") != "whatsapp_business_account":
        raise WebhookFormatError("Payload não é um webhook do WhatsApp Business.")
    messages: list[IncomingMessage] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value", {}) or {}
            names = {c.get("wa_id"): (c.get("profile") or {}).get("name", "") for c in value.get("contacts", []) or []}
            for msg in value.get("messages", []) or []:
                if msg.get("type") != "text":
                    continue
                body = ((msg.get("text") or {}).get("body") or "").strip()
                if not body or not msg.get("id"):
                    continue
                sender = str(msg.get("from", ""))
                messages.append(IncomingMessage(
                    external_id=str(msg["id"]),
                    sender=sender,
                    sender_name=names.get(sender, "") or sender,
                    body=body[:1000],
                    timestamp=int(msg.get("timestamp") or time.time()),
                ))
    return messages


class MessagingGateway(ABC):
    """Contrato de um provedor de mensagens."""

    name: str = "abstract"
    is_sandbox: bool = True

    @abstractmethod
    def send_text(self, to: str, body: str) -> str:
        """Envia texto e retorna o id externo da mensagem."""


class SandboxGateway(MessagingGateway):
    """Ambiente de testes: nada sai do computador."""

    name = "Sandbox local"
    is_sandbox = True
    BUSINESS_NUMBER = "5500000000000"
    TEST_CONTACT = "5500999990000"

    def __init__(self) -> None:
        self.outbox: list[tuple[str, str]] = []

    def send_text(self, to: str, body: str) -> str:
        self.outbox.append((to, body))  # registrado apenas localmente
        return f"sandbox.out.{uuid.uuid4().hex}"

    def build_incoming_payload(self, body: str, sender: str | None = None,
                               sender_name: str = "Contato de teste") -> dict[str, Any]:
        """Simula o POST que a Meta faria ao webhook quando chega uma mensagem."""
        sender = sender or self.TEST_CONTACT
        return {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "SANDBOX",
                "changes": [{
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"display_phone_number": self.BUSINESS_NUMBER, "phone_number_id": "SANDBOX"},
                        "contacts": [{"profile": {"name": sender_name}, "wa_id": sender}],
                        "messages": [{
                            "from": sender,
                            "id": f"sandbox.in.{uuid.uuid4().hex}",
                            "timestamp": str(int(time.time())),
                            "type": "text",
                            "text": {"body": body},
                        }],
                    },
                }],
            }],
        }

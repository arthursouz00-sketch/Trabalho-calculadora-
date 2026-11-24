"""Orquestra a conexão real: configuração + cliente Evolution + servidor de webhook.

O servidor de webhook é único por processo (a porta é do computador), mesmo
que o app seja aberto em várias janelas/abas.
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from app.services.whatsapp.automation import WhatsAppAutomation
from app.services.whatsapp.evolution import (
    EvolutionClient,
    EvolutionConfig,
    EvolutionError,
    EvolutionGateway,
    load_config,
    save_config,
)
from app.services.whatsapp.webhook_server import WebhookServer

log = logging.getLogger("visual_office.live")

_server_lock = threading.Lock()
_server: Optional[WebhookServer] = None
_automations: list[WhatsAppAutomation] = []


def _dispatch(payload: dict) -> None:
    for automation in list(_automations):
        automation.handle_evolution_webhook(payload)
        break  # todas as sessões compartilham o mesmo banco: processa uma vez só


class LiveWhatsApp:
    def __init__(self, settings, automation: WhatsAppAutomation):
        self.settings = settings
        self.automation = automation
        self.config: EvolutionConfig = load_config(settings)
        self.client = EvolutionClient(self.config)

    # ---------- estado ----------
    @property
    def server(self) -> Optional[WebhookServer]:
        return _server

    @property
    def listening(self) -> bool:
        return _server is not None and _server.running

    def save(self, cfg: EvolutionConfig) -> None:
        self.config = cfg
        self.client = EvolutionClient(cfg)
        save_config(self.settings, cfg)
        if self.automation.live_config is not None:
            self.automation.live_config = cfg
            self.automation.live_gateway = EvolutionGateway(self.client)

    # ---------- ciclo de vida ----------
    def activate(self) -> None:
        """Liga o recebimento: servidor de webhook + gateway de respostas."""
        global _server
        cfg = self.config
        self.automation.live_config = cfg
        self.automation.live_gateway = EvolutionGateway(self.client)
        with _server_lock:
            if _server and (_server.port != cfg.webhook_port or _server.token != cfg.token):
                _server.stop()
                _server = None
            if _server is None:
                srv = WebhookServer(cfg.webhook_port, cfg.token, _dispatch)
                srv.start()  # pode levantar RuntimeError (porta ocupada)
                _server = srv
            if self.automation not in _automations:
                _automations.insert(0, self.automation)

    def deactivate(self) -> None:
        global _server
        self.automation.live_config = None
        self.automation.live_gateway = None
        with _server_lock:
            if self.automation in _automations:
                _automations.remove(self.automation)
            if _server and not _automations:
                _server.stop()
                _server = None

    def auto_start(self) -> Optional[str]:
        """Na abertura do app: reativa se estava habilitado. Retorna erro amigável, se houver."""
        from app.utils.runtime import IS_BROWSER
        if not self.config.enabled or IS_BROWSER:
            return None
        try:
            self.activate()
        except RuntimeError as exc:
            return str(exc)
        return None

    # ---------- conexão com a Evolution ----------
    def setup(self) -> str:
        """Garante instância + webhook. Retorna o estado ('open', 'connecting', 'close')."""
        self.client.server_info()
        state = self.client.connection_state()
        if state == "not_found":
            self.client.create_instance()
            state = self.client.connection_state()
        else:
            self.client.set_webhook()
        return state

    def refresh_owner(self) -> str:
        try:
            owner = self.client.owner_number()
        except EvolutionError:
            return self.config.owner_number
        if owner and owner != self.config.owner_number:
            self.config.owner_number = owner
            save_config(self.settings, self.config)
        return owner

    def send_welcome(self) -> None:
        owner = self.refresh_owner()
        if not owner:
            raise EvolutionError("Número conectado ainda não identificado. Aguarde alguns segundos.")
        from app.services.whatsapp.automation import BOT_MARK
        text = (f"{BOT_MARK} *Visual Office conectado!*\n"
                "Escreva aqui nesta conversa (Mensagem para mim mesmo) os seus gastos e ganhos.\n"
                "Ex.: _Comprei um lanche foi 3 reais_\n"
                "Comandos: *saldo* · *extrato* · *desfazer* · *ajuda*")
        self.automation.live_gateway = self.automation.live_gateway or EvolutionGateway(self.client)
        self.automation._live_reply(owner, text)

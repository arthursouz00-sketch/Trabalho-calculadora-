"""Integração real com o WhatsApp via Evolution API (https://doc.evolution-api.com).

A Evolution API roda no seu computador (Docker) e conecta o seu número pelo
QR Code, como o WhatsApp Web. Cada mensagem gera um webhook ``messages.upsert``
que chega ao servidor local do app (``webhook_server.py``).

Por privacidade, o app só processa:
* mensagens que VOCÊ escreveu na conversa "Mensagem para mim mesmo"
  (``fromMe = true`` e a conversa é o seu próprio número); e
* opcionalmente, mensagens de números que você autorizar explicitamente.
Todas as outras conversas são ignoradas sem serem gravadas.

Somente biblioteca padrão (urllib/json) — nenhuma dependência extra.
"""
from __future__ import annotations

import base64
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Optional

from app.services.whatsapp.gateway import MessagingGateway

SETTINGS_KEY = "evolution_config"


class EvolutionError(Exception):
    """Erro com mensagem amigável para a interface."""


# ---------------------------------------------------------------- configuração
@dataclass
class EvolutionConfig:
    enabled: bool = False
    base_url: str = "http://localhost:8080"
    api_key: str = ""
    instance: str = "visual-office"
    webhook_port: int = 8765
    # endereço pelo qual o contêiner Docker enxerga este computador
    webhook_host: str = "host.docker.internal"
    token: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    auto_save: bool = True          # salva direto e permite "desfazer"; False = pede "sim"
    authorized_numbers: str = ""    # outros números permitidos (separados por vírgula)
    owner_number: str = ""          # preenchido automaticamente ao conectar

    @property
    def webhook_url(self) -> str:
        return (f"http://{self.webhook_host}:{self.webhook_port}/webhook/evolution"
                f"?token={urllib.parse.quote(self.token)}")

    def authorized_list(self) -> list[str]:
        return [only_digits(x) for x in re.split(r"[,;\n]+", self.authorized_numbers) if only_digits(x)]

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "EvolutionConfig":
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {}
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


def load_config(settings) -> EvolutionConfig:
    cfg = EvolutionConfig.from_json(settings.get(SETTINGS_KEY, ""))
    if not settings.get(SETTINGS_KEY, ""):
        settings.set(SETTINGS_KEY, cfg.to_json())  # persiste o token gerado
    return cfg


def save_config(settings, cfg: EvolutionConfig) -> None:
    settings.set(SETTINGS_KEY, cfg.to_json())


# ---------------------------------------------------------------- números
def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def jid_number(jid: str) -> str:
    """'5511987654321@s.whatsapp.net' -> '5511987654321' (vazio para grupos/LID)."""
    if not jid or "@g.us" in jid or "@broadcast" in jid or "@newsletter" in jid or "@lid" in jid:
        return ""
    return only_digits(jid.split("@")[0].split(":")[0])


def same_phone(a: str, b: str) -> bool:
    """Compara números tolerando o 9º dígito dos celulares brasileiros."""
    a, b = only_digits(a), only_digits(b)
    if not a or not b:
        return False
    if a == b:
        return True
    if a.startswith("55") and b.startswith("55") and len(a) >= 12 and len(b) >= 12:
        return a[:4] == b[:4] and a[-8:] == b[-8:]
    return False


# ---------------------------------------------------------------- webhook
@dataclass
class EvolutionMessage:
    external_id: str
    chat_number: str     # para onde a resposta deve ir
    from_me: bool
    body: str
    timestamp: int
    push_name: str = ""


def extract_text(message: dict) -> str:
    if not isinstance(message, dict):
        return ""
    return (message.get("conversation")
            or (message.get("extendedTextMessage") or {}).get("text")
            or "").strip()


def parse_evolution_webhook(payload: dict[str, Any], cfg: EvolutionConfig) -> tuple[list[EvolutionMessage], str]:
    """Filtra o webhook da Evolution. Retorna (mensagens aceitas, número do dono)."""
    if not isinstance(payload, dict):
        return [], ""
    event = str(payload.get("event", "")).lower().replace("_", ".")
    if event != "messages.upsert":
        return [], ""
    if cfg.instance and payload.get("instance") and payload.get("instance") != cfg.instance:
        return [], ""
    owner = jid_number(str(payload.get("sender", ""))) or only_digits(cfg.owner_number)
    data = payload.get("data")
    items = data if isinstance(data, list) else [data]
    accepted: list[EvolutionMessage] = []
    authorized = cfg.authorized_list()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or {}
        remote = str(key.get("remoteJid") or "")
        if "@lid" in remote and key.get("remoteJidAlt"):
            remote = str(key["remoteJidAlt"])
        chat = jid_number(remote)
        text = extract_text(item.get("message") or {})
        msg_id = str(key.get("id") or "")
        if not chat or not text or not msg_id:
            continue
        from_me = bool(key.get("fromMe"))
        self_chat = from_me and owner and same_phone(chat, owner)
        allowed_other = (not from_me) and any(same_phone(chat, n) for n in authorized)
        if not (self_chat or allowed_other):
            continue  # conversa de terceiros: ignorada, nada é gravado
        try:
            ts = int(item.get("messageTimestamp") or 0) or int(datetime.now().timestamp())
        except (TypeError, ValueError):
            ts = int(datetime.now().timestamp())
        accepted.append(EvolutionMessage(external_id=f"evo.{msg_id}", chat_number=chat, from_me=from_me,
                                         body=text[:1000], timestamp=ts, push_name=str(item.get("pushName") or "")))
    return accepted, owner


# ---------------------------------------------------------------- cliente HTTP
class EvolutionClient:
    def __init__(self, cfg: EvolutionConfig, timeout: float = 15):
        self.cfg = cfg
        self.timeout = timeout

    def _request(self, method: str, path: str, body: Optional[dict] = None,
                 query: Optional[dict] = None) -> Any:
        if not self.cfg.api_key:
            raise EvolutionError("Informe a API key da Evolution API.")
        url = self.cfg.base_url.rstrip("/") + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "apikey": self.cfg.api_key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode() or "null"
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            detail = _error_detail(exc)
            if exc.code == 401:
                raise EvolutionError("API key recusada pela Evolution API.") from None
            if exc.code == 404:
                raise EvolutionError(f"Não encontrado: {detail}") from None
            raise EvolutionError(f"Evolution API respondeu {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise EvolutionError(f"Não foi possível acessar {self.cfg.base_url} ({exc.reason}). "
                                 "A Evolution API está rodando?") from None
        except (TimeoutError, OSError) as exc:
            raise EvolutionError(f"Sem resposta da Evolution API: {exc}") from None
        except json.JSONDecodeError:
            raise EvolutionError("Resposta inválida da Evolution API.") from None

    # --- instância
    def server_info(self) -> dict:
        req = urllib.request.Request(self.cfg.base_url.rstrip("/") + "/", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except Exception as exc:
            raise EvolutionError(f"Evolution API inacessível em {self.cfg.base_url}: {exc}") from None

    def connection_state(self) -> str:
        """'open' (conectado), 'connecting', 'close' ou 'not_found'."""
        try:
            data = self._request("GET", f"/instance/connectionState/{self._inst()}")
        except EvolutionError as exc:
            if str(exc).startswith("Não encontrado"):
                return "not_found"
            raise
        return str(((data or {}).get("instance") or {}).get("state") or "close")

    def create_instance(self) -> dict:
        return self._request("POST", "/instance/create", {
            "instanceName": self.cfg.instance,
            "integration": "WHATSAPP-BAILEYS",
            "qrcode": True,
            "webhook": {"url": self.cfg.webhook_url, "byEvents": False, "base64": False,
                        "events": ["MESSAGES_UPSERT"]},
        })

    def set_webhook(self) -> dict:
        return self._request("POST", f"/webhook/set/{self._inst()}", {
            "webhook": {"enabled": True, "url": self.cfg.webhook_url, "webhookByEvents": False,
                        "webhookBase64": False, "events": ["MESSAGES_UPSERT"]},
        })

    def connect(self, phone_number: str = "") -> dict:
        """Retorna {'qr_png': bytes|None, 'pairing_code': str|None}."""
        query = {"number": only_digits(phone_number)} if only_digits(phone_number) else None
        data = self._request("GET", f"/instance/connect/{self._inst()}", query=query) or {}
        qr_png = None
        b64 = data.get("base64") or (data.get("qrcode") or {}).get("base64")
        if b64:
            try:
                qr_png = base64.b64decode(b64.split(",", 1)[-1])
            except (ValueError, TypeError):
                qr_png = None
        return {"qr_png": qr_png, "pairing_code": data.get("pairingCode")}

    def owner_number(self) -> str:
        data = self._request("GET", "/instance/fetchInstances", query={"instanceName": self.cfg.instance})
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            inst = item.get("instance") if isinstance(item.get("instance"), dict) else item
            jid = inst.get("ownerJid") or inst.get("owner") or ""
            if jid:
                return jid_number(jid)
        return ""

    def logout(self) -> None:
        self._request("DELETE", f"/instance/logout/{self._inst()}")

    # --- mensagens
    def send_text(self, number: str, text: str) -> str:
        data = self._request("POST", f"/message/sendText/{self._inst()}",
                             {"number": only_digits(number), "text": text}) or {}
        return str((data.get("key") or {}).get("id") or "")

    def _inst(self) -> str:
        return urllib.parse.quote(self.cfg.instance, safe="")


def _error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(exc.read().decode() or "{}")
        msg = (payload.get("response") or {}).get("message") or payload.get("message") or payload
        if isinstance(msg, list):
            msg = "; ".join(str(m) for m in msg)
        return str(msg)
    except Exception:
        return exc.reason or "erro"


class EvolutionGateway(MessagingGateway):
    """Envia as respostas do assistente pelo seu WhatsApp (Evolution API)."""

    name = "Evolution API"
    is_sandbox = False

    def __init__(self, client: EvolutionClient):
        self.client = client
        self.sent_ids: set[str] = set()  # evita que o app processe as próprias respostas

    def send_text(self, to: str, body: str) -> str:
        msg_id = self.client.send_text(to, body)
        if msg_id:
            self.sent_ids.add(msg_id)
        return f"evo.out.{msg_id}" if msg_id else f"evo.out.{secrets.token_hex(8)}"

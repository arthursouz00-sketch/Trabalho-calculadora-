"""Integração com a Evolution API: servidor de webhook real + Evolution simulada (mock HTTP)."""
import json
import threading
import time
import urllib.request
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.services.whatsapp.evolution import EvolutionConfig, parse_evolution_webhook, same_phone
from app.services.whatsapp.interpreter import interpret

OWNER = "5511987654321"


class FakeEvolution:
    """Imita as rotas usadas da Evolution API v2 (formatos conferidos na v2.3.8)."""

    def __init__(self):
        self.sent = []
        self.instances = {}
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _auth(self):
                if self.headers.get("apikey") != "k":
                    self._json(401, {"status": 401, "error": "Unauthorized", "response": {"message": "Unauthorized"}})
                    return False
                return True

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return json.loads(self.rfile.read(n) or b"{}")

            def do_GET(self):
                if self.path == "/":
                    return self._json(200, {"status": 200, "version": "2.3.8"})
                if not self._auth():
                    return
                name = self.path.split("/")[-1].split("?")[0]
                if self.path.startswith("/instance/connectionState/"):
                    if name not in fake.instances:
                        return self._json(404, {"status": 404, "response": {"message": ["not exist"]}})
                    return self._json(200, {"instance": {"instanceName": name, "state": "open"}})
                if self.path.startswith("/instance/fetchInstances"):
                    return self._json(200, [{"name": "visual-office", "ownerJid": f"{OWNER}@s.whatsapp.net"}])
                if self.path.startswith("/instance/connect/"):
                    return self._json(200, {"pairingCode": None, "code": "2@x", "base64": "data:image/png;base64,iVBORw0KGgo=", "count": 1})
                self._json(404, {})

            def do_POST(self):
                if not self._auth():
                    return
                body = self._body()
                if self.path == "/instance/create":
                    fake.instances[body["instanceName"]] = body
                    return self._json(201, {"instance": {"instanceName": body["instanceName"], "status": "close"}})
                if self.path.startswith("/webhook/set/"):
                    return self._json(201, body["webhook"])
                if self.path.startswith("/message/sendText/"):
                    msg_id = f"BOT{len(fake.sent)}"
                    fake.sent.append(body)
                    return self._json(201, {"key": {"remoteJid": body["number"] + "@s.whatsapp.net", "fromMe": True, "id": msg_id}})
                self._json(404, {})

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()


def evo_payload(text, msg_id, from_me=True, remote=OWNER, sender=OWNER, instance="visual-office"):
    """Corpo do webhook messages.upsert como a Evolution v2.3.8 envia."""
    return {
        "event": "messages.upsert", "instance": instance,
        "data": {"key": {"remoteJid": f"{remote}@s.whatsapp.net", "fromMe": from_me, "id": msg_id},
                 "pushName": "Você", "status": "SERVER_ACK", "message": {"conversation": text},
                 "messageType": "conversation", "messageTimestamp": int(time.time()), "source": "android"},
        "destination": "http://host.docker.internal:8765/webhook/evolution", "date_time": "2026-11-24T00:00:00.000Z",
        "sender": f"{sender}@s.whatsapp.net", "server_url": "http://localhost:8080", "apikey": "TOKEN",
    }


def test_interpret_user_example():
    s = interpret("Comprei um lanche foi 3 reais", date(2026, 11, 24))
    assert (s.kind, s.category, s.amount_cents, s.description) == ("expense", "Alimentação", 300, "Lanche")


def test_same_phone_ninth_digit():
    assert same_phone("5511987654321", "551187654321")
    assert not same_phone("5511987654321", "5521987654321")


def test_filter_only_self_chat_and_authorized():
    cfg = EvolutionConfig(instance="visual-office")
    ok, owner = parse_evolution_webhook(evo_payload("gastei 10", "A1"), cfg)
    assert len(ok) == 1 and owner == OWNER
    other = evo_payload("gastei 10", "A2", from_me=False, remote="5521911112222")
    assert parse_evolution_webhook(other, cfg)[0] == []           # terceiros: ignorado
    mine_to_friend = evo_payload("gastei 10", "A3", from_me=True, remote="5521911112222")
    assert parse_evolution_webhook(mine_to_friend, cfg)[0] == []  # minha msg para outra pessoa: ignorada
    cfg.authorized_numbers = "+55 21 91111-2222"
    assert len(parse_evolution_webhook(other, cfg)[0]) == 1       # número autorizado
    group = evo_payload("gastei 10", "A4")
    group["data"]["key"]["remoteJid"] = "1203630@g.us"
    assert parse_evolution_webhook(group, cfg)[0] == []
    assert parse_evolution_webhook(evo_payload("x 1", "A5", instance="outra"), cfg)[0] == []


@pytest.fixture
def live(services):
    fake = FakeEvolution()
    cfg = EvolutionConfig(enabled=True, base_url=f"http://127.0.0.1:{fake.port}", api_key="k",
                          instance="visual-office", webhook_port=0, token="secret")
    # porta livre para o webhook
    import socket
    s = socket.socket(); s.bind(("127.0.0.1", 0)); cfg.webhook_port = s.getsockname()[1]; s.close()
    services.live.save(cfg)
    services.live.activate()
    yield services, fake, cfg
    services.live.deactivate()
    fake.httpd.shutdown()


def post(cfg, payload, token=None):
    req = urllib.request.Request(
        f"http://127.0.0.1:{cfg.webhook_port}/webhook/evolution?token={token or cfg.token}",
        data=json.dumps(payload).encode(), method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def wait_for(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_end_to_end_auto_save_and_undo(live):
    services, fake, cfg = live
    assert services.live.setup() == "open" and "visual-office" in fake.instances
    assert post(cfg, evo_payload("Comprei um lanche foi 3 reais", "M1"), token="errado") == 401
    assert post(cfg, evo_payload("Comprei um lanche foi 3 reais", "M1")) == 200
    assert wait_for(lambda: services.finance.overall().expense_cents == 300)
    assert wait_for(lambda: len(fake.sent) == 1)
    reply = fake.sent[0]
    assert reply["number"] == OWNER and "Despesa registrada" in reply["text"] and "R$ 3,00" in reply["text"]
    # repetição do mesmo webhook e eco da resposta do bot não geram nada
    post(cfg, evo_payload("Comprei um lanche foi 3 reais", "M1"))
    post(cfg, evo_payload(reply["text"], "BOT0"))
    time.sleep(0.4)
    assert services.finance.overall().expense_cents == 300 and len(fake.sent) == 1
    # conversa de outra pessoa é ignorada e não é gravada
    post(cfg, evo_payload("me paga os 50 reais", "X9", from_me=False, remote="5521911112222"))
    # comandos
    post(cfg, evo_payload("saldo", "M2"))
    assert wait_for(lambda: len(fake.sent) == 2) and "Saldo atual" in fake.sent[1]["text"]
    post(cfg, evo_payload("Desfazer", "M3"))
    assert wait_for(lambda: services.finance.overall().expense_cents == 0)
    assert "Desfeito" in fake.sent[2]["text"]
    bodies = [m.message.body for m in services.whatsapp.history()]
    assert "me paga os 50 reais" not in bodies


def test_end_to_end_confirmation_mode(live):
    services, fake, cfg = live
    cfg.auto_save = False
    services.live.save(cfg)
    post(cfg, evo_payload("Recebi 3.500 de salário", "C1"))
    assert wait_for(lambda: len(fake.sent) == 1) and "Responda *sim*" in fake.sent[0]["text"]
    assert services.finance.overall().income_cents == 0
    post(cfg, evo_payload("Sim!", "C2"))
    assert wait_for(lambda: services.finance.overall().income_cents == 350000)
    tx = services.finance.list_month(date.today().year, date.today().month)[0]
    assert tx.source == "whatsapp" and tx.category == "Salário"


def test_welcome_message(live):
    services, fake, cfg = live
    services.live.send_welcome()
    assert fake.sent[-1]["number"] == OWNER and "conectado" in fake.sent[-1]["text"]

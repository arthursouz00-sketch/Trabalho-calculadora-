"""Servidor HTTP local que recebe os webhooks da Evolution API.

Roda numa thread em segundo plano enquanto o app está aberto.
Rotas:
    POST /webhook/evolution?token=...   (eventos da Evolution API)
    GET  /health                         (teste rápido no navegador)
O token na URL impede que outra pessoa da rede injete mensagens.
"""
from __future__ import annotations

import hmac
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

log = logging.getLogger("visual_office.webhook")
MAX_BODY = 2 * 1024 * 1024


class WebhookServer:
    def __init__(self, port: int, token: str, handler: Callable[[dict[str, Any]], None],
                 host: str = "0.0.0.0"):
        self.port = port
        self.token = token
        self.handler = handler
        self.host = host
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.last_event_at: Optional[str] = None
        self.received = 0

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self) -> None:
        if self._httpd:
            return
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):  # silencia o log padrão
                log.debug("webhook: " + fmt, *args)

            def _reply(self, code: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if urlparse(self.path).path == "/health":
                    self._reply(200, {"status": "ok", "app": "Visual Office Manager", "received": server.received})
                else:
                    self._reply(404, {"error": "not found"})

            def do_POST(self):
                url = urlparse(self.path)
                if not url.path.startswith("/webhook/evolution"):
                    self._reply(404, {"error": "not found"})
                    return
                token = (parse_qs(url.query).get("token") or [""])[0]
                if not hmac.compare_digest(token, server.token):
                    self._reply(401, {"error": "invalid token"})
                    return
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_BODY:
                    self._reply(400, {"error": "invalid body"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                except (ValueError, UnicodeDecodeError):
                    self._reply(400, {"error": "invalid json"})
                    return
                self._reply(200, {"status": "received"})  # responde rápido; processa em seguida
                server.received += 1
                from datetime import datetime
                server.last_event_at = datetime.now().strftime("%H:%M:%S")
                try:
                    server.handler(payload)
                except Exception:
                    log.exception("Falha ao processar webhook")

        try:
            self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        except OSError as exc:
            self._httpd = None
            raise RuntimeError(f"Não foi possível abrir a porta {self.port}: {exc}") from exc
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="evolution-webhook", daemon=True)
        self._thread.start()
        log.info("Webhook escutando em %s:%s", self.host, self.port)

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None

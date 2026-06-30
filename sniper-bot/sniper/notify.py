"""Alertas via Telegram (opcional).

Se TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID estiverem vazios, vira no-op.
Como criar:
  1. Fale com @BotFather no Telegram -> /newbot -> copie o token.
  2. Mande uma mensagem pro seu bot e pegue o chat_id em
     https://api.telegram.org/bot<TOKEN>/getUpdates (campo "chat":{"id":...}).
"""

from __future__ import annotations

import logging
import urllib.parse
import urllib.request

log = logging.getLogger("sniper.notify")


class Notifier:
    def __init__(self, token: str, chat_id: str):
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)
        if self.enabled:
            log.info("Alertas Telegram habilitados.")

    def send(self, text: str) -> None:
        if not self.enabled:
            return
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": self.chat_id, "text": text}).encode()
        try:
            # Falha de rede nunca deve derrubar o bot — apenas loga.
            with urllib.request.urlopen(url, data=data, timeout=5) as resp:
                resp.read()
        except Exception as exc:  # noqa: BLE001
            log.warning("Falha ao enviar Telegram: %s", exc)

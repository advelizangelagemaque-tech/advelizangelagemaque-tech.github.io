"""Alerta via Telegram (só usa urllib — sem dependência extra).

O token e o chat_id NUNCA entram no código/git. Ficam em variáveis de ambiente
(TELEGRAM_TOKEN / TELEGRAM_CHAT_ID) ou no arquivo .env.telegram (que está no
.gitignore), só na EC2. Este módulo manda mensagem e descobre o chat_id.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request

DEFAULT_ENV = os.path.join(os.path.dirname(__file__), "..", ".env.telegram")


# ---- parsing puro (testável) -----------------------------------------------

def parse_env(text: str) -> dict:
    """Lê 'CHAVE=valor' por linha (ignora vazias e #)."""
    conf = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        conf[k.strip()] = v.strip()
    return conf


def parse_chat_id(payload: dict):
    """Pega o chat_id mais recente da resposta do getUpdates."""
    for upd in reversed(payload.get("result", [])):
        msg = upd.get("message") or upd.get("edited_message") or upd.get("channel_post")
        if msg and "chat" in msg:
            return msg["chat"]["id"]
    return None


def upsert_lines(lines: list[str], key: str, value) -> list[str]:
    """Substitui a linha 'KEY=...' (ou acrescenta) — puro, testável."""
    out, found = [], False
    for ln in lines:
        if ln.strip().startswith(key + "="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{key}={value}")
    return out


def save_env(env_path: str, key: str, value) -> None:
    try:
        with open(env_path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        lines = []
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(upsert_lines(lines, key, value)) + "\n")


def get_config(env_path: str = DEFAULT_ENV) -> tuple:
    """(token, chat_id) — da variável de ambiente ou do .env.telegram."""
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        try:
            with open(env_path, encoding="utf-8") as f:
                conf = parse_env(f.read())
            token = token or conf.get("TELEGRAM_TOKEN")
            chat = chat or conf.get("TELEGRAM_CHAT_ID")
        except FileNotFoundError:
            pass
    return token, chat


# ---- rede (I/O) ------------------------------------------------------------

def send_message(token: str, chat_id, text: str) -> dict:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    with urllib.request.urlopen(url, data=data, timeout=15) as r:  # noqa: S310
        return json.load(r)


def fetch_chat_id(token: str):
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    with urllib.request.urlopen(url, timeout=15) as r:  # noqa: S310
        return parse_chat_id(json.load(r))


def main() -> int:
    p = argparse.ArgumentParser(description="Utilitário de alerta Telegram.")
    p.add_argument("--get-chat-id", action="store_true",
                   help="Descobre seu chat_id (mande um 'oi' pro bot ANTES).")
    p.add_argument("--test", action="store_true", help="Manda uma mensagem de teste.")
    args = p.parse_args()
    token, chat = get_config()
    if not token:
        print("Sem TELEGRAM_TOKEN. Crie o .env.telegram na EC2 (veja instruções).")
        return 1
    if args.get_chat_id:
        cid = fetch_chat_id(token)
        if cid is None:
            print("Não achei mensagem. Mande um 'oi' pro seu bot no Telegram e rode de novo.")
            return 1
        save_env(DEFAULT_ENV, "TELEGRAM_CHAT_ID", cid)
        print(f"✅ Seu chat_id é {cid} — já salvei no .env.telegram. Agora rode --test.")
        return 0
    if args.test:
        if not chat:
            print("Falta TELEGRAM_CHAT_ID. Rode --get-chat-id primeiro.")
            return 1
        r = send_message(token, chat, "✅ Teste do vigia: o alerta do Telegram está funcionando!")
        print("Enviado!" if r.get("ok") else f"Falhou: {r}")
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

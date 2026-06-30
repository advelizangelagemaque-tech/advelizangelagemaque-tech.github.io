"""Detecção automática de tokens recém-criados na Solana.

Assina os logs de um programa (pump.fun por padrão) via WebSocket
(`logsSubscribe`). Quando detecta um evento de criação, busca a transação e
extrai o endereço (mint) do token novo.

A lógica de parsing é pura e testável; a parte de rede (websockets) é fina e
deve ser validada por você em devnet/mainnet.
"""

from __future__ import annotations

import json
import logging

from .config import WSOL_MINT

log = logging.getLogger("solana_sniper.listener")

# Programas conhecidos e o marcador de "criação" nos logs.
PROGRAMS = {
    "pump": {
        "id": "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",
        "markers": ("Instruction: Create",),
    },
    "raydium": {
        "id": "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
        "markers": ("initialize2", "InitializeInstruction2"),
    },
}


def ws_url_from_rpc(rpc_url: str) -> str:
    """Converte a URL HTTP do RPC na URL WebSocket correspondente."""
    if rpc_url.startswith("https://"):
        return "wss://" + rpc_url[len("https://"):]
    if rpc_url.startswith("http://"):
        return "ws://" + rpc_url[len("http://"):]
    return rpc_url


def is_create_event(logs: list[str], markers: tuple[str, ...]) -> bool:
    """True se algum log indica criação de token/pool para o programa."""
    return any(any(m in line for m in markers) for line in (logs or []))


def extract_mint_from_tx(tx_result: dict) -> str | None:
    """Extrai o mint do token novo a partir dos saldos pós-transação."""
    meta = (tx_result or {}).get("meta") or {}
    for bal in meta.get("postTokenBalances") or []:
        mint = bal.get("mint")
        if mint and mint != WSOL_MINT:
            return mint
    return None


def mint_from_notification(rpc, msg: dict, markers: tuple[str, ...]) -> tuple[str, str] | None:
    """Processa uma notificação `logsNotification` e retorna (mint, assinatura)."""
    if msg.get("method") != "logsNotification":
        return None
    value = (((msg.get("params") or {}).get("result")) or {}).get("value") or {}
    if value.get("err"):
        return None
    if not is_create_event(value.get("logs", []), markers):
        return None
    sig = value.get("signature")
    if not sig:
        return None
    mint = extract_mint_from_tx(rpc.get_transaction(sig))
    return (mint, sig) if mint else None


def _subscribe_message(program_id: str) -> str:
    return json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "logsSubscribe",
        "params": [{"mentions": [program_id]}, {"commitment": "processed"}],
    })


class PoolListener:
    """Ouve novos tokens e chama `on_mint(mint, signature)` para cada um."""

    def __init__(self, rpc, ws_url: str, program: str = "pump"):
        if program not in PROGRAMS:
            raise ValueError(f"Programa desconhecido: {program} (use {list(PROGRAMS)}).")
        self.rpc = rpc
        self.ws_url = ws_url
        self.program = PROGRAMS[program]

    async def run(self, on_mint) -> None:
        import websockets  # import tardio: só exigido para ouvir ao vivo
        async with websockets.connect(self.ws_url, ping_interval=20) as ws:
            await ws.send(_subscribe_message(self.program["id"]))
            ack = await ws.recv()
            log.info("Inscrito nos logs de %s (%s).", self.program["id"], ack[:60])
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                try:
                    found = mint_from_notification(self.rpc, msg, self.program["markers"])
                except Exception as exc:  # noqa: BLE001
                    log.error("Erro ao processar notificação: %s", exc)
                    continue
                if found:
                    mint, sig = found
                    log.warning("NOVO TOKEN detectado: %s (tx %s)", mint, sig[:16])
                    await on_mint(mint, sig)

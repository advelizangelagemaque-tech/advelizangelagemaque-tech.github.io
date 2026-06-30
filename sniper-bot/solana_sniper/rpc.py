"""Cliente JSON-RPC mínimo para a Solana (sem dependências externas)."""

from __future__ import annotations

import json
import urllib.request

PUBLIC_RPC = {
    "devnet": "https://api.devnet.solana.com",
    "mainnet": "https://api.mainnet-beta.solana.com",
}


class SolanaRPC:
    def __init__(self, url: str):
        self.url = url

    def call(self, method: str, params: list, timeout: int = 10) -> dict:
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": method, "params": params,
        }).encode()
        req = urllib.request.Request(
            self.url, data=payload, headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        if "error" in data:
            raise RuntimeError(f"RPC error: {data['error']}")
        return data.get("result", {})

    def get_account_info(self, pubkey: str) -> dict:
        """Conta com dados já parseados (jsonParsed)."""
        return self.call("getAccountInfo", [pubkey, {"encoding": "jsonParsed"}])

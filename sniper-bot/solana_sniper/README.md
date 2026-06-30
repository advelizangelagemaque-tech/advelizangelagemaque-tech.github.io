# 🧪 Solana Sniper — EXPERIMENTAL (leia antes de tudo)

Módulo **separado e experimental** para sniping on-chain na Solana. Está aqui
de forma **responsável**: as partes seguras (checagem de honeypot, carteira-isca,
cotação) já funcionam; a **execução de swap** está propositalmente desativada até
você validar em **devnet**.

> 🔴 **Por que tanto cuidado?**
> On-chain, o bot precisa de uma **chave privada** para assinar transações.
> Foi isso que tornou perigoso o bot fechado de terceiros. Aqui o código é
> **seu e aberto**, mas o risco técnico continua real. Regras inegociáveis:
>
> 1. **Carteira-isca (burner):** crie uma carteira NOVA, só para o bot, com
>    **apenas o valor que pode perder**. NUNCA use sua carteira/seed principal.
> 2. **Devnet primeiro:** `NETWORK=devnet`. Mainnet só com `ALLOW_MAINNET=true`
>    setado de propósito.
> 3. **Limite de gasto:** `MAX_SPEND_SOL` limita quanto o bot pode usar.
> 4. A chave da burner fica num arquivo **`chmod 600`**, fora do Git.

## O que já funciona

- **`safety.py`** — checagem de honeypot via RPC: detecta **mint authority**
  (supply pode ser inflado) ou **freeze authority** (podem *congelar* seus
  tokens — a armadilha "compra e não vende"). Recusa tokens arriscados.
- **`rpc.py`** — cliente JSON-RPC mínimo (sem dependências).
- **`wallet.py`** — carrega a carteira-isca e **bloqueia mainnet** por padrão.
- **`execute.py`** — fluxo completo de swap: cotação (Jupiter) → montagem da
  transação → **assinatura com `solders`** → envio → confirmação, com teto de
  gasto e dry-run.

## Instalar e usar

```bash
pip install -r requirements-solana.txt     # solders/solana
solana-keygen new -o ~/.config/solana/burner.json   # carteira-isca
chmod 600 ~/.config/solana/burner.json
# (devnet) pegue SOL de faucet: solana airdrop 1 <pubkey> --url devnet
```

```bash
# 1) SEMPRE simule primeiro (checa segurança + cota, não envia):
python -m solana_sniper.main --mint <ENDERECO_DO_TOKEN> --amount-sol 0.01 --dry-run

# 2) Executa de verdade (devnet por padrão):
python -m solana_sniper.main --mint <ENDERECO_DO_TOKEN> --amount-sol 0.01
```

A compra é **abortada** se a checagem de segurança reprovar (use `--force` para
ignorar, o que é perigoso). Em mainnet, exige `ALLOW_MAINNET=true` de propósito.

## Auto-snipe (detecção automática) 🤖

Ouve novos tokens em tempo real (pump.fun por padrão) via WebSocket, checa o
anti-honeypot e compra automaticamente:

```bash
# SEMPRE comece simulando (detecta + checa segurança, não compra):
python -m solana_sniper.autosnipe --dry-run

# Compra de verdade (devnet por padrão), no máximo 1 token:
python -m solana_sniper.autosnipe --amount-sol 0.01 --max-trades 1

# Fonte alternativa de listagens:
python -m solana_sniper.autosnipe --program raydium --dry-run
```

Cada token novo passa pela mesma checagem de segurança: se tiver mint/freeze
authority ativa, é **pulado** automaticamente. Encerra após `--max-trades`.

> 🔴 Auto-snipe na **mainnet** compra sozinho, no instante do lançamento, sem
> você revisar cada token. Rode bastante em **devnet/`--dry-run`** antes, e
> mantenha `MAX_SPEND_SOL` baixo. O risco de comprar um rug é real.

## Configuração (`.env`)

```ini
NETWORK=devnet                       # devnet (padrão) ou mainnet
ALLOW_MAINNET=false                  # trava de segurança extra
SOLANA_RPC_URL=                      # ex.: Helius/QuickNode; vazio = RPC público
BURNER_KEYPAIR_PATH=~/.config/solana/burner.json
MAX_SPEND_SOL=0.05                   # teto de gasto por operação
SLIPPAGE_BPS=100                     # tolerância de slippage (100 = 1%)
```

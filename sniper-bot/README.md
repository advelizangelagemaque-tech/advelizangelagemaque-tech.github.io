# Sniper Bot — Binance Futures (USDⓈ-M)

Bot de "sniper de listagem" para **Binance Futures**. Ele monitora a exchange,
detecta quando um **novo contrato passa a ser negociável** e abre uma posição
automaticamente, com **stop-loss e take-profit obrigatórios**.

> ⚠️ **AVISO IMPORTANTE**
> - Trading automatizado tem **risco real de perda total**. Não existe garantia de lucro.
> - **Comece SEMPRE na testnet** (`USE_TESTNET=true`). Só passe pra real depois de testar muito.
> - **NUNCA** habilite permissão de **saque** na API key. Use apenas *Enable Futures*.
> - Restrinja a API key por **IP** no painel da Binance.
> - Este repositório é **público**. Antes de usar dinheiro real, **mova para um repositório privado**.
> - Verifique a **tributação** (IN RFB 1.888) e regras da CVM / Lei 14.478/22 no Brasil.

## Como funciona

1. Tira um "retrato" (snapshot) dos símbolos já existentes na Binance Futures.
2. Fica em loop checando `exchangeInfo` rapidamente.
3. Quando aparece um **símbolo novo com status `TRADING`**, ele:
   - define a alavancagem,
   - calcula o tamanho da posição a partir de uma **margem fixa em USDT**,
   - abre uma ordem a **mercado**,
   - registra **stop-loss** e **take-profit** (`reduceOnly`).
4. Tudo isso respeitando os filtros de preço/quantidade do símbolo.

## Instalação

```bash
cd sniper-bot
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # depois edite o .env com suas chaves de TESTNET
```

Gere chaves de **testnet de futuros** em: https://testnet.binancefuture.com

## Uso

Escolha o **modo de detecção** (`--mode poll` REST ou `--mode ws` WebSocket) e o
**modo de operação** (`--paper`, `--dry-run`, ou live):

```bash
# 1) Dry-run: só mostra a intenção, não registra nada — entender o fluxo:
python -m sniper.main --dry-run

# 2) PAPER-TRADING (recomendado p/ validar a estratégia):
#    simula a entrada e acompanha TP/SL com preço REAL, gravando tudo em trades.csv
python -m sniper.main --paper --mode ws
python -m sniper.main --paper --mode poll   # se o WebSocket falhar na sua versão da lib

# 3) LIVE na testnet (envia ordens reais na testnet): USE_TESTNET=true no .env
python -m sniper.main --mode ws

# 4) LIVE em produção (dinheiro real) — só depois de muito paper/testnet:
#    USE_TESTNET=false no .env. Recomendado: repositório PRIVADO.
python -m sniper.main --mode ws
```

### Diário de operações (`trades.csv`)

Nos modos `--paper` e live, cada trade vira linhas no CSV (`OPEN` → `WIN`/`LOSS`),
com PnL em USDT e em % da margem. Abra no Excel/Sheets para medir o desempenho
**antes** de arriscar dinheiro real.

### Detecção: poll vs ws

- `--mode poll`: consulta `exchangeInfo` por REST a cada `POLL_INTERVAL_MS`. Simples e robusto.
- `--mode ws`: assina o WebSocket `!ticker@arr` e reage no instante em que o símbolo aparece — mais rápido. A API de WebSocket varia entre versões da lib; se der erro, use `poll`.

## Configuração (`.env`)

Veja `.env.example`. Principais parâmetros:

| Variável | O que é |
|---|---|
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | suas chaves (testnet ou real) |
| `USE_TESTNET` | `true` usa a testnet de futuros |
| `MARGIN_USDT` | quanto de margem (USDT) usar por entrada |
| `LEVERAGE` | alavancagem (cuidado: amplifica perdas) |
| `TAKE_PROFIT_PCT` | alvo de lucro, ex. `0.10` = +10% no preço |
| `STOP_LOSS_PCT` | perda máxima, ex. `0.05` = -5% no preço |
| `POLL_INTERVAL_MS` | frequência de checagem (ms) |
| `QUOTE_ASSET` | só snipa pares com essa moeda de cotação (ex. `USDT`) |

## Estrutura

```
sniper-bot/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
└── sniper/
    ├── __init__.py
    ├── config.py       # carrega configuração do .env
    ├── client.py       # cliente Binance Futures (testnet/real)
    ├── detector.py     # detecção via REST polling (PollDetector)
    ├── ws_detector.py  # detecção via WebSocket (WSDetector)
    ├── risk.py         # tamanho de posição + arredondamento de filtros
    ├── trader.py       # envia ordens (entrada + TP + SL) / paper / dry
    ├── journal.py      # diário de operações em CSV (PnL)
    └── main.py         # loop principal
```

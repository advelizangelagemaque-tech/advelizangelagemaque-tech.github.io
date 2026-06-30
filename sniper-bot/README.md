# Sniper Bot — Binance Futures (USDⓈ-M)

Bot de "sniper de listagem" para **Binance Futures**. Ele monitora a exchange,
detecta quando um **novo contrato passa a ser negociável** e abre uma posição
automaticamente, com **stop-loss e take-profit obrigatórios**.

> 📘 **Novo por aqui?** Siga o **[GUIA passo a passo](GUIA.md)** (com fluxograma em `docs/fluxo.svg`).
> ☁️ **Rodar 24h na AWS?** Veja o **[DEPLOY-AWS](DEPLOY-AWS.md)** (EC2 + systemd).

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

### Resumo de desempenho

Depois de rodar em paper-trading, veja as estatísticas da estratégia:

```bash
python -m sniper.summary            # lê trades.csv
python -m sniper.summary trades.csv
```
Mostra: trades fechados, taxa de acerto, PnL total, média de ganho/perda,
expectativa por trade e profit factor.

Para um **painel visual** (HTML offline com curva de PnL):

```bash
python -m sniper.dashboard            # gera dashboard.html a partir do trades.csv
```

Ou um **painel web ao vivo** (atualiza sozinho no navegador):

```bash
python -m sniper.webpanel             # http://SEU_IP:8080  (libere a porta no firewall)
```

### Outras exchanges (Bybit, OKX, ...)

Defina `EXCHANGE=bybit` (ou `okx`, etc.) no `.env`. A Binance usa o conector
nativo (com WebSocket); as demais entram via `ccxt` em modo polling. O modelo
de segurança é o mesmo: **API key sem permissão de saque**.

### Solana (experimental)

Há um módulo **separado e experimental** em [`solana_sniper/`](solana_sniper/README.md)
com checagem de honeypot e carteira-isca. A execução de swap vem **desativada**
por segurança — leia o README dele antes de qualquer coisa.

### Filtro de qualidade

Antes de cada entrada, o bot checa o **livro de ofertas** (profundidade e spread)
e, opcionalmente, o volume 24h. Listagens com livro raso ou spread enorme são
**puladas** (registradas como `SKIPPED` no diário). Configure no `.env`:
`MAX_SPREAD_PCT`, `MIN_BOOK_DEPTH_USDT`, `MIN_QUOTE_VOLUME` (0 desliga cada um).

### Trailing stop, cooldown e alertas

- **Trailing stop** (`USE_TRAILING=true`): em vez de alvo fixo, protege o lucro
  deixando o preço correr e só sai quando ele recua `TRAILING_CALLBACK_PCT` a
  partir do pico. No modo live vira uma ordem `TRAILING_STOP_MARKET`; o
  stop-loss "duro" continua valendo como proteção.
- **Cooldown** (`COOLDOWN_SECONDS`): espera N segundos entre uma entrada e a
  próxima. Entradas durante o cooldown viram `SKIPPED` no diário.
- **Alertas Telegram** (`TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`): avisa quando
  o bot inicia, entra e sai de uma operação. Vazio = desligado.

### Detecção: poll vs ws

- `--mode poll`: consulta `exchangeInfo` por REST a cada `POLL_INTERVAL_MS`. Simples e robusto.
- `--mode ws`: assina o WebSocket `!ticker@arr` e reage no instante em que o símbolo aparece — mais rápido. A API de WebSocket varia entre versões da lib; se der erro, use `poll`.

## Testes

```bash
pip install -r requirements-dev.txt
pytest
```
A suíte (47 testes) cobre cálculo de risco, detecção de listagens, filtro de
qualidade, saída por TP/SL e trailing stop, diário/resumo, validação de config
e o Trader (dry/paper/live) — tudo com dublês, **sem rede e sem chaves**.

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
    ├── quality.py      # filtro de qualidade (liquidez/spread)
    ├── position.py     # saída por TP/SL ou trailing stop (paper)
    ├── trader.py       # envia ordens (entrada + SL + TP/trailing) / paper / dry
    ├── journal.py      # diário de operações em CSV (PnL)
    ├── notify.py       # alertas Telegram (opcional)
    ├── summary.py      # resumo de desempenho do diário
    └── main.py         # loop principal
```

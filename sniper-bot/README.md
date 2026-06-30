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

```bash
# 1) Simulação total (não envia ordem nenhuma) — comece por aqui:
python -m sniper.main --dry-run

# 2) Testnet de verdade (envia ordens na testnet):
#    deixe USE_TESTNET=true no .env e rode:
python -m sniper.main

# 3) Produção (dinheiro real) — só depois de validar tudo:
#    USE_TESTNET=false no .env. Recomendado: repositório privado.
python -m sniper.main
```

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
    ├── config.py      # carrega configuração do .env
    ├── client.py      # cliente Binance Futures (testnet/real)
    ├── detector.py    # detecta listagens novas
    ├── risk.py        # tamanho de posição + arredondamento de filtros
    ├── trader.py      # envia ordens (entrada + TP + SL)
    └── main.py        # loop principal
```

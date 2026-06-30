# 📘 Guia passo a passo — do zero ao paper-trading

Guia prático para você (Elizângela) rodar o sniper com segurança. Siga na ordem.
O fluxo visual completo está em [`docs/fluxo.svg`](docs/fluxo.svg).

> 🔒 **Regra de ouro:** testnet primeiro. Dinheiro real só depois de o
> paper-trading mostrar resultado bom e consistente — e em repositório privado.

---

## Passo 1 — Criar as chaves na TESTNET 🔑

A **testnet** é uma Binance "de mentira", com saldo fictício. Você testa sem
arriscar **nenhum centavo**.

1. Acesse **https://testnet.binancefuture.com**
2. Faça login (dá para entrar com GitHub/Google — é uma conta separada da real).
3. Role a página até o painel inferior e abra a aba **API Key**.
4. Clique em **Generate** / **Create**.
5. Vão aparecer dois códigos longos:

```
   ┌─────────────────────────────────────────────┐
   │  API Key    : a1b2c3d4e5..............  📋   │  ← copie
   │  Secret Key : z9y8x7w6v5..............  📋   │  ← copie (só aparece 1x!)
   └─────────────────────────────────────────────┘
```

> ⚠️ A **Secret Key** só é mostrada **uma vez**. Copie as duas agora.
> Na testnet não há saque, mas mantenha o hábito: **nunca** habilite saque.

---

## Passo 2 — Configurar o `.env` ⚙️

No computador, dentro da pasta `sniper-bot`:

```bash
cp .env.example .env
```

Abra o `.env` num editor de texto e preencha:

```ini
BINANCE_API_KEY=cole_a_api_key_aqui
BINANCE_API_SECRET=cole_a_secret_aqui
USE_TESTNET=true          # << MUITO IMPORTANTE: true = testnet
MARGIN_USDT=20            # comece pequeno
LEVERAGE=3                # alavancagem baixa no começo
TAKE_PROFIT_PCT=0.10      # alvo +10%
STOP_LOSS_PCT=0.05        # perda máx 5% (obrigatório)
```

> O `.env` está protegido pelo `.gitignore` — ele **nunca** vai pro GitHub. ✅

---

## Passo 3 — Instalar 📦

```bash
cd sniper-bot
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
```

Você saberá que o ambiente está ativo quando aparecer `(venv)` no início da linha.

---

## Passo 4 — Testar ✅

Antes de rodar o bot, confirme que está tudo sadio:

```bash
pytest
```

Esperado:

```
   ........................................   48 passed ✅
```

Se aparecer tudo verde, o código está íntegro. Pode seguir.

---

## Passo 5 — Dry-run (ensaio, não envia nada) 👀

```bash
python -m sniper.main --dry-run
```

Ele **não envia ordem nenhuma** — só mostra o que faria. Serve para você ver o
fluxo e confirmar que conectou. Encerre com **Ctrl+C**.

---

## Passo 6 — Paper-trading (a parte importante) 📝

Agora o bot simula entradas de verdade e acompanha o resultado com **preço real**,
gravando tudo em `trades.csv`:

```bash
python -m sniper.main --paper --mode ws
```

```
   detecta listagem → filtra liquidez → "entra" (simulado)
        → acompanha TP/SL → grava no trades.csv
```

Deixe rodando. Cada nova listagem detectada vira uma linha no diário.
Se o WebSocket der erro na sua versão da lib, troque para `--mode poll`.

---

## Passo 7 — Analisar o desempenho 📊

De tempos em tempos (ou depois de alguns dias):

```bash
python -m sniper.summary
```

```
   ===== RESUMO DO DIÁRIO =====
   Trades fechados : 12  (WIN 7 / LOSS 5)
   Taxa de acerto  : 58.3%
   PnL total       : +18.40 USDT
   Expectativa/tr. : +1.53 USDT
   Profit factor   : 1.74
   ============================
```

**Como ler:** quer **expectativa positiva** e **profit factor > 1**. Se estiver
negativo, ajuste TP/SL, o filtro de qualidade ou o trailing — e rode mais paper.

---

## Passo 8 — (Só quando for usar dinheiro real) Repositório PRIVADO 🔒

Quando o paper-trading mostrar resultado bom **e consistente**, antes do real:

```bash
cp -r sniper-bot ~/sniper-bot && cd ~/sniper-bot
git init && git add . && git commit -m "Sniper bot"
git remote add origin git@github.com:SEU_USUARIO/sniper-bot.git   # repo PRIVATE
git push -u origin main
```

Me avise e eu **removo a pasta `sniper-bot/` daqui** (do site público).

---

## Passo 9 — LIVE (dinheiro real) 💸

```ini
USE_TESTNET=false   # no .env
```
```bash
python -m sniper.main --mode ws
```

> 🔴 **A partir daqui é dinheiro de verdade.** Comece com o **mínimo possível**.
> Risco de perda total. Nunca aporte o que você não pode perder.

---

## 🆘 Problemas comuns

| Sintoma | Causa provável | Solução |
|---|---|---|
| `BINANCE_API_KEY... não configurados` | `.env` vazio | preencha as chaves no `.env` |
| `Configuração inválida: STOP_LOSS...` | stop-loss zerado | defina `STOP_LOSS_PCT` (ex. 0.05) |
| Erro de WebSocket | versão da lib | use `--mode poll` |
| `code=-2015` | API key sem permissão/IP | habilite *Futures* e libere o IP |
| Quantidade zero | margem/preço | aumente `MARGIN_USDT` ou `LEVERAGE` |

Qualquer erro, me manda a mensagem que aparece no terminal que eu te ajudo. 🚀

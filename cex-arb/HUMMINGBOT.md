# Hummingbot — resumo honesto (pesquisa) + plano de paper trading

Notas sobre usar o [Hummingbot](https://hummingbot.org) — framework open-source e
gratuito de bots de trading — pra decidir, com os pés no chão, se vale a pena.

## O que é

- Software **open-source e gratuito** pra criar bots em **50+ corretoras** (CEX e DEX).
- Suporta **Bybit** e **Binance** (inclusive tem parceria de *fee share* com a Bybit:
  parte da taxa volta pra você, sem custo).
- Estratégias principais:
  - **Pure Market Making (PMM)** — coloca ordem de compra e de venda ao redor do
    preço e ganha o *spread*. É a mais usada por iniciantes.
  - **Cross Exchange Market Making (XEMM)** — market making usando duas corretoras.
  - **Avellaneda MM** — market making "inteligente" (ajusta spread pela volatilidade).
  - **Arbitrage / AMM Arbitrage** — compra numa e vende na outra (o que você observou).
- Tem **paper trading** (modo simulação): pra PMM, XEMM e Avellaneda **não precisa
  de chave de API** — roda com preços reais, dinheiro falso. 🎯

## A verdade (sem ilusão)

- **Market making ≠ dinheiro grátis.** Você ganha o spread, mas carrega *risco de
  inventário*: se o preço anda forte contra o seu estoque, você perde mais do que
  ganhou de spread. Funciona melhor em mercado "de lado" (sem tendência forte).
- **Paper trading INFLA o resultado.** No papel, ninguém reage às suas ordens; no
  real, outros traders/bots reagem e comem parte do lucro. Serve pra comparar
  estratégias, **não** pra prever o lucro real.
- **Trabalho de operador:** é auto-hospedado — você cuida de servidor, segurança
  de chave, e monitorar risco. Não é "liga e esquece".
- ⚠️ **Pegadinha da Bybit:** o Hummingbot pode **não funcionar com conta Unified**
  (unificada) — às vezes só com conta **básica/standard**. A nossa subconta Delta é
  Unified. Ou seja: pra testar market making na Bybit, talvez precise de outra
  subconta em modo básico. (No paper trade isso não importa — não usa chave.)

## Como isso se compara ao que a gente já tem

- Nosso `cexarb` (medidor Bybit×Binance) e o `flashloan-sim` são **medidores** —
  descobrem se existe borda. O Hummingbot é um **executor** pronto de estratégias.
- Pra **arbitragem** entre corretoras, a realidade honesta continua: spread minúsculo,
  disputado por bots rápidos. O Hummingbot não cria borda que não existe.
- O ponto **mais interessante** do Hummingbot pra iniciante não é arbitragem — é
  **market making** num par líquido, em mercado de lado. É uma estratégia real,
  porém com risco de inventário que precisa ser monitorado.

## Plano de paper trading (risco zero) — quando você quiser

1. Instalar o Hummingbot na EC2 (via Docker — eu te passo o passo a passo).
2. Ativar o **modo paper_trade** (dinheiro falso, sem chave de API).
3. Rodar **Pure Market Making** num par líquido (ex: BTC/USDT), spread pequeno.
4. Observar por alguns dias: quantas ordens preencheram, como o "estoque" oscila,
   qual o P&L simulado.
5. Só depois — e só se fizer sentido — pensar em dinheiro real, pequeno, com uma
   subconta dedicada.

## Recomendação

- **Flashbots:** anotar pra Fase 2 (execução on-chain). Não usar agora.
- **Hummingbot:** vale um **paper trading de market making** pra aprender — é a via
  mais realista pra varejo. Mas **sem tirar o foco do Delta**, que já dá lucro real.
- Antes de instalar, terminar a medição (`cexarb` e `flashsim --tri`) pra decidir
  com dados.

## Fontes

- https://hummingbot.org — site oficial
- https://hummingbot.org/exchanges/bybit/ — conector Bybit
- https://hummingbot.org/strategies/v1-strategies/pure-market-making/ — Pure Market Making
- https://hummingbot.org/client/global-configs/paper-trade/ — paper trading
- https://github.com/hummingbot/hummingbot — código-fonte

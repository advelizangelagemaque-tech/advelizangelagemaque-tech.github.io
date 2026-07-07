# market-maker-sim — simulador de market making (Fase 0)

Mede, em candles **reais**, se a estratégia de **colocar compra e venda ao redor
do preço** rende (spread) mais do que perde (estoque). **Só leitura:** sem chave,
sem login, sem mover dinheiro. Medir antes de arriscar.

## A ideia (como se ganha)

Você é o "cambista": posta uma **compra logo abaixo** e uma **venda logo acima** do
preço. No vai-e-vem, embolsa a diferença (o *spread*) — sem apostar na direção.

⚠️ **O risco:** se o preço **dispara pra um lado só**, você acumula **estoque do
lado errado** e o prejuízo do estoque come o spread. Market making adora mercado
**de lado** e sofre em **tendência forte**.

## Usar

### Demonstração (na hora, sem internet)

```bash
python -m mmsim.main --demo
```

Mostra os dois mundos: mercado de lado (lucro) vs. tendência (prejuízo de estoque).

### Preços REAIS (precisa de ccxt)

```bash
pip install ccxt
python -m mmsim.main --run BTC/USDT:USDT --tf 1m --limit 1000
# ajustar a estratégia:
python -m mmsim.main --run ETH/USDT:USDT --spread-bps 8 --order 20 --max-inv 100
```

- `--spread-bps`: spread total (10 = 0.10%)
- `--order`: tamanho de cada ordem (USDT)
- `--max-inv`: teto de estoque por lado (controla o risco)
- `--fee-bps`: taxa de maker por execução (Bybit perp ~0.02%)

## GRID de futuros (o "botzinho de grid")

O grid é a versão automática do market making: espalha ordens de compra e venda em
**níveis fixos dentro de uma faixa** e embolsa cada ida-e-volta. Em **futuros** tem
alavancagem — e aí mora o perigo: se o preço **rompe a faixa e continua**, a posição
acumula de um lado só e pode **LIQUIDAR**. Este simulador mede isso ANTES de arriscar.

```bash
# demonstração na hora (sem internet): mercado de lado x crash x alavancagem
python -m mmsim.main --grid-demo

# preços REAIS — faixa automática pelo mínimo/máximo do período:
python -m mmsim.main --grid SOL/USDT:USDT --tf 1h --limit 720 --leverage 2 --capital 100

# escolhendo a faixa na mão:
python -m mmsim.main --grid SOL/USDT:USDT --lower 140 --upper 190 --grids 30 --leverage 2
```

- `--lower/--upper`: faixa do grid (sem isso, usa o mínimo/máximo recente)
- `--grids`: número de níveis (mais níveis = passos menores, mais execuções)
- `--leverage`: **use 2x**. É futuros — alavancagem alta liquida no rompimento
- `--capital`: margem em USDT

**Lição do demo:** de lado = lucro; crash de 40% a 2x sobrevive perdendo; o **mesmo**
crash a 5x **liquida**. Por isso: alavancagem baixa (2x), faixa larga e stop. Para
operar de verdade, use o **grid nativo da Bybit** — este simulador serve para você
escolher par, faixa e alavancagem com dados na mão, não no chute.

## Honestidade

A simulação assume que a ordem **executa quando o preço TOCA** o nosso preço — na
vida real isso **superestima** as execuções (fila, competição). Serve para medir a
**ordem de grandeza** e comparar spread × estoque, **não** para prever o lucro exato.

## Testes

```bash
python -m pytest tests/ -q
```

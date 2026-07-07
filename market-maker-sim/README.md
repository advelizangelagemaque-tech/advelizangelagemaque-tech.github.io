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

## Honestidade

A simulação assume que a ordem **executa quando o preço TOCA** o nosso preço — na
vida real isso **superestima** as execuções (fila, competição). Serve para medir a
**ordem de grandeza** e comparar spread × estoque, **não** para prever o lucro exato.

## Testes

```bash
python -m pytest tests/ -q
```

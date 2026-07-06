# cex-arb — medidor de gap entre corretoras (Fase 0)

Mede, com os **livros de ordem reais** de duas corretoras (ex: Bybit e Binance),
se o "gap" de preço sobrevive às taxas — ou seja, se sobra **lucro de verdade**.
**Só leitura:** sem chave, sem login, sem mover dinheiro.

> ⚠️ Isto **não** é flash loan. Flash loan é on-chain (DeFi). Arbitragem entre
> corretoras (CEX-CEX) usa **seu próprio capital** nas duas pontas — outro
> mecanismo. Veja `../flashloan-sim` para a parte on-chain.

## O que ele mostra

Para cada par, duas colunas:
- **vitrine**: a diferença "de tela" (preços do meio) — o número que ilude.
- **real (líq)**: o spread depois de cruzar o livro (compra no ask, vende no bid)
  **e** pagar taxa dos dois lados. É o único que conta.

## Como usar

Use o Python que já tem `ccxt` (o do bot Bybit):

```bash
cd cex-arb
VENV=/home/ec2-user/advelizangelagemaque-tech.github.io/sniper-bot/venv/bin/python
$VENV -m cexarb.main
```

Opções:

```bash
# outros pares
$VENV -m cexarb.main --pairs BTC/USDT,ETH/USDT,SOL/USDT

# outra corretora no lugar da Binance (ex: OKX)
$VENV -m cexarb.main --b okx

# ajustar sua taxa real de taker (ex: 0.055%)
$VENV -m cexarb.main --fee-a 0.00055 --fee-b 0.00075
```

## Cuidados honestos (por que o gap engana)

1. **Taxa dos dois lados** (~0.1% + 0.1%): o gap precisa passar de ~0.2%.
2. **Preço executável ≠ vitrine**: você compra no ask e vende no bid.
3. **Spot vs perpétuo**: comparar perp com spot mistura o *funding* — não é arbitragem.
4. **Capital nos dois lados + velocidade**: precisa saldo nas duas e os bots
   fecham o gap em milissegundos.

## Testes

```bash
python -m pytest tests/ -q
```

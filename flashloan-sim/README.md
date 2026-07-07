# flashloan-sim — Fase 0 (só medir, nunca operar)

Simulador honesto de **arbitragem com flash loan**: mede, com preços reais das
DEXs, se sobraria lucro **depois de todas as taxas** (swap de cada DEX + taxa do
flash loan + gás). **Não envia transações, não move dinheiro, não usa chave
privada.** É o passo seguro para descobrir se existe borda de verdade **antes** de
arriscar qualquer valor — igual o backtester fez pelo bot Sniper.

## Por que Fase 0 antes de tudo

A arbitragem de flash loan é o nicho **mais competitivo** do cripto. O "gap" que
aparece na tela quase sempre é comido pelas taxas e pelo gás, e os gaps grandes o
bastante são disputados por bots profissionais **no mesmo bloco**. Este projeto
serve para **provar com números** se vale a pena — sem custo e sem risco.

## Segurança (leia)

- Este projeto é **somente leitura**. Não precisa de chave privada em lugar nenhum.
- 🚫 Nunca faça deploy de um contrato de terceiros e coloque dinheiro nele para
  "ativar" — é golpe (honeypot).
- 🚫 Nunca envie cripto para "desbloquear" um bot.
- Se algo pedir chave privada, seed, ou saque → **pare**.

## Como usar

### 1) Demonstração (roda na hora, sem internet, sem risco)

```bash
python -m flashsim.main --demo
```

Mostra cenários realistas e a lição central: gap pequeno = prejuízo; só gap grande
em rede barata sobra lucro.

### 2) Ver as redes baratas suportadas

```bash
python -m flashsim.main --list-chains
```

### 3) Escanear preços REAIS (precisa de web3 + um RPC)

```bash
pip install web3
export RPC_POLYGON=https://polygon-rpc.com     # nó público (só leitura)
cp config.example.json config.json             # já vem preenchido p/ Polygon
python -m flashsim.main --scan config.json
```

O `config.example.json` já vem com endereços **verificados na PolygonScan**
(QuickSwap e SushiSwap, duplas WMATIC/USDC.e e WETH/USDC.e). As pools são
**descobertas sozinhas** via `factory.getPair` — você não precisa colar endereço
de pool. Para vigiar outra dupla, é só adicionar em `pairs` os endereços dos dois
tokens (`usdc` e `token`).

### 4) Caça à fresta: arbitragem TRIANGULAR (em ciclo)

A arbitragem de 2 pontas (acima) só olha o mesmo par em 2 DEXs — mercados
eficientes, spread ~0. A fresta costuma estar no **loop**: base → A → B → base.
O `--tri` procura esses ciclos entre vários tokens e DEXs de uma vez:

```bash
python -m flashsim.main --tri config.tri.example.json
```

### 5) RADAR: vigiar sem parar e anotar quando acender

Frestas aparecem em **janelas de segundos** (volatilidade). O `--watch` repete a
leitura no intervalo dado e o `--log` grava as frestas positivas com data/hora:

```bash
python -m flashsim.main --tri config.tri.example.json --watch 60 --log frestas.txt
```

Deixe rodando em segundo plano; depois de dias, `frestas.txt` mostra se e quando
apareceu alguma janela real.

## Redes (foco em baratas)

| Rede      | Gás/arb ~ | Observação                         |
|-----------|-----------|------------------------------------|
| Polygon   | $0.03     | barata, muita liquidez             |
| Base      | $0.02     | barata                             |
| Arbitrum  | $0.08     | barata                             |
| Optimism  | $0.05     | barata                             |
| BNB Chain | $0.20     | flash loan às vezes 0%             |
| Ethereum  | $25       | só comparação — gás inviabiliza    |

## Testes

```bash
python -m pytest tests/ -q
```

## Próximas fases (só se a Fase 0 mostrar lucro real e repetível)

- **Fase 1:** escrever **nosso** contrato de flash loan e testar em **testnet**
  (dinheiro falso).
- **Fase 2:** mainnet/L2 com o **menor valor possível** e proteção contra MEV.

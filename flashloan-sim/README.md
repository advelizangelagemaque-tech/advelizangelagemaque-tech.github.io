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
cp config.example.json config.json             # e preencha os endereços das pools
python -m flashsim.main --scan config.json
```

Onde achar os **endereços das pools** (com segurança, só para leitura):
- No [Dexscreener](https://dexscreener.com) procure a dupla (ex: WPOL/USDC),
  escolha a DEX (QuickSwap, SushiSwap…) e copie o endereço do "par/pool".
- Confirme que os tokens batem com `usdc` e `token` do config.

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

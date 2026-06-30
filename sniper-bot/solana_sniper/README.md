# 🧪 Solana Sniper — EXPERIMENTAL (leia antes de tudo)

Módulo **separado e experimental** para sniping on-chain na Solana. Está aqui
de forma **responsável**: as partes seguras (checagem de honeypot, carteira-isca,
cotação) já funcionam; a **execução de swap** está propositalmente desativada até
você validar em **devnet**.

> 🔴 **Por que tanto cuidado?**
> On-chain, o bot precisa de uma **chave privada** para assinar transações.
> Foi isso que tornou perigoso o bot fechado de terceiros. Aqui o código é
> **seu e aberto**, mas o risco técnico continua real. Regras inegociáveis:
>
> 1. **Carteira-isca (burner):** crie uma carteira NOVA, só para o bot, com
>    **apenas o valor que pode perder**. NUNCA use sua carteira/seed principal.
> 2. **Devnet primeiro:** `NETWORK=devnet`. Mainnet só com `ALLOW_MAINNET=true`
>    setado de propósito.
> 3. **Limite de gasto:** `MAX_SPEND_SOL` limita quanto o bot pode usar.
> 4. A chave da burner fica num arquivo **`chmod 600`**, fora do Git.

## O que já funciona (seguro, read-only)

- **`safety.py`** — checagem de honeypot via RPC: detecta se o token ainda tem
  **mint authority** (supply pode ser inflado) ou **freeze authority** (podem
  *congelar* seus tokens — armadilha clássica). Recusa tokens arriscados.
- **`rpc.py`** — cliente JSON-RPC mínimo (sem dependências).
- **`wallet.py`** — carrega a carteira-isca e **bloqueia mainnet** por padrão.
- **`execute.get_quote`** — cotação de preço via Jupiter (somente leitura).

## O que está desativado (até validar em devnet)

- **`execute.execute_swap`** — assinatura e envio da transação de swap.
  Levanta `NotImplementedError` de propósito. Ativar exige a lib `solders`
  e testes em **devnet** com a carteira-isca.

## Roadmap para ligar a execução (com segurança)

1. Rodar `safety.py` contra tokens novos e validar as checagens.
2. Criar carteira-isca devnet, pegar SOL de faucet.
3. Implementar a assinatura (`solders`) e testar swaps **em devnet**.
4. Só então, com valores mínimos, considerar mainnet.

## Configuração (`.env`)

```ini
NETWORK=devnet                       # devnet (padrão) ou mainnet
ALLOW_MAINNET=false                  # trava de segurança extra
SOLANA_RPC_URL=                      # ex.: Helius/QuickNode; vazio = RPC público
BURNER_KEYPAIR_PATH=~/.config/solana/burner.json
MAX_SPEND_SOL=0.05                   # teto de gasto por operação
```
